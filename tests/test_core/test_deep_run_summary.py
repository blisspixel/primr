"""Tests for the extracted deep-run finalization stage.

Previously the untestable tail of ``perform_deep_research``; extraction makes
its behavior (cost reconciliation across the pipeline + flat Deep-Research task
cost, the estimated-vs-actual summary, the report-trust row, usage recording,
and the job summary) pinnable with mocks. No behavior change from the inline
version.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.deep_run_summary import finalize_deep_run
from primr.core.strategy_outcome import StrategyOutcomeTracker
from primr.core.vendor_refresh_outcome import VendorRefreshTracker


@pytest.fixture
def env(monkeypatch):
    captured: dict = {}

    client = MagicMock()
    client.get_usage_summary.return_value = {
        "total_cost": 0.50,
        "total_input_tokens": 1000,
        "total_output_tokens": 200,
    }
    monkeypatch.setattr("primr.ai.client.get_client", lambda: client)

    # Flat Deep-Research task cost is deterministic: 0.30 per task.
    monkeypatch.setattr("primr.core.deep_budget.count_main_deep_research_tasks", lambda mode: 1)
    monkeypatch.setattr(
        "primr.core.deep_budget.deep_research_flat_cost", lambda tasks: 0.30 * tasks
    )
    monkeypatch.setattr(
        "primr.utils.cost_estimator.estimate_cost",
        lambda *a, **k: SimpleNamespace(total_cost=0.75),
    )

    tracker = MagicMock()
    monkeypatch.setattr("primr.utils.usage_tracker.get_usage_tracker", lambda: tracker)
    captured["tracker"] = tracker

    console = MagicMock()
    monkeypatch.setattr("primr.core.deep_run_summary.console", console)
    captured["console"] = console

    job_log = MagicMock()
    monkeypatch.setattr("primr.core.deep_run_summary.log_job_summary", job_log)
    captured["job_log"] = job_log

    return captured


def _result(**overrides):
    defaults = {
        "sections_written": 23,
        "section_results": {"intro": "text"},
        # One cited (Confirmed) claim + a resolvable Sources appendix -> the
        # label-citation trust row fires; real helper, not mocked.
        "raw_content": (
            "Revenue hit $9M. (Confirmed) [cite: 1]\n\n## Sources\n\n1. https://a.example/x\n"
        ),
        "search_queries_count": 12,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _call(env, **overrides):
    defaults = {
        "mode": "complete",
        "mode_label": "Complete (Two-Step)",
        "result": _result(),
        "ai_strategy": False,
        "platforms": ("agnostic",),
        "lite_strategy": False,
        "strategies": None,
        "strategy_deep_research_tasks_started": 0,
        "refresh_vendor_research": False,
        "vendor_refresh_tasks_started": 0,
        "strategy_outcome": StrategyOutcomeTracker(()).snapshot(),
        "vendor_refresh_outcome": VendorRefreshTracker(()).snapshot(),
        "time_str": "38m 0s",
        "elapsed": 2280.0,
        "display_name": "AcmeCo",
        "docx_path": "/out/AcmeCo.docx",
    }
    defaults.update(overrides)
    return finalize_deep_run(**defaults)


class TestFinalizeDeepRun:
    def test_records_usage_with_pipeline_and_dr_cost_split(self, env):
        _call(env)
        kwargs = env["tracker"].record_usage.call_args.kwargs
        assert kwargs["mode"] == "complete"
        assert kwargs["company"] == "AcmeCo"
        assert kwargs["input_tokens"] == 1000
        assert kwargs["output_tokens"] == 200
        assert kwargs["search_queries"] == 12
        assert kwargs["pipeline_cost"] == 0.50
        assert kwargs["deep_research_cost"] == pytest.approx(0.30)  # 1 main task
        env["tracker"].save.assert_called_once()

    def test_summary_shows_estimated_and_actual_cost(self, env):
        _call(env)
        items = dict(env["console"].summary.call_args.args[0])
        assert items["Mode"] == "Complete (Two-Step)"
        assert items["Chapters"] == "23"
        assert items["Est. Cost"] == "$0.75"
        # actual = 0.50 pipeline + 0.30 Deep Research
        assert items["Actual Cost"] == "~$0.80"

    def test_trust_panel_rendered_when_traceable_claims(self, env):
        _call(env)
        titles = [c.args[0] for c in env["console"].trust_summary.call_args_list]
        assert "Report Trust" in titles

    def test_no_trust_panel_without_traceable_claims(self, env):
        _call(env, result=_result(raw_content="No labels here.", section_results={}))
        env["console"].trust_summary.assert_not_called()

    def test_ai_strategy_row_added_when_enabled(self, env):
        tracker = StrategyOutcomeTracker(("ai:agnostic",))
        tracker.mark_completed("ai:agnostic")
        _call(env, ai_strategy=True, strategy_outcome=tracker.snapshot())
        items = dict(env["console"].summary.call_args.args[0])
        assert items["AI Strategy"] == "Yes"

    def test_replacement_strategy_does_not_claim_ai_artifact(self, env):
        tracker = StrategyOutcomeTracker(("customer_experience",))
        tracker.mark_completed("customer_experience")

        _call(
            env,
            ai_strategy=True,
            strategies=["customer_experience"],
            strategy_outcome=tracker.snapshot(),
        )

        assert "AI Strategy" not in dict(env["console"].summary.call_args.args[0])

    def test_dr_cost_includes_strategy_tasks(self, env):
        _call(env, strategy_deep_research_tasks_started=2)
        # 1 main + 2 strategy = 3 tasks * 0.30
        kwargs = env["tracker"].record_usage.call_args.kwargs
        assert kwargs["deep_research_cost"] == pytest.approx(0.90)

    def test_vendor_refresh_cost_is_shown_without_duplicate_usage(self, env):
        _call(
            env,
            ai_strategy=True,
            platforms=("azure", "aws"),
            refresh_vendor_research=True,
            vendor_refresh_tasks_started=2,
        )

        items = dict(env["console"].summary.call_args.args[0])
        assert items["Actual Cost"] == "~$1.40"
        assert items["Vendor Refresh"] == "2 task(s)  ~$0.60"
        usage = env["tracker"].record_usage.call_args.kwargs
        assert usage["deep_research_cost"] == pytest.approx(0.30)

    def test_estimate_includes_planned_vendor_refreshes(self, env, monkeypatch):
        estimate = MagicMock(return_value=SimpleNamespace(total_cost=5.0))
        monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", estimate)

        _call(
            env,
            ai_strategy=True,
            platforms=("azure", "aws"),
            refresh_vendor_research=True,
        )

        assert estimate.call_args.kwargs["vendor_research_refreshes"] == 2

    def test_job_summary_logged(self, env):
        _call(env)
        job = env["job_log"].call_args.args[0]
        assert job.company == "AcmeCo"
        assert job.sections_generated == 23
