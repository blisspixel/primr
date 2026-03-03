"""
Tests for the MasterArchitect component.

Tests chapter plan generation and validation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.report_architect import (
    DEFAULT_CHAPTERS,
    ChapterPlan,
    MasterArchitect,
    ReportPlan,
    get_master_architect,
    reset_master_architect,
)


class TestChapterPlan:
    """Tests for ChapterPlan dataclass."""

    def test_default_values(self) -> None:
        """Test ChapterPlan default values."""
        plan = ChapterPlan(
            chapter_number=1,
            title="Test Chapter",
            research_prompt="Test prompt"
        )
        assert plan.chapter_number == 1
        assert plan.title == "Test Chapter"
        assert plan.research_prompt == "Test prompt"
        assert plan.expected_pages == 5  # default

    def test_to_dict(self) -> None:
        """Test ChapterPlan serialization."""
        plan = ChapterPlan(
            chapter_number=2,
            title="Products",
            research_prompt="Research products",
            expected_pages=6
        )
        result = plan.to_dict()
        assert result["chapter_number"] == 2
        assert result["title"] == "Products"
        assert result["research_prompt"] == "Research products"
        assert result["expected_pages"] == 6


class TestReportPlan:
    """Tests for ReportPlan dataclass."""

    def test_total_expected_pages(self) -> None:
        """Test total page calculation."""
        chapters = [
            ChapterPlan(1, "Ch1", "Prompt1", expected_pages=5),
            ChapterPlan(2, "Ch2", "Prompt2", expected_pages=6),
            ChapterPlan(3, "Ch3", "Prompt3", expected_pages=4),
        ]
        plan = ReportPlan(company_name="Test", chapters=chapters)
        assert plan.total_expected_pages == 15

    def test_to_dict(self) -> None:
        """Test ReportPlan serialization."""
        chapters = [
            ChapterPlan(1, "Ch1", "Prompt1"),
        ]
        plan = ReportPlan(company_name="TestCo", chapters=chapters)
        result = plan.to_dict()
        assert result["company_name"] == "TestCo"
        assert len(result["chapters"]) == 1
        assert result["total_expected_pages"] == 5


class TestDefaultChapters:
    """Tests for default chapter structure."""

    def test_default_chapters_count(self) -> None:
        """Test that we have 10 default chapters."""
        assert len(DEFAULT_CHAPTERS) == 10

    def test_default_chapters_have_required_fields(self) -> None:
        """Test that all default chapters have title and research_prompt."""
        for chapter in DEFAULT_CHAPTERS:
            assert "title" in chapter
            assert "research_prompt" in chapter
            assert len(chapter["title"]) > 0
            assert len(chapter["research_prompt"]) > 0

    def test_default_chapters_cover_key_topics(self) -> None:
        """Test that default chapters cover essential topics."""
        titles = [ch["title"].lower() for ch in DEFAULT_CHAPTERS]

        # Check for key topics
        assert any("executive" in t for t in titles)
        assert any("product" in t for t in titles)
        assert any("leadership" in t or "culture" in t for t in titles)
        assert any("financial" in t for t in titles)
        assert any("competitive" in t for t in titles)
        assert any("swot" in t for t in titles)
        assert any("risk" in t for t in titles)


class TestMasterArchitect:
    """Tests for MasterArchitect class."""

    @pytest.fixture
    def architect(self) -> MasterArchitect:
        """Create a MasterArchitect instance."""
        with patch("primr.ai.report_architect.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            return MasterArchitect()

    def test_initialization(self, architect: MasterArchitect) -> None:
        """Test MasterArchitect initialization."""
        assert architect.PLANNING_MODEL == "gemini-3-flash-preview"

    def test_get_chapter_titles(self, architect: MasterArchitect) -> None:
        """Test getting default chapter titles."""
        titles = architect.get_chapter_titles()
        assert len(titles) == 10
        assert all(isinstance(t, str) for t in titles)

    def test_get_default_chapters(self, architect: MasterArchitect) -> None:
        """Test getting default chapters with company name substitution."""
        chapters = architect._get_default_chapters("TestCorp")

        assert len(chapters) == 10
        for ch in chapters:
            assert isinstance(ch, ChapterPlan)
            assert "TestCorp" in ch.research_prompt

    def test_get_default_plan(self, architect: MasterArchitect) -> None:
        """Test getting default plan."""
        plan = architect._get_default_plan("TestCorp")

        assert plan.company_name == "TestCorp"
        assert len(plan.chapters) == 10
        assert plan.total_expected_pages == 50  # 10 chapters * 5 pages

    @pytest.mark.asyncio
    async def test_generate_chapter_plan_uses_defaults_on_error(
        self, architect: MasterArchitect
    ) -> None:
        """Test that generate_chapter_plan falls back to defaults on error."""
        # Mock the client to raise an error
        architect._client = MagicMock()
        architect._client.models.generate_content.side_effect = Exception("API Error")

        plan = await architect.generate_chapter_plan("TestCorp", "Some context")

        # Should fall back to defaults
        assert plan.company_name == "TestCorp"
        assert len(plan.chapters) == 10

    @pytest.mark.asyncio
    async def test_generate_chapter_plan_parses_valid_json(
        self, architect: MasterArchitect
    ) -> None:
        """Test that generate_chapter_plan parses valid JSON response."""
        # Mock valid JSON response
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "chapters": [
                {
                    "chapter_number": i,
                    "title": f"Chapter {i}",
                    "research_prompt": f"Research prompt {i}",
                    "expected_pages": 5
                }
                for i in range(1, 11)
            ]
        })

        architect._client = MagicMock()
        architect._client.models.generate_content.return_value = mock_response

        plan = await architect.generate_chapter_plan("TestCorp", "Some context")

        assert plan.company_name == "TestCorp"
        assert len(plan.chapters) == 10
        assert plan.chapters[0].title == "Chapter 1"

    def test_parse_chapter_response_invalid_json(
        self, architect: MasterArchitect
    ) -> None:
        """Test parsing invalid JSON falls back to defaults."""
        chapters = architect._parse_chapter_response("not valid json", "TestCorp")

        assert len(chapters) == 10  # Falls back to defaults

    def test_parse_chapter_response_too_few_chapters(
        self, architect: MasterArchitect
    ) -> None:
        """Test parsing response with too few chapters falls back to defaults."""
        response = json.dumps({
            "chapters": [
                {"chapter_number": 1, "title": "Ch1", "research_prompt": "P1"}
            ]
        })

        chapters = architect._parse_chapter_response(response, "TestCorp")

        assert len(chapters) == 10  # Falls back to defaults


class TestSingletonAccess:
    """Tests for singleton access functions."""

    def test_get_master_architect_returns_instance(self) -> None:
        """Test that get_master_architect returns an instance."""
        reset_master_architect()

        with patch("primr.ai.report_architect.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            architect = get_master_architect()

        assert isinstance(architect, MasterArchitect)

    def test_get_master_architect_returns_same_instance(self) -> None:
        """Test that get_master_architect returns the same instance."""
        reset_master_architect()

        with patch("primr.ai.report_architect.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            architect1 = get_master_architect()
            architect2 = get_master_architect()

        assert architect1 is architect2

    def test_reset_master_architect(self) -> None:
        """Test that reset_master_architect clears the singleton."""
        with patch("primr.ai.report_architect.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            architect1 = get_master_architect()
            reset_master_architect()
            architect2 = get_master_architect()

        assert architect1 is not architect2


# Property-based tests using Hypothesis
from hypothesis import given, settings
from hypothesis import strategies as st


class TestChapterDecompositionProperty:
    """Property tests for chapter decomposition (Property 1)."""

    @given(
        company_name=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(max_examples=50)
    def test_default_plan_always_has_8_to_10_chapters(
        self, company_name: str
    ) -> None:
        """
        Property 1: Chapter Decomposition
        
        For any company name, the default plan SHALL produce 8-10 chapters.
        """
        with patch("primr.ai.report_architect.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            architect = MasterArchitect()

        plan = architect._get_default_plan(company_name.strip())

        assert 8 <= len(plan.chapters) <= 10

    @given(
        company_name=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(max_examples=50)
    def test_all_chapters_have_required_fields(
        self, company_name: str
    ) -> None:
        """
        Property 1: Chapter Decomposition
        
        For any company name, all chapters SHALL have title and research_prompt.
        """
        with patch("primr.ai.report_architect.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            architect = MasterArchitect()

        plan = architect._get_default_plan(company_name.strip())

        for chapter in plan.chapters:
            assert chapter.title, "Chapter must have a title"
            assert chapter.research_prompt, "Chapter must have a research_prompt"
            assert chapter.chapter_number > 0, "Chapter number must be positive"
