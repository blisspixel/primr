"""
Tests for the routing layer (`primr.ai.routing`).

These pin the role-based dispatch policy:

- Utility tier prefers Grok 4.20-NR when XAI_API_KEY is set, else Gemini Flash.
- Writing tier prefers Grok 4.20-NR when XAI_API_KEY is set, else Pro model.
- Reasoning tier prefers Grok 4.3 when XAI_API_KEY is set, else Pro model.
- PRO is a legacy alias for REASONING.

v1.24.0 added the WRITING and REASONING role split (was just UTILITY/PRO) to
let the cross-provider eval test recipes that pair a cheap writer with an
expensive reasoner. Recipe-override mode (set_active_eval_recipe) lets the
eval generation runner force a specific model for each role per run.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.ai.providers import OpenAICompatibleProvider, Provider
from primr.ai.routing import (
    EvalRecipeOverride,
    Role,
    get_active_eval_recipe,
    get_provider_for_model,
    pick_model_for_legacy_type,
    pick_model_for_role,
    reset_active_eval_recipe,
    set_active_eval_recipe,
)
from primr.config.models import PrimrModels
from primr.core.model_eval import ProfileRecipe

# All env-keyed provider API keys. Tests must scrub these so the real .env
# doesn't bleed into assertions about which model wins for a given key combo.
_PROVIDER_API_KEY_VARS = (
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def _scrubbed_env(**overrides: str) -> dict[str, str]:
    """Return current env with all provider API keys removed, plus overrides."""
    base = {
        k: v
        for k, v in __import__("os").environ.items()
        if k not in _PROVIDER_API_KEY_VARS
    }
    base.update(overrides)
    return base


class TestPickModelForRole:
    """v1.24.0 routing policy:

    - UTILITY: GEMINI_API_KEY wins -> gemini-3-flash-preview; else XAI -> grok-4.20-NR
    - WRITING: GEMINI_API_KEY wins -> gemini-3.1-flash-lite (v1.24.0 winner);
      else XAI -> grok-4.20-NR (legacy fallback at $4.27/run); else Pro model
    - REASONING / PRO: XAI -> grok-4.3; else Pro model
    """

    def test_utility_prefers_gemini_when_gemini_key_set(self) -> None:
        env = _scrubbed_env(GEMINI_API_KEY="test-gemini", XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.UTILITY) == PrimrModels.FLASH_MODEL

    def test_utility_falls_back_to_grok_when_only_xai_key_set(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.UTILITY) == PrimrModels.GROK_MODEL_WRITING

    def test_utility_falls_back_to_gemini_flash_with_no_keys(self) -> None:
        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.UTILITY) == PrimrModels.FLASH_MODEL

    def test_writing_prefers_flash_lite_when_gemini_key_set(self) -> None:
        """v1.24.0 winner: Gemini 3.1 Flash-Lite for bulk writing."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(GEMINI_API_KEY="test-gemini", XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.WRITING)
                == ModelRegistry.GEMINI_3_1_FLASH_LITE.name
            )

    def test_writing_falls_back_to_grok_when_only_xai_key_set(self) -> None:
        """Legacy XAI-only path: stays on grok-4.20-NR (the ~$4.27/run default)."""
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.WRITING) == PrimrModels.GROK_MODEL_WRITING

    def test_writing_falls_back_to_pro_model_with_no_keys(self) -> None:
        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.WRITING) == PrimrModels.PRO_MODEL

    def test_reasoning_picks_grok_43_when_xai_key_set(self) -> None:
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.REASONING) == PrimrModels.GROK_MODEL_43

    def test_reasoning_picks_grok_43_when_both_keys_set(self) -> None:
        """Reasoning prefers Grok 4.3 regardless of Gemini availability."""
        env = _scrubbed_env(XAI_API_KEY="test-xai", GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.REASONING) == PrimrModels.GROK_MODEL_43

    def test_reasoning_falls_back_to_pro_model_without_xai_key(self) -> None:
        env = _scrubbed_env(GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.REASONING) == PrimrModels.PRO_MODEL

    def test_pro_legacy_alias_routes_to_reasoning(self) -> None:
        """Role.PRO is a back-compat alias — should match REASONING behavior."""
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.PRO) == pick_model_for_role(Role.REASONING)

        env = _scrubbed_env()
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.PRO) == pick_model_for_role(Role.REASONING)

    def test_role_accepts_string_alias(self) -> None:
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(XAI_API_KEY="test-xai", GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role("utility") == PrimrModels.FLASH_MODEL
            assert (
                pick_model_for_role("writing") == ModelRegistry.GEMINI_3_1_FLASH_LITE.name
            )
            assert pick_model_for_role("reasoning") == PrimrModels.GROK_MODEL_43


class TestProviderAwareFallbackChain:
    """v1.24.x: when a user has only one provider's keys, routing picks that
    provider's cheapest-quality models for each role.

    Priority chain:
    - UTILITY  : GEMINI > OPENAI > ANTHROPIC > XAI > FLASH_MODEL fallback
    - WRITING  : GEMINI > OPENAI > ANTHROPIC > XAI > PRO_MODEL fallback
    - REASONING: XAI > GEMINI > OPENAI > ANTHROPIC > PRO_MODEL fallback
    """

    def test_openai_only_writing(self) -> None:
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(OPENAI_API_KEY="test-openai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.WRITING)
                == ModelRegistry.OPENAI_GPT_5_4_NANO.name
            )

    def test_openai_only_utility(self) -> None:
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(OPENAI_API_KEY="test-openai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.UTILITY)
                == ModelRegistry.OPENAI_GPT_5_4_NANO.name
            )

    def test_openai_only_reasoning(self) -> None:
        """OpenAI-only → o4-mini for reasoning (cheaper than gpt-5.4)."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(OPENAI_API_KEY="test-openai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.REASONING) == ModelRegistry.OPENAI_O4_MINI.name
            )

    def test_anthropic_only_writing(self) -> None:
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(ANTHROPIC_API_KEY="test-anthropic")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.WRITING) == ModelRegistry.ANTHROPIC_HAIKU.name
            )

    def test_anthropic_only_utility(self) -> None:
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(ANTHROPIC_API_KEY="test-anthropic")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.UTILITY) == ModelRegistry.ANTHROPIC_HAIKU.name
            )

    def test_anthropic_only_reasoning(self) -> None:
        """Anthropic-only → Sonnet 4.6 for reasoning (Opus is too expensive as default)."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(ANTHROPIC_API_KEY="test-anthropic")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.REASONING)
                == ModelRegistry.ANTHROPIC_SONNET.name
            )

    def test_gemini_only_writing(self) -> None:
        """Gemini-only → 3.1 Flash-Lite for writing (v1.24.0 winner)."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.WRITING)
                == ModelRegistry.GEMINI_3_1_FLASH_LITE.name
            )

    def test_gemini_only_reasoning(self) -> None:
        """Gemini-only → Pro model (gemini-3.1-pro-preview)."""
        env = _scrubbed_env(GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.REASONING) == PrimrModels.PRO_MODEL

    def test_priority_gemini_beats_openai_for_writing(self) -> None:
        """When both Gemini and OpenAI keys are set, Gemini wins writing tier."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(
            GEMINI_API_KEY="test-gemini", OPENAI_API_KEY="test-openai"
        )
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_role(Role.WRITING)
                == ModelRegistry.GEMINI_3_1_FLASH_LITE.name
            )

    def test_priority_xai_beats_others_for_reasoning(self) -> None:
        """XAI's Grok 4.3 cached-input is cheapest; wins reasoning regardless."""
        env = _scrubbed_env(
            XAI_API_KEY="test-xai",
            GEMINI_API_KEY="test-gemini",
            OPENAI_API_KEY="test-openai",
            ANTHROPIC_API_KEY="test-anthropic",
        )
        with patch.dict("os.environ", env, clear=True):
            assert pick_model_for_role(Role.REASONING) == PrimrModels.GROK_MODEL_43


class TestLegacyTypeMapping:
    """Legacy model_type strings -> Role mapping, post-v1.24.0 routing."""

    def test_legacy_utility_types_xai_only_path(self) -> None:
        """XAI-only -> Grok 4.20-NR for utility tier."""
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            for legacy_type in (
                "scraping",
                "link_selection",
                "filtering",
                "fast",
                "research",
                "summarization",
            ):
                assert (
                    pick_model_for_legacy_type(legacy_type)
                    == PrimrModels.GROK_MODEL_WRITING
                )

    def test_legacy_utility_types_gemini_wins(self) -> None:
        """With Gemini key set, utility tier prefers Gemini Flash (v1.24.0 default)."""
        env = _scrubbed_env(XAI_API_KEY="test-xai", GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            for legacy_type in (
                "scraping",
                "link_selection",
                "filtering",
                "fast",
                "research",
                "summarization",
            ):
                assert pick_model_for_legacy_type(legacy_type) == PrimrModels.FLASH_MODEL

    def test_legacy_writing_types_xai_only_path(self) -> None:
        """section_writing and report route to WRITING role; XAI-only -> Grok 4.20-NR."""
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            for legacy_type in ("section_writing", "report"):
                assert (
                    pick_model_for_legacy_type(legacy_type)
                    == PrimrModels.GROK_MODEL_WRITING
                )

    def test_legacy_writing_types_gemini_wins(self) -> None:
        """With Gemini key set, writing tier prefers Flash-Lite (v1.24.0 winner)."""
        from primr.config.models import ModelRegistry

        env = _scrubbed_env(XAI_API_KEY="test-xai", GEMINI_API_KEY="test-gemini")
        with patch.dict("os.environ", env, clear=True):
            for legacy_type in ("section_writing", "report"):
                assert (
                    pick_model_for_legacy_type(legacy_type)
                    == ModelRegistry.GEMINI_3_1_FLASH_LITE.name
                )

    def test_legacy_reasoning_types_map_to_reasoning_role(self) -> None:
        """analysis and reasoning route to REASONING which prefers Grok 4.3."""
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            for legacy_type in ("analysis", "reasoning"):
                assert (
                    pick_model_for_legacy_type(legacy_type) == PrimrModels.GROK_MODEL_43
                )

    def test_unknown_type_defaults_to_utility(self) -> None:
        # Unknown legacy strings should not crash; they map to utility role
        # so the call lands on a cheap model instead of an expensive Pro one.
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True):
            assert (
                pick_model_for_legacy_type("never-seen-before")
                == PrimrModels.GROK_MODEL_WRITING
            )


class TestEvalRecipeOverride:
    """Tests for the v1.24.0 recipe-override mechanism.

    The eval generation runner installs a ProfileRecipe to make one primr
    run use a specific slot's recipe. Tests that the override actually
    overrides default routing and cleans up after itself.
    """

    def test_no_override_returns_default(self) -> None:
        assert get_active_eval_recipe() is None

    def test_override_replaces_utility(self) -> None:
        recipe = ProfileRecipe(utility="gpt-5.4-nano")
        with EvalRecipeOverride(recipe):
            assert pick_model_for_role(Role.UTILITY) == "gpt-5.4-nano"

    def test_override_replaces_writing(self) -> None:
        recipe = ProfileRecipe(writing="gemini-3.1-flash-lite")
        with EvalRecipeOverride(recipe):
            assert pick_model_for_role(Role.WRITING) == "gemini-3.1-flash-lite"

    def test_override_replaces_reasoning(self) -> None:
        recipe = ProfileRecipe(reasoning="claude-opus-4-8")
        with EvalRecipeOverride(recipe):
            assert pick_model_for_role(Role.REASONING) == "claude-opus-4-8"

    def test_override_replaces_legacy_pro_alias(self) -> None:
        """Role.PRO with override should still hit the recipe's reasoning slot."""
        recipe = ProfileRecipe(reasoning="claude-opus-4-8")
        with EvalRecipeOverride(recipe):
            assert pick_model_for_role(Role.PRO) == "claude-opus-4-8"

    def test_partial_recipe_falls_through_for_unset_roles(self) -> None:
        """A recipe with only writing set should override writing but leave
        reasoning and utility on default routing.

        Uses XAI-only env so default routing predictably returns Grok models
        (the v1.24.0 Gemini-prefer rule would otherwise change utility's default).
        """
        recipe = ProfileRecipe(writing="gemini-3.1-flash-lite")
        env = _scrubbed_env(XAI_API_KEY="test-xai")
        with patch.dict("os.environ", env, clear=True), EvalRecipeOverride(recipe):
            assert pick_model_for_role(Role.WRITING) == "gemini-3.1-flash-lite"
            # Reasoning and utility still hit XAI-only defaults.
            assert pick_model_for_role(Role.REASONING) == PrimrModels.GROK_MODEL_43
            assert (
                pick_model_for_role(Role.UTILITY) == PrimrModels.GROK_MODEL_WRITING
            )

    def test_context_manager_clears_on_exit(self) -> None:
        recipe = ProfileRecipe(utility="gpt-5.4-nano")
        with EvalRecipeOverride(recipe):
            assert get_active_eval_recipe() is recipe
        # After exit the override is gone.
        assert get_active_eval_recipe() is None

    def test_context_manager_clears_on_exception(self) -> None:
        recipe = ProfileRecipe(utility="gpt-5.4-nano")
        with pytest.raises(RuntimeError, match="boom"), EvalRecipeOverride(recipe):
            raise RuntimeError("boom")
        # Even if the block raised, override is cleared.
        assert get_active_eval_recipe() is None

    def test_set_and_reset_via_token(self) -> None:
        """Lower-level set/reset API works for callers that don't want a context manager."""
        recipe = ProfileRecipe(reasoning="grok-4.3", writing="gemini-3.1-flash-lite")
        token = set_active_eval_recipe(recipe)
        try:
            assert get_active_eval_recipe() is recipe
            assert pick_model_for_role(Role.REASONING) == "grok-4.3"
        finally:
            reset_active_eval_recipe(token)
        assert get_active_eval_recipe() is None

    def test_extra_dict_provides_override(self) -> None:
        """Forward-compat: recipe.extra dict supports new role names."""
        recipe = ProfileRecipe(extra={"utility": "phi4:14b"})
        with EvalRecipeOverride(recipe):
            assert pick_model_for_role(Role.UTILITY) == "phi4:14b"

    def test_none_recipe_is_a_noop_clear(self) -> None:
        """Passing None to EvalRecipeOverride explicitly clears any active recipe."""
        outer_recipe = ProfileRecipe(utility="gpt-5.4-nano")
        with EvalRecipeOverride(outer_recipe):
            with EvalRecipeOverride(None):
                # Inner block has no active recipe; falls back to default.
                # Use XAI-only env so the default is predictable (Gemini-prefer
                # rule would otherwise route utility to Gemini Flash).
                env = _scrubbed_env(XAI_API_KEY="test-xai")
                with patch.dict("os.environ", env, clear=True):
                    assert (
                        pick_model_for_role(Role.UTILITY) == PrimrModels.GROK_MODEL_WRITING
                    )
            # Outer recipe is back in scope after inner exits.
            assert get_active_eval_recipe() is outer_recipe


class TestGetProviderForModel:
    def test_xai_model_returns_openai_compatible_provider(self) -> None:
        provider = get_provider_for_model(PrimrModels.GROK_MODEL_WRITING)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.name == "xai"

    def test_gemini_model_returns_provider_with_gemini_name(self) -> None:
        provider = get_provider_for_model(PrimrModels.PRO_MODEL)
        assert isinstance(provider, Provider)
        assert provider.name == "gemini"

    def test_unknown_model_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            get_provider_for_model("definitely-not-a-real-model")
