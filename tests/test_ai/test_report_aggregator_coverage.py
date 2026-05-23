"""Coverage tests for primr.ai.report_aggregator.

Targets aggregate() with missing chapters, TOC generation, header building,
chapter cleaning (both header branches), citation consolidation/dedupe,
transition smoothing (success + failure), estimated_pages, and the singleton
accessors. genai is mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.report_aggregator import (
    AggregatedReport,
    ReportAggregator,
    get_report_aggregator,
    reset_report_aggregator,
)
from primr.ai.research_executor import ChapterResult


@pytest.fixture
def aggregator():
    with (
        patch("primr.ai.report_aggregator.genai.Client") as mock_client_class,
        patch("primr.ai.report_aggregator.get_settings") as mock_get,
    ):
        mock_get.return_value.api.gemini_key = "test-key"
        inst = MagicMock()
        mock_client_class.return_value = inst
        agg = ReportAggregator()
        agg._mock_client = inst
        yield agg


# ---------------------------------------------------------------------------
# AggregatedReport
# ---------------------------------------------------------------------------


def test_aggregated_report_estimated_pages():
    r = AggregatedReport(
        company_name="Acme",
        content="x",
        table_of_contents="",
        chapter_count=2,
        total_word_count=1500,
    )
    assert r.estimated_pages == 3


def test_aggregated_report_min_one_page():
    r = AggregatedReport(
        company_name="Acme",
        content="x",
        table_of_contents="",
        chapter_count=0,
        total_word_count=0,
    )
    assert r.estimated_pages == 1


def test_aggregated_report_to_markdown():
    r = AggregatedReport(
        company_name="Acme",
        content="# Report",
        table_of_contents="",
        chapter_count=1,
        total_word_count=10,
    )
    assert r.to_markdown() == "# Report"


# ---------------------------------------------------------------------------
# _build_header / _generate_toc / _clean_chapter_content
# ---------------------------------------------------------------------------


def test_build_header(aggregator):
    header = aggregator._build_header("Acme Corp", 5)
    assert "Acme Corp" in header
    assert "Chapters:** 5" in header


def test_generate_toc_skips_failed(aggregator):
    chapters = [
        ChapterResult(1, "Market & Trends", "c", success=True),
        ChapterResult(2, "Failed One", "", success=False),
    ]
    toc = aggregator._generate_toc(chapters, "Acme")
    assert "Market & Trends" in toc
    assert "Failed One" not in toc
    # anchor sanitized: "&" -> "and", spaces -> dashes
    assert "market-and-trends" in toc


def test_clean_chapter_content_adds_header(aggregator):
    ch = ChapterResult(3, "Strategy", "Plain body without header.", success=True)
    out = aggregator._clean_chapter_content(ch)
    assert out.startswith("## 3. Strategy")


def test_clean_chapter_content_rewrites_existing_header(aggregator):
    ch = ChapterResult(4, "Ops", "## Operations\n\nBody.", success=True)
    out = aggregator._clean_chapter_content(ch)
    assert out.startswith("## 4. Operations")


# ---------------------------------------------------------------------------
# _consolidate_citations
# ---------------------------------------------------------------------------


def test_consolidate_citations_dedupes(aggregator):
    chapters = [
        ChapterResult(
            1,
            "Ch1",
            "c",
            success=True,
            citations=[
                {"title": "A", "url": "https://a.example"},
                {"title": "Dup", "url": "https://a.example"},
                {"title": "NoUrl", "url": ""},
            ],
        ),
        ChapterResult(
            2,
            "Ch2",
            "c",
            success=True,
            citations=[{"title": "B", "url": "https://b.example"}],
        ),
    ]
    cites = aggregator._consolidate_citations(chapters)
    urls = [c["url"] for c in cites]
    assert urls == ["https://a.example", "https://b.example"]
    assert cites[0]["number"] == "1"
    assert cites[1]["number"] == "2"


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_with_missing_chapters(aggregator):
    chapters = [
        ChapterResult(1, "Overview", "## Overview\n\nGood content here.", success=True),
        ChapterResult(2, "Broken", "", success=False, error="timeout"),
    ]
    report = await aggregator.aggregate(chapters, "Acme")
    assert report.chapter_count == 1
    assert report.missing_chapters == ["Broken"]
    assert "could not be generated" in report.content
    assert "timeout" in report.content


@pytest.mark.asyncio
async def test_aggregate_smooth_transitions_success(aggregator):
    aggregator._mock_client.models.generate_content.return_value = SimpleNamespace(
        text="SMOOTHED DOC"
    )
    chapters = [
        ChapterResult(1, "A", "## A\n\nbody", success=True),
        ChapterResult(2, "B", "## B\n\nbody", success=True),
    ]
    report = await aggregator.aggregate(chapters, "Acme", smooth_transitions=True)
    assert report.content == "SMOOTHED DOC"


@pytest.mark.asyncio
async def test_aggregate_smooth_transitions_failure_falls_back(aggregator):
    aggregator._mock_client.models.generate_content.side_effect = RuntimeError("api down")
    chapters = [
        ChapterResult(1, "A", "## A\n\nbody", success=True),
        ChapterResult(2, "B", "## B\n\nbody", success=True),
    ]
    report = await aggregator.aggregate(chapters, "Acme", smooth_transitions=True)
    # On smoothing failure, the original content is kept.
    assert "## 1. A" in report.content


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------


def test_singleton_get_and_reset():
    reset_report_aggregator()
    with (
        patch("primr.ai.report_aggregator.genai.Client"),
        patch("primr.ai.report_aggregator.get_settings") as mock_get,
    ):
        mock_get.return_value.api.gemini_key = "test-key"
        a1 = get_report_aggregator()
        a2 = get_report_aggregator()
        assert a1 is a2
        reset_report_aggregator()
        a3 = get_report_aggregator()
        assert a3 is not a1
    reset_report_aggregator()
