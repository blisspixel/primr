"""Tests for shared AI error policy helpers."""

from primr.ai.error_policy import (
    MAX_RETRY_AFTER_SECONDS,
    extract_retry_after_seconds,
    is_daily_quota_exhausted,
    is_invalid_api_key_error,
    is_timeout_error,
)


class _RetryAfterError(Exception):
    def __init__(self, value: object, key: str = "retry-after"):
        self.response = type("Response", (), {"headers": {key: value}})()


def test_extract_retry_after_seconds_accepts_header_and_text_delays():
    assert extract_retry_after_seconds(_RetryAfterError("2.5")) == 2.5
    assert extract_retry_after_seconds(_RetryAfterError("3", "Retry-After")) == 3.0
    assert extract_retry_after_seconds(Exception("Retry after 7 seconds")) == 7.0


def test_extract_retry_after_seconds_rejects_invalid_delays():
    for value in (None, "invalid", "inf", "nan", "0", "-1"):
        assert extract_retry_after_seconds(_RetryAfterError(value)) is None


def test_extract_retry_after_seconds_caps_attacker_controlled_delays():
    assert extract_retry_after_seconds(_RetryAfterError("1e100")) == MAX_RETRY_AFTER_SECONDS
    assert (
        extract_retry_after_seconds(Exception("Retry after 1e100 seconds"))
        == MAX_RETRY_AFTER_SECONDS
    )
    assert (
        extract_retry_after_seconds(Exception("Retry after 999999999999999999999 seconds"))
        == MAX_RETRY_AFTER_SECONDS
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
