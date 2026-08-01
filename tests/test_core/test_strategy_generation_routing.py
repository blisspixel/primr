"""Capability-router wiring for fast.strategy_generation."""

from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_strategy import run_strategy_phase


def _route(
    stage_id: str = "fast.strategy_generation",
    *,
    execution_mode: str = "llm",
    model_name: str = "routed-writer",
    profile: InferenceProfile = InferenceProfile.CLOUD,
    reasons: tuple[str, ...] = ("test",),
) -> StageModelRoute:
    return StageModelRoute(
        stage_id=stage_id,
        profile=profile,
        model_name=model_name,
        backend_id=model_name or "unavailable",
        backend_kind="cloud" if execution_mode == "llm" else "host_agent",
        billing_mode="metered_api",
        estimated_cost_usd=0.05,
        expected_input_tokens=160_000,
        expected_output_tokens=32_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def test_strategy_phase_skips_when_writing_route_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda stage_id, legacy_model_type="writing", **kwargs: _route(
            stage_id,
            execution_mode="unavailable",
            model_name="",
            profile=InferenceProfile.AGENT,
            reasons=("agent_profile_unavailable",),
        ),
    )
    called = {"failover": False}

    def boom(*a, **k):
        called["failover"] = True
        raise AssertionError("strategy LLM must not run when route is unavailable")

    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", boom)

    result = run_strategy_phase(
        has_strategies=True,
        ai_strategy=True,
        platforms=["azure"],
        strategy_types=None,
        company_label="ExampleCo",
        website=None,
        report_content="## Overview\nbody",
        analysis_workbook="wb",
        validated_source_urls=[],
        discovery_notes_content=None,
        refresh_vendor_research=False,
        grok_reasoning="legacy-r",
        grok_writing="legacy-w",
        folder_path=str(tmp_path),
        output_dir=str(tmp_path),
        diagnostics_dir=None,
        write_txt=False,
        recovery_executor=object(),
        total_phases=6,
    )
    assert result.strategy_paths == {}
    assert called["failover"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.strategy_generation"
    assert routes[-1]["outcome"] == "fallback"
