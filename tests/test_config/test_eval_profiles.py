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


class TestGrok45PromotionCandidate:
    def test_grok45_flashlite_slot_registered(self):
        """Optional 4.5-reasoning candidate exists but is not the hybrid default."""
        names = list_eval_profile_names()
        assert "grok43-flashlite" in names
        assert "grok45-flashlite" in names
        baseline = get_eval_profile("grok43-flashlite")
        candidate = get_eval_profile("grok45-flashlite")
        assert baseline.recipe.reasoning == "grok-4.3"
        assert candidate.recipe.reasoning == "grok-4.5"
        assert candidate.recipe.writing == "gemini-3.1-flash-lite"
        assert candidate.estimated_cost_usd > baseline.estimated_cost_usd


class TestPremiumAnthropicSlots:
    def test_premium_sonnet_slot_uses_current_sonnet(self):
        from primr.config.models import ModelRegistry

        slot = get_eval_profile("premium-sonnet-write")
        assert slot.recipe.writing == ModelRegistry.ANTHROPIC_SONNET.name
