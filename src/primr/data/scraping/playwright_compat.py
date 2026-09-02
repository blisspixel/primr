"""Compatibility policy for browser tiers that use Playwright's sync API."""

from __future__ import annotations

import sys

SYNC_BROWSER_UNAVAILABLE_REASON = (
    "Playwright and Patchright sync browser tiers are disabled on Python 3.15 "
    "until upstream greenlet compatibility is verified; use Python 3.12 through 3.14 "
    "for browser-complete runs"
)


def sync_browser_runtime_supported(version: tuple[int, int] | None = None) -> bool:
    """Return whether Playwright's greenlet-backed sync API is safe to start."""

    runtime = version if version is not None else (sys.version_info.major, sys.version_info.minor)
    return runtime < (3, 15)


__all__ = ["SYNC_BROWSER_UNAVAILABLE_REASON", "sync_browser_runtime_supported"]
