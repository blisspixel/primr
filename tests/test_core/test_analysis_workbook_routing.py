"""Capability-router wiring for fast.analysis_workbook generation."""

from __future__ import annotations

from types import SimpleNamespace

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_workbook import generate_analysis_workbook


class _Recovery:
    def __init__(self, output: str = "workbook body"):
        self.output = output

    def run(self, *a, **k):  # pragma: no cover - not used
        return self


def _route(
    *,
    execution_mode: str = "llm",
    model_name: str = "routed-workbook-model",
    profile: InferenceProfile = InferenceProfile.CLOUD,
    reasons: tuple[str, ...] = ("test",),
) -> StageModelRoute:
    return StageModelRoute(
        stage_id="fast.analysis_workbook",
        profile=profile,
        model_name=model_name,
        backend_id=model_name or "unavailable",
        backend_kind="cloud" if execution_mode == "llm" else "host_agent",
        billing_mode="metered_api",
        estimated_cost_usd=0.02,
        expected_input_tokens=180_000,
        expected_output_tokens=18_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def _call(monkeypatch, tmp_path, *, route: StageModelRoute, failover_output: str = "WB"):
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: route,
    )
    monkeypatch.setattr("primr.ai.stage_routing.capture_stage_usage", dict)
    monkeypatch.setattr("primr.ai.stage_routing.stage_usage_delta", lambda before: None)

    captured: dict[str, object] = {}

    def fake_recovery(executor, fn, folder_path):
        return SimpleNamespace(success=True, output=fn(), skip_reason=None)

    monkeypatch.setattr("primr.pipeline.integration.analysis_with_recovery", fake_recovery)

    def fake_failover(role, prompt, **kwargs):
        captured["preferred_model"] = kwargs.get("preferred_model")
        return failover_output

    monkeypatch.setattr("primr.core.fast_run_workbook.call_with_failover", fake_failover)

    workbook, session = generate_analysis_workbook(
        company_label="ExampleCo",
        website="https://example.co",
        raw_corpus="corpus",
        external_sources_raw="external",
        combined_insights="insights fallback",
        grok_reasoning="legacy-reasoning",
        grok_reasoning_effort=None,
        continuous_reasoning=False,
        reasoning_session=None,
        recovery_executor=object(),
        folder_path=str(tmp_path),
        total_phases=6,
    )
    return workbook, session, captured


def test_workbook_uses_routed_preferred_model(monkeypatch, tmp_path) -> None:
    workbook, _session, captured = _call(
        monkeypatch,
        tmp_path,
        route=_route(model_name="routed-workbook-model"),
    )
    assert workbook == "WB"
    assert captured["preferred_model"] == "routed-workbook-model"
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["stage_id"] == "fast.analysis_workbook"
    assert routes[-1]["outcome"] == "selected"


def test_workbook_fails_closed_when_agent_unavailable(monkeypatch, tmp_path) -> None:
    called = {"failover": False}

    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(
            execution_mode="unavailable",
            model_name="",
            profile=InferenceProfile.AGENT,
            reasons=("agent_profile_unavailable",),
        ),
    )

    def boom(*a, **k):
        called["failover"] = True
        raise AssertionError("must not call LLM when route unavailable")

    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", boom)
    monkeypatch.setattr(
        "primr.pipeline.integration.analysis_with_recovery",
        boom,
    )

    workbook, session = generate_analysis_workbook(
        company_label="ExampleCo",
        website=None,
        raw_corpus="corpus",
        external_sources_raw="external",
        combined_insights="insights fallback",
        grok_reasoning="legacy-reasoning",
        grok_reasoning_effort=None,
        continuous_reasoning=False,
        reasoning_session=None,
        recovery_executor=object(),
        folder_path=str(tmp_path),
        total_phases=6,
    )

    assert workbook == "insights fallback"
    assert session is None
    assert called["failover"] is False
    from primr.core.run_state_io import _load_run_state

    routes = _load_run_state(str(tmp_path)).get("stage_routes") or []
    assert routes
    assert routes[-1]["outcome"] == "fallback"
    assert routes[-1]["failure_class"] == "agent_profile_unavailable"
