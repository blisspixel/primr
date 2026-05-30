"""Coverage tests for primr.utils.telemetry enabled code paths.

The existing test_telemetry.py covers the disabled fast path, NullSpan, and
CostTracker math. This file drives the *enabled* paths by injecting a mock
tracer/span so the span/async_span bodies, exception recording, record_event,
record_cost attribute attachment, get_current_span, shutdown, and the
correlation-id helpers all execute without needing OpenTelemetry installed.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from primr.utils import telemetry as tel
from primr.utils.telemetry import (
    CostTracker,
    NullSpan,
    TelemetryConfig,
    TelemetrySystem,
    get_async_correlation_id,
)


class _FakeTracer:
    """Minimal tracer whose start_as_current_span yields a recording span."""

    def __init__(self, span):
        self._span = span

    @contextmanager
    def start_as_current_span(self, name, attributes=None):
        self._span.last_name = name
        self._span.last_attributes = attributes
        yield self._span


def _make_enabled_system(span=None):
    """Build a TelemetrySystem that reports as enabled with a mock tracer."""
    span = span or MagicMock()
    span.is_recording.return_value = True
    ts = TelemetrySystem(TelemetryConfig(enabled=True))
    # OTel likely not installed in CI; force the enabled internal state.
    ts._tracer = _FakeTracer(span)
    ts._initialized = True
    ts.config.enabled = True
    return ts, span


class TestEnabledSpan:
    def test_span_yields_real_span_and_sets_attributes(self):
        ts, span = _make_enabled_system()
        assert ts.is_enabled is True
        with ts.span("op", phase="scraping", attributes={"k": "v"}) as s:
            assert s is span
        attrs = span.last_attributes
        assert attrs["operation_name"] == "op"
        assert attrs["phase"] == "scraping"
        assert attrs["k"] == "v"
        assert "correlation_id" in attrs

    def test_span_without_phase(self):
        ts, span = _make_enabled_system()
        with ts.span("op2") as s:
            assert s is span
        assert "phase" not in span.last_attributes

    def test_span_records_exception_and_reraises(self):
        ts, span = _make_enabled_system()
        with pytest.raises(ValueError), ts.span("op"):
            raise ValueError("boom")
        span.record_exception.assert_called_once()

    def test_span_swallows_recording_failure(self):
        ts, span = _make_enabled_system()
        span.record_exception.side_effect = RuntimeError("recorder down")
        # Original exception still propagates even if recording fails.
        with pytest.raises(ValueError), ts.span("op"):
            raise ValueError("boom")


class TestEnabledAsyncSpan:
    @pytest.mark.asyncio
    async def test_async_span_yields_real_span(self):
        ts, span = _make_enabled_system()
        async with ts.async_span("aop", phase="generation", attributes={"a": 1}) as s:
            assert s is span
            # correlation id is propagated within the context.
            assert get_async_correlation_id() is not None
        assert span.last_attributes["phase"] == "generation"

    @pytest.mark.asyncio
    async def test_async_span_records_exception_and_reraises(self):
        ts, span = _make_enabled_system()
        with pytest.raises(KeyError):
            async with ts.async_span("aop"):
                raise KeyError("missing")
        span.record_exception.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_span_resets_correlation_id_after(self):
        ts, _ = _make_enabled_system()
        async with ts.async_span("aop"):
            pass
        # Outside the context the var is reset back to default (None).
        assert get_async_correlation_id() is None


class TestRecordEventAndCost:
    def test_record_event_enabled_adds_event(self, monkeypatch):
        ts, span = _make_enabled_system()
        current = MagicMock()
        current.is_recording.return_value = True
        monkeypatch.setattr(
            tel, "trace", MagicMock(get_current_span=lambda: current), raising=False
        )
        ts.record_event("cache_hit", {"key": "abc"})
        current.add_event.assert_called_once()
        _, kwargs = current.add_event.call_args
        assert kwargs["attributes"]["key"] == "abc"
        assert "correlation_id" in kwargs["attributes"]

    def test_record_event_no_recording_span(self, monkeypatch):
        ts, _ = _make_enabled_system()
        current = MagicMock()
        current.is_recording.return_value = False
        monkeypatch.setattr(
            tel, "trace", MagicMock(get_current_span=lambda: current), raising=False
        )
        ts.record_event("evt")
        current.add_event.assert_not_called()

    def test_record_cost_attaches_attributes(self, monkeypatch):
        ts, span = _make_enabled_system()
        span.is_recording.return_value = True
        monkeypatch.setattr(tel, "trace", MagicMock(get_current_span=lambda: span), raising=False)
        cost = ts.record_cost(
            "gemini-1.5-pro",
            input_tokens=1000,
            output_tokens=500,
            operation="generate",
        )
        assert cost > 0
        span.set_attributes.assert_called_once()
        span.set_attribute.assert_called_with("ai.operation", "generate")

    def test_record_cost_without_operation(self, monkeypatch):
        ts, span = _make_enabled_system()
        span.is_recording.return_value = True
        monkeypatch.setattr(tel, "trace", MagicMock(get_current_span=lambda: span), raising=False)
        cost = ts.record_cost("gemini-1.5-pro", 100, 50)
        assert cost >= 0
        span.set_attribute.assert_not_called()


class TestGetCurrentSpanAndCorrelation:
    def test_get_current_span_enabled_returns_span(self, monkeypatch):
        ts, _ = _make_enabled_system()
        sentinel = MagicMock()
        monkeypatch.setattr(
            tel, "trace", MagicMock(get_current_span=lambda: sentinel), raising=False
        )
        assert ts.get_current_span() is sentinel

    def test_get_current_span_enabled_none_returns_nullspan(self, monkeypatch):
        ts, _ = _make_enabled_system()
        monkeypatch.setattr(tel, "trace", MagicMock(get_current_span=lambda: None), raising=False)
        assert isinstance(ts.get_current_span(), NullSpan)

    def test_correlation_id_prefers_async_context(self):
        ts, _ = _make_enabled_system()
        from primr.utils.telemetry import (
            reset_async_correlation_id,
            set_async_correlation_id,
        )

        token = set_async_correlation_id("async-corr")
        try:
            assert ts._get_correlation_id() == "async-corr"
        finally:
            reset_async_correlation_id(token)

    def test_correlation_id_falls_back_to_observability(self):
        ts, _ = _make_enabled_system()
        cid = ts._get_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) > 0


class TestRecordExceptionHelper:
    def test_record_exception_on_nullspan_noop(self):
        ts, _ = _make_enabled_system()
        # Should return early without raising.
        ts._record_exception_on_span(NullSpan(), ValueError("x"))

    def test_record_exception_on_none_noop(self):
        ts, _ = _make_enabled_system()
        ts._record_exception_on_span(None, ValueError("x"))

    def test_record_exception_sets_attributes(self):
        ts, _ = _make_enabled_system()
        span = MagicMock()
        try:
            raise RuntimeError("kaboom")
        except RuntimeError as e:
            ts._record_exception_on_span(span, e)
        span.record_exception.assert_called_once()
        _, kwargs = span.record_exception.call_args
        assert kwargs["attributes"]["exception.type"] == "RuntimeError"
        assert kwargs["attributes"]["exception.message"] == "kaboom"


class TestShutdown:
    def test_shutdown_calls_provider(self):
        ts, _ = _make_enabled_system()
        provider = MagicMock()
        ts._provider = provider
        ts.shutdown()
        provider.shutdown.assert_called_once()
        assert ts._initialized is False
        assert ts._tracer is None

    def test_shutdown_swallows_provider_error(self):
        ts, _ = _make_enabled_system()
        provider = MagicMock()
        provider.shutdown.side_effect = RuntimeError("flush failed")
        ts._provider = provider
        # Should not raise.
        ts.shutdown()


class TestCreateExporterAndInit:
    def test_create_exporter_returns_none_without_otel(self, monkeypatch):
        monkeypatch.setattr(tel, "_OTEL_AVAILABLE", False)
        ts = TelemetrySystem(TelemetryConfig())
        assert ts._create_exporter() is None

    def test_initialize_tracer_warns_without_otel(self, monkeypatch):
        monkeypatch.setattr(tel, "_OTEL_AVAILABLE", False)
        ts = TelemetrySystem(TelemetryConfig())
        # No tracer set up, returns gracefully.
        ts._initialize_tracer()
        assert ts._tracer is None


class TestCostTrackerExtras:
    def test_get_model_pricing_known(self):
        t = CostTracker()
        pricing = t.get_model_pricing("gemini-1.5-pro")
        assert pricing == (1.25, 5.00)

    def test_calculate_cost_warns_unknown(self, caplog):
        t = CostTracker()
        import logging

        with caplog.at_level(logging.WARNING):
            assert t.calculate_cost("nonexistent-model", 1000, 1000) == 0.0
