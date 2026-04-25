"""Shared per-run budget for visible browser launches."""

from __future__ import annotations

import os
import sys
import threading

_HEADED_BUDGET_LOCK = threading.Lock()
_HEADED_ATTEMPTS_USED = 0


def default_headed_budget() -> int:
    """Total visible-browser attempts allowed in a single primr run.

    Defaults to 0 — no popups unless the user explicitly opts in via
    PRIMR_MAX_HEADED_POPUPS (e.g. =5 to allow up to five visible-browser
    challenges for a single run).
    """
    raw = os.getenv("PRIMR_MAX_HEADED_POPUPS", "0")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _display_available() -> bool:
    """On Linux, headed Chromium needs an X or Wayland display to launch.

    Returning False here keeps the budget intact on headless servers instead
    of burning it on launches that would just error out.
    """
    platform: str = sys.platform
    if platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def try_consume_headed_budget() -> bool:
    """Atomically reserve one visible browser attempt."""
    global _HEADED_ATTEMPTS_USED
    if not _display_available():
        return False
    cap = default_headed_budget()
    with _HEADED_BUDGET_LOCK:
        if cap <= _HEADED_ATTEMPTS_USED:
            return False
        _HEADED_ATTEMPTS_USED += 1
        return True


def remaining_headed_budget() -> int:
    if not _display_available():
        return 0
    with _HEADED_BUDGET_LOCK:
        return max(0, default_headed_budget() - _HEADED_ATTEMPTS_USED)


def reset_headed_budget_for_testing() -> None:
    global _HEADED_ATTEMPTS_USED
    with _HEADED_BUDGET_LOCK:
        _HEADED_ATTEMPTS_USED = 0
