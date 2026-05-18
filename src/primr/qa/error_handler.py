"""
Comprehensive error handling and retry logic for QA system.
"""

from collections.abc import Callable
from functools import wraps
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class QAError(Exception):
    """Base exception for QA system errors."""


class QAModelError(QAError):
    """Error related to AI model access or configuration."""


class QAAnalysisError(QAError):
    """Error during QA analysis process."""


class QAFileError(QAError):
    """Error related to file operations in QA system."""


class QARateLimitError(QAError):
    """Error due to API rate limiting."""


class QARetryHandler:
    """Handles retry logic with exponential backoff for QA operations."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        """
        Initialize retry handler.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay between retries
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def retry_with_backoff(
        self,
        operation: Callable[[], Any],
        retryable_exceptions: tuple = (Exception,),
        operation_name: str = "QA operation",
    ) -> Any:
        """
        Execute operation with exponential backoff retry logic.

        Args:
            operation: Function to execute
            retryable_exceptions: Tuple of exception types that should trigger retry
            operation_name: Name of operation for logging

        Returns:
            Result of successful operation

        Raises:
            Last exception if all retries exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Attempting {operation_name} (attempt {attempt + 1}/{self.max_retries + 1})"
                )
                result = operation()

                if attempt > 0:
                    logger.info(f"{operation_name} succeeded after {attempt + 1} attempts")

                return result

            except retryable_exceptions as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}): {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        f"{operation_name} failed after {self.max_retries + 1} attempts: {e}"
                    )

        # Re-raise the last exception if all retries exhausted
        raise last_exception


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_exceptions: tuple = (Exception,),
    operation_name: str | None = None,
):
    """
    Decorator for adding retry logic to functions.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay for exponential backoff
        retryable_exceptions: Exception types that should trigger retry
        operation_name: Name for logging (defaults to function name)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_handler = QARetryHandler(max_retries, base_delay)
            name = operation_name or f"{func.__module__}.{func.__name__}"

            def operation():
                return func(*args, **kwargs)

            return retry_handler.retry_with_backoff(operation, retryable_exceptions, name)

        return wrapper

    return decorator


class QAErrorHandler:
    """Centralized error handling for QA system."""

    @staticmethod
    def handle_model_error(error: Exception, model_name: str) -> str:
        """
        Handle AI model-related errors.

        Args:
            error: The exception that occurred
            model_name: Name of the model that failed

        Returns:
            User-friendly error message
        """
        if "authentication" in str(error).lower():
            return f"Authentication failed for model '{model_name}'. Please check your API credentials."

        if "rate limit" in str(error).lower() or "quota" in str(error).lower():
            return f"Rate limit exceeded for model '{model_name}'. Please try again later."

        if "not found" in str(error).lower() or "unavailable" in str(error).lower():
            return f"Model '{model_name}' is not available. Please check model configuration."

        if "timeout" in str(error).lower():
            return f"Request to model '{model_name}' timed out. Please try again."

        return f"Model error with '{model_name}': {error!s}"

    @staticmethod
    def handle_file_error(error: Exception, file_path: str) -> str:
        """
        Handle file operation errors.

        Args:
            error: The exception that occurred
            file_path: Path to the file that caused the error

        Returns:
            User-friendly error message
        """
        if isinstance(error, FileNotFoundError):
            return f"Report file not found: {file_path}"

        if isinstance(error, PermissionError):
            return f"Permission denied accessing file: {file_path}"

        if "encoding" in str(error).lower():
            return (
                f"File encoding error for: {file_path}. Please ensure the file is in UTF-8 format."
            )

        return f"File error with '{file_path}': {error!s}"

    @staticmethod
    def handle_analysis_error(error: Exception, company_name: str) -> str:
        """
        Handle QA analysis errors.

        Args:
            error: The exception that occurred
            company_name: Name of company being analyzed

        Returns:
            User-friendly error message
        """
        if "json" in str(error).lower() or "parse" in str(error).lower():
            return f"Failed to parse QA analysis results for {company_name}. The AI response was malformed."

        if "timeout" in str(error).lower():
            return f"QA analysis timed out for {company_name}. Please try again."

        return f"QA analysis failed for {company_name}: {error!s}"

    @staticmethod
    def create_fallback_error_message(operation: str, error: Exception) -> str:
        """
        Create a generic fallback error message.

        Args:
            operation: Name of the operation that failed
            error: The exception that occurred

        Returns:
            User-friendly error message
        """
        return f"{operation} failed: {error!s}. Please check your configuration and try again."


def safe_qa_operation(operation_name: str = "QA operation"):
    """
    Decorator for making QA operations safe with comprehensive error handling.

    Args:
        operation_name: Name of the operation for error messages
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except QAModelError as e:
                logger.error(f"{operation_name} - Model error: {e}")
                raise
            except QAFileError as e:
                logger.error(f"{operation_name} - File error: {e}")
                raise
            except QAAnalysisError as e:
                logger.error(f"{operation_name} - Analysis error: {e}")
                raise
            except Exception as e:
                logger.error(f"{operation_name} - Unexpected error: {e}")
                # Convert to QA-specific error
                raise QAError(f"{operation_name} failed: {e!s}") from e

        return wrapper

    return decorator
