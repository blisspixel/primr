"""
Recovery executor — orchestrates retry/fallback/skip logic for pipeline stages.

This module provides:
- RecoveryContext dataclass with stage, folder_path, attempt, last_error, budget_stressed
- StageResult dataclass with success, output, actions_taken, skipped, skip_reason
- RecoveryExecutor class that walks recovery hierarchies and dispatches action handlers
- compute_backoff() utility for exponential backoff with jitter
- reduce_queries() helper that reduces query count by at least 50%

The executor is the ONLY component that performs I/O (via the callable).
The recovery table, stage classifier, and circuit breaker are pure data/logic
that the executor consults.

**Feature: pipeline-resilience**
**Validates: Requirements 1.2, 1.4, 9.1-9.4, 10.1-10.3, 15.5, 16.1, 16.2, 16.3**
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import TYPE_CHECKING, Any

from primr.pipeline.errors import ErrorCategory, classify_error, is_rate_limited
from primr.pipeline.recovery import (
    RecoveryActionType,
    RecoveryTable,
    build_default_recovery_table,
)
from primr.pipeline.stages import PipelineStage, is_background

if TYPE_CHECKING:
    from collections.abc import Callable


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class RecoveryContext:
    """Context passed to recovery action handlers and the executor."""

    stage: PipelineStage
    folder_path: str
    attempt: int
    last_error: Exception | None
    budget_stressed: bool


@dataclass
class StageResult:
    """Result of executing a pipeline stage through the recovery executor."""

    success: bool
    output: Any
    actions_taken: list[RecoveryActionType] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def compute_backoff(
    attempt: int,
    base: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    """Compute exponential backoff delay with up to 20% jitter, capped at max_delay.

    The raw delay is ``base * 2^attempt``. A random jitter of 0-20% is added.
    The result is capped at *max_delay*.

    **Validates: Requirements 10.3**
    """
    raw = base * (2**attempt)
    jitter_factor = 1.0 + random.random() * 0.2
    delay = raw * jitter_factor
    return float(min(delay, max_delay))


def reduce_queries(original_count: int) -> int:
    """Reduce query count by at least 50%, minimum 1.

    **Validates: Requirements 3.2**
    """
    if original_count <= 1:
        return 1
    reduced = original_count // 2
    return max(reduced, 1)


# =============================================================================
# ACTION HANDLER TYPE
# =============================================================================

# Action handlers are callables registered per (stage, action_type).
# They receive a RecoveryContext and return Any (the stage output on success).
# They raise on failure so the executor can advance to the next action.
ActionHandlerRegistry = dict[
    tuple[PipelineStage, RecoveryActionType],
    "Callable[[RecoveryContext], Any]",
]


# =============================================================================
# RECOVERY EVENT TYPE
# =============================================================================


@dataclass
class RecoveryEvent:
    """A timestamped recovery event for run state logging."""

    timestamp: str
    stage: str
    action: str
    detail: str
    success: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage."""
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "action": self.action,
            "detail": self.detail,
            "success": self.success,
        }


@dataclass
class BackgroundAbort:
    """A timestamped background abort event for run state logging."""

    timestamp: str
    stage: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage."""
        return {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "reason": self.reason,
        }


# =============================================================================
# RECOVERY EXECUTOR
# =============================================================================


class RecoveryExecutor:
    """Orchestrates retry/fallback/skip logic for a pipeline stage.

    The executor does NOT contain stage-specific recovery logic. Each stage
    provides action handlers as callables registered in *action_handlers*.
    The executor walks the hierarchy and dispatches to the registered handler
    for each action type. If no handler is registered for an action, the
    executor skips that action.

    **Validates: Requirements 1.2, 1.4, 9.1-9.4, 10.1-10.3, 15.5, 16.1-16.3**
    """

    def __init__(
        self,
        recovery_table: RecoveryTable | None = None,
        action_handlers: ActionHandlerRegistry | None = None,
        event_listener: Callable[[RecoveryEvent | BackgroundAbort], None] | None = None,
    ) -> None:
        self._table = recovery_table or build_default_recovery_table()
        self._handlers: ActionHandlerRegistry = action_handlers or {}
        self._event_listener = event_listener

    def _emit_recovery_event(self, event: RecoveryEvent | BackgroundAbort) -> None:
        """Forward a recovery event to the listener callback."""
        if self._event_listener is not None:
            self._event_listener(event)

    def execute(
        self,
        stage: PipelineStage,
        callable_fn: Callable[[], Any],
        context: RecoveryContext | None = None,
    ) -> StageResult:
        """Execute *callable_fn* with recovery logic for *stage*.

        For background stages: aborts immediately on HTTP 429 or budget_stressed.
        For foreground stages: walks the recovery hierarchy from cheapest to most
        expensive action on failure.
        """
        ctx = context or RecoveryContext(
            stage=stage,
            folder_path="",
            attempt=0,
            last_error=None,
            budget_stressed=False,
        )

        # --- Background stage: check budget_stressed BEFORE calling ---
        if is_background(stage) and ctx.budget_stressed:
            return self._abort_background(stage, "budget_stress")

        # --- Try the initial call ---
        try:
            output = callable_fn()
            return StageResult(success=True, output=output)
        except Exception as exc:
            ctx.last_error = exc
            ctx.attempt += 1

            # Classify the error
            category = classify_error(exc)

            # Quota errors abort immediately regardless of stage type
            if category == ErrorCategory.QUOTA:
                raise

            # Configuration errors are non-retryable
            if category == ErrorCategory.CONFIGURATION:
                raise

            # --- Background stage: abort on 429 or budget_stressed ---
            if is_background(stage):
                if is_rate_limited(exc):
                    return self._abort_background(stage, "rate_limit")
                # Background stages get one retry attempt, then skip
                return self._abort_background(
                    stage,
                    f"transient_error: {exc}",
                )

            # --- Foreground stage: walk the recovery hierarchy ---
            return self._walk_hierarchy(stage, callable_fn, ctx)

    def _abort_background(
        self,
        stage: PipelineStage,
        reason: str,
    ) -> StageResult:
        """Abort a background stage immediately and log the abort."""
        from datetime import datetime

        abort = BackgroundAbort(
            timestamp=datetime.now().isoformat(),
            stage=stage.value,
            reason=reason,
        )
        self._emit_recovery_event(abort)
        return StageResult(
            success=False,
            output=None,
            skipped=True,
            skip_reason=reason,
        )

    def _walk_hierarchy(
        self,
        stage: PipelineStage,
        callable_fn: Callable[[], Any],
        ctx: RecoveryContext,
    ) -> StageResult:
        """Walk the recovery hierarchy for a foreground stage."""
        from datetime import datetime

        hierarchy = self._table.get_hierarchy(stage)
        actions_taken: list[RecoveryActionType] = []

        for action in hierarchy.actions:
            action_type = action.action_type
            handler = self._handlers.get((stage, action_type))

            if handler is None:
                # No handler registered — skip this action
                actions_taken.append(action_type)
                continue

            try:
                output = handler(ctx)
                # Handler succeeded
                event = RecoveryEvent(
                    timestamp=datetime.now().isoformat(),
                    stage=stage.value,
                    action=action_type.value,
                    detail=action.description,
                    success=True,
                )
                self._emit_recovery_event(event)
                actions_taken.append(action_type)
                return StageResult(
                    success=True,
                    output=output,
                    actions_taken=actions_taken,
                )
            except Exception as handler_exc:
                # Handler failed — log and continue to next action
                event = RecoveryEvent(
                    timestamp=datetime.now().isoformat(),
                    stage=stage.value,
                    action=action_type.value,
                    detail=f"{action.description} — failed: {handler_exc}",
                    success=False,
                )
                self._emit_recovery_event(event)
                actions_taken.append(action_type)
                ctx.last_error = handler_exc
                ctx.attempt += 1

        # All actions exhausted — terminal failure
        return StageResult(
            success=False,
            output=None,
            actions_taken=actions_taken,
            skipped=True,
            skip_reason=f"All recovery actions exhausted for {stage.value}",
        )
