"""
Tests for the cost estimator module.

Verifies cost estimation calculations and display formatting.
"""

import pytest
from primr.utils.cost_estimator import (
    estimate_cost,
    get_cost_summary,
    CostEstimate,
    MODE_ESTIMATES,
    GEMINI_3_PRO_INPUT_PRICE_SMALL,
    GEMINI_3_PRO_OUTPUT_PRICE_SMALL,
    GEMINI_3_FLASH_INPUT_PRICE,
    GEMINI_3_FLASH_OUTPUT_PRICE,
)
from primr.config.models import (
    ModelRegistry,
    PrimrModels,
    DEEP_RESEARCH_COST,
    SEARCH_COST_PER_QUERY,
)


class TestCostEstimate:
    """Tests for CostEstimate dataclass."""

    def test_cost_estimate_str_format(self):
        """CostEstimate formats correctly as string."""
        estimate = CostEstimate(
            mode="structured",
            estimated_input_tokens=100_000,
            estimated_output_tokens=50_000,
            estimated_search_queries=10,
            input_cost=0.20,
            output_cost=0.60,
            search_cost=0.0,
            total_cost=0.80,
            duration_minutes="20-25 min",
            notes=["Test note"]
        )

        result = str(estimate)

        assert "structured" in result
        assert "20-25 min" in result
        assert "100,000" in result
        assert "$0.80" in result
        assert "Test note" in result

    def test_cost_estimate_str_shows_deep_research(self):
        """CostEstimate shows deep research cost when > 0."""
        estimate = CostEstimate(
            mode="deep-research",
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            estimated_search_queries=0,
            input_cost=0.0,
            output_cost=0.0,
            search_cost=0.0,
            total_cost=2.50,
            duration_minutes="8-15 min",
            notes=[],
            deep_research_cost=2.50,
        )
        result = str(estimate)
        assert "Deep Research" in result
        assert "approximate" in result


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_estimate_structured_mode(self):
        """Estimate cost for structured mode."""
        estimate = estimate_cost("structured")

        assert estimate.mode == "structured"
        structured = MODE_ESTIMATES["structured"]
        expected_input = structured["flash_input_tokens"] + structured["pro_input_tokens"]
        expected_output = structured["flash_output_tokens"] + structured["pro_output_tokens"]
        assert estimate.estimated_input_tokens == expected_input
        assert estimate.estimated_output_tokens == expected_output
        assert estimate.total_cost > 0

    def test_estimate_deep_research_mode(self):
        """Estimate cost for deep-research mode."""
        estimate = estimate_cost("deep-research", use_historical=False)

        assert estimate.mode == "deep-research"
        # Deep research uses flat per-task cost, no tokens
        assert estimate.deep_research_cost == DEEP_RESEARCH_COST.standard_task_cost
        assert estimate.total_cost >= DEEP_RESEARCH_COST.standard_task_cost

    def test_estimate_complete_mode(self):
        """Estimate cost for complete mode."""
        estimate = estimate_cost("complete", use_historical=False)

        assert estimate.mode == "complete"
        complete = MODE_ESTIMATES["complete"]
        expected_input = complete["flash_input_tokens"] + complete["pro_input_tokens"]
        expected_output = complete["flash_output_tokens"] + complete["pro_output_tokens"]
        assert estimate.estimated_input_tokens == expected_input
        assert estimate.estimated_output_tokens == expected_output
        # Complete mode should cost more than deep-research alone
        deep_estimate = estimate_cost("deep-research", use_historical=False)
        assert estimate.total_cost > deep_estimate.total_cost

    def test_estimate_hybrid_mode(self):
        """Estimate cost for hybrid mode."""
        estimate = estimate_cost("hybrid")

        assert estimate.mode == "hybrid"
        hybrid = MODE_ESTIMATES["hybrid"]
        expected_input = hybrid["flash_input_tokens"] + hybrid["pro_input_tokens"]
        assert estimate.estimated_input_tokens == expected_input

    def test_estimate_with_ai_strategy(self):
        """AI strategy adds to cost estimate."""
        base_estimate = estimate_cost("structured", include_ai_strategy=False)
        ai_estimate = estimate_cost("structured", include_ai_strategy=True)

        assert ai_estimate.total_cost > base_estimate.total_cost

    def test_search_free_period(self):
        """Search is free during free period."""
        estimate = estimate_cost("structured", search_free=True)

        assert estimate.search_cost == 0.0

    def test_search_paid_period(self):
        """Search has cost after free period."""
        estimate = estimate_cost("structured", search_free=False)

        assert estimate.search_cost > 0.0
        expected_search_cost = estimate.estimated_search_queries * SEARCH_COST_PER_QUERY
        assert abs(estimate.search_cost - expected_search_cost) < 0.001

    def test_cost_calculation_blended(self):
        """Verify blended cost calculation across Flash + Pro models."""
        estimate = estimate_cost("structured", use_historical=False)
        structured = MODE_ESTIMATES["structured"]

        expected_flash_cost = PrimrModels.calculate_flash_cost(
            structured["flash_input_tokens"], structured["flash_output_tokens"]
        )
        expected_pro_cost = PrimrModels.calculate_pro_cost(
            structured["pro_input_tokens"], structured["pro_output_tokens"]
        )
        expected_search_cost = PrimrModels.calculate_search_cost(structured["search_queries"])
        expected_total = expected_flash_cost + expected_pro_cost + expected_search_cost

        assert abs(estimate.total_cost - expected_total) < 0.01

    def test_unknown_mode_defaults_to_scrape_only(self):
        """Unknown mode defaults to scrape-only estimates (safest/cheapest)."""
        estimate = estimate_cost("unknown-mode")
        scrape_estimate = estimate_cost("scrape-only")

        assert estimate.estimated_input_tokens == scrape_estimate.estimated_input_tokens


class TestGetCostSummary:
    """Tests for get_cost_summary function."""

    def test_summary_format(self):
        """Summary has expected format."""
        summary = get_cost_summary("structured")

        assert "$" in summary
        assert "min" in summary

    def test_summary_includes_ai_strategy(self):
        """Summary reflects AI strategy addition."""
        base_summary = get_cost_summary("structured", include_ai_strategy=False)
        ai_summary = get_cost_summary("structured", include_ai_strategy=True)

        # AI strategy should increase cost
        base_cost = float(base_summary.split("$")[1].split(" ")[0])
        ai_cost = float(ai_summary.split("$")[1].split(" ")[0])

        assert ai_cost > base_cost


class TestModeEstimates:
    """Tests for MODE_ESTIMATES configuration."""

    def test_all_modes_have_estimates(self):
        """All modes have estimate configurations."""
        expected_modes = ["structured", "deep-research", "complete", "hybrid"]

        for mode in expected_modes:
            assert mode in MODE_ESTIMATES
            assert "flash_input_tokens" in MODE_ESTIMATES[mode]
            assert "flash_output_tokens" in MODE_ESTIMATES[mode]
            assert "pro_input_tokens" in MODE_ESTIMATES[mode]
            assert "pro_output_tokens" in MODE_ESTIMATES[mode]
            assert "deep_research_tasks" in MODE_ESTIMATES[mode]
            assert "search_queries" in MODE_ESTIMATES[mode]
            assert "duration_min" in MODE_ESTIMATES[mode]
            assert "duration_max" in MODE_ESTIMATES[mode]

    def test_complete_mode_has_highest_tokens(self):
        """Complete mode should have highest total token estimates."""
        complete_input = (
            MODE_ESTIMATES["complete"]["flash_input_tokens"]
            + MODE_ESTIMATES["complete"]["pro_input_tokens"]
        )

        for mode in ["structured", "deep-research"]:
            mode_input = (
                MODE_ESTIMATES[mode]["flash_input_tokens"]
                + MODE_ESTIMATES[mode]["pro_input_tokens"]
            )
            assert complete_input >= mode_input


class TestPricingSingleSourceOfTruth:
    """Assert pricing constants are derived from models.py and match expected values."""

    def test_flash_pricing(self):
        """Flash pricing should be $0.50 input / $3.00 output."""
        assert ModelRegistry.GEMINI_3_FLASH.cost_per_1m_input_tokens == 0.50
        assert ModelRegistry.GEMINI_3_FLASH.cost_per_1m_output_tokens == 3.00

    def test_pro_pricing(self):
        """Pro pricing should be $2.00 input / $12.00 output."""
        assert ModelRegistry.GEMINI_3_PRO.cost_per_1m_input_tokens == 2.00
        assert ModelRegistry.GEMINI_3_PRO.cost_per_1m_output_tokens == 12.00

    def test_search_pricing(self):
        """Search should be $0.035/query."""
        assert SEARCH_COST_PER_QUERY == 0.035

    def test_deep_research_standard_cost_range(self):
        """Deep Research standard cost should be in $2-3 range."""
        assert 2.0 <= DEEP_RESEARCH_COST.standard_task_cost <= 3.0

    def test_cost_estimator_constants_match_model_registry(self):
        """Backward-compat aliases in cost_estimator should match models.py."""
        assert GEMINI_3_PRO_INPUT_PRICE_SMALL == ModelRegistry.GEMINI_3_PRO.cost_per_1m_input_tokens
        assert GEMINI_3_PRO_OUTPUT_PRICE_SMALL == ModelRegistry.GEMINI_3_PRO.cost_per_1m_output_tokens
        assert GEMINI_3_FLASH_INPUT_PRICE == ModelRegistry.GEMINI_3_FLASH.cost_per_1m_input_tokens
        assert GEMINI_3_FLASH_OUTPUT_PRICE == ModelRegistry.GEMINI_3_FLASH.cost_per_1m_output_tokens
