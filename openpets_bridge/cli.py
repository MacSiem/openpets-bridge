"""``openpets-bridge`` command-line entry point."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from . import config as bridgeconfig
from . import orchestrator
from .openpets_client import OpenPetsClient


LAUNCHD_LABEL = "sh.openpets.bridge"


def _launchd_plist_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _python_executable() -> str:
    # Prefer Homebrew python explicitly so launchd doesn't break on PATH
    for cand in ("/opt/homebrew/bin/python3.12",
                 "/opt/homebrew/bin/python3",
                 sys.executable):
        if os.path.isfile(cand):
            return cand
    return sys.executable


def _launchd_plist_xml(stdout_log: str, stderr_log: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>            <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{_python_executable()}</string>
        <string>-u</string>
        <string>-m</string>
        <string>openpets_bridge</string>
        <string>run</string>
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


def cmd_install(args) -> int:
    """Install launchd agent so the bridge runs at login."""
    bridgeconfig.write_default()
    plist = _launchd_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path.home() / "ai-stack/openpets-bridge"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = str(log_dir / "launchd.stdout.log")
    stderr = str(log_dir / "launchd.stderr.log")
    plist.write_text(_launchd_plist_xml(stdout, stderr))

    # bootstrap
    uid = os.getuid()
    os.system(f"launchctl bootout gui/{uid}/{LAUNCHD_LABEL} 2>/dev/null")
    rc = os.system(f"launchctl bootstrap gui/{uid} {shutil_quote(str(plist))}")
    if rc != 0:
        print("WARN: bootstrap returned non-zero — run `launchctl bootstrap gui/$(id -u) {plist}` manually", file=sys.stderr)
    else:
        print(f"Installed launchd agent: {plist}")
        print(f"  stdout → {stdout}")
        print(f"  stderr → {stderr}")
    return 0


def cmd_uninstall(args) -> int:
    plist = _launchd_plist_path()
    uid = os.getuid()
    os.system(f"launchctl bootout gui/{uid}/{LAUNCHD_LABEL} 2>/dev/null")
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
    sp_inst.set_defaults(func=cmd_install)

    sp_un = sub.add_parser("uninstall", help="Stop + remove launchd agent")
    sp_un.set_defaults(func=cmd_uninstall)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
