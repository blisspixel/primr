"""Tests for the registered cross-provider eval profile slots.

Focus on the May-2026 PRO-tier head-to-head (Gemini 3.1 Pro reference vs
Gemini 3.5 Flash candidate) added for the eval-gated repoint decision. Importing
the module registers the slots as a side effect.
"""

from __future__ import annotations

import primr.config.eval_profiles  # noqa: F401 - import registers the slots
from primr.core.model_eval import get_eval_profile, list_eval_profile_names


class TestProTierEvalSlots:
    def test_both_slots_registered(self):
        names = list_eval_profile_names()
        assert "protier-gemini31pro" in names
        assert "protier-gemini35flash" in names
        assert "protier-gemini36flash" in names
        assert "protier-gemini37flash" in names

    def test_reference_uses_31_pro(self):
        slot = get_eval_profile("protier-gemini31pro")
        assert slot.recipe.writing == "gemini-3.1-pro-preview"
        assert slot.recipe.reasoning == "grok-4.3"

    def test_candidate_uses_35_flash(self):
        slot = get_eval_profile("protier-gemini35flash")
        assert slot.recipe.writing == "gemini-3.5-flash"
        assert slot.recipe.reasoning == "grok-4.3"

    def test_candidate_is_cheaper_than_reference(self):
        """The whole point of the repoint: 3.5 Flash is the cheaper writer."""
        ref = get_eval_profile("protier-gemini31pro")
        cand = get_eval_profile("protier-gemini35flash")
        assert cand.estimated_cost_usd < ref.estimated_cost_usd

    def test_candidate_writing_model_is_registered(self):
        """The candidate's writing model must exist in the model registry."""
        from primr.config.models import PrimrModels

        cfg = PrimrModels.get_model_config("gemini-3.5-flash")
        assert cfg is not None
        assert cfg.provider == "google"

    def test_current_flash_candidates_are_registered_without_routing_change(self):
        from primr.config.models import PrimrModels

        candidate_36 = get_eval_profile("protier-gemini36flash")
        candidate_37 = get_eval_profile("protier-gemini37flash")
        assert candidate_36.recipe.writing == "gemini-3.6-flash"
        assert candidate_37.recipe.writing == "gemini-3.7-flash"
        assert PrimrModels.get_model_config(candidate_37.recipe.writing) is not None
        assert PrimrModels.PRO_MODEL == "gemini-3.1-pro-preview"


class TestGrokPromotionCandidates:
    def test_grok_candidates_registered(self):
        """Versioned flagship candidates exist without changing the hybrid default."""
        names = list_eval_profile_names()
        assert "grok43-flashlite" in names
        assert "grok45-flashlite" in names
        assert "grok46-flashlite" in names
        baseline = get_eval_profile("grok43-flashlite")
        candidate_45 = get_eval_profile("grok45-flashlite")
        candidate_46 = get_eval_profile("grok46-flashlite")
        assert baseline.recipe.reasoning == "grok-4.3"
        assert candidate_45.recipe.reasoning == "grok-4.5"
        assert candidate_46.recipe.reasoning == "grok-4.6"
        assert candidate_46.recipe.writing == "gemini-3.1-flash-lite"
        assert candidate_46.estimated_cost_usd > baseline.estimated_cost_usd


class TestOpenAICurrentCandidate:
    def test_gpt56_luna_candidate_is_registered_without_routing_change(self):
        from primr.config.models import PrimrModels

        slot = get_eval_profile("grok43-luna")
        assert slot.recipe.writing == "gpt-5.6-luna"
        assert PrimrModels.get_model_config(slot.recipe.writing) is not None
        assert PrimrModels.GROK_MODEL == "grok-4.3"


class TestPremiumAnthropicSlots:
    def test_premium_sonnet_slot_uses_current_sonnet(self):
        from primr.config.models import ModelRegistry

        slot = get_eval_profile("premium-sonnet-write")
        assert slot.recipe.writing == ModelRegistry.ANTHROPIC_SONNET.name
