#!/usr/bin/env bash
# Installer / updater for primr (macOS / Linux)
# Recommended: download this file, inspect it, then run it with bash.
#
# Idempotent: run it again any time to upgrade to the latest release.

set -euo pipefail

PACKAGE="primr"
CLI="primr"

echo "==> Installing / updating $PACKAGE ..."

tool_guidance() {
    echo "Install uv (https://docs.astral.sh/uv/getting-started/installation/) and rerun this script."
    echo "Or install pipx with your package manager:"
    if command -v pacman >/dev/null 2>&1; then
        echo "  sudo pacman -S python-pipx"
    elif command -v apt-get >/dev/null 2>&1; then
        echo "  sudo apt install pipx"
    elif command -v dnf >/dev/null 2>&1; then
        echo "  sudo dnf install pipx"
    elif command -v brew >/dev/null 2>&1; then
        echo "  brew install pipx"
    else
        echo "  https://pipx.pypa.io/stable/how-to/install-pipx.html"
    fi
}

# pipx may also select UV as its backend, so check it before either route.
if command -v uv >/dev/null 2>&1; then
    UV_VERSION=$(uv --version)
    if [[ ! "$UV_VERSION" =~ ^uv\ ([0-9]+)\.([0-9]+)\.([0-9]+)($|[[:space:]]) ]] || \
        (( BASH_REMATCH[1] == 0 && (BASH_REMATCH[2] < 13 || (BASH_REMATCH[2] == 13 && BASH_REMATCH[3] < 4)) )); then
        echo "Error: UV 0.13.4 or newer is required to repair its TLS trust store."
        tool_guidance
        exit 1
    fi
fi
PATCHED_PIP_URL="https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"

# Keep an existing pipx install with its manager; prefer uv for fresh installs.
PIPX_INSTALLED=false
if command -v pipx >/dev/null 2>&1 && \
    pipx list 2>/dev/null | grep -Ei "^[[:space:]]*package $PACKAGE([[:space:]]|$)" >/dev/null; then
    PIPX_INSTALLED=true
fi

if [ "$PIPX_INSTALLED" = false ] && command -v uv >/dev/null 2>&1; then
    INSTALLER=uv
    PATH_COMMAND="uv tool update-shell"
    echo "==> Using uv with Python 3.15 (downloaded automatically if needed)"
else
    INSTALLER=pipx
    PATH_COMMAND="pipx ensurepath"
    PIPX_COMMAND=(pipx)

    # Validate actual versions: a versioned executable can itself be a shim.
    PYTHON=""
    for CANDIDATE in python3.15 python3.14 python3.13 python3.12 python3.11 python3; do
        if command -v "$CANDIDATE" >/dev/null 2>&1 && \
            "$CANDIDATE" -c 'import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 15)))' 2>/dev/null; then
            PYTHON="$(command -v "$CANDIDATE")"
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "Error: pipx needs Python 3.11 through 3.15 for Primr installs."
        tool_guidance
        exit 1
    fi
    PYVER=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "==> Using Python $PYVER"

    if ! command -v pipx >/dev/null 2>&1; then
        if "$PYTHON" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)'; then
            echo "Error: the selected Python is a virtual environment; install uv or pipx separately."
            tool_guidance
            exit 1
        fi
        # PEP 668 also prohibits --user installs outside a virtual environment.
        if "$PYTHON" -c 'import sys, sysconfig; from pathlib import Path; sys.exit(not (sys.prefix == sys.base_prefix and (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").is_file()))'; then
            echo "Error: this Python is externally managed; install pipx with your package manager."
            tool_guidance
            exit 1
        fi
        if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
            echo "Error: pipx and pip are unavailable."
            tool_guidance
            exit 1
        fi
        echo "==> pipx not found. Installing pipx..."
        "$PYTHON" -m pip install --user --no-deps --no-cache-dir "$PATCHED_PIP_URL"
        "$PYTHON" -m pip install --user pipx
        PIPX_COMMAND=("$PYTHON" -m pipx)
        "${PIPX_COMMAND[@]}" ensurepath
        export PATH="${PIPX_BIN_DIR:-$HOME/.local/bin}:$PATH"
    fi
fi

# --- Dev mode: if run from inside a primr checkout, install EDITABLE from source
# so `primr` tracks the working tree instead of a frozen PyPI release. That trap
# (a released install shadowing local edits) is what makes new commands like
# `keys set openai` look "missing". A downloaded copy outside a checkout
# installs the published package instead.
REPO_ROOT=""
SCRIPT_SRC="${BASH_SOURCE[0]:-}"
if [ -n "$SCRIPT_SRC" ] && [ -f "$SCRIPT_SRC" ]; then
    CANDIDATE="$(cd "$(dirname "$SCRIPT_SRC")/.." && pwd)"
    if [ -f "$CANDIDATE/pyproject.toml" ] && grep -q 'name *= *"primr"' "$CANDIDATE/pyproject.toml"; then
        REPO_ROOT="$CANDIDATE"
    fi
fi

if [ -n "$REPO_ROOT" ]; then
    echo "==> Detected a primr checkout at $REPO_ROOT"
    echo "==> Installing EDITABLE from source (dev mode) so 'primr' tracks your working tree."
    echo "    For day-to-day dev, 'uv run primr' from the repo is the lightest path."
fi

if [ "$INSTALLER" = uv ]; then
    if [ -n "$REPO_ROOT" ]; then
        uv tool install --upgrade --python 3.15 --editable "$REPO_ROOT"
    else
        uv tool install --upgrade --python 3.15 "$PACKAGE"
    fi
else
    # Repair shared pip without a package-index lookup, then verify the result.
    "${PIPX_COMMAND[@]}" upgrade-shared --pip-args "--no-index --no-deps $PATCHED_PIP_URL"
    SHARED_LIBS=$("${PIPX_COMMAND[@]}" environment --value PIPX_SHARED_LIBS)
    "$PYTHON" -c 'import sys; from pathlib import Path; from importlib.metadata import distributions; root=Path(sys.argv[1]); paths=[root/"Lib/site-packages", *root.glob("lib/python*/site-packages")]; versions=[d.version for p in paths for d in distributions(path=[str(p)]) if d.metadata["Name"].lower()=="pip"]; sys.exit(0 if versions and all(tuple(map(int,v.split("."))) >= (26,2,2) for v in versions) else "Repair pipx shared installer to pip >=26.2.2 before continuing")' "$SHARED_LIBS"
    if [ "$PIPX_INSTALLED" = true ]; then
        # --force install ignores --python in older distro pipx releases.
        echo "==> Reinstalling $PACKAGE with Python $PYVER..."
        "${PIPX_COMMAND[@]}" reinstall --python "$PYTHON" "$PACKAGE"
    fi
    if [ -n "$REPO_ROOT" ]; then
        "${PIPX_COMMAND[@]}" install --force --editable --python "$PYTHON" "$REPO_ROOT"
    elif [ "$PIPX_INSTALLED" = false ]; then
        echo "==> Installing $PACKAGE with pipx..."
        "${PIPX_COMMAND[@]}" install --python "$PYTHON" "$PACKAGE"
    fi
fi

# --- Verify ---
echo ""
if command -v "$CLI" >/dev/null 2>&1; then
    INSTALLED_VER=$("$CLI" --version 2>/dev/null || echo "$PACKAGE")
    echo "==> Installed: $INSTALLED_VER"
    echo "    at $(command -v "$CLI")"
else
    echo "==> Installed, but '$CLI' is not on PATH in this shell yet."
    echo "    Run '$PATH_COMMAND', then open a new terminal."
fi

echo ""
echo "==> Done."
echo ""
echo "Keyless agent-host path:"
echo "  1. Open a new terminal (so PATH is fresh)"
echo "  2. Run: $CLI prep \"ExampleCo\" https://example.co --dry-run"
echo "  3. Run: $CLI prep \"ExampleCo\" https://example.co"
echo ""
echo "Provider-backed path:"
echo "  1. Run: $CLI init          # Guided provider setup"
echo "  2. Run: $CLI doctor        # Verify configuration"
echo "  3. Run: $CLI \"ExampleCo\" https://example.co --dry-run"
echo "     Review the estimate and approve spend before launching the paid run."
echo ""
echo "To update later:"
echo "  $CLI update                # Self-update to the latest release"
echo ""
echo "For development / editable from source:"
echo "  git clone https://github.com/blisspixel/primr.git"
echo "  cd primr"
echo "  uv tool install --python 3.15 --editable ."
echo ""
