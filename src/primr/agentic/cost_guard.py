"""Budget-enforcement hook (extracted from ``primr.agentic.hooks``).

``CostGuardHook`` is the spend-accounting primitive behind both the agentic
hook system (registered as a PreToolUse guard) and the ``--budget`` per-run
ceiling (``primr.utils.run_budget`` wraps one for absolute-spend
checkpoints). It lives in its own module so the hook framework file stays
under its architecture ceiling; the behavior is unchanged.
"""

from __future__ import annotations

import logging
import threading

from primr.agentic.hooks import Hook, HookContext, HookResponse, HookResult, HookType

logger = logging.getLogger(__name__)

__all__ = ["CostGuardHook"]


class CostGuardHook(Hook):
    """
    PreToolUse hook that blocks operations exceeding budget.

    Tracks cumulative cost and blocks operations that would exceed
    the configured maximum budget.

    Attributes:
        max_cost_usd: Maximum allowed cost in USD
        spent: Current cumulative spend

    Example:
        hook = CostGuardHook(max_cost_usd=5.0)
        hooks.register(hook)

        # After operation completes
        hook.record_cost(0.50)
    """

    def __init__(self, max_cost_usd: float = 5.0, priority: int = 10):
        """
        Initialize cost guard.

        Args:
            max_cost_usd: Maximum allowed cost in USD
            priority: Execution priority (default 10 = runs early)
        """
        super().__init__(priority=priority, name="CostGuard")
        self._max_cost = max_cost_usd
        self._spent = 0.0
        # Hook callers can come from multiple threads (the pipeline runs
        # research in a background asyncio task, while the MCP HTTP worker
        # processes other tool calls on its own thread). `_spent += cost`
        # is a read-modify-write — without locking, two concurrent
        # record_cost calls can lose an update, and the execute() check
        # can race against record_cost() to admit a paid operation that
        # together with already-in-flight work blows the budget.
        self._lock = threading.Lock()

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    @property
    def max_cost(self) -> float:
        """Get the maximum allowed cost."""
        return self._max_cost

    @property
    def spent(self) -> float:
        """Get the current cumulative spend."""
        with self._lock:
            return self._spent

    @property
    def remaining(self) -> float:
        """Get the remaining budget."""
        with self._lock:
            return max(0.0, self._max_cost - self._spent)

    async def execute(self, context: HookContext) -> HookResponse:
        """Check if operation would exceed budget."""
        estimated_cost = max(0.0, context.arguments.get("estimated_cost_usd", 0.0))

        with self._lock:
            spent_snapshot = self._spent
            if spent_snapshot + estimated_cost > self._max_cost:
                return HookResponse(
                    result=HookResult.BLOCK,
                    message=(
                        f"Budget exceeded: ${spent_snapshot:.2f} spent, "
                        f"${estimated_cost:.2f} requested, "
                        f"${self._max_cost:.2f} limit"
                    ),
                )

        return HookResponse(result=HookResult.ALLOW)

    def record_cost(self, cost: float) -> None:
        """
        Record actual cost after operation.

        Args:
            cost: Cost in USD to record
        """
        with self._lock:
            self._spent += cost
            total = self._spent
        logger.debug(f"CostGuard: recorded ${cost:.2f}, total ${total:.2f}")

    def set_spent(self, total_cost: float) -> None:
        """Atomically replace the spent total with an absolute value.

        Absolute-sync checkpoints (``RunBudget.sync_spend``) run from parallel
        worker threads; a separate reset() + record_cost() pair can interleave
        and double-count, so the replacement must be a single locked write.
        """
        with self._lock:
            self._spent = max(0.0, total_cost)

    def reset(self) -> None:
        """Reset the spent counter."""
        with self._lock:
            self._spent = 0.0
