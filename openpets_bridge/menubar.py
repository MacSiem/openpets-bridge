"""Optional menubar app for openpets-bridge.

A tiny rumps-based menubar icon that lets users see whether the bridge is
running and run the most common ops without touching ``launchctl`` or
``vim ~/.config/openpets-bridge/config.toml``.

Install:
    pipx install 'openpets-bridge[menubar]'
    openpets-bridge install         # registers BOTH the daemon and this app

Run manually:
    openpets-bridge-menubar

Headless deployments (servers / CI) should skip the ``[menubar]`` extra.

The menubar app is **stateless** — it only invokes:
* ``launchctl list / bootout / bootstrap`` to read & toggle the daemon
* ``openpets ping`` to probe the desktop pet
* ``open <path>`` for "Open config" / "Open log"

It never reads session content or talks to OpenPets's IPC directly.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

try:
    import rumps  # type: ignore[import-not-found]
except ImportError as e:  # pragma: no cover
    sys.stderr.write(
        "openpets-bridge-menubar requires the [menubar] extra:\n"
        "    pipx install 'openpets-bridge[menubar]'\n"
        f"or:  pip install rumps   # ImportError: {e}\n"
    )
    sys.exit(1)

from . import __version__
from . import pets as petsmod
from .openpets_client import OpenPetsClient
from .state import ThreadStore

LAUNCHD_LABEL = "sh.openpets.bridge"
CONFIG_PATH = Path.home() / ".config/openpets-bridge/config.toml"
LOG_PATH = Path.home() / "ai-stack/openpets-bridge/bridge.log"
PLIST_PATH = Path.home() / f"Library/LaunchAgents/{LAUNCHD_LABEL}.plist"
REPO_URL = "https://github.com/MacSiem/openpets-bridge"

POLL_INTERVAL_S = 5  # how often to refresh the title icon


# ---------------------------------------------------------------------------
def _bridge_running() -> bool:
    try:
        out = subprocess.run(
            ["launchctl", "list"], check=False, timeout=3,
            capture_output=True, text=True,
        )
        for line in out.stdout.splitlines():
            if LAUNCHD_LABEL in line:
                # "<pid>  <status>  <label>" — pid="-" means not running
                pid = line.split()[0]
                return pid != "-"
        return False
    except Exception:  # noqa: BLE001
        return False


def _pet_alive() -> bool:
    try:
        return OpenPetsClient().ping()
    except Exception:  # noqa: BLE001
        return False


def _bootstrap() -> None:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)],
        check=False, timeout=10,
    )


def _bootout() -> None:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{LAUNCHD_LABEL}"],
        check=False, timeout=10,
    )


def _restart() -> None:
    _bootout()
    time.sleep(1.5)
    _bootstrap()


# ---------------------------------------------------------------------------
class OpenPetsBridgeMenubar(rumps.App):
    """Stateless menubar control panel for the bridge daemon."""

    def __init__(self) -> None:
        super().__init__("openpets-bridge", title="🐾", quit_button=None)
        self.menu = [
            rumps.MenuItem("Bridge status: …", callback=None),
            rumps.MenuItem("Pet host: …", callback=None),
            None,  # separator
            rumps.MenuItem("Start bridge", callback=self.on_start),
            rumps.MenuItem("Stop bridge", callback=self.on_stop),
            rumps.MenuItem("Restart bridge", callback=self.on_restart),
            None,
            rumps.MenuItem("Open config…", callback=self.on_open_config),
            rumps.MenuItem("Open log…", callback=self.on_open_log),
            rumps.MenuItem("List installed pets", callback=self.on_list_pets),
            None,
            rumps.MenuItem("Clear done bubbles", callback=self.on_clear_done),
            rumps.MenuItem("Clear ALL bubbles…", callback=self.on_clear_all),
            None,
            rumps.MenuItem("Documentation", callback=self.on_docs),
            rumps.MenuItem(f"openpets-bridge v{__version__}", callback=None),
            rumps.MenuItem("Quit menubar", callback=self.on_quit),
        ]
        self._refresh()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # --- background polling -------------------------------------------------
    def _poll_loop(self) -> None:
        while True:
            try:
                self._refresh()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(POLL_INTERVAL_S)

    def _refresh(self) -> None:
        running = _bridge_running()
        pet = _pet_alive()
        # Title icon: 🐾 (both ok) / 🐾(faded) / 💤
        if running and pet:
            self.title = "🐾"
        elif running and not pet:
            self.title = "🐾·"  # bridge up, pet down
        else:
            self.title = "💤"
        # Sync menu text
        self.menu["Bridge status: …"].title = (
            f"Bridge: {'running' if running else 'stopped'}"
        )
        self.menu["Pet host: …"].title = (
            f"Pet host: {'reachable' if pet else 'NOT reachable'}"
        )
        # Toggle Start/Stop visibility
        self.menu["Start bridge"].set_callback(None if running else self.on_start)
        self.menu["Stop bridge"].set_callback(self.on_stop if running else None)

    # --- actions ------------------------------------------------------------
    def on_start(self, _) -> None:
        _bootstrap()
        time.sleep(1)
        self._refresh()

    def on_stop(self, _) -> None:
        _bootout()
        time.sleep(1)
        self._refresh()

    def on_restart(self, _) -> None:
        rumps.notification(
            title="openpets-bridge",
            subtitle="Restarting daemon…",
            message="Bridge will reload config and reconnect.",
        )
        _restart()
        time.sleep(1)
        self._refresh()

    def on_open_config(self, _) -> None:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text("# openpets-bridge config\n")
        subprocess.run(["open", str(CONFIG_PATH)], check=False)

    def on_open_log(self, _) -> None:
        if not LOG_PATH.exists():
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            LOG_PATH.touch()
        subprocess.run(["open", str(LOG_PATH)], check=False)

    def on_list_pets(self, _) -> None:
        pets = petsmod.discover()
        if not pets:
            rumps.alert(
                title="No pet packs found",
                message=("Install a pack into ~/Library/Application Support/"
                         "OpenPets/Pets/ or ~/.codex/pets/, then try again."),
            )
            return
        body = "\n".join(
            f"• {p.display_name} [{p.pet_id}]\n  {p.path}"
            for p in pets
        )
        rumps.alert(
            title=f"{len(pets)} pet pack(s) installed",
            message=body,
        )

    def on_clear_done(self, _) -> None:
        """Clear bubbles for sessions that already finished (status=done)."""
        store = ThreadStore()
        store.load()
        client = OpenPetsClient()
        cleared = 0
        for rec in list(store.all()):
            if rec.last_status != "done":
                continue
            client.clear(rec.thread_id)
            store.drop(rec.source_id, rec.session_id)
            cleared += 1
        store.save(force=True)
        rumps.notification(
            title="openpets-bridge",
            subtitle=f"Cleared {cleared} done bubble(s)",
            message="Active conversations were left alone.",
        )

    def on_clear_all(self, _) -> None:
        """Clear EVERY bubble — active and done. Asks for confirmation."""
        confirm = rumps.alert(
            title="Clear all bubbles?",
            message=("This removes every OpenPets bubble created by the "
                     "bridge, including active conversations. They will "
                     "reappear on the next activity from each session."),
            ok="Clear all",
            cancel="Cancel",
        )
        if confirm != 1:
            return
        store = ThreadStore()
        store.load()
        client = OpenPetsClient()
        cleared = 0
        for rec in list(store.all()):
            client.clear(rec.thread_id)
            store.drop(rec.source_id, rec.session_id)
            cleared += 1
        store.save(force=True)
        rumps.notification(
            title="openpets-bridge",
            subtitle=f"Cleared {cleared} bubble(s)",
            message="Active sessions will repopulate on next activity.",
        )

    def on_docs(self, _) -> None:
        webbrowser.open(REPO_URL)

    def on_quit(self, _) -> None:
        rumps.quit_application()


def main() -> int:
    OpenPetsBridgeMenubar().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
