"""Approval-gate tests for billable ``primr --eval`` helpers."""

from __future__ import annotations

from types import SimpleNamespace

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
