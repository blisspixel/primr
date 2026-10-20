"""Compatibility policy for browser tiers that use Playwright's sync API."""

from __future__ import annotations

import os
import sys

from .models import Attempt, ErrorType, ScrapeResult

SYNC_BROWSER_UNAVAILABLE_REASON = (
    "Playwright and Patchright sync browser tiers require Python 3.11 through 3.15; "
    "Python 3.15 also requires greenlet 3.5.6 or newer. Update Primr's dependencies "
    "before using browser-backed collection."
)


def sync_browser_runtime_supported(version: tuple[int, int] | None = None) -> bool:
    """Return whether Playwright's greenlet-backed sync API is safe to start."""

    runtime = version if version is not None else (sys.version_info.major, sys.version_info.minor)
    if not (3, 11) <= runtime <= (3, 15):
        return False
    if runtime < (3, 15):
        return True
    try:
        import greenlet

        return tuple(int(part) for part in greenlet.__version__.split(".")) >= (3, 5, 6)
    except (ImportError, ValueError):
        return False


def resolve_browser_headless(headless: bool | None) -> bool:
    """Allow CLI or environment policy to force headed browser recovery."""

    if os.getenv("PRIMR_BROWSER_HEADED", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return True if headless is None else headless


def sync_browser_unavailable_result(url: str, tier: str) -> ScrapeResult:
    """Return a typed failure before an unsafe sync browser runtime can start."""

    return ScrapeResult(
        url=url,
        success=False,
        error_type=ErrorType.NETWORK_ERROR,
        error=SYNC_BROWSER_UNAVAILABLE_REASON,
        tier=tier,
        elapsed_ms=0,
        attempts=[
            Attempt(
                tier=tier,
                success=False,
                error=SYNC_BROWSER_UNAVAILABLE_REASON,
                error_type=ErrorType.NETWORK_ERROR,
                elapsed_ms=0,
            )
        ],
    )


__all__ = [
    "SYNC_BROWSER_UNAVAILABLE_REASON",
    "resolve_browser_headless",
    "sync_browser_runtime_supported",
    "sync_browser_unavailable_result",
]
