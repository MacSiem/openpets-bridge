"""Multi-pet display mode (one OpenPets host per AI source).

Each enabled source spawns its own ``openpets run --pet <pack> --socket <path>``
child process and routes its updates to that dedicated host. Bubbles still
use threadId per-conversation, but each AI now has a visually distinct
sprite (Mando for Cowork, Starcorn for Codex, …) on the desktop.

Status: **stub** in 0.1.0. The plumbing is here; spawn/lifecycle is wired
but not yet battle-tested. Open issues:

* OpenPets currently allows only one host per macOS session by default
  (singleton check on the IPC socket). Need to verify ``--socket`` truly
  side-steps that on the user's machine.
* Position management for multiple pets (avoid stacking on top of each
  other) is left to the user via the OpenPets tray menu / ``positions.json``.

Use ``mode = "single"`` until this hardens. Track progress in:
https://github.com/MacSiem/openpets-bridge/issues
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Iterable

from ..openpets_client import OpenPetsClient, _resolve_binary
from ..sources.base import SourceUpdate, SourceConfig

log = logging.getLogger("openpets-bridge.mode.multi")


@dataclass(slots=True)
class _ThreadState:
    thread_id: str
    last_status: str = ""
    last_text: str = ""
    last_push_ts: float = 0.0


class MultiPetMode:
    def __init__(
        self,
        source_configs: dict[str, SourceConfig],
        push_throttle_s: float = 1.5,
    ) -> None:
        self._configs = source_configs
        self._throttle = push_throttle_s
        # source_id → OpenPetsClient bound to that host's socket
        self._clients: dict[str, OpenPetsClient] = {}
        # source_id → child process (the openpets run host)
        self._hosts: dict[str, subprocess.Popen] = {}
        # (source_id, session_id) → _ThreadState
        self._threads: dict[tuple[str, str], _ThreadState] = {}
        self._spawn_hosts()

    # ------------------------------------------------------------------
    def _spawn_hosts(self) -> None:
        bin_path = _resolve_binary()
        for sid, cfg in self._configs.items():
            if not cfg.enabled:
                continue
            extra = cfg.extra or {}
            pet_dir = extra.get("pet_dir") or extra.get("pet")
            socket_path = extra.get("socket") or f"/tmp/openpets-{sid}.sock"
            if not pet_dir:
                log.warning(
                    "multi-pet: source %s has no pet pack configured (set "
                    "[sources.%s.extra] pet_dir=... or pet=...) — skipping host",
                    sid, sid,
                )
                continue
            args = [bin_path, "run", "--pet", str(pet_dir), "--socket", socket_path]
            log.info("multi-pet: spawning %s → %s", sid, shlex.join(args))
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env={**os.environ,
                         "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")},
                )
                self._hosts[sid] = proc
                self._clients[sid] = OpenPetsClient(socket_path=socket_path,
                                                    binary=bin_path)
            except Exception as e:  # noqa: BLE001
                log.error("multi-pet: failed to spawn %s host: %s", sid, e)

    def shutdown(self) -> None:
        for sid, proc in list(self._hosts.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                proc.kill()
        self._hosts.clear()
        self._clients.clear()

    # ------------------------------------------------------------------
    def consume(self, updates: Iterable[SourceUpdate]) -> None:
        for u in updates:
            client = self._clients.get(u.source_id)
            if client is None:
                continue  # this source has no dedicated host
            cfg = self._configs.get(u.source_id)
            icon = cfg.icon if cfg else ""
            title = f"{icon} {u.title}".strip()
            if cfg and cfg.redact_body:
                text = (u.body.split(" ", 1)[0] if u.body else "·")
            else:
                text = u.body or " "

            key = (u.source_id, u.session_id)
            st = self._threads.get(key)
            if st is None:
                st = _ThreadState(thread_id=str(uuid.uuid4()).upper())
                self._threads[key] = st

            now = time.time()
            same = (st.last_status == u.status and st.last_text == text)
            if same and (now - st.last_push_ts) < self._throttle:
                continue

            new_tid = client.notify(
                title=title, text=text, status=u.status, thread_id=st.thread_id,
            )
            if new_tid and new_tid != st.thread_id:
                st.thread_id = new_tid
            st.last_status = u.status
            st.last_text = text
            st.last_push_ts = now
            # Privacy: log only metadata, never bubble content
            log.info(
                "[multi/%s/%s] status=%s",
                u.source_id, u.session_id[:8] + "…", u.status,
            )
