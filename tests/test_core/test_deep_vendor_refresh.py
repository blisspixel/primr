"""Tests for budget-aware explicit vendor refresh preparation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.config.models import DEEP_RESEARCH_COST
from primr.core.deep_vendor_refresh import refresh_deep_strategy_vendors


@pytest.fixture
def seams(monkeypatch, tmp_path):
    generate = MagicMock()

    def start_vendor(*args, **kwargs):
        kwargs["task_observer"]("started")
        kwargs["task_observer"]("completed")
        return []

    generate.side_effect = start_vendor
    monkeypatch.setattr(
        "primr.core.vendor_research.get_or_generate_vendor_research_sync",
        generate,
    )
    client = SimpleNamespace(
        get_usage_summary=lambda: {"total_cost": 1.0},
    )
    monkeypatch.setattr("primr.ai.client.get_client", lambda: client)
    append_event = MagicMock()
    monkeypatch.setattr("primr.core.run_state_io._append_run_event", append_event)
    return generate, append_event, str(tmp_path)


def test_refreshes_unique_vendors_and_counts_started_tasks(seams, monkeypatch):
    generate, _append_event, folder = seams
    monkeypatch.setattr(
        "primr.utils.run_budget.skip_stage_if_cost_would_exceed",
        lambda *_args, **_kwargs: False,
    )

    result = refresh_deep_strategy_vendors(
        mode="complete",
        vendors=("azure", "aws", "azure"),
        folder_path=folder,
    )

    assert result.planned_count == 2
    assert result.started_count == 2
    assert result.skipped_budget_count == 0
    assert result.outcome.status == "completed"
    assert [call.args[0] for call in generate.call_args_list] == ["azure", "aws"]


def test_budget_skip_starts_no_second_provider_task(seams, monkeypatch):
    generate, append_event, folder = seams
    gate = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(
        "primr.utils.run_budget.skip_stage_if_cost_would_exceed",
        gate,
    )

    result = refresh_deep_strategy_vendors(
        mode="complete",
        vendors=("azure", "aws"),
        folder_path=folder,
    )

    assert result.started_count == 1
    assert result.skipped_budget_count == 1
    call = generate.call_args
    assert call.args == ("azure",)
    assert call.kwargs["force_refresh"] is True
    assert call.kwargs["allow_auto_refresh"] is False
    assert callable(call.kwargs["task_observer"])
    assert result.outcome.status == "partial"
    assert result.outcome.skipped_vendors == ("aws",)
    append_event.assert_called_once()


def test_later_budget_checks_include_prior_refresh_spend(seams, monkeypatch):
    _generate, _append_event, folder = seams
    observed: list[float] = []

    def capture(spent, _next_cost, _label):
        observed.append(spent)
        return False

    monkeypatch.setattr(
        "primr.utils.run_budget.skip_stage_if_cost_would_exceed",
        capture,
    )

    refresh_deep_strategy_vendors(
        mode="complete",
        vendors=("azure", "aws"),
        folder_path=folder,
    )

    task_cost = DEEP_RESEARCH_COST.standard_task_cost
    assert observed == pytest.approx([1.0 + task_cost, 1.0 + (2 * task_cost)])
