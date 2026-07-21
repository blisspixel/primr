from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from primr.core.standard_run_summary import finalize_standard_run
from primr.core.standard_strategy import StandardStrategyResult
from primr.core.strategy_outcome import StrategyOutcomeTracker
from primr.core.vendor_refresh_outcome import VendorRefreshTracker


def test_standard_summary_reconciles_flat_tasks_without_double_counting_refresh(
    monkeypatch,
):
    client = SimpleNamespace(
        get_usage_summary=lambda: {
            "total_cost": 0.50,
            "total_input_tokens": 1000,
            "total_output_tokens": 200,
            "api_calls": 4,
        }
    )
    monkeypatch.setattr("primr.ai.client.get_client", lambda: client)
    monkeypatch.setattr(
        "primr.core.deep_budget.deep_research_flat_cost",
        lambda count: count * 2.50,
    )
    tracker = MagicMock()
    monkeypatch.setattr("primr.utils.usage_tracker.get_usage_tracker", lambda: tracker)
    console = MagicMock()
    monkeypatch.setattr("primr.core.standard_run_summary.console", console)
    update_state = MagicMock()
    append_event = MagicMock()
    monkeypatch.setattr("primr.core.run_state_io._update_run_state", update_state)
    monkeypatch.setattr("primr.core.run_state_io._append_run_event", append_event)
    job_log = MagicMock()
    monkeypatch.setattr("primr.core.standard_run_summary.log_job_summary", job_log)

    strategy_tracker = StrategyOutcomeTracker(("ai:azure",))
    strategy_tracker.mark_completed("ai:azure")
    refresh_tracker = VendorRefreshTracker(("azure",))
    refresh_tracker.observe("azure", "started")
    refresh_tracker.observe("azure", "completed")
    strategy = StandardStrategyResult(
        output_path="/out/strategy.docx",
        outcome=strategy_tracker.snapshot(),
        deep_research_tasks_started=1,
        vendor_refresh_tasks_started=1,
        vendor_refresh_outcome=refresh_tracker.snapshot(),
    )

    actual = finalize_standard_run(
        mode="structured",
        display_name="ExampleCo",
        folder_path="working/example",
        elapsed=42.0,
        time_str="42s",
        sections_generated=18,
        docx_path="/out/report.docx",
        strategy=strategy,
    )

    assert actual == 5.50
    usage = tracker.record_usage.call_args.kwargs
    assert usage["pipeline_cost"] == 0.50
    assert usage["deep_research_cost"] == 2.50
    assert update_state.call_args.kwargs["actual_cost_usd"] == 5.50
    summary = dict(console.summary.call_args.args[0])
    assert summary["Cost"] == "$5.50"
    assert summary["Vendor Refresh"] == "1 task(s)  ~$2.50"
    assert summary["Strategy Status"] == "COMPLETED"
    assert summary["Vendor Refresh Status"] == "COMPLETED"
    tracker.save.assert_called_once()
    job_log.assert_called_once()
    append_event.assert_called_once()
