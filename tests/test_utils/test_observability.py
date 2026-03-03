"""
Tests for observability utilities.

Includes property-based tests using Hypothesis for comprehensive validation.
"""

import time
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.utils.observability import (
    Metrics,
    OperationContext,
    emit_metrics,
    get_correlation_id,
    operation_context,
    timed,
    tracked_operation,
)

# =============================================================================
# UNIT TESTS - Correlation ID
# =============================================================================

class TestCorrelationId:
    """Tests for correlation ID management."""

    def test_generates_id(self):
        """Should generate a correlation ID."""
        cid = get_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 8

    def test_id_within_context(self):
        """Should return context's correlation ID when in context."""
        with operation_context("test") as ctx:
            cid = get_correlation_id()
            assert cid == ctx.correlation_id


# =============================================================================
# UNIT TESTS - OperationContext
# =============================================================================

class TestOperationContext:
    """Tests for OperationContext dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        ctx = OperationContext()
        assert len(ctx.correlation_id) == 8
        assert ctx.operation == ""  # Uses property alias
        assert ctx.operation_name == ""
        assert ctx.metadata == {}

    def test_custom_values(self):
        """Should accept custom values."""
        ctx = OperationContext(
            correlation_id="abc12345",
            operation_name="test_op",
            metadata={"key": "value"}
        )
        assert ctx.correlation_id == "abc12345"
        assert ctx.operation == "test_op"  # Uses property alias
        assert ctx.operation_name == "test_op"
        assert ctx.metadata == {"key": "value"}

    def test_duration_calculation(self):
        """Should calculate duration correctly."""
        ctx = OperationContext()
        time.sleep(0.1)
        assert ctx.duration_seconds >= 0.1


# =============================================================================
# UNIT TESTS - operation_context
# =============================================================================

class TestOperationContextManager:
    """Tests for operation_context context manager."""

    def test_yields_context(self):
        """Should yield OperationContext."""
        with operation_context("test") as ctx:
            assert isinstance(ctx, OperationContext)
            assert ctx.operation == "test"  # Uses property alias
            assert ctx.operation_name == "test"

    def test_includes_metadata(self):
        """Should include metadata in context."""
        with operation_context("test", company="Acme Corp", mode="full") as ctx:
            assert ctx.metadata == {"company": "Acme Corp", "mode": "full"}

    def test_logs_entry_and_exit(self):
        """Should log entry and exit."""
        with patch("primr.utils.observability.logger") as mock_logger:
            with operation_context("test_op"):
                pass

            # Should have logged entry and exit
            assert mock_logger.debug.call_count >= 2

    def test_logs_error_on_exception(self):
        """Should log error when exception occurs."""
        with patch("primr.utils.observability.logger") as mock_logger:
            try:
                with operation_context("test_op"):
                    raise ValueError("test error")
            except ValueError:
                pass

            mock_logger.error.assert_called_once()

    def test_propagates_exception(self):
        """Should propagate exceptions."""
        with pytest.raises(ValueError, match="test error"), operation_context("test"):
            raise ValueError("test error")


# =============================================================================
# UNIT TESTS - timed decorator
# =============================================================================

class TestTimedDecorator:
    """Tests for timed decorator."""

    def test_returns_result(self):
        """Should return function result."""
        @timed
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_logs_timing(self):
        """Should log entry and exit with timing."""
        @timed
        def slow_func():
            time.sleep(0.05)
            return "done"

        with patch("primr.utils.observability.logger") as mock_logger:
            result = slow_func()
            assert result == "done"
            assert mock_logger.debug.call_count >= 2

    def test_propagates_exception(self):
        """Should propagate exceptions."""
        @timed
        def failing_func():
            raise ValueError("error")

        with pytest.raises(ValueError):
            failing_func()

    def test_preserves_function_metadata(self):
        """Should preserve function name and docstring."""
        @timed
        def documented_func():
            """This is a docstring."""

        assert documented_func.__name__ == "documented_func"
        assert "docstring" in documented_func.__doc__


# =============================================================================
# UNIT TESTS - Metrics
# =============================================================================

class TestMetrics:
    """Tests for Metrics dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        metrics = Metrics(
            operation="test",
            duration_seconds=1.5,
            success=True
        )
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
        assert metrics.cost_usd == 0.0
        assert metrics.error_type is None

    def test_to_dict(self):
        """Should convert to dictionary."""
        metrics = Metrics(
            operation="test",
            duration_seconds=1.5,
            success=True,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01
        )
        d = metrics.to_dict()
        assert d["operation"] == "test"
        assert d["duration_seconds"] == 1.5
        assert d["success"] is True
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert "correlation_id" in d
        assert "timestamp" in d


class TestEmitMetrics:
    """Tests for emit_metrics function."""

    def test_logs_metrics(self):
        """Should log metrics as JSON."""
        metrics = Metrics(
            operation="test",
            duration_seconds=1.0,
            success=True
        )

        with patch("primr.utils.observability.logger") as mock_logger:
            emit_metrics(metrics)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            assert "METRICS:" in call_args
            assert "test" in call_args


class TestTrackedOperation:
    """Tests for tracked_operation context manager."""

    def test_emits_metrics_on_success(self):
        """Should emit metrics on successful completion."""
        with patch("primr.utils.observability.emit_metrics") as mock_emit:
            with tracked_operation("test_op"):
                pass

            mock_emit.assert_called_once()
            metrics = mock_emit.call_args[0][0]
            assert metrics.operation == "test_op"
            assert metrics.success is True

    def test_emits_metrics_on_failure(self):
        """Should emit metrics on failure."""
        with patch("primr.utils.observability.emit_metrics") as mock_emit:
            try:
                with tracked_operation("test_op"):
                    raise ValueError("error")
            except ValueError:
                pass

            mock_emit.assert_called_once()
            metrics = mock_emit.call_args[0][0]
            assert metrics.success is False
            assert metrics.error_type == "ValueError"

    def test_captures_tracker_values(self):
        """Should capture values set in tracker."""
        with patch("primr.utils.observability.emit_metrics") as mock_emit:
            with tracked_operation("test_op") as tracker:
                tracker["input_tokens"] = 100
                tracker["output_tokens"] = 50
                tracker["cost_usd"] = 0.01

            metrics = mock_emit.call_args[0][0]
            assert metrics.input_tokens == 100
            assert metrics.output_tokens == 50
            assert metrics.cost_usd == 0.01


# =============================================================================
# PROPERTY-BASED TESTS
# =============================================================================

class TestOperationLoggingCompletenessProperty:
    """
    Property-based tests for operation logging completeness.
    
    **Feature: code-quality-hardening, Property 10: Operation Logging Completeness**
    **Validates: Requirements 5.1, 5.2**
    
    For any operation executed within an operation_context, the logs SHALL
    contain entry, exit, duration, and correlation ID.
    """

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_context_always_has_correlation_id(self, operation_name: str):
        """Every operation context should have a correlation ID."""
        with operation_context(operation_name) as ctx:
            assert ctx.correlation_id is not None
            assert len(ctx.correlation_id) == 8

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_context_tracks_duration(self, operation_name: str):
        """Every operation context should track duration."""
        with operation_context(operation_name) as ctx:
            time.sleep(0.01)
            assert ctx.duration_seconds >= 0.01

    @given(
        st.text(alphabet="abcdefghij", min_size=1, max_size=10),
        st.dictionaries(
            st.text(alphabet="abcde", min_size=1, max_size=5),
            st.text(alphabet="xyz", min_size=1, max_size=5),
            min_size=0,
            max_size=3
        )
    )
    @settings(max_examples=100)
    def test_context_preserves_metadata(self, operation_name: str, metadata: dict):
        """Operation context should preserve all metadata."""
        with operation_context(operation_name, **metadata) as ctx:
            assert ctx.metadata == metadata


class TestMetricsEmissionCompletenessProperty:
    """
    Property-based tests for metrics emission completeness.
    
    **Feature: code-quality-hardening, Property 11: Metrics Emission Completeness**
    **Validates: Requirements 5.3, 5.5**
    
    For any completed research operation, the emitted metrics SHALL contain
    duration, token counts, cost, and success status.
    """

    @given(
        st.text(alphabet="abcdefghij", min_size=1, max_size=10),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.integers(min_value=0, max_value=10000),
        st.integers(min_value=0, max_value=10000),
        st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_metrics_contains_all_required_fields(
        self,
        operation: str,
        duration: float,
        success: bool,
        input_tokens: int,
        output_tokens: int,
        cost: float
    ):
        """Metrics should contain all required fields."""
        metrics = Metrics(
            operation=operation,
            duration_seconds=duration,
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost
        )

        d = metrics.to_dict()

        # All required fields present
        assert "operation" in d
        assert "duration_seconds" in d
        assert "success" in d
        assert "input_tokens" in d
        assert "output_tokens" in d
        assert "cost_usd" in d
        assert "correlation_id" in d
        assert "timestamp" in d

        # Values match
        assert d["operation"] == operation
        assert d["success"] == success
        assert d["input_tokens"] == input_tokens
        assert d["output_tokens"] == output_tokens

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_tracked_operation_always_emits_metrics(self, operation_name: str):
        """tracked_operation should always emit metrics."""
        with patch("primr.utils.observability.emit_metrics") as mock_emit:
            with tracked_operation(operation_name):
                pass

            mock_emit.assert_called_once()
            metrics = mock_emit.call_args[0][0]
            assert metrics.operation == operation_name
            assert metrics.duration_seconds >= 0
            assert isinstance(metrics.success, bool)


# =============================================================================
# TESTS FOR NEW OBSERVABILITY FEATURES
# =============================================================================

from primr.utils.observability import (
    APICallLog,
    CorrelationContext,
    JobSummary,
    correlation_scope,
    get_current_context,
    is_json_output_mode,
    log_job_summary,
    log_structured,
    set_json_output_mode,
)


class TestCorrelationContext:
    """Tests for CorrelationContext dataclass."""

    def test_create_generates_id(self):
        """Should generate correlation ID on create."""
        ctx = CorrelationContext.create("test_op")
        assert len(ctx.correlation_id) == 8
        assert ctx.operation_name == "test_op"

    def test_create_with_metadata(self):
        """Should store metadata on create."""
        ctx = CorrelationContext.create("test_op", company="Acme Corp", mode="deep")
        assert ctx.metadata == {"company": "Acme Corp", "mode": "deep"}

    def test_duration_calculation(self):
        """Should calculate duration correctly."""
        ctx = CorrelationContext.create("test")
        time.sleep(0.05)
        assert ctx.duration_seconds >= 0.05

    def test_start_datetime(self):
        """Should provide start time as datetime."""
        ctx = CorrelationContext.create("test")
        assert ctx.start_datetime is not None
        from datetime import datetime
        assert isinstance(ctx.start_datetime, datetime)


class TestCorrelationScope:
    """Tests for correlation_scope context manager."""

    def test_yields_context(self):
        """Should yield CorrelationContext."""
        with correlation_scope("test") as ctx:
            assert isinstance(ctx, CorrelationContext)
            assert ctx.operation_name == "test"

    def test_sets_thread_local_context(self):
        """Should set context in thread-local storage."""
        with correlation_scope("test") as ctx:
            current = get_current_context()
            assert current is ctx
            assert get_correlation_id() == ctx.correlation_id

    def test_restores_previous_context(self):
        """Should restore previous context on exit."""
        with correlation_scope("outer") as outer:
            with correlation_scope("inner") as inner:
                assert get_correlation_id() == inner.correlation_id
            assert get_correlation_id() == outer.correlation_id

    def test_propagates_exception(self):
        """Should propagate exceptions."""
        with pytest.raises(ValueError, match="test error"), correlation_scope("test"):
            raise ValueError("test error")


class TestLogStructured:
    """Tests for log_structured function."""

    def test_logs_with_correlation_id(self):
        """Should include correlation ID in log."""
        with patch("primr.utils.observability.logger") as mock_logger:
            with correlation_scope("test") as ctx:
                log_structured("info", "Test message", key="value")

            # Check that info was called with correlation ID
            calls = mock_logger.info.call_args_list
            assert any(ctx.correlation_id in str(call) for call in calls)

    def test_logs_with_fields(self):
        """Should include fields in log message."""
        with patch("primr.utils.observability.logger") as mock_logger:
            log_structured("info", "Test message", status=200, duration=1.5)

            call_args = mock_logger.info.call_args[0][0]
            assert "status=200" in call_args
            assert "duration=1.5" in call_args

    def test_json_output_mode(self, capsys):
        """Should output JSON when in JSON mode."""
        import json

        set_json_output_mode(True)
        try:
            log_structured("info", "Test message", key="value")
            captured = capsys.readouterr()
            data = json.loads(captured.out.strip())
            assert data["message"] == "Test message"
            assert data["key"] == "value"
            assert "correlation_id" in data
            assert "timestamp" in data
        finally:
            set_json_output_mode(False)

    def test_json_mode_toggle(self):
        """Should toggle JSON mode correctly."""
        assert not is_json_output_mode()
        set_json_output_mode(True)
        assert is_json_output_mode()
        set_json_output_mode(False)
        assert not is_json_output_mode()


class TestAPICallLog:
    """Tests for APICallLog dataclass."""

    def test_create_with_current_context(self):
        """Should use current correlation ID."""
        with correlation_scope("test") as ctx:
            log = APICallLog.create(
                operation="api_call",
                request_params={"model": "gemini"},
                response_status=200,
                duration_ms=150.5,
            )
            assert log.correlation_id == ctx.correlation_id

    def test_to_dict(self):
        """Should convert to dictionary."""
        log = APICallLog(
            correlation_id="abc12345",
            timestamp="2025-01-01T00:00:00",
            operation="test_api",
            request_params={"key": "value"},
            response_status=200,
            duration_ms=100.5,
            tokens_used=500,
        )
        d = log.to_dict()
        assert d["correlation_id"] == "abc12345"
        assert d["operation"] == "test_api"
        assert d["response_status"] == 200
        assert d["duration_ms"] == 100.5
        assert d["tokens_used"] == 500

    def test_has_required_fields(self):
        """Should validate required fields."""
        log = APICallLog.create(
            operation="test",
            request_params={"key": "value"},
            response_status=200,
            duration_ms=100,
        )
        assert log.has_required_fields()

    def test_missing_required_fields(self):
        """Should detect missing required fields."""
        log = APICallLog(
            correlation_id="",  # Empty
            timestamp="",
            operation="test",
            request_params={},
            response_status=200,
            duration_ms=100,
        )
        assert not log.has_required_fields()


class TestJobSummary:
    """Tests for JobSummary dataclass."""

    def test_create_with_defaults(self):
        """Should create with sensible defaults."""
        summary = JobSummary.create(
            company="Acme Corp",
            mode="deep",
            duration_seconds=120.5,
        )
        assert summary.company == "Acme Corp"
        assert summary.mode == "deep"
        assert summary.api_calls == 0
        assert summary.total_tokens == 0
        assert summary.errors == []
        assert summary.warnings == []

    def test_success_property(self):
        """Should report success based on errors."""
        summary_ok = JobSummary.create("Acme Corp", "deep", 100)
        assert summary_ok.success

        summary_err = JobSummary.create("Acme Corp", "deep", 100, errors=["Error 1"])
        assert not summary_err.success

    def test_to_dict(self):
        """Should convert to dictionary."""
        summary = JobSummary.create(
            company="Acme Corp",
            mode="deep",
            duration_seconds=120.5,
            api_calls=15,
            total_tokens=50000,
            sections_generated=8,
            errors=["Error 1"],
            warnings=["Warning 1"],
            output_path="/path/to/report.md",
        )
        d = summary.to_dict()
        assert d["company"] == "Acme Corp"
        assert d["mode"] == "deep"
        assert d["api_calls"] == 15
        assert d["total_tokens"] == 50000
        assert d["sections_generated"] == 8
        assert d["error_count"] == 1
        assert d["warning_count"] == 1
        assert d["output_path"] == "/path/to/report.md"

    def test_log_job_summary(self):
        """Should log job summary."""
        summary = JobSummary.create("Acme Corp", "deep", 100)
        with patch("primr.utils.observability.log_structured") as mock_log:
            log_job_summary(summary)
            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert call_args[0][0] == "info"
            assert "Acme Corp" in call_args[0][1]


# =============================================================================
# PROPERTY-BASED TESTS FOR API LOG COMPLETENESS
# =============================================================================


class TestAPILogCompletenessProperty:
    """
    Property-based tests for API log completeness.

    **Feature: primr-excellence, Property 17: API Log Completeness**
    **Validates: Requirements 8.2**

    For any API call, the log entry SHALL contain:
    - correlation_id
    - request params
    - response status
    - duration
    """

    @given(
        operation=st.text(alphabet="abcdefghij", min_size=1, max_size=20),
        status=st.integers(min_value=100, max_value=599),
        duration_ms=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False),
    )
    @settings(max_examples=100)
    def test_api_log_always_has_required_fields(
        self, operation: str, status: int, duration_ms: float
    ):
        """API call log should always have required fields."""
        log = APICallLog.create(
            operation=operation,
            request_params={"test": "value"},
            response_status=status,
            duration_ms=duration_ms,
        )

        assert log.has_required_fields()
        assert log.correlation_id  # Non-empty
        assert log.request_params is not None
        assert log.response_status == status
        assert log.duration_ms == duration_ms

    @given(
        st.dictionaries(
            st.text(alphabet="abcde", min_size=1, max_size=5),
            st.one_of(st.text(max_size=10), st.integers(), st.booleans()),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_api_log_preserves_request_params(self, params: dict):
        """API call log should preserve all request params."""
        log = APICallLog.create(
            operation="test",
            request_params=params,
            response_status=200,
            duration_ms=100,
        )

        assert log.request_params == params
        d = log.to_dict()
        assert d["request_params"] == params

    @given(
        st.one_of(
            st.integers(min_value=100, max_value=599),
            st.sampled_from(["ok", "error", "timeout", "rate_limited"]),
        )
    )
    @settings(max_examples=100)
    def test_api_log_accepts_various_status_types(self, status):
        """API call log should accept int or string status."""
        log = APICallLog.create(
            operation="test",
            request_params={},
            response_status=status,
            duration_ms=100,
        )

        assert log.response_status == status
        assert log.has_required_fields()

    @given(st.text(alphabet="abcdefghij", min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_api_log_within_correlation_scope(self, operation: str):
        """API log should use correlation ID from scope."""
        with correlation_scope("parent_op") as ctx:
            log = APICallLog.create(
                operation=operation,
                request_params={},
                response_status=200,
                duration_ms=100,
            )

            assert log.correlation_id == ctx.correlation_id


class TestJobSummaryProperty:
    """
    Property-based tests for job summary logging.

    **Feature: primr-excellence, Task 4.4: Job Summary Logging**
    **Validates: Requirements 8.4**
    """

    @given(
        company=st.text(alphabet="abcdefghij", min_size=1, max_size=20),
        mode=st.sampled_from(["scrape", "deep", "hybrid"]),
        duration=st.floats(min_value=0.0, max_value=3600.0, allow_nan=False),
        api_calls=st.integers(min_value=0, max_value=1000),
        tokens=st.integers(min_value=0, max_value=1000000),
        sections=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_job_summary_contains_all_fields(
        self,
        company: str,
        mode: str,
        duration: float,
        api_calls: int,
        tokens: int,
        sections: int,
    ):
        """Job summary should contain all required fields."""
        summary = JobSummary.create(
            company=company,
            mode=mode,
            duration_seconds=duration,
            api_calls=api_calls,
            total_tokens=tokens,
            sections_generated=sections,
        )

        d = summary.to_dict()
        assert d["company"] == company
        assert d["mode"] == mode
        assert d["api_calls"] == api_calls
        assert d["total_tokens"] == tokens
        assert d["sections_generated"] == sections
        assert "correlation_id" in d
        assert "timestamp" in d

    @given(
        st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5),
        st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_job_summary_success_based_on_errors(
        self, errors: list[str], warnings: list[str]
    ):
        """Job summary success should be based on error count."""
        summary = JobSummary.create(
            company="Test",
            mode="deep",
            duration_seconds=100,
            errors=errors,
            warnings=warnings,
        )

        if errors:
            assert not summary.success
        else:
            assert summary.success

        # Warnings don't affect success
        d = summary.to_dict()
        if warnings:
            assert d["warning_count"] == len(warnings)
