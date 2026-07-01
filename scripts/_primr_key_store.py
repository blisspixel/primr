"""Shared helpers for scripts that need to save Primr configuration keys."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from primr.config.env import set_user_key


def save_primr_key(name: str, value: str) -> Path:
    """Persist a Primr key through the same local store used by `primr keys set`."""
    _, path = set_user_key(name, value)
    return path
