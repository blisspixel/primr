"""
Core data models for the scraping module.

All models are defined here for consistency and to avoid circular imports.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ErrorType(Enum):
    """Types of errors that can occur during scraping."""

    TIMEOUT = "timeout"
    SOFT_BLOCK = "soft_block"
    HARD_BLOCK = "hard_block"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"
    CHALLENGE = "challenge"
    SUCCESS_SIGNAL_FAILED = "success_signal_failed"
    EMPTY_CONTENT = "empty_content"


class BlockType(Enum):
    """Types of blocks detected during scraping."""

    CHALLENGE = "challenge"  # Cloudflare "Just a moment", solvable
    HARD_BLOCK = "hard_block"  # 403/Access Denied, not solvable
    SOFT_BLOCK = "soft_block"  # 200 OK but fake content
    CONSENT_WALL = "consent_wall"  # Cookie consent blocking content
    TEMPLATE_BLOCK = "template_block"  # Known blocked page template


class PageAccessState(Enum):
    """Classification of whether a response contains real site content."""

    SUCCESS = "success"
    SOFT_BLOCK = "soft_block"
    THIN_CONTENT = "thin_content"
    UNKNOWN = "unknown"


@dataclass
class Attempt:
    """Single tier attempt record (typed, not dict)."""

    tier: str
    success: bool
    error: str | None = None
    error_type: ErrorType | None = None
    elapsed_ms: float | None = None
    http_status: int | None = None
    blocked_reason: str | None = None


@dataclass
class ValidationResult:
    """Result of content validation (separate from soft block detection)."""

    valid: bool
    reason: str | None = None
    content_density: float | None = None
    is_duplicate_template: bool = False
    content_class: str = "full_content"
    counts_as_full_page: bool = True


@dataclass
class PageAccessAssessment:
    """Evidence-backed access classification for a fetched page."""

    state: PageAccessState
    reason: str | None = None
    confidence: float = 0.0
    page_kind: str = "generic"
    title: str | None = None
    visible_text_length: int = 0
    matched_expected_markers: list[str] = field(default_factory=list)
    matched_challenge_markers: list[str] = field(default_factory=list)
    landmarks: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class HostState:
    """Per-host trust state for optimizing tier selection."""

    host: str
    cookies: dict | None = None  # Clearance cookies (cf_clearance, etc.)
    last_clearance_ts: datetime | None = None
    best_tier: str | None = None  # Tier that worked best for this host
    hard_blocked: bool = False
    browser_headed_preferred: bool = False
    browser_escalations: dict = field(default_factory=dict)  # tier_name -> retry count

    # Per-tier success/failure tracking for circuit breaker
    tier_attempts: dict = field(default_factory=dict)  # tier_name -> total attempts
    tier_failures: dict = field(default_factory=dict)  # tier_name -> failure count

    def has_fresh_clearance(self, max_age_minutes: int = 10) -> bool:
        """Check if clearance cookies are still fresh."""
        if not self.cookies or not self.last_clearance_ts:
            return False
        age = (datetime.now() - self.last_clearance_ts).total_seconds() / 60
        return age < max_age_minutes

    def record_tier_attempt(self, tier_name: str, success: bool) -> None:
        """Record an attempt for a specific tier."""
        self.tier_attempts[tier_name] = self.tier_attempts.get(tier_name, 0) + 1
        if not success:
            self.tier_failures[tier_name] = self.tier_failures.get(tier_name, 0) + 1

    def record_tier_failure(self, tier_name: str) -> None:
        """Record a failure for a specific tier (legacy method)."""
        self.record_tier_attempt(tier_name, success=False)

    def should_skip_tier(self, tier_name: str, threshold: int = 3) -> bool:
        """
        Check if tier should be skipped based on failure history.

        Circuit breaker logic:
        - Skip if tier has NEVER worked (100% failure rate) after threshold attempts
        - Don't skip if tier has ANY successes (even 20% success rate is worth trying)

        Rationale: README says 20-40% failure is expected for protected sites.
        We should only skip tiers that are COMPLETELY broken for this host.
        """
        attempts = self.tier_attempts.get(tier_name, 0)
        failures = self.tier_failures.get(tier_name, 0)

        # Not enough data yet - keep trying
        if attempts < threshold:
            return False

        # Skip only if tier has NEVER worked (100% failure rate)
        return failures >= attempts


@dataclass
class ScrapeResult:
    """Standardized result from every tier and orchestrator."""

    url: str
    success: bool
    raw_content: bytes | None = None  # Raw HTML/PDF bytes (None for vision)
    extracted_text: str | None = None  # Clean text (filled by content.py or vision)
    tier: str | None = None  # Which tier succeeded
    cached: bool = False

    # Metadata for debugging and detection
    http_status: int | None = None
    content_type: str | None = None  # "html", "pdf", "vision_text"
    final_url: str | None = None  # After redirects
    elapsed_ms: float | None = None

    # Session info for cookie handoff (browser tiers populate this)
    cookies: dict | None = field(default_factory=dict)  # Clearance cookies for handoff to curl_cffi

    # Error info
    error: str | None = None
    error_type: ErrorType | None = None
    blocked_reason: str | None = None

    # Content validation (filled after extraction, separate from soft block)
    validation: ValidationResult | None = None
    access_assessment: PageAccessAssessment | None = None

    # Tier attempt history (typed records)
    attempts: list = field(default_factory=list)  # list[Attempt]


@dataclass
class ScrapeTier:
    """Configuration for a single scraping tier."""

    name: str
    scrape_fn: Callable[[str, int], ScrapeResult]
    timeout: int
    requires: str | None = None  # Optional dependency check
