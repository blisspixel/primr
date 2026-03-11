"""
Typed error hierarchy with automatic recovery classification.

This module provides the core exception hierarchy that enables automatic
retry policies and informed recovery decisions based on error classification.

Classes:
    PrimrError: Base exception with context capture
    TransientError: Errors that may succeed on retry
    PermanentError: Errors that will never succeed on retry
    TypedRateLimitError: API rate limit exceeded
    QuotaError: API quota exhausted
    TypedNetworkError: Network connectivity issues
    PrimrValidationError: Input validation failed
    AuthenticationError: Authentication failed
    PrimrConfigurationError: Configuration invalid/missing
    PrimrAIError: AI/LLM operation failed
    PrimrScrapingError: Web scraping failed
    PrimrSearchError: Search operation failed
    PrimrOutputError: Report generation failed
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from primr.config.config import ConfigurationError as _ConfigConfigurationError
from primr.utils.errors.base import CATEGORY_GUIDANCE, get_correlation_id

# =============================================================================
# BASE ERROR CLASS
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
    correlation_id: str = field(default_factory=get_correlation_id)
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
        return CATEGORY_GUIDANCE.get(self.category, "")

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


# =============================================================================
# BASE TRANSIENT/PERMANENT CLASSES
# =============================================================================


@dataclass
class TransientError(PrimrError):
    """
    Base class for errors that may succeed on retry.

    Transient errors represent temporary failures that are likely to
    resolve themselves, such as network timeouts, rate limits, or
    temporary service unavailability.
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
    """

    recoverable: bool = False
    category: str = "permanent"


# =============================================================================
# SPECIFIC ERROR TYPES
# =============================================================================


@dataclass
class TypedRateLimitError(TransientError):
    """
    API rate limit exceeded.

    Attributes:
        retry_after_seconds: Seconds to wait before retrying (default: 60.0)
    """

    message: str = "API rate limit exceeded"
    category: str = "rate_limit"
    retry_after_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Set retry_after from retry_after_seconds and update guidance."""
        super().__post_init__()
        self.retry_after = self.retry_after_seconds
        if self.retry_after_seconds:
            self.guidance = (
                f"Rate limit exceeded. Try again in {self.retry_after_seconds:.0f} seconds."
            )


@dataclass
class QuotaError(TransientError):
    """
    API quota exhausted.

    Attributes:
        quota_reset_time: When the quota will be reset (optional)
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
    Network connectivity issues.

    Attributes:
        host: The host that was being connected to
        port: The port that was being connected to (optional)
    """

    category: str = "network"
    host: str = ""
    port: int | None = None


@dataclass
class PrimrValidationError(PermanentError):
    """
    Input validation failed.

    Attributes:
        field_errors: Mapping of field names to error messages
    """

    category: str = "validation"
    field_errors: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class AuthenticationError(PermanentError):
    """
    Authentication failed.

    Attributes:
        auth_method: The authentication method that failed (e.g., "api_key", "oauth")
    """

    category: str = "authentication"
    auth_method: str = ""


@dataclass
class PrimrConfigurationError(PermanentError, _ConfigConfigurationError):
    """
    Configuration is invalid or missing.

    Inherits from both PermanentError (typed error hierarchy) and
    config.ConfigurationError so that isinstance checks work for either type.

    Attributes:
        config_path: Path to the configuration file (if applicable)
        missing_keys: List of missing configuration keys
    """

    category: str = "configuration"
    config_path: str = ""
    missing_keys: list[str] = field(default_factory=list)


@dataclass
class PrimrAIError(TransientError):
    """
    AI/LLM operation failed.

    Attributes:
        model: The model that was being used
        operation: The operation that failed (e.g., "generate", "embed")
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

    Attributes:
        url: The URL that was being scraped
        status_code: HTTP status code (if available)
        tier: The scraping tier that failed
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

    Attributes:
        query: The search query that failed
        status_code: HTTP status code (if available)
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

    Attributes:
        output_path: Path where output was being written
        output_format: Format being generated (e.g., "docx", "pdf")
    """

    category: str = "output"
    output_path: str = ""
    output_format: str = ""


# =============================================================================
# BACKWARD-COMPATIBLE ALIASES
# =============================================================================

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
        **kwargs: Any,
    ):
        super().__init__(
            message=message,
            retry_after_seconds=retry_after or 60.0,
            cause=cause,
            **kwargs,
        )
