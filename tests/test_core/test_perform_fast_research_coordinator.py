"""Coordinator-contract tests for perform_fast_research (roadmap #23 endgame).

The seven-batch extraction turned the ~1,900-line monster into a ~295-line
coordinator over module-level stage functions. These tests patch every stage
seam and pin the ORCHESTRATION CONTRACT itself: which stage gets which data,
what threads forward, the all-sections-failed early exit, and the outer
catch-all degradation — the wiring that no stage-level suite can see.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core import research_agent
from primr.core.fast_run_collection import DataCollectionResult
from primr.core.fast_run_gaps import GapDeepeningResult
from primr.core.fast_run_sections import SectionWritingResult
from primr.core.fast_run_strategy import StrategyPhaseResult
from primr.core.fast_run_trust import FastTrustResult
from primr.core.fast_run_validation import CrossValidationResult


@pytest.fixture
def stages(monkeypatch, tmp_path):
    """Patch every stage seam; return the mocks for wiring assertions."""
    setup = SimpleNamespace(
        grok_reasoning="reasoner-model",
        grok_writing="writer-model",
        grok_reasoning_effort=None,
        continuous_reasoning=True,
        display_name="AcmeCo",
        folder_path=str(tmp_path),
        has_strategies=False,
        total_phases=5,
    )
    pools = {
        "source_urls": ["https://evidence.example/a"],
        "source_urls_seen": {"https://evidence.example/a"},
        "external_text_parts": ["[Source: https://evidence.example/a]\ntext"],
        "external_raw_parts": ["[Source: https://evidence.example/a]\nraw"],
    }
    executor_token = object()
    session_token = object()

    mocks = {
        "setup": MagicMock(return_value=setup),
        "collect": MagicMock(
            return_value=DataCollectionResult(
                scraped_data={"https://acme.example": "page"},
                pages_scraped=1,
                summarized="summary",
                raw_corpus="corpus",
                total_scraped_chars=4,
                external_data={"https://evidence.example/a": "text"},
                external_query_count=10,
                recovery_executor=executor_token,
                **pools,
            )
        ),
        "hiring": MagicMock(return_value="=== HIRING SIGNALS ===\npostings"),
        "gaps": MagicMock(
            return_value=GapDeepeningResult(
                external_sources_raw="rebuilt external",
                combined_insights="rebuilt insights",
                gap_new_sources=2,
                gap_search_count=3,
            )
        ),
        "workbook": MagicMock(return_value=("the workbook", session_token)),
        "sections": MagicMock(
            return_value=SectionWritingResult(
                report_content="## Report\nwritten",
                written_sections=[SimpleNamespace(title="Overview", words=100)],
                total_words=100,
            )
        ),
        "cv": MagicMock(
            return_value=CrossValidationResult(
                report_content="## Report\nvalidated",
                unresolved_contradictions=1,
                sections_enriched=1,
                cv_search_count=4,
            )
        ),
        "trust": MagicMock(
            return_value=FastTrustResult(
                report_content="## Report\npolished",
                qa_metrics={"citations_used": 5, "citations_defined": 5},
                report_trust_stats=[("Report Gate", "PASS")],
            )
        ),
        "docx": MagicMock(return_value=str(tmp_path / "report.docx")),
        "strategy": MagicMock(return_value=StrategyPhaseResult({}, [])),
        "finalize": MagicMock(return_value=str(tmp_path / "report.docx")),
    }

    monkeypatch.setattr("primr.core.fast_run_setup.resolve_fast_run_setup", mocks["setup"])
    monkeypatch.setattr(research_agent, "collect_research_data", mocks["collect"])
    monkeypatch.setattr(research_agent, "collect_hiring_block", mocks["hiring"])
    monkeypatch.setattr(research_agent, "deepen_research", mocks["gaps"])
    monkeypatch.setattr(research_agent, "generate_analysis_workbook", mocks["workbook"])
    monkeypatch.setattr(research_agent, "write_report_sections", mocks["sections"])
    monkeypatch.setattr(research_agent, "cross_validate_and_enrich", mocks["cv"])
    monkeypatch.setattr(research_agent, "polish_and_gate_fast_report", mocks["trust"])
    monkeypatch.setattr(research_agent, "_convert_deep_research_to_docx", mocks["docx"])
    monkeypatch.setattr(research_agent, "run_strategy_phase", mocks["strategy"])
    monkeypatch.setattr("primr.core.fast_run_summary.finalize_fast_run", mocks["finalize"])

    mocks["executor_token"] = executor_token
    mocks["session_token"] = session_token
    mocks["tmp"] = tmp_path
    mocks["setup_obj"] = setup
    return mocks


def _run(stages, **overrides):
    defaults = {
        "company_name": "AcmeCo",
        "website": "https://acme.example",
        "start_time": time.time(),
    }
    defaults.update(overrides)
    return research_agent.perform_fast_research(**defaults)


class TestHappyPathWiring:
    def test_returns_finalize_result(self, stages):
        result = _run(stages)
        assert result == str(stages["tmp"] / "report.docx")
        stages["finalize"].assert_called_once()

    def test_recovery_executor_threaded_to_consumers(self, stages):
        _run(stages)
        token = stages["executor_token"]
        assert stages["workbook"].call_args.kwargs["recovery_executor"] is token
        assert stages["sections"].call_args.kwargs["recovery_executor"] is token
        assert stages["cv"].call_args.kwargs["recovery_executor"] is token

    def test_session_from_workbook_reaches_cross_validation(self, stages):
        _run(stages)
        assert stages["cv"].call_args.kwargs["reasoning_session"] is stages["session_token"]

    def test_pools_flow_from_collection_to_gaps_and_cv(self, stages):
        _run(stages)
        collected = stages["collect"].return_value
        gaps_kwargs = stages["gaps"].call_args.kwargs
        assert gaps_kwargs["source_urls"] is collected.source_urls
        assert gaps_kwargs["source_urls_seen"] is collected.source_urls_seen
        cv_kwargs = stages["cv"].call_args.kwargs
        assert cv_kwargs["source_urls"] is collected.source_urls

    def test_rebuilt_insights_feed_workbook(self, stages):
        _run(stages)
        wb_kwargs = stages["workbook"].call_args.kwargs
        assert wb_kwargs["external_sources_raw"] == "rebuilt external"
        assert wb_kwargs["combined_insights"] == "rebuilt insights"

    def test_report_content_chains_sections_cv_trust_docx(self, stages):
        _run(stages)
        assert stages["cv"].call_args.kwargs["report_content"] == "## Report\nwritten"
        assert stages["trust"].call_args.kwargs["report_content"] == "## Report\nvalidated"
        assert stages["docx"].call_args.args[0] == "## Report\npolished"

    def test_contradictions_thread_cv_to_trust(self, stages):
        _run(stages)
        assert stages["trust"].call_args.kwargs["unresolved_contradictions"] == 1

    def test_search_query_count_sums_all_three_phases(self, stages):
        _run(stages)
        # collection 10 + gaps 3 + cv 4
        assert stages["finalize"].call_args.kwargs["search_query_count"] == 17

    def test_hiring_block_threads_into_gap_rebuild(self, stages):
        _run(stages)
        assert stages["gaps"].call_args.kwargs["hiring_block"] == "=== HIRING SIGNALS ===\npostings"

    def test_insights_file_written_before_gap_phase(self, stages):
        _run(stages)
        insights = (stages["tmp"] / "insights.txt").read_text(encoding="utf-8")
        assert "summary" in insights  # initial build, pre-rebuild
        assert stages["gaps"].call_args.kwargs["insights_file"] == str(
            stages["tmp"] / "insights.txt"
        )

    def test_report_md_persisted_for_strategy_context(self, stages):
        _run(stages)
        md = (stages["tmp"] / "report.md").read_text(encoding="utf-8")
        assert md == "## Report\npolished"

    def test_company_label_falls_back_to_display_name(self, stages):
        _run(stages, company_name=None)
        assert stages["cv"].call_args.kwargs["company_label"] == "AcmeCo"
        assert stages["cv"].call_args.kwargs["company_name"] is None


class TestEarlyExitsAndDegradation:
    def test_all_sections_failed_returns_none_before_cv(self, stages):
        stages["sections"].return_value = SectionWritingResult(report_content=None)
        result = _run(stages)
        assert result is None
        stages["cv"].assert_not_called()
        stages["finalize"].assert_not_called()

    def test_stage_exception_degrades_to_none(self, stages):
        stages["workbook"].side_effect = RuntimeError("workbook exploded")
        result = _run(stages)
        assert result is None
        stages["sections"].assert_not_called()

    def test_setup_exception_propagates(self, stages):
        # Setup runs BEFORE the catch-all try — a config failure must raise,
        # not silently return None.
        stages["setup"].side_effect = RuntimeError("bad tier")
        with pytest.raises(RuntimeError, match="bad tier"):
            _run(stages)


class TestStrategyWiring:
    def test_strategy_receives_validated_sources_snapshot(self, stages):
        stages["setup_obj"].has_strategies = True
        stages["setup_obj"].total_phases = 6
        _run(stages, ai_strategy=True)
        kwargs = stages["strategy"].call_args.kwargs
        # Snapshot taken AFTER gap deepening, from the live pool
        assert kwargs["validated_source_urls"] == ["https://evidence.example/a"]
        assert kwargs["report_content"] == "## Report\npolished"
        assert kwargs["recovery_executor"] is stages["executor_token"]

    def test_strategy_outputs_reach_finalize(self, stages):
        stages["setup_obj"].has_strategies = True
        stages["setup_obj"].total_phases = 6
        stages["strategy"].return_value = StrategyPhaseResult(
            {"ai": "path.docx"}, [("AI Strategy", [("Gate", "PASS")])]
        )
        _run(stages, ai_strategy=True)
        fin = stages["finalize"].call_args.kwargs
        assert fin["strategy_paths"] == {"ai": "path.docx"}
        assert fin["strategy_trust_stats"] == [("AI Strategy", [("Gate", "PASS")])]
