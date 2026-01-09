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
# Default Tier Order (2026 - Browser First)
# =============================================================================

# Modern corporate websites: JS-heavy, image-heavy, or bot-protected.
# Order optimized for success rate on real business sites.
#
# Logic:
# 1. Browser tiers first (handles JS rendering - 95% of modern sites)
# 2. Stealth tiers for bot protection (Cloudflare, etc.)
# 3. Vision for image-heavy sites where text extraction fails
# 4. Simple HTTP as last resort (rare for corporate sites)

DEFAULT_TIERS: List[ScrapeTier] = [
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
    
    # Tier 3: TLS fingerprint impersonation (some bot detection)
    ScrapeTier(
        name="curl_cffi",
        scrape_fn=scrape_with_curl_cffi,
        timeout=DEFAULT_TIMEOUT_CURL_CFFI,
        requires="curl_cffi",
    ),
    
    # Tier 4: Stealth browser (Cloudflare/heavy protection)
    ScrapeTier(
        name="drissionpage_stealth",
        scrape_fn=scrape_with_drissionpage_stealth,
        timeout=DEFAULT_TIMEOUT_DRISSION_STEALTH,
        requires="DrissionPage",
    ),
    
    # Tier 5: Driverless browser (CDP fallback)
    ScrapeTier(
        name="drissionpage",
        scrape_fn=scrape_with_drissionpage,
        timeout=DEFAULT_TIMEOUT_DRISSION,
        requires="DrissionPage",
    ),
    
    # Tier 6: Vision AI (image-heavy sites where text extraction fails)
    ScrapeTier(
        name="vision",
        scrape_fn=scrape_with_vision,
        timeout=DEFAULT_TIMEOUT_VISION,
        requires=None,
    ),
    
    # Tier 7: HTTP/2 (simple sites fallback)
    ScrapeTier(
        name="httpx",
        scrape_fn=scrape_with_httpx,
        timeout=DEFAULT_TIMEOUT_HTTPX,
        requires="httpx",
    ),
    
    # Tier 8: Basic HTTP (last resort)
    ScrapeTier(
        name="requests",
        scrape_fn=scrape_with_requests,
        timeout=DEFAULT_TIMEOUT_REQUESTS,
        requires=None,
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
