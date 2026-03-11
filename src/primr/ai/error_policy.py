"""Shared AI error classification helpers."""

from __future__ import annotations


def is_daily_quota_exhausted(error: Exception | str) -> bool:
    """Return True when an error indicates daily quota exhaustion."""
    text = str(error).lower()
    patterns = (
        "resource_exhausted" in text and "per_day" in text,
        "resource_exhausted" in text and "quota" in text,
        "quota exceeded" in text,
        "daily limit" in text,
        "rate limit exceeded" in text and "daily" in text,
        "requests per day" in text,
    )
    return any(patterns)


def is_invalid_api_key_error(error: Exception | str) -> bool:
    """Return True when an error indicates invalid API authentication."""
    text = str(error).lower()
    return "invalid" in text and ("api" in text or "key" in text or "authentication" in text)


def is_timeout_error(error: Exception) -> bool:
    """Handle runtime timeout variants consistently."""
    if isinstance(error, TimeoutError):
        return True
    return error.__class__.__name__ == "TimeoutError" and error.__class__.__module__.startswith(
        "asyncio"
    )
