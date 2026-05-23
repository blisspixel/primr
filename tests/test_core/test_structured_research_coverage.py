"""
Coverage-focused tests for primr.core.structured_research.

Exercises the dataclasses, metadata helpers, single-section research,
refinement branch, and the full run_research pipeline with all scraping,
search, summarization, and LLM calls mocked.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from primr.core.structured_research import (
    AnalysisResult,
    ResearchContext,
    ScrapedData,
    _get_metadata_value,
    _refine_section_if_needed,
    generate_initial_overview,
    research_section,
    run_research,
)

# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


def test_scraped_data_properties():
    sd = ScrapedData(
        website_pages={"a": "1", "b": "2"},
        external_sources={"c": "3"},
    )
    assert sd.page_count == 2
    assert sd.source_count == 1
    assert sd.all_content == {"a": "1", "b": "2", "c": "3"}


def test_scraped_data_defaults():
    sd = ScrapedData()
    assert sd.page_count == 0
    assert sd.source_count == 0


# ---------------------------------------------------------------------------
# _get_metadata_value
# ---------------------------------------------------------------------------


def test_metadata_company_name():
    assert _get_metadata_value("Company Name", "Acme", "https://a.com", "Tech") == "Acme"


def test_metadata_website():
    assert _get_metadata_value("Website", "Acme", "https://a.com", "Tech") == "https://a.com"


def test_metadata_website_none():
    assert _get_metadata_value("Website", "Acme", None, "Tech") == "N/A"


def test_metadata_industry():
    assert _get_metadata_value("Industry", "Acme", "https://a.com", "Tech") == "Tech"


def test_metadata_unknown_section():
    assert _get_metadata_value("Other", "Acme", "https://a.com", "Tech") == "N/A"


# ---------------------------------------------------------------------------
# research_section
# ---------------------------------------------------------------------------


def test_research_section_unknown_returns_empty():
    assert research_section("NotARealSection", "Acme", None, "Tech", "/x", "ov", "ins") == ""


def test_research_section_metadata(tmp_path):
    with patch("primr.core.structured_research.save_section_output") as mock_save:
        out = research_section(
            "Company Name", "Acme", "https://a.com", "Tech", str(tmp_path), "ov", "ins"
        )
    assert out == "Acme"
    assert mock_save.called


def test_research_section_complex_with_content(tmp_path):
    with (
        patch(
            "primr.core.structured_research._generate_section_content",
            return_value="x" * 200,
        ),
        patch(
            "primr.core.structured_research._refine_section_if_needed",
            side_effect=lambda resp, *a, **k: resp,
        ),
        patch("primr.core.structured_research.save_section_output") as mock_save,
    ):
        out = research_section(
            "Mission & Vision", "Acme", "https://a.com", "Tech", str(tmp_path), "ov", "ins"
        )
    assert len(out) >= 50
    assert mock_save.called


def test_research_section_short_content_gets_placeholder(tmp_path):
    with (
        patch("primr.core.structured_research._generate_section_content", return_value="hi"),
        patch(
            "primr.core.structured_research._refine_section_if_needed",
            side_effect=lambda resp, *a, **k: resp,
        ),
        patch("primr.core.structured_research.save_section_output"),
    ):
        out = research_section(
            "Mission & Vision", "Acme", "https://a.com", "Tech", str(tmp_path), "ov", "ins"
        )
    assert out == "No detailed Mission & Vision information available for Acme."


# ---------------------------------------------------------------------------
# _refine_section_if_needed
# ---------------------------------------------------------------------------


def test_refine_no_research_needed():
    with patch(
        "primr.core.structured_research.grade_report",
        return_value=(95, False, "good"),
    ):
        out = _refine_section_if_needed("original", "Mission", "Acme", None, "ov", "ins")
    assert out == "original"


def test_refine_triggers_additional_research():
    with (
        patch(
            "primr.core.structured_research.grade_report",
            return_value=(40, True, "needs more"),
        ),
        patch(
            "primr.core.structured_research.generate_search_queries",
            return_value=["q1"],
        ),
        patch(
            "primr.core.structured_research.search_web",
            return_value=[{"title": "T", "url": "https://u.com", "snippet": "snip"}],
        ),
        patch(
            "primr.core.structured_research.llm",
            return_value="refined content",
        ),
    ):
        out = _refine_section_if_needed("original", "Mission", "Acme", "https://a.com", "ov", "ins")
    assert out == "refined content"


def test_refine_swallows_exception():
    with patch(
        "primr.core.structured_research.grade_report",
        side_effect=RuntimeError("grade failed"),
    ):
        out = _refine_section_if_needed("original", "Mission", "Acme", None, "ov", "ins")
    assert out == "original"


# ---------------------------------------------------------------------------
# generate_initial_overview
# ---------------------------------------------------------------------------


def test_generate_initial_overview_writes_file(tmp_path):
    with (
        patch(
            "primr.core.structured_research.generate_prompt",
            return_value="prompt text",
        ),
        patch("primr.core.structured_research.llm", return_value="OVERVIEW BODY"),
    ):
        out = generate_initial_overview("Acme", "https://a.com", "Tech", str(tmp_path))
    assert out == "OVERVIEW BODY"
    written = list(tmp_path.glob("*_Draft_Overview.txt"))
    assert written
    assert written[0].read_text(encoding="utf-8") == "OVERVIEW BODY"


# ---------------------------------------------------------------------------
# run_research full pipeline (all I/O mocked)
# ---------------------------------------------------------------------------


def test_run_research_pipeline(tmp_path):
    progress_msgs = []

    with (
        patch(
            "primr.core.structured_research.create_working_folder",
            return_value=str(tmp_path),
        ),
        patch(
            "primr.core.structured_research.fetch_web_content",
            return_value={"https://a.com": "page content"},
        ),
        patch(
            "primr.core.structured_research.generate_external_search_queries",
            return_value=["news"],
        ),
        patch("primr.core.structured_research.search_web", return_value=[]),
        patch(
            "primr.core.structured_research.summarize_scraped_content",
            return_value="summary insights",
        ),
        patch(
            "primr.core.structured_research.generate_prompt",
            return_value="prompt",
        ),
        patch("primr.core.structured_research.llm", return_value="Tech"),
        patch(
            "primr.core.structured_research.research_section",
            return_value="section body",
        ),
    ):
        results = run_research(
            "Acme", "https://a.com", on_progress=progress_msgs.append
        )

    assert isinstance(results, dict)
    assert progress_msgs  # progress callback fired


def test_run_research_limited_pages_warns(tmp_path):
    msgs = []
    with (
        patch(
            "primr.core.structured_research.create_working_folder",
            return_value=str(tmp_path),
        ),
        patch(
            "primr.core.structured_research.fetch_web_content",
            return_value={"https://a.com": "only one"},
        ),
        patch(
            "primr.core.structured_research.generate_external_search_queries",
            return_value=[],
        ),
        patch("primr.core.structured_research.search_web", return_value=[]),
        patch(
            "primr.core.structured_research.summarize_scraped_content",
            return_value="",
        ),
        patch("primr.core.structured_research.generate_prompt", return_value="p"),
        patch("primr.core.structured_research.llm", return_value="Tech"),
        patch("primr.core.structured_research.research_section", return_value="body"),
    ):
        run_research("Acme", "https://a.com", on_progress=msgs.append)

    assert any("Limited website access" in m for m in msgs)


# ---------------------------------------------------------------------------
# ResearchContext / AnalysisResult basic construction
# ---------------------------------------------------------------------------


def test_research_context_fields():
    ctx = ResearchContext(
        company_name="Acme",
        website="https://a.com",
        folder_path="/tmp/x",
        industry="Tech",
        overview="ov",
        summarized_insights="ins",
    )
    assert ctx.company_name == "Acme"
    assert ctx.industry == "Tech"


def test_analysis_result_fields():
    ar = AnalysisResult(summarized_content="s", industry="Tech", overview="ov")
    assert ar.industry == "Tech"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
