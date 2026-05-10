"""Display modes for the bridge.

* ``single_pet`` — one OpenPets host shared by every AI; bubbles show the AI
  icon as a prefix in the title. Default for first-time users.
* ``multi_pet``  — one OpenPets host per AI source, each on its own socket
  (and each wearing a different pet pack). Spawns/manages child processes.
"""

from __future__ import annotations

from .single_pet import SinglePetMode
from .multi_pet import MultiPetMode

__all__ = ["SinglePetMode", "MultiPetMode"]
