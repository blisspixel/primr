"""
Application configuration with lazy validation.

This module provides:
- Dataclass-based configuration
- Lazy API key validation (only when needed)
- Environment-specific settings
- Type-safe configuration access
- Validated timeout, cache, and retry configurations
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from primr.config.models import PrimrModels

from dotenv import load_dotenv

from primr.utils.errors import ConfigurationError

# Load environment variables
load_dotenv()


# =============================================================================
# VALIDATED CONFIGURATION DATACLASSES
# =============================================================================


@dataclass
class TimeoutConfig:
    """
    Timeout configuration with separate values for different phases.

    Attributes:
        connect: Timeout for establishing connection (seconds)
        read: Timeout for reading response data (seconds)
        total: Overall operation timeout (seconds)

    Example:
        config = TimeoutConfig(connect=5.0, read=30.0, total=60.0)
        config.validate()  # Raises ValueError if invalid
    """
    connect: float = 10.0
    read: float = 30.0
    total: float = 60.0

    def validate(self) -> None:
        """
        Validate timeout values are positive and sensible.

        Raises:
            ValueError: If any timeout value is invalid
        """
        if self.connect <= 0:
            raise ValueError("connect timeout must be positive")
        if self.read <= 0:
            raise ValueError("read timeout must be positive")
        if self.total <= 0:
            raise ValueError("total timeout must be positive")
        if self.total < self.connect:
            raise ValueError("total timeout must be >= connect timeout")
        if self.total < self.read:
            raise ValueError("total timeout must be >= read timeout")

    def as_tuple(self) -> tuple[float, float]:
        """Return (connect, read) tuple for requests library."""
        return (self.connect, self.read)


@dataclass
class CacheConfig:
    """
    Cache configuration with size limits and TTL.

    Attributes:
        max_size: Maximum number of items in cache
        ttl_seconds: Time-to-live for cache entries (None = no expiry)
        name: Cache name for logging/metrics

    Example:
        config = CacheConfig(max_size=100, ttl_seconds=3600.0)
        config.validate()  # Raises ValueError if invalid
    """
    max_size: int = 100
    ttl_seconds: float | None = 3600.0
    name: str = "default"

    def validate(self) -> None:
        """
        Validate cache configuration.

        Raises:
            ValueError: If any configuration value is invalid
        """
        if self.max_size <= 0:
            raise ValueError("max_size must be positive")
        if self.ttl_seconds is not None and self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive or None")
        if not self.name or not self.name.strip():
            raise ValueError("name must be a non-empty string")


# =============================================================================
# API AND SERVICE CONFIGURATION
# =============================================================================

@dataclass
class APIConfig:
    """API keys and authentication configuration."""

    _gemini_key: str | None = field(default=None, repr=False)
    _search_key: str | None = field(default=None, repr=False)
    _search_engine_id: str | None = field(default=None, repr=False)

    def __post_init__(self):
        # Load from environment but don't validate yet
        self._gemini_key = os.getenv("GEMINI_API_KEY")
        self._search_key = os.getenv("SEARCH_API_KEY")
        self._search_engine_id = os.getenv("SEARCH_ENGINE_ID")

    @property
    def gemini_key(self) -> str:
        """Get Gemini API key, raising if not set."""
        if not self._gemini_key:
            raise ConfigurationError(
                "GEMINI_API_KEY not set. Add it to your .env file or environment."
            )
        return self._gemini_key

    @property
    def search_key(self) -> str:
        """Get Google Search API key, raising if not set."""
        if not self._search_key:
            raise ConfigurationError(
                "SEARCH_API_KEY not set. Add it to your .env file or environment."
            )
        return self._search_key

    @property
    def search_engine_id(self) -> str:
        """Get Google Search Engine ID, raising if not set."""
        if not self._search_engine_id:
            raise ConfigurationError(
                "SEARCH_ENGINE_ID not set. Add it to your .env file or environment."
            )
        return self._search_engine_id

    def validate(self) -> None:
        """Validate all API keys are present."""
        # Access properties to trigger validation
        _ = self.gemini_key
        _ = self.search_key
        _ = self.search_engine_id

    def is_configured(self) -> bool:
        """Check if all API keys are configured (without raising)."""
        return bool(
            self._gemini_key and
            self._search_key and
            self._search_engine_id
        )


@dataclass
class ScrapingConfig:
    """Web scraping configuration."""

    max_retries: int = 2
    timeout: int = 15
    max_depth: int = 2
    cache_ttl_hours: int = 24
    min_content_length: int = 100
    min_html_length: int = 500

    excluded_sites: list[str] = field(default_factory=lambda: [
        "login", "captcha", "privacy-policy", "terms-of-service"
    ])

    # Soft block detection keywords
    soft_block_indicators: list[str] = field(default_factory=lambda: [
        "captcha", "verify you are human", "access denied", "forbidden",
        "please enable javascript", "browser check", "checking your browser",
        "ddos protection", "cloudflare", "just a moment", "ray id",
        "unusual traffic", "automated access", "bot detected",
        "enable cookies", "login required", "sign in to continue",
        "403 forbidden", "401 unauthorized", "blocked"
    ])


@dataclass
class AIConfig:
    """
    AI model configuration.
    
    Model assignments (update PrimrModels to change globally):
        - flash_model: Fast tasks (summarization, filtering) - cheap
        - pro_model: Complex tasks (report generation, reasoning) - expensive
        - fast_model/reasoning_model: Aliases for flash/pro
    """

    # Primary model assignments - pull from PrimrModels
    flash_model: str = field(
        default_factory=lambda: os.getenv("AI_FAST_MODEL", PrimrModels.FLASH_MODEL)
    )
    pro_model: str = field(
        default_factory=lambda: os.getenv("AI_REASONING_MODEL", PrimrModels.PRO_MODEL)
    )
    
    # Task-specific aliases (for backward compatibility)
    fast_model: str = field(
        default_factory=lambda: os.getenv("AI_FAST_MODEL", PrimrModels.FAST_MODEL)
    )
    reasoning_model: str = field(
        default_factory=lambda: os.getenv("AI_REASONING_MODEL", PrimrModels.REASONING_MODEL)
    )
    
    # Legacy aliases (backward compatible)
    research_model: str = field(
        default_factory=lambda: os.getenv("AI_RESEARCH_MODEL", PrimrModels.FAST_MODEL)
    )
    report_model: str = field(
        default_factory=lambda: os.getenv("AI_REPORT_MODEL", PrimrModels.PRO_MODEL)
    )

    max_retries: int = 3
    grade_threshold: int = 80
    default_temperature: float = 1.0
    default_thinking_level: str = "high"

    # No fallback models - fail immediately if model unavailable
    model_fallbacks: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SearchConfig:
    """Search API configuration."""

    num_results: int = 3
    parallel_limit: int = 2
    initial_retry_delay: int = 5

    excluded_domains: list[str] = field(default_factory=lambda: [
        "reddit.com", "quora.com", "facebook.com", "twitter.com",
        "pinterest.com", "tiktok.com", "tumblr.com", "instagram.com"
    ])


@dataclass
class PathConfig:
    """File path configuration."""

    project_root: Path = field(default_factory=Path.cwd)

    # These are computed from project_root
    output_dir: Path = field(init=False)
    working_dir: Path = field(init=False)
    logs_dir: Path = field(init=False)
    cache_dir: Path = field(init=False)
    prompts_file: Path = field(init=False)

    def __post_init__(self):
        self.output_dir = self.project_root / "output"
        self.working_dir = self.project_root / "working"
        self.logs_dir = self.project_root / "logs"
        self.cache_dir = self.logs_dir / "scrape_cache"
        # prompts.json is in the package config directory
        self.prompts_file = Path(__file__).parent / "prompts.json"

    def ensure_directories(self) -> None:
        """Create all required directories."""
        for directory in [self.output_dir, self.working_dir, self.logs_dir, self.cache_dir]:
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class OutputConfig:
    """Report output configuration."""

    supported_formats: list[str] = field(default_factory=lambda: [
        ".txt", ".docx", ".pdf", ".md"
    ])
    convert_to_pdf: bool = True
    include_sources: bool = True
    include_timestamps: bool = True


@dataclass
class PricingConfig:
    """
    API pricing configuration for cost estimation.

    Prices are per 1 million tokens.
    Update these when pricing changes.
    """

    # Gemini API pricing (per 1M tokens)
    gemini_input_per_million: float = 2.00
    gemini_output_per_million: float = 12.00

    # Deep Research estimated costs (based on typical usage)
    deep_research_base_cost: float = 0.50  # Base cost per query

    # Google Search API (free until Jan 5, 2026)
    search_cost_per_query: float = 0.00

    # Last updated date for tracking staleness
    last_updated: str = "2024-12-16"

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculate cost for given token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        input_cost = (input_tokens / 1_000_000) * self.gemini_input_per_million
        output_cost = (output_tokens / 1_000_000) * self.gemini_output_per_million
        return input_cost + output_cost


# =============================================================================
# MAIN SETTINGS CLASS
# =============================================================================

@dataclass
class Settings:
    """
    Main application settings container.

    Usage:
        settings = get_settings()
        api_key = settings.api.gemini_key  # Validates on access
        timeout = settings.scraping.timeout
        cost = settings.pricing.calculate_cost(input_tokens, output_tokens)

    Configuration Validation:
        settings.validate_all()  # Validates all config values (except API keys)
        settings.validate()      # Validates API keys only
    """

    api: APIConfig = field(default_factory=APIConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)

    # Validated configuration objects
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    # Runtime flags
    verbose: bool = field(
        default_factory=lambda: os.getenv("VERBOSE", "false").lower() == "true"
    )
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    def __post_init__(self):
        # Ensure directories exist
        self.paths.ensure_directories()

    def validate(self) -> None:
        """Validate API keys are present (lazy validation)."""
        self.api.validate()

    def validate_all(self, include_api_keys: bool = False) -> None:
        """
        Validate all configuration values at startup.

        This performs fail-fast validation of all config values,
        raising descriptive errors for any invalid configuration.

        Args:
            include_api_keys: If True, also validate API keys are present

        Raises:
            ValueError: If any configuration value is invalid
            ConfigurationError: If API keys are missing (when include_api_keys=True)
        """
        errors: list[str] = []

        # Validate timeout config
        try:
            self.timeouts.validate()
        except ValueError as e:
            errors.append(f"TimeoutConfig: {e}")

        # Validate cache config
        try:
            self.cache.validate()
        except ValueError as e:
            errors.append(f"CacheConfig: {e}")

        # Validate scraping config values
        if self.scraping.max_retries < 0:
            errors.append("ScrapingConfig: max_retries must be non-negative")
        if self.scraping.timeout <= 0:
            errors.append("ScrapingConfig: timeout must be positive")
        if self.scraping.max_depth < 0:
            errors.append("ScrapingConfig: max_depth must be non-negative")
        if self.scraping.cache_ttl_hours <= 0:
            errors.append("ScrapingConfig: cache_ttl_hours must be positive")

        # Validate AI config values
        if self.ai.max_retries < 0:
            errors.append("AIConfig: max_retries must be non-negative")
        if not 0 <= self.ai.grade_threshold <= 100:
            errors.append("AIConfig: grade_threshold must be between 0 and 100")
        if not 0.0 <= self.ai.default_temperature <= 2.0:
            errors.append("AIConfig: default_temperature must be between 0.0 and 2.0")

        # Validate search config values
        if self.search.num_results <= 0:
            errors.append("SearchConfig: num_results must be positive")
        if self.search.parallel_limit <= 0:
            errors.append("SearchConfig: parallel_limit must be positive")

        # Optionally validate API keys
        if include_api_keys:
            try:
                self.api.validate()
            except ConfigurationError as e:
                errors.append(f"APIConfig: {e}")

        # Raise all errors at once
        if errors:
            raise ValueError(
                "Configuration validation failed:\n  - " + "\n  - ".join(errors)
            )

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "Settings":
        """
        Create settings from environment variables.

        Args:
            project_root: Override project root path
        """
        paths = PathConfig(project_root=project_root) if project_root else PathConfig()
        return cls(paths=paths)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get application settings (lazy singleton).

    Returns:
        Settings instance

    Example:
        settings = get_settings()
        model = settings.ai.research_model
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings singleton (useful for testing)."""
    global _settings
    _settings = None


def configure(
    project_root: Path | None = None,
    verbose: bool = False,
    debug: bool = False,
    **overrides: Any
) -> Settings:
    """
    Configure application settings.

    Args:
        project_root: Override project root path
        verbose: Enable verbose output
        debug: Enable debug mode
        **overrides: Additional setting overrides

    Returns:
        Configured Settings instance
    """
    global _settings

    paths = PathConfig(project_root=project_root) if project_root else PathConfig()
    _settings = Settings(
        paths=paths,
        verbose=verbose,
        debug=debug,
    )

    return _settings
