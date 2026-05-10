"""Single-pet display mode.

One OpenPets host receives notifications from every enabled source. Bubbles
are namespaced by ``(source_id, session_id)`` so multiple AI conversations
stack independently. The bubble title is prefixed with the source's icon
(set in TOML) so the user can tell at a glance which AI is speaking.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Iterable

from ..openpets_client import OpenPetsClient
from ..sources.base import SourceUpdate, SourceConfig

log = logging.getLogger("openpets-bridge.mode.single")


@dataclass(slots=True)
class _ThreadState:
    thread_id: str
    last_status: str = ""
    last_text: str = ""
    last_push_ts: float = 0.0


class SinglePetMode:
    """Aggregate every source into one OpenPets host."""

    def __init__(
        self,
        source_configs: dict[str, SourceConfig],
        push_throttle_s: float = 1.5,
    ) -> None:
        self._client = OpenPetsClient()
        self._configs = source_configs
        self._throttle = push_throttle_s
        # (source_id, session_id) → _ThreadState
        self._threads: dict[tuple[str, str], _ThreadState] = {}

    def consume(self, updates: Iterable[SourceUpdate]) -> None:
        for u in updates:
            self._handle(u)

    def _handle(self, u: SourceUpdate) -> None:
        cfg = self._configs.get(u.source_id)
        if cfg is None or not cfg.enabled:
            return  # source removed/disabled mid-flight

        key = (u.source_id, u.session_id)
        st = self._threads.get(key)
        if st is None:
            st = _ThreadState(thread_id=str(uuid.uuid4()).upper())
            self._threads[key] = st

        title = f"{cfg.icon} {u.title}".strip()
        text = u.body or " "
        now = time.time()
        same = (st.last_status == u.status and st.last_text == text)
        if same and (now - st.last_push_ts) < self._throttle:
            return

        new_tid = self._client.notify(
            title=title, text=text, status=u.status, thread_id=st.thread_id,
        )
        if new_tid and new_tid != st.thread_id:
            st.thread_id = new_tid

        st.last_status = u.status
        st.last_text = text
        st.last_push_ts = now
        log.info(
            "[%s/%s] %s — %s — %s",
            u.source_id, u.session_id[:8] + "…", u.status, title, text,
        )
