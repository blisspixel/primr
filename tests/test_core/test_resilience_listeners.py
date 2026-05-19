"""Unit tests for primr.core.resilience_listeners.

The two factories build callbacks that route resilience events into the
per-run state JSON file. Tests assert routing behavior and verify the
returned callbacks are callables with the right shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from primr.core.resilience_listeners import (
    _build_health_listener,
    _build_resilience_event_listener,
)
from primr.core.run_state_io import _load_run_state


@dataclass
class _FakeRecoveryEvent:
    """Stand-in for pipeline.executor.RecoveryEvent."""

    action: str

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action}


@dataclass
class _FakeBackgroundAbort:
    """Stand-in for pipeline.executor.BackgroundAbort."""

    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"reason": self.reason}


@dataclass
class _FakeModelHealthEvent:
    """Stand-in for pipeline.model_breaker.ModelHealthEvent."""

    model: str
    from_state: str
    to_state: str
    failure_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "failure_count": self.failure_count,
        }


class TestBuildResilienceEventListener:
    def test_returns_callable(self, tmp_path):
        listener = _build_resilience_event_listener(str(tmp_path))
        assert callable(listener)

    def test_recovery_event_routed_to_recovery_array(self, tmp_path):
        # The factory imports RecoveryEvent at call time, so patch BEFORE building.
        with patch(
            "primr.pipeline.executor.RecoveryEvent",
            _FakeRecoveryEvent,
        ):
            listener = _build_resilience_event_listener(str(tmp_path))
            listener(_FakeRecoveryEvent(action="fallback"))

        loaded = _load_run_state(str(tmp_path))
        assert loaded["recovery_events"] == [{"action": "fallback"}]
        assert loaded["background_aborts"] == []

    def test_background_abort_routed_to_aborts_array(self, tmp_path):
        with patch(
            "primr.pipeline.executor.BackgroundAbort",
            _FakeBackgroundAbort,
        ):
            listener = _build_resilience_event_listener(str(tmp_path))
            listener(_FakeBackgroundAbort(reason="timeout"))

        loaded = _load_run_state(str(tmp_path))
        assert loaded["background_aborts"] == [{"reason": "timeout"}]
        assert loaded["recovery_events"] == []

    def test_unknown_event_ignored(self, tmp_path):
        listener = _build_resilience_event_listener(str(tmp_path))
        # Object that matches neither RecoveryEvent nor BackgroundAbort — no-op.
        listener(object())
        # No file was created because no append happened.
        loaded = _load_run_state(str(tmp_path))
        assert loaded == {}


class TestBuildHealthListener:
    def test_returns_callable(self, tmp_path):
        listener = _build_health_listener(str(tmp_path))
        assert callable(listener)

    def test_health_event_appended_and_logged(self, tmp_path):
        listener = _build_health_listener(str(tmp_path))
        event = _FakeModelHealthEvent(
            model="grok-4",
            from_state="healthy",
            to_state="degraded",
            failure_count=3,
        )

        with patch(
            "primr.core.resilience_listeners.log_structured"
        ) as log_mock:
            listener(event)

        loaded = _load_run_state(str(tmp_path))
        assert loaded["model_health"] == [
            {
                "model": "grok-4",
                "from_state": "healthy",
                "to_state": "degraded",
                "failure_count": 3,
            }
        ]
        # The log_structured call carries the per-event fields.
        log_mock.assert_called_once()
        _level_arg, message_arg = log_mock.call_args.args
        assert message_arg == "Model health transition"
        kwargs = log_mock.call_args.kwargs
        assert kwargs["model"] == "grok-4"
        assert kwargs["from_state"] == "healthy"
        assert kwargs["to_state"] == "degraded"
        assert kwargs["failure_count"] == 3
