import pytest

from primr.config.models import DEEP_RESEARCH_COST
from primr.core.deep_budget import (
    count_main_deep_research_tasks,
    deep_research_flat_cost,
    deep_research_spend,
    strategy_uses_deep_research,
)


def test_counts_required_main_deep_research_tasks():
    assert count_main_deep_research_tasks("deep-research") == 1
    assert count_main_deep_research_tasks("complete") == 1
    assert count_main_deep_research_tasks("hybrid") == 1
    assert count_main_deep_research_tasks("scrape-only") == 0


def test_strategy_deep_research_classification():
    assert strategy_uses_deep_research("ai", lite_strategy=False) is True
    assert strategy_uses_deep_research("ai", lite_strategy=True) is False
    assert strategy_uses_deep_research("customer_experience", lite_strategy=False) is True
    assert strategy_uses_deep_research("skills", lite_strategy=False) is True
    assert strategy_uses_deep_research("unknown_placeholder", lite_strategy=False) is False


def test_deep_research_flat_cost_and_spend():
    task_cost = DEEP_RESEARCH_COST.standard_task_cost

    assert deep_research_flat_cost(-1) == 0
    assert deep_research_flat_cost(2) == pytest.approx(2 * task_cost)
    assert deep_research_spend(
        mode="deep-research",
        pipeline_cost=1.25,
        optional_strategy_tasks_started=2,
        vendor_refresh_tasks_started=1,
    ) == pytest.approx(1.25 + (4 * task_cost))
