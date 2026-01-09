"""
Tier registry - defines DEFAULT_TIERS list.

This module exists separately from config.py to avoid circular imports.
config.py loads early (constants only), tier_registry.py loads late
(after all tier modules are defined).
"""

from typing import List, Callable, Optional

from .models import ScrapeTier, ScrapeResult
from .config import (
    DEFAULT_TIMEOUT_REQUESTS,
    DEFAULT_TIMEOUT_HTTPX,
    DEFAULT_TIMEOUT_CURL_CFFI,
    DEFAULT_TIMEOUT_PLAYWRIGHT,
    DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
    DEFAULT_TIMEOUT_DRISSION,
    DEFAULT_TIMEOUT_DRISSION_STEALTH,
    DEFAULT_TIMEOUT_VISION,
)

# Import tier functions
from .http_clients import (
    scrape_with_requests,
    scrape_with_httpx,
    scrape_with_curl_cffi,
)
from .browsers import (
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    scrape_with_drissionpage,
    scrape_with_drissionpage_stealth,
    scrape_with_vision,
)


# =============================================================================
# Default Tier Order
# =============================================================================

# Tiers are tried in order from fastest/lightest to slowest/heaviest.
# Each tier has:
# - name: Unique identifier
# - scrape_fn: Function that takes (url, timeout) and returns ScrapeResult
# - timeout: Default timeout in seconds
# - requires: Optional dependency check (e.g., "curl_cffi" for TLS impersonation)

DEFAULT_TIERS: List[ScrapeTier] = [
    # Tier 1: Basic HTTP (fastest, easily detected)
    ScrapeTier(
        name="requests",
        scrape_fn=scrape_with_requests,
        timeout=DEFAULT_TIMEOUT_REQUESTS,
        requires=None,
    ),
    
    # Tier 2: HTTP/2 with better headers
    ScrapeTier(
        name="httpx",
        scrape_fn=scrape_with_httpx,
        timeout=DEFAULT_TIMEOUT_HTTPX,
        requires="httpx",
    ),
    
    # Tier 3: TLS fingerprint impersonation
    ScrapeTier(
        name="curl_cffi",
        scrape_fn=scrape_with_curl_cffi,
        timeout=DEFAULT_TIMEOUT_CURL_CFFI,
        requires="curl_cffi",
    ),
    
    # Tier 4: Full browser automation
    ScrapeTier(
        name="playwright",
        scrape_fn=scrape_with_playwright,
        timeout=DEFAULT_TIMEOUT_PLAYWRIGHT,
        requires="playwright",
    ),
    
    # Tier 5: Browser with content expansion
    ScrapeTier(
        name="playwright_aggressive",
        scrape_fn=scrape_with_playwright_aggressive,
        timeout=DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE,
        requires="playwright",
    ),
    
    # Tier 6: Driverless browser (CDP)
    ScrapeTier(
        name="drissionpage",
        scrape_fn=scrape_with_drissionpage,
        timeout=DEFAULT_TIMEOUT_DRISSION,
        requires="DrissionPage",
    ),
    
    # Tier 7: Stealth browser with challenge waiting
    ScrapeTier(
        name="drissionpage_stealth",
        scrape_fn=scrape_with_drissionpage_stealth,
        timeout=DEFAULT_TIMEOUT_DRISSION_STEALTH,
        requires="DrissionPage",
    ),
    
    # Tier 8: Vision fallback (opt-in only)
    # NOTE: This tier is skipped unless explicitly enabled
    ScrapeTier(
        name="vision",
        scrape_fn=scrape_with_vision,
        timeout=DEFAULT_TIMEOUT_VISION,
        requires=None,  # Uses Gemini API, not a local dependency
    ),
]


def get_tier_by_name(name: str) -> Optional[ScrapeTier]:
    """Get a tier by name."""
    for tier in DEFAULT_TIERS:
        if tier.name == name:
            return tier
    return None


def get_available_tiers() -> List[ScrapeTier]:
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
                import httpx
            elif tier.requires == "curl_cffi":
                from curl_cffi import requests
            elif tier.requires == "playwright":
                from playwright.sync_api import sync_playwright
            elif tier.requires == "DrissionPage":
                from DrissionPage import ChromiumPage
            
            available.append(tier)
        except ImportError:
            pass
    
    return available


def get_tier_names() -> List[str]:
    """Get list of all tier names."""
    return [tier.name for tier in DEFAULT_TIERS]


def get_available_tier_names() -> List[str]:
    """Get list of available tier names (dependencies installed)."""
    return [tier.name for tier in get_available_tiers()]
