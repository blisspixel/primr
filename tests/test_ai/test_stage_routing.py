from __future__ import annotations

import json

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import (
    INFERENCE_PROFILE_ENV,
    current_inference_profile,
    record_stage_route_usage,
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
    assert route.expected_input_tokens == 18_000
    assert route.expected_output_tokens == 2_000
    assert "meets_context" in route.reasons


def test_scrape_summary_cloud_route_uses_stage_token_budget(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    route = resolve_stage_model(
        "fast.scrape_summary",
        legacy_model_type="scraping",
        profile="cloud",
    )

    assert route.routed is True
    assert route.model_name == PrimrModels.SCRAPING_MODEL
    assert route.expected_input_tokens == 70_000
    assert route.expected_output_tokens == 5_000
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


def test_record_stage_route_usage_appends_body_free_run_state(tmp_path, monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="cloud",
    )

    record_stage_route_usage(
        tmp_path,
        route,
        outcome="selected",
        input_items=10,
        output_items=4,
        duration_seconds=1.23456,
    )

    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    [record] = state["stage_routes"]
    assert record["stage_id"] == "fast.source_relevance"
    assert record["inference_profile"] == "cloud"
    assert record["backend_id"] == PrimrModels.FLASH_MODEL
    assert record["expected_input_tokens"] == 18_000
    assert record["expected_output_tokens"] == 2_000
    assert record["input_items"] == 10
    assert record["output_items"] == 4
    assert record["duration_seconds"] == 1.235
    assert "prompt" not in record
    assert "response" not in record


def test_record_stage_route_usage_caps_history(tmp_path, monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="cloud",
    )

    for i in range(205):
        record_stage_route_usage(tmp_path, route, outcome=f"selected-{i}")

    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    assert len(state["stage_routes"]) == 200
    assert state["stage_routes"][0]["outcome"] == "selected-5"
    assert state["stage_routes"][-1]["outcome"] == "selected-204"
