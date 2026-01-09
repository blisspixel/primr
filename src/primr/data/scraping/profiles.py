"""
Browser fingerprint profiles for stealth scraping.

Separated into three concerns to reduce fingerprint mismatch risk:
1. HttpHeaderProfile - HTTP headers that must match TLS fingerprint
2. BrowserContextProfile - Browser context settings (viewport, locale, timezone)
3. StealthPatch - Minimal JS patches for specific detection bypasses

WARNING: Keep stealth patches minimal. Many properties are read-only or
create detectable inconsistencies if patched naively.
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class HttpHeaderProfile:
    """HTTP headers that must match TLS fingerprint."""
    name: str
    user_agent: str
    sec_ch_ua: Optional[str]
    sec_ch_ua_platform: Optional[str]
    accept_language: str


@dataclass
class BrowserContextProfile:
    """Browser context settings (safe to set via Playwright/DrissionPage)."""
    name: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone: str
    color_scheme: str  # "light" or "dark"


@dataclass
class StealthPatch:
    """
    Minimal JS patches for specific detection bypasses.
    
    WARNING: Keep minimal. Many properties are read-only or create
    detectable inconsistencies if patched naively.
    """
    name: str
    script: str  # JavaScript to inject
    description: str  # What detection it bypasses


# =============================================================================
# Pre-defined HTTP Header Profiles
# Must match curl_cffi impersonation targets
# =============================================================================

HTTP_PROFILES = [
    HttpHeaderProfile(
        name="chrome_124_windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="chrome_124_mac",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"macOS"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="chrome_125_windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        sec_ch_ua='"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="edge_124_windows",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        sec_ch_ua='"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"',
        sec_ch_ua_platform='"Windows"',
        accept_language="en-US,en;q=0.9",
    ),
    HttpHeaderProfile(
        name="safari_17_mac",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        sec_ch_ua=None,  # Safari doesn't send sec-ch-ua
        sec_ch_ua_platform=None,
        accept_language="en-US,en;q=0.9",
    ),
]


# =============================================================================
# Pre-defined Browser Context Profiles
# =============================================================================

CONTEXT_PROFILES = [
    BrowserContextProfile(
        name="desktop_1080p",
        viewport_width=1920,
        viewport_height=1080,
        locale="en-US",
        timezone="America/New_York",
        color_scheme="light",
    ),
    BrowserContextProfile(
        name="desktop_1440p",
        viewport_width=2560,
        viewport_height=1440,
        locale="en-US",
        timezone="America/Los_Angeles",
        color_scheme="light",
    ),
    BrowserContextProfile(
        name="desktop_1200",
        viewport_width=1920,
        viewport_height=1200,
        locale="en-US",
        timezone="America/Chicago",
        color_scheme="light",
    ),
    BrowserContextProfile(
        name="laptop_1366",
        viewport_width=1366,
        viewport_height=768,
        locale="en-US",
        timezone="America/Denver",
        color_scheme="light",
    ),
]


# =============================================================================
# Minimal Stealth Patches
# Only add patches that are proven necessary and safe
# =============================================================================

STEALTH_PATCHES = [
    StealthPatch(
        name="webdriver_false",
        script="Object.defineProperty(navigator, 'webdriver', {get: () => false});",
        description="Hide webdriver flag (basic detection bypass)",
    ),
    # NOTE: Keep this list minimal. Adding more patches increases detection risk.
    # Most "stealth" patches create detectable inconsistencies.
]


# =============================================================================
# Public API Functions
# =============================================================================

def get_random_http_profile() -> HttpHeaderProfile:
    """Get a random HTTP header profile for fingerprint diversity."""
    return random.choice(HTTP_PROFILES)


def get_random_context_profile() -> BrowserContextProfile:
    """Get a random browser context profile."""
    return random.choice(CONTEXT_PROFILES)


def get_stealth_script() -> str:
    """Get combined stealth script (minimal patches only)."""
    return "\n".join(p.script for p in STEALTH_PATCHES)


def get_http_profile_by_name(name: str) -> Optional[HttpHeaderProfile]:
    """Get a specific HTTP profile by name."""
    for profile in HTTP_PROFILES:
        if profile.name == name:
            return profile
    return None


def get_context_profile_by_name(name: str) -> Optional[BrowserContextProfile]:
    """Get a specific context profile by name."""
    for profile in CONTEXT_PROFILES:
        if profile.name == name:
            return profile
    return None
