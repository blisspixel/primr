"""Capability-router wiring for fast.report_sections."""

from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_sections import write_report_sections


def _route(
    *,
    execution_mode: str = "llm",
    model_name: str = "routed-writing-model",
    profile: InferenceProfile = InferenceProfile.CLOUD,
    reasons: tuple[str, ...] = ("test",),
) -> StageModelRoute:
    return StageModelRoute(
        stage_id="fast.report_sections",
        profile=profile,
        model_name=model_name,
        backend_id=model_name or "unavailable",
        backend_kind="cloud" if execution_mode == "llm" else "host_agent",
        billing_mode="metered_api",
        estimated_cost_usd=0.05,
        expected_input_tokens=140_000,
        expected_output_tokens=32_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def test_report_sections_fails_closed_when_writing_route_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(
            execution_mode="unavailable",
            model_name="",
            profile=InferenceProfile.AGENT,
            reasons=("agent_profile_unavailable",),
        ),
    )
    called = {"write": False}

    def boom(*a, **k):
        called["write"] = True
        raise AssertionError("section writer must not run when route is unavailable")

    monkeypatch.setattr("primr.core.research_agent._write_section_with_retry", boom)

    result = write_report_sections(
        company_label="ExampleCo",
        website=None,
        analysis_workbook="wb",
        raw_corpus="corpus",
        external_sources_raw="ext",
        source_urls=[],
        grok_writing="legacy-writer",
        recovery_executor=object(),
        folder_path=str(tmp_path),
        total_phases=6,
    )
    assert result.report_content is None
    assert called["write"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.report_sections"
    assert routes[-1]["outcome"] == "fallback"
    assert routes[-1]["failure_class"] == "agent_profile_unavailable"
