"""
Tests for the ReportAggregator component.

Tests chapter aggregation, TOC generation, and document formatting.
"""

from collections.abc import Iterator
from unittest.mock import patch

import pytest

from primr.ai.report_aggregator import (
    AggregatedReport,
    ReportAggregator,
    get_report_aggregator,
    reset_report_aggregator,
)
from primr.ai.research_executor import ChapterResult


@pytest.fixture(autouse=True)
def _stub_genai_client() -> Iterator[None]:
    """Avoid constructing a real SDK client in every Hypothesis example."""
    with patch("primr.ai.report_aggregator.genai.Client"):
        yield


class TestAggregatedReport:
    """Tests for AggregatedReport dataclass."""

    def test_estimated_pages(self) -> None:
        """Test page estimation."""
        report = AggregatedReport(
            company_name="Test",
            content="word " * 2500,  # 2500 words
            table_of_contents="TOC",
            chapter_count=5,
            total_word_count=2500,
        )
        assert report.estimated_pages == 5  # 2500 / 500

    def test_estimated_pages_minimum(self) -> None:
        """Test minimum page estimation."""
        report = AggregatedReport(
            company_name="Test",
            content="short",
            table_of_contents="TOC",
            chapter_count=1,
            total_word_count=10,
        )
        assert report.estimated_pages == 1  # Minimum 1 page

    def test_to_markdown(self) -> None:
        """Test markdown output."""
        report = AggregatedReport(
            company_name="Test",
            content="# Report Content",
            table_of_contents="## TOC",
            chapter_count=1,
            total_word_count=100,
        )
        assert report.to_markdown() == "# Report Content"


class TestReportAggregator:
    """Tests for ReportAggregator class."""

    @pytest.fixture
    def aggregator(self) -> ReportAggregator:
        """Create a ReportAggregator instance."""
        with patch("primr.ai.report_aggregator.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            return ReportAggregator()

    def test_initialization(self, aggregator: ReportAggregator) -> None:
        """Test aggregator initialization."""
        assert aggregator.SMOOTHING_MODEL == "gemini-3-flash-preview"

    def test_build_header(self, aggregator: ReportAggregator) -> None:
        """Test header generation."""
        header = aggregator._build_header("TestCorp", 10)

        assert "TestCorp" in header
        assert "10" in header
        assert "Hierarchy of Truth" in header

    def test_generate_toc(self, aggregator: ReportAggregator) -> None:
        """Test table of contents generation - clean format without status markers."""
        chapters = [
            ChapterResult(1, "Executive Summary", "content", success=True),
            ChapterResult(2, "Products", "content", success=True),
            ChapterResult(3, "Failed Chapter", "", success=False, error="Error"),
        ]

        toc = aggregator._generate_toc(chapters, "TestCorp")

        assert "Table of Contents" in toc
        assert "Executive Summary" in toc
        assert "Products" in toc
        # Failed chapters should NOT appear in TOC (clean format)
        assert "Failed Chapter" not in toc
        # No status markers in clean TOC
        assert "✓" not in toc
        assert "✗" not in toc

    def test_clean_chapter_content_adds_header(self, aggregator: ReportAggregator) -> None:
        """Test that clean_chapter_content adds header if missing."""
        chapter = ChapterResult(
            chapter_number=1,
            title="Test Chapter",
            content="Just some content without header",
            success=True,
        )

        cleaned = aggregator._clean_chapter_content(chapter)

        assert cleaned.startswith("## 1. Test Chapter")

    def test_clean_chapter_content_updates_existing_header(
        self, aggregator: ReportAggregator
    ) -> None:
        """Test that clean_chapter_content updates existing header."""
        chapter = ChapterResult(
            chapter_number=3,
            title="Test Chapter",
            content="## Test Chapter\n\nContent here",
            success=True,
        )

        cleaned = aggregator._clean_chapter_content(chapter)

        assert "## 3. Test Chapter" in cleaned

    def test_consolidate_citations(self, aggregator: ReportAggregator) -> None:
        """Test citation consolidation."""
        chapters = [
            ChapterResult(
                1,
                "Ch1",
                "content",
                citations=[
                    {"number": "1", "title": "Source 1", "url": "http://a.com"},
                    {"number": "2", "title": "Source 2", "url": "http://b.com"},
                ],
                success=True,
            ),
            ChapterResult(
                2,
                "Ch2",
                "content",
                citations=[
                    {"number": "1", "title": "Source 1", "url": "http://a.com"},  # Duplicate
                    {"number": "2", "title": "Source 3", "url": "http://c.com"},
                ],
                success=True,
            ),
        ]

        citations = aggregator._consolidate_citations(chapters)

        # Should deduplicate by URL
        assert len(citations) == 3
        urls = [c["url"] for c in citations]
        assert "http://a.com" in urls
        assert "http://b.com" in urls
        assert "http://c.com" in urls

    @pytest.mark.asyncio
    async def test_aggregate_successful_chapters(self, aggregator: ReportAggregator) -> None:
        """Test aggregating successful chapters."""
        chapters = [
            ChapterResult(
                1, "Executive Summary", "## Executive Summary\n\nThis is the summary.", success=True
            ),
            ChapterResult(2, "Products", "## Products\n\nProduct details here.", success=True),
        ]

        report = await aggregator.aggregate(chapters, "TestCorp")

        assert report.company_name == "TestCorp"
        assert report.chapter_count == 2
        assert "Executive Summary" in report.content
        assert "Products" in report.content
        assert len(report.missing_chapters) == 0

    @pytest.mark.asyncio
    async def test_aggregate_with_failed_chapters(self, aggregator: ReportAggregator) -> None:
        """Test aggregating with some failed chapters."""
        chapters = [
            ChapterResult(
                1, "Executive Summary", "## Executive Summary\n\nThis is the summary.", success=True
            ),
            ChapterResult(2, "Failed Chapter", "", success=False, error="API Error"),
        ]

        report = await aggregator.aggregate(chapters, "TestCorp")

        assert report.chapter_count == 1
        assert len(report.missing_chapters) == 1
        assert "Failed Chapter" in report.missing_chapters
        assert "could not be generated" in report.content

    @pytest.mark.asyncio
    async def test_aggregate_orders_chapters(self, aggregator: ReportAggregator) -> None:
        """Test that chapters are ordered by number."""
        chapters = [
            ChapterResult(3, "Chapter 3", "Content 3", success=True),
            ChapterResult(1, "Chapter 1", "Content 1", success=True),
            ChapterResult(2, "Chapter 2", "Content 2", success=True),
        ]

        report = await aggregator.aggregate(chapters, "TestCorp")

        # Check order in content
        pos1 = report.content.find("Chapter 1")
        pos2 = report.content.find("Chapter 2")
        pos3 = report.content.find("Chapter 3")

        assert pos1 < pos2 < pos3


class TestSingletonAccess:
    """Tests for singleton access functions."""

    def test_get_report_aggregator_returns_instance(self) -> None:
        """Test that get_report_aggregator returns an instance."""
        reset_report_aggregator()

        with patch("primr.ai.report_aggregator.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            aggregator = get_report_aggregator()

        assert isinstance(aggregator, ReportAggregator)

    def test_get_report_aggregator_returns_same_instance(self) -> None:
        """Test that get_report_aggregator returns the same instance."""
        reset_report_aggregator()

        with patch("primr.ai.report_aggregator.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            aggregator1 = get_report_aggregator()
            aggregator2 = get_report_aggregator()

        assert aggregator1 is aggregator2

    def test_reset_report_aggregator(self) -> None:
        """Test that reset_report_aggregator clears the singleton."""
        with patch("primr.ai.report_aggregator.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            aggregator1 = get_report_aggregator()
            reset_report_aggregator()
            aggregator2 = get_report_aggregator()

        assert aggregator1 is not aggregator2


# Property-based tests using Hypothesis
from hypothesis import given, settings
from hypothesis import strategies as st


class TestAggregationProperty:
    """Property tests for aggregation (Property 5)."""

    @pytest.mark.asyncio
    @given(
        chapter_count=st.integers(min_value=1, max_value=15),
    )
    @settings(max_examples=20, deadline=None)
    async def test_aggregation_produces_single_document(self, chapter_count: int) -> None:
        """
        Property 5: Aggregation Produces Single Document

        For any number of chapters, aggregation SHALL produce a single document.
        """
        with patch("primr.ai.report_aggregator.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            aggregator = ReportAggregator()

        chapters = [
            ChapterResult(
                chapter_number=i,
                title=f"Chapter {i}",
                content=f"## Chapter {i}\n\nContent for chapter {i}.",
                success=True,
            )
            for i in range(1, chapter_count + 1)
        ]

        report = await aggregator.aggregate(chapters, "TestCorp")

        # Should produce a single document
        assert isinstance(report.content, str)
        assert len(report.content) > 0

        # Should contain all chapters
        assert report.chapter_count == chapter_count

    @pytest.mark.asyncio
    async def test_aggregation_includes_all_successful_chapters(self) -> None:
        """
        Property 5: Aggregation Produces Single Document

        The final document SHALL contain all successful chapters.
        """
        with patch("primr.ai.report_aggregator.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            aggregator = ReportAggregator()

        chapters = [
            ChapterResult(1, "Alpha", "## Alpha\n\nAlpha content.", success=True),
            ChapterResult(2, "Beta", "## Beta\n\nBeta content.", success=True),
            ChapterResult(3, "Gamma", "", success=False, error="Failed"),
            ChapterResult(4, "Delta", "## Delta\n\nDelta content.", success=True),
        ]

        report = await aggregator.aggregate(chapters, "TestCorp")

        # All successful chapters should be in content
        assert "Alpha content" in report.content
        assert "Beta content" in report.content
        assert "Delta content" in report.content

        # Failed chapter should be noted
        assert "Gamma" in report.content
        assert "could not be generated" in report.content


class TestChapterCompletenessProperty:
    """Property tests for chapter completeness (Property 4)."""

    def test_word_count_tracked_correctly(self) -> None:
        """
        Property 4: Chapter Completeness

        Word count SHALL be tracked correctly for each chapter.
        """
        # Create chapters with known word counts
        chapters = [
            ChapterResult(
                1,
                "Ch1",
                "one two three four five",  # 5 words
                success=True,
            ),
            ChapterResult(
                2,
                "Ch2",
                "six seven eight nine ten eleven twelve",  # 7 words
                success=True,
            ),
        ]

        total = sum(ch.word_count for ch in chapters if ch.success)
        assert total == 12
