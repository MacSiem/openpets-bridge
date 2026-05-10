"""Multi-pet display mode (one OpenPets host per AI source).

Each enabled source spawns its own ``openpets run --pet <pack> --socket <path>``
child process and routes its updates to that dedicated host. Bubbles still
use threadId per-conversation, but each AI now has a visually distinct
sprite (e.g. Mando for Cowork, Grogu for Codex CLI) on the desktop.

Defaults & failure handling:

* If a source has no ``[sources.<id>.extra] pet_dir = "..."``, that source
  falls back to the default OpenPets host (the menubar app's active pet).
* If ``pet_dir`` doesn't exist on disk, the source is skipped (with a clear
  log line pointing at ``openpets-bridge list-pets``).
* If the host's socket fails to bind within 2 s after spawn, the bridge
  warns and continues — notify will degrade gracefully.
* Stale orphan socket files from previous crashes are removed before bind.

Position management for multiple pets (avoid stacking) is left to the user
via the OpenPets tray menu / ``positions.json``.
"""

from __future__ import annotations

import logging
import os
import os.path
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


def _socket_alive(path: str, bin_path: str) -> bool:
    """Probe whether something is listening on the given socket."""
    try:
        return subprocess.run(
            [bin_path, "ping", "--socket", path],
            check=False, timeout=2,
            capture_output=True, text=True,
        ).returncode == 0
    except Exception:  # noqa: BLE001
        return False


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
                    "multi-pet: source %s has no pet pack — set "
                    "[sources.%s.extra] pet_dir=\"...\". Falling back to the "
                    "default OpenPets host (menubar app's active pet).",
                    sid, sid,
                )
                self._clients[sid] = OpenPetsClient(socket_path=None, binary=bin_path)
                continue

            pet_path = os.path.expanduser(str(pet_dir))
            if not os.path.isdir(pet_path):
                log.error(
                    "multi-pet: pet pack for %s not found at %s — skipping. "
                    "Run `openpets-bridge list-pets` to see installed packs.",
                    sid, pet_path,
                )
                continue

            # If a stale socket file exists (orphaned from a previous crash),
            # remove it — Unix sockets can't be re-bound otherwise.
            if os.path.exists(socket_path) and not _socket_alive(socket_path, bin_path):
                try:
                    os.unlink(socket_path)
                except OSError:
                    pass

            args = [bin_path, "run", "--pet", pet_path, "--socket", socket_path]
            log.info("multi-pet: spawning %s → %s", sid, shlex.join(args))
            try:
                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env={**os.environ,
                         "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")},
                )
            except Exception as e:  # noqa: BLE001
                log.error("multi-pet: failed to spawn %s host: %s", sid, e)
                continue

            # Give the host ~2 s to come up + bind the socket.
            for _ in range(20):
                if os.path.exists(socket_path):
                    break
                time.sleep(0.1)
            else:
                log.warning(
                    "multi-pet: %s socket %s did not appear within 2 s — the "
                    "host may have failed to start. Check `pgrep -f 'openpets "
                    "run'` and the OpenPets logs.",
                    sid, socket_path,
                )
            self._hosts[sid] = proc
            self._clients[sid] = OpenPetsClient(socket_path=socket_path,
                                                binary=bin_path)

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        for sid, proc in list(self._hosts.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        self._hosts.clear()
        self._clients.clear()

    # ------------------------------------------------------------------
    def consume(self, updates: Iterable[SourceUpdate]) -> None:
        for u in updates:
            client = self._clients.get(u.source_id)
            if client is None:
                continue  # this source has no host (skipped above)
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
