"""Coverage tests for primr.qa.error_handler.

Covers QARetryHandler backoff (sleep mocked), the with_retry and
safe_qa_operation decorators, and every branch of the QAErrorHandler
static message builders.
"""

from __future__ import annotations

import pytest

from primr.qa.error_handler import (
    QAAnalysisError,
    QAError,
    QAErrorHandler,
    QAFileError,
    QAModelError,
    QARetryHandler,
    safe_qa_operation,
    with_retry,
)


class TestQARetryHandler:
    def test_negative_retry_count_is_rejected(self):
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            QARetryHandler(max_retries=-1)

    def test_success_first_try(self):
        handler = QARetryHandler(max_retries=2)
        assert handler.retry_with_backoff(lambda: "ok") == "ok"

    def test_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        handler = QARetryHandler(max_retries=3, base_delay=0.01)
        calls = {"n": 0}

        def op():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("transient")
            return "done"

        assert handler.retry_with_backoff(op) == "done"
        assert calls["n"] == 3

    def test_exhausts_and_reraises_last(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        handler = QARetryHandler(max_retries=2, base_delay=0.01)

        def op():
            raise RuntimeError("always")

        with pytest.raises(RuntimeError, match="always"):
            handler.retry_with_backoff(op)

    def test_non_retryable_exception_propagates(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        handler = QARetryHandler(max_retries=3)

        def op():
            raise KeyError("not retryable")

        # Only ValueError is retryable here -> KeyError raised immediately.
        with pytest.raises(KeyError):
            handler.retry_with_backoff(op, retryable_exceptions=(ValueError,))

    def test_delay_capped_at_max(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr("time.sleep", lambda d: sleeps.append(d))
        handler = QARetryHandler(max_retries=5, base_delay=10.0, max_delay=15.0)
        calls = {"n": 0}

        def op():
            calls["n"] += 1
            if calls["n"] <= 3:
                raise ValueError("x")
            return "ok"

        handler.retry_with_backoff(op)
        assert all(d <= 15.0 for d in sleeps)


class TestWithRetryDecorator:
    def test_decorator_retries(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        calls = {"n": 0}

        @with_retry(max_retries=3, base_delay=0.01)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry me")
            return "success"

        assert flaky() == "success"
        assert calls["n"] == 2

    def test_decorator_with_custom_name(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)

        @with_retry(max_retries=1, operation_name="custom-op")
        def ok():
            return 7

        assert ok() == 7


class TestQAErrorHandlerModelErrors:
    def test_authentication_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("Authentication failed"), "m")
        assert "Authentication failed" in msg

    def test_rate_limit_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("rate limit hit"), "m")
        assert "Rate limit exceeded" in msg

    def test_quota_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("quota gone"), "m")
        assert "Rate limit exceeded" in msg

    def test_not_found_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("model not found"), "m")
        assert "not available" in msg

    def test_unavailable_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("service unavailable"), "m")
        assert "not available" in msg

    def test_timeout_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("request timeout"), "m")
        assert "timed out" in msg

    def test_generic_error(self):
        msg = QAErrorHandler.handle_model_error(Exception("weird thing"), "gemini")
        assert "Model error" in msg
        assert "gemini" in msg


class TestQAErrorHandlerFileErrors:
    def test_file_not_found(self):
        msg = QAErrorHandler.handle_file_error(FileNotFoundError(), "/x/y.txt")
        assert "not found" in msg

    def test_permission_error(self):
        msg = QAErrorHandler.handle_file_error(PermissionError(), "/x/y.txt")
        assert "Permission denied" in msg

    def test_encoding_error(self):
        msg = QAErrorHandler.handle_file_error(Exception("bad encoding"), "/x/y.txt")
        assert "UTF-8" in msg

    def test_generic_file_error(self):
        msg = QAErrorHandler.handle_file_error(Exception("disk error"), "/x/y.txt")
        assert "File error" in msg


class TestQAErrorHandlerAnalysisErrors:
    def test_json_parse_error(self):
        msg = QAErrorHandler.handle_analysis_error(Exception("json broken"), "Acme")
        assert "malformed" in msg

    def test_parse_keyword_error(self):
        msg = QAErrorHandler.handle_analysis_error(Exception("cannot parse"), "Acme")
        assert "malformed" in msg

    def test_timeout_analysis_error(self):
        msg = QAErrorHandler.handle_analysis_error(Exception("timeout"), "Acme")
        assert "timed out" in msg

    def test_generic_analysis_error(self):
        msg = QAErrorHandler.handle_analysis_error(Exception("oops"), "Acme")
        assert "QA analysis failed for Acme" in msg

    def test_fallback_message(self):
        msg = QAErrorHandler.create_fallback_error_message("Scoring", Exception("nope"))
        assert "Scoring failed" in msg


class TestSafeQAOperationDecorator:
    def test_passes_through_success(self):
        @safe_qa_operation("op")
        def good():
            return "value"

        assert good() == "value"

    def test_reraises_model_error(self):
        @safe_qa_operation("op")
        def bad():
            raise QAModelError("model down")

        with pytest.raises(QAModelError):
            bad()

    def test_reraises_file_error(self):
        @safe_qa_operation("op")
        def bad():
            raise QAFileError("no file")

        with pytest.raises(QAFileError):
            bad()

    def test_reraises_analysis_error(self):
        @safe_qa_operation("op")
        def bad():
            raise QAAnalysisError("analysis fail")

        with pytest.raises(QAAnalysisError):
            bad()

    def test_wraps_unexpected_in_qaerror(self):
        @safe_qa_operation("op")
        def bad():
            raise ValueError("surprise")

        with pytest.raises(QAError) as exc:
            bad()
        assert "op failed" in str(exc.value)
        assert isinstance(exc.value.__cause__, ValueError)
