"""
Custom exceptions and error handling utilities.

This package provides:
- Custom exception hierarchy for the application
- Typed error hierarchy with automatic recovery classification
- Decorators for safe function calls with logging
- Error context management
- Retry configuration with exponential backoff and jitter

The package is organized into submodules:
- base: Core error classes and retry configuration
- typed: Typed error hierarchy (PrimrError and subclasses)
- decorators: Error handling decorators and context managers
- retry: RetryManager and backoff utilities

All public symbols are re-exported from this __init__.py for backward
compatibility with code that imports from primr.utils.errors.
"""

# Re-export everything for backward compatibility
from primr.utils.errors.base import (
    RetryConfig,
    calculate_backoff_delay,
)
from primr.utils.errors.decorators import (
    ErrorContext,
    async_safe_callback,
    error_context,
    retry_on_failure,
    safe_call,
)
from primr.utils.errors.formatting import (
    format_error_for_user,
    get_error_guidance,
    is_recoverable_error,
)
from primr.utils.errors.retry import RetryManager
from primr.utils.errors.typed import (
    # Backward-compatible aliases
    AIError,
    AuthenticationError,
    ConfigurationError,
    NetworkError,
    OutputError,
    PermanentError,
    PrimrAIError,
    PrimrConfigurationError,
    # Base classes
    PrimrError,
    PrimrOutputError,
    PrimrScrapingError,
    PrimrSearchError,
    PrimrValidationError,
    QuotaError,
    RateLimitError,
    ResearchError,
    ScrapingError,
    SearchError,
    TransientError,
    TypedNetworkError,
    # Typed errors
    TypedRateLimitError,
    ValidationError,
)

__all__ = [
    # Aliases
    "AIError",
    "AuthenticationError",
    "ConfigurationError",
    "ErrorContext",
    "NetworkError",
    "OutputError",
    "PermanentError",
    "PrimrAIError",
    "PrimrConfigurationError",
    # Typed errors
    "PrimrError",
    "PrimrOutputError",
    "PrimrScrapingError",
    "PrimrSearchError",
    "PrimrValidationError",
    "QuotaError",
    "RateLimitError",
    "ResearchError",
    # Base
    "RetryConfig",
    # Retry
    "RetryManager",
    "ScrapingError",
    "SearchError",
    "TransientError",
    "TypedNetworkError",
    "TypedRateLimitError",
    "ValidationError",
    "async_safe_callback",
    "calculate_backoff_delay",
    "error_context",
    # Formatting
    "format_error_for_user",
    "get_error_guidance",
    "is_recoverable_error",
    "retry_on_failure",
    # Decorators
    "safe_call",
]
