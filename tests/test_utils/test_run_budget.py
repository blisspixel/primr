"""Tests for the per-run cost ceiling (--budget flag plumbing)."""

import pytest

from primr.utils.run_budget import (
    RunBudget,
    clear_run_budget,
    get_run_budget,
    set_run_budget,
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

    def test_set_and_get(self):
        budget = set_run_budget(3.5)
        assert get_run_budget() is budget
        assert budget.max_cost == 3.5

    def test_clear(self):
        set_run_budget(1.0)
        clear_run_budget()
        assert get_run_budget() is None

    def test_set_rejects_non_positive(self):
        with pytest.raises(ValueError):
            set_run_budget(0.0)
        assert get_run_budget() is None
