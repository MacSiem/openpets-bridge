"""Anthropic Claude Code CLI activity source.

Watches per-project transcript JSONL files under
``~/.claude/projects/<encoded-cwd>/<sessionUUID>.jsonl``.
The format mirrors Cowork's audit.jsonl (assistant tool_use blocks),
so we re-use the same derive logic via a shared helper.

Note: if the user installs the official @anthropic-ai/claude-pets package,
those hooks fire alongside this watcher. Both writing to the same OpenPets
host is OK — the bridge just provides backup signal + per-conversation
threadId persistence (which claude-pets test-event style doesn't do).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

from .base import Source, SourceUpdate
from .cowork import _tail_json_lines, _derive_status_text


PROJECTS_ROOT = Path.home() / ".claude/projects"
ACTIVITY_WINDOW_S = 6
IDLE_AFTER_S = 25


class ClaudeCodeSource(Source):
    id = "claude_code"

    def __init__(self, config) -> None:
        super().__init__(config)
        root = (self.config.extra or {}).get("projects_root", str(PROJECTS_ROOT))
        self._projects_root = Path(root)
        self._state: dict[Path, tuple[float, int, bool]] = {}

    def poll(self) -> Iterable[SourceUpdate]:
        if not self._projects_root.is_dir():
            return
        now = time.time()
        for path in self._projects_root.glob("*/*.jsonl"):
            try:
                stt = path.stat()
            except OSError:
                continue

            # First sighting → silent baseline; never emit for sessions
            # that already existed when the bridge started.
            if path not in self._state:
                self._state[path] = (stt.st_mtime, stt.st_size, False)
                continue

            last_mtime, last_size, emitted_done = self._state[path]
            size_grew = stt.st_size > last_size
            is_active = (now - stt.st_mtime) < ACTIVITY_WINDOW_S
            session_id = path.stem
            title = path.parent.name.replace("-", "/").lstrip("/").rsplit("/", 1)[-1] or "Claude Code"

            if is_active and size_grew:
                status, body = _derive_status_text(_tail_json_lines(path))
                self._state[path] = (stt.st_mtime, stt.st_size, False)
                yield SourceUpdate(
                    source_id=self.id, session_id=session_id,
                    title=title, body=body, status=status, is_active=True,
                )
            elif (not is_active and not emitted_done and last_size > 0
                  and last_size < stt.st_size
                  and (now - stt.st_mtime) > IDLE_AFTER_S):
                self._state[path] = (stt.st_mtime, stt.st_size, True)
                yield SourceUpdate(
                    source_id=self.id, session_id=session_id,
                    title=title, body="✓ Done", status="done", is_active=False,
                )
            else:
                self._state[path] = (stt.st_mtime, stt.st_size, emitted_done)
