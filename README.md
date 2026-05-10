# openpets-bridge

> One desktop pet for **every** AI agent on your machine.
> See Cowork, Codex CLI, Claude Code, and friends speak through one shared
> [OpenPets](https://github.com/alterhq/openpets) sprite — or one sprite per AI.

`openpets-bridge` is a small Python daemon that watches the activity logs
of multiple AI coding agents and forwards their status to OpenPets as
**threaded, persistent bubbles** (title + body + status icon, just like
Codex's built-in pet). It works whether the agent supports OpenPets
natively or not — it just tails the on-disk session files the agents
already write.

```
[🤝 Cowork] Refactor Mando bridge   ▶ python3 -m openpets_bridge run
[🟢 Codex]  Plan trial premium      ✓ Done
[🟠 Claude] Review PR #312          ❓ Waiting for your approval
```

---

## Why?

OpenPets's official Claude/OpenCode integrations only fire **brief test
pulses** (`bunx @open-pets/claude-pets test-event ...`) and the Cowork
runtime ignores Claude Code hook settings entirely. As soon as you have
more than one AI doing things on your Mac, you want:

* **One bubble per conversation** that sticks until the conversation moves
  on (using OpenPets' `notify --thread <uuid>` API)
* **A clear indication of which AI is talking** (icon prefix or a separate
  pet on the desktop)
* **Drop-in support for the agents you actually use** (Cowork, Codex CLI,
  Claude Code CLI, llm-router scripts, …) — without each agent's vendor
  shipping a separate plugin

That's it. Zero runtime dependencies (stdlib only), MIT licensed.

## Requirements

* macOS (Apple Silicon or Intel)
* [OpenPets ≥ 0.6.0](https://github.com/alterhq/openpets) (alterhq native
  Swift build — **not** the older alvinunreal Electron build)
* Python ≥ 3.10

The bridge shells out to the `openpets` CLI bundled with OpenPets.app, so
no Bun or Node toolchain is required.

## Install

```bash
pip install --user openpets-bridge   # once published to PyPI
# or, from source:
pip install --user 'git+https://github.com/MacSiem/openpets-bridge.git'

openpets-bridge init        # writes ~/.config/openpets-bridge/config.toml
openpets-bridge status      # shows enabled sources + OpenPets reachability
openpets-bridge install     # registers a launchd agent (auto-start at login)
```

## Configure

Edit `~/.config/openpets-bridge/config.toml`. The defaults already enable
Cowork and Codex CLI; flip Claude Code on if you use the `claude` CLI.

```toml
[bridge]
mode = "single"            # "single" (one pet) | "multi" (one pet per AI)

[sources.cowork]
enabled = true
icon = "🤝"
label = "Cowork"

[sources.codex_cli]
enabled = true
icon = "🟢"
label = "Codex"

[sources.claude_code]
enabled = true
icon = "🟠"
label = "Claude Code"
```

Pick whatever icon you like — single emoji works best in OpenPets bubbles.

### Single-pet vs multi-pet

| | `mode = "single"` (default) | `mode = "multi"` |
|---|---|---|
| OpenPets hosts | one shared | one per source |
| Sprite | your active OpenPets pet | one pet pack per source (configure under `[sources.*.extra]`) |
| Bubbles | stack on the same pet, prefixed with the source icon | each pet has its own bubble stack |
| Resource use | minimal | one extra Swift process per AI |
| Status | **stable** | beta — single host per pack only verified for two AIs so far |

### Adding a source

Built-in sources live in `openpets_bridge/sources/`. To support a new
agent, subclass `Source`, implement `poll()` to yield `SourceUpdate`
snapshots, and register it in `sources/__init__.py`. PRs welcome.

## How it compares

| | claude-pets | opencode-pets | **openpets-bridge** |
|---|---|---|---|
| Activates from | Claude Code hooks | OpenCode plugin | direct file tail (works with Cowork too) |
| Bubble | brief test pulse | brief test pulse | **persistent threaded** (`notify --thread`) |
| Multi-AI | no | no | **yes — one icon per AI or one pet per AI** |
| Per-conversation | no | no | **yes — threadId per session** |
| Runtime deps | Bun + Node | Bun + Node | Python 3.10 stdlib |

## Acknowledgements

* [alterhq/openpets](https://github.com/alterhq/openpets) — the native
  macOS pet host and the rich `notify` API this whole project depends on.
* [openpets.dev](https://openpets.dev) — pet packs and the canonical
  spritesheet format.

## License

MIT — see [LICENSE](LICENSE).
