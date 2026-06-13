"""Lightweight, fail-safe update checking against PyPI.

Modern CLIs tell you when a newer version is out and make upgrading a single
command. This module is the read-side of that: a cached, network-tolerant
lookup of the latest published ``primr`` version on PyPI, plus the small
helpers the ``primr update`` command and the post-run notice share.

Design rules:
- **Never crash a run.** Every network/parse/IO failure is swallowed and
  reported as "no information" (``None``), never raised to the caller.
- **Never block a run.** Lookups use a short timeout and a ~24h on-disk cache
  in the per-user cache dir, so the network is touched at most once a day.
- **Respect opt-out.** ``PRIMR_NO_UPDATE_CHECK=1`` disables the cached check
  entirely (the explicit ``primr update`` command still works).
- **No new dependency.** Uses ``requests`` (already a core dependency) and a
  self-contained version parser so the check adds nothing to the install.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from primr.utils.logging_config import get_logger

logger = get_logger("utils.version_check")

PYPI_JSON_URL = "https://pypi.org/pypi/primr/json"

# Short timeout: an update check is a nicety, not a blocker.
_NETWORK_TIMEOUT_SECONDS = 2.5

# How long a cached PyPI answer is trusted before we look again.
_CACHE_TTL_SECONDS = 24 * 60 * 60

_CACHE_FILENAME = "update_check.json"

# Matches a leading PEP 440-ish release segment: 1.31.0, 2.0, 1.31.0rc1, ...
_VERSION_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)")


def update_check_disabled() -> bool:
    """True when the user has opted out of background update checks."""
    return os.environ.get("PRIMR_NO_UPDATE_CHECK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def parse_version(value: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of release ints.

    Self-contained (no ``packaging`` dependency). Pre-release/build suffixes
    are ignored for comparison, which is fine for our purpose: we only ever
    nudge users toward a *higher release number*. Unparseable input yields an
    empty tuple, which compares as the lowest possible version.
    """
    match = _VERSION_RE.match(value or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a strictly higher release than ``current``."""
    cand = parse_version(candidate)
    cur = parse_version(current)
    if not cand:
        return False
    return cand > cur


def _cache_path() -> Path:
    from primr.utils.user_cache import get_user_cache_dir

    return get_user_cache_dir() / _CACHE_FILENAME


def _read_cache() -> dict | None:
    try:
        path = _cache_path()
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("update-check cache read failed: %s", exc)
    return None


def _write_cache(latest: str) -> None:
    try:
        payload = {"checked_at": time.time(), "latest_version": latest}
        path = _cache_path()
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        tmp.replace(path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("update-check cache write failed: %s", exc)


def fetch_latest_version(timeout: float = _NETWORK_TIMEOUT_SECONDS) -> str | None:
    """Query PyPI for the latest released ``primr`` version.

    Returns the version string, or ``None`` on any failure (offline, timeout,
    malformed response). Never raises.
    """
    import requests

    try:
        resp = requests.get(
            PYPI_JSON_URL,
            headers={"Accept": "application/json", "User-Agent": "primr-update-check"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        version = data.get("info", {}).get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except Exception as exc:
        logger.debug("PyPI version lookup failed: %s", exc)
    return None


def get_latest_version(*, force: bool = False) -> str | None:
    """Return the latest PyPI version, using the ~24h cache when fresh.

    ``force=True`` bypasses both the opt-out and the cache (used by the
    explicit ``primr update`` command). Otherwise honors
    ``PRIMR_NO_UPDATE_CHECK`` and serves a cached value when it is still fresh.
    """
    if force:
        latest = fetch_latest_version()
        if latest:
            _write_cache(latest)
        return latest

    if update_check_disabled():
        return None

    cache = _read_cache()
    if cache:
        checked_at = cache.get("checked_at", 0)
        cached_version = cache.get("latest_version")
        try:
            age = time.time() - float(checked_at)
        except (TypeError, ValueError):
            age = _CACHE_TTL_SECONDS + 1
        if isinstance(cached_version, str) and age < _CACHE_TTL_SECONDS:
            return cached_version

    latest = fetch_latest_version()
    if latest:
        _write_cache(latest)
    return latest


def check_for_update(current: str, *, force: bool = False) -> str | None:
    """Return the latest version string iff it is newer than ``current``.

    ``None`` means "up to date, unknown, or check disabled" — callers treat all
    three identically (show nothing). Never raises.
    """
    try:
        latest = get_latest_version(force=force)
    except Exception as exc:  # pragma: no cover - get_latest_version is itself safe
        logger.debug("update check failed: %s", exc)
        return None
    if latest and is_newer(latest, current):
        return latest
    return None


@dataclass(frozen=True)
class InstallMethod:
    """How this primr was installed, and the command to upgrade it."""

    kind: str  # "pipx" | "pip" | "unknown"
    upgrade_command: list[str]
    note: str = ""


def detect_install_method() -> InstallMethod:
    """Best-effort detection of how the running primr was installed.

    pipx installs live under a ``pipx/venvs`` path; everything else is treated
    as a pip install into the current interpreter. The returned command is what
    ``primr update`` will run.
    """
    exe = Path(sys.prefix).resolve()
    parts = {p.lower() for p in exe.parts}
    looks_like_pipx = "pipx" in parts or "venvs" in {p.lower() for p in exe.parts}

    # pipx venvs are typically <pipx home>/venvs/primr/...
    if looks_like_pipx and "primr" in {p.lower() for p in exe.parts}:
        return InstallMethod(
            kind="pipx",
            upgrade_command=["pipx", "upgrade", "primr"],
            note="Detected a pipx install.",
        )

    return InstallMethod(
        kind="pip",
        upgrade_command=[sys.executable, "-m", "pip", "install", "--upgrade", "primr"],
        note="Detected a pip install (using the current interpreter).",
    )
