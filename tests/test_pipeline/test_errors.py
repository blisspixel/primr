"""
Unit tests for pipeline error classification.

Tests verify that errors are correctly classified into TRANSIENT, QUOTA,
and CONFIGURATION categories, that ``is_rate_limited`` detects HTTP 429,
and that the module delegates to ``error_policy.py`` rather than
duplicating logic.

**Feature: pipeline-resilience**
**Validates: Requirements 15.1, 15.2, 15.3, 15.4**
"""

from __future__ import annotations

import ast
import inspect

from primr.pipeline.errors import (
    ErrorCategory,
    classify_error,
    is_rate_limited,
)

# =========================================================================
# Requirement 15.1 — Transient errors
# =========================================================================


class TestTransientClassification:
    """HTTP 429, 500, 502, 503, 504, timeout, and connection reset → TRANSIENT."""

    def test_http_429(self) -> None:
        err = Exception("429 Too Many Requests")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_http_500(self) -> None:
        err = Exception("500 Internal Server Error")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_http_502(self) -> None:
        err = Exception("502 Bad Gateway")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_http_503(self) -> None:
        err = Exception("503 Service Unavailable")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_http_504(self) -> None:
        err = Exception("504 Gateway Timeout")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_timeout_error(self) -> None:
        err = TimeoutError("request timed out")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_connection_reset(self) -> None:
        err = Exception("connection reset by peer")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_connection_refused(self) -> None:
        err = Exception("connection refused")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_connection_error_builtin(self) -> None:
        err = ConnectionError("remote end closed connection")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_service_unavailable_text(self) -> None:
        err = Exception("service unavailable, try again later")
        assert classify_error(err) == ErrorCategory.TRANSIENT


# =========================================================================
# Requirement 15.2 — Quota errors
# =========================================================================


class TestQuotaClassification:
    """Daily quota exhaustion → QUOTA."""

    def test_resource_exhausted_per_day(self) -> None:
        err = Exception("RESOURCE_EXHAUSTED: per_day limit reached")
        assert classify_error(err) == ErrorCategory.QUOTA

    def test_quota_exceeded(self) -> None:
        err = Exception("quota exceeded for project")
        assert classify_error(err) == ErrorCategory.QUOTA

    def test_daily_limit(self) -> None:
        err = Exception("daily limit reached")
        assert classify_error(err) == ErrorCategory.QUOTA


# =========================================================================
# Requirement 15.3 — Configuration errors
# =========================================================================


class TestConfigurationClassification:
    """Missing API key and invalid model name → CONFIGURATION."""

    def test_invalid_api_key(self) -> None:
        err = Exception("invalid api key provided")
        assert classify_error(err) == ErrorCategory.CONFIGURATION

    def test_invalid_authentication(self) -> None:
        err = Exception("invalid authentication credentials")
        assert classify_error(err) == ErrorCategory.CONFIGURATION

    def test_invalid_model_name(self) -> None:
        err = Exception("invalid model: grok-nonexistent")
        assert classify_error(err) == ErrorCategory.CONFIGURATION

    def test_model_not_found(self) -> None:
        err = Exception("model not found: bad-model-name")
        assert classify_error(err) == ErrorCategory.CONFIGURATION


# =========================================================================
# is_rate_limited — HTTP 429 detection
# =========================================================================


class TestIsRateLimited:
    """``is_rate_limited`` detects HTTP 429 specifically."""

    def test_429_rate_limit(self) -> None:
        assert is_rate_limited(Exception("429 rate limit exceeded")) is True

    def test_429_too_many_requests(self) -> None:
        assert is_rate_limited(Exception("429 Too Many Requests")) is True

    def test_non_429_error(self) -> None:
        assert is_rate_limited(Exception("500 Internal Server Error")) is False

    def test_timeout_is_not_rate_limited(self) -> None:
        assert is_rate_limited(TimeoutError("timed out")) is False

    def test_quota_is_not_rate_limited(self) -> None:
        assert is_rate_limited(Exception("quota exceeded")) is False


# =========================================================================
# Requirement 15.4 — Reuse of error_policy.py functions
# =========================================================================


class TestErrorPolicyReuse:
    """Verify that errors.py delegates to error_policy.py functions
    rather than duplicating their logic."""

    def test_source_imports_error_policy_functions(self) -> None:
        """The module must import the three error_policy helpers."""
        module_source = inspect.getmodule(classify_error)
        assert module_source is not None
        full_source = inspect.getsource(module_source)

        tree = ast.parse(full_source)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "primr.ai.error_policy":
                for alias in node.names:
                    imported_names.add(alias.name)

        expected = {"is_daily_quota_exhausted", "is_invalid_api_key_error", "is_timeout_error"}
        assert expected.issubset(imported_names), (
            f"errors.py must import {expected} from error_policy; found {imported_names}"
        )

    def test_classify_error_calls_is_daily_quota_exhausted(self) -> None:
        """classify_error must call is_daily_quota_exhausted, not reimplement it."""
        source = inspect.getsource(classify_error)
        assert "is_daily_quota_exhausted" in source

    def test_classify_error_calls_is_invalid_api_key_error(self) -> None:
        """classify_error must call is_invalid_api_key_error, not reimplement it."""
        source = inspect.getsource(classify_error)
        assert "is_invalid_api_key_error" in source
