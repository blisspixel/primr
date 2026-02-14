"""Tests for shared AI error policy helpers."""

from primr.ai.error_policy import (
    is_daily_quota_exhausted,
    is_invalid_api_key_error,
    is_timeout_error,
)


def test_is_daily_quota_exhausted_patterns():
    assert is_daily_quota_exhausted("RESOURCE_EXHAUSTED per_day")
    assert is_daily_quota_exhausted("quota exceeded")
    assert is_daily_quota_exhausted("rate limit exceeded daily")
    assert not is_daily_quota_exhausted("temporary connection error")


def test_is_invalid_api_key_error_patterns():
    assert is_invalid_api_key_error("invalid api key")
    assert is_invalid_api_key_error("invalid authentication")
    assert not is_invalid_api_key_error("timeout contacting endpoint")


def test_is_timeout_error_variants():
    assert is_timeout_error(TimeoutError("timed out"))

    AsyncioTimeoutError = type("TimeoutError", (Exception,), {"__module__": "asyncio.tasks"})
    e = AsyncioTimeoutError("async timeout")
    assert is_timeout_error(e)
