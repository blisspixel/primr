"""Tests for the per-run cost ceiling (--budget flag plumbing)."""

import pytest

from primr.utils.run_budget import (
    RunBudget,
    clear_run_budget,
    get_run_budget,
    set_run_budget,
    skip_stage_if_cost_would_exceed,
)


@pytest.fixture(autouse=True)
def _clean_budget():
    """Every test starts and ends with no active budget."""
    clear_run_budget()
    yield
    clear_run_budget()


class TestRunBudget:
    def test_rejects_non_positive_budget(self):
        with pytest.raises(ValueError):
            RunBudget(0.0)
        with pytest.raises(ValueError):
            RunBudget(-1.0)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_nonfinite_budget(self, value):
        with pytest.raises(ValueError):
            RunBudget(value)

    def test_initial_state(self):
        budget = RunBudget(2.0)
        assert budget.max_cost == 2.0
        assert budget.spent == 0.0
        assert budget.remaining == 2.0
        assert not budget.exceeded()

    def test_sync_spend_is_absolute_not_cumulative(self):
        budget = RunBudget(2.0)
        budget.sync_spend(0.5)
        budget.sync_spend(0.8)  # re-sync at a later checkpoint
        assert budget.spent == 0.8
        assert budget.remaining == pytest.approx(1.2)

    def test_sync_spend_clamps_negative(self):
        budget = RunBudget(2.0)
        budget.sync_spend(-3.0)
        assert budget.spent == 0.0

    def test_exceeded_at_and_past_ceiling(self):
        budget = RunBudget(1.0)
        budget.sync_spend(0.99)
        assert not budget.exceeded()
        budget.sync_spend(1.0)
        assert budget.exceeded()
        budget.sync_spend(1.5)
        assert budget.exceeded()

    def test_would_exceed(self):
        budget = RunBudget(1.0)
        budget.sync_spend(0.6)
        # Landing exactly on the ceiling counts as exceeded, consistent with
        # exceeded() (remaining <= 0): 0.6 + 0.4 == 1.0 -> would_exceed.
        assert budget.would_exceed(0.4)
        assert not budget.would_exceed(0.39)
        assert budget.would_exceed(0.41)
        # Negative estimates are clamped, never "un-exceed"
        assert not budget.would_exceed(-5.0)


class TestActiveBudgetRegistry:
    def test_no_budget_by_default(self):
        assert get_run_budget() is None

    def test_discrete_task_is_skipped_when_remaining_budget_cannot_cover_it(self):
        set_run_budget(3.0)

        assert skip_stage_if_cost_would_exceed(0.75, 2.5, "vendor refresh") is True
        assert get_run_budget().spent == 0.75

    def test_discrete_task_runs_when_budget_has_headroom(self):
        set_run_budget(4.0)

        assert skip_stage_if_cost_would_exceed(0.75, 2.5, "vendor refresh") is False
        assert get_run_budget().spent == 0.75

    def test_set_and_get(self):
        budget = set_run_budget(3.5)
        assert get_run_budget() is budget
        assert budget.max_cost == 3.5

    def test_as_hook_is_the_same_cost_guard_sync_spend_updates(self):
        from primr.agentic.cost_guard import CostGuardHook

        budget = set_run_budget(4.0)
        hook = budget.as_hook()
        assert isinstance(hook, CostGuardHook)
        budget.sync_spend(1.25)
        assert hook.spent == 1.25
        assert hook is budget.as_hook()

    def test_clear(self):
        set_run_budget(1.0)
        clear_run_budget()
        assert get_run_budget() is None

    def test_set_rejects_non_positive(self):
        with pytest.raises(ValueError):
            set_run_budget(0.0)
        assert get_run_budget() is None


class TestSyncSpendConcurrency:
    """sync_spend is an absolute set and must stay atomic: the per-vendor
    strategy checkpoints call it from parallel worker threads, and a
    reset-then-record pair could interleave to double the recorded spend
    and falsely skip stages that had headroom (bug-hunt finding)."""

    def test_concurrent_syncs_never_double_count(self):
        import sys
        import threading

        from primr.utils.run_budget import RunBudget

        budget = RunBudget(10.0)
        workers = 16
        barrier = threading.Barrier(workers + 1)  # +1 for the watcher
        stop = threading.Event()
        max_observed = 0.0

        def hammer():
            barrier.wait()
            for _ in range(200):
                budget.sync_spend(0.5)

        def watch():
            # The old reset-then-record pair exposed transient inflated values
            # (a checkpoint in another thread could see 1.0+ and falsely skip).
            # A final-state assertion alone cannot see that; the watcher can.
            nonlocal max_observed
            barrier.wait()
            while not stop.is_set():
                max_observed = max(max_observed, budget.spent)

        old_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-5)
        try:
            threads = [threading.Thread(target=hammer) for _ in range(workers)]
            watcher = threading.Thread(target=watch)
            watcher.start()
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            stop.set()
            watcher.join()
        finally:
            sys.setswitchinterval(old_interval)

        # Absolute semantics: every sync reported the same observed spend, so
        # neither the final value nor any mid-run observation may exceed it.
        assert budget.spent == 0.5
        assert max_observed <= 0.5
        assert not budget.exceeded()
