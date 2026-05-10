"""Activity sources for openpets-bridge.

Built-in sources:

* `cowork`       — Claude desktop app's Cowork mode (audit.jsonl)
* `codex_cli`    — OpenAI Codex CLI sessions (~/.codex/sessions/)
* `claude_code`  — Anthropic Claude Code CLI projects (~/.claude/projects/)

To register a new one, subclass :class:`openpets_bridge.sources.base.Source`,
set ``id``, implement ``poll``, and add it to :func:`load_sources` below.
"""

from __future__ import annotations

from typing import Mapping

from .base import Source, SourceConfig, SourceUpdate
from .cowork import CoworkSource
from .codex_cli import CodexCliSource
from .claude_code import ClaudeCodeSource

__all__ = [
    "Source",
    "SourceConfig",
    "SourceUpdate",
    "CoworkSource",
    "CodexCliSource",
    "ClaudeCodeSource",
    "load_sources",
    "REGISTRY",
]

REGISTRY: Mapping[str, type[Source]] = {
    "cowork": CoworkSource,
    "codex_cli": CodexCliSource,
    "claude_code": ClaudeCodeSource,
}


def load_sources(configs: Mapping[str, SourceConfig]) -> list[Source]:
    """Instantiate sources for each enabled config entry."""
    out: list[Source] = []
    for sid, cfg in configs.items():
        if not cfg.enabled:
            continue
        cls = REGISTRY.get(sid)
        if cls is None:
            continue  # unknown source key — silently skip (logged elsewhere)
        out.append(cls(cfg))
    return out
