"""Discover installed OpenPets pet packs.

Walks the standard OpenPets pet locations and returns each `pet.json` it
finds, parsed. Used by `openpets-bridge list-pets` and by the multi-pet
config wizard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Locations OpenPets / OpenPetsKit are known to discover pet packs from.
# Add new locations here when other tools start dropping packs in new
# directories.
DEFAULT_PET_ROOTS: tuple[Path, ...] = (
    Path.home() / "Library/Application Support/OpenPets/Pets",
    Path.home() / ".codex/pets",
    Path.home() / ".config/openpets/pets",
    Path.home() / ".config/openpets/Pets",
    Path.home() / ".local/share/openpets/pets",
)


@dataclass(slots=True, frozen=True)
class Pet:
    pet_id: str
    display_name: str
    description: str
    path: Path

    @property
    def has_spritesheet(self) -> bool:
        return any((self.path / f"spritesheet.{ext}").is_file()
                   for ext in ("webp", "png"))


def discover(extra_roots: list[Path] | None = None) -> list[Pet]:
    """Return all pet packs found across the known + extra roots.

    Skips folders without a parseable `pet.json`. Sorted by display name.
    """
    seen: dict[Path, Pet] = {}
    roots = list(DEFAULT_PET_ROOTS) + list(extra_roots or [])
    for root in roots:
        if not root.is_dir():
            continue
        for pet_json in root.glob("*/pet.json"):
            try:
                with pet_json.open("rb") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            pet = Pet(
                pet_id=str(data.get("id", pet_json.parent.name)),
                display_name=str(data.get("displayName", pet_json.parent.name)),
                description=str(data.get("description", "")),
                path=pet_json.parent,
            )
            seen.setdefault(pet.path, pet)
    return sorted(seen.values(), key=lambda p: p.display_name.lower())
