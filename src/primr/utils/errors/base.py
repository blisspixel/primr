"""
Base error utilities and retry configuration.

This module provides foundational utilities used by the error hierarchy:
- RetryConfig: Configuration for retry behavior
- calculate_backoff_delay: Exponential backoff with jitter
- Shared constants for error guidance
"""

from __future__ import annotations

import contextvars
import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =============================================================================
# SHARED CONSTANTS
# =============================================================================

# Centralized guidance messages for error categories
CATEGORY_GUIDANCE: dict[str, str] = {
    "configuration": "Check your .env file and environment variables",
    "scraping": "The website may be blocking automated access. Try again later.",
    "ai": "Check API quota and try again",
    "rate_limit": "Rate limit exceeded. Wait a moment and try again.",
    "search": "Search API may be unavailable. Check your API key and quota.",
    "output": "Check disk space and file permissions",
    "validation": "Check your input and try again",
    "network": "Check your internet connection",
    "authentication": "Check your API keys and credentials",
    "quota": "API quota exhausted. Wait for quota reset.",
}

# Guidance for common Python exception types
EXCEPTION_TYPE_GUIDANCE: dict[str, str] = {
    "ConnectionError": "Check your internet connection",
    "TimeoutError": "The operation timed out. Try again or increase timeout.",
    "FileNotFoundError": "The specified file does not exist",
    "PermissionError": "Permission denied. Check file/folder permissions.",
    "JSONDecodeError": "Invalid JSON data received",
}


# =============================================================================
# RETRY CONFIGURATION
# =============================================================================

@dataclass
class RetryConfig:
    """
    Configuration for retry behavior with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential growth (typically 2.0)
        jitter_factor: Random jitter as fraction of delay (0.0-1.0)

    Example:
        config = RetryConfig(max_retries=3, base_delay=1.0, jitter_factor=0.1)
        delay = calculate_backoff_delay(attempt=2, config=config)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1

    def validate(self) -> None:
        """
        Validate configuration values.

        Raises:
            ValueError: If any configuration value is invalid
        """
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be positive")
        if self.max_delay <= 0:
            raise ValueError("max_delay must be positive")
        if self.exponential_base <= 1:
            raise ValueError("exponential_base must be greater than 1")
        if not 0 <= self.jitter_factor <= 1:
            raise ValueError("jitter_factor must be between 0 and 1")


def calculate_backoff_delay(attempt: int, config: RetryConfig) -> float:
    """
    Calculate delay with exponential backoff and jitter.

    The delay grows exponentially with each attempt, capped at max_delay,
    with random jitter added to prevent thundering herd.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds with jitter applied (always >= 0)

    Example:
        >>> config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter_factor=0.1)
        >>> delay = calculate_backoff_delay(0, config)  # ~1.0 +/- 10%
        >>> delay = calculate_backoff_delay(1, config)  # ~2.0 +/- 10%
        >>> delay = calculate_backoff_delay(2, config)  # ~4.0 +/- 10%
    """
    # Calculate base exponential delay
    base_delay = config.base_delay * (config.exponential_base ** attempt)

    # Cap at max_delay
    capped_delay = min(base_delay, config.max_delay)

    # Add jitter: random value in range [-jitter, +jitter]
    jitter_range = capped_delay * config.jitter_factor
    jitter = random.uniform(-jitter_range, jitter_range)

    # Ensure non-negative
    return max(0.0, capped_delay + jitter)


def is_rate_limit_error(error: Exception) -> bool:
    """Check if an exception indicates a rate-limit (429) or resource-exhaustion error."""
    error_str = str(error).lower()
    return "429" in str(error) or "resource_exhausted" in error_str


def calculate_retry_delay(attempt: int, *, is_rate_limited: bool) -> float:
    """Calculate retry delay, using longer backoff for rate-limit errors."""
    if is_rate_limited:
        return min(2 ** attempt * 5, 60)  # 5s, 10s, 20s, max 60s
    return float(2 ** attempt)  # 1s, 2s, 4s


# =============================================================================
# CORRELATION ID HELPER
# =============================================================================

def get_correlation_id() -> str:
    """
    Get the current correlation ID from context or generate a new one.

    This is a local helper to avoid circular imports with observability module.
    Uses contextvars for thread-safe and async-safe context propagation.

    Returns:
        8-character correlation ID string
    """
    import uuid

    # Try to import from observability module (preferred — has full context)
    try:
        from primr.utils.observability import get_correlation_id as obs_get_correlation_id
        return obs_get_correlation_id()
    except ImportError:
        pass

    # Fallback: use module-level ContextVar for thread/async-safe storage
    return _fallback_correlation_id.get(str(uuid.uuid4())[:8])


# Module-level ContextVar — works correctly with both threading and asyncio
_fallback_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "primr_correlation_id"
)
