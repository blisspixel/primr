"""
Tier registry - defines DEFAULT_TIERS list.

This module exists separately from config.py to avoid circular imports.
config.py loads early (constants only), tier_registry.py loads late
(after all tier modules are defined).
"""

from .browsers import (
    scrape_with_drissionpage,
    scrape_with_drissionpage_stealth,
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    scrape_with_vision,
)
from .config import (
    DEFAULT_TIMEOUT_CURL_CFFI,
    DEFAULT_TIMEOUT_DRISSION,
    DEFAULT_TIMEOUT_DRISSION_STEALTH,
    DEFAULT_TIMEOUT_HTTPX,
    DEFAULT_TIMEOUT_PLAYWRIGHT,
    DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
    DEFAULT_TIMEOUT_REQUESTS,
    DEFAULT_TIMEOUT_VISION,
)

# Import tier functions
from .http_clients import (
    scrape_with_curl_cffi,
    scrape_with_httpx,
    scrape_with_requests,
)
from .models import ScrapeTier
from .stealth_browser import scrape_with_patchright

# =============================================================================
# Default Tier Order (2026 - Browser First, Vision as Safety Net)
# =============================================================================

# Modern corporate websites: JS-heavy, image-heavy, WAF-protected.
# Order optimized for success rate on real business sites in 2026.
#
# Philosophy: GET THE CONTENT. Period.
# - Browser tiers first (handles JS rendering - 95% of modern sites)
# - Stealth tiers for bot protection (Cloudflare, Akamai, etc.)
# - Vision tier as safety net (costs ~$0.01-0.02 but works on almost anything)
# - Simple HTTP as last resort (rare for corporate sites)
#
# The user said it best: "I DONT FUCKING CARE if it costs a few cents...
# WE MUST have it work"

DEFAULT_TIERS: list[ScrapeTier] = [
    # Tier 1: Full browser (works on 95%+ of modern sites)
    ScrapeTier(
        name="playwright",
        scrape_fn=scrape_with_playwright,
        timeout=DEFAULT_TIMEOUT_PLAYWRIGHT,
        requires="playwright",
    ),
    # Tier 2: Browser with content expansion (lazy-loaded, accordions)
    ScrapeTier(
        name="playwright_aggressive",
        scrape_fn=scrape_with_playwright_aggressive,
        timeout=DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
        requires="playwright",
    ),
    # Tier 3: Patchright stealth browser (real Chrome + persistent profile).
    # Bypasses Kasada / Akamai / PerimeterX challenges that blank on plain
    # Playwright. Expensive (~15-30s per page); escalated to by orchestrator
    # when earlier tiers return challenge shells.
    ScrapeTier(
        name="patchright",
        scrape_fn=scrape_with_patchright,
        timeout=60,
        requires="patchright",
    ),
    # Tier 4: TLS fingerprint impersonation (some bot detection)
    ScrapeTier(
        name="curl_cffi",
        scrape_fn=scrape_with_curl_cffi,
        timeout=DEFAULT_TIMEOUT_CURL_CFFI,
        requires="curl_cffi",
    ),
    # Tier 5: Stealth browser (Cloudflare/heavy protection)
    ScrapeTier(
        name="drissionpage_stealth",
        scrape_fn=scrape_with_drissionpage_stealth,
        timeout=DEFAULT_TIMEOUT_DRISSION_STEALTH,
        requires="DrissionPage",
    ),
    # Tier 6: Driverless browser (CDP fallback)
    ScrapeTier(
        name="drissionpage",
        scrape_fn=scrape_with_drissionpage,
        timeout=DEFAULT_TIMEOUT_DRISSION,
        requires="DrissionPage",
    ),
    # Tier 7: Vision AI - screenshot + Gemini extraction. Costs ~$0.01-0.02
    # per page but works on almost anything that renders in a browser.
    ScrapeTier(
        name="vision",
        scrape_fn=scrape_with_vision,
        timeout=DEFAULT_TIMEOUT_VISION,
        requires=None,  # Only requires GEMINI_API_KEY which we already need
    ),
    # Tier 8: HTTP/2 (simple sites fallback - rare in 2026)
    ScrapeTier(
        name="httpx",
        scrape_fn=scrape_with_httpx,
        timeout=DEFAULT_TIMEOUT_HTTPX,
        requires="httpx",
    ),
    # Tier 9: Basic HTTP (last resort - almost never works on modern sites)
    ScrapeTier(
        name="requests",
        scrape_fn=scrape_with_requests,
        timeout=DEFAULT_TIMEOUT_REQUESTS,
        requires=None,
    ),
]


def get_tier_by_name(name: str) -> ScrapeTier | None:
    """Get a tier by name."""
    for tier in DEFAULT_TIERS:
        if tier.name == name:
            return tier
    return None


def get_available_tiers() -> list[ScrapeTier]:
    """
    Get list of tiers that have their dependencies installed.

    Checks each tier's 'requires' field and filters out unavailable tiers.
    """
    available = []

    for tier in DEFAULT_TIERS:
        if tier.requires is None:
            available.append(tier)
            continue

        # Check if dependency is installed
        try:
            if tier.requires == "httpx":
                import httpx  # noqa: F401
            elif tier.requires == "curl_cffi":
                from curl_cffi import requests  # noqa: F401
            elif tier.requires == "playwright":
                from playwright.sync_api import sync_playwright
            elif tier.requires == "patchright":
                from patchright.sync_api import sync_playwright  # noqa: F401
            elif tier.requires == "DrissionPage":
                from DrissionPage import ChromiumPage  # noqa: F401

            available.append(tier)
        except ImportError:
            pass

    return available


def get_tier_names() -> list[str]:
    """Get list of all tier names."""
    return [tier.name for tier in DEFAULT_TIERS]


def get_available_tier_names() -> list[str]:
    """Get list of available tier names (dependencies installed)."""
    return [tier.name for tier in get_available_tiers()]
