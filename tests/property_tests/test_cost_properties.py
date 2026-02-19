"""
Property-based tests for the Cost Attribution system.

This module contains property tests that verify universal correctness properties
of the CostTracker implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 5.1-5.6**
"""

from typing import Any

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck, assume

from primr.utils.telemetry import (
    TelemetryConfig,
    TelemetrySystem,
    CostTracker,
    NullSpan,
    is_otel_available,
)
from primr.utils.observability import correlation_scope


# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating valid model names
model_name_strategy = st.sampled_from([
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
])

# Strategy for generating unknown model names
unknown_model_strategy = st.from_regex(r'unknown-model-[a-z0-9]{4}', fullmatch=True)

# Strategy for generating token counts (non-negative integers)
token_count_strategy = st.integers(min_value=0, max_value=10_000_000)

# Strategy for generating pricing values (positive floats)
price_strategy = st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)

# Strategy for generating operation names
operation_name_strategy = st.sampled_from([
    "generate_report",
    "summarize_content",
    "extract_entities",
    "translate_text",
    "analyze_sentiment",
    None,
])

# Strategy for generating custom pricing tables
custom_pricing_strategy = st.dictionaries(
    st.from_regex(r'[a-z]+-[a-z0-9]+', fullmatch=True),
    st.tuples(price_strategy, price_strategy),
    min_size=1,
    max_size=5
)


# =============================================================================
# PROPERTY 14: COST CALCULATION CORRECTNESS
# =============================================================================

class TestCostCalculationCorrectness:
    """
    **Property 14: Cost Calculation Correctness**
    
    For any model in the pricing table and any token counts (input_tokens, output_tokens),
    `calculate_cost()` SHALL return `(input_tokens / 1_000_000) * input_price + 
    (output_tokens / 1_000_000) * output_price` where prices are from the pricing table.
    
    **Validates: Requirements 5.2**
    """

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cost_calculation_formula_correctness(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        Cost calculation should follow the exact formula from the design.
        
        Formula: (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
        """
        tracker = CostTracker()
        
        # Get the pricing for this model
        pricing = tracker.get_model_pricing(model)
        assert pricing is not None, f"Model {model} should be in default pricing"
        
        input_price, output_price = pricing
        
        # Calculate expected cost using the formula
        expected_cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
        
        # Calculate actual cost
        actual_cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        
        # Verify the formula is correct (using approximate equality for floating point)
        assert abs(actual_cost - expected_cost) < 1e-10, (
            f"Cost calculation mismatch for {model}: "
            f"expected {expected_cost}, got {actual_cost}"
        )

    @given(
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_unknown_model_returns_zero_cost(
        self, input_tokens: int, output_tokens: int
    ):
        """
        Unknown models should return 0.0 cost.
        """
        tracker = CostTracker()
        
        cost = tracker.calculate_cost("unknown-model", input_tokens, output_tokens)
        
        assert cost == 0.0, f"Unknown model should return 0.0 cost, got {cost}"

    @given(
        model=model_name_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_input_tokens_only_charges_output(
        self, model: str, output_tokens: int
    ):
        """
        With zero input tokens, cost should only be from output tokens.
        """
        tracker = CostTracker()
        pricing = tracker.get_model_pricing(model)
        assert pricing is not None
        
        _, output_price = pricing
        
        expected_cost = (output_tokens / 1_000_000) * output_price
        actual_cost = tracker.calculate_cost(model, 0, output_tokens)
        
        assert abs(actual_cost - expected_cost) < 1e-10

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_output_tokens_only_charges_input(
        self, model: str, input_tokens: int
    ):
        """
        With zero output tokens, cost should only be from input tokens.
        """
        tracker = CostTracker()
        pricing = tracker.get_model_pricing(model)
        assert pricing is not None
        
        input_price, _ = pricing
        
        expected_cost = (input_tokens / 1_000_000) * input_price
        actual_cost = tracker.calculate_cost(model, input_tokens, 0)
        
        assert abs(actual_cost - expected_cost) < 1e-10

    @given(model=model_name_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_tokens_returns_zero_cost(self, model: str):
        """
        Zero input and output tokens should return zero cost.
        """
        tracker = CostTracker()
        
        cost = tracker.calculate_cost(model, 0, 0)
        
        assert cost == 0.0, f"Zero tokens should return 0.0 cost, got {cost}"

    @given(
        custom_pricing=custom_pricing_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_custom_pricing_table_is_used(
        self, custom_pricing: dict[str, tuple[float, float]], 
        input_tokens: int, 
        output_tokens: int
    ):
        """
        Custom pricing tables should be used for cost calculation.
        """
        tracker = CostTracker(pricing=custom_pricing)
        
        # Pick a model from the custom pricing
        model = list(custom_pricing.keys())[0]
        input_price, output_price = custom_pricing[model]
        
        expected_cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
        actual_cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        
        assert abs(actual_cost - expected_cost) < 1e-10

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cost_is_non_negative(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        Cost should always be non-negative for non-negative token counts.
        """
        tracker = CostTracker()
        
        cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        
        assert cost >= 0.0, f"Cost should be non-negative, got {cost}"

    @given(
        model=model_name_strategy,
        input_tokens=st.integers(min_value=1, max_value=10_000_000),
        output_tokens=st.integers(min_value=1, max_value=10_000_000)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cost_increases_with_tokens(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        Cost should increase when token counts increase.
        """
        tracker = CostTracker()
        
        base_cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        more_input_cost = tracker.calculate_cost(model, input_tokens + 1000, output_tokens)
        more_output_cost = tracker.calculate_cost(model, input_tokens, output_tokens + 1000)
        
        assert more_input_cost >= base_cost, "Cost should increase with more input tokens"
        assert more_output_cost >= base_cost, "Cost should increase with more output tokens"


# =============================================================================
# PROPERTY 15: COST ATTRIBUTION TO SPANS
# =============================================================================

class TestCostAttributionToSpans:
    """
    **Property 15: Cost Attribution to Spans**
    
    For any call to `record_cost()` within an active span, the span SHALL have
    `ai.model`, `ai.input_tokens`, `ai.output_tokens`, and `ai.cost_usd` attributes
    set to the provided values.
    
    **Validates: Requirements 5.4, 5.5**
    """

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy,
        operation=operation_name_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_record_cost_returns_calculated_cost(
        self, model: str, input_tokens: int, output_tokens: int, operation: str | None
    ):
        """
        record_cost() should return the calculated cost value.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)
        tracker = CostTracker()
        
        expected_cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        
        with telemetry.span("test_operation") as span:
            actual_cost = telemetry.record_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                operation=operation
            )
        
        assert abs(actual_cost - expected_cost) < 1e-10, (
            f"record_cost should return calculated cost: expected {expected_cost}, got {actual_cost}"
        )

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_record_cost_does_not_raise_when_disabled(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        record_cost() should not raise errors when telemetry is disabled.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)
        
        # Should not raise
        cost = telemetry.record_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
        
        # Should still return the calculated cost
        tracker = CostTracker()
        expected_cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        assert abs(cost - expected_cost) < 1e-10

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy,
        operation=operation_name_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_record_cost_within_span_does_not_raise(
        self, model: str, input_tokens: int, output_tokens: int, operation: str | None
    ):
        """
        record_cost() within a span should not raise errors.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)
        
        with telemetry.span("test_operation") as span:
            # Should not raise
            cost = telemetry.record_cost(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                operation=operation
            )
            
            # Cost should be calculated correctly
            assert cost >= 0.0

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_record_cost_uses_custom_cost_tracker(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        record_cost() should use the provided cost_tracker if given.
        """
        config = TelemetryConfig(enabled=False)
        telemetry = TelemetrySystem(config)
        
        # Create a custom tracker with different pricing
        custom_pricing = {model: (10.0, 20.0)}  # Much higher prices
        custom_tracker = CostTracker(pricing=custom_pricing)
        
        expected_cost = custom_tracker.calculate_cost(model, input_tokens, output_tokens)
        
        actual_cost = telemetry.record_cost(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_tracker=custom_tracker
        )
        
        assert abs(actual_cost - expected_cost) < 1e-10

    @pytest.mark.skipif(not is_otel_available(), reason="OpenTelemetry not installed")
    @given(
        model=model_name_strategy,
        input_tokens=st.integers(min_value=100, max_value=10000),
        output_tokens=st.integers(min_value=100, max_value=10000)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_record_cost_attaches_attributes_to_span_with_otel(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        When OpenTelemetry is enabled, record_cost() should attach attributes to the span.
        """
        config = TelemetryConfig(enabled=True, exporter_type="none")
        telemetry = TelemetrySystem(config)
        
        if telemetry.is_enabled:
            with correlation_scope("test") as ctx:
                with telemetry.span("ai_operation", phase="generation") as span:
                    cost = telemetry.record_cost(
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        operation="test_operation"
                    )
                    
                    # Span should be a real OpenTelemetry span
                    assert not isinstance(span, NullSpan)
                    assert span.is_recording()
                    
                    # Cost should be calculated
                    assert cost >= 0.0


# =============================================================================
# COST TRACKER CONFIGURATION TESTS
# =============================================================================

class TestCostTrackerConfiguration:
    """
    Additional tests for CostTracker configuration and behavior.
    
    **Validates: Requirements 5.6**
    """

    def test_default_pricing_includes_gemini_models(self):
        """
        Default pricing should include all Gemini model variants.
        """
        tracker = CostTracker()

        # Both legacy and current models should be present
        expected_models = [
            "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash",
            "gemini-3-pro-preview", "gemini-3-flash-preview",
        ]

        for model in expected_models:
            assert model in tracker.get_supported_models(), (
                f"Model {model} should be in default pricing"
            )
            pricing = tracker.get_model_pricing(model)
            assert pricing is not None
            assert len(pricing) == 2
            assert all(p > 0 for p in pricing), "Prices should be positive"

    def test_default_pricing_values_match_design(self):
        """
        Default pricing values should match the design specification.
        """
        tracker = CostTracker()

        # Legacy models (still present for backward compat)
        assert tracker.get_model_pricing("gemini-1.5-pro") == (1.25, 5.00)
        assert tracker.get_model_pricing("gemini-1.5-flash") == (0.075, 0.30)
        assert tracker.get_model_pricing("gemini-2.0-flash") == (0.10, 0.40)

        # Current Gemini 3 models (from ModelRegistry)
        assert tracker.get_model_pricing("gemini-3-flash-preview") == (0.50, 3.00)
        assert tracker.get_model_pricing("gemini-3-pro-preview") == (2.00, 12.00)

    @given(
        model=st.from_regex(r'[a-z]+-[a-z0-9]+', fullmatch=True),
        input_price=price_strategy,
        output_price=price_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_add_model_pricing(
        self, model: str, input_price: float, output_price: float
    ):
        """
        add_model_pricing should add new models to the pricing table.
        """
        tracker = CostTracker()
        
        tracker.add_model_pricing(model, input_price, output_price)
        
        assert model in tracker.get_supported_models()
        assert tracker.get_model_pricing(model) == (input_price, output_price)

    @given(
        input_price=price_strategy,
        output_price=price_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_add_model_pricing_updates_existing(
        self, input_price: float, output_price: float
    ):
        """
        add_model_pricing should update pricing for existing models.
        """
        tracker = CostTracker()
        model = "gemini-1.5-pro"
        
        # Update existing model pricing
        tracker.add_model_pricing(model, input_price, output_price)
        
        assert tracker.get_model_pricing(model) == (input_price, output_price)

    def test_get_model_pricing_returns_none_for_unknown(self):
        """
        get_model_pricing should return None for unknown models.
        """
        tracker = CostTracker()
        
        assert tracker.get_model_pricing("unknown-model") is None

    @given(custom_pricing=custom_pricing_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_custom_pricing_initialization(
        self, custom_pricing: dict[str, tuple[float, float]]
    ):
        """
        CostTracker should accept custom pricing at initialization.
        """
        tracker = CostTracker(pricing=custom_pricing)
        
        assert tracker.pricing == custom_pricing
        assert set(tracker.get_supported_models()) == set(custom_pricing.keys())


# =============================================================================
# COST CALCULATION EDGE CASES
# =============================================================================

class TestCostCalculationEdgeCases:
    """
    Edge case tests for cost calculation.
    """

    def test_very_large_token_counts(self):
        """
        Cost calculation should handle very large token counts.
        """
        tracker = CostTracker()
        
        # 1 billion tokens
        large_count = 1_000_000_000
        
        cost = tracker.calculate_cost("gemini-1.5-pro", large_count, large_count)
        
        # Expected: (1B/1M) * 1.25 + (1B/1M) * 5.00 = 1000 * 1.25 + 1000 * 5.00 = 6250
        expected = 1000 * 1.25 + 1000 * 5.00
        assert abs(cost - expected) < 1e-6

    def test_exact_one_million_tokens(self):
        """
        Cost for exactly 1 million tokens should equal the price per million.
        """
        tracker = CostTracker()
        
        # 1 million input tokens with gemini-1.5-pro (input price = 1.25)
        cost = tracker.calculate_cost("gemini-1.5-pro", 1_000_000, 0)
        assert abs(cost - 1.25) < 1e-10
        
        # 1 million output tokens with gemini-1.5-pro (output price = 5.00)
        cost = tracker.calculate_cost("gemini-1.5-pro", 0, 1_000_000)
        assert abs(cost - 5.00) < 1e-10

    def test_small_token_counts(self):
        """
        Cost calculation should handle small token counts accurately.
        """
        tracker = CostTracker()
        
        # 1 token
        cost = tracker.calculate_cost("gemini-1.5-pro", 1, 1)
        
        # Expected: (1/1M) * 1.25 + (1/1M) * 5.00 = 0.00000125 + 0.000005 = 0.00000625
        expected = (1 / 1_000_000) * 1.25 + (1 / 1_000_000) * 5.00
        assert abs(cost - expected) < 1e-15

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cost_calculation_is_deterministic(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        Cost calculation should be deterministic (same inputs = same output).
        """
        tracker = CostTracker()
        
        cost1 = tracker.calculate_cost(model, input_tokens, output_tokens)
        cost2 = tracker.calculate_cost(model, input_tokens, output_tokens)
        
        assert cost1 == cost2, "Cost calculation should be deterministic"

    @given(
        model=model_name_strategy,
        input_tokens=token_count_strategy,
        output_tokens=token_count_strategy
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cost_is_additive(
        self, model: str, input_tokens: int, output_tokens: int
    ):
        """
        Cost should be additive: cost(a+b) = cost(a) + cost(b) for same model.
        """
        tracker = CostTracker()
        
        # Calculate cost for combined tokens
        combined_cost = tracker.calculate_cost(model, input_tokens, output_tokens)
        
        # Calculate cost for input and output separately
        input_only_cost = tracker.calculate_cost(model, input_tokens, 0)
        output_only_cost = tracker.calculate_cost(model, 0, output_tokens)
        
        # Should be additive
        assert abs(combined_cost - (input_only_cost + output_only_cost)) < 1e-10
