#!/usr/bin/env bash
# Easy one-line installer for primr (macOS / Linux)
# Usage (recommended):
#   curl -fsSL https://raw.githubusercontent.com/blisspixel/primr/main/scripts/install.sh | bash

set -euo pipefail

PACKAGE="primr"
CLI="primr"

echo "==> Installing $PACKAGE ..."

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 (3.12+) is required."
    exit 1
fi

PYTHON=python3
PYVER=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
if [ "$(printf '%s\n' "3.12" "$PYVER" | sort -V | head -1)" != "3.12" ]; then
    echo "Error: Python 3.12+ is required (found $PYVER)."
    exit 1
fi

if ! command -v pipx >/dev/null 2>&1; then
    echo "==> pipx not found. Installing pipx..."
    $PYTHON -m pip install --user pipx
    $PYTHON -m pipx ensurepath
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> Using pipx to install $PACKAGE ..."
pipx install "$PACKAGE"

echo ""
echo "==> Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Open a new terminal"
echo "  2. Run: $CLI init          # Guided setup for API keys + browser"
echo "  3. Run: $CLI doctor        # Verify everything"
echo ""
echo "Quick start:"
echo "  $CLI \"Company Name\" https://company.com"
echo ""
echo "For development / editable from source:"
echo "  git clone https://github.com/blisspixel/primr.git"
echo "  cd primr"
echo "  pipx install -e ."
echo ""