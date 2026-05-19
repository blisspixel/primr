"""Tests for primr.utils.telemetry.

Covers TelemetryConfig validation, NullSpan no-op behavior, the disabled
fast path (which is the only path that runs in CI without
OpenTelemetry installed), async correlation-id propagation, the global
get/init helpers, and the CostTracker pricing math.
"""

from __future__ import annotations

import asyncio

import pytest

from primr.utils.telemetry import (
    CostTracker,
    ExporterType,
    NullSpan,
    TelemetryConfig,
    TelemetrySystem,
    get_async_correlation_id,
    get_telemetry,
    init_telemetry,
    is_otel_available,
    propagate_correlation_id,
    reset_async_correlation_id,
    run_with_correlation_id,
    set_async_correlation_id,
)

# ---------------------------------------------------------------------------
# ExporterType + TelemetryConfig
# ---------------------------------------------------------------------------


class TestExporterType:
    def test_enum_values(self):
        assert ExporterType.CONSOLE.value == "console"
        assert ExporterType.OTLP.value == "otlp"
        assert ExporterType.JAEGER.value == "jaeger"
        assert ExporterType.NONE.value == "none"


class TestTelemetryConfig:
    def test_defaults_disabled(self):
        cfg = TelemetryConfig()
        assert cfg.enabled is False
        assert cfg.service_name == "primr"
        assert cfg.exporter_type == "console"
        assert cfg.sampling_rate == 1.0

    def test_custom_values(self):
        cfg = TelemetryConfig(
            enabled=True,
            service_name="primr-test",
            exporter_type="otlp",
            otlp_endpoint="http://collector:4317",
            sampling_rate=0.5,
        )
        assert cfg.enabled is True
        assert cfg.service_name == "primr-test"
        assert cfg.exporter_type == "otlp"
        assert cfg.sampling_rate == 0.5

    @pytest.mark.parametrize("rate", [-0.1, 1.1, 2.0, -5.0])
    def test_sampling_rate_out_of_range_rejected(self, rate):
        with pytest.raises(ValueError, match="sampling_rate"):
            TelemetryConfig(sampling_rate=rate)

    @pytest.mark.parametrize("rate", [0.0, 0.5, 1.0])
    def test_sampling_rate_in_range_accepted(self, rate):
        # Should not raise
        TelemetryConfig(sampling_rate=rate)

    def test_invalid_exporter_type_rejected(self):
        with pytest.raises(ValueError, match="exporter_type"):
            TelemetryConfig(exporter_type="ghostscript")

    @pytest.mark.parametrize("exporter", ["console", "otlp", "jaeger", "none"])
    def test_valid_exporter_types_accepted(self, exporter):
        TelemetryConfig(exporter_type=exporter)


# ---------------------------------------------------------------------------
# NullSpan
# ---------------------------------------------------------------------------


class TestNullSpan:
    def test_set_attribute_is_noop(self):
        s = NullSpan()
        # Should not raise
        s.set_attribute("k", "v")

    def test_set_attributes_is_noop(self):
        NullSpan().set_attributes({"a": 1, "b": 2})

    def test_add_event_is_noop(self):
        NullSpan().add_event("event", attributes={"x": 1})

    def test_add_event_without_attrs_is_noop(self):
        NullSpan().add_event("event")

    def test_record_exception_is_noop(self):
        NullSpan().record_exception(ValueError("test"))

    def test_record_exception_with_kwargs_is_noop(self):
        NullSpan().record_exception(
            ValueError("test"),
            attributes={"foo": "bar"},
            timestamp=1234567890,
            escaped=True,
        )

    def test_set_status_is_noop(self):
        NullSpan().set_status(None, description="anything")

    def test_is_recording_returns_false(self):
        assert NullSpan().is_recording() is False

    def test_get_span_context_returns_none(self):
        assert NullSpan().get_span_context() is None


# ---------------------------------------------------------------------------
# Async correlation-id propagation
# ---------------------------------------------------------------------------


class TestAsyncCorrelationId:
    def test_get_default_is_none(self):
        # Default ContextVar value
        assert get_async_correlation_id() is None

    def test_set_and_get(self):
        token = set_async_correlation_id("abc123")
        try:
            assert get_async_correlation_id() == "abc123"
        finally:
            reset_async_correlation_id(token)
        assert get_async_correlation_id() is None

    @pytest.mark.asyncio
    async def test_propagate_context_manager(self):
        assert get_async_correlation_id() is None
        async with propagate_correlation_id("ctx-001"):
            assert get_async_correlation_id() == "ctx-001"
        assert get_async_correlation_id() is None

    @pytest.mark.asyncio
    async def test_propagate_resets_on_exception(self):
        try:
            async with propagate_correlation_id("ctx-002"):
                assert get_async_correlation_id() == "ctx-002"
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert get_async_correlation_id() is None

    @pytest.mark.asyncio
    async def test_run_with_correlation_id(self):
        async def _inner() -> str | None:
            return get_async_correlation_id()

        result = await run_with_correlation_id("run-id-1", _inner())
        assert result == "run-id-1"
        # Cleared after the run
        assert get_async_correlation_id() is None


# ---------------------------------------------------------------------------
# TelemetrySystem (disabled-by-default fast path)
# ---------------------------------------------------------------------------


class TestTelemetrySystemDisabled:
    def test_defaults_to_disabled(self):
        ts = TelemetrySystem()
        assert ts.is_enabled is False

    def test_explicit_disabled_config(self):
        ts = TelemetrySystem(TelemetryConfig(enabled=False))
        assert ts.is_enabled is False

    def test_span_returns_null_span_when_disabled(self):
        ts = TelemetrySystem()
        with ts.span("op") as s:
            assert isinstance(s, NullSpan)

    def test_span_with_phase_and_attrs_disabled(self):
        ts = TelemetrySystem()
        with ts.span("op", phase="scraping", attributes={"k": "v"}) as s:
            assert isinstance(s, NullSpan)

    def test_record_event_disabled_is_noop(self):
        ts = TelemetrySystem()
        # Should not raise
        ts.record_event("event", {"k": "v"})
        ts.record_event("event")

    def test_get_current_span_when_disabled(self):
        ts = TelemetrySystem()
        s = ts.get_current_span()
        assert isinstance(s, NullSpan)

    def test_shutdown_is_safe_when_no_provider(self):
        ts = TelemetrySystem()
        # Should not raise even though provider was never created
        ts.shutdown()
        assert ts._tracer is None

    @pytest.mark.asyncio
    async def test_async_span_when_disabled(self):
        ts = TelemetrySystem()
        async with ts.async_span("op", phase="generation") as s:
            assert isinstance(s, NullSpan)

    @pytest.mark.asyncio
    async def test_async_span_propagates_correlation_even_when_disabled(self):
        # Even with telemetry disabled, the async_span helper still pushes
        # a correlation_id into the async context.
        ts = TelemetrySystem()
        async with ts.async_span("op") as _s:
            assert get_async_correlation_id() is not None
        # Cleaned up after
        assert get_async_correlation_id() is None


class TestGlobalHelpers:
    def test_get_telemetry_is_singleton(self):
        a = get_telemetry()
        b = get_telemetry()
        assert a is b

    def test_init_telemetry_replaces_global(self):
        init_telemetry(TelemetryConfig(enabled=False, service_name="x"))
        ts = get_telemetry()
        assert ts.config.service_name == "x"

    def test_is_otel_available_returns_bool(self):
        # We don't care about the value (depends on env); just that it's a bool.
        assert isinstance(is_otel_available(), bool)


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class TestCostTracker:
    def test_default_pricing_includes_legacy_models(self):
        tracker = CostTracker()
        # Legacy entries seeded by _build_default_pricing
        assert tracker.get_model_pricing("gemini-1.5-pro") == (1.25, 5.00)
        assert tracker.get_model_pricing("gemini-1.5-flash") == (0.075, 0.30)
        assert tracker.get_model_pricing("gemini-2.0-flash") == (0.10, 0.40)

    def test_calculate_cost_gemini_pro(self):
        tracker = CostTracker()
        # 1000 input + 500 output @ (1.25, 5.00) per 1M
        # = (1000/1M)*1.25 + (500/1M)*5.00 = 0.00125 + 0.0025 = 0.00375
        cost = tracker.calculate_cost("gemini-1.5-pro", 1000, 500)
        assert cost == pytest.approx(0.00375, rel=1e-6)

    def test_calculate_cost_unknown_model_returns_zero(self):
        tracker = CostTracker()
        assert tracker.calculate_cost("not-a-real-model-xyz", 1_000_000, 1_000_000) == 0.0

    def test_calculate_cost_zero_tokens(self):
        tracker = CostTracker()
        assert tracker.calculate_cost("gemini-1.5-pro", 0, 0) == 0.0

    def test_add_model_pricing(self):
        tracker = CostTracker()
        tracker.add_model_pricing("custom-x", 2.0, 8.0)
        assert tracker.get_model_pricing("custom-x") == (2.0, 8.0)
        # Should now calculate correctly
        cost = tracker.calculate_cost("custom-x", 1_000_000, 1_000_000)
        assert cost == pytest.approx(10.0)

    def test_add_overrides_existing(self):
        tracker = CostTracker()
        tracker.add_model_pricing("gemini-1.5-pro", 99.0, 199.0)
        assert tracker.get_model_pricing("gemini-1.5-pro") == (99.0, 199.0)

    def test_get_supported_models_includes_legacy(self):
        tracker = CostTracker()
        models = tracker.get_supported_models()
        assert "gemini-1.5-pro" in models
        assert "gemini-1.5-flash" in models
        assert "gemini-2.0-flash" in models

    def test_get_model_pricing_unknown_returns_none(self):
        tracker = CostTracker()
        assert tracker.get_model_pricing("not-a-real-model-xyz") is None

    def test_custom_pricing_overrides_defaults(self):
        custom = {"only-model": (3.0, 9.0)}
        tracker = CostTracker(pricing=custom)
        assert tracker.get_model_pricing("only-model") == (3.0, 9.0)
        # gemini-1.5-pro NOT in this custom pricing
        assert tracker.get_model_pricing("gemini-1.5-pro") is None


class TestTelemetryRecordCostDisabled:
    def test_record_cost_when_disabled_still_returns_cost(self):
        ts = TelemetrySystem()  # disabled
        # Should still calculate the cost even though no span gets the attrs
        cost = ts.record_cost(
            model="gemini-1.5-pro",
            input_tokens=1000,
            output_tokens=500,
            operation="test_op",
        )
        assert cost == pytest.approx(0.00375, rel=1e-6)

    def test_record_cost_with_custom_tracker(self):
        ts = TelemetrySystem()
        tracker = CostTracker(pricing={"custom": (1.0, 1.0)})
        cost = ts.record_cost(
            model="custom",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cost_tracker=tracker,
        )
        assert cost == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Smoke: spans with telemetry enabled but OTel unavailable
# ---------------------------------------------------------------------------


class TestEnabledButOtelMissing:
    """If OTel isn't installed, an enabled config should still gracefully
    degrade to NullSpan rather than crash."""

    def test_enabled_without_otel_yields_null_spans(self, monkeypatch):
        # Force the OTel-available flag off regardless of environment.
        import primr.utils.telemetry as tele_mod

        monkeypatch.setattr(tele_mod, "_OTEL_AVAILABLE", False)
        ts = TelemetrySystem(TelemetryConfig(enabled=True))
        # Even though enabled, initialization should bail and is_enabled stays False
        assert ts.is_enabled is False
        with ts.span("op") as s:
            assert isinstance(s, NullSpan)


# ---------------------------------------------------------------------------
# Module sanity (asyncio import warm)
# ---------------------------------------------------------------------------


def test_module_has_asyncio_loop_compatibility():
    """The async helpers should work inside asyncio.run."""

    async def _check():
        async with propagate_correlation_id("smoke"):
            return get_async_correlation_id()

    assert asyncio.run(_check()) == "smoke"
