"""Capability-router wiring for fast.cross_validation."""

from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_validation import cross_validate_and_enrich


def _route(
    stage_id: str,
    *,
    execution_mode: str = "llm",
    model_name: str = "routed-model",
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
        estimated_cost_usd=0.02,
        expected_input_tokens=120_000,
        expected_output_tokens=10_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def test_cross_validation_fails_closed_when_route_unavailable(monkeypatch, tmp_path):
    def fake_resolve(stage_id, legacy_model_type="reasoning", **kwargs):
        return _route(
            stage_id,
            execution_mode="unavailable",
            model_name="",
            profile=InferenceProfile.AGENT,
            reasons=("agent_profile_unavailable",),
        )

    monkeypatch.setattr("primr.ai.stage_routing.resolve_stage_model", fake_resolve)
    called = {"cv": False}

    def boom(*a, **k):
        called["cv"] = True
        raise AssertionError("cross-validate must not run when route is unavailable")

    result = cross_validate_and_enrich(
        company_name="ExampleCo",
        company_label="ExampleCo",
        website=None,
        report_content="## Overview\n\nBody",
        source_urls=[],
        source_urls_seen=set(),
        review_report=boom,
        analysis_workbook="wb",
        grok_reasoning="legacy-r",
        grok_writing="legacy-w",
        reasoning_session=None,
        recovery_executor=object(),
        folder_path=str(tmp_path),
        total_phases=6,
    )
    assert result.report_content == "## Overview\n\nBody"
    assert result.sections_enriched == 0
    assert called["cv"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.cross_validation"
    assert routes[-1]["outcome"] == "fallback"
