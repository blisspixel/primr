"""Coverage tests for primr.qa.analyzer.QAAnalyzer.

The AI client and retry sleeps are mocked so no real LLM calls or delays
occur. Covers analyze_report (success, no-client fallback, parse-failure
fallback, retry-exhaustion fallback), prompt building, report-type
identification, expected-section selection, the section-score template,
_parse_ai_response (markdown / brace / no-json / malformed-issue branches),
and the fallback analysis builder.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from primr.qa.analyzer import QAAnalyzer
from primr.qa.models import (
    QAAnalysis,
    ReportContent,
    ReportMetadata,
)


def _report(content="Some report content about the business.", sections=None, citations=None):
    if sections is None:
        sections = {"Executive Summary": "summary", "Analysis": "details"}
    if citations is None:
        citations = ["https://acme.example/1", "https://acme.example/2"]
    return ReportContent(
        company_name="Acme Corp",
        content=content,
        sections=sections,
        citations=citations,
        metadata=ReportMetadata(
            company_name="Acme Corp",
            generation_date=datetime(2024, 1, 1),
            generation_mode="full",
            model_used="test-model",
            file_path=Path("r.txt"),
        ),
        file_path=Path("r.txt"),
    )


def _valid_analysis_json(report):
    return json.dumps(
        {
            "overall_score": 85,
            "section_scores": {"Analysis": 80},
            "citation_check": {
                "total_citations": len(report.citations),
                "valid_citations": len(report.citations),
                "broken_links": [],
                "unsupported_claims": [],
                "score": 85,
            },
            "logic_check": {
                "contradictions_found": [],
                "unsupported_leaps": [],
                "score": 85,
            },
            "completeness_check": {
                "expected_sections": ["Executive Summary"],
                "missing_sections": [],
                "weak_sections": [],
                "score": 85,
            },
            "issues": [
                {
                    "issue_type": "logical",
                    "severity": "low",
                    "section": "Analysis",
                    "description": "Minor leap",
                    "location": "para 2",
                    "suggestion": "Add evidence",
                }
            ],
            "confidence_assessment": {
                "section_confidence": {"Analysis": 80},
                "overall_confidence": 85,
            },
        }
    )


@pytest.fixture
def analyzer():
    with patch("primr.ai.client.get_client", return_value=MagicMock()):
        a = QAAnalyzer()
    return a


class TestSetup:
    def test_setup_failure_sets_client_none(self):
        with patch("primr.ai.client.get_client", side_effect=RuntimeError("no key")):
            a = QAAnalyzer()
        assert a.ai_client is None


class TestAnalyzeReport:
    def test_no_client_uses_fallback(self, analyzer):
        analyzer.ai_client = None
        result = analyzer.analyze_report(_report())
        assert isinstance(result, QAAnalysis)
        assert result.overall_score == 50

    def test_success_path(self, analyzer):
        report = _report()
        analyzer.ai_client.generate.return_value = _valid_analysis_json(report)
        result = analyzer.analyze_report(report)
        assert isinstance(result, QAAnalysis)
        assert result.overall_score == 85
        assert len(result.issues) == 1

    def test_short_response_triggers_fallback(self, analyzer, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        analyzer.ai_client.generate.return_value = "too short"
        result = analyzer.analyze_report(_report())
        # Retry exhausts -> handled -> fallback analysis.
        assert result.overall_score == 50

    def test_exception_during_analysis_uses_fallback(self, analyzer, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        analyzer.ai_client.generate.side_effect = RuntimeError("model exploded")
        result = analyzer.analyze_report(_report())
        assert result.overall_score == 50


class TestBuildPrompt:
    def test_prompt_contains_company_and_dimensions(self, analyzer):
        prompt = analyzer._build_qa_prompt(_report())
        assert "Acme Corp" in prompt
        assert "CITATION ACCURACY" in prompt
        assert "COMPLETENESS" in prompt


class TestIdentifyReportType:
    def test_ai_strategy_from_content(self, analyzer):
        assert analyzer._identify_report_type(_report(content="our ai strategy roadmap")) == "AI Strategy"

    def test_ai_strategy_from_section(self, analyzer):
        r = _report(sections={"AI Strategy": "x"})
        assert analyzer._identify_report_type(r) == "AI Strategy"

    def test_strategic_analysis(self, analyzer):
        assert (
            analyzer._identify_report_type(_report(content="strategic overview of firm"))
            == "Strategic Analysis"
        )

    def test_company_overview(self, analyzer):
        assert (
            analyzer._identify_report_type(_report(content="company overview and history"))
            == "Company Overview"
        )

    def test_financial_analysis(self, analyzer):
        assert (
            analyzer._identify_report_type(_report(content="financial analysis of revenue"))
            == "Financial Analysis"
        )

    def test_market_research(self, analyzer):
        assert (
            analyzer._identify_report_type(_report(content="market analysis and trends"))
            == "Market Research"
        )

    def test_default_type(self, analyzer):
        assert (
            analyzer._identify_report_type(_report(content="generic text here"))
            == "Business Intelligence Report"
        )


class TestExpectedSections:
    def test_ai_strategy_sections(self, analyzer):
        sections = analyzer._get_expected_sections("AI Strategy", [])
        assert "Implementation Roadmap" in sections
        assert len(sections) <= 10

    def test_unknown_type_uses_base_only(self, analyzer):
        sections = analyzer._get_expected_sections("Unknown", [])
        assert "Executive Summary" in sections

    def test_existing_long_sections_appended(self, analyzer):
        sections = analyzer._get_expected_sections(
            "Unknown", ["A Very Distinct Custom Section"]
        )
        assert "A Very Distinct Custom Section" in sections

    def test_short_existing_section_skipped(self, analyzer):
        sections = analyzer._get_expected_sections("Unknown", ["abc"])
        assert "abc" not in sections


class TestSectionScoreTemplate:
    def test_template_format(self, analyzer):
        out = analyzer._format_section_scores_template(["Intro", "Body"])
        assert '"Intro": 0' in out
        assert '"Body": 0' in out

    def test_template_escapes_quotes(self, analyzer):
        out = analyzer._format_section_scores_template(['Weird"Name'])
        assert '\\"' in out

    def test_template_limits_to_five(self, analyzer):
        out = analyzer._format_section_scores_template([f"S{i}" for i in range(10)])
        assert out.count(":") == 5


class TestParseAIResponse:
    def test_parse_markdown_block(self, analyzer):
        report = _report()
        text = f"```json\n{_valid_analysis_json(report)}\n```"
        result = analyzer._parse_ai_response(text, report)
        assert result.overall_score == 85

    def test_parse_markdown_block_unclosed(self, analyzer):
        report = _report()
        text = f"```json\n{_valid_analysis_json(report)}"
        result = analyzer._parse_ai_response(text, report)
        assert result.overall_score == 85

    def test_parse_brace_extraction(self, analyzer):
        report = _report()
        text = f"prefix {_valid_analysis_json(report)} suffix"
        result = analyzer._parse_ai_response(text, report)
        assert result.overall_score == 85

    def test_no_json_uses_fallback(self, analyzer):
        report = _report()
        result = analyzer._parse_ai_response("no json at all", report)
        assert result.overall_score == 50

    def test_malformed_json_uses_fallback(self, analyzer):
        report = _report()
        result = analyzer._parse_ai_response("{ broken: ", report)
        assert result.overall_score == 50

    def test_malformed_issue_skipped(self, analyzer):
        report = _report()
        data = json.loads(_valid_analysis_json(report))
        # Add an issue with an invalid issue_type so it is skipped.
        data["issues"].append(
            {
                "issue_type": "not_a_real_type",
                "severity": "low",
                "section": "x",
                "description": "y",
                "location": "z",
            }
        )
        result = analyzer._parse_ai_response(json.dumps(data), report)
        # Only the one valid issue survives.
        assert len(result.issues) == 1

    def test_missing_fields_use_defaults(self, analyzer):
        report = _report()
        # Minimal valid JSON object; defaults fill the rest.
        result = analyzer._parse_ai_response('{"overall_score": 70}', report)
        assert result.overall_score == 70
        assert result.citation_check.score == 50


class TestFallbackAnalysis:
    def test_fallback_structure(self, analyzer):
        report = _report()
        result = analyzer._create_fallback_analysis(report)
        assert result.overall_score == 50
        assert len(result.issues) == 1
        assert result.citation_check.total_citations == len(report.citations)
        assert result.model_used == analyzer.model_name
