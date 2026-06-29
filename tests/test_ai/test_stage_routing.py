from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import (
    INFERENCE_PROFILE_ENV,
    current_inference_profile,
    resolve_stage_model,
)
from primr.config.models import PrimrModels


def _clear_provider_env(monkeypatch) -> None:
    for name in ("GEMINI_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_current_inference_profile_defaults_to_cloud(monkeypatch) -> None:
    monkeypatch.delenv(INFERENCE_PROFILE_ENV, raising=False)

    assert current_inference_profile() is InferenceProfile.CLOUD


def test_invalid_inference_profile_falls_back_to_cloud(monkeypatch) -> None:
    monkeypatch.setenv(INFERENCE_PROFILE_ENV, "unsupported")

    assert current_inference_profile() is InferenceProfile.CLOUD


def test_source_relevance_cloud_route_uses_legacy_utility_model(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="cloud",
    )

    assert route.routed is True
    assert route.profile is InferenceProfile.CLOUD
    assert route.model_name == PrimrModels.FLASH_MODEL
    assert route.backend_id == PrimrModels.FLASH_MODEL
    assert route.billing_mode == "api_dollars"
    assert route.estimated_cost_usd is not None
    assert "meets_context" in route.reasons


def test_local_profile_records_rejection_and_preserves_legacy_model(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="local",
    )

    assert route.routed is False
    assert route.model_name == PrimrModels.FLASH_MODEL
    assert route.reasons == ("legacy_fallback",)
    assert "profile_disallows_backend" in route.rejections
