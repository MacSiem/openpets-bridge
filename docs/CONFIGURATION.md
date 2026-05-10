# openpets-bridge — Configuration Guide

Three tiers: pick the one that matches how much you want to fiddle.

* **[Tier 1 — Easy](#tier-1--easy-recommended)** — one-line install, everything works out of the box.
* **[Tier 2 — Common tweaks](#tier-2--common-tweaks)** — the five things most people change.
* **[Tier 3 — Advanced](#tier-3--advanced)** — multi-pet mode, custom sources, env overrides, running without launchd.

After any change to `~/.config/openpets-bridge/config.toml`, restart the agent:

```bash
launchctl bootout gui/$(id -u)/sh.openpets.bridge
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/sh.openpets.bridge.plist
```

---

## Tier 1 — Easy (recommended)

Install [OpenPets ≥ 0.6](https://github.com/alterhq/openpets/releases/latest) (alterhq build), launch it once, then:

```bash
curl -fsSL https://raw.githubusercontent.com/MacSiem/openpets-bridge/main/install.sh | bash
```

Done. The bridge starts at login and forwards both **Cowork** and **Codex CLI** activity to your active OpenPets pet. Each conversation gets its own bubble; an icon prefix tells you which AI is talking.

Sanity check:

```bash
openpets-bridge status
```

You should see `openpets ping: pong`, `[ON ] cowork`, `[ON ] codex_cli`, and an installed launchd plist.

---

## Tier 2 — Common tweaks

Edit `~/.config/openpets-bridge/config.toml` (`open ~/.config/openpets-bridge/config.toml`). Then restart the agent (command at the top).

### 2.1 Turn an AI on or off

```toml
[sources.claude_code]
enabled = true     # was false — flip on if you actually use the `claude` CLI

[sources.codex_cli]
enabled = false    # silence Codex if Codex.app's own pet is enough for you
```

### 2.2 Privacy mode (don't show prompts/commands in the bubble)

Useful for screen-sharing, live-streaming, pair coding.

```toml
[sources.cowork]
redact_body = true       # bubble shows ONLY the tool glyph (▶ ✎ 📖 …),
                         # never the file path / shell command / search query
```

The bridge already keeps the launchd log content-free (only `status=running` lines) regardless of this flag.

### 2.3 Change the bubble icon / label per AI

Pick any single emoji — it renders as the title prefix in the OpenPets bubble.

```toml
[sources.cowork]
icon  = "💜"
label = "Maciek's Cowork"

[sources.codex_cli]
icon  = "🤖"
```

### 2.4 Switch to a different pet sprite

That's an OpenPets setting, not a bridge setting:

```bash
# 1. Install a pet pack into ~/Library/Application Support/OpenPets/Pets/<id>/
#    (the bridge already moved the legacy 'pets/' lowercase folder there)
# 2. Set it as active:
python3 -c "import json,pathlib; p=pathlib.Path.home()/'.config/openpets/config.json'; d=json.loads(p.read_text()); d['activePetID']='<your-pet-id>'; p.write_text(json.dumps(d,indent=2))"
# 3. Quit + relaunch OpenPets.app
```

### 2.5 Quiet down or speed up

```toml
[bridge]
poll_interval_s = 2.0     # default 1.0 — slower polling = lower CPU
push_throttle_s = 3.0     # default 1.5 — less chatty bubbles
```

---

## Tier 3 — Advanced

### 3.1 Multi-pet mode (one pet sprite per AI)

Each enabled source spawns its own OpenPets host on its own socket. **Beta** — works with two AIs in testing; positions of the extra pets are managed via the OpenPets tray (`positions.json`).

```toml
[bridge]
mode = "multi"

[sources.cowork.extra]
pet_dir = "~/Library/Application Support/OpenPets/Pets/mandalorian"
socket  = "/tmp/openpets-cowork.sock"

[sources.codex_cli.extra]
pet_dir = "~/.codex/pets/grogu-kid"
socket  = "/tmp/openpets-codex.sock"
```

Restart the agent. You should now have two pet sprites floating on the desktop, each with its own bubble stack.

### 3.2 Add a new AI source (Aider, OpenCode, internal orchestrator, …)

Subclass `Source` in `openpets_bridge/sources/<my_source>.py`:

```python
from openpets_bridge.sources.base import Source, SourceUpdate

class MySource(Source):
    id = "my_source"

    def poll(self):
        # Tail your agent's session log, derive (status, body) from the
        # latest activity, and yield SourceUpdate snapshots.
        for path in self._sessions_root.glob("..."):
            yield SourceUpdate(
                source_id=self.id,
                session_id="<some-stable-id>",
                title="My agent",
                body="▶ doing the thing",
                status="running",
                is_active=True,
            )
```

Register it in `openpets_bridge/sources/__init__.py` and `openpets_bridge/config.py` (`DEFAULT_SOURCES`). PRs welcome.

### 3.3 Run in the foreground (debug / no launchd)

```bash
openpets-bridge uninstall            # remove the launchd agent
openpets-bridge run                  # foreground, Ctrl-C to stop
openpets-bridge run --config /path/to/custom.toml
```

### 3.4 Custom paths (non-default Cowork install, etc.)

Each source accepts an `[sources.<id>.extra]` table that's passed to the source class. The Cowork and Codex sources accept an alternative root:

```toml
[sources.cowork.extra]
sessions_root = "/Users/me/elsewhere/local-agent-mode-sessions"

[sources.codex_cli.extra]
sessions_root = "/Volumes/External/codex/sessions"
```

### 3.5 Tail the live log (debugging)

```bash
tail -f ~/ai-stack/openpets-bridge/bridge.log
# launchd's own stdout/stderr capture:
tail -f ~/ai-stack/openpets-bridge/launchd.std{out,err}.log
```

### 3.6 Move the log somewhere else

```toml
[bridge]
log_path = "/Users/me/Logs/openpets-bridge.log"
```

### 3.7 Uninstall everything

```bash
openpets-bridge uninstall            # stops + removes launchd agent
pipx uninstall openpets-bridge       # removes the Python package
rm -rf ~/.config/openpets-bridge     # removes config (optional)
rm -rf ~/ai-stack/openpets-bridge    # removes logs (optional)
```

OpenPets.app and your pet pack(s) are untouched.

---

## Quick reference — config keys

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[bridge]` | `mode` | `"single"` | `"single"` (one pet, AI icon prefix) or `"multi"` (one pet per AI) |
| `[bridge]` | `poll_interval_s` | `1.0` | How often to scan session files |
| `[bridge]` | `push_throttle_s` | `1.5` | Minimum gap between identical pushes |
| `[bridge]` | `log_path` | `~/ai-stack/openpets-bridge/bridge.log` | Daemon log destination |
| `[sources.<id>]` | `enabled` | varies | Turn this AI source on/off |
| `[sources.<id>]` | `label` | `<source id>` | Display name (currently used in bridge logs only) |
| `[sources.<id>]` | `icon` | `"•"` / per-source default | Single emoji prefix in bubble title |
| `[sources.<id>]` | `redact_body` | `false` | Hide tool inputs from the bubble + log |
| `[sources.<id>.extra]` | `sessions_root` | per-source default | Override the watched directory |
| `[sources.<id>.extra]` | `pet_dir` *(multi only)* | — | Pet pack folder for this AI's dedicated host |
| `[sources.<id>.extra]` | `socket` *(multi only)* | `/tmp/openpets-<id>.sock` | IPC socket for this AI's dedicated host |
