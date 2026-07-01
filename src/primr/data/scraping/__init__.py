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
# Browser automation
from .browsers import (
    BROWSER_TIERS,
    CLICK_DENYLIST,
    CONSENT_DISMISS_PATTERNS,
    EXPAND_PATTERNS,
    BrowserSession,
    FakeBrowserSession,
    scrape_with_drissionpage,
    scrape_with_drissionpage_stealth,
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    scrape_with_vision,
)

# Cache
from .cache import (
    LRUCache,
    ScrapeCache,
    normalize_url,
    url_to_cache_key,
)

# Configuration
from .config import (
    COMMON_PAGE_PATTERNS,
    MIN_CONTENT_LENGTH_BYTES,
    MIN_UNIQUE_LINE_RATIO,
    WAF_SIGNATURES,
    RateLimitConfig,
    SitemapConfig,
)

# Content extraction
from .content import (
    detect_content_type,
    extract_clean_text,
    extract_main_content,
    extract_text_from_pdf_via_llm,
    get_meta_description,
    get_page_title,
)

# Detection
from .detection import (
    check_success_signal,
    clear_block_templates,
    detect_challenge_page,
    detect_consent_wall,
    detect_soft_block,
    register_block_template,
)

# Discovery
from .discovery import (
    DiscoveredLink,
    discover_links,
    extract_links_from_homepage,
    extract_links_from_html,
    fetch_sitemap_links,
    guess_common_urls,
    score_links_heuristically,
    verify_urls_exist,
)

# HTTP clients
from .http_clients import (
    HTTP_TIERS,
    scrape_with_curl_cffi,
    scrape_with_httpx,
    scrape_with_requests,
)
from .models import (
    Attempt,
    BlockType,
    ErrorType,
    HostState,
    PageAccessAssessment,
    PageAccessState,
    RenderSnapshotComparison,
    ScrapeResult,
    ScrapeTier,
    ValidationResult,
)

# Network helpers
from .net import (
    extract_host,
    get_default_headers,
    head_exists,
    is_in_scope,
    is_same_domain,
    make_request,
    normalize_url_for_request,
)

# Orchestrator
from .orchestrator import (
    ScrapeOrchestrator,
)
from .org_profile import (
    OrganizationProfile,
    classify_organization_type,
    get_focus_areas_for_org_type,
)
from .page_access import (
    classify_page_access,
    infer_page_kind,
)
from .page_access_eval import (
    PageAccessEvalCase,
    PageAccessEvalMetrics,
    PageAccessEvalReport,
    PageAccessEvalRow,
    PageAccessPrediction,
    evaluate_page_access_cases,
    page_access_eval_payload,
    prediction_from_access_assessment,
    score_page_access_predictions,
    write_page_access_eval_json,
    write_page_access_eval_markdown,
)
from .page_snapshots import (
    compare_render_snapshots,
    html_to_snapshot_text,
)

# Profiles
from .profiles import (
    BrowserContextProfile,
    HttpHeaderProfile,
    StealthPatch,
    get_random_context_profile,
    get_random_http_profile,
    get_stealth_script,
)

# Rate limiting
from .rate_limiter import (
    NoOpRateLimiter,
    RateLimiter,
)

# Structured content extraction
from .structured_content import (
    BoilerplateFilter,
    ContentBlock,
    ExtractionMetrics,
    QualityScore,
    StructuredContent,
    compute_link_density,
    extract_structured_content,
    extract_with_boilerplate_learning,
    find_main_content,
    get_clean_text_for_summarization,
    is_cta_block,
    prune_dom,
    score_container,
    should_escalate_tier,
)

# Tier registry
from .tier_registry import (
    DEFAULT_TIERS,
    get_available_tier_names,
    get_available_tiers,
    get_tier_by_name,
    get_tier_names,
)

# Trace logging
from .trace import (
    TRACE_SCHEMA_VERSION,
    TraceEntry,
    TraceHeader,
    TraceLogger,
    read_trace_file,
)

# Validation
from .validation import (
    detect_duplicate_template,
    estimate_content_quality,
    is_nav_only_page,
    validate_content,
    validate_content_density,
)

# Vertical slice (minimal orchestrator for testing)
from .vertical_slice import (
    scrape_single_url,
)

__all__ = [
    "BROWSER_TIERS",
    "CLICK_DENYLIST",
    "COMMON_PAGE_PATTERNS",
    "CONSENT_DISMISS_PATTERNS",
    # Tier registry
    "DEFAULT_TIERS",
    "EXPAND_PATTERNS",
    "HTTP_TIERS",
    "MIN_CONTENT_LENGTH_BYTES",
    "MIN_UNIQUE_LINE_RATIO",
    # Trace
    "TRACE_SCHEMA_VERSION",
    "WAF_SIGNATURES",
    "Attempt",
    "BlockType",
    # Structured content
    "BoilerplateFilter",
    "BrowserContextProfile",
    # Browser automation
    "BrowserSession",
    "ContentBlock",
    # Discovery
    "DiscoveredLink",
    # Models
    "ErrorType",
    "ExtractionMetrics",
    "FakeBrowserSession",
    "HostState",
    # Profiles
    "HttpHeaderProfile",
    "LRUCache",
    "NoOpRateLimiter",
    "OrganizationProfile",
    "PageAccessAssessment",
    "PageAccessEvalCase",
    "PageAccessEvalMetrics",
    "PageAccessEvalReport",
    "PageAccessEvalRow",
    "PageAccessPrediction",
    "PageAccessState",
    "QualityScore",
    # Config
    "RateLimitConfig",
    # Rate limiting
    "RateLimiter",
    "RenderSnapshotComparison",
    "ScrapeCache",
    # Orchestrator
    "ScrapeOrchestrator",
    "ScrapeResult",
    "ScrapeTier",
    "SitemapConfig",
    "StealthPatch",
    "StructuredContent",
    "TraceEntry",
    "TraceHeader",
    "TraceLogger",
    "ValidationResult",
    "check_success_signal",
    "classify_organization_type",
    "classify_page_access",
    "clear_block_templates",
    "compare_render_snapshots",
    "compute_link_density",
    "detect_challenge_page",
    "detect_consent_wall",
    # Content extraction
    "detect_content_type",
    "detect_duplicate_template",
    # Detection
    "detect_soft_block",
    "discover_links",
    "estimate_content_quality",
    "evaluate_page_access_cases",
    "extract_clean_text",
    "extract_host",
    "extract_links_from_homepage",
    "extract_links_from_html",
    "extract_main_content",
    "extract_structured_content",
    "extract_text_from_pdf_via_llm",
    "extract_with_boilerplate_learning",
    "fetch_sitemap_links",
    "find_main_content",
    "get_available_tier_names",
    "get_available_tiers",
    "get_clean_text_for_summarization",
    # Network helpers
    "get_default_headers",
    "get_focus_areas_for_org_type",
    "get_meta_description",
    "get_page_title",
    "get_random_context_profile",
    "get_random_http_profile",
    "get_stealth_script",
    "get_tier_by_name",
    "get_tier_names",
    "guess_common_urls",
    "head_exists",
    "html_to_snapshot_text",
    "infer_page_kind",
    "is_cta_block",
    "is_in_scope",
    "is_nav_only_page",
    "is_same_domain",
    "make_request",
    # Cache
    "normalize_url",
    "normalize_url_for_request",
    "page_access_eval_payload",
    "prediction_from_access_assessment",
    "prune_dom",
    "read_trace_file",
    "register_block_template",
    "score_container",
    "score_links_heuristically",
    "score_page_access_predictions",
    # Vertical slice
    "scrape_single_url",
    "scrape_with_curl_cffi",
    "scrape_with_drissionpage",
    "scrape_with_drissionpage_stealth",
    "scrape_with_httpx",
    "scrape_with_playwright",
    "scrape_with_playwright_aggressive",
    # HTTP clients
    "scrape_with_requests",
    "scrape_with_vision",
    "should_escalate_tier",
    "url_to_cache_key",
    # Validation
    "validate_content",
    "validate_content_density",
    "verify_urls_exist",
    "write_page_access_eval_json",
    "write_page_access_eval_markdown",
]
