"""Coverage tests for primr.qa.simple_analyzer.SimpleQAAnalyzer.

The AI client is mocked so no real LLM calls are made. Covers the
assess_report happy path, the no-client and exhausted-retry fallbacks, the
retry/backoff branches (rate limit, quota, generic — sleeps mocked), prompt
building, report-type detection, citation counting, score conversion, and the
JSON/regex parse paths.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from primr.qa.models import ReportContent, ReportMetadata
from primr.qa.simple_analyzer import QA_DIMENSIONS, SimpleQAAnalyzer, SimpleQAResult

VALID_JSON = """{
    "ready_for_use": true,
    "confidence_level": "high",
    "scores": {
        "company_understanding": 4,
        "analytical_depth": 3,
        "actionable_intelligence": 4,
        "evidence_quality": 3,
        "structure_clarity": 4
    },
    "key_strengths": ["clear model", "good citations"],
    "areas_for_improvement": [],
    "recommendation": "Ready for internal use."
}"""


_DEFAULT_SECTIONS = {"Overview": "intro text", "Analysis": "deep text"}


def _report(content="Strategic analysis of value creation. [cite: 1, 2]", sections=None):
    if sections is None:
        sections = dict(_DEFAULT_SECTIONS)
    return ReportContent(
        company_name="Acme Corp",
        content=content,
        sections=sections,
        citations=["https://acme.example/a"],
        metadata=ReportMetadata(
            company_name="Acme Corp",
            generation_date=datetime(2024, 1, 1),
            generation_mode="full",
            model_used="test-model",
            file_path=Path("r.txt"),
        ),
        file_path=Path("r.txt"),
    )


@pytest.fixture
def analyzer():
    """Analyzer with the AI client patched out (no real network)."""
    with patch("primr.ai.client.get_client", return_value=MagicMock()):
        a = SimpleQAAnalyzer()
    return a


class TestSetup:
    def test_setup_failure_sets_client_none(self):
        with patch("primr.ai.client.get_client", side_effect=RuntimeError("no key")):
            a = SimpleQAAnalyzer()
        assert a.ai_client is None


class TestAssessReport:
    def test_no_client_returns_error_result(self, analyzer):
        analyzer.ai_client = None
        result = analyzer.assess_report(_report())
        assert isinstance(result, SimpleQAResult)
        assert result.ready_for_use is False
        assert result.error_message is not None

    def test_happy_path_primary_model(self, analyzer):
        analyzer.ai_client.generate.return_value = VALID_JSON
        result = analyzer.assess_report(_report())
        assert result.ready_for_use is True
        assert result.confidence_level == "high"
        assert result.parsing_success is True
        assert result.scores["company_understanding"] == 80  # 4 * 20

    def test_falls_back_to_secondary_model(self, analyzer):
        # Primary returns empty (None result), fallback returns valid JSON.
        analyzer.ai_client.generate.side_effect = ["", "", "", VALID_JSON]
        result = analyzer.assess_report(_report())
        assert result.ready_for_use is True

    def test_both_models_fail_returns_error(self, analyzer):
        analyzer.ai_client.generate.return_value = ""  # always too short
        result = analyzer.assess_report(_report())
        assert result.ready_for_use is False
        assert "failed" in result.recommendation.lower() or result.error_message

    def test_unexpected_exception_returns_error_result(self, analyzer):
        with patch.object(
            analyzer, "_build_assessment_prompt", side_effect=RuntimeError("boom")
        ):
            result = analyzer.assess_report(_report())
        assert result.ready_for_use is False


class TestTryAssessmentRetry:
    def test_rate_limit_retries_then_gives_up(self, analyzer, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        analyzer.ai_client.generate.side_effect = Exception("429 rate limit")
        result = analyzer._try_assessment_with_retry("p", "Acme", max_retries=2)
        assert result is not None
        assert "Rate limit" in result.recommendation or result.error_message

    def test_quota_exhausted_stops_immediately(self, analyzer):
        analyzer.ai_client.generate.side_effect = Exception("quota exceeded")
        result = analyzer._try_assessment_with_retry("p", "Acme", max_retries=3)
        assert result is not None
        assert "quota" in (result.error_message or "").lower() or "quota" in result.recommendation.lower()

    def test_generic_error_retries_then_returns_none(self, analyzer, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        analyzer.ai_client.generate.side_effect = Exception("transient glitch")
        result = analyzer._try_assessment_with_retry("p", "Acme", max_retries=2)
        assert result is None

    def test_short_response_then_none(self, analyzer):
        analyzer.ai_client.generate.return_value = "tiny"
        result = analyzer._try_assessment_with_retry("p", "Acme", max_retries=1)
        assert result is None

    def test_final_attempt_returns_parse_failure(self, analyzer):
        # Long but unparseable response; on final attempt returns the result.
        analyzer.ai_client.generate.return_value = "x" * 100  # > 20 chars, not JSON
        result = analyzer._try_assessment_with_retry("p", "Acme", max_retries=1)
        assert result is not None
        assert result.parsing_success is False


class TestPromptBuilding:
    def test_prompt_includes_company_and_sections(self, analyzer):
        prompt = analyzer._build_assessment_prompt(_report())
        assert "Acme Corp" in prompt
        assert "Overview" in prompt

    def test_prompt_no_sections(self, analyzer):
        prompt = analyzer._build_assessment_prompt(_report(sections={}))
        assert "No sections identified" in prompt


class TestCitationCounting:
    def test_counts_unique_inline_citations(self, analyzer):
        n = analyzer._count_inline_citations("[cite: 1, 2, 3] then [cite: 2, 4]")
        assert n == 4

    def test_no_citations(self, analyzer):
        assert analyzer._count_inline_citations("no citations here") == 0


class TestReportTypeDetection:
    def test_ai_strategy(self, analyzer):
        r = _report(content="Our ai strategy and digital strategy transformation")
        assert analyzer._determine_report_type(r) == "AI Strategy Report"

    def test_comprehensive_strategic(self, analyzer):
        content = "market analysis competitive landscape swot analysis financial overview"
        assert (
            analyzer._determine_report_type(_report(content=content))
            == "Comprehensive Strategic Analysis"
        )

    def test_strategic_report(self, analyzer):
        assert analyzer._determine_report_type(_report(content="general strategy here")) == "Strategic Report"

    def test_business_analysis_default(self, analyzer):
        assert (
            analyzer._determine_report_type(_report(content="just numbers and facts"))
            == "Business Analysis Report"
        )

    def test_comprehensive_by_size(self, analyzer):
        sections = {f"s{i}": "x" for i in range(60)}
        r = _report(content="z" * 51000, sections=sections)
        assert analyzer._determine_report_type(r) == "Comprehensive Strategic Analysis"


class TestEvaluationContext:
    def test_ai_strategy_context(self, analyzer):
        ctx = analyzer._get_evaluation_context("AI Strategy Report")
        assert "AI/STRATEGY" in ctx

    def test_research_context(self, analyzer):
        ctx = analyzer._get_evaluation_context("Business Analysis Report")
        assert "COMPANY RESEARCH" in ctx


class TestScoreConversion:
    def test_valid_scores_converted(self, analyzer):
        raw = dict.fromkeys(QA_DIMENSIONS, 3)
        converted = analyzer._validate_and_convert_scores(raw)
        assert all(v == 60 for v in converted.values())

    def test_non_dict_returns_none(self, analyzer):
        assert analyzer._validate_and_convert_scores(None) is None
        assert analyzer._validate_and_convert_scores([1, 2]) is None

    def test_missing_dimension_returns_none(self, analyzer):
        raw = {"company_understanding": 4}  # incomplete
        assert analyzer._validate_and_convert_scores(raw) is None

    def test_out_of_range_returns_none(self, analyzer):
        raw = dict.fromkeys(QA_DIMENSIONS, 9)
        assert analyzer._validate_and_convert_scores(raw) is None

    def test_non_numeric_returns_none(self, analyzer):
        raw = dict.fromkeys(QA_DIMENSIONS, "high")
        assert analyzer._validate_and_convert_scores(raw) is None


class TestParseJsonResponse:
    def test_parse_valid_json(self, analyzer):
        result = analyzer._parse_json_response(VALID_JSON)
        assert result.parsing_success is True
        assert result.ready_for_use is True

    def test_parse_regex_fallback(self, analyzer):
        text = '"ready_for_use": false, "confidence_level": "low", "recommendation": "Needs work"'
        result = analyzer._parse_json_response(text)
        assert result.parsing_success is False
        assert result.ready_for_use is False

    def test_parse_critical_error_uses_fallback(self, analyzer):
        with patch.object(
            analyzer.json_parser, "parse_qa_response", side_effect=RuntimeError("crash")
        ):
            result = analyzer._parse_json_response("anything")
        assert result.parsing_success is False
        assert "Manual review" in result.recommendation


class TestResultCreators:
    def test_create_error_result_rate_limit(self, analyzer):
        r = analyzer._create_error_result("Rate limit exceeded for primary model")
        assert "rate limit" in r.recommendation.lower()

    def test_create_error_result_quota(self, analyzer):
        r = analyzer._create_error_result("API quota exceeded today")
        assert "quota" in r.recommendation.lower()

    def test_create_error_result_client_unavailable(self, analyzer):
        r = analyzer._create_error_result("AI client not available")
        assert "configuration" in r.recommendation.lower()

    def test_create_error_result_parsing(self, analyzer):
        r = analyzer._create_error_result("parsing issue detected")
        assert "format" in r.recommendation.lower()

    def test_create_error_result_generic(self, analyzer):
        r = analyzer._create_error_result("some other failure")
        assert "Technical issue" in r.recommendation

    def test_create_parsing_fallback(self, analyzer):
        r = analyzer._create_parsing_fallback("garbled")
        assert r.ready_for_use is False
        assert r.parsing_success is False
