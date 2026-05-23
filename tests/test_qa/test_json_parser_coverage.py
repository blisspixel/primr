"""Coverage tests for primr.qa.json_parser.SimpleJSONParser.

Pure-logic tests for every extraction strategy, structure validation, the
regex fallback (including scores + keyword text extraction), and the parsing
statistics helpers.
"""

from __future__ import annotations

import pytest

from primr.qa.json_parser import SimpleJSONParser

VALID_PAYLOAD = {
    "ready_for_use": True,
    "confidence_level": "high",
    "key_strengths": ["clear", "thorough"],
    "areas_for_improvement": [],
    "recommendation": "Use it.",
}


def _valid_json_text():
    import json

    return json.dumps(VALID_PAYLOAD)


@pytest.fixture
def parser():
    return SimpleJSONParser()


class TestParseQAResponse:
    def test_empty_response_returns_none(self, parser):
        assert parser.parse_qa_response("   ") is None

    def test_plain_json(self, parser):
        result = parser.parse_qa_response(_valid_json_text())
        assert result["ready_for_use"] is True
        assert parser.successful_extractions == 1

    def test_markdown_json_block(self, parser):
        text = f"Here:\n```json\n{_valid_json_text()}\n```\nDone"
        result = parser.parse_qa_response(text)
        assert result is not None

    def test_markdown_json_block_unclosed(self, parser):
        text = f"```json\n{_valid_json_text()}"
        result = parser.parse_qa_response(text)
        assert result is not None

    def test_generic_code_block(self, parser):
        text = f"```\n{_valid_json_text()}\n```"
        result = parser.parse_qa_response(text)
        assert result is not None

    def test_invalid_json_returns_none(self, parser):
        assert parser.parse_qa_response("{ broken json") is None

    def test_no_extractable_json_returns_none(self, parser):
        assert parser.parse_qa_response("totally unrelated prose") is None

    def test_structure_validation_failure_returns_none(self, parser):
        # Valid JSON but missing required fields.
        assert parser.parse_qa_response('{"foo": 1}') is None

    def test_scores_included_when_valid(self, parser):
        import json

        payload = dict(VALID_PAYLOAD)
        payload["scores"] = {"company_understanding": 4}
        result = parser.parse_qa_response(json.dumps(payload))
        assert result["scores"]["company_understanding"] == 4


class TestExtractJsonStrategies:
    def test_brace_matching_strategy(self, parser):
        text = f"prefix {_valid_json_text()} suffix"
        extracted = parser._extract_json_from_response(text)
        assert extracted.startswith("{")
        assert extracted.endswith("}")

    def test_generic_block_non_json_falls_through(self, parser):
        # Code block holds non-JSON, then a real JSON object follows.
        text = "```\nnot json here\n```\n" + _valid_json_text()
        extracted = parser._extract_json_from_response(text)
        assert '"ready_for_use"' in extracted

    def test_pattern_strategy_for_unbalanced_braces(self, parser):
        # Brace matching never closes; strategy 4 regex catches ready_for_use.
        text = 'noise {"ready_for_use": true} trailing {'
        extracted = parser._extract_json_from_response(text)
        assert extracted is not None
        assert "ready_for_use" in extracted

    def test_no_json_returns_none(self, parser):
        assert parser._extract_json_from_response("nothing here") is None


class TestValidateStructure:
    def test_missing_field(self, parser):
        data = dict(VALID_PAYLOAD)
        del data["recommendation"]
        assert parser._validate_qa_structure(data) is False

    def test_ready_not_bool(self, parser):
        data = dict(VALID_PAYLOAD, ready_for_use="yes")
        assert parser._validate_qa_structure(data) is False

    def test_invalid_confidence(self, parser):
        data = dict(VALID_PAYLOAD, confidence_level="superb")
        assert parser._validate_qa_structure(data) is False

    def test_strengths_not_list(self, parser):
        data = dict(VALID_PAYLOAD, key_strengths="nope")
        assert parser._validate_qa_structure(data) is False

    def test_improvements_not_list(self, parser):
        data = dict(VALID_PAYLOAD, areas_for_improvement="nope")
        assert parser._validate_qa_structure(data) is False

    def test_recommendation_empty(self, parser):
        data = dict(VALID_PAYLOAD, recommendation="   ")
        assert parser._validate_qa_structure(data) is False

    def test_scores_not_dict_is_dropped(self, parser):
        data = dict(VALID_PAYLOAD, scores=[1, 2, 3])
        assert parser._validate_qa_structure(data) is True
        assert "scores" not in data

    def test_scores_non_numeric_dropped(self, parser):
        data = dict(VALID_PAYLOAD, scores={"a": "high"})
        assert parser._validate_qa_structure(data) is True
        assert "scores" not in data

    def test_scores_numeric_kept(self, parser):
        data = dict(VALID_PAYLOAD, scores={"a": 4, "b": 5})
        assert parser._validate_qa_structure(data) is True
        assert data["scores"] == {"a": 4, "b": 5}


class TestRegexFallback:
    def test_extracts_all_fields(self, parser):
        text = """
        "ready_for_use": true,
        "confidence_level": "medium",
        "recommendation": "Looks reasonable",
        "key_strengths": ["good structure", "clear writing"],
        "areas_for_improvement": ["needs citations"]
        """
        result = parser.extract_with_regex_fallback(text)
        assert result["ready_for_use"] is True
        assert result["confidence_level"] == "medium"
        assert result["recommendation"] == "Looks reasonable"
        assert "good structure" in result["key_strengths"]
        assert "needs citations" in result["areas_for_improvement"]

    def test_defaults_when_nothing_matches(self, parser):
        result = parser.extract_with_regex_fallback("opaque text with no markers")
        assert result["ready_for_use"] is False
        assert result["confidence_level"] == "low"
        assert isinstance(result["key_strengths"], list)

    def test_scores_block_extracted(self, parser):
        text = '"scores": { "company_understanding": 4, "analytical_depth": 3 }'
        result = parser.extract_with_regex_fallback(text)
        assert result["scores"]["company_understanding"] == 4
        assert result["scores"]["analytical_depth"] == 3

    def test_keyword_text_fallback_for_strengths(self, parser):
        text = "The report is well-structured and demonstrates thorough analysis."
        result = parser.extract_with_regex_fallback(text)
        assert len(result["key_strengths"]) > 0

    def test_keyword_text_fallback_for_improvements(self, parser):
        text = "There are missing citations and several unclear sections with gaps."
        result = parser.extract_with_regex_fallback(text)
        assert len(result["areas_for_improvement"]) > 0


class TestKeywordHelpers:
    def test_extract_strengths_limited_to_three(self, parser):
        text = (
            "well-structured clear strategic comprehensive analysis "
            "good citations actionable insights thorough detailed extensive"
        )
        strengths = parser._extract_strengths_from_text(text)
        assert len(strengths) == 3

    def test_extract_improvements_limited_to_three(self, parser):
        text = (
            "missing citations unclear needs more insufficient "
            "contradictions inconsistent gaps"
        )
        improvements = parser._extract_improvements_from_text(text)
        assert len(improvements) == 3

    def test_extract_strengths_empty(self, parser):
        assert parser._extract_strengths_from_text("nothing notable") == []


class TestStats:
    def test_get_parsing_stats_zero_attempts(self, parser):
        stats = parser.get_parsing_stats()
        assert stats["total_attempts"] == 0
        assert stats["success_rate"] == 0

    def test_get_parsing_stats_after_success(self, parser):
        parser.parse_qa_response(_valid_json_text())
        stats = parser.get_parsing_stats()
        assert stats["total_attempts"] == 1
        assert stats["successful_extractions"] == 1
        assert stats["success_rate"] == 100.0
        assert stats["failed_extractions"] == 0

    def test_reset_stats(self, parser):
        parser.parse_qa_response(_valid_json_text())
        parser.reset_stats()
        assert parser.extraction_attempts == 0
        assert parser.successful_extractions == 0
