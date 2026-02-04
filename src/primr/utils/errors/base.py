"""
Base error utilities and retry configuration.

This module provides foundational utilities used by the error hierarchy:
- RetryConfig: Configuration for retry behavior
- calculate_backoff_delay: Exponential backoff with jitter
- Shared constants for error guidance
"""

from __future__ import annotations

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


# =============================================================================
# CORRELATION ID HELPER
# =============================================================================

def get_correlation_id() -> str:
    """
    Get the current correlation ID from context or generate a new one.

    This is a local helper to avoid circular imports with observability module.
    It attempts to get the correlation ID from the thread-local context,
    falling back to generating a new UUID if no context exists.

    Returns:
        8-character correlation ID string
    """
    import threading
    import uuid

    # Try to get from thread-local context (set by observability module)
    _context_var = getattr(threading, '_primr_context', None)
    if _context_var is None:
        # Create thread-local storage if it doesn't exist
        threading._primr_context = threading.local()  # type: ignore[attr-defined]
        _context_var = threading._primr_context  # type: ignore[attr-defined]

    ctx = getattr(_context_var, 'context', None)
    if ctx is not None and hasattr(ctx, 'correlation_id'):
        return ctx.correlation_id

    # Try to import from observability module (preferred)
    try:
        from primr.utils.observability import get_correlation_id as obs_get_correlation_id
        return obs_get_correlation_id()
    except ImportError:
        pass

    # Fallback: generate new correlation ID
    return str(uuid.uuid4())[:8]
