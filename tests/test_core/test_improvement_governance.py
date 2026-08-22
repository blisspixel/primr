"""Hermetic regression tests for improve and refine cost governance."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import primr.core.improvement_governance as governance
from primr.core.improvement_governance import (
    ImprovementBudgetError,
    ImprovementBudgetGate,
    ImprovementEstimate,
    ImprovementStageEstimate,
)


def _config(**overrides):
    values = {
        "improve_path": None,
        "improve_in_place": False,
        "improve_agentic": False,
        "refine_company": None,
        "refine_target_grade": 90.0,
        "dry_run_requested": False,
        "json_output": False,
        "skip_confirm": False,
        "budget_usd": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def bounded_estimate() -> ImprovementEstimate:
    return ImprovementEstimate(
        operation="agentic_improve",
        stages=(
            ImprovementStageEstimate("review", 1, 2, 0.10),
            ImprovementStageEstimate("polish", 1, 1, 0.20),
        ),
        model_names=("test-model",),
        estimated_time_range="1-2 min",
        cost_basis="test bound",
    )


def test_agentic_improve_estimate_has_three_task_ceiling(monkeypatch):
    monkeypatch.setattr(
        governance,
        "_routed_models",
        lambda: (
            "gemini-3-flash-preview",
            "gemini-3.1-pro-preview",
            "gemini-3-flash-preview",
        ),
    )

    estimate = governance.estimate_agentic_improve("report body", is_strategy=False)

    assert estimate.max_model_tasks == 3
    assert estimate.estimated_cost_usd > 0


def test_refine_estimate_has_bounded_full_loop(monkeypatch):
    monkeypatch.setattr(
        governance,
        "_routed_models",
        lambda: (
            "gemini-3-flash-preview",
            "gemini-3.1-pro-preview",
            "gemini-3-flash-preview",
        ),
    )

    estimate = governance.estimate_refine("report body")

    assert estimate.max_model_tasks == 249
    assert {stage.name for stage in estimate.stages} == {"regenerate", "acceptance"}


def test_budget_gate_reserves_stages_and_blocks_unquoted_repeat(bounded_estimate):
    gate = ImprovementBudgetGate(bounded_estimate, cap_usd=0.30)

    gate.before_model_stage("review")
    gate.before_model_stage("polish")

    assert gate.spent_usd == pytest.approx(0.30)
    with pytest.raises(ImprovementBudgetError, match="invocation count"):
        gate.before_model_stage("polish")


def test_agentic_json_requires_approval_without_starting(
    tmp_path, monkeypatch, capsys, bounded_estimate
):
    report = tmp_path / "report.md"
    report.write_text("## Overview\n\nContent", encoding="utf-8")
    run = MagicMock()
    monkeypatch.setattr(
        governance,
        "estimate_agentic_improve",
        lambda _content, *, is_strategy: bounded_estimate,
    )

    result = governance.handle_improve(
        _config(improve_path=str(report), improve_agentic=True, json_output=True),
        improve_output_file=run,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["error_type"] == "approval_required"
    assert payload["estimate"]["estimated_cost_usd"] == pytest.approx(0.30)
    run.assert_not_called()


def test_agentic_budget_refusal_happens_before_model_work(
    tmp_path, monkeypatch, capsys, bounded_estimate
):
    report = tmp_path / "report.md"
    report.write_text("## Overview\n\nContent", encoding="utf-8")
    run = MagicMock()
    monkeypatch.setattr(
        governance,
        "estimate_agentic_improve",
        lambda _content, *, is_strategy: bounded_estimate,
    )

    result = governance.handle_improve(
        _config(
            improve_path=str(report),
            improve_agentic=True,
            json_output=True,
            skip_confirm=True,
            budget_usd=0.29,
        ),
        improve_output_file=run,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["error_type"] == "budget_exceeded"
    run.assert_not_called()


def test_human_agentic_execution_repeats_quote_and_requires_yes(
    tmp_path, monkeypatch, capsys, bounded_estimate
):
    report = tmp_path / "report.md"
    report.write_text("## Overview\n\nContent", encoding="utf-8")
    run = MagicMock()
    monkeypatch.setattr(
        governance,
        "estimate_agentic_improve",
        lambda _content, *, is_strategy: bounded_estimate,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    result = governance.handle_improve(
        _config(improve_path=str(report), improve_agentic=True),
        improve_output_file=run,
    )

    stdout = capsys.readouterr().out
    assert result == 0
    assert "Estimated cost: ~$0.30" in stdout
    assert "Cancelled. No model calls were started." in stdout
    run.assert_not_called()


def test_approved_agentic_json_is_one_object_and_suppresses_human_output(
    tmp_path, monkeypatch, capsys, bounded_estimate
):
    report = tmp_path / "report.md"
    report.write_text("## Overview\n\nContent", encoding="utf-8")
    artifact = tmp_path / "report_improved.md"
    monkeypatch.setattr(
        governance,
        "estimate_agentic_improve",
        lambda _content, *, is_strategy: bounded_estimate,
    )

    def run(_path, **kwargs):
        print("human provider output")
        kwargs["before_model_stage"]("review")
        kwargs["before_model_stage"]("polish")
        return str(artifact)

    result = governance.handle_improve(
        _config(
            improve_path=str(report),
            improve_agentic=True,
            json_output=True,
            skip_confirm=True,
            budget_usd=0.30,
        ),
        improve_output_file=run,
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert result == 0
    assert stdout.count("primr.improvement-result.v1") == 1
    assert "human provider output" not in stdout
    assert payload["artifact"] == str(artifact)


def test_deterministic_improve_stays_free_and_ungated(capsys):
    run = MagicMock(return_value="report_improved.md")

    result = governance.handle_improve(
        _config(improve_path="report.md", json_output=True),
        improve_output_file=run,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["estimate"]["estimated_cost_usd"] == 0
    run.assert_called_once_with("report.md", in_place=False, use_agentic=False)


def test_refine_json_requires_approval_without_execution(
    tmp_path, monkeypatch, capsys, bounded_estimate
):
    report = tmp_path / "Acme_Strategic_Overview.md"
    report.write_text("## Overview\n\nContent", encoding="utf-8")
    refine_estimate = ImprovementEstimate(
        operation="refine",
        stages=bounded_estimate.stages,
        model_names=bounded_estimate.model_names,
        estimated_time_range=bounded_estimate.estimated_time_range,
        cost_basis=bounded_estimate.cost_basis,
    )
    monkeypatch.setattr(governance, "estimate_refine", lambda _content: refine_estimate)
    refine = MagicMock()

    result = governance.handle_refine(
        _config(refine_company="Acme", json_output=True),
        find_inputs=lambda _company: (str(report), None, "", None),
        refine_report=refine,
        output_dir=str(tmp_path),
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["error_type"] == "approval_required"
    refine.assert_not_called()


def test_refine_rejects_path_traversal_company(tmp_path, capsys):
    find_inputs = MagicMock(return_value=("report.md", None, "", None))
    refine = MagicMock()

    result = governance.handle_refine(
        _config(refine_company="../etc", json_output=True),
        find_inputs=find_inputs,
        refine_report=refine,
        output_dir=str(tmp_path),
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["error_type"] == "invalid_company"
    find_inputs.assert_not_called()
    refine.assert_not_called()
