"""Capability-router wiring for fast.research_deepening gap analysis."""

from __future__ import annotations

from primr.ai.capability_routing import InferenceProfile
from primr.ai.stage_routing import StageModelRoute
from primr.core.fast_run_gaps import _fast_gap_analysis


def _route(
    *,
    execution_mode: str = "llm",
    model_name: str = "routed-reasoning-model",
    profile: InferenceProfile = InferenceProfile.CLOUD,
    reasons: tuple[str, ...] = ("test",),
) -> StageModelRoute:
    return StageModelRoute(
        stage_id="fast.research_deepening",
        profile=profile,
        model_name=model_name,
        backend_id=model_name or "unavailable",
        backend_kind="cloud" if execution_mode == "llm" else "host_agent",
        billing_mode="metered_api",
        estimated_cost_usd=0.01,
        expected_input_tokens=95_000,
        expected_output_tokens=5_000,
        routed=execution_mode == "llm",
        reasons=reasons,
        rejections=(),
        execution_mode=execution_mode,
    )


def test_gap_analysis_uses_routed_preferred_model(monkeypatch) -> None:
    captured: dict[str, object] = {}
    records: list[dict[str, object]] = []

    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(model_name="routed-reasoning-model"),
    )
    monkeypatch.setattr("primr.ai.stage_routing.capture_stage_usage", dict)
    monkeypatch.setattr("primr.ai.stage_routing.stage_usage_delta", lambda before: None)

    def fake_failover(role, prompt, **kwargs):
        captured["preferred_model"] = kwargs.get("preferred_model")
        captured["prompt"] = prompt
        return "GAP: funding\nQUERY: ExampleCo funding round\nPRIORITY: CRITICAL\n"

    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", fake_failover)

    def capture_record(folder_path, route, **kwargs):
        records.append({"folder": folder_path, "route": route, **kwargs})

    monkeypatch.setattr("primr.ai.stage_routing.record_stage_route_usage", capture_record)

    queries, text = _fast_gap_analysis(
        "ExampleCo",
        "https://example.co",
        "[Page: https://example.co]\nabout us",
        "[Source: https://news.example]\nnews",
        ["https://example.co"],
        model="legacy-model",
        folder_path="/tmp/run",
    )

    assert queries == ["ExampleCo funding round"]
    assert "funding" in text
    assert captured["preferred_model"] == "routed-reasoning-model"
    assert records
    assert records[0]["outcome"] == "selected"
    assert records[0]["output_items"] == 1


def test_gap_analysis_fails_closed_when_agent_profile_unavailable(monkeypatch) -> None:
    records: list[dict[str, object]] = []
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

    def fake_failover(*a, **k):
        called["failover"] = True
        raise AssertionError("cloud LLM must not run when route is unavailable")

    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", fake_failover)
    monkeypatch.setattr(
        "primr.ai.stage_routing.record_stage_route_usage",
        lambda folder_path, route, **kwargs: records.append(kwargs),
    )

    queries, text = _fast_gap_analysis(
        "ExampleCo",
        None,
        "corpus",
        "external",
        [],
        folder_path="/tmp/run",
    )

    assert queries == []
    assert "agent_profile_unavailable" in text
    assert called["failover"] is False
    assert records
    assert records[0]["outcome"] == "fallback"
    assert records[0]["failure_class"] == "agent_profile_unavailable"


def test_gap_analysis_records_failure_without_leaking_prompt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "primr.ai.stage_routing.resolve_stage_model",
        lambda *a, **k: _route(),
    )
    monkeypatch.setattr("primr.ai.stage_routing.capture_stage_usage", dict)
    monkeypatch.setattr("primr.ai.stage_routing.stage_usage_delta", lambda before: None)

    def boom(*a, **k):
        raise RuntimeError("provider down: secret-prompt-body")

    monkeypatch.setattr("primr.pipeline.llm_failover.call_with_failover", boom)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    queries, text = _fast_gap_analysis(
        "ExampleCo",
        None,
        "secret corpus body",
        "secret external body",
        ["https://example.co/secret"],
        folder_path=str(run_dir),
    )

    assert queries == []
    assert "failed" in text.lower()
    from primr.core.run_state_io import _load_run_state

    state = _load_run_state(str(run_dir))
    routes = state.get("stage_routes") or []
    assert routes
    record = routes[-1]
    assert record["outcome"] == "fallback"
    assert record["failure_class"] == "RuntimeError"
    assert record["stage_id"] == "fast.research_deepening"
    serialized = repr(record)
    assert "secret corpus body" not in serialized
    assert "secret-prompt-body" not in serialized
