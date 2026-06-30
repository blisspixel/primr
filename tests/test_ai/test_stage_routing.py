from __future__ import annotations

import json
from unittest.mock import MagicMock

from primr.ai.capability_routing import InferenceProfile
from primr.ai.host_agent_cli import codex_cli_backend
from primr.ai.provider_availability import ProviderQuotaSnapshot, QuotaWindow
from primr.ai.stage_routing import (
    INFERENCE_PROFILE_ENV,
    capture_stage_usage,
    current_inference_profile,
    record_stage_route_usage,
    resolve_stage_model,
    stage_usage_delta,
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
    assert route.availability is not None
    assert route.availability["available"] is True
    assert route.availability["provider"] == "gemini"
    assert route.availability["credential_source"] == "env"


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


def test_hiring_signals_cloud_route_uses_stage_token_budget(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    route = resolve_stage_model(
        "fast.hiring_signals",
        legacy_model_type="fast",
        profile="cloud",
    )

    assert route.routed is True
    assert route.model_name == PrimrModels.FLASH_MODEL
    assert route.expected_input_tokens == 45_000
    assert route.expected_output_tokens == 4_000
    assert "meets_context" in route.reasons


def test_agent_profile_routes_to_available_codex_host_runner(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr(
        "primr.ai.stage_routing._supported_host_agent_backends",
        lambda stage_id: (
            (codex_cli_backend(available=True),) if stage_id == "fast.source_relevance" else ()
        ),
    )

    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="agent",
    )

    assert route.routed is True
    assert route.profile is InferenceProfile.AGENT
    assert route.model_name == "codex-cli"
    assert route.backend_kind == "host_agent"
    assert route.billing_mode == "host_plan_usage"
    assert route.execution_mode == "host_agent"
    assert route.host_agent_kind == "codex"
    assert route.estimated_cost_usd == 0.0
    assert "host_plan_usage" in route.reasons
    assert route.log_metadata()["execution_mode"] == "host_agent"


def test_hybrid_scrape_summary_preserves_cloud_until_host_stage_is_wired(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setattr(
        "primr.ai.stage_routing._supported_host_agent_backends",
        lambda stage_id: (
            (codex_cli_backend(available=True),) if stage_id == "fast.source_relevance" else ()
        ),
    )

    route = resolve_stage_model(
        "fast.scrape_summary",
        legacy_model_type="scraping",
        profile="hybrid",
    )

    assert route.routed is True
    assert route.profile is InferenceProfile.HYBRID
    assert route.model_name == PrimrModels.SCRAPING_MODEL
    assert route.backend_kind == "cloud_api"
    assert route.execution_mode == "llm"


def test_agent_profile_for_unwired_stage_does_not_fall_back_to_cloud(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setattr(
        "primr.ai.stage_routing._supported_host_agent_backends",
        lambda stage_id: (
            (codex_cli_backend(available=True),) if stage_id == "fast.source_relevance" else ()
        ),
    )

    route = resolve_stage_model(
        "fast.scrape_summary",
        legacy_model_type="scraping",
        profile="agent",
    )

    assert route.routed is False
    assert route.model_name == ""
    assert route.execution_mode == "unavailable"
    assert route.reasons == ("agent_profile_unavailable",)


def test_agent_profile_without_runner_does_not_fall_back_to_cloud(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setattr(
        "primr.ai.stage_routing._supported_host_agent_backends", lambda stage_id: ()
    )

    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="agent",
    )

    assert route.routed is False
    assert route.profile is InferenceProfile.AGENT
    assert route.model_name == ""
    assert route.backend_id == "agent-profile-unavailable"
    assert route.execution_mode == "unavailable"
    assert route.billing_mode == "unknown"
    assert route.reasons == ("agent_profile_unavailable",)
    assert "profile_disallows_backend" in route.rejections


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


def test_provider_availability_snapshot_marks_runtime_route_unavailable(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    snapshot = ProviderQuotaSnapshot(
        provider="google",
        windows=(QuotaWindow("requests_per_day", used_percent=100.0),),
        metadata={
            "configured": True,
            "credential_source": "env",
            "quota_source": "not_collected",
        },
    )

    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="cloud",
        availability_snapshots=(snapshot,),
    )

    assert route.routed is False
    assert route.model_name == PrimrModels.FLASH_MODEL
    assert route.reasons == ("legacy_fallback",)
    assert "unavailable" in route.rejections
    assert route.availability == {
        "available": False,
        "provider": "google",
        "quota_source": "not_collected",
        "stale": False,
        "headroom_percent": 0.0,
        "binding_window_label": "requests_per_day",
        "configured": True,
        "credential_source": "env",
    }
    assert route.log_metadata()["availability"] == route.availability


def test_default_availability_collection_skips_local_probe(monkeypatch) -> None:
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    collector = MagicMock(
        return_value=(
            ProviderQuotaSnapshot(
                provider="google",
                metadata={
                    "configured": True,
                    "credential_source": "env",
                    "quota_source": "not_collected",
                },
            ),
        )
    )
    monkeypatch.setattr("primr.ai.stage_routing.collect_provider_availability_snapshots", collector)

    route = resolve_stage_model(
        "fast.source_relevance",
        legacy_model_type="fast",
        profile="cloud",
    )

    collector.assert_called_once_with(include_local=False)
    assert route.routed is True
    assert route.availability is not None
    assert route.availability["configured"] is True
    assert route.availability["quota_source"] == "not_collected"


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


def test_record_stage_route_usage_appends_actual_usage_delta(tmp_path, monkeypatch) -> None:
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
        usage_delta={
            "actual_input_tokens": 100,
            "actual_output_tokens": 25,
            "actual_cached_input_tokens": 10,
            "actual_cost_usd": 0.00001234,
            "actual_usage_by_model": {
                route.model_name: {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "cached_input_tokens": 10,
                    "actual_cost_usd": 0.00001234,
                }
            },
        },
    )

    state = json.loads((tmp_path / "_run_state.json").read_text(encoding="utf-8"))
    [record] = state["stage_routes"]
    assert record["actual_input_tokens"] == 100
    assert record["actual_output_tokens"] == 25
    assert record["actual_cached_input_tokens"] == 10
    assert record["actual_cost_usd"] == 0.00001234
    assert record["actual_usage_by_model"][route.model_name]["cached_input_tokens"] == 10
    assert "prompt" not in record
    assert "response" not in record


def test_stage_usage_delta_reports_body_free_model_cost() -> None:
    from primr.ai.grok_client import _mirror_session_usage, reset_grok_session

    reset_grok_session()
    before = capture_stage_usage()
    _mirror_session_usage(PrimrModels.FLASH_MODEL, 1_000, 250, cached_input_tokens=100)

    delta = stage_usage_delta(before)
    expected_cost = PrimrModels.calculate_cost(
        PrimrModels.FLASH_MODEL,
        1_000,
        250,
        cached_input_tokens=100,
        prompt_tokens=1_000,
    )

    assert delta["actual_input_tokens"] == 1_000
    assert delta["actual_output_tokens"] == 250
    assert delta["actual_cached_input_tokens"] == 100
    assert delta["actual_cost_usd"] == round(expected_cost, 8)
    assert delta["actual_usage_by_model"][PrimrModels.FLASH_MODEL] == {
        "input_tokens": 1_000,
        "output_tokens": 250,
        "cached_input_tokens": 100,
        "actual_cost_usd": round(expected_cost, 8),
    }

    reset_grok_session()


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
