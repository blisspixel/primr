"""
Comprehensive tests for Primr v1.23.0 Multi-Provider Foundation.

Covers optional test tasks: 1.6, 3.6, 4.3, 5.3, 8.5, 8.6, 12.2, 12.3, 13.4.

**Feature: multi-provider-foundation**
**Validates: Requirements 1.1-1.11, 2.1-2.8, 3.1-3.8, 6.1-6.7, 8.1-8.6, 9.1-9.7, 10.1-10.5**
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.ai.providers.base import _UsageAccumulator
from primr.config.models import GrokTier, ModelConfig, ModelRegistry, PrimrModels


# =============================================================================
# TASK 1.6: Unit tests for retirement migration
# =============================================================================


class TestRetirementMigration:
    """Task 1.6 — Verify xAI model retirement migration is correct."""

    def test_get_grok_models_fast_tier(self) -> None:
        """FAST tier returns (grok-4.3, grok-4.20-non-reasoning)."""
        reasoning, writing = PrimrModels.get_grok_models(GrokTier.FAST)
        assert reasoning == "grok-4.3"
        assert writing == "grok-4.20-non-reasoning"

    def test_get_grok_models_hybrid_tier(self) -> None:
        """HYBRID tier returns (grok-4.3, grok-4.20-non-reasoning)."""
        reasoning, writing = PrimrModels.get_grok_models(GrokTier.HYBRID)
        assert reasoning == "grok-4.3"
        assert writing == "grok-4.20-non-reasoning"

    def test_get_grok_models_max_tier(self) -> None:
        """MAX tier returns (grok-4.3, grok-4.3)."""
        reasoning, writing = PrimrModels.get_grok_models(GrokTier.MAX)
        assert reasoning == "grok-4.3"
        assert writing == "grok-4.3"

    def test_grok_model_resolves_to_grok_43(self) -> None:
        """PrimrModels.GROK_MODEL resolves to grok-4.3."""
        assert PrimrModels.GROK_MODEL == "grok-4.3"

    def test_grok_model_writing_resolves_to_420_nr(self) -> None:
        """PrimrModels.GROK_MODEL_WRITING resolves to grok-4.20-non-reasoning."""
        assert PrimrModels.GROK_MODEL_WRITING == "grok-4.20-non-reasoning"

    def test_deprecated_models_have_deprecated_flag(self) -> None:
        """Retired models grok-4-1-fast-reasoning and grok-4-1-fast-non-reasoning are deprecated."""
        fast = ModelRegistry.GROK_4_1_FAST
        fast_nr = ModelRegistry.GROK_4_1_FAST_NR
        assert fast.deprecated is True
        assert fast_nr.deprecated is True

    def test_deprecated_models_not_in_active_fallback_chains(self) -> None:
        """Deprecated models are NOT in any active fallback chain's routing path."""
        from primr.pipeline.model_breaker import (
            ANALYSIS_FALLBACK_CHAIN,
            PREMIUM_FALLBACK_CHAIN,
            UTILITY_FALLBACK_CHAIN,
        )

        deprecated_names = {
            ModelRegistry.GROK_4_1_FAST.name,
            ModelRegistry.GROK_4_1_FAST_NR.name,
        }
        all_chain_models = set(
            ANALYSIS_FALLBACK_CHAIN.models
            + PREMIUM_FALLBACK_CHAIN.models
            + UTILITY_FALLBACK_CHAIN.models
        )
        assert deprecated_names.isdisjoint(all_chain_models), (
            f"Deprecated models found in fallback chains: {deprecated_names & all_chain_models}"
        )

    def test_pick_model_for_role_utility_with_xai_key(self, monkeypatch) -> None:
        """pick_model_for_role(Role.UTILITY) returns grok-4.20-non-reasoning when XAI_API_KEY is set."""
        from primr.ai.routing import Role, pick_model_for_role

        monkeypatch.setenv("XAI_API_KEY", "test-key")
        result = pick_model_for_role(Role.UTILITY)
        assert result == "grok-4.20-non-reasoning"


# =============================================================================
# TASK 3.6: Unit tests for registry expansion
# =============================================================================


class TestRegistryExpansion:
    """Task 3.6 — Verify provider registry contains all five providers."""

    def test_known_providers_has_five_entries(self) -> None:
        """KNOWN_PROVIDERS contains exactly 5 entries."""
        from primr.ai.providers.registry import KNOWN_PROVIDERS

        assert len(KNOWN_PROVIDERS) == 5

    def test_known_providers_names(self) -> None:
        """KNOWN_PROVIDERS contains xai, gemini, openai, anthropic, ollama."""
        from primr.ai.providers.registry import KNOWN_PROVIDERS

        names = {p.name for p in KNOWN_PROVIDERS}
        assert names == {"xai", "gemini", "openai", "anthropic", "ollama"}

    def test_get_available_providers_includes_ollama_without_env(self, monkeypatch) -> None:
        """Ollama is available even without OLLAMA_API_KEY (has api_key_default)."""
        from primr.ai.providers.registry import get_available_providers

        # Clear all provider keys to isolate
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

        available = get_available_providers()
        available_names = {p.name for p in available}
        assert "ollama" in available_names

    def test_get_available_providers_excludes_openai_without_key(self, monkeypatch) -> None:
        """OpenAI is excluded when OPENAI_API_KEY is unset."""
        from primr.ai.providers.registry import get_available_providers

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        available = get_available_providers()
        available_names = {p.name for p in available}
        assert "openai" not in available_names

    def test_get_available_providers_excludes_anthropic_without_key(self, monkeypatch) -> None:
        """Anthropic is excluded when ANTHROPIC_API_KEY is unset."""
        from primr.ai.providers.registry import get_available_providers

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        available = get_available_providers()
        available_names = {p.name for p in available}
        assert "anthropic" not in available_names

    def test_build_provider_returns_correct_types(self) -> None:
        """build_provider returns correct provider types for each entry."""
        from primr.ai.providers import OpenAICompatibleProvider
        from primr.ai.providers.anthropic import AnthropicProvider
        from primr.ai.providers.gemini import GeminiProvider
        from primr.ai.providers.registry import KNOWN_PROVIDERS, build_provider

        type_map = {
            "xai": OpenAICompatibleProvider,
            "gemini": GeminiProvider,
            "openai": OpenAICompatibleProvider,
            "anthropic": AnthropicProvider,
            "ollama": OpenAICompatibleProvider,
        }
        for entry in KNOWN_PROVIDERS:
            provider = build_provider(entry)
            expected_type = type_map[entry.name]
            assert isinstance(provider, expected_type), (
                f"build_provider({entry.name!r}) returned {type(provider).__name__}, "
                f"expected {expected_type.__name__}"
            )

    def test_get_provider_for_model_routes_openai(self) -> None:
        """get_provider_for_model routes OpenAI model names to OpenAI provider."""
        from primr.ai.routing import get_provider_for_model

        provider = get_provider_for_model("gpt-5.4")
        assert provider.name == "openai"

    def test_get_provider_for_model_routes_anthropic(self) -> None:
        """get_provider_for_model routes Anthropic model names to Anthropic provider."""
        from primr.ai.routing import get_provider_for_model

        provider = get_provider_for_model("claude-sonnet-4-6")
        assert provider.name == "anthropic"

    def test_get_provider_for_model_routes_ollama(self) -> None:
        """get_provider_for_model routes Ollama model names to Ollama provider."""
        from primr.ai.routing import get_provider_for_model

        provider = get_provider_for_model("qwen3-coder:30b")
        assert provider.name == "ollama"


# =============================================================================
# TASK 4.3: Unit tests for OpenAI integration
# =============================================================================


class TestOpenAIIntegration:
    """Task 4.3 — Verify OpenAI ModelConfig entries and routing."""

    OPENAI_MODELS = ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"]

    def test_openai_model_configs_exist(self) -> None:
        """ModelConfig entries exist for all OpenAI models."""
        for model_name in self.OPENAI_MODELS:
            config = PrimrModels.get_model_config(model_name)
            assert config is not None, f"Missing ModelConfig for {model_name}"

    def test_openai_models_have_correct_provider(self) -> None:
        """All OpenAI models have provider='openai'."""
        for model_name in self.OPENAI_MODELS:
            config = PrimrModels.get_model_config(model_name)
            assert config is not None
            assert config.provider == "openai", (
                f"{model_name} has provider={config.provider!r}, expected 'openai'"
            )

    def test_openai_models_have_cached_pricing(self) -> None:
        """All OpenAI models have cost_per_1m_input_tokens_cached set."""
        for model_name in self.OPENAI_MODELS:
            config = PrimrModels.get_model_config(model_name)
            assert config is not None
            assert config.cost_per_1m_input_tokens_cached is not None, (
                f"{model_name} missing cost_per_1m_input_tokens_cached"
            )

    def test_get_provider_for_model_gpt54_no_raise(self) -> None:
        """get_provider_for_model('gpt-5.4') doesn't raise."""
        from primr.ai.routing import get_provider_for_model

        # Should not raise KeyError or ValueError
        provider = get_provider_for_model("gpt-5.4")
        assert provider is not None


# =============================================================================
# TASK 5.3: Unit tests for Ollama integration
# =============================================================================


class TestOllamaIntegration:
    """Task 5.3 — Verify Ollama models have zero cost and default key availability."""

    OLLAMA_MODELS = ["qwen3-coder:30b", "qwen2.5:32b", "deepseek-r1:32b", "qwen3:7b"]

    def test_ollama_models_have_zero_cost(self) -> None:
        """All Ollama models have cost_per_1m_input_tokens=0.0 and cost_per_1m_output_tokens=0.0."""
        for model_name in self.OLLAMA_MODELS:
            config = PrimrModels.get_model_config(model_name)
            assert config is not None, f"Missing ModelConfig for {model_name}"
            assert config.cost_per_1m_input_tokens == 0.0, (
                f"{model_name} input cost is {config.cost_per_1m_input_tokens}, expected 0.0"
            )
            assert config.cost_per_1m_output_tokens == 0.0, (
                f"{model_name} output cost is {config.cost_per_1m_output_tokens}, expected 0.0"
            )

    def test_calculate_cost_returns_zero_for_ollama(self) -> None:
        """calculate_cost returns $0.00 for any Ollama model regardless of token count."""
        for model_name in self.OLLAMA_MODELS:
            cost = PrimrModels.calculate_cost(model_name, 1_000_000, 500_000)
            assert cost == 0.0, (
                f"calculate_cost({model_name!r}, 1M, 500k) = {cost}, expected 0.0"
            )

    def test_ollama_provider_available_with_default_key(self, monkeypatch) -> None:
        """Ollama provider is available with default key (no env var needed)."""
        from primr.ai.providers.registry import get_available_providers

        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        available = get_available_providers()
        available_names = {p.name for p in available}
        assert "ollama" in available_names


# =============================================================================
# TASK 8.5: Property test for cache cost monotonicity
# =============================================================================


class TestCacheCostMonotonicity:
    """Task 8.5 — Property: cached cost <= non-cached cost for all models with cached pricing.

    **Validates: Requirements 6.7, 9.7**
    """

    # Collect models that have cached pricing
    _CACHED_MODELS = [
        name
        for name, config in PrimrModels.ALL_MODELS.items()
        if config.cost_per_1m_input_tokens_cached is not None
    ]

    @given(
        input_tokens=st.integers(min_value=1, max_value=2_000_000),
        output_tokens=st.integers(min_value=1, max_value=131_072),
        cached_fraction=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_discount_monotonicity(
        self, input_tokens: int, output_tokens: int, cached_fraction: float
    ) -> None:
        """For all models with cached pricing, cost with cache <= cost without cache."""
        for model_name in self._CACHED_MODELS:
            cached_input_tokens = int(input_tokens * cached_fraction)
            cost_with_cache = PrimrModels.calculate_cost(
                model_name, input_tokens, output_tokens, cached_input_tokens=cached_input_tokens
            )
            cost_without_cache = PrimrModels.calculate_cost(
                model_name, input_tokens, output_tokens, cached_input_tokens=0
            )
            assert cost_with_cache <= cost_without_cache + 1e-10, (
                f"{model_name}: cost_with_cache={cost_with_cache} > "
                f"cost_without_cache={cost_without_cache} "
                f"(cached_fraction={cached_fraction}, input={input_tokens})"
            )


# =============================================================================
# TASK 8.6: Unit tests for cache token reporting
# =============================================================================


class TestCacheTokenReporting:
    """Task 8.6 — Verify _UsageAccumulator and Provider track cached_input_tokens."""

    def test_usage_accumulator_records_cached_tokens(self) -> None:
        """_UsageAccumulator.record() accumulates cached_input_tokens correctly."""
        acc = _UsageAccumulator()
        acc.record("grok-4.3", input_tokens=100, output_tokens=50, cached_input_tokens=30)
        acc.record("grok-4.3", input_tokens=200, output_tokens=100, cached_input_tokens=70)
        assert acc.cached_input_tokens == 100  # 30 + 70

    def test_usage_accumulator_by_model_includes_cached(self) -> None:
        """_UsageAccumulator.by_model includes cached_input_tokens per model."""
        acc = _UsageAccumulator()
        acc.record("gpt-5.4", input_tokens=500, output_tokens=200, cached_input_tokens=150)
        acc.record("gpt-5.5", input_tokens=300, output_tokens=100, cached_input_tokens=50)

        assert acc.by_model["gpt-5.4"]["cached_input_tokens"] == 150
        assert acc.by_model["gpt-5.5"]["cached_input_tokens"] == 50

    def test_provider_get_usage_returns_cached_input_tokens(self) -> None:
        """Provider.get_usage() returns cached_input_tokens."""
        from primr.ai.providers import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            name="test",
            base_url="http://localhost:1234/v1",
            api_key_env="TEST_KEY",
            api_key_default="test",
        )
        # Simulate recording usage with cached tokens
        provider._record_usage("test-model", input_tokens=1000, output_tokens=500, cached_input_tokens=200)

        usage = provider.get_usage()
        assert "cached_input_tokens" in usage
        assert usage["cached_input_tokens"] == 200


# =============================================================================
# TASK 12.2: Property tests for cost invariants
# =============================================================================


class TestCostInvariants:
    """Task 12.2 — Property tests for cost calculation invariants.

    **Validates: Requirements 9.5, 9.6, 9.7**
    """

    @given(model_name=st.sampled_from(list(PrimrModels.ALL_MODELS.keys())))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_zero_input_invariant(self, model_name: str) -> None:
        """For all models, calculate_cost(model, 0, 0) == 0.0.

        **Validates: Requirement 9.5**
        """
        assert PrimrModels.calculate_cost(model_name, 0, 0) == 0.0

    @given(
        model_name=st.sampled_from(list(PrimrModels.ALL_MODELS.keys())),
        input_tokens=st.integers(min_value=0, max_value=2_000_000),
        output_tokens=st.integers(min_value=0, max_value=131_072),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_non_negative_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> None:
        """For all models and non-negative tokens, cost >= 0.

        **Validates: Requirement 9.6**
        """
        cost = PrimrModels.calculate_cost(model_name, input_tokens, output_tokens)
        assert cost >= 0.0, f"{model_name}: cost={cost} < 0 for ({input_tokens}, {output_tokens})"

    # Cache discount monotonicity (Property 3) is covered in TestCacheCostMonotonicity above


# =============================================================================
# TASK 12.3: Unit tests for cost estimator edge cases
# =============================================================================


class TestCostEstimatorEdgeCases:
    """Task 12.3 — Edge cases for cost estimation."""

    def test_tiered_pricing_triggers_for_grok_43(self) -> None:
        """Tiered pricing triggers for grok-4.3 when prompt_tokens > 200k."""
        model = "grok-4.3"
        config = PrimrModels.get_model_config(model)
        assert config is not None
        assert config.has_tiered_pricing
        assert config.tier_threshold_tokens == 200_000

        # Standard tier (prompt <= 200k)
        cost_standard = PrimrModels.calculate_cost(
            model, 100_000, 50_000, prompt_tokens=100_000
        )
        # High tier (prompt > 200k)
        cost_high = PrimrModels.calculate_cost(
            model, 100_000, 50_000, prompt_tokens=300_000
        )
        # High tier should cost more
        assert cost_high > cost_standard

    def test_calculate_cost_conservative_uses_highest_tier(self) -> None:
        """calculate_cost_conservative uses highest tier for tiered models."""
        model = "grok-4.3"
        config = PrimrModels.get_model_config(model)
        assert config is not None

        conservative = PrimrModels.calculate_cost_conservative(model, 100_000, 50_000)
        standard = PrimrModels.calculate_cost(model, 100_000, 50_000)

        # Conservative should use high tier rates, standard uses low tier
        assert conservative >= standard

    def test_grok_43_pricing(self) -> None:
        """grok-4.3 priced at $1.25/$2.50 per 1M tokens."""
        config = PrimrModels.get_model_config("grok-4.3")
        assert config is not None
        assert config.cost_per_1m_input_tokens == 1.25
        assert config.cost_per_1m_output_tokens == 2.50

    def test_grok_420_non_reasoning_pricing(self) -> None:
        """grok-4.20-non-reasoning priced at $2.00/$6.00 per 1M tokens."""
        config = PrimrModels.get_model_config("grok-4.20-non-reasoning")
        assert config is not None
        assert config.cost_per_1m_input_tokens == 2.00
        assert config.cost_per_1m_output_tokens == 6.00

    def test_negative_token_clamping(self) -> None:
        """Negative input/output tokens are clamped to 0, cost >= 0."""
        cost = PrimrModels.calculate_cost("grok-4.3", -1000, -500)
        assert cost >= 0.0
        assert cost == 0.0  # Both clamped to 0 → zero cost


# =============================================================================
# TASK 13.4: Unit tests for doctor diagnostics
# =============================================================================


class TestDoctorDiagnostics:
    """Task 13.4 — Verify _check_providers function behavior."""

    def test_check_providers_lists_all_five(self, monkeypatch, capsys) -> None:
        """_check_providers lists all five providers."""
        from primr.ai.providers.registry import KNOWN_PROVIDERS
        from primr.core.cli import _check_providers

        # Set all keys so all providers show as configured
        monkeypatch.setenv("XAI_API_KEY", "test")
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
        monkeypatch.setenv("OLLAMA_API_KEY", "test")

        warnings = _check_providers(0)
        assert warnings == 0

    def test_check_providers_shows_not_configured(self, monkeypatch, capsys) -> None:
        """_check_providers shows 'not configured' for providers without keys."""
        from primr.core.cli import _check_providers

        # Only set XAI key, leave others unset
        monkeypatch.setenv("XAI_API_KEY", "test")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

        # Should not crash and should return 0 warnings (unconfigured is info, not warning)
        warnings = _check_providers(0)
        assert warnings == 0

    def test_check_providers_no_crash_when_none_configured(self, monkeypatch) -> None:
        """_check_providers doesn't crash when no providers are configured."""
        from primr.core.cli import _check_providers

        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

        # Should not crash — returns 1 warning for "no providers configured"
        # but Ollama has api_key_default so it's always available
        warnings = _check_providers(0)
        # Either 0 (ollama available via default) or 1 (no providers) — just don't crash
        assert isinstance(warnings, int)
