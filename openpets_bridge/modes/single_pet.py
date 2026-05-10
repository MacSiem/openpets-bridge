"""Single-pet display mode.

One OpenPets host receives notifications from every enabled source. Bubbles
are namespaced by ``(source_id, session_id)`` so multiple AI conversations
stack independently. The bubble title is prefixed with the source's icon
(set in TOML) so the user can tell at a glance which AI is speaking.

Per-conversation persistence (since 0.1.4):

* ThreadIds are persisted to ``~/.local/state/openpets-bridge/threads.json``
  so a daemon restart picks up exactly where it left off — same conversation
  → same threadId → next ``notify`` REPLACES the existing bubble (no
  duplicates from restart).
* When a conversation goes done and stays quiet for ``CLEAR_AFTER_S``
  (default 5 min), the bubble is fully cleared from OpenPets via
  ``openpets clear --thread <id>`` and dropped from state.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Iterable

from ..openpets_client import OpenPetsClient
from ..sources.base import SourceConfig, SourceUpdate
from ..state import ThreadRecord, ThreadStore

log = logging.getLogger("openpets-bridge.mode.single")

# After status=done, wait this long with no further activity before fully
# clearing the bubble from OpenPets. Tunable via env if needed later.
CLEAR_AFTER_S = 300.0


class SinglePetMode:
    """Aggregate every source into one OpenPets host."""

    def __init__(
        self,
        source_configs: dict[str, SourceConfig],
        push_throttle_s: float = 1.5,
        store: ThreadStore | None = None,
    ) -> None:
        self._client = OpenPetsClient()
        self._configs = source_configs
        self._throttle = push_throttle_s
        self._store = store or ThreadStore()
        self._store.load()

    # ------------------------------------------------------------------
    def consume(self, updates: Iterable[SourceUpdate]) -> None:
        for u in updates:
            self._handle(u)
        self._store.save()  # debounced internally

    def tick(self) -> None:
        """Call every poll iteration so we can clear stale 'done' bubbles."""
        now = time.time()
        for rec in list(self._store.all()):
            if rec.done_at is None:
                continue
            if (now - rec.done_at) < CLEAR_AFTER_S:
                continue
            self._client.clear(rec.thread_id)
            self._store.drop(rec.source_id, rec.session_id)
            log.info(
                "[%s/%s] cleared (idle for %.0fs after done)",
                rec.source_id, rec.session_id[:8] + "…",
                now - rec.done_at,
            )
        self._store.save()

    # ------------------------------------------------------------------
    def _handle(self, u: SourceUpdate) -> None:
        cfg = self._configs.get(u.source_id)
        if cfg is None or not cfg.enabled:
            return  # source removed/disabled mid-flight

        rec = self._store.get(u.source_id, u.session_id)
        if rec is None:
            rec = ThreadRecord(
                source_id=u.source_id, session_id=u.session_id,
                thread_id=str(uuid.uuid4()).upper(),
            )

        title = f"{cfg.icon} {u.title}".strip()
        # Privacy mode: strip everything past the leading glyph.
        if cfg.redact_body:
            text = (u.body.split(" ", 1)[0] if u.body else "·")
        else:
            text = u.body or " "

        now = time.time()
        same = (rec.last_status == u.status and rec.last_text == text)
        if same and (now - rec.last_push_ts) < self._throttle:
            return

        new_tid = self._client.notify(
            title=title, text=text, status=u.status, thread_id=rec.thread_id,
        )
        if new_tid and new_tid != rec.thread_id:
            rec.thread_id = new_tid

        rec.last_status = u.status
        rec.last_text = text
        rec.last_push_ts = now
        # Mark/unmark the done countdown
        if u.status == "done":
            rec.done_at = now
        else:
            rec.done_at = None  # session got active again — reset timer

        self._store.upsert(rec)
        log.info("[%s/%s] status=%s",
                 u.source_id, u.session_id[:8] + "…", u.status)
