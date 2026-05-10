"""OpenAI Codex CLI activity source.

Watches Codex rollout JSONL files under ``~/.codex/sessions/YYYY/MM/DD/``.
Each line is ``{"timestamp", "type", "payload": {"type", ...}}`` where
``payload.type`` is one of ``message`` / ``function_call`` / ``token_count``
/ ``task_complete`` / ``reasoning`` / ``turn_aborted`` / etc.

Mapping:
* ``function_call``  → status=running, body=tool name
* ``task_complete``  → status=done
* ``turn_aborted``   → status=failed
* ``reasoning``      → status=running, body="💭 thinking…"
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

from .base import Source, SourceUpdate


SESSIONS_ROOT = Path.home() / ".codex/sessions"
ACTIVITY_WINDOW_S = 6
IDLE_AFTER_S = 25
TAIL_BYTES = 16_384

# Codex function_call.name → (status, glyph)
TOOL_MAP: dict[str, tuple[str, str]] = {
    "shell": ("running", "▶"),
    "container_exec": ("running", "▶"),
    "view_image": ("running", "🖼"),
    "patch": ("running", "✎"),
    "apply_patch": ("running", "✎"),
    "edit": ("running", "✎"),
    "read": ("running", "📖"),
    "search": ("running", "🔎"),
    "web_search": ("running", "🔎"),
    "browser": ("running", "🌐"),
    "browser_open_url": ("running", "🌐"),
    "notify": ("running", "🔔"),
}


def _truncate(s: str, n: int = 60) -> str:
    s = s.strip().replace("\n", " ")
    return s if len(s) <= n else (s[: n - 1] + "…")


def _tail_jsonl(path: Path, n: int = 8) -> list[dict]:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - TAIL_BYTES))
            chunk = f.read()
        text = chunk.decode("utf-8", errors="replace")
        out: list[dict] = []
        for line in text.split("\n")[-n - 1:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return out[-n:]
    except OSError:
        return []


def _derive(events: list[dict]) -> tuple[str, str, bool]:
    """Return (status, body, terminal) — terminal=True for done/failed end states."""
    for ev in reversed(events):
        p = ev.get("payload") or {}
        ptype = p.get("type")
        if ptype == "task_complete":
            return "done", "✓ Done", True
        if ptype == "turn_aborted":
            return "failed", "⚠ Aborted", True
        if ptype == "function_call":
            tool = p.get("name", "") or ""
            status, glyph = TOOL_MAP.get(tool.lower(), ("running", "•"))
            args_raw = p.get("arguments", "")
            short = ""
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                if isinstance(args, dict):
                    short = (
                        args.get("command")
                        or args.get("cmd")
                        or args.get("path")
                        or args.get("file_path")
                        or args.get("query")
                        or args.get("url")
                        or ""
                    )
                    if isinstance(short, list):
                        short = " ".join(str(x) for x in short)
            except (json.JSONDecodeError, TypeError):
                pass
            body = f"{glyph} {_truncate(str(short))}".strip() if short else glyph
            return status, body, False
        if ptype == "reasoning":
            return "running", "💭 thinking…", False
        if ptype == "message":
            return "running", "💬 replying…", False
    return "running", "💭 working…", False


class CodexCliSource(Source):
    id = "codex_cli"

    def __init__(self, config) -> None:
        super().__init__(config)
        root = (self.config.extra or {}).get("sessions_root", str(SESSIONS_ROOT))
        self._sessions_root = Path(root)
        self._state: dict[Path, tuple[float, int, bool]] = {}

    def poll(self) -> Iterable[SourceUpdate]:
        if not self._sessions_root.is_dir():
            return
        now = time.time()
        for path in self._sessions_root.glob("*/*/*/rollout-*.jsonl"):
            try:
                stt = path.stat()
            except OSError:
                continue

            # First sighting → silent baseline; never emit for sessions that
            # already existed when the bridge started.
            if path not in self._state:
                self._state[path] = (stt.st_mtime, stt.st_size, False)
                continue

            last_mtime, last_size, emitted_done = self._state[path]
            size_grew = stt.st_size > last_size
            is_active = (now - stt.st_mtime) < ACTIVITY_WINDOW_S
            sid = path.stem.split("-", 2)[-1]

            if is_active and size_grew:
                status, body, terminal = _derive(_tail_jsonl(path))
                self._state[path] = (stt.st_mtime, stt.st_size, terminal)
                yield SourceUpdate(
                    source_id=self.id, session_id=sid,
                    title="Codex CLI", body=body, status=status, is_active=not terminal,
                )
            elif (not is_active and not emitted_done and last_size > 0
                  and last_size < stt.st_size
                  and (now - stt.st_mtime) > IDLE_AFTER_S):
                self._state[path] = (stt.st_mtime, stt.st_size, True)
                yield SourceUpdate(
                    source_id=self.id, session_id=sid,
                    title="Codex CLI", body="✓ Done", status="done", is_active=False,
                )
            else:
                self._state[path] = (stt.st_mtime, stt.st_size, emitted_done)
