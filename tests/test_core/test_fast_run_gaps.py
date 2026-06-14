"""Tests for the extracted research-deepening stage (roadmap #23, Batch F).

Pins tangle #1 (in-place source-pool mutation + rebuild-don't-mutate for the
external bundle), the gap-candidate dedup/filter rules, the source cap, and
the no-gaps / failed-analysis degradation paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_gaps import GapDeepeningResult, deepen_research


@pytest.fixture
def seams(monkeypatch, tmp_path):
    captured: dict = {}
    gap_analysis = MagicMock(return_value=(["what is their revenue?"], "## Gaps\nrevenue unknown"))
    monkeypatch.setattr("primr.core.research_agent._fast_gap_analysis", gap_analysis)

    search = MagicMock(return_value=[{"url": "https://evidence.example/revenue"}])
    monkeypatch.setattr("primr.core.fast_run_gaps.search_web", search)

    scrape = MagicMock(
        side_effect=lambda candidates, **k: {c["url"]: "validated content" for c in candidates}
    )
    monkeypatch.setattr("primr.core.fast_run_gaps.scrape_external_sources_validated", scrape)

    def fake_update(folder_path, **updates):
        captured["run_state"] = updates

    monkeypatch.setattr("primr.core.fast_run_gaps._update_run_state", fake_update)

    captured["gap_analysis"] = gap_analysis
    captured["search"] = search
    captured["scrape"] = scrape
    captured["tmp"] = tmp_path
    return captured


def _call(seams, **overrides) -> GapDeepeningResult:
    defaults = {
        "company_name": "AcmeCo",
        "company_label": "AcmeCo",
        "website": "https://acme.example",
        "raw_corpus": "corpus",
        "external_sources_raw": "[Source: https://acme.example/about]\nexisting",
        "combined_insights": "=== WEBSITE INSIGHTS ===\nexisting insights",
        "summarized": "site summary",
        "hiring_block": "=== HIRING SIGNALS ===\npostings",
        "source_urls": ["https://acme.example/about"],
        "source_urls_seen": {"https://acme.example/about"},
        "external_text_parts": [],
        "external_raw_parts": ["[Source: https://acme.example/about]\nexisting"],
        "grok_reasoning": "reasoner-model",
        "folder_path": str(seams["tmp"]),
        "insights_file": str(seams["tmp"] / "insights.txt"),
        "total_phases": 5,
    }
    defaults.update(overrides)
    return deepen_research(**defaults)


class TestGapFillingHappyPath:
    def test_new_source_lands_everywhere(self, seams):
        urls = ["https://acme.example/about"]
        seen = {"https://acme.example/about"}
        text_parts: list = []
        raw_parts = ["[Source: https://acme.example/about]\nexisting"]
        result = _call(
            seams,
            source_urls=urls,
            source_urls_seen=seen,
            external_text_parts=text_parts,
            external_raw_parts=raw_parts,
        )
        # In-place mutation of the caller's pools (tangle #1)
        assert "https://evidence.example/revenue" in urls
        assert "https://evidence.example/revenue" in seen
        assert any("validated content" in p for p in text_parts)
        assert any("validated content" in p for p in raw_parts)
        # Rebuilt bundle carries the new source AND the hiring block
        assert "validated content" in result.external_sources_raw
        assert "=== HIRING SIGNALS ===" in result.external_sources_raw
        assert result.gap_new_sources == 1
        assert result.gap_search_count == 1

    def test_insights_file_rewritten(self, seams):
        result = _call(seams)
        on_disk = (seams["tmp"] / "insights.txt").read_text(encoding="utf-8")
        assert on_disk == result.combined_insights
        assert "validated content" in on_disk

    def test_gap_analysis_artifact_written(self, seams):
        _call(seams)
        artifact = (seams["tmp"] / "gap_analysis.md").read_text(encoding="utf-8")
        assert "revenue unknown" in artifact

    def test_run_state_records_gap_metrics(self, seams):
        _call(seams)
        state = seams["run_state"]
        assert state["gap_queries"] == 1
        assert state["gap_new_sources"] == 1
        assert state["external_sources_validated"] == 2  # original + new

    def test_search_uses_raw_company_name(self, seams):
        _call(seams, company_name=None, company_label="acme.example")
        assert seams["search"].call_args.args[1] is None
        # ...while the gap-analysis prompt gets the display label
        assert seams["gap_analysis"].call_args.args[0] == "acme.example"


class TestFilteringAndDedup:
    def test_own_site_and_seen_urls_filtered(self, seams):
        seams["search"].return_value = [
            {"url": "https://acme.example/self"},
            {"url": "https://acme.example/about"},
        ]
        result = _call(seams)
        assert result.gap_new_sources == 0
        seams["scrape"].assert_not_called()

    def test_duplicate_candidates_across_queries_deduped(self, seams):
        seams["gap_analysis"].return_value = (["q1", "q2"], "gaps")
        seams["search"].return_value = [{"url": "https://evidence.example/same"}]
        result = _call(seams)
        # Two queries surfaced the same URL → validated once, counted once
        assert result.gap_new_sources == 1
        assert seams["scrape"].call_count == 1
        assert result.gap_search_count == 2

    def test_source_cap_bounds_additions(self, seams):
        queries = [f"q{i}" for i in range(14)]
        seams["gap_analysis"].return_value = (queries, "gaps")
        seams["search"].side_effect = lambda q, c, w: [{"url": f"https://evidence.example/{q}"}]
        result = _call(seams)
        assert result.gap_new_sources == 10  # max_gap_sources cap


class TestDegradationPaths:
    def test_no_gaps_skips_deepening(self, seams):
        seams["gap_analysis"].return_value = ([], "no gaps found")
        result = _call(seams)
        assert result.gap_new_sources == 0
        assert result.gap_search_count == 0
        seams["search"].assert_not_called()
        # Bundle and insights pass through unchanged
        assert result.external_sources_raw == "[Source: https://acme.example/about]\nexisting"
        assert result.combined_insights == "=== WEBSITE INSIGHTS ===\nexisting insights"
        # Insights file NOT rewritten on the skip path
        assert not (seams["tmp"] / "insights.txt").exists()

    def test_empty_gap_text_writes_placeholder(self, seams):
        seams["gap_analysis"].return_value = ([], "")
        _call(seams)
        artifact = (seams["tmp"] / "gap_analysis.md").read_text(encoding="utf-8")
        assert artifact == "(no gap analysis performed)"

    def test_one_search_failure_does_not_block_others(self, seams):
        seams["gap_analysis"].return_value = (["q1", "q2"], "gaps")

        def flaky(q, c, w):
            if q == "q1":
                raise RuntimeError("search died")
            return [{"url": "https://evidence.example/q2"}]

        seams["search"].side_effect = flaky
        result = _call(seams)
        assert result.gap_new_sources == 1
        assert result.gap_search_count == 2  # both queries counted

    def test_validation_failure_degrades_to_zero_sources(self, seams):
        seams["scrape"].side_effect = RuntimeError("scrape died")
        result = _call(seams)
        assert result.gap_new_sources == 0
        # Stage still completes: artifact + run state written
        assert (seams["tmp"] / "gap_analysis.md").exists()
        assert seams["run_state"]["gap_new_sources"] == 0


class TestBudgetCheckpoint:
    """Research deepening is an optional spend stage: when an active --budget is
    already exhausted, skip it (gate the irreversible act, never the reasoning)."""

    def test_skipped_when_budget_already_exceeded(self, seams, monkeypatch):
        from primr.utils.run_budget import clear_run_budget, set_run_budget

        monkeypatch.setattr("primr.core.research_agent._compute_session_llm_cost", lambda: 100.0)
        set_run_budget(1.0)  # ceiling $1, already spent $100 -> exceeded
        try:
            result = _call(seams)
        finally:
            clear_run_budget()

        # No spend: neither the gap-analysis LLM call nor any search ran.
        seams["gap_analysis"].assert_not_called()
        seams["search"].assert_not_called()
        assert result.gap_new_sources == 0
        assert result.gap_search_count == 0
        # Sources collected so far pass through unchanged.
        assert result.external_sources_raw == "[Source: https://acme.example/about]\nexisting"
        assert result.combined_insights == "=== WEBSITE INSIGHTS ===\nexisting insights"
        # Skip is recorded, not silent.
        artifact = (seams["tmp"] / "gap_analysis.md").read_text(encoding="utf-8")
        assert "budget" in artifact.lower()
        assert seams["run_state"]["gap_new_sources"] == 0

    def test_proceeds_when_budget_has_headroom(self, seams, monkeypatch):
        from primr.utils.run_budget import clear_run_budget, set_run_budget

        monkeypatch.setattr("primr.core.research_agent._compute_session_llm_cost", lambda: 0.10)
        set_run_budget(100.0)  # plenty of headroom -> normal deepening
        try:
            result = _call(seams)
        finally:
            clear_run_budget()

        seams["gap_analysis"].assert_called_once()
        assert result.gap_new_sources == 1

    def test_no_budget_active_is_unchanged(self, seams):
        # No set_run_budget() -> get_run_budget() is None -> happy path.
        result = _call(seams)
        assert result.gap_new_sources == 1
        seams["gap_analysis"].assert_called_once()


class TestHypothesisSteering:
    """Tradecraft Step 4: the Day-1 tree block is threaded into gap analysis so
    queries test branches; absent a tree, the default empty block is passed."""

    def test_hypothesis_block_threaded_to_gap_analysis(self, seams):
        _call(seams, hypothesis_block="=== DAY-1 HYPOTHESIS TREE ===\nH1: azure vs on-prem")
        assert (
            seams["gap_analysis"].call_args.kwargs["hypothesis_block"]
            == "=== DAY-1 HYPOTHESIS TREE ===\nH1: azure vs on-prem"
        )

    def test_default_passes_empty_block(self, seams):
        _call(seams)
        assert seams["gap_analysis"].call_args.kwargs["hypothesis_block"] == ""
