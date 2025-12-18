"""
Custom exceptions and error handling utilities.

This module provides:
- Custom exception hierarchy for the application
- Decorators for safe function calls with logging
- Error context management
- Retry configuration with exponential backoff and jitter
"""

import functools
import logging
import random
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


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
# EXCEPTION HIERARCHY
# =============================================================================

class ResearchError(Exception):
    """Base exception for all research-related errors."""

    # Error category for classification
    category: str = "general"
    # Whether this error is recoverable (can be retried)
    recoverable: bool = False
    # User-friendly guidance for resolving the error
    guidance: str = ""

    def __init__(
        self,
        message: str,
        cause: Exception | None = None,
        guidance: str | None = None
    ):
        super().__init__(message)
        self.cause = cause
        self.message = message
        if guidance:
            self.guidance = guidance

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message

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
            Detailed message including cause chain
        """
        parts = [f"[{self.category}] {self.message}"]
        if self.cause:
            parts.append(f"  Caused by: {type(self.cause).__name__}: {self.cause}")
        if self.guidance:
            parts.append(f"  Guidance: {self.guidance}")
        return "\n".join(parts)


class ConfigurationError(ResearchError):
    """Raised when configuration is invalid or missing."""
    category = "configuration"
    recoverable = False
    guidance = "Check your .env file and environment variables"


class ScrapingError(ResearchError):
    """Raised when web scraping fails."""
    category = "scraping"
    recoverable = True
    guidance = "The website may be blocking automated access. Try again later."

    def __init__(
        self,
        message: str,
        url: str = "",
        cause: Exception | None = None,
        guidance: str | None = None
    ):
        super().__init__(message, cause, guidance)
        self.url = url

    def debug_message(self) -> str:
        base = super().debug_message()
        if self.url:
            return f"{base}\n  URL: {self.url}"
        return base


class AIError(ResearchError):
    """Raised when AI operations fail."""
    category = "ai"
    recoverable = True
    guidance = "Check API quota and try again"

    def __init__(
        self,
        message: str,
        model: str = "",
        cause: Exception | None = None,
        guidance: str | None = None
    ):
        super().__init__(message, cause, guidance)
        self.model = model

    def debug_message(self) -> str:
        base = super().debug_message()
        if self.model:
            return f"{base}\n  Model: {self.model}"
        return base


class RateLimitError(AIError):
    """Raised when API rate limit is exceeded."""
    category = "rate_limit"
    recoverable = True
    guidance = "Rate limit exceeded. Wait a moment and try again."

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        retry_after: float | None = None,
        cause: Exception | None = None
    ):
        guidance = "Rate limit exceeded."
        if retry_after:
            guidance += f" Try again in {retry_after:.0f} seconds."
        super().__init__(message, cause=cause, guidance=guidance)
        self.retry_after = retry_after


class SearchError(ResearchError):
    """Raised when search operations fail."""
    category = "search"
    recoverable = True
    guidance = "Search API may be unavailable. Check your API key and quota."

    def __init__(
        self,
        message: str,
        query: str = "",
        cause: Exception | None = None,
        guidance: str | None = None
    ):
        super().__init__(message, cause, guidance)
        self.query = query

    def debug_message(self) -> str:
        base = super().debug_message()
        if self.query:
            return f"{base}\n  Query: {self.query}"
        return base


class OutputError(ResearchError):
    """Raised when report generation fails."""
    category = "output"
    recoverable = False
    guidance = "Check disk space and file permissions"


class ValidationError(ResearchError):
    """Raised when input validation fails."""
    category = "validation"
    recoverable = False
    guidance = "Check your input and try again"


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
    if isinstance(error, ResearchError):
        if verbose:
            return error.debug_message()
        return error.user_message()

    # For non-ResearchError exceptions, provide generic formatting
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
    if isinstance(error, ResearchError) and error.guidance:
        return error.guidance

    # Common error type guidance
    error_type = type(error).__name__
    guidance_map = {
        "ConnectionError": "Check your internet connection",
        "TimeoutError": "The operation timed out. Try again or increase timeout.",
        "FileNotFoundError": "The specified file does not exist",
        "PermissionError": "Permission denied. Check file/folder permissions.",
        "JSONDecodeError": "Invalid JSON data received",
    }
    return guidance_map.get(error_type)


def is_recoverable_error(error: Exception) -> bool:
    """
    Check if an error is recoverable (can be retried).

    Args:
        error: The exception to check

    Returns:
        True if the error is recoverable
    """
    if isinstance(error, ResearchError):
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
