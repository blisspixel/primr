"""
Configuration constants and dataclasses for the scraping module.

NOTE: This module contains ONLY constants and dataclasses.
DEFAULT_TIERS is defined in tier_registry.py to avoid circular imports.
"""

from dataclasses import dataclass

# =============================================================================
# Rate Limiting Configuration
# =============================================================================

@dataclass
class RateLimitConfig:
    """Per-host rate limiting configuration."""
    per_host_concurrency: int = 2          # Max concurrent requests per host
    per_host_requests_per_minute: int = 20 # Max requests per minute per host
    per_run_max_pages: int = 500           # Max pages per scrape run
    base_delay_seconds: float = 1.5        # Base delay between requests
    max_delay_seconds: float = 5.0         # Max delay (with jitter)
    backoff_multiplier: float = 2.0        # Exponential backoff for 429s


# =============================================================================
# Sitemap Configuration
# =============================================================================

@dataclass
class SitemapConfig:
    """Safety constraints for sitemap parsing."""
    max_sitemap_depth: int = 3             # Max depth for sitemap index recursion
    max_urls_per_sitemap: int = 100000     # Stop after N URLs (with log)
    max_sitemap_size_mb: int = 50          # Treat larger sitemaps as special mode
    stream_parse: bool = True              # Stream parse XML to avoid memory issues


# =============================================================================
# Content Thresholds
# =============================================================================

MIN_CONTENT_LENGTH_BYTES = 5000  # 5KB for HTML
MIN_UNIQUE_LINE_RATIO = 0.3     # Less than 30% unique lines is suspicious


# =============================================================================
# WAF Detection Signatures
# =============================================================================

WAF_SIGNATURES = [
    # Cloudflare
    ("cloudflare", "Cloudflare protection"),
    ("just a moment", "Cloudflare challenge"),
    ("ray id:", "Cloudflare block"),
    ("cf-browser-verification", "Cloudflare verification"),
    ("cf_clearance", "Cloudflare clearance"),

    # Akamai
    ("akamai", "Akamai bot protection"),
    ("ak_bmsc", "Akamai cookie"),
    ("bm_sz", "Akamai cookie"),

    # Imperva/Incapsula
    ("incapsula", "Incapsula WAF"),
    ("imperva", "Imperva WAF"),
    ("visid_incap", "Incapsula cookie"),

    # DataDome
    ("datadome", "DataDome protection"),
    ("dd_cookie_test", "DataDome cookie"),

    # PerimeterX
    ("perimeterx", "PerimeterX protection"),
    ("px-captcha", "PerimeterX captcha"),
    ("_pxhd", "PerimeterX cookie"),

    # Kasada
    ("kasada", "Kasada protection"),
    ("x-kpsdk", "Kasada header"),

    # Distil Networks
    ("distil", "Distil Networks"),
    ("d_id", "Distil cookie"),

    # WireWall (seen on torexgold)
    ("wirewall", "WireWall bot protection"),

    # Generic indicators
    ("captcha", "CAPTCHA required"),
    ("access denied", "Access denied"),
    ("forbidden", "Forbidden"),
    ("verify you are human", "Human verification"),
    ("checking your browser", "Browser check"),
    ("ddos protection", "DDoS protection"),
    ("unusual traffic", "Unusual traffic"),
    ("automated access", "Automated access detected"),
    ("bot detected", "Bot detected"),
    ("enable cookies", "Cookies required"),
    ("security check", "Security check"),
    ("one more step", "Additional verification"),
    ("please wait", "Please wait"),
    ("too many requests", "Rate limited"),
    ("rate limit", "Rate limited"),
]


# =============================================================================
# Common URL Patterns for Business Research (60+)
# =============================================================================

COMMON_PAGE_PATTERNS = [
    # About
    "/about", "/about-us", "/about-us/", "/company", "/who-we-are",
    "/our-story", "/our-company", "/corporate", "/overview",

    # Leadership & Team
    "/leadership", "/team", "/management", "/board", "/executives",
    "/board-of-directors", "/leadership-team", "/our-team", "/people",
    "/management-team", "/executive-team", "/founders",

    # Investors & Financials
    "/investors", "/investor-relations", "/financials", "/ir",
    "/investor", "/shareholders", "/annual-report", "/sec-filings",
    "/quarterly-results", "/earnings", "/stock",

    # Products & Services
    "/products", "/services", "/solutions", "/offerings", "/platform",
    "/what-we-do", "/capabilities", "/technology", "/features",

    # Industries & Markets
    "/industries", "/markets", "/sectors", "/verticals", "/segments",

    # Customers & Case Studies
    "/customers", "/clients", "/case-studies", "/success-stories",
    "/testimonials", "/references", "/portfolio",

    # Partners
    "/partners", "/partnerships", "/alliances", "/ecosystem",
    "/channel-partners", "/technology-partners",

    # News & Press
    "/news", "/press", "/newsroom", "/press-releases", "/media",
    "/announcements", "/blog", "/insights", "/resources",

    # Careers
    "/careers", "/jobs", "/join-us", "/work-with-us", "/opportunities",
    "/employment", "/hiring", "/open-positions",

    # Contact
    "/contact", "/contact-us", "/get-in-touch", "/locations", "/offices",

    # ESG & Sustainability
    "/sustainability", "/esg", "/corporate-responsibility", "/csr",
    "/environmental", "/social-responsibility", "/impact",

    # Legal & Compliance
    "/privacy", "/privacy-policy", "/terms", "/terms-of-service",
    "/legal", "/compliance", "/security",

    # Support
    "/support", "/help", "/faq", "/documentation", "/docs",

    # Pricing
    "/pricing", "/plans", "/packages",
]


# =============================================================================
# Timeouts (in seconds unless noted)
# =============================================================================
# Based on Antea scraper analysis (88.1% coverage with 60s total budget)
# Philosophy: If a tier works, it works quickly. Long waits = tier won't work.

DEFAULT_TIMEOUT_REQUESTS = 10       # Simple HTTP (Antea: 10s)
DEFAULT_TIMEOUT_HTTPX = 10          # HTTP/2 (Antea: 10s)
DEFAULT_TIMEOUT_CURL_CFFI = 10      # TLS fingerprint (Antea: 10s)
DEFAULT_TIMEOUT_DRISSION = 15       # Driverless browser
DEFAULT_TIMEOUT_PLAYWRIGHT = 15     # Full browser (Antea: 20s for basic)
DEFAULT_TIMEOUT_DRISSION_STEALTH = 20  # Stealth browser
DEFAULT_TIMEOUT_PLAYWRIGHT_AGGRESSIVE = 15  # Interactive browser (Antea: 15s)
DEFAULT_TIMEOUT_VISION = 30         # Vision AI (LLM extraction, needs time)

# Total potential: 125s (still more generous than Antea's 60s)
# In practice: orchestrator's max_page_time=90s allows multiple tier attempts while being reasonable
# Philosophy: Content quality > speed. Be patient to get the content, but stop after 3 consecutive failures.
