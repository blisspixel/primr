"""Capability-router wiring for optional fast.label_honesty."""

from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_trust import _maybe_apply_label_honesty
from primr.qa.label_honesty import LabelHonestyResult


def _route(
    *,
    execution_mode: str = "llm",
    model_name: str = "utility-model",
    profile: InferenceProfile = InferenceProfile.CLOUD,
    reasons: tuple[str, ...] = ("test",),
) -> StageModelRoute:
    return StageModelRoute(
        stage_id="fast.label_honesty",
        profile=profile,
        model_name=model_name,
        backend_id=model_name or "unavailable",
        backend_kind="cloud" if execution_mode == "llm" else "host_agent",
        billing_mode="metered_api",
        estimated_cost_usd=0.01,
        expected_input_tokens=12_000,
        expected_output_tokens=2_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def test_label_honesty_skips_judge_when_route_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("PRIMR_LABEL_HONESTY", "1")
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(
            execution_mode="unavailable",
            model_name="",
            profile=InferenceProfile.AGENT,
            reasons=("agent_profile_unavailable",),
        ),
    )
    called = {"apply": False}

    def boom(*a, **k):
        called["apply"] = True
        raise AssertionError("judge must not run when route is unavailable")

    monkeypatch.setattr("primr.qa.label_honesty.apply_label_honesty", boom)

    out = _maybe_apply_label_honesty("## S\nbody (Confirmed)", str(tmp_path))
    assert out == "## S\nbody (Confirmed)"
    assert called["apply"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.label_honesty"
    assert routes[-1]["outcome"] == "fallback"


def test_label_honesty_records_selected_route_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("PRIMR_LABEL_HONESTY", "1")
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(),
    )
    monkeypatch.setattr(
        "primr.qa.label_honesty.apply_label_honesty",
        lambda report: LabelHonestyResult(report_content=report, downgrades=()),
    )

    out = _maybe_apply_label_honesty("## S\nbody (Confirmed)", str(tmp_path))
    assert out == "## S\nbody (Confirmed)"
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.label_honesty"
    assert routes[-1]["outcome"] == "selected"
