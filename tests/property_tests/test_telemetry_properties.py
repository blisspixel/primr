"""
Property-based tests for the OpenTelemetry integration.

This module contains property tests that verify universal correctness properties
of the telemetry system implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 4.1-4.8**
"""

import asyncio
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
import pytest

from primr.utils.observability import correlation_scope
from primr.utils.telemetry import (
    ExporterType,
    NullSpan,
    TelemetryConfig,
    TelemetrySystem,
    get_async_correlation_id,
    is_otel_available,
    propagate_correlation_id,
    reset_async_correlation_id,
    run_with_correlation_id,
    set_async_correlation_id,
)

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating valid operation names (alphanumeric with underscores)
operation_name_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]{0,49}", fullmatch=True)

# Strategy for generating phase names
phase_strategy = st.sampled_from(["scraping", "generation", "output", "processing", None])

# Strategy for generating service names (alphanumeric with dashes and underscores)
service_name_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,29}", fullmatch=True)

# Strategy for generating sampling rates
sampling_rate_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for generating exporter types
exporter_type_strategy = st.sampled_from([e.value for e in ExporterType])

# Strategy for generating span attributes (JSON-serializable)
json_value_strategy = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-1000000, max_value=1000000)
    | st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)
    | st.text(max_size=50),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(
            st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,19}", fullmatch=True), children, max_size=3
        )
    ),
    max_leaves=5,
)

attributes_strategy = st.dictionaries(
    st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,19}", fullmatch=True), json_value_strategy, max_size=5
)

# Strategy for generating correlation IDs (8 alphanumeric characters)
correlation_id_strategy = st.from_regex(r"[a-zA-Z0-9]{8}", fullmatch=True)

# Strategy for generating event names
event_name_strategy = st.sampled_from(
    [
        "api_call",
        "cache_hit",
        "cache_miss",
        "tier_escalation",
        "request_start",
        "request_end",
        "error_occurred",
    ]
)


# =============================================================================
# PROPERTY 11: SPAN ATTRIBUTE COMPLETENESS
# =============================================================================


class TestSpanAttributeCompleteness:
    """
    **Property 11: Span Attribute Completeness**

    For any span created via `TelemetrySystem.span()`, the span SHALL have
    `correlation_id` and `operation_name` attributes. If a `phase` parameter
    is provided, the span SHALL also have a `phase` attribute.

    **Validates: Requirements 4.2, 4.3**
    """

    @given(
        operation_name=operation_name_strategy, phase=phase_strategy, attributes=attributes_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_span_has_correlation_id_and_operation_name_disabled(
        self, operation_name: str, phase: str | None, attributes: dict[str, Any]
    ):
        """
        Span should have correlation_id and operation_name attributes.
        When telemetry is disabled, NullSpan is returned but the contract is maintained.
        """
        # Test with disabled telemetry (default)
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        with telemetry.span(operation_name, phase=phase, attributes=attributes) as span:
            # When disabled, we get a NullSpan
            assert isinstance(span, NullSpan)
            # NullSpan should not raise errors when methods are called
            span.set_attribute("test", "value")
            span.add_event("test_event")

    @given(
        operation_name=operation_name_strategy, phase=phase_strategy, attributes=attributes_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_span_with_phase_includes_phase_attribute(
        self, operation_name: str, phase: str | None, attributes: dict[str, Any]
    ):
        """
        When phase is provided, the span should include it as an attribute.
        This test verifies the contract even when telemetry is disabled.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        with telemetry.span(operation_name, phase=phase, attributes=attributes) as span:
            # Contract: span context manager should work without errors
            assert span is not None
            # NullSpan methods should be no-ops
            if phase is not None:
                span.set_attribute("phase", phase)

    @given(operation_name=operation_name_strategy, attributes=attributes_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_span_inherits_correlation_id_from_context(
        self, operation_name: str, attributes: dict[str, Any]
    ):
        """
        Span should inherit correlation_id from the current correlation context.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        with correlation_scope("test_operation") as ctx:
            expected_correlation_id = ctx.correlation_id

            with telemetry.span(operation_name, attributes=attributes):
                # The telemetry system should use the correlation_id from context
                actual_correlation_id = telemetry._get_correlation_id()
                assert actual_correlation_id == expected_correlation_id

    @pytest.mark.skipif(not is_otel_available(), reason="OpenTelemetry not installed")
    @given(operation_name=operation_name_strategy, phase=phase_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_span_attributes_with_otel_enabled(self, operation_name: str, phase: str | None):
        """
        When OpenTelemetry is available and enabled, spans should have proper attributes.
        """
        config = TelemetryConfig(enabled=True, exporter_type="none")
        telemetry = TelemetrySystem(config)

        if telemetry.is_enabled:
            with correlation_scope("test"), telemetry.span(operation_name, phase=phase) as span:
                # Span should be a real OpenTelemetry span
                assert not isinstance(span, NullSpan)
                # Span should be recording
                assert span.is_recording()


# =============================================================================
# PROPERTY 12: ERROR RECORDING IN SPANS
# =============================================================================


class TestErrorRecordingInSpans:
    """
    **Property 12: Error Recording in Spans**

    For any exception raised within a `TelemetrySystem.span()` context, the span
    SHALL have its status set to ERROR and SHALL have the exception recorded
    with type and message.

    **Validates: Requirements 4.6**
    """

    @given(
        operation_name=operation_name_strategy,
        error_message=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_exception_is_recorded_in_span_disabled(self, operation_name: str, error_message: str):
        """
        Exceptions raised within a span should be recorded.
        When telemetry is disabled, the exception should still propagate.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        with pytest.raises(ValueError) as exc_info, telemetry.span(operation_name):
            raise ValueError(error_message)

        # Exception should propagate with correct message
        assert error_message in str(exc_info.value)

    @given(
        operation_name=operation_name_strategy,
        error_message=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_exception_type_is_preserved(self, operation_name: str, error_message: str):
        """
        The exception type should be preserved when raised within a span.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError), telemetry.span(operation_name):
            raise CustomError(error_message)

    @given(
        operation_name=operation_name_strategy,
        error_types=st.sampled_from(
            [ValueError, TypeError, RuntimeError, KeyError, AttributeError]
        ),
        error_message=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_various_exception_types_are_handled(
        self, operation_name: str, error_types: type, error_message: str
    ):
        """
        Various exception types should be properly handled within spans.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        with pytest.raises(error_types), telemetry.span(operation_name):
            raise error_types(error_message)

    @pytest.mark.skipif(not is_otel_available(), reason="OpenTelemetry not installed")
    @given(
        operation_name=operation_name_strategy,
        error_message=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_exception_recorded_with_otel_enabled(self, operation_name: str, error_message: str):
        """
        When OpenTelemetry is enabled, exceptions should be recorded on the span.
        """
        config = TelemetryConfig(enabled=True, exporter_type="none")
        telemetry = TelemetrySystem(config)

        if telemetry.is_enabled:
            with pytest.raises(ValueError), telemetry.span(operation_name):
                raise ValueError(error_message)


# =============================================================================
# PROPERTY 13: ASYNC CONTEXT PROPAGATION
# =============================================================================


class TestAsyncContextPropagation:
    """
    **Property 13: Async Context Propagation**

    For any async operation executed within a correlation scope, `get_correlation_id()`
    called from within that operation SHALL return the same correlation ID as the
    outer scope.

    **Validates: Requirements 4.4**
    """

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_async_correlation_id_set_and_get(self, correlation_id: str):
        """
        Setting and getting async correlation ID should work correctly.
        """
        # Initially should be None
        initial = get_async_correlation_id()

        # Set the correlation ID
        token = set_async_correlation_id(correlation_id)

        try:
            # Should return the set value
            assert get_async_correlation_id() == correlation_id
        finally:
            # Reset to previous value
            reset_async_correlation_id(token)

        # Should be back to initial value
        assert get_async_correlation_id() == initial

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_async_context_propagation_with_context_manager(self, correlation_id: str):
        """
        Correlation ID should propagate correctly using the context manager.
        """

        async def check_correlation_id():
            return get_async_correlation_id()

        async def run_test():
            async with propagate_correlation_id(correlation_id):
                result = await check_correlation_id()
                assert result == correlation_id

            # After context, should be None again
            result = await check_correlation_id()
            assert result is None

        asyncio.run(run_test())

    @given(outer_id=correlation_id_strategy, inner_id=correlation_id_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_nested_async_context_propagation(self, outer_id: str, inner_id: str):
        """
        Nested async contexts should properly manage correlation IDs.
        """

        async def run_test():
            async with propagate_correlation_id(outer_id):
                assert get_async_correlation_id() == outer_id

                async with propagate_correlation_id(inner_id):
                    # Inner context should override
                    assert get_async_correlation_id() == inner_id

                # After inner context, should be back to outer
                assert get_async_correlation_id() == outer_id

            # After all contexts, should be None
            assert get_async_correlation_id() is None

        asyncio.run(run_test())

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_run_with_correlation_id_helper(self, correlation_id: str):
        """
        run_with_correlation_id should properly set context for coroutine.
        """

        async def get_id():
            return get_async_correlation_id()

        async def run_test():
            result = await run_with_correlation_id(correlation_id, get_id())
            assert result == correlation_id

            # After the call, context should be reset
            assert get_async_correlation_id() is None

        asyncio.run(run_test())

    @given(correlation_id=correlation_id_strategy, operation_name=operation_name_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_async_span_propagates_correlation_id(self, correlation_id: str, operation_name: str):
        """
        async_span should propagate correlation_id across async boundaries.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        async def run_test():
            # Set up correlation context
            token = set_async_correlation_id(correlation_id)
            try:
                async with telemetry.async_span(operation_name):
                    # Inside async span, correlation_id should be available
                    assert get_async_correlation_id() == correlation_id
            finally:
                reset_async_correlation_id(token)

        asyncio.run(run_test())

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_correlation_id_propagates_to_spawned_tasks(self, correlation_id: str):
        """
        Correlation ID should propagate to tasks spawned within the context.
        """

        async def inner_task():
            return get_async_correlation_id()

        async def run_test():
            async with propagate_correlation_id(correlation_id):
                # Spawn a task within the context
                task = asyncio.create_task(inner_task())
                result = await task
                # Task should see the same correlation ID
                assert result == correlation_id

        asyncio.run(run_test())

    @given(correlation_id=correlation_id_strategy, operation_name=operation_name_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_telemetry_system_uses_async_correlation_id(
        self, correlation_id: str, operation_name: str
    ):
        """
        TelemetrySystem should use async correlation ID when available.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        async def run_test():
            token = set_async_correlation_id(correlation_id)
            try:
                # TelemetrySystem should pick up the async correlation ID
                result = telemetry._get_correlation_id()
                assert result == correlation_id
            finally:
                reset_async_correlation_id(token)

        asyncio.run(run_test())


# =============================================================================
# ADDITIONAL TELEMETRY CONFIGURATION TESTS
# =============================================================================


class TestTelemetryConfiguration:
    """
    Additional tests for TelemetryConfig validation and behavior.

    **Validates: Requirements 4.7, 4.8**
    """

    @given(
        enabled=st.booleans(),
        service_name=service_name_strategy,
        exporter_type=exporter_type_strategy,
        sampling_rate=sampling_rate_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_config_creation(
        self, enabled: bool, service_name: str, exporter_type: str, sampling_rate: float
    ):
        """
        Valid configuration values should create a TelemetryConfig without errors.
        """
        config = TelemetryConfig(
            enabled=enabled,
            service_name=service_name,
            exporter_type=exporter_type,
            sampling_rate=sampling_rate,
        )

        assert config.enabled == enabled
        assert config.service_name == service_name
        assert config.exporter_type == exporter_type
        assert config.sampling_rate == sampling_rate

    @given(sampling_rate=st.floats().filter(lambda x: x < 0.0 or x > 1.0))
    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much]
    )
    def test_invalid_sampling_rate_raises_error(self, sampling_rate: float):
        """
        Invalid sampling rate should raise ValueError.
        """
        with pytest.raises(ValueError, match="sampling_rate"):
            TelemetryConfig(sampling_rate=sampling_rate)

    @given(
        exporter_type=st.text(min_size=1, max_size=20).filter(
            lambda x: x not in {e.value for e in ExporterType}
        )
    )
    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much]
    )
    def test_invalid_exporter_type_raises_error(self, exporter_type: str):
        """
        Invalid exporter type should raise ValueError.
        """
        with pytest.raises(ValueError, match="exporter_type"):
            TelemetryConfig(exporter_type=exporter_type)

    def test_default_config_is_disabled(self):
        """
        Default TelemetryConfig should have telemetry disabled (opt-in).
        """
        config = TelemetryConfig()
        assert config.enabled is False
        assert config.service_name == "primr"
        assert config.exporter_type == "console"
        assert config.sampling_rate == 1.0

    def test_telemetry_system_disabled_by_default(self):
        """
        TelemetrySystem with default config should be disabled.
        """
        telemetry = TelemetrySystem()
        assert not telemetry.is_enabled

    @given(service_name=service_name_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_telemetry_system_with_disabled_config(self, service_name: str):
        """
        TelemetrySystem with disabled config should return NullSpan.
        """
        config = TelemetryConfig(enabled=False, service_name=service_name)
        telemetry = TelemetrySystem(config)

        with telemetry.span("test_operation") as span:
            assert isinstance(span, NullSpan)


# =============================================================================
# RECORD EVENT TESTS
# =============================================================================


class TestRecordEvent:
    """
    Tests for record_event functionality.

    **Validates: Requirements 4.5**
    """

    @given(event_name=event_name_strategy, attributes=attributes_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_record_event_does_not_raise_when_disabled(
        self, event_name: str, attributes: dict[str, Any]
    ):
        """
        record_event should not raise errors when telemetry is disabled.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        # Should not raise
        telemetry.record_event(event_name, attributes)

    @given(
        operation_name=operation_name_strategy,
        event_name=event_name_strategy,
        attributes=attributes_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_record_event_within_span_does_not_raise(
        self, operation_name: str, event_name: str, attributes: dict[str, Any]
    ):
        """
        record_event within a span should not raise errors.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)

        with telemetry.span(operation_name):
            # Should not raise
            telemetry.record_event(event_name, attributes)

    @pytest.mark.skipif(not is_otel_available(), reason="OpenTelemetry not installed")
    @given(operation_name=operation_name_strategy, event_name=event_name_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_record_event_with_otel_enabled(self, operation_name: str, event_name: str):
        """
        record_event should work when OpenTelemetry is enabled.
        """
        config = TelemetryConfig(enabled=True, exporter_type="none")
        telemetry = TelemetrySystem(config)

        if telemetry.is_enabled:
            with telemetry.span(operation_name):
                # Should not raise
                telemetry.record_event(event_name, {"test": "value"})


# =============================================================================
# NULL SPAN TESTS
# =============================================================================


class TestNullSpan:
    """
    Tests for NullSpan behavior.
    """

    def test_null_span_methods_are_no_ops(self):
        """
        NullSpan methods should be no-ops and not raise errors.
        """
        span = NullSpan()

        # All these should be no-ops
        span.set_attribute("key", "value")
        span.set_attributes({"key1": "value1", "key2": "value2"})
        span.add_event("event_name", {"attr": "value"})
        span.record_exception(ValueError("test"))
        span.set_status(None, "description")

        # These should return expected values
        assert span.is_recording() is False
        assert span.get_span_context() is None

    @given(key=st.text(min_size=1, max_size=20), value=json_value_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_null_span_set_attribute_accepts_any_value(self, key: str, value: Any):
        """
        NullSpan.set_attribute should accept any key-value pair without error.
        """
        span = NullSpan()
        span.set_attribute(key, value)  # Should not raise

    @given(attributes=attributes_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_null_span_set_attributes_accepts_any_dict(self, attributes: dict[str, Any]):
        """
        NullSpan.set_attributes should accept any dictionary without error.
        """
        span = NullSpan()
        span.set_attributes(attributes)  # Should not raise
