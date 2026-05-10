# Contributing to openpets-bridge

Thanks for taking a look. The project is small on purpose — keep it that
way unless you have a strong reason.

## Local dev

```bash
git clone https://github.com/MacSiem/openpets-bridge.git
cd openpets-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

Run the bridge in the foreground for fast iteration:

```bash
openpets-bridge run
# Ctrl-C to stop
```

Run the tests:

```bash
pytest -q
```

Lint and typecheck:

```bash
ruff check .
mypy openpets_bridge
```

## Adding a source

A *source* is anything that emits `SourceUpdate(source_id, session_id,
title, body, status, is_active)` snapshots. To add one (e.g. for OpenCode,
Cursor, Aider, an in-house orchestrator…):

1. Create `openpets_bridge/sources/<my_source>.py`.
2. Subclass `Source`, set `id = "my_source"`, implement `poll()` as a
   generator yielding `SourceUpdate`s.
3. Register the class in `openpets_bridge/sources/__init__.py` and
   `openpets_bridge/config.py` (`DEFAULT_SOURCES`).
4. Add a test under `tests/` that synthesises an input file and asserts
   `poll()` yields the expected updates.
5. Update the README's source list and (if helpful) the comparison table.

The Cowork source is the simplest reference implementation.

## Code style

* Stdlib only — please don't add runtime dependencies.
* Type hints everywhere, mypy clean.
* `ruff format` (black-compatible).
* Privacy by default: never log bubble title or body content; never
  exfiltrate anything off the user's machine.

## Releasing

1. Bump `__version__` in `openpets_bridge/__init__.py` and the version
   field in `pyproject.toml`.
2. Update the README "Quick start" if the install flow changed.
3. Commit, tag `vX.Y.Z`, push tags. GitHub Releases is published manually
   for now.
