"""Capability-router wiring for premium.deep_research."""

from __future__ import annotations

import pytest

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import resolve_stage_model, stage_route_failure_class
from primr.config.models import PrimrModels


def test_premium_deep_research_routes_to_gemini_agent_when_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-route-test")
    route = resolve_stage_model(
        "premium.deep_research",
        legacy_model_type="reasoning",
        profile=InferenceProfile.CLOUD,
        availability_snapshots=(),
    )
    assert route.routed is True
    assert route.execution_mode == "llm"
    assert route.backend_id == PrimrModels.DEEP_RESEARCH_AGENT
    assert "supports_deep_research" in route.reasons or route.routed


def test_premium_deep_research_unavailable_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    route = resolve_stage_model(
        "premium.deep_research",
        legacy_model_type="reasoning",
        profile=InferenceProfile.CLOUD,
        availability_snapshots=(),
    )
    assert route.execution_mode == "unavailable"
    assert route.routed is False
    assert stage_route_failure_class(route) == "deep_research_backend_unavailable"


def test_premium_deep_research_agent_profile_fails_closed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-route-test")
    route = resolve_stage_model(
        "premium.deep_research",
        legacy_model_type="reasoning",
        profile=InferenceProfile.AGENT,
        availability_snapshots=(),
    )
    # No host deep-research adapter exists; agent profile must not launch Gemini.
    assert route.execution_mode == "unavailable"
    assert route.routed is False


@pytest.mark.asyncio
async def test_orchestrator_fails_closed_when_route_unavailable(monkeypatch, tmp_path):
    from primr.ai.stage_routing import StageModelRoute
    from primr.core.research_orchestrator import ResearchConfig, ResearchOrchestrator

    unavailable = StageModelRoute(
        stage_id="premium.deep_research",
        profile=InferenceProfile.AGENT,
        model_name="",
        backend_id="deep-research-unavailable",
        backend_kind="cloud_api",
        billing_mode="api_dollars",
        estimated_cost_usd=None,
        expected_input_tokens=500_000,
        expected_output_tokens=40_000,
        routed=False,
        reasons=("deep_research_backend_unavailable",),
        rejections=(),
        execution_mode="unavailable",
    )
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: unavailable,
    )
    launched = {"orchestrator": False}

    def boom(*a, **k):
        launched["orchestrator"] = True
        raise AssertionError("deep research must not launch when route is unavailable")

    monkeypatch.setattr("primr.core.research_orchestrator.get_deep_research_orchestrator", boom)

    orch = ResearchOrchestrator()
    result = await orch._run_deep_research_with_context(
        company_name="ExampleCo",
        website="https://example.co",
        config=ResearchConfig(),
        on_progress=None,
        folder_path=str(tmp_path),
    )
    assert result.success is False
    assert "unavailable" in (result.error or "").lower()
    assert launched["orchestrator"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "premium.deep_research"
    assert routes[-1]["outcome"] == "fallback"
