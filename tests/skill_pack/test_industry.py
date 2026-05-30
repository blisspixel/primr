"""Tests for industry classification.

Covers:
  - `classify_from_report`: regex parsing of structured industry fields
    from a primr strategic report.
  - `classify_via_llm`: the LLM-driven classification path with mocked
    grok_llm.
  - `classify_industry`: the orchestrator's resolution order
    (report → llm → unknown fallback).
"""

from __future__ import annotations

import json
from unittest.mock import patch

from primr.skill_pack.industry import (
    classify_from_report,
    classify_industry,
    classify_via_llm,
)
from primr.skill_pack.schema import IndustryClassification

# =============================================================================
# classify_from_report
# =============================================================================


class TestClassifyFromReport:
    def test_returns_none_for_short_text(self):
        assert classify_from_report("") is None
        assert classify_from_report("short text") is None
        assert classify_from_report("a" * 150) is None  # below 200 char floor

    def test_returns_none_when_no_fields_match(self):
        text = "a" * 250 + " no recognizable fields here"
        assert classify_from_report(text) is None

    def test_parses_industry_field(self):
        text = "x" * 200 + "\nIndustry: Cybersecurity\n"
        result = classify_from_report(text)
        assert result is not None
        assert result.industry_vertical == "Cybersecurity"
        assert result.source == "report"

    def test_parses_business_model_field(self):
        text = "x" * 200 + "\nBusiness model: B2B SaaS\n"
        result = classify_from_report(text)
        assert result is not None
        assert result.business_model == "B2B SaaS"

    def test_parses_stage_field(self):
        text = "x" * 200 + "\nCompany stage: Public / Mature\n"
        result = classify_from_report(text)
        assert result is not None
        assert result.company_stage == "Public / Mature"

    def test_high_confidence_when_three_or_more_fields_match(self):
        text = (
            "x" * 200
            + "\nIndustry: FinTech\nBusiness model: B2B SaaS\nStage: Growth\nEmployees: 1500\n"
        )
        result = classify_from_report(text)
        assert result is not None
        assert result.confidence == "High"
        assert result.industry_vertical == "FinTech"
        assert result.business_model == "B2B SaaS"

    def test_medium_confidence_with_two_fields(self):
        text = "x" * 200 + "\nIndustry: FinTech\nBusiness model: B2B SaaS\n"
        result = classify_from_report(text)
        assert result is not None
        assert result.confidence == "Medium"

    def test_low_confidence_with_one_field(self):
        text = "x" * 200 + "\nIndustry: FinTech\n"
        result = classify_from_report(text)
        assert result is not None
        assert result.confidence == "Low"

    def test_markdown_bullet_styles_parse(self):
        text = "x" * 200 + "\n- **Industry:** FinTech\n* **Business model:** B2B SaaS\n"
        result = classify_from_report(text)
        assert result is not None
        # Bullet variants should match; both fields captured.
        assert "FinTech" in result.industry_vertical
        assert "B2B SaaS" in result.business_model

    def test_cited_evidence_captured(self):
        text = "x" * 200 + "\nIndustry: Cybersecurity\nBusiness model: B2B SaaS\n"
        result = classify_from_report(text)
        assert result is not None
        assert len(result.cited_evidence) >= 2
        assert any("industry" in c.lower() for c in result.cited_evidence)


# =============================================================================
# classify_via_llm
# =============================================================================


class TestClassifyViaLlm:
    def test_returns_none_with_no_evidence(self):
        # All three evidence streams empty → no call made.
        result = classify_via_llm("Acme", "", "", "")
        assert result is None

    def test_parses_valid_llm_response(self):
        response = json.dumps(
            {
                "business_model": "B2B SaaS",
                "industry_vertical": "Developer Tools",
                "company_stage": "Growth / Late-stage",
                "employee_estimate": "Mid-market (500-5000)",
                "confidence": "High",
                "cited_evidence": ["dbt postings", "Snowflake DNS"],
            }
        )
        with patch("primr.ai.grok_client.grok_llm", return_value=response):
            result = classify_via_llm(
                "Acme", "Recon: Snowflake", "Hiring: dbt", "Research: SaaS"
            )
        assert result is not None
        assert result.business_model == "B2B SaaS"
        assert result.industry_vertical == "Developer Tools"
        assert result.confidence == "High"
        assert result.source == "llm"
        assert len(result.cited_evidence) == 2

    def test_returns_none_on_llm_exception(self):
        with patch(
            "primr.ai.grok_client.grok_llm",
            side_effect=RuntimeError("provider error"),
        ):
            result = classify_via_llm("Acme", "Recon: x", "", "")
        assert result is None

    def test_returns_none_on_malformed_json(self):
        with patch("primr.ai.grok_client.grok_llm", return_value="not json"):
            result = classify_via_llm("Acme", "Recon: x", "", "")
        assert result is None

    def test_handles_fenced_json_response(self):
        response = (
            "Here is the classification:\n```json\n"
            + json.dumps(
                {
                    "business_model": "Marketplace",
                    "industry_vertical": "Logistics",
                    "company_stage": "Public / Mature",
                    "employee_estimate": "Enterprise (5000+)",
                    "confidence": "Medium",
                    "cited_evidence": ["GMV"],
                }
            )
            + "\n```\n"
        )
        with patch("primr.ai.grok_client.grok_llm", return_value=response):
            result = classify_via_llm(
                "Acme", "Recon: GMV", "Hiring: x", ""
            )
        assert result is not None
        assert result.business_model == "Marketplace"


# =============================================================================
# classify_industry — orchestrator
# =============================================================================


class TestClassifyIndustryOrchestrator:
    def test_report_path_wins_when_confident(self):
        report = (
            "x" * 200
            + "\nIndustry: FinTech\nBusiness model: B2B SaaS\nStage: Growth\n"
        )
        with patch("primr.ai.grok_client.grok_llm") as mock_llm:
            result = classify_industry(
                company_name="Acme",
                recon_text="",
                hiring_text="",
                research_text="",
                report_text=report,
            )
        # Report path was taken; LLM never called.
        mock_llm.assert_not_called()
        assert result.source == "report"

    def test_falls_through_to_llm_when_report_absent(self):
        response = json.dumps(
            {
                "business_model": "B2B SaaS",
                "industry_vertical": "Developer Tools",
                "company_stage": "Early",
                "employee_estimate": "Early (50-500)",
                "confidence": "High",
                "cited_evidence": ["seed round"],
            }
        )
        with patch("primr.ai.grok_client.grok_llm", return_value=response):
            result = classify_industry(
                company_name="Acme",
                recon_text="Recon: Snowflake",
                hiring_text="Hiring: dbt",
                research_text="Research: SaaS",
                report_text="",
            )
        assert result.source == "llm"
        assert result.business_model == "B2B SaaS"

    def test_unknown_when_both_paths_fail(self):
        with patch(
            "primr.ai.grok_client.grok_llm",
            side_effect=RuntimeError("provider down"),
        ):
            result = classify_industry(
                company_name="Acme",
                recon_text="Recon: x",
                hiring_text="",
                research_text="",
                report_text="",
            )
        # LLM failed; report wasn't supplied. Fallback placeholder.
        assert result.source == "unavailable"
        assert result.business_model == "Unknown"

    def test_unknown_when_no_evidence_at_all(self):
        result = classify_industry(
            company_name="Acme",
            recon_text="",
            hiring_text="",
            research_text="",
            report_text="",
        )
        # No evidence → LLM returns None → fallback placeholder.
        assert result.business_model == "Unknown"
        assert result.source == "unavailable"


# =============================================================================
# Default IndustryClassification
# =============================================================================


class TestIndustryClassificationDefault:
    def test_default_source_is_unknown(self):
        """Bug 6 regression: default source should be 'unknown' (not the
        stale 'heuristic' value from the deprecated heuristic path)."""
        ic = IndustryClassification()
        assert ic.source == "unknown"
        assert ic.business_model == "Unknown"
        assert ic.confidence == "Low"
