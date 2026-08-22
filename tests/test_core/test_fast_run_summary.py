"""Tests for the extracted fast-run finalization stage (roadmap #23, Batch A).

This stage was previously the untestable tail of perform_fast_research;
extraction makes its behavior (output-path selection, artifact gating,
run-state metrics, usage recording) pinnable with mocks.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from primr.core.fast_run_summary import _strategy_display_label, finalize_fast_run
from primr.core.strategy_outcome import StrategyOutcomeTracker
from primr.core.vendor_refresh_outcome import VendorRefreshTracker


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Mock every side-effect boundary and return the capture points."""
    captured: dict = {}

    monkeypatch.setattr(
        "primr.ai.grok_client.get_grok_session_usage",
        lambda: {"input_tokens": 1000, "output_tokens": 200, "cached_input_tokens": 400},
    )
    monkeypatch.setattr("primr.utils.run_budget.observed_session_spend", lambda: 0.79)

    def fake_update_run_state(folder_path, **updates):
        captured["run_state"] = updates

    monkeypatch.setattr("primr.core.fast_run_summary._update_run_state", fake_update_run_state)

    tracker = MagicMock()
    monkeypatch.setattr("primr.utils.usage_tracker.get_usage_tracker", lambda: tracker)
    captured["tracker"] = tracker
    captured["tmp"] = tmp_path
    return captured


def _call(env, **overrides):
    defaults = {
        "start_time": time.time() - 65,
        "docx_path": str(env["tmp"] / "AcmeCo_Strategic_Overview.docx"),
        "strategy_paths": {},
        "output_dir": str(env["tmp"]),
        "company_name": "AcmeCo",
        "display_name": "AcmeCo",
        "folder_path": str(env["tmp"]),
        "written_sections_count": 23,
        "expected_sections_count": 23,
        "report_complete": True,
        "total_words": 21000,
        "validated_source_count": 14,
        "pages_scraped": 48,
        "grok_tier": "hybrid",
        "report_trust_stats": [],
        "strategy_trust_stats": [],
        "search_query_count": 18,
        "vendor_refresh_tasks_started": 0,
        "strategy_outcome": StrategyOutcomeTracker(()).snapshot(),
        "vendor_refresh_outcome": VendorRefreshTracker(()).snapshot(),
    }
    defaults.update(overrides)
    with patch("primr.core.fast_run_summary.log_job_summary") as job_log:
        env["job_log"] = job_log
        result = finalize_fast_run(**defaults)
    return result


class TestStrategyLabels:
    def test_ai_vendor_label(self):
        assert _strategy_display_label("ai_azure") == "AI Strategy (AZURE)"
        assert _strategy_display_label("ai") == "AI Strategy"

    def test_yaml_strategy_label(self):
        assert _strategy_display_label("customer_experience") == "Customer Experience"


class TestFinalize:
    def test_returns_docx_when_no_md_fallback(self, env):
        result = _call(env)
        assert result is not None
        assert result.endswith(".docx")

    def test_prefers_markdown_fallback_when_it_exists(self, env):
        from datetime import datetime

        date_str = datetime.now().strftime("%m-%d-%Y")
        md = env["tmp"] / f"AcmeCo_Strategic_Overview_{date_str}.md"
        md.write_text("# report", encoding="utf-8")
        result = _call(env)
        assert result == str(md)

    def test_fallback_filename_is_portable(self, env):
        from datetime import datetime

        date_str = datetime.now().strftime("%m-%d-%Y")
        md = env["tmp"] / f"Acme, Inc_Strategic_Overview_{date_str}.md"
        md.write_text("# report", encoding="utf-8")

        result = _call(env, company_name="Acme, Inc.", display_name="Acme, Inc.")

        assert result == str(md)

    def test_run_state_metrics_persisted(self, env):
        _call(env)
        state = env["run_state"]
        assert state["report_sections"] == 23
        assert state["report_sections_expected"] == 23
        assert state["report_complete"] is True
        assert state["report_words"] == 21000
        assert state["external_sources_validated"] == 14
        assert state["artifact_gate_passed"] is True
        assert state["actual_cost_usd"] == 0.79

    def test_refresh_cost_is_in_run_total_without_duplicate_usage(self, env):
        _call(env, vendor_refresh_tasks_started=2)

        assert env["run_state"]["actual_cost_usd"] == 5.79
        usage = env["tracker"].record_usage.call_args.kwargs
        assert usage["pipeline_cost"] == 0.79

    def test_artifact_gate_fails_on_non_docx_strategy(self, env):
        _call(env, strategy_paths={"ai_azure": str(env["tmp"] / "strategy.md")})
        assert env["run_state"]["artifact_gate_passed"] is False

    def test_artifact_gate_fails_without_report_docx(self, env):
        _call(env, docx_path=None)
        assert env["run_state"]["artifact_gate_passed"] is False

    def test_artifact_gate_surfaces_materially_incomplete_markdown(self, env):
        from datetime import datetime

        date_str = datetime.now().strftime("%m-%d-%Y")
        md = env["tmp"] / f"AcmeCo_Strategic_Overview_{date_str}.md"
        md.write_text("# Partial report", encoding="utf-8")
        result = _call(
            env,
            docx_path=None,
            written_sections_count=8,
            expected_sections_count=23,
            report_complete=False,
        )
        assert result == str(md)
        assert env["run_state"]["artifact_gate_passed"] is False
        assert env["run_state"]["report_complete"] is False

    def test_partial_strategy_outcome_fails_artifact_gate_and_is_persisted(self, env):
        tracker = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
        tracker.mark_completed("ai:azure")

        _call(
            env,
            strategy_paths={"ai_azure": str(env["tmp"] / "strategy.docx")},
            strategy_outcome=tracker.snapshot(),
        )

        assert env["run_state"]["artifact_gate_passed"] is False
        assert env["run_state"]["strategy_status"] == "partial"
        assert env["run_state"]["strategy_failed_targets"] == ["ai:aws"]

    def test_usage_recorded_with_cache_tokens(self, env):
        _call(env)
        kwargs = env["tracker"].record_usage.call_args.kwargs
        assert kwargs["mode"] == "fast"
        assert kwargs["input_tokens"] == 1000
        assert kwargs["cached_input_tokens"] == 400
        assert kwargs["search_queries"] == 18
        assert kwargs["pipeline_cost"] == 0.79
        env["tracker"].save.assert_called_once()

    def test_job_summary_logged(self, env):
        _call(env)
        job = env["job_log"].call_args.args[0]
        assert job.company == "AcmeCo"
        assert job.sections_generated == 23
