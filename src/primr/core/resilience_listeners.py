"""Resilience and health event listener factories.

Extracted from `primr.core.research_agent` for isolated unit testing.

These factories return single-purpose callbacks suitable for plugging into
`RecoveryExecutor(event_listener=...)` and
`ModelCircuitBreaker(health_listener=...)`. Each callback routes the
incoming event into the per-run JSON state file via the run_state_io
appender helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from primr.core.run_state_io import (
    _append_background_abort,
    _append_model_health_event,
    _append_recovery_event,
)
from primr.utils.observability import log_structured

if TYPE_CHECKING:
    from collections.abc import Callable

    from primr.pipeline.model_breaker import ModelHealthEvent


def _build_resilience_event_listener(folder_path: str) -> Callable[[Any], None]:
    """Build an event listener callback that routes recovery events to run state."""
    from primr.pipeline.executor import BackgroundAbort, RecoveryEvent

    def _listener(event: Any) -> None:
        if isinstance(event, RecoveryEvent):
            _append_recovery_event(folder_path, event.to_dict())
        elif isinstance(event, BackgroundAbort):
            _append_background_abort(folder_path, event.to_dict())

    return _listener


def _build_health_listener(folder_path: str) -> Callable[[Any], None]:
    """Build a health listener callback that logs ModelHealthEvents to run state."""

    def _listener(event: ModelHealthEvent) -> None:
        _append_model_health_event(folder_path, event.to_dict())
        log_structured(
            "info",
            "Model health transition",
            model=event.model,
            from_state=event.from_state,
            to_state=event.to_state,
            failure_count=event.failure_count,
        )

    return _listener
