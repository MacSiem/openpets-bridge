"""``openpets-bridge`` command-line entry point."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def _find_first_existing(*candidates: Path) -> str | None:
    for c in candidates:
        if c.is_file():
            return str(c)
    return None

from . import __version__
from . import config as bridgeconfig
from . import orchestrator
from . import pets as petsmod
from .openpets_client import OpenPetsClient


LAUNCHD_LABEL = "sh.openpets.bridge"
MENUBAR_LABEL = "sh.openpets.bridge.menubar"


def _launchd_plist_path(label: str = LAUNCHD_LABEL) -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{label}.plist"


def _python_executable() -> str:
    # Prefer Homebrew python explicitly so launchd doesn't break on PATH
    for cand in ("/opt/homebrew/bin/python3.12",
                 "/opt/homebrew/bin/python3",
                 sys.executable):
        if os.path.isfile(cand):
            return cand
    return sys.executable


def _launchd_plist_xml(stdout_log: str, stderr_log: str,
                       label: str = LAUNCHD_LABEL,
                       module: str = "openpets_bridge",
                       subcommand: str = "run") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>            <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{_python_executable()}</string>
        <string>-u</string>
        <string>-m</string>
        <string>{module}</string>
        <string>{subcommand}</string>
    </array>
    <key>RunAtLoad</key>        <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key> <false/>
        <key>Crashed</key>        <true/>
    </dict>
    <key>ThrottleInterval</key> <integer>10</integer>
    <key>StandardOutPath</key>  <string>{stdout_log}</string>
    <key>StandardErrorPath</key><string>{stderr_log}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
"""


def _menubar_plist_xml(stdout_log: str, stderr_log: str) -> str:
    """Plist for the rumps menubar app.

    launchd does NOT honor the per-job PATH for resolving ProgramArguments[0]
    (only for child env), so we MUST embed the absolute path to the
    ``openpets-bridge-menubar`` script. We try shutil.which first, then a
    short list of well-known pipx / brew / user locations.
    """
    binary_str = (
        shutil.which("openpets-bridge-menubar")
        or _find_first_existing(
            Path.home() / ".local/bin/openpets-bridge-menubar",
            Path("/opt/homebrew/bin/openpets-bridge-menubar"),
            Path("/usr/local/bin/openpets-bridge-menubar"),
            Path.home() / ".local/pipx/venvs/openpets-bridge/bin/openpets-bridge-menubar",
        )
        or "openpets-bridge-menubar"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>            <string>{MENUBAR_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{binary_str}</string>
    </array>
    <key>RunAtLoad</key>        <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key> <false/>
        <key>Crashed</key>        <true/>
    </dict>
    <key>ThrottleInterval</key> <integer>10</integer>
    <key>StandardOutPath</key>  <string>{stdout_log}</string>
    <key>StandardErrorPath</key><string>{stderr_log}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{Path.home()}/.local/bin</string>
    </dict>
</dict>
</plist>
"""


def cmd_init(args) -> int:
    p = bridgeconfig.write_default()
    print(f"wrote {p}")
    return 0


def cmd_run(args) -> int:
    cfg = bridgeconfig.load(args.config)
    return orchestrator.run(cfg)


def cmd_status(args) -> int:
    cfg = bridgeconfig.load(args.config)
    print(f"openpets-bridge {__version__}")
    print(f"  mode             : {cfg.mode}")
    print(f"  poll_interval_s  : {cfg.poll_interval_s}")
    print(f"  log              : {cfg.log_path}")
    print( "  sources:")
    for sid, sc in cfg.sources.items():
        flag = "ON " if sc.enabled else "off"
        print(f"    [{flag}] {sid:<14} {sc.icon}  {sc.label}")
    client = OpenPetsClient()
    print(f"  openpets ping    : {'pong' if client.ping() else 'NOT REACHABLE — is OpenPets.app running?'}")
    plist = _launchd_plist_path()
    print(f"  launchd plist    : {plist} {'(installed)' if plist.exists() else '(not installed — run `openpets-bridge install`)'}")
    return 0


def _menubar_available() -> bool:
    """Detect whether the optional [menubar] extra (rumps) is installed."""
    try:
        import importlib.util
        return importlib.util.find_spec("rumps") is not None
    except Exception:  # noqa: BLE001
        return False


def cmd_install(args) -> int:
    """Install launchd agent(s): bridge daemon (always) + menubar (optional)."""
    bridgeconfig.write_default()
    log_dir = Path.home() / "ai-stack/openpets-bridge"
    log_dir.mkdir(parents=True, exist_ok=True)
    uid = os.getuid()

    # 1. Bridge daemon (always)
    plist = _launchd_plist_path(LAUNCHD_LABEL)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(_launchd_plist_xml(
        stdout_log=str(log_dir / "launchd.stdout.log"),
        stderr_log=str(log_dir / "launchd.stderr.log"),
    ))
    os.system(f"launchctl bootout gui/{uid}/{LAUNCHD_LABEL} 2>/dev/null")
    rc = os.system(f"launchctl bootstrap gui/{uid} {shutil_quote(str(plist))}")
    if rc != 0:
        print(f"WARN: bridge bootstrap returned {rc} — run `launchctl bootstrap "
              f"gui/$(id -u) {plist}` manually", file=sys.stderr)
    else:
        print(f"Installed bridge daemon agent: {plist}")

    # 2. Menubar app (only if rumps installed and user didn't opt out)
    if getattr(args, "no_menubar", False):
        print("Menubar agent skipped (--no-menubar).")
    elif not _menubar_available():
        print("Menubar app not installed (rumps missing). To enable:")
        print("  pipx inject openpets-bridge rumps")
        print("  openpets-bridge install")
    else:
        mplist = _launchd_plist_path(MENUBAR_LABEL)
        mplist.write_text(_menubar_plist_xml(
            stdout_log=str(log_dir / "menubar.stdout.log"),
            stderr_log=str(log_dir / "menubar.stderr.log"),
        ))
        os.system(f"launchctl bootout gui/{uid}/{MENUBAR_LABEL} 2>/dev/null")
        rc = os.system(f"launchctl bootstrap gui/{uid} {shutil_quote(str(mplist))}")
        if rc != 0:
            print(f"WARN: menubar bootstrap returned {rc}", file=sys.stderr)
        else:
            print(f"Installed menubar app agent:   {mplist}")
            print("  Look for the 🐾 icon in your macOS menu bar.")
    return 0


def cmd_list_pets(args) -> int:
    """List installed OpenPets pet packs across the standard locations."""
    pets = petsmod.discover()
    if not pets:
        print("No pet packs found in any of:")
        for root in petsmod.DEFAULT_PET_ROOTS:
            print(f"  - {root}")
        print("\nInstall a pack into one of those folders, or download one"
              " from https://openpets.dev")
        return 1
    print(f"{len(pets)} pet pack(s) installed:\n")
    for p in pets:
        marker = "✓" if p.has_spritesheet else "✗ (missing spritesheet)"
        print(f"  {marker} {p.display_name}  [{p.pet_id}]")
        print(f"      {p.path}")
        if p.description:
            print(f"      {p.description}")
        print()
    print("To use one in multi-pet mode, copy its absolute path into your config:\n")
    print('  [sources.<source_id>.extra]')
    print(f'  pet_dir = "{pets[0].path}"')
    print(f'  socket  = "/tmp/openpets-<source_id>.sock"')
    return 0


def cmd_uninstall(args) -> int:
    """Stop + remove both the bridge daemon and the menubar agent."""
    uid = os.getuid()
    for label in (MENUBAR_LABEL, LAUNCHD_LABEL):
        os.system(f"launchctl bootout gui/{uid}/{label} 2>/dev/null")
        plist = _launchd_plist_path(label)
        if plist.exists():
            plist.unlink()
            print(f"Removed {plist}")
    print("openpets-bridge uninstalled (config + logs left in place)")
    return 0


def shutil_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="openpets-bridge",
        description="Multi-AI desktop pet bridge for OpenPets.",
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_run = sub.add_parser("run", help="Run the bridge in the foreground")
    sp_run.add_argument("--config", default=None, help="Path to config.toml")
    sp_run.set_defaults(func=cmd_run)

    sp_init = sub.add_parser("init", help="Write a default config.toml")
    sp_init.set_defaults(func=cmd_init)

    sp_st = sub.add_parser("status", help="Show config + connectivity")
    sp_st.add_argument("--config", default=None)
    sp_st.set_defaults(func=cmd_status)

    sp_inst = sub.add_parser("install", help="Install + start launchd agent")
    sp_inst.add_argument("--no-menubar", action="store_true",
                         help="Skip the menubar app (headless install)")
    sp_inst.set_defaults(func=cmd_install)

    sp_un = sub.add_parser("uninstall", help="Stop + remove launchd agent")
    sp_un.set_defaults(func=cmd_uninstall)

    sp_pets = sub.add_parser("list-pets",
                             help="Discover installed OpenPets pet packs")
    sp_pets.set_defaults(func=cmd_list_pets)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
