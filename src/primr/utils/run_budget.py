"""Per-run cost ceiling for the research pipeline (``--budget`` flag).

Activates the existing :class:`~primr.agentic.cost_guard.CostGuardHook` accounting
for standard (non-orchestrated) runs. The CLI sets a budget before
``perform_research`` starts. Supported execution paths sync actual session
spend into it at optional-stage checkpoints and skip those stages once the
ceiling is reached. Required provider tasks that expose no mid-flight spend
state remain pre-flight estimate-gated.

The budget is process-global because a primr process runs one research job at
a time (single-job model).
"""

from __future__ import annotations

import threading
from math import isfinite

from primr.agentic.cost_guard import CostGuardHook
from primr.utils.logging_config import get_logger

logger = get_logger("utils.run_budget")


class RunBudget:
    """A per-run cost ceiling backed by ``CostGuardHook`` accounting.

    The pipeline reports *absolute* session spend (recomputed from token
    counters at each checkpoint), so :meth:`sync_spend` replaces the spent
    total rather than incrementing it.
    """

    def __init__(self, max_cost_usd: float) -> None:
        if not isfinite(max_cost_usd) or max_cost_usd <= 0:
            raise ValueError(f"Run budget must be a finite positive number, got {max_cost_usd}")
        self._hook = CostGuardHook(max_cost_usd=max_cost_usd)

    @property
    def max_cost(self) -> float:
        return self._hook.max_cost

    @property
    def spent(self) -> float:
        return self._hook.spent

    @property
    def remaining(self) -> float:
        return self._hook.remaining

    def sync_spend(self, total_spent_usd: float) -> None:
        """Set the absolute spend observed so far (idempotent per checkpoint).

        Atomic single write: checkpoints run concurrently from strategy vendor
        threads, and a reset-then-record pair could interleave to double the
        recorded spend and falsely skip stages that had headroom.
        """
        self._hook.set_spent(total_spent_usd)

    def exceeded(self) -> bool:
        """True when spend has reached or passed the ceiling."""
        return self.remaining <= 0.0

    def would_exceed(self, estimated_next_cost_usd: float) -> bool:
        """True when spending ``estimated_next_cost_usd`` more would reach or pass the ceiling.

        Uses ``>=`` to stay consistent with ``exceeded()`` (``remaining <= 0``):
        landing exactly on the ceiling counts as exceeded for both.
        """
        return self.spent + max(0.0, estimated_next_cost_usd) >= self.max_cost


_active_budget: RunBudget | None = None
_budget_lock = threading.Lock()


def set_run_budget(max_cost_usd: float) -> RunBudget:
    """Activate a budget for the upcoming run. Returns the budget object."""
    global _active_budget
    budget = RunBudget(max_cost_usd)
    with _budget_lock:
        _active_budget = budget
    logger.info("Run budget set: $%.2f", max_cost_usd)
    return budget


def get_run_budget() -> RunBudget | None:
    """Return the active run budget, or None when no ``--budget`` was given."""
    with _budget_lock:
        return _active_budget


def clear_run_budget() -> None:
    """Deactivate the run budget (call in a finally block after the run)."""
    global _active_budget
    with _budget_lock:
        _active_budget = None


def skip_stage_if_over_budget(spent_usd: float, stage_label: str) -> bool:
    """Sync absolute spend into the active budget and report whether to skip.

    Shared checkpoint for optional, expensive fast-mode stages. Returns True
    (and emits the warn + structured log) when a budget is active and the
    ceiling is reached, so the caller can skip the stage rather than overrun
    ``--budget``.
    """
    budget = get_run_budget()
    if budget is None:
        return False
    budget.sync_spend(spent_usd)
    if not budget.exceeded():
        return False

    from primr.utils.console import console
    from primr.utils.observability import log_structured

    console.warn(
        f"Run budget ${budget.max_cost:.2f} reached "
        f"(~${spent_usd:.2f} spent); skipping {stage_label}"
    )
    log_structured(
        "warning",
        f"Run budget reached; {stage_label} skipped",
        budget_usd=budget.max_cost,
        spent_usd=round(spent_usd, 4),
    )
    return True
