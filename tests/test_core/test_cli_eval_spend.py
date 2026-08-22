"""Approval-gate tests for billable ``primr --eval`` helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.cli_eval_spend import approve_eval_spend


def test_dry_run_stops_without_prompt(monkeypatch):
    prompted = []
    monkeypatch.setattr(
        "primr.core.cli_eval_spend.prompt_yes_no",
        lambda *a, **k: prompted.append(True) or True,
    )
    code = approve_eval_spend(
        SimpleNamespace(dry_run_requested=True, skip_confirm=False),
        4.0,
        "eval run-missing",
    )
    assert code == 0
    assert prompted == []


def test_skip_confirm_approves_without_prompt(monkeypatch):
    monkeypatch.setattr(
        "primr.core.cli_eval_spend.prompt_yes_no",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not prompt")),
    )
    assert (
        approve_eval_spend(
            SimpleNamespace(dry_run_requested=False, skip_confirm=True),
            4.0,
            "eval LLM judge",
        )
        is None
    )


@pytest.mark.parametrize("estimate", [float("nan"), float("inf"), -0.01])
def test_invalid_estimate_fails_closed_without_prompt(monkeypatch, estimate):
    prompt = MagicMock()
    monkeypatch.setattr("primr.core.cli_eval_spend.prompt_yes_no", prompt)

    assert (
        approve_eval_spend(
            SimpleNamespace(dry_run_requested=False, skip_confirm=True),
            estimate,
            "eval run-missing",
        )
        == 1
    )
    prompt.assert_not_called()


def test_eval_profile_cost_uses_planning_floor_not_cheap_history(monkeypatch):
    from primr.core.cli_eval_spend import estimate_eval_profile_cost
    from primr.utils.cost_estimator import CostEstimate

    monkeypatch.setattr(
        "primr.core.model_eval.get_eval_profile",
        lambda _profile: None,
    )

    def fake_estimate(mode, include_ai_strategy=False, use_historical=False, **kwargs):
        cost = 0.10 if use_historical else 4.27
        return CostEstimate(
            mode=mode,
            estimated_input_tokens=1,
            estimated_output_tokens=1,
            estimated_search_queries=0,
            input_cost=0.0,
            output_cost=cost,
            search_cost=0.0,
            total_cost=cost,
            duration_minutes="10-20",
            notes=["Based on 3 historical runs"] if use_historical else [],
        )

    monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", fake_estimate)
    assert estimate_eval_profile_cost("full") == 4.27


def test_execute_eval_run_missing_reserves_prior_run_estimates(tmp_path, monkeypatch):
    from primr.core.cli_eval_spend import execute_eval_run_missing
    from primr.utils.run_budget import get_run_budget

    active_ceilings: list[float] = []

    def research(**_kwargs):
        budget = get_run_budget()
        assert budget is not None
        active_ceilings.append(budget.max_cost)
        return "out.md"

    monkeypatch.setattr(
        "primr.core.model_eval.get_eval_profile",
        lambda _profile: SimpleNamespace(recipe=None, estimated_cost_usd=2.5),
    )
    execute_eval_run_missing(
        to_run=(
            ("ExampleCo", "full"),
            ("SampleWorks", "full"),
            ("ThirdCo", "full"),
        ),
        websites={
            "exampleco": "https://example.test",
            "sampleworks": "https://sample.test",
            "thirdco": "https://third.test",
        },
        eval_dir=tmp_path,
        max_cost_usd=6.0,
        output_dir=str(tmp_path),
        perform_research=research,
    )
    assert active_ceilings == [6.0, 3.5]
    assert get_run_budget() is None


@pytest.mark.parametrize("ceiling", [0.0, -1.0, float("nan"), float("inf")])
def test_execute_eval_run_missing_rejects_invalid_ceiling(tmp_path, ceiling):
    from primr.core.cli_eval_spend import execute_eval_run_missing

    with pytest.raises(ValueError, match="finite and positive"):
        execute_eval_run_missing(
            to_run=(),
            websites={},
            eval_dir=tmp_path,
            max_cost_usd=ceiling,
            output_dir=str(tmp_path),
            perform_research=MagicMock(),
        )


def test_decline_cancels(monkeypatch):
    monkeypatch.setattr("primr.core.cli_eval_spend.prompt_yes_no", lambda *a, **k: False)
    assert (
        approve_eval_spend(
            SimpleNamespace(dry_run_requested=False, skip_confirm=False),
            4.0,
            "eval run-missing",
        )
        == 1
    )
