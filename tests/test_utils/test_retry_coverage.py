"""Coverage tests for primr.utils.retry.RetryPolicyManager.

Deterministic unit tests (sleeps mocked) covering RetryPolicy validation,
RetryAttempt serialization, should_retry decision branches, get_delay's
error-specific and backoff branches, telemetry emission (success + failure),
retry-history attachment, and both async/sync execute_with_retry flows.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from primr.utils.errors import PrimrError, QuotaError
from primr.utils.retry import (
    RetryAttempt,
    RetryPolicy,
    RetryPolicyManager,
)


def _transient(msg="boom", retry_after=None):
    return PrimrError(
        msg, category="transient", recoverable=True, retry_after=retry_after
    )


class TestRetryPolicyValidation:
    def test_defaults(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert "transient" in p.retryable_categories

    def test_negative_max_retries(self):
        with pytest.raises(ValueError, match="max_retries"):
            RetryPolicy(max_retries=-1)

    def test_nonpositive_base_delay(self):
        with pytest.raises(ValueError, match="base_delay"):
            RetryPolicy(base_delay=0)

    def test_nonpositive_max_delay(self):
        with pytest.raises(ValueError, match="max_delay"):
            RetryPolicy(max_delay=0)

    def test_exponential_base_too_small(self):
        with pytest.raises(ValueError, match="exponential_base"):
            RetryPolicy(exponential_base=1.0)

    def test_jitter_out_of_range(self):
        with pytest.raises(ValueError, match="jitter_factor"):
            RetryPolicy(jitter_factor=1.5)


class TestRetryAttempt:
    def test_to_dict(self):
        err = _transient("oops")
        attempt = RetryAttempt(attempt_number=1, error=err, delay_seconds=2.5)
        d = attempt.to_dict()
        assert d["attempt"] == 1
        assert d["error_type"] == "PrimrError"
        assert d["delay"] == 2.5
        assert "timestamp" in d


class TestShouldRetry:
    def test_non_primr_error_not_retried(self):
        mgr = RetryPolicyManager()
        assert mgr.should_retry(ValueError("x"), attempt=0) is False

    def test_non_recoverable_not_retried(self):
        mgr = RetryPolicyManager()
        err = PrimrError("x", category="transient", recoverable=False)
        assert mgr.should_retry(err, attempt=0) is False

    def test_category_not_in_set_not_retried(self):
        mgr = RetryPolicyManager(RetryPolicy(retryable_categories={"network"}))
        err = PrimrError("x", category="transient", recoverable=True)
        assert mgr.should_retry(err, attempt=0) is False

    def test_max_retries_exceeded_not_retried(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=2))
        assert mgr.should_retry(_transient(), attempt=2) is False

    def test_eligible_error_retried(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))
        assert mgr.should_retry(_transient(), attempt=0) is True


class TestGetDelay:
    def test_uses_error_retry_after(self):
        mgr = RetryPolicyManager()
        assert mgr.get_delay(_transient(retry_after=7.0), attempt=2) == 7.0

    def test_negative_retry_after_clamped(self):
        mgr = RetryPolicyManager()
        assert mgr.get_delay(_transient(retry_after=-3.0), attempt=0) == 0.0

    def test_quota_reset_time(self):
        mgr = RetryPolicyManager()
        reset = datetime.now() + timedelta(seconds=30)
        err = QuotaError("quota", quota_reset_time=reset)
        delay = mgr.get_delay(err, attempt=0)
        assert 0 < delay <= 31

    def test_quota_reset_in_past_clamped(self):
        mgr = RetryPolicyManager()
        reset = datetime.now() - timedelta(seconds=30)
        err = QuotaError("quota", quota_reset_time=reset)
        assert mgr.get_delay(err, attempt=0) == 0.0

    def test_exponential_backoff_capped(self):
        policy = RetryPolicy(base_delay=10.0, max_delay=15.0, jitter_factor=0.0)
        mgr = RetryPolicyManager(policy)
        # base * 2^5 = 320, capped to 15.
        assert mgr.get_delay(_transient(), attempt=5) == 15.0

    def test_backoff_includes_jitter_nonnegative(self):
        policy = RetryPolicy(base_delay=1.0, jitter_factor=0.5)
        mgr = RetryPolicyManager(policy)
        delay = mgr.get_delay(_transient(), attempt=1)
        assert delay >= 0.0


class TestEmitMetricAndHistory:
    def test_emit_metric_noop_without_telemetry(self):
        mgr = RetryPolicyManager()
        mgr._emit_retry_metric(_transient(), attempt=0, delay=1.0)  # no telemetry, no-op

    def test_emit_metric_calls_telemetry(self):
        telemetry = MagicMock()
        mgr = RetryPolicyManager(telemetry=telemetry)
        mgr._emit_retry_metric(_transient(), attempt=1, delay=2.0)
        telemetry.emit_metric.assert_called_once()
        _, kwargs = telemetry.emit_metric.call_args
        assert kwargs["name"] == "retry_attempt"
        assert kwargs["tags"]["attempt"] == "1"

    def test_emit_metric_swallows_telemetry_error(self):
        telemetry = MagicMock()
        telemetry.emit_metric.side_effect = RuntimeError("metrics down")
        mgr = RetryPolicyManager(telemetry=telemetry)
        # Should not raise.
        mgr._emit_retry_metric(_transient(), attempt=0, delay=1.0)

    def test_attach_retry_history_populates_context(self):
        mgr = RetryPolicyManager()
        err = _transient()
        mgr._record_attempt(0, _transient("first"), 1.0)
        mgr._attach_retry_history(err)
        assert "retry_history" in err.context
        assert len(err.context["retry_history"]) == 1

    def test_attach_retry_history_no_attempts(self):
        mgr = RetryPolicyManager()
        err = _transient()
        mgr._attach_retry_history(err)
        assert "retry_history" not in err.context

    def test_attempts_property_returns_copy(self):
        mgr = RetryPolicyManager()
        mgr._record_attempt(0, _transient(), 1.0)
        copied = mgr.attempts
        copied.clear()
        assert len(mgr.attempts) == 1


class TestExecuteWithRetryAsync:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))

        def op():
            return "ok"

        assert await mgr.execute_with_retry(op) == "ok"

    @pytest.mark.asyncio
    async def test_async_coroutine_result_awaited(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=2))

        async def op():
            return 42

        assert await mgr.execute_with_retry(op) == 42

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self, monkeypatch):
        async def no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", no_sleep)
        calls = {"n": 0}
        policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter_factor=0.0)
        mgr = RetryPolicyManager(policy)

        def op():
            calls["n"] += 1
            if calls["n"] < 3:
                raise _transient()
            return "done"

        result = await mgr.execute_with_retry(op)
        assert result == "done"
        assert calls["n"] == 3
        assert len(mgr.attempts) == 2

    @pytest.mark.asyncio
    async def test_exhausts_and_raises_with_history(self, monkeypatch):
        async def no_sleep(_):
            return None

        monkeypatch.setattr("asyncio.sleep", no_sleep)
        policy = RetryPolicy(max_retries=2, base_delay=0.01, jitter_factor=0.0)
        mgr = RetryPolicyManager(policy)

        def op():
            raise _transient("always fails")

        with pytest.raises(PrimrError) as exc:
            await mgr.execute_with_retry(op)
        assert "retry_history" in exc.value.context

    @pytest.mark.asyncio
    async def test_non_retryable_primr_error_raises_immediately(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))

        def op():
            raise PrimrError("fatal", category="general", recoverable=False)

        with pytest.raises(PrimrError):
            await mgr.execute_with_retry(op)
        assert len(mgr.attempts) == 0

    @pytest.mark.asyncio
    async def test_non_primr_exception_not_retried(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))

        def op():
            raise ValueError("plain")

        with pytest.raises(ValueError):
            await mgr.execute_with_retry(op)


class TestExecuteWithRetrySync:
    def test_success_first_try(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))
        assert mgr.execute_with_retry_sync(lambda: "ok") == "ok"

    def test_retries_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        calls = {"n": 0}
        policy = RetryPolicy(max_retries=3, base_delay=0.01, jitter_factor=0.0)
        mgr = RetryPolicyManager(policy)

        def op():
            calls["n"] += 1
            if calls["n"] < 2:
                raise _transient()
            return "done"

        assert mgr.execute_with_retry_sync(op) == "done"
        assert calls["n"] == 2

    def test_exhausts_and_raises(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        policy = RetryPolicy(max_retries=1, base_delay=0.01, jitter_factor=0.0)
        mgr = RetryPolicyManager(policy)

        def op():
            raise _transient("nope")

        with pytest.raises(PrimrError) as exc:
            mgr.execute_with_retry_sync(op)
        assert "retry_history" in exc.value.context

    def test_non_retryable_raises_immediately(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))

        def op():
            raise PrimrError("fatal", category="general", recoverable=False)

        with pytest.raises(PrimrError):
            mgr.execute_with_retry_sync(op)

    def test_non_primr_exception_not_retried(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=3))
        with pytest.raises(KeyError):
            mgr.execute_with_retry_sync(lambda: (_ for _ in ()).throw(KeyError("k")))
