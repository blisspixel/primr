"""
Error handling decorators and context managers.

This module provides:
- safe_call: Decorator for safe function calls with logging
- retry_on_failure: Decorator for automatic retry with backoff
- ErrorContext: Class-based context manager for error enrichment
- error_context: Function-based context manager for error enrichment
- async_safe_callback: Wrapper for safe async callbacks
"""

from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# ERROR HANDLING DECORATORS
# =============================================================================


def safe_call(
    default: T | None = None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    log_level: str = "warning",
    reraise: bool = False,
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
                    exc_info=(log_level == "error"),
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
    exceptions: tuple[type[Exception], ...] = (Exception,),
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
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")

            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Unexpected state: no exception captured")

        return wrapper

    return decorator


# =============================================================================
# ERROR CONTEXT MANAGERS
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

    def __enter__(self) -> ErrorContext:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
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


# =============================================================================
# CALLBACK UTILITIES
# =============================================================================


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
    def safe_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return callback(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Callback {callback.__name__} failed: {e}")
            return None

    return safe_wrapper
