"""Smoke test for the Cowork source — exercises baseline + emit-on-growth."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from openpets_bridge.sources.base import SourceConfig
from openpets_bridge.sources.cowork import CoworkSource


def _make_session(root: Path, sid: str, *, title: str = "Test session",
                  events: list[dict] | None = None) -> Path:
    """Create a minimal Cowork-like session layout under root."""
    session_dir = root / "host" / "run" / f"local_{sid}"
    session_dir.mkdir(parents=True, exist_ok=True)
    audit = session_dir / "audit.jsonl"
    audit.write_text("")
    (session_dir.parent / f"local_{sid}.json").write_text(
        json.dumps({"title": title, "isAgentCompleted": False})
    )
    if events:
        with audit.open("a") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
    return audit


def _cfg() -> SourceConfig:
    return SourceConfig(enabled=True, label="Cowork", icon="🤝",
                        redact_body=False, extra={})


def test_baseline_skips_existing_sessions(tmp_path: Path):
    """A session that already exists at startup must NOT emit on first poll."""
    audit = _make_session(tmp_path, "abc", events=[
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
        ]}}
    ])
    cfg = _cfg()
    cfg.extra["sessions_root"] = str(tmp_path)
    src = CoworkSource(cfg)

    # First poll = baseline only
    updates = list(src.poll())
    assert updates == [], f"first poll should baseline, got {updates}"


def test_emit_on_growth_after_baseline(tmp_path: Path):
    audit = _make_session(tmp_path, "def", events=[
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
        ]}}
    ])
    cfg = _cfg()
    cfg.extra["sessions_root"] = str(tmp_path)
    src = CoworkSource(cfg)

    list(src.poll())  # baseline

    # Append a new tool_use → file grew → next poll should emit
    with audit.open("a") as f:
        f.write(json.dumps({
            "type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Edit",
                 "input": {"file_path": "/tmp/foo.py"}}
            ]}
        }) + "\n")
    # Touch mtime to "now" so is_active picks it up
    audit.touch()

    updates = list(src.poll())
    assert len(updates) == 1, f"expected one update, got {updates}"
    u = updates[0]
    assert u.source_id == "cowork"
    assert u.session_id == "local_def"
    assert u.status == "running"
    assert "foo.py" in u.body  # body should reflect the Edit input


def test_session_id_format(tmp_path: Path):
    """session_id should be the local_<uuid> directory name."""
    _make_session(tmp_path, "xyz")
    cfg = _cfg()
    cfg.extra["sessions_root"] = str(tmp_path)
    src = CoworkSource(cfg)
    list(src.poll())  # baseline

    audit = tmp_path / "host" / "run" / "local_xyz" / "audit.jsonl"
    with audit.open("a") as f:
        f.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "echo hi"}}
        ]}}) + "\n")
    audit.touch()

    updates = list(src.poll())
    assert updates and updates[0].session_id == "local_xyz"
