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

from primr.core.fast_run_trust import (
    FastTrustResult,
    _maybe_apply_label_honesty,
    polish_and_gate_fast_report,
)
from primr.qa.label_honesty import LabelDowngrade, LabelHonestyResult

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


def _downgrade_result(content: str, *, changed: bool) -> LabelHonestyResult:
    downgrades = (
        (
            LabelDowngrade(
                section="Overview",
                original_label="Confirmed",
                new_label="Estimated",
                span=(0, 0),
                sentence="a sourced claim its source did not support",
            ),
        )
        if changed
        else ()
    )
    return LabelHonestyResult(report_content=content, downgrades=downgrades)


class TestLabelHonestyHelper:
    """The opt-in label-honesty seam: gating, audit sidecar, fail-safety."""

    def test_default_off_is_a_noop(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PRIMR_LABEL_HONESTY", raising=False)
        called = MagicMock()
        monkeypatch.setattr("primr.qa.label_honesty.apply_label_honesty", called)
        out = _maybe_apply_label_honesty("## S\nbody", str(tmp_path))
        assert out == "## S\nbody"
        called.assert_not_called()
        assert not (tmp_path / "_label_honesty.json").exists()

    def test_flag_on_applies_downgrade_and_writes_sidecar(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PRIMR_LABEL_HONESTY", "1")
        monkeypatch.setattr(
            "primr.qa.label_honesty.apply_label_honesty",
            lambda content: _downgrade_result("## S\nbody (Estimated)", changed=True),
        )
        out = _maybe_apply_label_honesty("## S\nbody (Confirmed)", str(tmp_path))
        assert out == "## S\nbody (Estimated)"
        sidecar = json.loads((tmp_path / "_label_honesty.json").read_text(encoding="utf-8"))
        assert sidecar["downgraded_count"] == 1

    def test_flag_on_no_change_still_audits(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PRIMR_LABEL_HONESTY", "true")
        monkeypatch.setattr(
            "primr.qa.label_honesty.apply_label_honesty",
            lambda content: _downgrade_result(content, changed=False),
        )
        out = _maybe_apply_label_honesty("## S\nbody (Confirmed)", str(tmp_path))
        assert out == "## S\nbody (Confirmed)"
        # The audit sidecar is written even when nothing was downgraded.
        sidecar = json.loads((tmp_path / "_label_honesty.json").read_text(encoding="utf-8"))
        assert sidecar["downgraded_count"] == 0

    def test_failure_never_breaks_shipping(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PRIMR_LABEL_HONESTY", "yes")
        monkeypatch.setattr(
            "primr.qa.label_honesty.apply_label_honesty",
            MagicMock(side_effect=RuntimeError("judge offline")),
        )
        out = _maybe_apply_label_honesty("## S\nbody (Confirmed)", str(tmp_path))
        assert out == "## S\nbody (Confirmed)"  # original content preserved

    def test_full_stage_recomputes_qa_after_downgrade(self, seams, monkeypatch):
        monkeypatch.setenv("PRIMR_LABEL_HONESTY", "1")
        monkeypatch.setattr(
            "primr.qa.label_honesty.apply_label_honesty",
            lambda content: _downgrade_result(content + "\n[honesty]", changed=True),
        )
        result = seams["call"]()
        assert "[honesty]" in result.report_content
        # QA recomputed once for the base report and again after the downgrade.
        assert seams["qa"].call_count == 2


class TestLabelCitationTrustRow:
    """The deterministic, judge-free label-citation coverage row appears in the
    report trust summary whenever the report has Confirmed/Reported claims."""

    _REPORT = (
        "## Findings\n"
        "Revenue hit $9M. (Confirmed) [cite: 1]\n"
        "A bold claim with no citation. (Confirmed)\n\n"
        "## Sources\n1. https://acme.example/ir\n"
    )

    def test_row_present_with_coverage_ratio(self, seams):
        result = seams["call"](report_content=self._REPORT)
        stats = dict(result.report_trust_stats)
        assert "Label Citations" in stats
        # One of two Confirmed claims carries a resolvable citation.
        assert stats["Label Citations"].startswith("1/2")

    def test_row_omitted_when_no_traceable_claims(self, seams):
        result = seams["call"](report_content="## S\nMarket may shift. (Estimated)\n")
        stats = dict(result.report_trust_stats)
        assert "Label Citations" not in stats
