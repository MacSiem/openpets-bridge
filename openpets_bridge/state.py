"""On-disk persistence for per-conversation thread state.

Why this matters: OpenPets bubbles are addressed by a server-assigned
``threadId`` (UUID). When the bridge restarts, in-memory threadIds are lost
— if we generate fresh ones, the old bubbles for active conversations
**stay alive** (nothing replaces them) AND new bubbles spawn alongside them
(duplicates). Persisting ``(source_id, session_id) → thread_id`` to disk
means a restart picks up exactly where it left off.

State file format (JSON, single source of truth):

    {
      "version": 1,
      "threads": [
        {
          "source_id": "cowork",
          "session_id": "local_abc",
          "thread_id": "FFEE-…",
          "last_status": "running",
          "last_text": "▶ ls -la",
          "last_push_ts": 1778414000.0,
          "done_at": null
        },
        …
      ]
    }

Saves are debounced (at most once every SAVE_THROTTLE_S) to avoid disk
churn when many sources push rapidly. The state file is rewritten
atomically (tempfile + rename) so a crash mid-save can't corrupt it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("openpets-bridge.state")

DEFAULT_STATE_PATH = Path.home() / ".local/state/openpets-bridge/threads.json"
SCHEMA_VERSION = 1
SAVE_THROTTLE_S = 5.0


@dataclass(slots=True)
class ThreadRecord:
    source_id: str
    session_id: str
    thread_id: str
    last_status: str = ""
    last_text: str = ""
    last_push_ts: float = 0.0
    done_at: float | None = None  # set when status=done was pushed


@dataclass(slots=True)
class ThreadStore:
    """Mapping from (source_id, session_id) → ThreadRecord, persisted to disk."""

    path: Path = DEFAULT_STATE_PATH
    _records: dict[tuple[str, str], ThreadRecord] = field(default_factory=dict)
    _last_save_ts: float = 0.0
    _dirty: bool = False

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("could not read %s (%s) — starting empty", self.path, e)
            return
        if data.get("version") != SCHEMA_VERSION:
            log.warning("state schema mismatch in %s (got %s, want %s) — ignoring",
                        self.path, data.get("version"), SCHEMA_VERSION)
            return
        for r in data.get("threads", []):
            try:
                rec = ThreadRecord(
                    source_id=str(r["source_id"]),
                    session_id=str(r["session_id"]),
                    thread_id=str(r["thread_id"]),
                    last_status=str(r.get("last_status", "")),
                    last_text=str(r.get("last_text", "")),
                    last_push_ts=float(r.get("last_push_ts", 0.0)),
                    done_at=(float(r["done_at"]) if r.get("done_at") is not None else None),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._records[(rec.source_id, rec.session_id)] = rec
        log.info("loaded %d thread records from %s", len(self._records), self.path)

    # ------------------------------------------------------------------
    def get(self, source_id: str, session_id: str) -> ThreadRecord | None:
        return self._records.get((source_id, session_id))

    def upsert(self, rec: ThreadRecord) -> None:
        self._records[(rec.source_id, rec.session_id)] = rec
        self._dirty = True

    def drop(self, source_id: str, session_id: str) -> ThreadRecord | None:
        rec = self._records.pop((source_id, session_id), None)
        if rec is not None:
            self._dirty = True
        return rec

    def all(self) -> list[ThreadRecord]:
        return list(self._records.values())

    # ------------------------------------------------------------------
    def save(self, force: bool = False) -> None:
        """Debounced atomic write."""
        now = time.time()
        if not self._dirty and not force:
            return
        if not force and (now - self._last_save_ts) < SAVE_THROTTLE_S:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": SCHEMA_VERSION,
                "threads": [asdict(r) for r in self._records.values()],
            }
            tmp = tempfile.NamedTemporaryFile(
                mode="w", dir=str(self.path.parent), delete=False, suffix=".tmp"
            )
            try:
                json.dump(payload, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
            finally:
                tmp.close()
            os.replace(tmp.name, self.path)
            self._last_save_ts = now
            self._dirty = False
        except OSError as e:  # noqa: BLE001
            log.warning("could not write state file %s: %s", self.path, e)
