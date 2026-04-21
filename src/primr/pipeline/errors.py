"""
Error classification helpers for pipeline recovery decisions.

This module provides:
- ErrorCategory enum (TRANSIENT, QUOTA, CONFIGURATION)
- classify_error() to map any exception to its ErrorCategory
- is_rate_limited() to detect HTTP 429 specifically

All classification delegates to existing ``error_policy.py`` functions
where possible — no logic is duplicated.

**Feature: pipeline-resilience**
**Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5**
"""

from __future__ import annotations

from enum import Enum

from primr.ai.error_policy import (
    is_billing_exhausted,
    is_daily_quota_exhausted,
    is_invalid_api_key_error,
    is_timeout_error,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TRANSIENT_HTTP_CODES: frozenset[str] = frozenset({"429", "500", "502", "503", "504"})

_TRANSIENT_MARKERS: tuple[str, ...] = (
    "connection reset",
    "connection aborted",
    "connection refused",
    "service unavailable",
    "temporarily unavailable",
    "internal server error",
)


# ---------------------------------------------------------------------------
# ErrorCategory enum
# ---------------------------------------------------------------------------


class ErrorCategory(Enum):
    """Classification that determines recovery behaviour.

    * TRANSIENT — retryable via the recovery hierarchy.
    * QUOTA — non-retryable, abort the run immediately.
    * CONFIGURATION — non-retryable, skip fallback, raise.
    """

    TRANSIENT = "transient"
    QUOTA = "quota"
    CONFIGURATION = "configuration"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_rate_limited(error: Exception) -> bool:
    """Return True when the error indicates an HTTP 429 rate-limit response."""
    text = str(error).lower()
    return "429" in text and (
        "rate" in text or "limit" in text or "too many" in text or text.strip() == "429"
    )


def _is_transient_error(error: Exception) -> bool:
    """Return True for transient / retryable errors.

    Covers HTTP 429, 500, 502, 503, 504, timeouts, and connection resets.
    Delegates timeout detection to ``error_policy.is_timeout_error``.
    """
    # Timeout — delegate to existing helper
    if is_timeout_error(error):
        return True

    text = str(error).lower()

    # HTTP status codes embedded in the error message
    if any(code in text for code in _TRANSIENT_HTTP_CODES):
        return True

    # Connection-level failures
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return True

    # Python built-in connection errors
    return isinstance(error, ConnectionError)


def classify_error(error: Exception) -> ErrorCategory:
    """Classify *error* into a recovery category.

    Evaluation order:
    1. **Configuration** — checked first so that missing-key errors are never
       retried even if the message also contains a transient marker.
    2. **Quota** — daily quota exhaustion aborts the run immediately.
    3. **Transient** — everything retryable (429, 5xx, timeout, connection).
    4. Falls back to **TRANSIENT** for unknown errors so the recovery
       hierarchy gets a chance to handle them.
    """
    # 1. Configuration errors — delegate to error_policy
    if is_invalid_api_key_error(error):
        return ErrorCategory.CONFIGURATION

    text = str(error).lower()
    if "invalid model" in text or "model not found" in text:
        return ErrorCategory.CONFIGURATION

    # 2. Billing / quota errors — delegate to error_policy
    if is_billing_exhausted(error) or is_daily_quota_exhausted(error):
        return ErrorCategory.QUOTA

    # 3. Transient errors
    if _is_transient_error(error):
        return ErrorCategory.TRANSIENT

    # 4. Unknown errors default to transient so the hierarchy can attempt recovery
    return ErrorCategory.TRANSIENT
