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


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_estimate_structured_mode(self):
        """Estimate cost for structured mode."""
        estimate = estimate_cost("structured")
        
        assert estimate.mode == "structured"
        assert estimate.estimated_input_tokens == MODE_ESTIMATES["structured"]["input_tokens"]
        assert estimate.estimated_output_tokens == MODE_ESTIMATES["structured"]["output_tokens"]
        assert estimate.total_cost > 0

    def test_estimate_deep_research_mode(self):
        """Estimate cost for deep-research mode."""
        # Use use_historical=False to get default estimates
        estimate = estimate_cost("deep-research", use_historical=False)
        
        assert estimate.mode == "deep-research"
        assert estimate.estimated_input_tokens == MODE_ESTIMATES["deep-research"]["input_tokens"]
        # Notes should contain search free info
        assert any("FREE" in note or "Search" in note for note in estimate.notes)

    def test_estimate_complete_mode(self):
        """Estimate cost for complete mode."""
        # Use use_historical=False to get default estimates
        estimate = estimate_cost("complete", use_historical=False)
        
        assert estimate.mode == "complete"
        assert estimate.estimated_input_tokens == MODE_ESTIMATES["complete"]["input_tokens"]
        assert estimate.estimated_output_tokens == MODE_ESTIMATES["complete"]["output_tokens"]
        # Complete mode should have more input tokens than deep-research alone
        deep_estimate = estimate_cost("deep-research", use_historical=False)
        assert estimate.estimated_input_tokens > deep_estimate.estimated_input_tokens

    def test_estimate_hybrid_mode(self):
        """Estimate cost for hybrid mode."""
        estimate = estimate_cost("hybrid")
        
        assert estimate.mode == "hybrid"
        assert estimate.estimated_input_tokens == MODE_ESTIMATES["hybrid"]["input_tokens"]

    def test_estimate_with_ai_strategy(self):
        """AI strategy adds to cost estimate."""
        base_estimate = estimate_cost("structured", include_ai_strategy=False)
        ai_estimate = estimate_cost("structured", include_ai_strategy=True)
        
        assert ai_estimate.estimated_input_tokens > base_estimate.estimated_input_tokens
        assert ai_estimate.estimated_output_tokens > base_estimate.estimated_output_tokens
        assert ai_estimate.total_cost > base_estimate.total_cost

    def test_search_free_period(self):
        """Search is free during free period."""
        estimate = estimate_cost("deep-research", search_free=True)
        
        assert estimate.search_cost == 0.0
        assert any("FREE" in note for note in estimate.notes)

    def test_search_paid_period(self):
        """Search has cost after free period."""
        estimate = estimate_cost("deep-research", search_free=False)
        
        assert estimate.search_cost > 0.0
        # Verify $35/1000 queries pricing ($0.035/query)
        expected_search_cost = (estimate.estimated_search_queries / 1000) * 35.0
        assert abs(estimate.search_cost - expected_search_cost) < 0.001

    def test_cost_calculation_accuracy(self):
        """Verify cost calculation is accurate."""
        estimate = estimate_cost("structured")
        
        expected_input_cost = (estimate.estimated_input_tokens / 1_000_000) * GEMINI_3_PRO_INPUT_PRICE_SMALL
        expected_output_cost = (estimate.estimated_output_tokens / 1_000_000) * GEMINI_3_PRO_OUTPUT_PRICE_SMALL
        
        assert abs(estimate.input_cost - expected_input_cost) < 0.001
        assert abs(estimate.output_cost - expected_output_cost) < 0.001

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
            assert "input_tokens" in MODE_ESTIMATES[mode]
            assert "output_tokens" in MODE_ESTIMATES[mode]
            assert "search_queries" in MODE_ESTIMATES[mode]
            # Duration is split into min/max
            assert "duration_min" in MODE_ESTIMATES[mode]
            assert "duration_max" in MODE_ESTIMATES[mode]

    def test_complete_mode_has_highest_tokens(self):
        """Complete mode should have highest token estimates."""
        complete_input = MODE_ESTIMATES["complete"]["input_tokens"]
        
        for mode in ["structured", "deep-research"]:
            assert complete_input >= MODE_ESTIMATES[mode]["input_tokens"]
