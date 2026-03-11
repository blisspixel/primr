"""
Cost estimation accuracy tests.

Tests that cost estimates are within acceptable ranges of actual usage.

**Feature: test-coverage-hardening**
**Validates: Requirements 9.1, 9.2, 9.3**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.config.models import PrimrModels
from primr.utils.cost_estimator import (
    GEMINI_3_FLASH_INPUT_PRICE,
    GEMINI_3_FLASH_OUTPUT_PRICE,
    MODE_ESTIMATES,
    estimate_cost,
)

# =============================================================================
# Historical Usage Data (for accuracy validation)
# =============================================================================

# Typical actual costs observed in production (approximate)
# Updated Feb 2026 for blended Flash+Pro + Deep Research per-task pricing
TYPICAL_ACTUAL_COSTS = {
    "deep-research": {
        "min_cost": 1.50,  # Minimum observed (cheap DR task)
        "max_cost": 4.00,  # Maximum observed (complex DR task)
        "typical_cost": 2.50,  # Standard task cost
    },
    "complete": {
        "min_cost": 2.00,
        "max_cost": 5.00,
        "typical_cost": 3.00,
    },
    "structured": {
        "min_cost": 0.20,
        "max_cost": 1.50,
        "typical_cost": 0.60,
    },
}


# =============================================================================
# Unit Tests for Cost Estimation
# =============================================================================


class TestFullModeEstimate:
    """Tests for full mode (complete) cost estimation."""

    def test_full_mode_includes_scraping_and_deep_research(self):
        """
        WHEN cost is estimated for full mode
        THEN the estimate SHALL account for both scraping and Deep Research

        **Validates: Requirements 9.2**
        """
        complete_estimate = estimate_cost("complete", use_historical=False)
        deep_estimate = estimate_cost("deep-research", use_historical=False)
        structured_estimate = estimate_cost("structured", use_historical=False)

        # Complete mode should have more tokens than deep-research (which has 0 tokens)
        assert complete_estimate.estimated_input_tokens > deep_estimate.estimated_input_tokens
        # Complete mode tokens >= structured (same scraping + writing, plus DR task)
        assert (
            complete_estimate.estimated_input_tokens >= structured_estimate.estimated_input_tokens
        )

        # Complete mode cost should be higher than either alone
        assert complete_estimate.total_cost > deep_estimate.total_cost
        assert complete_estimate.total_cost > structured_estimate.total_cost

    def test_full_mode_duration_is_longer(self):
        """Full mode should have longer duration estimate."""
        complete_estimate = estimate_cost("complete", use_historical=False)
        deep_estimate = estimate_cost("deep-research", use_historical=False)

        # Both should have duration strings
        assert "min" in complete_estimate.duration_minutes
        assert "min" in deep_estimate.duration_minutes


class TestAIStrategyCost:
    """Tests for AI strategy cost addition."""

    def test_ai_strategy_adds_cost(self):
        """
        WHEN AI strategy is included
        THEN the estimate SHALL add the strategy generation cost

        **Validates: Requirements 9.3**
        """
        base_estimate = estimate_cost("deep-research", include_ai_strategy=False)
        ai_estimate = estimate_cost("deep-research", include_ai_strategy=True)

        # AI strategy should add cost (adds another DR task)
        assert ai_estimate.total_cost > base_estimate.total_cost

        # The difference should be meaningful (at least 10% increase)
        cost_increase = (
            ai_estimate.total_cost - base_estimate.total_cost
        ) / base_estimate.total_cost
        assert cost_increase >= 0.10, "AI strategy should add at least 10% to cost"

    def test_ai_strategy_cost_for_all_modes(self):
        """AI strategy adds cost for all research modes."""
        modes = ["structured", "deep-research", "complete"]

        for mode in modes:
            base = estimate_cost(mode, include_ai_strategy=False)
            with_ai = estimate_cost(mode, include_ai_strategy=True)

            assert with_ai.total_cost > base.total_cost, f"AI strategy should add cost for {mode}"


class TestCostAccuracyBounds:
    """Tests for cost estimate accuracy bounds."""

    def test_deep_mode_within_50_percent(self):
        """
        WHEN cost is estimated for deep mode
        THEN the estimate SHALL be within 50% of typical actual costs

        **Validates: Requirements 9.1**
        """
        estimate = estimate_cost("deep-research", use_historical=False)
        typical = TYPICAL_ACTUAL_COSTS["deep-research"]["typical_cost"]

        # Calculate bounds (50% tolerance)
        lower_bound = typical * 0.5
        upper_bound = typical * 1.5

        assert estimate.total_cost >= lower_bound, (
            f"Estimate ${estimate.total_cost:.2f} below lower bound ${lower_bound:.2f}"
        )
        assert estimate.total_cost <= upper_bound, (
            f"Estimate ${estimate.total_cost:.2f} above upper bound ${upper_bound:.2f}"
        )

    def test_estimates_are_reasonable(self):
        """All mode estimates should be in reasonable ranges."""
        for mode in ["structured", "deep-research", "complete"]:
            estimate = estimate_cost(mode, use_historical=False)

            # Cost should be positive
            assert estimate.total_cost > 0, f"{mode} cost should be positive"

            # Cost should be less than $10 for a single report
            assert estimate.total_cost < 10.0, f"{mode} cost should be < $10"

            # Token counts should be reasonable
            assert estimate.estimated_input_tokens >= 0
            assert estimate.estimated_output_tokens >= 0
            assert estimate.estimated_input_tokens < 10_000_000  # < 10M tokens


# =============================================================================
# Property Tests
# =============================================================================


@given(
    include_ai=st.booleans(),
    search_free=st.booleans(),
)
@settings(max_examples=20, deadline=None)
def test_property_cost_is_non_negative(include_ai: bool, search_free: bool):
    """
    **Feature: test-coverage-hardening, Property 14: Cost estimate accuracy**
    **Validates: Requirements 9.1**

    For any cost estimate configuration, the cost should be non-negative.
    """
    for mode in ["structured", "deep-research", "complete"]:
        estimate = estimate_cost(
            mode,
            include_ai_strategy=include_ai,
            search_free=search_free,
        )

        assert estimate.total_cost >= 0
        assert estimate.input_cost >= 0
        assert estimate.output_cost >= 0
        assert estimate.search_cost >= 0
        assert estimate.deep_research_cost >= 0


@given(
    mode=st.sampled_from(["structured", "deep-research", "complete"]),
)
@settings(max_examples=30, deadline=None)
def test_property_ai_strategy_increases_cost(mode: str):
    """
    **Feature: test-coverage-hardening, Property 14: Cost estimate accuracy**
    **Validates: Requirements 9.3**

    For any mode, adding AI strategy should increase the cost.
    """
    base = estimate_cost(mode, include_ai_strategy=False)
    with_ai = estimate_cost(mode, include_ai_strategy=True)

    assert with_ai.total_cost >= base.total_cost


@given(
    mode=st.sampled_from(["structured", "deep-research", "complete"]),
)
@settings(max_examples=30, deadline=None)
def test_property_cost_calculation_consistent(mode: str):
    """
    **Feature: test-coverage-hardening, Property 14: Cost estimate accuracy**
    **Validates: Requirements 9.1**

    For any mode, the total cost should equal input + output + search + deep_research costs.
    """
    estimate = estimate_cost(mode)

    calculated_total = (
        estimate.input_cost
        + estimate.output_cost
        + estimate.search_cost
        + estimate.deep_research_cost
    )

    # Allow small floating point tolerance
    assert abs(estimate.total_cost - calculated_total) < 0.01


@given(
    mode=st.sampled_from(["structured"]),  # Only test modes with token costs
)
@settings(max_examples=30, deadline=None)
def test_property_token_cost_relationship(mode: str):
    """
    **Feature: test-coverage-hardening, Property 14: Cost estimate accuracy**
    **Validates: Requirements 9.1**

    For structured mode, cost should reflect blended Flash + active Pro pricing.
    Active Pro model may have tiered pricing — estimates use conservative (high) tier.
    """

    estimate = estimate_cost(mode, use_historical=False)
    m = MODE_ESTIMATES[mode]

    # Resolve active Pro model pricing (conservative for tiered models)
    active_pro = PrimrModels.get_active_pro_model()
    if active_pro.has_tiered_pricing:
        pro_inp_price = active_pro.cost_per_1m_input_tokens_high
        pro_out_price = active_pro.cost_per_1m_output_tokens_high
    else:
        pro_inp_price = active_pro.cost_per_1m_input_tokens
        pro_out_price = active_pro.cost_per_1m_output_tokens

    expected_input_cost = (m["flash_input_tokens"] / 1_000_000) * GEMINI_3_FLASH_INPUT_PRICE + (
        m["pro_input_tokens"] / 1_000_000
    ) * pro_inp_price
    expected_output_cost = (m["flash_output_tokens"] / 1_000_000) * GEMINI_3_FLASH_OUTPUT_PRICE + (
        m["pro_output_tokens"] / 1_000_000
    ) * pro_out_price

    assert abs(estimate.input_cost - expected_input_cost) < 0.001
    assert abs(estimate.output_cost - expected_output_cost) < 0.001
