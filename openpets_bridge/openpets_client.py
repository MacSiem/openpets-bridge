"""Thin wrapper around the alterhq ``openpets`` CLI.

The CLI handles socket discovery and IPC framing for us; we just shell out.
This keeps the bridge dependency-free and decoupled from OpenPets's
internal protocol changes.

If you have multiple OpenPets hosts running on different sockets (multi-pet
mode), pass ``socket_path`` to the constructor.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

log = logging.getLogger("openpets-bridge.client")

_DEFAULT_BIN_CANDIDATES = (
    os.path.expanduser("~/.local/bin/openpets"),
    "/Applications/OpenPets.app/Contents/MacOS/openpets-cli",
    "openpets",  # last resort: PATH
)


def _resolve_binary() -> str:
    for cand in _DEFAULT_BIN_CANDIDATES:
        if os.path.isfile(cand) or shutil.which(cand):
            return cand
    raise RuntimeError(
        "openpets CLI not found. Install alterhq/openpets >=0.6 from "
        "https://github.com/alterhq/openpets/releases"
    )


@dataclass(slots=True)
class OpenPetsClient:
    socket_path: str | None = None  # for multi-pet (one host per socket)
    binary: str | None = None       # default: auto-resolve

    def __post_init__(self) -> None:
        if self.binary is None:
            self.binary = _resolve_binary()

    def _common_args(self) -> list[str]:
        out: list[str] = []
        if self.socket_path:
            out += ["--socket", self.socket_path]
        return out

    def _run(self, args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
        env = {**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")}
        return subprocess.run(
            [self.binary, *args],
            check=False, timeout=timeout,
            capture_output=True, text=True, env=env,
        )

    # ------------------------------------------------------------------
    def ping(self) -> bool:
        try:
            res = self._run(["ping", *self._common_args()], timeout=3)
            return res.returncode == 0 and res.stdout.strip().startswith("pong")
        except Exception:  # noqa: BLE001
            return False

    def notify(
        self,
        *,
        title: str,
        text: str,
        status: str,
        thread_id: str | None = None,
        ttl_seconds: float | None = None,
        button_label: str | None = None,
        url: str | None = None,
    ) -> str | None:
        """Send a notification bubble. Returns the (possibly server-assigned)
        threadId on success, or None on failure."""
        args = ["notify",
                "--title", title or " ",
                "--text", text or " ",
                "--status", status]
        if thread_id:
            args += ["--thread", thread_id]
        if ttl_seconds is not None:
            args += ["--ttl", str(ttl_seconds)]
        if button_label:
            args += ["--button", button_label]
        if url:
            args += ["--url", url]
        args += self._common_args()
        try:
            res = self._run(args)
            if res.returncode != 0:
                log.warning("notify rc=%s stderr=%s", res.returncode, res.stderr.strip()[:200])
                return None
            tail = res.stdout.strip().splitlines()[-1] if res.stdout else ""
            return tail or thread_id
        except Exception as e:  # noqa: BLE001
            log.warning("notify failed: %s", e)
            return None

    def clear(self, thread_id: str) -> None:
        try:
            self._run(["clear", "--thread", thread_id, *self._common_args()])
        except Exception:  # noqa: BLE001
            pass

    def stop_animation(self) -> None:
        try:
            self._run(["stop-animation", *self._common_args()])
        except Exception:  # noqa: BLE001
            pass
