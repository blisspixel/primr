"""Tests for the extracted trust polish + citation repair stage (roadmap #23, Batch B).

These pin the stage ORCHESTRATION (ordering, repair gating, QA recompute,
trust-stat assembly, diagnostic resilience). The helpers it chains are
deterministic and have their own suites; here they are patched at the module
seams so the tests stay hermetic and offline.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from primr.core.fast_run_trust import FastTrustResult, polish_and_gate_fast_report

CLEAN_QA = {
    "confidence_labels": 12,
    "citations_used": 8,
    "citations_defined": 8,
    "sections_with_validate": 5,
    "section_count": 5,
    "qa_gate_passed": True,
    "missing_citations": 0,
}

BROKEN_QA = {**CLEAN_QA, "citations_used": 0, "citations_defined": 0, "qa_gate_passed": False}


@pytest.fixture
def seams(monkeypatch, tmp_path):
    """Patch every helper boundary; return the mocks + a default-call helper."""
    mocks = {
        "polish": MagicMock(side_effect=lambda c, w, r, s, model=None: r + "\n[polished]"),
        "repair": MagicMock(side_effect=lambda c, w, r, s, model=None: r),
        "clean": MagicMock(side_effect=lambda r: r),
        "normalize": MagicMock(side_effect=lambda r, source_urls=None: r),
        "enforce": MagicMock(side_effect=lambda r: r),
        "qa": MagicMock(return_value=dict(CLEAN_QA)),
        "repair_report": MagicMock(
            return_value={
                "writer_output_clean": True,
                "scaffolding_removed": 0,
                "chars_removed": 0,
            }
        ),
    }
    monkeypatch.setattr("primr.core.research_agent._polish_fast_report_for_trust", mocks["polish"])
    monkeypatch.setattr(
        "primr.core.research_agent._repair_fast_report_citation_integrity", mocks["repair"]
    )
    monkeypatch.setattr("primr.core.fast_run_trust._clean_fast_report_output", mocks["clean"])
    monkeypatch.setattr("primr.core.fast_run_trust._normalize_fast_citations", mocks["normalize"])
    monkeypatch.setattr(
        "primr.core.fast_run_trust._enforce_fast_section_quality_guards", mocks["enforce"]
    )
    monkeypatch.setattr("primr.core.fast_run_trust._compute_fast_report_qa_metrics", mocks["qa"])
    monkeypatch.setattr("primr.core.fast_run_trust.compute_repair_report", mocks["repair_report"])

    def call(**overrides) -> FastTrustResult:
        defaults = {
            "company_label": "AcmeCo",
            "website": "https://acme.example",
            "report_content": "## Section\nbody",
            "source_urls": ["https://acme.example/about"],
            "grok_writing": "writer-model",
            "folder_path": str(tmp_path),
            "unresolved_contradictions": 0,
        }
        defaults.update(overrides)
        return polish_and_gate_fast_report(**defaults)

    mocks["call"] = call
    mocks["tmp"] = tmp_path
    return mocks


class TestChainOrdering:
    def test_polish_then_cleanup_chain(self, seams):
        result = seams["call"]()
        assert "[polished]" in result.report_content
        seams["clean"].assert_called_once()
        seams["normalize"].assert_called_once()
        seams["enforce"].assert_called_once()
        # Cleanup chain receives the POLISHED content, not the raw report
        assert "[polished]" in seams["clean"].call_args.args[0]

    def test_polish_receives_writing_model(self, seams):
        seams["call"](grok_writing="special-writer")
        assert seams["polish"].call_args.kwargs["model"] == "special-writer"


class TestCitationRepairGate:
    def test_repair_skipped_when_citations_intact(self, seams):
        seams["call"]()
        seams["repair"].assert_not_called()
        assert seams["qa"].call_count == 1

    def test_repair_runs_when_citations_missing(self, seams):
        seams["qa"].side_effect = [dict(BROKEN_QA), dict(CLEAN_QA)]
        seams["repair"].side_effect = lambda c, w, r, s, model=None: r + "\n[repaired]"
        result = seams["call"]()
        seams["repair"].assert_called_once()
        assert "[repaired]" in result.report_content
        # QA recomputed on the repaired content
        assert seams["qa"].call_count == 2
        assert result.qa_metrics["citations_used"] == CLEAN_QA["citations_used"]

    def test_unchanged_repair_keeps_original_metrics(self, seams):
        seams["qa"].return_value = dict(BROKEN_QA)
        result = seams["call"]()  # repair returns content unchanged
        seams["repair"].assert_called_once()
        assert seams["qa"].call_count == 1
        assert result.qa_metrics["citations_used"] == 0

    def test_contradictions_threaded_into_qa(self, seams):
        seams["call"](unresolved_contradictions=3)
        assert seams["qa"].call_args.kwargs["unresolved_contradictions"] == 3


class TestTrustStats:
    def test_pass_gate_stats(self, seams):
        result = seams["call"]()
        stats = dict(result.report_trust_stats)
        assert stats["Report Gate"] == "PASS"
        assert stats["Citations"] == "8/8 defined"
        assert stats["Validate Lines"] == "5/5 sections"
        assert "Contradictions" not in stats

    def test_warn_gate_and_contradictions(self, seams):
        seams["qa"].return_value = {
            **CLEAN_QA,
            "qa_gate_passed": False,
            "unresolved_contradictions": 2,
        }
        result = seams["call"]()
        stats = dict(result.report_trust_stats)
        assert stats["Report Gate"] == "WARN"
        assert stats["Contradictions"] == "2"


class TestDiagnostics:
    def test_shipping_repair_json_written(self, seams):
        seams["call"]()
        path = seams["tmp"] / "_shipping_repair.json"
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))["writer_output_clean"] is True

    def test_diagnostic_failure_never_breaks_shipping(self, seams):
        seams["repair_report"].side_effect = RuntimeError("diagnostics down")
        result = seams["call"]()
        assert result.report_content  # run completed
        assert not (seams["tmp"] / "_shipping_repair.json").exists()
