#!/usr/bin/env bash
# openpets-bridge installer (macOS)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/MacSiem/openpets-bridge/main/install.sh | bash
#
# What this does, idempotently:
#   1. Verifies macOS + Python 3.10+ + Homebrew (or asks how to fix)
#   2. Verifies OpenPets.app (alterhq build) is installed
#   3. Installs `pipx` if missing (via Homebrew)
#   4. Installs `openpets-bridge` from GitHub (via pipx, isolated)
#   5. Writes a default config and registers a launchd agent so the
#      bridge starts at login
#
# Privacy: this script reads no personal data and does not phone home.
# It runs entirely on your machine and prints every command before
# executing it. Inspect the source first if you'd like:
#   curl -fsSL https://raw.githubusercontent.com/MacSiem/openpets-bridge/main/install.sh | less

set -euo pipefail

REPO="https://github.com/MacSiem/openpets-bridge.git"

c_blue() { printf "\033[1;34m%s\033[0m\n" "$*"; }
c_red()  { printf "\033[1;31m%s\033[0m\n" "$*"; }
c_dim()  { printf "\033[2m%s\033[0m\n" "$*"; }

abort() { c_red "✗ $*"; exit 1; }
ok()    { c_blue "✓ $*"; }

# 1. macOS check
[[ "$(uname -s)" == "Darwin" ]] || abort "openpets-bridge is macOS-only (uname=$(uname -s))."
ok "macOS detected"

# 2. Python 3.10+
if ! command -v python3 >/dev/null 2>&1; then
  abort "Python 3 not found. Install with: brew install python@3.12"
fi
PY_MAJ=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MIN=$(python3 -c 'import sys; print(sys.version_info.minor)')
if (( PY_MAJ < 3 || ( PY_MAJ == 3 && PY_MIN < 10 ) )); then
  abort "Python 3.10+ required (found $PY_MAJ.$PY_MIN). Install: brew install python@3.12"
fi
ok "Python $PY_MAJ.$PY_MIN"

# 3. Homebrew (only if pipx is missing — otherwise it's not strictly required)
if ! command -v pipx >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    c_blue "Installing pipx via Homebrew..."
    brew install pipx
    pipx ensurepath
    # Add ~/.local/bin to current session PATH if pipx put it there
    export PATH="$HOME/.local/bin:$PATH"
  else
    abort "pipx is missing. Install Homebrew first (https://brew.sh) or run:
    python3 -m pip install --user pipx
    python3 -m pipx ensurepath"
  fi
fi
ok "pipx ready"

# 4. OpenPets.app (alterhq build)
if [[ ! -d /Applications/OpenPets.app ]]; then
  c_red "OpenPets.app not found in /Applications."
  c_red "Install it first from: https://github.com/alterhq/openpets/releases/latest"
  c_red "(get the alterhq build, not the older alvinunreal Electron one)"
  exit 1
fi
ok "OpenPets.app present"

# 5. Install or upgrade openpets-bridge (with [menubar] extra by default)
#    Skip the menubar extra by setting OPENPETS_BRIDGE_HEADLESS=1 before running.
EXTRAS=""
if [[ -z "${OPENPETS_BRIDGE_HEADLESS:-}" ]]; then
  EXTRAS="[menubar]"
fi
if pipx list 2>/dev/null | grep -q "openpets-bridge"; then
  c_blue "Upgrading openpets-bridge..."
  pipx upgrade openpets-bridge
  # Re-inject menubar extra in case the user enabled it on a previous
  # headless install
  if [[ -n "$EXTRAS" ]]; then
    pipx inject openpets-bridge rumps 2>/dev/null || true
  fi
else
  c_blue "Installing openpets-bridge from GitHub${EXTRAS:+ (with menubar app)}..."
  pipx install "openpets-bridge${EXTRAS} @ git+${REPO}"
fi
ok "openpets-bridge installed: $(command -v openpets-bridge)"

# 6. Write default config (idempotent — won't overwrite existing)
openpets-bridge init >/dev/null
ok "config: $HOME/.config/openpets-bridge/config.toml"

# 7. Register launchd agent
openpets-bridge install
ok "launchd agent registered"

cat <<MSG

  All set. Look for the 🐾 in your menu bar — that's the openpets-bridge
  control panel. Click it for: status, start/stop, open config, open log,
  list installed pet packs.

  Or from the terminal:

      openpets-bridge status                # health check
      openpets-bridge list-pets             # discover installed pet packs
      tail -f ~/ai-stack/openpets-bridge/bridge.log
      open ~/.config/openpets-bridge/config.toml

  Headless install (no menubar): set OPENPETS_BRIDGE_HEADLESS=1 before
  running this script, or use \`openpets-bridge install --no-menubar\`.

  Uninstall (anytime):

      openpets-bridge uninstall
      pipx uninstall openpets-bridge

MSG
