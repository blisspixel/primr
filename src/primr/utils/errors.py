"""
Custom exceptions and error handling utilities.

This module provides:
- Custom exception hierarchy for the application
- Typed error hierarchy with automatic recovery classification
- Decorators for safe function calls with logging
- Error context management
- Retry configuration with exponential backoff and jitter
"""

from __future__ import annotations

import functools
import logging
import random
from abc import ABC
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


# =============================================================================
# SHARED CONSTANTS
# =============================================================================

# Centralized guidance messages for error categories (used by both PrimrError and utilities)
_CATEGORY_GUIDANCE: dict[str, str] = {
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
_EXCEPTION_TYPE_GUIDANCE: dict[str, str] = {
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

def _get_correlation_id() -> str:
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
        threading._primr_context = threading.local()
        _context_var = threading._primr_context

    ctx = getattr(_context_var, 'context', None)
    if ctx is not None and hasattr(ctx, 'correlation_id'):
        return ctx.correlation_id

    # Try to import from observability module (preferred)
    try:
        from primr.utils.observability import get_correlation_id
        return get_correlation_id()
    except ImportError:
        pass

    # Fallback: generate new correlation ID
    return str(uuid.uuid4())[:8]


# =============================================================================
# TYPED ERROR HIERARCHY (PhD-Level Excellence)
# =============================================================================

@dataclass
class PrimrError(Exception, ABC):
    """
    Base exception for all Primr errors with automatic context capture.

    This is the foundation of the typed error hierarchy that enables
    automatic retry policies and informed recovery decisions based on
    error classification.

    Attributes:
        message: Human-readable error description
        category: Error category for classification (e.g., "transient", "permanent")
        recoverable: Whether this error can be retried
        retry_after: Suggested delay before retry in seconds (None if not applicable)
        correlation_id: Unique ID for tracing related operations (auto-captured)
        timestamp: When the error occurred
        cause: The underlying exception that caused this error
        context: Additional context data for debugging
        guidance: User-friendly guidance for resolving the error

    Example:
        try:
            result = api_call()
        except PrimrError as e:
            if e.recoverable:
                await asyncio.sleep(e.retry_after or 1.0)
                result = api_call()  # Retry
            else:
                raise  # Don't retry permanent errors
    """

    message: str
    category: str = "general"
    recoverable: bool = False
    retry_after: float | None = None
    correlation_id: str = field(default_factory=_get_correlation_id)
    timestamp: datetime = field(default_factory=datetime.now)
    cause: Exception | None = None
    context: dict[str, Any] = field(default_factory=dict)
    guidance: str = ""

    def __post_init__(self) -> None:
        """Initialize the exception with the message."""
        super().__init__(self.message)
        # Set default guidance based on category if not provided
        if not self.guidance:
            self.guidance = self._default_guidance()

    def _default_guidance(self) -> str:
        """Get default guidance based on error category."""
        return _CATEGORY_GUIDANCE.get(self.category, "")

    def __str__(self) -> str:
        """Return the error message."""
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message

    def __repr__(self) -> str:
        """Return a detailed representation of the error."""
        return (
            f"{type(self).__name__}("
            f"message={self.message!r}, "
            f"category={self.category!r}, "
            f"recoverable={self.recoverable}, "
            f"correlation_id={self.correlation_id!r})"
        )

    def user_message(self) -> str:
        """
        Get user-friendly error message without stack traces.

        Returns:
            Clean message suitable for display to users
        """
        msg = self.message
        if self.guidance:
            msg += f"\n    {self.guidance}"
        return msg

    def debug_message(self) -> str:
        """
        Get detailed error message for debugging.

        Returns:
            Detailed message including cause chain and context
        """
        parts = [f"[{self.category}] {self.message}"]
        if self.cause:
            parts.append(f"  Caused by: {type(self.cause).__name__}: {self.cause}")
        if self.guidance:
            parts.append(f"  Guidance: {self.guidance}")
        # Add any extra attributes from subclasses
        for attr in self._debug_attributes():
            value = getattr(self, attr, None)
            if value:
                parts.append(f"  {attr.replace('_', ' ').title()}: {value}")
        return "\n".join(parts)

    def _debug_attributes(self) -> list[str]:
        """Return list of additional attributes to include in debug message."""
        return []

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary containing all error attributes suitable for JSON serialization.
            The dictionary includes: type, message, category, recoverable, retry_after,
            correlation_id, timestamp, and context.

        Example:
            error = RateLimitError("Rate limit exceeded", retry_after_seconds=60)
            data = error.to_dict()
            json_str = json.dumps(data)  # Safe to serialize
        """
        result: dict[str, Any] = {
            "type": type(self).__name__,
            "message": self.message,
            "category": self.category,
            "recoverable": self.recoverable,
            "retry_after": self.retry_after,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }
        if self.cause is not None:
            result["cause"] = {
                "type": type(self.cause).__name__,
                "message": str(self.cause),
            }
        return result


@dataclass
class TransientError(PrimrError):
    """
    Base class for errors that may succeed on retry.

    Transient errors represent temporary failures that are likely to
    resolve themselves, such as network timeouts, rate limits, or
    temporary service unavailability.

    Attributes:
        recoverable: Always True for transient errors
        category: Always "transient" for base transient errors

    Example:
        try:
            result = fetch_data()
        except TransientError as e:
            # Safe to retry
            await asyncio.sleep(e.retry_after or 1.0)
            result = fetch_data()
    """

    recoverable: bool = True
    category: str = "transient"


@dataclass
class PermanentError(PrimrError):
    """
    Base class for errors that will never succeed on retry.

    Permanent errors represent failures that cannot be resolved by
    retrying, such as invalid input, authentication failures, or
    missing resources.

    Attributes:
        recoverable: Always False for permanent errors
        category: Always "permanent" for base permanent errors

    Example:
        try:
            result = validate_input(data)
        except PermanentError as e:
            # Do NOT retry - fix the input instead
            raise UserInputError(str(e))
    """

    recoverable: bool = False
    category: str = "permanent"


@dataclass
class TypedRateLimitError(TransientError):
    """
    API rate limit exceeded (Typed Error Hierarchy).

    Raised when an API call fails due to rate limiting. The retry_after_seconds
    attribute indicates how long to wait before retrying.

    Attributes:
        message: Error message (default: "API rate limit exceeded")
        retry_after_seconds: Seconds to wait before retrying (default: 60.0)
        category: Always "rate_limit"

    Example:
        try:
            response = api.call()
        except TypedRateLimitError as e:
            await asyncio.sleep(e.retry_after_seconds)
            response = api.call()
    """

    message: str = "API rate limit exceeded"
    category: str = "rate_limit"
    retry_after_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Set retry_after from retry_after_seconds and update guidance."""
        super().__post_init__()
        self.retry_after = self.retry_after_seconds
        # Update guidance to include retry time
        if self.retry_after_seconds:
            self.guidance = (
                f"Rate limit exceeded. Try again in {self.retry_after_seconds:.0f} seconds."
            )



@dataclass
class QuotaError(TransientError):
    """
    API quota exhausted.

    Raised when an API quota is exhausted. The quota_reset_time attribute
    indicates when the quota will be reset.

    Attributes:
        quota_reset_time: When the quota will be reset (optional)
        category: Always "quota"

    Example:
        try:
            response = api.call()
        except QuotaError as e:
            if e.quota_reset_time:
                wait_time = (e.quota_reset_time - datetime.now()).total_seconds()
                await asyncio.sleep(max(0, wait_time))
            response = api.call()
    """

    category: str = "quota"
    quota_reset_time: datetime | None = None

    def __post_init__(self) -> None:
        """Calculate retry_after from quota_reset_time."""
        super().__post_init__()
        if self.quota_reset_time is not None:
            delta = (self.quota_reset_time - datetime.now()).total_seconds()
            self.retry_after = max(0.0, delta)


@dataclass
class TypedNetworkError(TransientError):
    """
    Network connectivity issues (Typed Error Hierarchy).

    Raised when a network operation fails due to connectivity issues,
    such as connection refused, DNS resolution failure, or timeout.

    Attributes:
        host: The host that was being connected to
        port: The port that was being connected to (optional)
        category: Always "network"

    Example:
        try:
            response = fetch_url(url)
        except TypedNetworkError as e:
            logger.warning(f"Network error connecting to {e.host}:{e.port}")
            await asyncio.sleep(1.0)
            response = fetch_url(url)
    """

    category: str = "network"
    host: str = ""
    port: int | None = None


@dataclass
class PrimrValidationError(PermanentError):
    """
    Input validation failed.

    Raised when input validation fails. The field_errors attribute
    contains a mapping of field names to lists of error messages.

    Note: Named PrimrValidationError to avoid conflict with existing
    ValidationError class. Use this for new code requiring the typed
    error hierarchy.

    Attributes:
        field_errors: Mapping of field names to error messages
        category: Always "validation"

    Example:
        errors = validate_form(data)
        if errors:
            raise PrimrValidationError(
                "Validation failed",
                field_errors=errors
            )
    """

    category: str = "validation"
    field_errors: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class AuthenticationError(PermanentError):
    """
    Authentication failed.

    Raised when authentication fails, such as invalid credentials,
    expired tokens, or missing API keys.

    Attributes:
        auth_method: The authentication method that failed (e.g., "api_key", "oauth")
        category: Always "authentication"

    Example:
        if not api_key:
            raise AuthenticationError(
                "API key not provided",
                auth_method="api_key"
            )
    """

    category: str = "authentication"
    auth_method: str = ""


@dataclass
class PrimrConfigurationError(PermanentError):
    """
    Configuration is invalid or missing.

    Raised when configuration validation fails or required configuration
    is missing.

    Note: Named PrimrConfigurationError to avoid conflict with existing
    ConfigurationError class. Use this for new code requiring the typed
    error hierarchy.

    Attributes:
        config_path: Path to the configuration file (if applicable)
        missing_keys: List of missing configuration keys
        category: Always "configuration"

    Example:
        missing = check_required_config(config)
        if missing:
            raise PrimrConfigurationError(
                "Missing required configuration",
                config_path="config.yaml",
                missing_keys=missing
            )
    """

    category: str = "configuration"
    config_path: str = ""
    missing_keys: list[str] = field(default_factory=list)


@dataclass
class PrimrAIError(TransientError):
    """
    AI/LLM operation failed.

    Raised when an AI API call fails. This is typically a transient error
    that can be retried.

    Attributes:
        model: The model that was being used
        operation: The operation that failed (e.g., "generate", "embed")
        category: Always "ai"

    Example:
        try:
            response = client.generate(prompt)
        except PrimrAIError as e:
            logger.warning(f"AI call failed with {e.model}: {e.message}")
            if e.recoverable:
                response = client.generate(prompt)  # Retry
    """

    category: str = "ai"
    model: str = ""
    operation: str = ""

    def _debug_attributes(self) -> list[str]:
        return ["model", "operation"]


@dataclass
class PrimrScrapingError(TransientError):
    """
    Web scraping operation failed.

    Raised when a scraping operation fails. Includes context about
    the URL, HTTP status, and scraping tier that was attempted.

    Attributes:
        url: The URL that was being scraped
        status_code: HTTP status code (if available)
        tier: The scraping tier that failed
        category: Always "scraping"

    Example:
        try:
            content = scrape_page(url)
        except PrimrScrapingError as e:
            logger.warning(f"Scrape failed for {e.url} (tier: {e.tier})")
            if e.recoverable:
                content = scrape_page(url, escalate=True)
    """

    category: str = "scraping"
    url: str = ""
    status_code: int | None = None
    tier: str = ""

    def _debug_attributes(self) -> list[str]:
        return ["url", "status_code", "tier"]


@dataclass
class PrimrSearchError(TransientError):
    """
    Search operation failed.

    Raised when a search API call fails. Includes context about
    the query and HTTP status.

    Attributes:
        query: The search query that failed
        status_code: HTTP status code (if available)
        category: Always "search"

    Example:
        try:
            results = search(query)
        except PrimrSearchError as e:
            logger.warning(f"Search failed for '{e.query}': {e.message}")
    """

    category: str = "search"
    query: str = ""
    status_code: int | None = None

    def _debug_attributes(self) -> list[str]:
        return ["query", "status_code"]


@dataclass
class PrimrOutputError(PermanentError):
    """
    Report/output generation failed.

    Raised when report generation fails, such as file write errors
    or formatting failures.

    Attributes:
        output_path: Path where output was being written
        output_format: Format being generated (e.g., "docx", "pdf")
        category: Always "output"

    Example:
        try:
            write_report(content, path)
        except PrimrOutputError as e:
            logger.error(f"Failed to write {e.output_format} to {e.output_path}")
    """

    category: str = "output"
    output_path: str = ""
    output_format: str = ""


# =============================================================================
# BACKWARD-COMPATIBLE ALIASES
# =============================================================================
# These aliases allow existing code to continue working while migrating.
# They point to the new typed error classes.

# Primary aliases - use these names in new code
AIError = PrimrAIError
ScrapingError = PrimrScrapingError
SearchError = PrimrSearchError
ConfigurationError = PrimrConfigurationError
ValidationError = PrimrValidationError
OutputError = PrimrOutputError
NetworkError = TypedNetworkError

# Base class alias
ResearchError = PrimrError


# RateLimitError wrapper for backward compatibility
# The old API used retry_after, the new API uses retry_after_seconds
class RateLimitError(TypedRateLimitError):
    """
    Backward-compatible wrapper for TypedRateLimitError.

    Accepts the old `retry_after` parameter and maps it to `retry_after_seconds`.
    """

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        retry_after: float | None = None,
        cause: Exception | None = None,
        **kwargs
    ):
        # Map old parameter name to new
        super().__init__(
            message=message,
            retry_after_seconds=retry_after or 60.0,
            cause=cause,
            **kwargs
        )


# =============================================================================
# LEGACY EXCEPTION HIERARCHY (Deprecated - Remove in v2.0)
# =============================================================================
# The classes below are kept only for backward compatibility with code
# that catches these specific exception types. New code should use the
# typed error hierarchy above.

# Legacy classes removed - aliases above provide backward compatibility


# =============================================================================
# ERROR FORMATTING UTILITIES
# =============================================================================

def format_error_for_user(error: Exception, verbose: bool = False) -> str:
    """
    Format an error for user display.

    Args:
        error: The exception to format
        verbose: If True, include debug details

    Returns:
        Formatted error string suitable for console output
    """
    if isinstance(error, PrimrError):
        if verbose:
            return error.debug_message()
        return error.user_message()

    # For non-PrimrError exceptions, provide generic formatting
    error_type = type(error).__name__
    message = str(error)

    if verbose:
        return f"[error] {error_type}: {message}"
    return message


def get_error_guidance(error: Exception) -> str | None:
    """
    Get actionable guidance for an error.

    Args:
        error: The exception to get guidance for

    Returns:
        Guidance string or None if no guidance available
    """
    # For typed errors, return the guidance attribute if set
    if isinstance(error, PrimrError):
        if error.guidance:
            return error.guidance
        # Fall back to category-based guidance
        return _CATEGORY_GUIDANCE.get(error.category)

    # Common error type guidance
    return _EXCEPTION_TYPE_GUIDANCE.get(type(error).__name__)


def is_recoverable_error(error: Exception) -> bool:
    """
    Check if an error is recoverable (can be retried).

    Args:
        error: The exception to check

    Returns:
        True if the error is recoverable
    """
    if isinstance(error, PrimrError):
        return error.recoverable

    # Common recoverable error types
    recoverable_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    return isinstance(error, recoverable_types)


# =============================================================================
# ERROR HANDLING DECORATORS
# =============================================================================

def safe_call(
    default: T | None = None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    log_level: str = "warning",
    reraise: bool = False
) -> Callable[[Callable[..., T]], Callable[..., T | None]]:
    """
    Decorator for safe function calls with automatic logging.

    Args:
        default: Value to return on failure
        exceptions: Tuple of exception types to catch
        log_level: Logging level for caught exceptions
        reraise: If True, re-raise after logging

    Example:
        @safe_call(default=None, exceptions=(requests.RequestException,))
        def fetch_url(url: str) -> Optional[str]:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T | None]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T | None:
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                log_func = getattr(logger, log_level)
                log_func(
                    f"{func.__module__}.{func.__name__} failed: {e}",
                    exc_info=(log_level == "error")
                )
                if reraise:
                    raise
                return default
        return wrapper
    return decorator


def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function on failure with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to retry on

    Example:
        @retry_on_failure(max_retries=3, exceptions=(requests.Timeout,))
        def fetch_with_retry(url: str) -> str:
            ...
    """
    import time

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} attempts: {e}"
                        )

            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unexpected state: no exception captured")
        return wrapper
    return decorator


# =============================================================================
# ERROR CONTEXT
# =============================================================================

class ErrorContext:
    """
    Context manager for adding context to errors.

    Example:
        with ErrorContext("scraping homepage", url=url):
            content = scrape_page(url)
    """

    def __init__(self, operation: str, **context: Any) -> None:
        self.operation = operation
        self.context = context

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            logger.error(f"Error during {self.operation} ({context_str}): {exc_val}")
        return False  # Don't suppress the exception


@contextmanager
def error_context(operation: str, **metadata: Any) -> Generator[None, None, None]:
    """
    Context manager that enriches exceptions with context information.

    Unlike ErrorContext class, this function-based context manager provides
    a more Pythonic interface and can be used with the 'with' statement.

    Args:
        operation: Name of the operation being performed
        **metadata: Additional context to include in error messages

    Yields:
        None

    Example:
        with error_context("fetching user", user_id=123):
            result = fetch_user(123)

        # On exception, logs: "Error during fetching user (user_id=123): <error>"
    """
    try:
        yield
    except Exception as e:
        context_str = ", ".join(f"{k}={v}" for k, v in metadata.items())
        if context_str:
            logger.error(f"Error during {operation} ({context_str}): {e}")
        else:
            logger.error(f"Error during {operation}: {e}")
        raise


class RetryManager:
    """
    Manages retry logic with exponential backoff and jitter.

    Provides both sync and async execution with configurable retry behavior,
    callbacks for retry events, and detailed tracking.

    Example:
        manager = RetryManager(RetryConfig(max_retries=3))

        # Sync usage
        result = manager.execute_sync(lambda: risky_operation())

        # Async usage
        result = await manager.execute(async_risky_operation)

        # With retry callback
        def on_retry(attempt, error):
            print(f"Retry {attempt}: {error}")
        result = manager.execute_sync(operation, on_retry=on_retry)
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        retryable_exceptions: tuple[type[Exception], ...] = (
            ConnectionError,
            TimeoutError,
            OSError,
        )
    ):
        """
        Initialize RetryManager.

        Args:
            config: Retry configuration (uses defaults if None)
            retryable_exceptions: Exception types that trigger retry
        """
        self.config = config or RetryConfig()
        self.retryable_exceptions = retryable_exceptions
        self._last_attempt_count = 0
        self._last_total_delay = 0.0

    @property
    def last_attempt_count(self) -> int:
        """Number of attempts in last execution."""
        return self._last_attempt_count

    @property
    def last_total_delay(self) -> float:
        """Total delay time in last execution (seconds)."""
        return self._last_total_delay

    async def execute(
        self,
        operation: Callable[[], Any],
        on_retry: Callable[[int, Exception], None] | None = None
    ) -> Any:
        """
        Execute async operation with retry logic.

        Args:
            operation: Async callable to execute
            on_retry: Optional callback called on each retry (attempt, error)

        Returns:
            Result of successful operation

        Raises:
            Last exception if all retries exhausted
        """
        import asyncio

        self._last_attempt_count = 0
        self._last_total_delay = 0.0
        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            self._last_attempt_count = attempt + 1
            try:
                # Handle both sync and async callables
                result = operation()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = calculate_backoff_delay(attempt, self.config)
                    self._last_total_delay += delay

                    if on_retry:
                        try:
                            on_retry(attempt + 1, e)
                        except Exception:
                            pass  # Don't let callback errors affect retry

                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_retries}: {e} "
                        f"(waiting {delay:.2f}s)"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.config.max_retries} retries exhausted: {e}"
                    )

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Unexpected state: no exception captured")

    def execute_sync(
        self,
        operation: Callable[[], T],
        on_retry: Callable[[int, Exception], None] | None = None
    ) -> T:
        """
        Execute sync operation with retry logic.

        Args:
            operation: Callable to execute
            on_retry: Optional callback called on each retry (attempt, error)

        Returns:
            Result of successful operation

        Raises:
            Last exception if all retries exhausted
        """
        import time

        self._last_attempt_count = 0
        self._last_total_delay = 0.0
        last_exception: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            self._last_attempt_count = attempt + 1
            try:
                return operation()
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    delay = calculate_backoff_delay(attempt, self.config)
                    self._last_total_delay += delay

                    if on_retry:
                        try:
                            on_retry(attempt + 1, e)
                        except Exception:
                            pass  # Don't let callback errors affect retry

                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_retries}: {e} "
                        f"(waiting {delay:.2f}s)"
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"All {self.config.max_retries} retries exhausted: {e}"
                    )

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Unexpected state: no exception captured")


def async_safe_callback(callback: Callable | None) -> Callable:
    """
    Wrap a callback to be safe for async/threaded contexts.

    The wrapped callback:
    - Never raises exceptions (logs them instead)
    - Handles None callbacks gracefully
    - Is safe to call from any thread

    Args:
        callback: The callback function to wrap (can be None)

    Returns:
        A safe wrapper function that won't raise

    Example:
        safe_cb = async_safe_callback(user_callback)
        safe_cb("progress", 50)  # Won't raise even if user_callback fails
    """
    if callback is None:
        return lambda *args, **kwargs: None

    @functools.wraps(callback)
    def safe_wrapper(*args, **kwargs):
        try:
            return callback(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Callback {callback.__name__} failed: {e}")
            return None

    return safe_wrapper
