"""Source ABC and shared dataclasses.

A Source watches one kind of agent activity (Cowork sessions, Codex CLI
rollouts, Claude Code project transcripts, llm-router scripts, …) and
produces SourceUpdate snapshots that the orchestrator forwards to OpenPets.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Iterable


# OpenPets `notify --status` enum
PetStatus = str  # one of: running | review | done | failed | waiting | message


@dataclass(slots=True, frozen=True)
class SourceUpdate:
    """One observed agent activity snapshot.

    The orchestrator de-dupes / pushes notifies based on (source_id, session_id).
    """

    source_id: str         # e.g. "cowork" / "codex_cli" / "claude_code" — same as Source.id
    session_id: str        # opaque per-conversation key (uuid, path, ...)
    title: str             # short human title (e.g. Cowork chat title)
    body: str              # short status text (e.g. "✎ bridge.py" / "▶ ls -la")
    status: PetStatus      # OpenPets status enum
    is_active: bool        # True = still running, False = quiet/done/failed
    extras: dict | None = None  # optional source-specific debug payload


@dataclass(slots=True, frozen=True)
class SourceConfig:
    """User-configurable knobs for a source. Built from TOML."""

    enabled: bool
    label: str             # display name, e.g. "Cowork"
    icon: str              # short single-glyph or emoji shown in bubble
    pet: str | None = None       # multi-pet mode: pet pack id to use
    redact_body: bool = False    # if True, bubble body shows ONLY the tool
                                 # type/glyph — never inputs (safer for
                                 # screenshots / streaming / pair-coding)
    extra: dict | None = None    # source-specific (paths, filters, ...)


class Source(abc.ABC):
    """Abstract source of agent activity updates."""

    #: Stable short identifier — used as TOML section key, threadId namespace,
    #: and source_id in SourceUpdate.
    id: str = ""

    def __init__(self, config: SourceConfig) -> None:
        self.config = config

    @abc.abstractmethod
    def poll(self) -> Iterable[SourceUpdate]:
        """Return zero or more updates seen since the last poll.

        Implementations should be idempotent and cheap. Polling cadence is
        decided by the orchestrator (typically ~1 second).
        """
        raise NotImplementedError
