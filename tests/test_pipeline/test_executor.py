"""
Unit tests for recovery executor behavior.

**Feature: pipeline-resilience**
**Validates: Requirements 9.4, 10.2, 16.1, 16.2, 16.3**
"""

from __future__ import annotations

from typing import Any

import pytest

from primr.pipeline.executor import (
    BackgroundAbort,
    RecoveryContext,
    RecoveryEvent,
    RecoveryExecutor,
    compute_backoff,
    reduce_queries,
)
from primr.pipeline.recovery import RecoveryActionType, build_default_recovery_table
from primr.pipeline.stages import PipelineStage


class TestBackgroundAbortLogging:
    """Test that background stage aborts log the correct reason."""

    def test_rate_limit_abort_logs_reason(self) -> None:
        """Background abort on rate limit logs reason='rate_limit'."""
        events: list[BackgroundAbort | RecoveryEvent] = []
        executor = RecoveryExecutor(event_listener=events.append)

        def raise_429() -> None:
            raise Exception("429 rate limit exceeded")

        ctx = RecoveryContext(
            stage=PipelineStage.CROSS_VALIDATION,
            folder_path="/tmp/test",
            attempt=0,
            last_error=None,
            budget_stressed=False,
        )
        result = executor.execute(PipelineStage.CROSS_VALIDATION, raise_429, ctx)

        assert result.skipped is True
        assert result.skip_reason == "rate_limit"
        assert len(events) == 1
        abort = events[0]
        assert isinstance(abort, BackgroundAbort)
        assert abort.reason == "rate_limit"
        assert abort.stage == "cross_validation"
        assert len(abort.timestamp) > 0

    def test_budget_stress_abort_logs_reason(self) -> None:
        """Background abort on budget stress logs reason='budget_stress'."""
        events: list[BackgroundAbort | RecoveryEvent] = []
        executor = RecoveryExecutor(event_listener=events.append)

        ctx = RecoveryContext(
            stage=PipelineStage.STRATEGY_GENERATION,
            folder_path="/tmp/test",
            attempt=0,
            last_error=None,
            budget_stressed=True,
        )
        result = executor.execute(
            PipelineStage.STRATEGY_GENERATION,
            lambda: None,
            ctx,
        )

        assert result.skipped is True
        assert result.skip_reason == "budget_stress"
        assert len(events) == 1
        abort = events[0]
        assert isinstance(abort, BackgroundAbort)
        assert abort.reason == "budget_stress"
        assert abort.stage == "strategy_generation"


class TestForegroundExhaustionLogging:
    """Test that foreground stage exhaustion logs failure and terminates."""

    def test_exhaustion_logs_all_recovery_events(self) -> None:
        """Foreground exhaustion logs a recovery event for each action attempted."""
        events: list[BackgroundAbort | RecoveryEvent] = []
        table = build_default_recovery_table()
        hierarchy = table.get_hierarchy(PipelineStage.SCRAPING)

        handlers: dict[tuple[PipelineStage, RecoveryActionType], Any] = {}
        for action in hierarchy.actions:
            handlers[(PipelineStage.SCRAPING, action.action_type)] = lambda ctx: (
                _ for _ in ()
            ).throw(Exception("fail"))

        executor = RecoveryExecutor(
            recovery_table=table,
            action_handlers=handlers,
            event_listener=events.append,
        )

        def always_fail() -> None:
            raise Exception("initial fail")

        ctx = RecoveryContext(
            stage=PipelineStage.SCRAPING,
            folder_path="/tmp/test",
            attempt=0,
            last_error=None,
            budget_stressed=False,
        )
        result = executor.execute(PipelineStage.SCRAPING, always_fail, ctx)

        assert result.success is False
        # Should have one recovery event per action in the hierarchy
        recovery_events = [e for e in events if isinstance(e, RecoveryEvent)]
        assert len(recovery_events) == len(hierarchy.actions)
        for event in recovery_events:
            assert event.success is False
            assert event.stage == "scraping"

    def test_exhaustion_result_has_skip_reason(self) -> None:
        """Foreground exhaustion produces a result with a clear skip_reason."""
        table = build_default_recovery_table()
        hierarchy = table.get_hierarchy(PipelineStage.ANALYSIS)

        handlers: dict[tuple[PipelineStage, RecoveryActionType], Any] = {}
        for action in hierarchy.actions:
            handlers[(PipelineStage.ANALYSIS, action.action_type)] = lambda ctx: (
                _ for _ in ()
            ).throw(Exception("fail"))

        executor = RecoveryExecutor(
            recovery_table=table,
            action_handlers=handlers,
        )

        def always_fail() -> None:
            raise Exception("initial fail")

        result = executor.execute(PipelineStage.ANALYSIS, always_fail)

        assert result.success is False
        assert result.skip_reason is not None
        assert "analysis" in result.skip_reason


class TestRecoveryEventsRecording:
    """Test that recovery events are recorded in the expected structure."""

    def test_successful_recovery_logged(self) -> None:
        """A successful recovery action is logged with success=True."""
        events: list[BackgroundAbort | RecoveryEvent] = []
        table = build_default_recovery_table()

        handlers: dict[tuple[PipelineStage, RecoveryActionType], Any] = {
            (PipelineStage.SECTION_WRITING, RecoveryActionType.RETRY_SAME): (
                lambda ctx: "recovered output"
            ),
        }

        executor = RecoveryExecutor(
            recovery_table=table,
            action_handlers=handlers,
            event_listener=events.append,
        )

        def fail_once() -> None:
            raise Exception("transient error 500")

        result = executor.execute(PipelineStage.SECTION_WRITING, fail_once)

        assert result.success is True
        assert result.output == "recovered output"
        recovery_events = [e for e in events if isinstance(e, RecoveryEvent)]
        assert len(recovery_events) == 1
        assert recovery_events[0].success is True
        assert recovery_events[0].stage == "section_writing"
        assert recovery_events[0].action == "retry_same"

    def test_listener_failure_cannot_discard_successful_recovery(self) -> None:
        """Best-effort telemetry cannot change a recovered stage result."""
        calls = 0

        def fail_once() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("transient error")
            return "recovered"

        def unavailable_listener(_event: BackgroundAbort | RecoveryEvent) -> None:
            raise OSError("state persistence unavailable")

        executor = RecoveryExecutor(
            event_listener=unavailable_listener,
            sleep_fn=lambda _delay: None,
        )

        result = executor.execute(PipelineStage.ANALYSIS, fail_once)

        assert result.success is True
        assert result.output == "recovered"
        assert calls == 2

    def test_unavailable_actions_are_not_recorded_as_attempted(self) -> None:
        """The executor reports only recovery actions it actually executes."""
        events: list[BackgroundAbort | RecoveryEvent] = []
        calls = 0

        def always_fail() -> None:
            nonlocal calls
            calls += 1
            raise RuntimeError("transient failure")

        executor = RecoveryExecutor(event_listener=events.append)
        result = executor.execute(PipelineStage.SECTION_WRITING, always_fail)

        assert calls == 2
        assert result.success is False
        assert result.actions_taken == [RecoveryActionType.RETRY_SAME]
        assert len(events) == 1
        assert events[0].action == "retry_same"
        assert events[0].success is False

    def test_builtin_backoff_retry_sleeps_before_reinvocation(self) -> None:
        """Backoff recovery delays once, then invokes the original callable."""
        delays: list[float] = []
        calls = 0

        def fail_once() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("transient failure")
            return "recovered"

        executor = RecoveryExecutor(sleep_fn=delays.append)
        result = executor.execute(PipelineStage.ANALYSIS, fail_once)

        assert result.success is True
        assert result.output == "recovered"
        assert result.actions_taken == [RecoveryActionType.RETRY_BACKOFF]
        assert calls == 2
        assert len(delays) == 1
        assert 1.0 <= delays[0] <= 1.2

    @pytest.mark.parametrize("terminal_error", ["quota exceeded", "invalid API key"])
    def test_builtin_retry_reraises_new_nonretryable_failure(self, terminal_error: str) -> None:
        """A retry cannot downgrade a newly exposed terminal provider failure."""
        calls = 0

        def transient_then_terminal() -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("HTTP 500 from provider")
            raise RuntimeError(terminal_error)

        executor = RecoveryExecutor(sleep_fn=lambda _delay: None)

        with pytest.raises(RuntimeError, match=terminal_error):
            executor.execute(PipelineStage.ANALYSIS, transient_then_terminal)

        assert calls == 2

    def test_recovery_event_to_dict(self) -> None:
        """RecoveryEvent.to_dict() produces the expected structure."""
        event = RecoveryEvent(
            timestamp="2026-02-15T10:30:05",
            stage="analysis",
            action="fallback_model",
            detail="Fell back from grok-4.20 to grok-4.1",
            success=True,
        )
        d = event.to_dict()
        assert d == {
            "timestamp": "2026-02-15T10:30:05",
            "stage": "analysis",
            "action": "fallback_model",
            "detail": "Fell back from grok-4.20 to grok-4.1",
            "success": True,
        }

    def test_background_abort_to_dict(self) -> None:
        """BackgroundAbort.to_dict() produces the expected structure."""
        abort = BackgroundAbort(
            timestamp="2026-02-15T10:31:00",
            stage="strategy_generation",
            reason="rate_limit",
        )
        d = abort.to_dict()
        assert d == {
            "timestamp": "2026-02-15T10:31:00",
            "stage": "strategy_generation",
            "reason": "rate_limit",
        }


class TestSuccessfulExecution:
    """Test that successful calls pass through without recovery."""

    def test_successful_call_returns_output(self) -> None:
        """A successful callable returns StageResult with success=True."""
        executor = RecoveryExecutor()
        result = executor.execute(
            PipelineStage.ANALYSIS,
            lambda: "analysis output",
        )
        assert result.success is True
        assert result.output == "analysis output"
        assert result.skipped is False
        assert len(result.actions_taken) == 0


class TestComputeBackoff:
    """Unit tests for compute_backoff utility."""

    def test_attempt_zero_base_delay(self) -> None:
        """Attempt 0 produces delay in [base, base * 1.2]."""
        delay = compute_backoff(0, base=1.0, max_delay=60.0)
        assert 1.0 <= delay <= 1.2

    def test_capped_at_max_delay(self) -> None:
        """High attempt values are capped at max_delay."""
        delay = compute_backoff(100, base=1.0, max_delay=60.0)
        assert delay <= 60.0


class TestReduceQueries:
    """Unit tests for reduce_queries helper."""

    def test_reduces_10_to_5(self) -> None:
        assert reduce_queries(10) == 5

    def test_reduces_1_to_1(self) -> None:
        assert reduce_queries(1) == 1

    def test_reduces_3_to_1(self) -> None:
        assert reduce_queries(3) == 1

    def test_reduces_100_to_50(self) -> None:
        assert reduce_queries(100) == 50
