"""
Resilient Scraping Module

A modular, testable architecture for web scraping with tiered fallbacks.
Refactored from the monolithic scrape.py for better maintainability.

Public API:
- ScrapeOrchestrator: Main coordinator for tiered scraping
- ScrapeResult: Standardized result from all tiers
- ScrapeCache: LRU + disk caching with URL normalization
- TraceLogger: Scrape trace artifact logging
- RateLimiter: Per-host rate limiting

Tier functions (for direct use or custom orchestration):
- scrape_with_requests: Basic HTTP (fastest)
- scrape_with_httpx: HTTP/2 with better headers
- scrape_with_curl_cffi: TLS fingerprint impersonation
- scrape_with_playwright: Browser automation
- scrape_with_drissionpage: Driverless browser (CDP)

Detection functions:
- detect_soft_block: WAF/soft block detection
- check_success_signal: Content validity check

Discovery functions:
- fetch_sitemap_links: Sitemap parsing with guardrails
- guess_common_urls: Standard business page patterns
- verify_urls_exist: HEAD request verification
"""

# Core models (always available)
from .models import (
    ErrorType,
    BlockType,
    Attempt,
    ValidationResult,
    HostState,
    ScrapeResult,
    ScrapeTier,
)

# Configuration
from .config import (
    RateLimitConfig,
    SitemapConfig,
    COMMON_PAGE_PATTERNS,
    WAF_SIGNATURES,
    MIN_CONTENT_LENGTH_BYTES,
    MIN_UNIQUE_LINE_RATIO,
)

# Profiles
from .profiles import (
    HttpHeaderProfile,
    BrowserContextProfile,
    StealthPatch,
    get_random_http_profile,
    get_random_context_profile,
    get_stealth_script,
)

# Cache
from .cache import (
    normalize_url,
    url_to_cache_key,
    LRUCache,
    ScrapeCache,
)

# Trace logging
from .trace import (
    TRACE_SCHEMA_VERSION,
    TraceHeader,
    TraceEntry,
    TraceLogger,
    read_trace_file,
)

# Rate limiting
from .rate_limiter import (
    RateLimiter,
    NoOpRateLimiter,
)

# Detection
from .detection import (
    detect_soft_block,
    detect_challenge_page,
    detect_consent_wall,
    check_success_signal,
    register_block_template,
    clear_block_templates,
)

# Validation
from .validation import (
    validate_content,
    validate_content_density,
    detect_duplicate_template,
    is_nav_only_page,
    estimate_content_quality,
)

# Content extraction
from .content import (
    detect_content_type,
    extract_clean_text,
    extract_main_content,
    get_page_title,
    get_meta_description,
)

# Network helpers
from .net import (
    get_default_headers,
    make_request,
    head_exists,
    extract_host,
    is_same_domain,
    normalize_url_for_request,
)

# HTTP clients
from .http_clients import (
    scrape_with_requests,
    scrape_with_httpx,
    scrape_with_curl_cffi,
    HTTP_TIERS,
)

# Vertical slice (minimal orchestrator for testing)
from .vertical_slice import (
    scrape_single_url,
)

# Browser automation
from .browsers import (
    BrowserSession,
    FakeBrowserSession,
    EXPAND_PATTERNS,
    CLICK_DENYLIST,
    CONSENT_DISMISS_PATTERNS,
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    scrape_with_drissionpage,
    scrape_with_drissionpage_stealth,
    scrape_with_vision,
    BROWSER_TIERS,
)

# Tier registry
from .tier_registry import (
    DEFAULT_TIERS,
    get_tier_by_name,
    get_available_tiers,
    get_tier_names,
    get_available_tier_names,
)

# Orchestrator
from .orchestrator import (
    ScrapeOrchestrator,
)

# Discovery
from .discovery import (
    DiscoveredLink,
    fetch_sitemap_links,
    guess_common_urls,
    verify_urls_exist,
    extract_links_from_html,
    score_links_heuristically,
    extract_links_from_homepage,
    discover_links,
)

# Structured content extraction
from .structured_content import (
    BoilerplateFilter,
    ContentBlock,
    StructuredContent,
    ExtractionMetrics,
    QualityScore,
    extract_structured_content,
    extract_with_boilerplate_learning,
    get_clean_text_for_summarization,
    should_escalate_tier,
    prune_dom,
    find_main_content,
    is_cta_block,
    compute_link_density,
    score_container,
)

__all__ = [
    # Models
    "ErrorType",
    "BlockType", 
    "Attempt",
    "ValidationResult",
    "HostState",
    "ScrapeResult",
    "ScrapeTier",
    # Config
    "RateLimitConfig",
    "SitemapConfig",
    "COMMON_PAGE_PATTERNS",
    "WAF_SIGNATURES",
    "MIN_CONTENT_LENGTH_BYTES",
    "MIN_UNIQUE_LINE_RATIO",
    # Profiles
    "HttpHeaderProfile",
    "BrowserContextProfile",
    "StealthPatch",
    "get_random_http_profile",
    "get_random_context_profile",
    "get_stealth_script",
    # Cache
    "normalize_url",
    "url_to_cache_key",
    "LRUCache",
    "ScrapeCache",
    # Trace
    "TRACE_SCHEMA_VERSION",
    "TraceHeader",
    "TraceEntry",
    "TraceLogger",
    "read_trace_file",
    # Rate limiting
    "RateLimiter",
    "NoOpRateLimiter",
    # Detection
    "detect_soft_block",
    "detect_challenge_page",
    "detect_consent_wall",
    "check_success_signal",
    "register_block_template",
    "clear_block_templates",
    # Validation
    "validate_content",
    "validate_content_density",
    "detect_duplicate_template",
    "is_nav_only_page",
    "estimate_content_quality",
    # Content extraction
    "detect_content_type",
    "extract_clean_text",
    "extract_main_content",
    "get_page_title",
    "get_meta_description",
    # Network helpers
    "get_default_headers",
    "make_request",
    "head_exists",
    "extract_host",
    "is_same_domain",
    "normalize_url_for_request",
    # HTTP clients
    "scrape_with_requests",
    "scrape_with_httpx",
    "scrape_with_curl_cffi",
    "HTTP_TIERS",
    # Vertical slice
    "scrape_single_url",
    # Browser automation
    "BrowserSession",
    "FakeBrowserSession",
    "EXPAND_PATTERNS",
    "CLICK_DENYLIST",
    "CONSENT_DISMISS_PATTERNS",
    "scrape_with_playwright",
    "scrape_with_playwright_aggressive",
    "scrape_with_drissionpage",
    "scrape_with_drissionpage_stealth",
    "scrape_with_vision",
    "BROWSER_TIERS",
    # Tier registry
    "DEFAULT_TIERS",
    "get_tier_by_name",
    "get_available_tiers",
    "get_tier_names",
    "get_available_tier_names",
    # Orchestrator
    "ScrapeOrchestrator",
    # Discovery
    "DiscoveredLink",
    "fetch_sitemap_links",
    "guess_common_urls",
    "verify_urls_exist",
    "extract_links_from_html",
    "score_links_heuristically",
    "extract_links_from_homepage",
    "discover_links",
    # Structured content
    "BoilerplateFilter",
    "ContentBlock",
    "StructuredContent",
    "ExtractionMetrics",
    "QualityScore",
    "extract_structured_content",
    "extract_with_boilerplate_learning",
    "get_clean_text_for_summarization",
    "should_escalate_tier",
    "prune_dom",
    "find_main_content",
    "is_cta_block",
    "compute_link_density",
    "score_container",
]
