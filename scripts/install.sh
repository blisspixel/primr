#!/usr/bin/env bash
# Easy one-line installer / updater for primr (macOS / Linux)
# Usage (recommended):
#   curl -fsSL https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.sh | bash
#
# Idempotent: run it again any time to upgrade to the latest release.

set -euo pipefail

PACKAGE="primr"
CLI="primr"

echo "==> Installing / updating $PACKAGE ..."

# --- Locate a suitable Python (3.12+) ---
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 (3.12+) is required."
    echo "Install it from https://www.python.org/downloads/ or your package manager."
    exit 1
fi

PYTHON=python3
PYVER=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
if [ "$(printf '%s\n' "3.12" "$PYVER" | sort -V | head -1)" != "3.12" ]; then
    echo "Error: Python 3.12+ is required (found $PYVER)."
    exit 1
fi
echo "==> Using Python $PYVER"

# --- Ensure pipx is available ---
if ! command -v pipx >/dev/null 2>&1; then
    echo "==> pipx not found. Installing pipx..."
    $PYTHON -m pip install --user pipx
    $PYTHON -m pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
fi

# --- Install fresh, or upgrade an existing install (idempotent) ---
if pipx list 2>/dev/null | grep -qi "package $PACKAGE\|[[:space:]]$PACKAGE[[:space:]]"; then
    echo "==> $PACKAGE is already installed. Upgrading to the latest release..."
    pipx upgrade "$PACKAGE"
else
    echo "==> Installing $PACKAGE with pipx..."
    pipx install "$PACKAGE"
fi

# --- Verify ---
echo ""
if command -v "$CLI" >/dev/null 2>&1; then
    INSTALLED_VER=$("$CLI" --version 2>/dev/null || echo "$PACKAGE")
    echo "==> Installed: $INSTALLED_VER"
    echo "    at $(command -v "$CLI")"
else
    echo "==> Installed, but '$CLI' is not on PATH in this shell yet."
    echo "    Open a new terminal so the updated PATH takes effect."
fi

echo ""
echo "==> Done."
echo ""
echo "Next steps:"
echo "  1. Open a new terminal (so PATH is fresh)"
echo "  2. Run: $CLI init          # Guided setup for API keys + browser"
echo "  3. Run: $CLI doctor        # Verify everything"
echo ""
echo "Quick start:"
echo "  $CLI \"Company Name\" https://company.com"
echo ""
echo "To update later:"
echo "  $CLI update                # Self-update to the latest release"
echo ""
echo "For development / editable from source:"
echo "  git clone https://github.com/blisspixel/primr.git"
echo "  cd primr"
echo "  pipx install -e ."
echo ""
