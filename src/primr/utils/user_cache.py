"""Per-user cache directory for state shared across runs and invocation dirs.

Vendor research, recon caches, and similar artifacts have no business being
duplicated per company folder: regenerating them per invocation directory
wastes Deep Research budget and time, and the legacy ``PROJECT_ROOT``-based
location lands inside site-packages for pip installs. This module is the one
place that decides where that shared state lives.

Resolution order:
1. ``PRIMR_CACHE_DIR`` env var (explicit override, e.g. to keep the cache
   out of a synced folder)
2. ``%LOCALAPPDATA%\\primr`` on Windows
3. ``$XDG_CACHE_HOME/primr`` when XDG_CACHE_HOME is set
4. ``~/.cache/primr`` otherwise
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from primr.utils.logging_config import get_logger

logger = get_logger("utils.user_cache")


def get_user_cache_dir() -> Path:
    """Return the per-user primr cache root (created on first use)."""
    override = os.environ.get("PRIMR_CACHE_DIR", "").strip()
    if override:
        root = Path(override)
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        root = base / "primr"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
        base = Path(xdg) if xdg else Path.home() / ".cache"
        root = base / "primr"

    root.mkdir(parents=True, exist_ok=True)
    return root


def get_user_cache_subdir(name: str) -> Path:
    """Return (and create) a named subdirectory of the user cache."""
    subdir = get_user_cache_dir() / name
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir


def migrate_legacy_file(legacy_path: Path, new_path: Path) -> bool:
    """One-time migration: move a legacy cache file to its per-user location.

    Returns True when a migration happened. No-op when the legacy file is
    missing or the new path already exists (the per-user copy wins). Failures
    are logged and swallowed — a failed migration just means the file is
    regenerated at the new location, never a crashed run.
    """
    try:
        if not legacy_path.exists() or new_path.exists():
            return False
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_path), str(new_path))
        logger.info("Migrated legacy cache file %s -> %s", legacy_path, new_path)
        return True
    except Exception as e:
        logger.warning("Could not migrate legacy cache file %s: %s", legacy_path, e)
        return False
