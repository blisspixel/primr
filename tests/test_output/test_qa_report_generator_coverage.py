"""Coverage tests for primr.output.qa_report_generator.QAReportGenerator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from primr.output.qa_report_generator import QAReportGenerator
from primr.qa.models import (
    CitationCheckResult,
    ClassifiedIssue,
    CompletenessCheckResult,
    ConfidenceAssessment,
    IssueType,
    LogicCheckResult,
    QAAnalysis,
    Severity,
)


def _make_analysis(
    *,
    overall_score: int = 85,
    timestamp: datetime | None = None,
    with_optional: bool = True,
) -> QAAnalysis:
    ts = timestamp or datetime(2026, 5, 22, 10, 30, 0)
    issues = []
    if with_optional:
        issues = [
            ClassifiedIssue(
                issue_type=IssueType.CITATION,
                severity=Severity.CRITICAL,
                section="Financials",
                description="Missing source",
                location="line 12",
                suggestion="Add citation",
            ),
            ClassifiedIssue(
                issue_type=IssueType.LOGICAL,
                severity=Severity.HIGH,
                section="Strategy",
                description="Logic gap",
                location="line 30",
                suggestion=None,
            ),
        ]
    return QAAnalysis(
        overall_score=overall_score,
        section_scores={"Financials": 80} if with_optional else {},
        issues=issues,
        citation_check=CitationCheckResult(
            total_citations=10,
            valid_citations=8,
            broken_links=["https://broken.example"] if with_optional else [],
            unsupported_claims=["claim X"] if with_optional else [],
            score=70 if with_optional else 90,
        ),
        logic_check=LogicCheckResult(
            contradictions_found=["A vs B"] if with_optional else [],
            unsupported_leaps=["leap Y"] if with_optional else [],
            score=70 if with_optional else 90,
        ),
        completeness_check=CompletenessCheckResult(
            expected_sections=["A", "B"],
            missing_sections=["B"] if with_optional else [],
            weak_sections=["A"] if with_optional else [],
            score=70 if with_optional else 90,
        ),
        confidence_assessment=ConfidenceAssessment(
            section_confidence={"Financials": 80}, overall_confidence=82
        ),
        timestamp=ts,
        model_used="test-model",
    )


# --------------------------------------------------------------------------- #
# output_dir property
# --------------------------------------------------------------------------- #
def test_output_dir_default():
    gen = QAReportGenerator()
    assert gen.output_dir == Path("output")


def test_output_dir_setter(tmp_path):
    gen = QAReportGenerator()
    gen.output_dir = tmp_path
    assert gen.output_dir == tmp_path


# --------------------------------------------------------------------------- #
# save_detailed_analysis
# --------------------------------------------------------------------------- #
def test_save_detailed_analysis_writes_file(tmp_path):
    gen = QAReportGenerator(output_dir=tmp_path)
    analysis = _make_analysis()
    path = gen.save_detailed_analysis("Acme Corp", analysis)
    assert path is not None
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Quality Assessment Report for Acme Corp" in text
    assert "Broken Links" in text
    assert "Contradictions Found" in text
    assert "Missing Sections" in text
    assert "DETAILED ISSUES" in text
    assert "RECOMMENDATIONS" in text


def test_save_detailed_analysis_sanitizes_company_name(tmp_path):
    gen = QAReportGenerator(output_dir=tmp_path)
    analysis = _make_analysis()
    path = gen.save_detailed_analysis("Acme & Co / Ltd", analysis)
    assert path is not None
    assert "and" in path.name
    assert "&" not in path.name
    assert "/" not in path.name


def test_save_detailed_analysis_handles_write_failure(tmp_path):
    gen = QAReportGenerator(output_dir=tmp_path)
    analysis = _make_analysis()
    with patch.object(Path, "write_text", side_effect=OSError("denied")):
        result = gen.save_detailed_analysis("Acme Corp", analysis)
    assert result is None


# --------------------------------------------------------------------------- #
# _generate_detailed_report — minimal (no optional sections)
# --------------------------------------------------------------------------- #
def test_generate_detailed_report_minimal():
    gen = QAReportGenerator()
    analysis = _make_analysis(overall_score=95, with_optional=False)
    report = gen._generate_detailed_report("CleanCo", analysis)
    assert "Overall Quality Score: 95/100" in report.summary
    assert "NEEDS ATTENTION" not in report.summary
    # No optional sub-lists present.
    assert "Broken Links" not in report.detailed_findings
    assert "DETAILED ISSUES" not in report.detailed_findings


def test_generate_detailed_report_low_score_flags_attention():
    gen = QAReportGenerator()
    analysis = _make_analysis(overall_score=50)
    report = gen._generate_detailed_report("LowCo", analysis)
    assert "NEEDS ATTENTION" in report.summary


# --------------------------------------------------------------------------- #
# _generate_recommendations
# --------------------------------------------------------------------------- #
def test_generate_recommendations_low_scores():
    gen = QAReportGenerator()
    analysis = _make_analysis(overall_score=50)
    recs = gen._generate_recommendations(analysis)
    assert any("critical issues" in r for r in recs)
    assert any("citations" in r for r in recs)
    assert any("logical consistency" in r for r in recs)
    assert any("missing sections" in r for r in recs)
    assert any("1 critical" in r for r in recs)
    assert any("1 high-priority" in r for r in recs)


def test_generate_recommendations_acceptable():
    gen = QAReportGenerator()
    analysis = _make_analysis(overall_score=95, with_optional=False)
    recs = gen._generate_recommendations(analysis)
    assert recs == ["Report quality is acceptable for use"]
