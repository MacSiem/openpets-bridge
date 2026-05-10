# openpets-bridge — moved

This standalone repository has been archived. The implementation lives
on as a `bridge/` subdirectory inside [**MacSiem/openpets**](https://github.com/MacSiem/openpets),
a regular GitHub fork of [**alterhq/openpets**](https://github.com/alterhq/openpets).

> All credit for OpenPets — the desktop app, the MCP server, the
> [OpenPetsKit](https://github.com/alterhq/OpenPetsKit) Swift package —
> belongs to the alterhq team. The bridge is opt-in extra glue we built
> on top of their documented `notify --thread <uuid>` API.

## Install (new path)

```bash
curl -fsSL https://raw.githubusercontent.com/MacSiem/openpets/main/bridge/install.sh | bash
```

…or via pipx:

```bash
pipx install 'openpets-bridge[menubar] @ git+https://github.com/MacSiem/openpets.git#subdirectory=bridge'
```

## Where things are now

| | New location |
|---|---|
| Code | https://github.com/MacSiem/openpets/tree/main/bridge |
| Docs | https://github.com/MacSiem/openpets/blob/main/bridge/README.md |
| Releases | https://github.com/MacSiem/openpets/releases |
| Issues | https://github.com/MacSiem/openpets/issues |

## Why the move?

The bridge is an extension on top of OpenPets — we don't modify the
upstream code, we just orchestrate it. Hosting the Python bridge inside
a real fork of upstream makes that relationship explicit (the GitHub
"forked from alterhq/openpets" badge does the framing for us), and
makes it trivial to keep our copy in sync with new OpenPets releases.

MIT licensed (same as upstream).
