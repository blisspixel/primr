"""Per-run cost ceiling for the research pipeline (``--budget`` flag).

Activates the existing :class:`~primr.agentic.hooks.CostGuardHook` accounting
for standard (non-orchestrated) runs. The CLI sets a budget before
``perform_research`` starts; the pipeline syncs actual session spend into it
at stage checkpoints and skips optional stages once the ceiling is reached.

The budget is process-global because a primr process runs one research job at
a time (single-job model).
"""

from __future__ import annotations

import threading

from primr.agentic.hooks import CostGuardHook
from primr.utils.logging_config import get_logger

logger = get_logger("utils.run_budget")


class RunBudget:
    """A per-run cost ceiling backed by ``CostGuardHook`` accounting.

    The pipeline reports *absolute* session spend (recomputed from token
    counters at each checkpoint), so :meth:`sync_spend` replaces the spent
    total rather than incrementing it.
    """

    def __init__(self, max_cost_usd: float) -> None:
        if max_cost_usd <= 0:
            raise ValueError(f"Run budget must be positive, got {max_cost_usd}")
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
        """Set the absolute spend observed so far (idempotent per checkpoint)."""
        self._hook.reset()
        self._hook.record_cost(max(0.0, total_spent_usd))

    def exceeded(self) -> bool:
        """True when spend has reached or passed the ceiling."""
        return self.remaining <= 0.0

    def would_exceed(self, estimated_next_cost_usd: float) -> bool:
        """True when spending ``estimated_next_cost_usd`` more would pass the ceiling."""
        return self.spent + max(0.0, estimated_next_cost_usd) > self.max_cost


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
