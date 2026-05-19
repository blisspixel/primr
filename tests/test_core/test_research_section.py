"""Unit tests for research_section in primr.core.research_agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.research_agent import research_section


@pytest.fixture
def folder(tmp_path):
    f = tmp_path / "work"
    f.mkdir()
    return str(f)


class TestResearchSection:
    def test_unknown_section_returns_empty(self, folder):
        result = research_section(
            "UnknownSectionName",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="overview",
            summarized_insights="insights",
        )
        assert result == ""

    def test_company_name_section_returns_company_name(self, folder):
        result = research_section(
            "Company Name",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="x",
            summarized_insights="x",
        )
        assert result == "Acme"

    def test_website_section_returns_website(self, folder):
        result = research_section(
            "Website",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="x",
            summarized_insights="x",
        )
        assert result == "https://acme.example"

    def test_industry_section_returns_industry(self, folder):
        result = research_section(
            "Industry",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="x",
            summarized_insights="x",
        )
        assert result == "Tech"

    def test_metadata_section_with_none_value(self, folder):
        result = research_section(
            "Website",
            company_name="Acme",
            website=None,
            industry="Tech",
            folder_path=folder,
            overview="x",
            summarized_insights="x",
        )
        # None becomes "N/A" when written
        assert result is None  # The function returns the raw value

    def test_full_section_generates_response(self, folder, monkeypatch):
        # Mock the LLM call
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(
                return_value=(
                    "Generated section body with sufficient detail. " * 10
                )
            ),
        )
        # Mock grader to skip the refinement path
        monkeypatch.setattr(
            "primr.core.research_agent.grade_report",
            MagicMock(return_value=(80, False, "good")),
        )
        result = research_section(
            "Detailed Products/Services",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="overview body",
            summarized_insights="insights body",
        )
        assert "Generated section body" in result

    def test_short_response_replaced_with_placeholder(self, folder, monkeypatch):
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="too short"),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.grade_report",
            MagicMock(return_value=(80, False, "good")),
        )
        result = research_section(
            "Detailed Products/Services",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="overview",
            summarized_insights="insights",
        )
        assert "No detailed" in result

    def test_grader_exception_swallowed(self, folder, monkeypatch):
        monkeypatch.setattr(
            "primr.core.research_agent.llm",
            MagicMock(return_value="x" * 200),
        )
        # Grader raises -> should not crash; just skip refinement.
        monkeypatch.setattr(
            "primr.core.research_agent.grade_report",
            MagicMock(side_effect=RuntimeError("grade failed")),
        )
        result = research_section(
            "Detailed Products/Services",
            company_name="Acme",
            website="https://acme.example",
            industry="Tech",
            folder_path=folder,
            overview="overview",
            summarized_insights="insights",
        )
        # Function should still complete and write something.
        assert result
