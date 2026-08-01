"""Capability-router wiring for fast.trust_polish."""

from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_trust import polish_and_gate_fast_report


def _route(
    *,
    execution_mode: str = "llm",
    model_name: str = "routed-writer",
    profile: InferenceProfile = InferenceProfile.CLOUD,
    reasons: tuple[str, ...] = ("test",),
) -> StageModelRoute:
    return StageModelRoute(
        stage_id="fast.trust_polish",
        profile=profile,
        model_name=model_name,
        backend_id=model_name or "unavailable",
        backend_kind="cloud" if execution_mode == "llm" else "host_agent",
        billing_mode="metered_api",
        estimated_cost_usd=0.01,
        expected_input_tokens=65_000,
        expected_output_tokens=8_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def test_trust_polish_skips_llm_when_route_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(
            execution_mode="unavailable",
            model_name="",
            profile=InferenceProfile.AGENT,
            reasons=("agent_profile_unavailable",),
        ),
    )
    called = {"polish": False, "repair": False}

    def boom_polish(*a, **k):
        called["polish"] = True
        raise AssertionError("polish must not run")

    def boom_repair(*a, **k):
        called["repair"] = True
        raise AssertionError("repair must not run")

    monkeypatch.setattr("primr.core.research_agent._polish_fast_report_for_trust", boom_polish)
    monkeypatch.setattr(
        "primr.core.research_agent._repair_fast_report_citation_integrity", boom_repair
    )
    monkeypatch.setattr(
        "primr.core.fast_run_trust._compute_fast_report_qa_metrics",
        lambda *a, **k: {
            "confidence_labels": 0,
            "citations_used": 0,
            "citations_defined": 0,
            "sections_with_validate": 0,
            "section_count": 1,
            "qa_gate_passed": False,
            "missing_citations": 0,
        },
    )
    monkeypatch.setattr("primr.core.fast_run_trust._clean_fast_report_output", lambda r: r)
    monkeypatch.setattr(
        "primr.core.fast_run_trust._normalize_fast_citations",
        lambda r, source_urls=None: r,
    )
    monkeypatch.setattr(
        "primr.core.fast_run_trust._enforce_fast_section_quality_guards",
        lambda r: r,
    )
    monkeypatch.setattr(
        "primr.core.fast_run_trust.compute_repair_report",
        lambda a, b: {
            "writer_output_clean": True,
            "scaffolding_removed": 0,
            "chars_removed": 0,
        },
    )
    monkeypatch.setattr(
        "primr.core.fast_run_trust.label_citations_trust_row",
        lambda *a, **k: None,
    )

    result = polish_and_gate_fast_report(
        company_label="ExampleCo",
        website=None,
        report_content="## Overview\nbody",
        source_urls=[],
        grok_writing="legacy-writer",
        folder_path=str(tmp_path),
        unresolved_contradictions=0,
    )
    assert result.report_content == "## Overview\nbody"
    assert called["polish"] is False
    assert called["repair"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.trust_polish"
    assert routes[-1]["outcome"] == "fallback"
