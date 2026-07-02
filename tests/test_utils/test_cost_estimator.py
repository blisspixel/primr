"""
Tests for the cost estimator module.

Verifies cost estimation calculations and display formatting.
"""

import pytest

from primr.config.models import (
    DEEP_RESEARCH_COST,
    SEARCH_COST_PER_QUERY,
    ModelRegistry,
    PrimrModels,
)
from primr.utils.cost_estimator import (
    GEMINI_3_FLASH_INPUT_PRICE,
    GEMINI_3_FLASH_OUTPUT_PRICE,
    GEMINI_3_PRO_INPUT_PRICE_SMALL,
    GEMINI_3_PRO_OUTPUT_PRICE_SMALL,
    MODE_ESTIMATES,
    CostEstimate,
    _apply_tokenizer_safety_factor,
    estimate_cost,
    get_cost_summary,
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
            notes=["Test note"],
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

    def test_cost_estimate_str_shows_cached_and_long_context_lines(self):
        """CostEstimate shows cache and surcharge detail when present."""
        estimate = CostEstimate(
            mode="structured",
            estimated_input_tokens=500_000,
            estimated_output_tokens=20_000,
            estimated_search_queries=0,
            input_cost=1.00,
            output_cost=0.50,
            search_cost=0.0,
            total_cost=1.50,
            duration_minutes="20-25 min",
            notes=[],
            estimated_cached_input_tokens=125_000,
            cached_input_cost=0.05,
            long_context_surcharge_cost=0.25,
        )

        result = str(estimate)

        assert "Cached input" in result
        assert "125,000" in result
        assert "Long-context surcharge" in result


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
        """Verify blended cost calculation across Flash + active Pro models."""
        estimate = estimate_cost("structured", use_historical=False)
        structured = MODE_ESTIMATES["structured"]

        expected_flash_cost = PrimrModels.calculate_flash_cost(
            structured["flash_input_tokens"], structured["flash_output_tokens"]
        )
        # estimate_cost uses conservative pricing for the active Pro model
        expected_pro_cost = PrimrModels.calculate_active_pro_cost_conservative(
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

    def test_historical_cached_tokens_are_reflected_in_estimate(self, monkeypatch):
        """Historical cached-token averages populate estimate cache fields."""

        class FakeTracker:
            def get_average_by_mode(self, mode):
                assert mode == "structured"
                return {
                    "mode": "structured",
                    "sample_size": 3,
                    "avg_input_tokens": 200_000,
                    "avg_output_tokens": 20_000,
                    "avg_cached_input_tokens": 50_000,
                    "avg_search_queries": 10,
                    "avg_cost": 0.5,
                    "avg_duration_seconds": 1200,
                }

        monkeypatch.setattr("primr.utils.usage_tracker.get_usage_tracker", lambda: FakeTracker())

        estimate = estimate_cost("structured", use_historical=True)

        assert estimate.estimated_cached_input_tokens == 50_000
        assert estimate.estimated_live_input_tokens == 150_000
        assert estimate.cached_input_cost > 0
        assert estimate.live_input_cost > 0
        assert estimate.input_cost == pytest.approx(
            estimate.live_input_cost + estimate.cached_input_cost
        )
        assert any("Historical cache hits included" in note for note in estimate.notes)


class TestStrategyTypeEstimates:
    """--strategy-type documents must be priced (bug-hunt finding: the
    pre-flight --budget gate and dry-run previously omitted them entirely,
    understating spend by a full strategy per document). Pricing mirrors the
    runtime: non-fast paths REPLACE the AI strategy with the explicit types
    and only generate Deep-Research-backed types; fast mode runs both."""

    def test_deep_research_strategy_replaces_ai_strategy_on_non_fast(self):
        base = estimate_cost("complete", use_historical=False, include_ai_strategy=False)
        with_strategy = estimate_cost(
            "complete",
            use_historical=False,
            include_ai_strategy=True,  # runtime ignores this when strategies are explicit
            strategy_types=["customer_experience"],
        )
        assert (
            with_strategy.deep_research_cost
            == base.deep_research_cost + DEEP_RESEARCH_COST.standard_task_cost
        )
        assert any("customer_experience" in n for n in with_strategy.notes)

    def test_placeholder_strategy_priced_at_zero_with_note(self):
        """Non-DR types warn-skip at runtime on non-fast paths; pricing them
        would tell the user they pay for a document they will not get."""
        base = estimate_cost("complete", use_historical=False, include_ai_strategy=False)
        with_strategy = estimate_cost(
            "complete", use_historical=False, include_ai_strategy=False, strategy_types=["skills"]
        )
        assert with_strategy.total_cost == base.total_cost
        assert any("skip" in n and "skills" in n for n in with_strategy.notes)

    def test_fast_mode_strategy_adds_writing_bundle(self, monkeypatch):
        # Pin provider keys so routing (and therefore pricing) is deterministic.
        for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-key-for-estimate-shape")

        base = estimate_cost("complete", fast_mode=True, use_historical=False)
        with_strategy = estimate_cost(
            "complete",
            fast_mode=True,
            use_historical=False,
            strategy_types=["customer_experience"],
        )
        # Fast mode has no Deep Research; every strategy doc is a writing
        # bundle, generated IN ADDITION to the AI strategy.
        assert with_strategy.deep_research_cost == base.deep_research_cost
        assert with_strategy.estimated_input_tokens > base.estimated_input_tokens
        assert with_strategy.total_cost > base.total_cost
        assert any("customer_experience" in n for n in with_strategy.notes)

    def test_ai_type_is_not_double_priced(self):
        """ "ai" is covered by include_ai_strategy; the list must ignore it."""
        base = estimate_cost("complete", use_historical=False, include_ai_strategy=True)
        with_ai_listed = estimate_cost(
            "complete", use_historical=False, include_ai_strategy=True, strategy_types=["ai"]
        )
        assert with_ai_listed.total_cost == base.total_cost


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
        assert ModelRegistry.GEMINI_3_PRO.cost_per_1m_input_tokens == GEMINI_3_PRO_INPUT_PRICE_SMALL
        assert (
            ModelRegistry.GEMINI_3_PRO.cost_per_1m_output_tokens == GEMINI_3_PRO_OUTPUT_PRICE_SMALL
        )
        assert ModelRegistry.GEMINI_3_FLASH.cost_per_1m_input_tokens == GEMINI_3_FLASH_INPUT_PRICE
        assert ModelRegistry.GEMINI_3_FLASH.cost_per_1m_output_tokens == GEMINI_3_FLASH_OUTPUT_PRICE

    def test_sonnet_5_tokenizer_safety_factor(self):
        """Sonnet 5 estimates should account for the documented tokenizer expansion."""
        input_tokens, output_tokens, applied = _apply_tokenizer_safety_factor(
            "claude-sonnet-5", 100_000, 10_000
        )

        assert input_tokens == 130_000
        assert output_tokens == 13_000
        assert applied is True

    def test_other_models_do_not_get_sonnet_5_tokenizer_safety_factor(self):
        input_tokens, output_tokens, applied = _apply_tokenizer_safety_factor(
            "claude-haiku-4-5", 100_000, 10_000
        )

        assert input_tokens == 100_000
        assert output_tokens == 10_000
        assert applied is False


class TestTieredPricing:
    """Tests for tiered pricing support (Gemini 3.1 Pro)."""

    def test_has_tiered_pricing_on_3_1_pro(self):
        """Gemini 3.1 Pro should have tiered pricing."""
        assert ModelRegistry.GEMINI_3_1_PRO.has_tiered_pricing is True
        assert ModelRegistry.GEMINI_3_1_PRO.tier_threshold_tokens == 200_000
        assert ModelRegistry.GEMINI_3_1_PRO.cost_per_1m_input_tokens_high == 4.00
        assert ModelRegistry.GEMINI_3_1_PRO.cost_per_1m_output_tokens_high == 18.00

    def test_has_tiered_pricing_on_3_1_pro_customtools(self):
        """Gemini 3.1 Pro CustomTools should have tiered pricing."""
        assert ModelRegistry.GEMINI_3_1_PRO_CUSTOMTOOLS.has_tiered_pricing is True

    def test_openai_gpt5_family_has_long_context_tiers(self):
        """OpenAI GPT-5.x models should carry long-context surcharge metadata."""
        expected = (
            (ModelRegistry.OPENAI_GPT_5_5, 10.00, 45.00),
            (ModelRegistry.OPENAI_GPT_5_4, 5.00, 22.50),
            (ModelRegistry.OPENAI_GPT_5_4_MINI, 1.50, 6.75),
            (ModelRegistry.OPENAI_GPT_5_4_NANO, 0.40, 1.875),
        )

        for model, input_high, output_high in expected:
            assert model.has_tiered_pricing is True
            assert model.tier_threshold_tokens == 270_000
            assert model.cost_per_1m_input_tokens_high == input_high
            assert model.cost_per_1m_output_tokens_high == output_high

    def test_no_tiered_pricing_on_3_0_pro(self):
        """Gemini 3.0 Pro should NOT have tiered pricing."""
        assert ModelRegistry.GEMINI_3_PRO.has_tiered_pricing is False

    def test_no_tiered_pricing_on_flash(self):
        """Flash model should NOT have tiered pricing."""
        assert ModelRegistry.GEMINI_3_FLASH.has_tiered_pricing is False

    def test_calculate_cost_standard_tier(self):
        """calculate_cost uses standard tier when prompt_tokens is below threshold."""
        cost = PrimrModels.calculate_cost(
            ModelRegistry.GEMINI_3_1_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
            prompt_tokens=150_000,  # below 200k threshold
        )
        # Standard tier: $2/$12
        expected = (100_000 / 1_000_000) * 2.00 + (10_000 / 1_000_000) * 12.00
        assert abs(cost - expected) < 0.001

    def test_calculate_cost_high_tier(self):
        """calculate_cost uses high tier when prompt_tokens exceeds threshold."""
        cost = PrimrModels.calculate_cost(
            ModelRegistry.GEMINI_3_1_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
            prompt_tokens=250_000,  # above 200k threshold
        )
        # High tier: $4/$18
        expected = (100_000 / 1_000_000) * 4.00 + (10_000 / 1_000_000) * 18.00
        assert abs(cost - expected) < 0.001

    def test_calculate_cost_breakdown_reports_cache_and_surcharge(self):
        """Detailed cost breakdown exposes cache cost and long-context surcharge."""
        breakdown = PrimrModels.calculate_cost_breakdown(
            ModelRegistry.OPENAI_GPT_5_4_MINI.name,
            input_tokens=300_000,
            output_tokens=20_000,
            prompt_tokens=300_000,
            cached_input_tokens=100_000,
        )

        assert breakdown.tier_applied is True
        assert breakdown.tier_threshold_tokens == 270_000
        assert breakdown.live_input_tokens == 200_000
        assert breakdown.cached_input_tokens == 100_000
        assert breakdown.cached_input_cost == pytest.approx(0.0075)
        assert breakdown.long_context_surcharge_cost > 0
        assert breakdown.total_cost == pytest.approx(breakdown.input_cost + breakdown.output_cost)

    def test_calculate_cost_no_prompt_tokens_uses_standard(self):
        """calculate_cost uses standard tier when prompt_tokens is None."""
        cost = PrimrModels.calculate_cost(
            ModelRegistry.GEMINI_3_1_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
        )
        # Standard tier: $2/$12
        expected = (100_000 / 1_000_000) * 2.00 + (10_000 / 1_000_000) * 12.00
        assert abs(cost - expected) < 0.001

    def test_calculate_cost_conservative_tiered_model(self):
        """calculate_cost_conservative uses high tier for tiered models."""
        conservative = PrimrModels.calculate_cost_conservative(
            ModelRegistry.GEMINI_3_1_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
        )
        standard = PrimrModels.calculate_cost(
            ModelRegistry.GEMINI_3_1_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
        )
        assert conservative > standard

    def test_calculate_cost_conservative_flat_model(self):
        """calculate_cost_conservative equals calculate_cost for flat models."""
        conservative = PrimrModels.calculate_cost_conservative(
            ModelRegistry.GEMINI_3_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
        )
        standard = PrimrModels.calculate_cost(
            ModelRegistry.GEMINI_3_PRO.name,
            input_tokens=100_000,
            output_tokens=10_000,
        )
        assert abs(conservative - standard) < 0.001

    def test_estimate_cost_with_tiered_model(self, monkeypatch):
        """estimate_cost uses conservative pricing when active model is tiered."""
        from primr.config.settings import reset_settings

        monkeypatch.setenv("AI_REASONING_MODEL", "gemini-3.1-pro-preview")
        reset_settings()

        try:
            estimate = estimate_cost("structured", use_historical=False)

            # Should have a tiered pricing note
            tiered_notes = [n for n in estimate.notes if "tiered pricing" in n]
            assert len(tiered_notes) == 1
            assert "conservative" in tiered_notes[0].lower()

            # Cost should be higher than default 3.0 Pro pricing
            monkeypatch.setenv("AI_REASONING_MODEL", "gemini-3-pro-preview")
            reset_settings()
            baseline = estimate_cost("structured", use_historical=False)
            assert estimate.total_cost > baseline.total_cost
        finally:
            monkeypatch.delenv("AI_REASONING_MODEL", raising=False)
            reset_settings()

    def test_estimate_cost_default_model_has_tiered_note(self):
        """estimate_cost with default 3.1 Pro should have tiered pricing note."""
        from primr.config.settings import reset_settings

        reset_settings()

        estimate = estimate_cost("structured", use_historical=False)

        tiered_notes = [n for n in estimate.notes if "tiered pricing" in n]
        assert len(tiered_notes) == 1
        assert "conservative" in tiered_notes[0].lower()

    def test_estimate_cost_flat_model_no_tiered_note(self, monkeypatch):
        """estimate_cost with flat-pricing 3.0 Pro should have no tiered pricing note."""
        from primr.config.settings import reset_settings

        monkeypatch.setenv("AI_REASONING_MODEL", "gemini-3-pro-preview")
        reset_settings()
        try:
            estimate = estimate_cost("structured", use_historical=False)
            tiered_notes = [n for n in estimate.notes if "tiered pricing" in n]
            assert len(tiered_notes) == 0
        finally:
            monkeypatch.delenv("AI_REASONING_MODEL", raising=False)
            reset_settings()


class TestFastModeAIStrategy:
    """Tests for fast mode with AI Strategy and cloud vendors."""

    def test_fast_with_strategy_costs_more_than_without(self):
        """Fast mode + AI Strategy should cost more than fast without."""
        base = estimate_cost(
            "complete", fast_mode=True, include_ai_strategy=False, use_historical=False
        )
        with_strategy = estimate_cost(
            "complete", fast_mode=True, include_ai_strategy=True, use_historical=False
        )
        assert with_strategy.total_cost > base.total_cost

    def test_fast_two_vendors_costs_more_than_one(self):
        """Fast mode + 2 vendors should cost more than 1 vendor."""
        one_vendor = estimate_cost(
            "complete",
            fast_mode=True,
            include_ai_strategy=True,
            num_vendors=1,
            use_historical=False,
        )
        two_vendors = estimate_cost(
            "complete",
            fast_mode=True,
            include_ai_strategy=True,
            num_vendors=2,
            use_historical=False,
        )
        assert two_vendors.total_cost > one_vendor.total_cost

    def test_fast_mode_never_includes_deep_research(self):
        """Fast mode should never include Deep Research cost, even with AI Strategy."""
        no_strategy = estimate_cost(
            "complete", fast_mode=True, include_ai_strategy=False, use_historical=False
        )
        with_strategy = estimate_cost(
            "complete", fast_mode=True, include_ai_strategy=True, use_historical=False
        )
        multi_vendor = estimate_cost(
            "complete",
            fast_mode=True,
            include_ai_strategy=True,
            num_vendors=3,
            use_historical=False,
        )
        assert no_strategy.deep_research_cost == 0.0
        assert with_strategy.deep_research_cost == 0.0
        assert multi_vendor.deep_research_cost == 0.0

    def test_fast_mode_strategy_note_mentions_grok(self, monkeypatch):
        """Fast mode AI Strategy note should mention Grok.

        The note names the reasoning provider, which the router resolves from
        configured keys. Pin XAI_API_KEY so reasoning routes to Grok
        deterministically - otherwise this depended on env leaking in from an
        earlier test and failed when run in isolation.
        """
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        estimate = estimate_cost(
            "complete",
            fast_mode=True,
            include_ai_strategy=True,
            num_vendors=2,
            use_historical=False,
        )
        grok_notes = [n for n in estimate.notes if "Grok" in n]
        assert len(grok_notes) >= 1

    def test_fast_mode_returns_default_mode_label(self, monkeypatch):
        """Fast mode estimate should report Grok mode when xAI is the routed provider."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        estimate = estimate_cost("complete", fast_mode=True, use_historical=False)
        assert estimate.mode == "standard (Grok 4.3 hybrid)"

    def test_fast_mode_explicit_fast_tier_label(self, monkeypatch):
        """Fast mode with explicit fast tier should report 'standard (Grok 4.3 (low-effort))'."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        estimate = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="fast")
        assert estimate.mode == "standard (Grok 4.3 (low-effort))"


class TestGrokTier:
    """Tests for Grok 4.20 tier support."""

    def test_grok_tier_enum_values(self):
        """GrokTier enum has fast, hybrid, max."""
        from primr.config.models import GrokTier

        assert GrokTier.FAST.value == "fast"
        assert GrokTier.HYBRID.value == "hybrid"
        assert GrokTier.MAX.value == "max"

    def test_get_grok_models_fast(self):
        """Fast tier returns grok-4.3 reasoning + grok-4.20-non-reasoning writing."""
        from primr.config.models import GrokTier

        reasoning, writing = PrimrModels.get_grok_models(GrokTier.FAST)
        assert reasoning == "grok-4.3"
        assert writing == "grok-4.20-non-reasoning"

    def test_get_grok_models_hybrid(self):
        """Hybrid tier returns same models as fast (difference is reasoning_effort)."""
        from primr.config.models import GrokTier

        reasoning, writing = PrimrModels.get_grok_models(GrokTier.HYBRID)
        assert reasoning == "grok-4.3"
        assert writing == "grok-4.20-non-reasoning"

    def test_get_grok_models_max(self):
        """Max tier returns Grok 4.3 for both stages (4.3 has no NR variant)."""
        from primr.config.models import GrokTier

        reasoning, writing = PrimrModels.get_grok_models(GrokTier.MAX)
        assert reasoning == "grok-4.3"
        assert writing == "grok-4.3"

    def test_grok_43_pricing(self):
        """Grok 4.3 standard pricing: $1.25/$2.50, cache $0.20."""
        assert ModelRegistry.GROK_4_3.cost_per_1m_input_tokens == 1.25
        assert ModelRegistry.GROK_4_3.cost_per_1m_output_tokens == 2.50
        assert ModelRegistry.GROK_4_3.cost_per_1m_input_tokens_cached == 0.20

    def test_grok_43_flat_pricing(self):
        """Grok 4.3 launched as flat-rate — xAI publishes no >200K tier.

        v1.22.0 registered placeholder high-tier rates (2x base) pending xAI
        confirmation. The May 2026 audit confirmed no such tier exists, so the
        placeholders were removed in the post-audit registry update.
        See ROADMAP "Model Landscape Audit — May 2026".
        """
        assert not ModelRegistry.GROK_4_3.has_tiered_pricing
        assert ModelRegistry.GROK_4_3.tier_threshold_tokens is None
        assert ModelRegistry.GROK_4_3.cost_per_1m_input_tokens_high is None
        assert ModelRegistry.GROK_4_3.cost_per_1m_output_tokens_high is None

    def test_grok_43_always_on_reasoning(self):
        """Grok 4.3 is reasoning-only — there is no non-reasoning variant."""
        assert ModelRegistry.GROK_4_3.supports_thinking is True
        assert ModelRegistry.GROK_4_3.supports_multimodal is True

    def test_grok_43_in_all_models(self):
        """Grok 4.3 should be registered in ALL_MODELS."""
        assert "grok-4.3" in PrimrModels.ALL_MODELS

    def test_grok_43_cache_discount(self):
        """Cached input tokens should bill at the cache rate, not the standard rate."""
        live_only = PrimrModels.calculate_cost("grok-4.3", 200_000, 10_000)
        with_cache = PrimrModels.calculate_cost(
            "grok-4.3", 200_000, 10_000, cached_input_tokens=150_000
        )
        assert with_cache < live_only

    def test_grok_420_pricing(self):
        """Legacy Grok 4.20 still registered with $2.00/$6.00 pricing."""
        assert ModelRegistry.GROK_4_20_REASONING.cost_per_1m_input_tokens == 2.00
        assert ModelRegistry.GROK_4_20_REASONING.cost_per_1m_output_tokens == 6.00
        assert ModelRegistry.GROK_4_20_NR.cost_per_1m_input_tokens == 2.00
        assert ModelRegistry.GROK_4_20_NR.cost_per_1m_output_tokens == 6.00

    def test_grok_420_in_all_models(self):
        """Legacy Grok 4.20 models should remain registered for back-compat."""
        assert "grok-4.20-0309-reasoning" in PrimrModels.ALL_MODELS
        assert "grok-4.20-0309-non-reasoning" in PrimrModels.ALL_MODELS
        assert "grok-4.20-multi-agent-0309" in PrimrModels.ALL_MODELS

    def test_grok_420_supports_thinking(self):
        """Legacy 4.20 reasoning variant supports thinking, NR does not."""
        assert ModelRegistry.GROK_4_20_REASONING.supports_thinking is True
        assert ModelRegistry.GROK_4_20_NR.supports_thinking is False

    def test_hybrid_tier_same_cost_as_fast(self):
        """FAST and HYBRID now use the same models; difference is reasoning_effort."""
        fast_est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="fast")
        hybrid_est = estimate_cost(
            "complete", fast_mode=True, use_historical=False, grok_tier="hybrid"
        )
        assert abs(hybrid_est.total_cost - fast_est.total_cost) < 0.001

    def test_max_tier_cheaper_than_hybrid_when_xai_only(self, monkeypatch):
        """With XAI-only (legacy) routing both tiers price writing as Grok, and
        MAX (grok-4.3 cached) edges out HYBRID (grok-4.20-nr) on writing.

        Once GEMINI_API_KEY is also set, the v1.24.x cross-provider routing
        makes HYBRID much cheaper than MAX (gemini-3.1-flash-lite writing
        vs grok-4.3 writing) — see test_hybrid_cheaper_than_max_with_gemini.
        """
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        hybrid_est = estimate_cost(
            "complete", fast_mode=True, use_historical=False, grok_tier="hybrid"
        )
        max_est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="max")
        assert max_est.total_cost <= hybrid_est.total_cost

    def test_hybrid_cheaper_than_max_with_gemini(self, monkeypatch):
        """With GEMINI_API_KEY set, HYBRID routes writing to gemini-3.1-flash-lite
        ($0.25/$1.50) while MAX stays all-Grok ($1.25/$2.50). HYBRID should
        come in well under MAX — the v1.24.0 sub-$1 default behavior."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        hybrid_est = estimate_cost(
            "complete", fast_mode=True, use_historical=False, grok_tier="hybrid"
        )
        max_est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="max")
        assert hybrid_est.total_cost < max_est.total_cost
        # Standard-mode default should now sit in the sub-$2 band, not the
        # legacy $4+ band — guard against regression of the v1.24.x routing fix.
        assert hybrid_est.total_cost < 2.00

    def test_hybrid_tier_mode_label(self, monkeypatch):
        """Hybrid tier estimate should have correct xAI-routed mode label."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        estimate = estimate_cost(
            "complete", fast_mode=True, use_historical=False, grok_tier="hybrid"
        )
        assert estimate.mode == "standard (Grok 4.3 hybrid)"

    def test_hybrid_tier_mode_label_with_gemini(self, monkeypatch):
        """Hybrid tier estimate should name Gemini when routed through Gemini."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
        estimate = estimate_cost(
            "complete", fast_mode=True, use_historical=False, grok_tier="hybrid"
        )
        assert estimate.mode == "standard (Gemini routed)"

    def test_max_tier_mode_label(self):
        """Max tier estimate should have correct mode label."""
        estimate = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="max")
        assert estimate.mode == "standard (Grok 4.3 max)"

    def test_fast_tier_cost_range_xai_only(self, monkeypatch):
        """Fast tier in legacy XAI-only mode: grok-4.3 reasoning + grok-4.20-nr writing,
        roughly $1.50-$5.00 range."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="fast")
        assert 1.50 < est.total_cost < 5.00

    def test_hybrid_tier_cost_range_xai_only(self, monkeypatch):
        """Hybrid tier in legacy XAI-only mode: same model pair as fast, same band."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="hybrid")
        assert 1.50 < est.total_cost < 5.00

    def test_hybrid_tier_cost_range_with_gemini(self, monkeypatch):
        """Hybrid tier with GEMINI_API_KEY set: writing routed to gemini-3.1-flash-lite,
        total drops into the sub-$1 band that the v1.24.0 default targets."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
        monkeypatch.setenv("XAI_API_KEY", "fake-test-key")
        est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="hybrid")
        # Sub-$2 (with strategy/hiring overhead included); without overhead,
        # the v1.24.0 stage-1 eval landed at $0.79.
        assert est.total_cost < 2.00

    def test_standard_estimate_routes_openai_only(self, monkeypatch):
        """OpenAI-only standard estimates should not price Gemini premium stages."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "fake-test-key")

        est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="hybrid")

        notes = " ".join(est.notes)
        assert est.mode == "standard (OpenAI routed)"
        assert est.deep_research_cost == 0.0
        assert "o4-mini reasoning" in notes
        assert "gpt-5.4-nano writing" in notes
        assert "gpt-5.4-nano utility" in notes
        assert "Gemini 3.1 Pro" not in notes

    def test_standard_estimate_routes_anthropic_only(self, monkeypatch):
        """Anthropic-only standard estimates should price Claude for every routed role."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-test-key")

        est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="hybrid")

        notes = " ".join(est.notes)
        assert est.mode == "standard (Anthropic routed)"
        assert est.deep_research_cost == 0.0
        assert f"{ModelRegistry.ANTHROPIC_SONNET.name} reasoning" in notes
        assert "claude-haiku-4-5 writing" in notes
        assert "claude-haiku-4-5 utility" in notes
        assert "Sonnet 5 token estimates include a 30% tokenizer safety factor" in notes

    def test_max_tier_cost_range(self):
        """Max tier (Grok 4.3 everywhere) should be in the $2.00-$5.00 band."""
        est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier="max")
        assert 2.00 < est.total_cost < 5.00

    def test_fast_mode_never_includes_deep_research_any_tier(self):
        """No Grok tier should include Deep Research cost."""
        for tier in ("fast", "hybrid", "max"):
            est = estimate_cost("complete", fast_mode=True, use_historical=False, grok_tier=tier)
            assert est.deep_research_cost == 0.0

    def test_grok_tier_default_is_hybrid(self):
        """Default grok_tier should produce same result as explicit hybrid."""
        default_est = estimate_cost("complete", fast_mode=True, use_historical=False)
        hybrid_est = estimate_cost(
            "complete", fast_mode=True, use_historical=False, grok_tier="hybrid"
        )
        assert abs(default_est.total_cost - hybrid_est.total_cost) < 0.001
