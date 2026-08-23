"""Tests for the extracted cross-validation stage (roadmap #23, Batch E).

Pins the two highest-risk tangles from the refactor map: the enrichment
worker's default-arg query binding (late-binding trap) with explicit URL
merge-back into the caller's collections, and the serial regex splice loop.
Also pins the contradiction-resolution structure guard and the cv artifact.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_validation import CrossValidationResult, cross_validate_and_enrich

REPORT = """## Overview
Overview body text here.

## Market
Market body text here.

## Competitors
Competitor body text here.
"""


@pytest.fixture
def seams(monkeypatch, tmp_path):
    cv_review = MagicMock(return_value={"weak_sections": [], "contradictions": []})

    regenerate = MagicMock(
        side_effect=lambda company, website, title, original, *a, **k: (
            f"## {title}\nENRICHED {title} body.\n"
        )
    )
    monkeypatch.setattr("primr.core.fast_run_validation._fast_regenerate_section", regenerate)

    def fake_recovery(executor, fn, folder):
        try:
            return SimpleNamespace(success=True, output=fn(), skip_reason=None)
        except Exception as e:
            return SimpleNamespace(success=False, output=None, skip_reason=str(e))

    monkeypatch.setattr("primr.pipeline.integration.cross_validate_with_recovery", fake_recovery)

    search = MagicMock(return_value=[{"url": "https://evidence.example/page"}])
    monkeypatch.setattr("primr.core.fast_run_validation.search_web", search)

    scrape = MagicMock(
        side_effect=lambda filtered, **k: {r["url"]: "evidence content" for r in filtered}
    )
    monkeypatch.setattr("primr.core.fast_run_validation.scrape_external_sources_validated", scrape)

    resolver = MagicMock(return_value="")
    monkeypatch.setattr("primr.core.fast_run_validation.call_with_failover", resolver)

    return {
        "cv_review": cv_review,
        "regenerate": regenerate,
        "search": search,
        "scrape": scrape,
        "resolver": resolver,
        "tmp": tmp_path,
    }


def _call(seams, **overrides) -> CrossValidationResult:
    defaults = {
        "company_name": "AcmeCo",
        "company_label": "AcmeCo",
        "website": "https://acme.example",
        "report_content": REPORT,
        "source_urls": ["https://acme.example/about"],
        "source_urls_seen": {"https://acme.example/about"},
        "review_report": seams["cv_review"],
        "analysis_workbook": "workbook",
        "grok_reasoning": "reasoner-model",
        "grok_writing": "writer-model",
        "reasoning_session": None,
        "recovery_executor": object(),
        "folder_path": str(seams["tmp"]),
        "total_phases": 5,
    }
    defaults.update(overrides)
    return cross_validate_and_enrich(**defaults)


class TestCleanReview:
    def test_no_findings_leaves_report_unchanged(self, seams):
        result = _call(seams)
        assert result.report_content == REPORT
        assert result.unresolved_contradictions == 0
        assert result.sections_enriched == 0
        assert result.cv_search_count == 0

    def test_cv_artifact_written(self, seams):
        _call(seams)
        data = json.loads((seams["tmp"] / "cross_validation.json").read_text(encoding="utf-8"))
        assert data["weak_sections"] == []
        assert "_failed" not in data

    def test_review_failure_degrades_without_blocking(self, seams):
        seams["cv_review"].side_effect = RuntimeError("review died")
        result = _call(seams)
        assert result.report_content == REPORT
        assert result.unresolved_contradictions == 0

    @pytest.mark.parametrize(
        "review_output",
        [
            None,
            [],
            {"weak_sections": "invalid", "contradictions": [1, None, ""]},
        ],
    )
    def test_malformed_successful_review_degrades_without_blocking(self, seams, review_output):
        seams["cv_review"].return_value = review_output

        result = _call(seams)

        assert result.report_content == REPORT
        assert result.unresolved_contradictions == 0
        assert result.sections_enriched == 0

    def test_diagnostic_write_failure_does_not_discard_report(self, seams, monkeypatch):
        monkeypatch.setattr(
            "primr.core.fast_run_validation.atomic_write_text",
            MagicMock(side_effect=OSError("disk unavailable")),
        )

        result = _call(seams)

        assert result.report_content == REPORT
        assert result.sections_enriched == 0

    def test_session_threaded_to_review(self, seams):
        session = object()
        _call(seams, reasoning_session=session)
        assert seams["cv_review"].call_args.kwargs["reasoning_session"] is session


class TestEnrichment:
    def _flag(self, seams, *sections):
        seams["cv_review"].side_effect = None
        seams["cv_review"].return_value = {
            "weak_sections": [{"title": t, "queries": [f"query about {t}"]} for t in sections],
            "contradictions": [],
        }

    def test_weak_section_enriched_and_spliced(self, seams):
        self._flag(seams, "Market")
        result = _call(seams)
        assert "ENRICHED Market body." in result.report_content
        assert "Overview body text here." in result.report_content  # neighbors intact
        assert "Competitor body text here." in result.report_content
        assert result.sections_enriched == 1
        assert result.cv_search_count == 1

    def test_new_urls_merged_into_caller_collections(self, seams):
        self._flag(seams, "Market")
        urls = ["https://acme.example/about"]
        seen = {"https://acme.example/about"}
        _call(seams, source_urls=urls, source_urls_seen=seen)
        assert "https://evidence.example/page" in urls
        assert "https://evidence.example/page" in seen

    def test_serial_splice_both_sections(self, seams):
        # Second pattern must match against the report AFTER the first splice.
        # Distinct evidence URLs per query; discovered URLs dedup across
        # sections via source_urls_seen, so identical URLs would starve the
        # second section of evidence.
        self._flag(seams, "Market", "Competitors")
        seams["search"].side_effect = lambda q, c, w: [
            {"url": f"https://evidence.example/{q.split()[-1].lower()}"}
        ]
        result = _call(seams)
        assert "ENRICHED Market body." in result.report_content
        assert "ENRICHED Competitors body." in result.report_content
        assert result.sections_enriched == 2

    def test_late_binding_each_section_uses_own_queries(self, seams):
        self._flag(seams, "Market", "Competitors")
        _call(seams)
        queries = [c.args[0] for c in seams["search"].call_args_list]
        assert queries == ["query about Market", "query about Competitors"]

    def test_search_uses_raw_company_name_not_label(self, seams):
        self._flag(seams, "Market")
        _call(seams, company_name=None, company_label="acme.example")
        assert seams["search"].call_args.args[1] is None

    def test_own_site_and_seen_urls_filtered(self, seams):
        self._flag(seams, "Market")
        seams["search"].return_value = [
            {"url": "https://acme.example/self-praise"},
            {"url": "https://acme.example/about"},
        ]
        result = _call(seams)
        # Both candidates filtered (own site / already seen), so nothing is scraped.
        assert result.sections_enriched == 0
        assert "ENRICHED" not in result.report_content

    def test_own_site_variants_and_subdomains_are_filtered(self, seams):
        self._flag(seams, "Market")
        seams["search"].return_value = [
            {"url": "http://www.acme.example/self-praise"},
            {"url": "https://news.acme.example/announcement"},
        ]

        result = _call(seams)

        assert result.sections_enriched == 0
        assert result.report_content == REPORT

    def test_timeout_detaches_enrichment_worker(self, seams, monkeypatch):
        self._flag(seams, "Market")
        detach = MagicMock()

        def timeout(*args, **kwargs):
            raise TimeoutError

        monkeypatch.setattr("concurrent.futures.as_completed", timeout)
        monkeypatch.setattr("primr.core.fast_run_validation.detach_running_workers", detach)

        result = _call(seams)

        assert result.report_content == REPORT
        assert result.sections_enriched == 0
        assert result.cv_search_count == 1
        detach.assert_called_once()

    def test_unknown_heading_skipped(self, seams):
        self._flag(seams, "Nonexistent Section")
        result = _call(seams)
        assert result.sections_enriched == 0
        assert result.report_content == REPORT

    def test_unchanged_regeneration_not_spliced(self, seams):
        self._flag(seams, "Market")
        seams["regenerate"].side_effect = lambda company, website, title, original, *a, **k: (
            original
        )
        result = _call(seams)
        assert result.sections_enriched == 0
        assert result.report_content == REPORT

    def test_diminishing_returns_summary_persisted(self, seams):
        self._flag(seams, "Market")
        _call(seams)
        data = json.loads((seams["tmp"] / "cross_validation.json").read_text(encoding="utf-8"))
        assert "diminishing_returns" in data


class TestContradictions:
    def _contradict(self, seams):
        seams["cv_review"].side_effect = None
        seams["cv_review"].return_value = {
            "weak_sections": [],
            "contradictions": ["Revenue stated as $10M in Overview but $12M in Market"],
        }

    def test_resolved_when_structure_preserved(self, seams, monkeypatch):
        self._contradict(seams)
        seams["resolver"].return_value = REPORT + " resolved"
        monkeypatch.setattr(
            "primr.core.fast_run_validation._preserves_report_structure", lambda a, b: True
        )
        result = _call(seams)
        assert result.unresolved_contradictions == 0
        assert result.report_content.endswith("resolved")

    def test_structure_guard_keeps_original(self, seams, monkeypatch):
        self._contradict(seams)
        seams["resolver"].return_value = "## Gutted\nreport"
        monkeypatch.setattr(
            "primr.core.fast_run_validation._preserves_report_structure", lambda a, b: False
        )
        result = _call(seams)
        assert result.unresolved_contradictions == 1
        assert result.report_content == REPORT

    def test_resolver_failure_keeps_original(self, seams):
        self._contradict(seams)
        seams["resolver"].side_effect = RuntimeError("resolver down")
        result = _call(seams)
        assert result.unresolved_contradictions == 1
        assert result.report_content == REPORT


class TestBudgetCheckpoint:
    """Phase-5 enrichment (search + regeneration per weak section) and
    contradiction resolution (one writing call) are optional spend on an
    already-assembled report. An active ``--budget`` ceiling skips them and ships
    the report, mirroring the Phase-2 deepening and Phase-6 strategy checkpoints
    (roadmap #5). Gate the irreversible act (spend), never the reasoning."""

    _WEAK = {
        "weak_sections": [{"title": "Market", "queries": ["query about Market"]}],
        "contradictions": ["Revenue $10M vs $12M"],
    }

    def test_enrichment_and_resolution_skipped_when_budget_exceeded(self, seams, monkeypatch):
        from primr.utils.run_budget import clear_run_budget, set_run_budget

        seams["cv_review"].return_value = dict(self._WEAK)
        monkeypatch.setattr("primr.core.fast_run_validation.observed_session_spend", lambda: 100.0)
        set_run_budget(1.0)  # ceiling $1, already spent $100 -> exceeded
        try:
            result = _call(seams)
        finally:
            clear_run_budget()

        # No spend: no enrichment search/scrape/regeneration, no resolve call.
        seams["search"].assert_not_called()
        seams["scrape"].assert_not_called()
        seams["regenerate"].assert_not_called()
        seams["resolver"].assert_not_called()
        # The assembled report ships unchanged; contradictions noted, unresolved.
        assert result.report_content == REPORT
        assert result.sections_enriched == 0
        assert result.cv_search_count == 0
        assert result.unresolved_contradictions == 1

    def test_resolution_skipped_when_over_budget_with_no_weak_sections(self, seams, monkeypatch):
        from primr.utils.run_budget import clear_run_budget, set_run_budget

        # No weak sections -> the enrichment loop never runs and never syncs
        # spend, so the contradiction checkpoint must gate on its own.
        seams["cv_review"].return_value = {
            "weak_sections": [],
            "contradictions": ["Revenue $10M vs $12M"],
        }
        monkeypatch.setattr("primr.core.fast_run_validation.observed_session_spend", lambda: 100.0)
        set_run_budget(1.0)
        try:
            result = _call(seams)
        finally:
            clear_run_budget()

        seams["resolver"].assert_not_called()
        assert result.unresolved_contradictions == 1

    def test_proceeds_when_budget_has_headroom(self, seams, monkeypatch):
        from primr.utils.run_budget import clear_run_budget, set_run_budget

        seams["cv_review"].return_value = dict(self._WEAK)
        monkeypatch.setattr("primr.core.fast_run_validation.observed_session_spend", lambda: 0.10)
        set_run_budget(100.0)  # plenty of headroom -> full Phase-5 work
        try:
            result = _call(seams)
        finally:
            clear_run_budget()

        seams["regenerate"].assert_called_once()
        seams["resolver"].assert_called_once()
        assert "ENRICHED Market body." in result.report_content
        assert result.sections_enriched == 1

    def test_no_budget_active_does_not_compute_spend(self, seams, monkeypatch):
        # With no active budget the checkpoint must short-circuit and never call
        # observed_session_spend, keeping the default path free.
        cost = MagicMock(return_value=0.0)
        monkeypatch.setattr("primr.core.fast_run_validation.observed_session_spend", cost)
        seams["cv_review"].return_value = dict(self._WEAK)

        result = _call(seams)

        cost.assert_not_called()
        seams["regenerate"].assert_called_once()
        seams["resolver"].assert_called_once()
        assert result.sections_enriched == 1
