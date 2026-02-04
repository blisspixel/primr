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
from primr.utils.errors.typed import (
    # Base classes
    PrimrError,
    TransientError,
    PermanentError,
    # Typed errors
    TypedRateLimitError,
    QuotaError,
    TypedNetworkError,
    PrimrValidationError,
    AuthenticationError,
    PrimrConfigurationError,
    PrimrAIError,
    PrimrScrapingError,
    PrimrSearchError,
    PrimrOutputError,
    # Backward-compatible aliases
    AIError,
    ScrapingError,
    SearchError,
    ConfigurationError,
    ValidationError,
    OutputError,
    NetworkError,
    ResearchError,
    RateLimitError,
)
from primr.utils.errors.decorators import (
    safe_call,
    retry_on_failure,
    ErrorContext,
    error_context,
    async_safe_callback,
)
from primr.utils.errors.retry import RetryManager
from primr.utils.errors.formatting import (
    format_error_for_user,
    get_error_guidance,
    is_recoverable_error,
)

__all__ = [
    # Base
    "RetryConfig",
    "calculate_backoff_delay",
    # Typed errors
    "PrimrError",
    "TransientError",
    "PermanentError",
    "TypedRateLimitError",
    "QuotaError",
    "TypedNetworkError",
    "PrimrValidationError",
    "AuthenticationError",
    "PrimrConfigurationError",
    "PrimrAIError",
    "PrimrScrapingError",
    "PrimrSearchError",
    "PrimrOutputError",
    # Aliases
    "AIError",
    "ScrapingError",
    "SearchError",
    "ConfigurationError",
    "ValidationError",
    "OutputError",
    "NetworkError",
    "ResearchError",
    "RateLimitError",
    # Decorators
    "safe_call",
    "retry_on_failure",
    "ErrorContext",
    "error_context",
    "async_safe_callback",
    # Retry
    "RetryManager",
    # Formatting
    "format_error_for_user",
    "get_error_guidance",
    "is_recoverable_error",
]
