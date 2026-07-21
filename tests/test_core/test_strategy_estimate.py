"""Contracts for standalone strategy planning estimates."""

from primr.config.models import DEEP_RESEARCH_COST
from primr.core.strategy_estimate import estimate_standalone_strategy


def test_standard_ai_prices_each_platform_as_one_deep_research_task():
    estimate = estimate_standalone_strategy("ai", platforms=("azure", "aws", "agnostic"))

    assert estimate.strategy_calls == 3
    assert estimate.deep_research_tasks == 3
    assert estimate.vendor_refresh_tasks == 0
    assert estimate.estimated_cost_usd == 3 * DEEP_RESEARCH_COST.standard_task_cost


def test_forced_refresh_prices_each_selected_target():
    estimate = estimate_standalone_strategy(
        "ai",
        platforms=("azure", "aws", "agnostic", "private"),
        refresh_vendor_research=True,
    )

    assert estimate.strategy_calls == 4
    assert estimate.vendor_refresh_tasks == 4
    assert estimate.deep_research_tasks == 8
    assert estimate.estimated_cost_usd == 8 * DEEP_RESEARCH_COST.standard_task_cost


def test_lite_ai_prices_reasoning_calls_and_grounded_refresh_cheaply():
    estimate = estimate_standalone_strategy(
        "ai_strategy",
        platforms=("azure", "agnostic"),
        lite_strategy=True,
        refresh_vendor_research=True,
    )

    assert estimate.strategy_calls == 2
    assert estimate.vendor_refresh_tasks == 2
    # Lite engine applies to BOTH strategy and vendor news: no Deep Research tasks.
    assert estimate.deep_research_tasks == 0
    from primr.ai.routing import Role, pick_model_for_role

    assert estimate.model_name == pick_model_for_role(Role.REASONING)
    # Two grounded AI-news briefs + two lite strategy calls stay well under a
    # single Deep Research task's flat cost.
    assert estimate.estimated_cost_usd > 0
    assert estimate.estimated_cost_usd < DEEP_RESEARCH_COST.standard_task_cost


def test_generic_strategy_is_one_agnostic_deep_research_task():
    estimate = estimate_standalone_strategy(
        "customer_experience",
        platforms=("azure", "aws"),
        lite_strategy=True,
        refresh_vendor_research=True,
    )

    assert estimate.platforms == ("agnostic",)
    assert estimate.lite_strategy is False
    assert estimate.strategy_calls == 1
    assert estimate.deep_research_tasks == 1
    assert estimate.vendor_refresh_tasks == 0
