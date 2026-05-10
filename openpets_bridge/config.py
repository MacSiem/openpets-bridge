"""TOML config loading + sensible defaults.

Layout:

    [bridge]
    mode = "single"       # "single" | "multi"
    poll_interval_s = 1.0
    push_throttle_s = 1.5

    [sources.cowork]
    enabled = true
    label = "Cowork"
    icon = "🤝"

    [sources.codex_cli]
    enabled = true
    label = "Codex"
    icon = "🟢"

    [sources.claude_code]
    enabled = false
    label = "Claude Code"
    icon = "🟠"

    # Multi-pet only — pet pack id per source
    [sources.cowork.multi_pet]
    pet = "mandalorian"
    socket = "/tmp/openpets-cowork.sock"

    [sources.codex_cli.multi_pet]
    pet = "starcorn"
    socket = "/tmp/openpets-codex.sock"
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib  # noqa
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from .sources.base import SourceConfig


DEFAULT_CONFIG_PATH = Path.home() / ".config/openpets-bridge/config.toml"


# Sensible defaults — every popular AI source enabled with a recognizable icon.
# User overrides via TOML.
DEFAULT_SOURCES: dict[str, dict] = {
    "cowork": {
        "enabled": True,
        "label": "Cowork",
        "icon": "🤝",
        "extra": {},
    },
    "codex_cli": {
        "enabled": True,
        "label": "Codex",
        "icon": "🟢",
        "extra": {},
    },
    "claude_code": {
        "enabled": False,  # off by default — many users don't have CLI installed
        "label": "Claude Code",
        "icon": "🟠",
        "extra": {},
    },
}


@dataclass(slots=True)
class BridgeConfig:
    mode: str = "single"           # "single" | "multi"
    poll_interval_s: float = 1.0
    push_throttle_s: float = 1.5
    log_path: str = str(Path.home() / "ai-stack/openpets-bridge/bridge.log")
    sources: dict[str, SourceConfig] = field(default_factory=dict)


def _build_source_config(sid: str, raw: dict) -> SourceConfig:
    defaults = DEFAULT_SOURCES.get(sid, {})
    return SourceConfig(
        enabled=bool(raw.get("enabled", defaults.get("enabled", False))),
        label=str(raw.get("label", defaults.get("label", sid))),
        icon=str(raw.get("icon", defaults.get("icon", "•"))),
        pet=raw.get("pet"),
        extra=dict(raw.get("extra", defaults.get("extra", {}))),
    )


def load(path: Path | str | None = None) -> BridgeConfig:
    """Load config from TOML, falling back to defaults."""
    cfg = BridgeConfig()
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict = {}
    if p.is_file():
        with p.open("rb") as f:
            raw = tomllib.load(f)
    bridge_raw = raw.get("bridge", {}) or {}
    cfg.mode = str(bridge_raw.get("mode", cfg.mode))
    cfg.poll_interval_s = float(bridge_raw.get("poll_interval_s", cfg.poll_interval_s))
    cfg.push_throttle_s = float(bridge_raw.get("push_throttle_s", cfg.push_throttle_s))
    cfg.log_path = str(bridge_raw.get("log_path", cfg.log_path))

    sources_raw = raw.get("sources", {}) or {}
    # Merge with defaults so newly added sources work without config edits
    all_keys = set(DEFAULT_SOURCES) | set(sources_raw.keys())
    for sid in all_keys:
        cfg.sources[sid] = _build_source_config(sid, sources_raw.get(sid, {}))
    return cfg


def write_default(path: Path | None = None) -> Path:
    """Write the default config to ``path`` (or the standard location)."""
    p = path or DEFAULT_CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(_DEFAULT_TOML)
    return p


_DEFAULT_TOML = """\
# openpets-bridge config — see https://github.com/MacSiem/openpets-bridge

[bridge]
mode = "single"            # "single" (one pet, AI icon per bubble) | "multi"
poll_interval_s = 1.0
push_throttle_s = 1.5

# ---- Sources --------------------------------------------------------------
# Set enabled=true for each agent runtime you want the pet to react to.
# You can override label/icon to taste; icons render inside the bubble title.

[sources.cowork]
enabled = true
label = "Cowork"
icon = "🤝"

[sources.codex_cli]
enabled = true
label = "Codex"
icon = "🟢"

[sources.claude_code]
enabled = false           # turn on when you use the `claude` CLI
label = "Claude Code"
icon = "🟠"

# ---- Multi-pet mode (optional) -------------------------------------------
# When mode = "multi", each enabled source gets its OWN OpenPets host on a
# separate socket. Specify which pet pack to wear and where the socket lives:
#
# [sources.cowork.multi_pet]
# pet = "mandalorian"
# socket = "/tmp/openpets-cowork.sock"
#
# [sources.codex_cli.multi_pet]
# pet = "starcorn"
# socket = "/tmp/openpets-codex.sock"
"""
