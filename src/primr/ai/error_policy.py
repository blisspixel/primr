"""Shared AI error classification helpers."""

from __future__ import annotations

import math
import re

MAX_RETRY_AFTER_SECONDS = 90.0


def _positive_finite_seconds(value: object) -> float | None:
    """Parse and cap a finite positive delay from untrusted response metadata."""
    try:
        seconds = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    return min(seconds, MAX_RETRY_AFTER_SECONDS)


def extract_retry_after_seconds(error: Exception) -> float | None:
    """Return a finite positive Retry-After delay from headers or error text."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers and hasattr(headers, "get"):
        retry_after = headers.get("retry-after")
        if retry_after is None:
            retry_after = headers.get("Retry-After")
        if (seconds := _positive_finite_seconds(retry_after)) is not None:
            return seconds

    match = re.search(
        r"retry after\s+(\d+(?:\.\d+)?(?:e[+-]?\d+)?)",
        str(error).casefold(),
    )
    return _positive_finite_seconds(match.group(1)) if match else None


def is_billing_exhausted(error: Exception | str) -> bool:
    """Return True when an error indicates credits or spending limit exhaustion.

    These are non-retryable — the user must add credits or raise their
    spending limit before any further API calls can succeed.
    """
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code == 402:
        return True
    text = str(error).lower()
    patterns = (
        "used all available credits" in text,
        "spending limit" in text,
        "credits" in text and "exhausted" in text,
        "insufficient credits" in text,
        "insufficient_quota" in text,
        "billing" in text and "limit" in text,
    )
    return any(patterns)


def is_daily_quota_exhausted(error: Exception | str) -> bool:
    """Return True when an error indicates daily quota or billing exhaustion."""
    text = str(error).lower()
    patterns = (
        "resource_exhausted" in text and "per_day" in text,
        "resource_exhausted" in text and "quota" in text,
        "quota exceeded" in text,
        "daily limit" in text,
        "rate limit exceeded" in text and "daily" in text,
        "requests per day" in text,
        is_billing_exhausted(error),
    )
    return any(patterns)


def is_invalid_api_key_error(error: Exception | str) -> bool:
    """Return True when an error indicates invalid API authentication.

    Matches auth-specific phrases only. The previous ``"invalid" + ("api"|"key")``
    rule was too loose: a 400 ``"Invalid argument"`` or ``"invalid request to the
    api"`` would be misclassified as a bad key and abort the run as non-retryable.
    """
    text = str(error).lower()
    return (
        "invalid api key" in text
        or "invalid api_key" in text
        or "invalid x-api-key" in text
        or "incorrect api key" in text
        or "api key not valid" in text
        or "api_key_invalid" in text
        or "invalid authentication" in text
        or "authentication_error" in text
        or "unauthorized" in text
        or "401" in text
    )


def is_timeout_error(error: Exception) -> bool:
    """Handle runtime timeout variants consistently."""
    if isinstance(error, TimeoutError):
        return True
    return error.__class__.__name__ == "TimeoutError" and error.__class__.__module__.startswith(
        "asyncio"
    )
