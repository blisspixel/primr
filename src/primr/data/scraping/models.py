"""
Core data models for the scraping module.

All models are defined here for consistency and to avoid circular imports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional


class ErrorType(Enum):
    """Types of errors that can occur during scraping."""
    TIMEOUT = "timeout"
    SOFT_BLOCK = "soft_block"
    HARD_BLOCK = "hard_block"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"
    CHALLENGE = "challenge"
    SUCCESS_SIGNAL_FAILED = "success_signal_failed"


class BlockType(Enum):
    """Types of blocks detected during scraping."""
    CHALLENGE = "challenge"          # Cloudflare "Just a moment", solvable
    HARD_BLOCK = "hard_block"        # 403/Access Denied, not solvable
    SOFT_BLOCK = "soft_block"        # 200 OK but fake content
    CONSENT_WALL = "consent_wall"    # Cookie consent blocking content
    TEMPLATE_BLOCK = "template_block"  # Known blocked page template


@dataclass
class Attempt:
    """Single tier attempt record (typed, not dict)."""
    tier: str
    success: bool
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    elapsed_ms: Optional[float] = None
    http_status: Optional[int] = None
    blocked_reason: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of content validation (separate from soft block detection)."""
    valid: bool
    reason: Optional[str] = None
    content_density: Optional[float] = None
    is_duplicate_template: bool = False


@dataclass
class HostState:
    """Per-host trust state for optimizing tier selection."""
    host: str
    cookies: Optional[dict] = None           # Clearance cookies (cf_clearance, etc.)
    last_clearance_ts: Optional[datetime] = None
    best_tier: Optional[str] = None          # Tier that worked best for this host
    hard_blocked: bool = False
    
    # Per-tier failure tracking for circuit breaker
    tier_failures: dict = field(default_factory=dict)  # tier_name -> failure count
    
    def has_fresh_clearance(self, max_age_minutes: int = 10) -> bool:
        """Check if clearance cookies are still fresh."""
        if not self.cookies or not self.last_clearance_ts:
            return False
        age = (datetime.now() - self.last_clearance_ts).total_seconds() / 60
        return age < max_age_minutes
    
    def record_tier_failure(self, tier_name: str) -> None:
        """Record a failure for a specific tier."""
        self.tier_failures[tier_name] = self.tier_failures.get(tier_name, 0) + 1
    
    def should_skip_tier(self, tier_name: str, threshold: int = 3) -> bool:
        """Check if tier should be skipped based on failure history."""
        return self.tier_failures.get(tier_name, 0) >= threshold


@dataclass
class ScrapeResult:
    """Standardized result from every tier and orchestrator."""
    url: str
    success: bool
    raw_content: Optional[bytes] = None      # Raw HTML/PDF bytes (None for vision)
    extracted_text: Optional[str] = None     # Clean text (filled by content.py or vision)
    tier: Optional[str] = None               # Which tier succeeded
    cached: bool = False
    
    # Metadata for debugging and detection
    http_status: Optional[int] = None
    content_type: Optional[str] = None       # "html", "pdf", "vision_text"
    final_url: Optional[str] = None          # After redirects
    elapsed_ms: Optional[float] = None
    
    # Session info for cookie handoff (browser tiers populate this)
    cookies: Optional[dict] = None           # Clearance cookies for handoff to curl_cffi
    
    # Error info
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    blocked_reason: Optional[str] = None
    
    # Content validation (filled after extraction, separate from soft block)
    validation: Optional[ValidationResult] = None
    
    # Tier attempt history (typed records)
    attempts: list = field(default_factory=list)  # list[Attempt]


@dataclass
class ScrapeTier:
    """Configuration for a single scraping tier."""
    name: str
    scrape_fn: Callable[[str, int], ScrapeResult]
    timeout: int
    requires: Optional[str] = None  # Optional dependency check
