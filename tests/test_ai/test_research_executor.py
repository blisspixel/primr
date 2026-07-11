"""
Tests for the ResearchNodeExecutor component.

Tests parallel execution, rate limiting, and error handling.
"""

import asyncio
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from primr.ai.report_architect import ChapterPlan
from primr.ai.research_executor import (
    CHAPTER_PROMPT_TEMPLATE,
    ChapterResult,
    ExecutionResult,
    ResearchNodeExecutor,
    get_research_executor,
    reset_research_executor,
)


@pytest.fixture(autouse=True)
def _stub_genai_client() -> Iterator[None]:
    """Avoid constructing a real SDK client in every Hypothesis example."""
    with patch("primr.ai.research_executor.genai.Client"):
        yield


class TestChapterResult:
    """Tests for ChapterResult dataclass."""

    def test_successful_result(self) -> None:
        """Test successful chapter result."""
        result = ChapterResult(
            chapter_number=1,
            title="Test Chapter",
            content="This is test content with many words.",
            success=True,
            duration_seconds=120.0,
        )
        assert result.success
        assert result.word_count > 0
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test failed chapter result."""
        result = ChapterResult(
            chapter_number=2, title="Failed Chapter", content="", success=False, error="API Error"
        )
        assert not result.success
        assert result.word_count == 0
        assert result.error == "API Error"

    def test_word_count_calculation(self) -> None:
        """Test word count calculation."""
        result = ChapterResult(
            chapter_number=1, title="Test", content="one two three four five", success=True
        )
        assert result.word_count == 5


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_total_word_count(self) -> None:
        """Test total word count across chapters."""
        chapters = [
            ChapterResult(1, "Ch1", "one two three", success=True),
            ChapterResult(2, "Ch2", "four five", success=True),
            ChapterResult(3, "Ch3", "", success=False, error="Failed"),
        ]
        result = ExecutionResult(
            company_name="Test", chapters=chapters, successful_chapters=2, failed_chapters=1
        )
        assert result.total_word_count == 5  # Only successful chapters

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        chapters = [
            ChapterResult(1, "Ch1", "content", success=True),
            ChapterResult(2, "Ch2", "content", success=True),
            ChapterResult(3, "Ch3", "", success=False),
        ]
        result = ExecutionResult(
            company_name="Test", chapters=chapters, successful_chapters=2, failed_chapters=1
        )
        assert result.success_rate == pytest.approx(66.67, rel=0.1)

    def test_success_rate_zero_chapters(self) -> None:
        """Test success rate with no chapters."""
        result = ExecutionResult(
            company_name="Test", chapters=[], successful_chapters=0, failed_chapters=0
        )
        assert result.success_rate == 0.0


class TestChapterPromptTemplate:
    """Tests for the chapter prompt template."""

    def test_template_has_placeholders(self) -> None:
        """Test that template has required placeholders."""
        assert "{chapter_title}" in CHAPTER_PROMPT_TEMPLATE
        assert "{company_name}" in CHAPTER_PROMPT_TEMPLATE
        assert "{chapter_research_prompt}" in CHAPTER_PROMPT_TEMPLATE

    def test_template_mentions_hierarchy_of_truth(self) -> None:
        """Test that template includes hierarchy of truth."""
        assert "HIERARCHY OF TRUTH" in CHAPTER_PROMPT_TEMPLATE
        assert "File Search" in CHAPTER_PROMPT_TEMPLATE
        assert "Google Search" in CHAPTER_PROMPT_TEMPLATE


class TestResearchNodeExecutor:
    """Tests for ResearchNodeExecutor class."""

    @pytest.fixture
    def executor(self) -> ResearchNodeExecutor:
        """Create a ResearchNodeExecutor instance."""
        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            return ResearchNodeExecutor(file_search_store="test-store", max_concurrent=3)

    def test_initialization(self, executor: ResearchNodeExecutor) -> None:
        """Test executor initialization."""
        assert executor._file_search_store == "test-store"
        assert executor._max_concurrent == 3
        assert executor.AGENT_ID == "deep-research-preview-04-2026"

    def test_initialization_without_store(self) -> None:
        """Test executor initialization without file search store."""
        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor = ResearchNodeExecutor(max_concurrent=2)

        assert executor._file_search_store is None
        assert executor._max_concurrent == 2

    def test_get_poll_interval_fast(self, executor: ResearchNodeExecutor) -> None:
        """Test fast polling interval."""
        assert executor._get_poll_interval(30) == 5.0

    def test_get_poll_interval_normal(self, executor: ResearchNodeExecutor) -> None:
        """Test normal polling interval."""
        assert executor._get_poll_interval(120) == 10.0

    def test_get_poll_interval_slow(self, executor: ResearchNodeExecutor) -> None:
        """Test slow polling interval."""
        assert executor._get_poll_interval(400) == 20.0


class TestSingletonAccess:
    """Tests for singleton access functions."""

    def test_get_research_executor_returns_instance(self) -> None:
        """Test that get_research_executor returns an instance."""
        reset_research_executor()

        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor = get_research_executor("test-store")

        assert isinstance(executor, ResearchNodeExecutor)

    def test_get_research_executor_different_store_creates_new(self) -> None:
        """Test that different store creates new executor."""
        reset_research_executor()

        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor1 = get_research_executor("store1")
            executor2 = get_research_executor("store2")

        # Different stores should create different executors
        assert executor1._file_search_store != executor2._file_search_store

    def test_reset_research_executor(self) -> None:
        """Test that reset_research_executor clears the singleton."""
        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor1 = get_research_executor("store1")
            reset_research_executor()
            executor2 = get_research_executor("store1")

        assert executor1 is not executor2


# Property-based tests using Hypothesis
from hypothesis import given, settings
from hypothesis import strategies as st


class TestRateLimitingProperty:
    """Property tests for rate limiting (Property 2)."""

    @given(
        max_concurrent=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20)
    def test_semaphore_initialized_correctly(self, max_concurrent: int) -> None:
        """
        Property 2: Parallel Execution with Rate Limiting

        For any max_concurrent value, the semaphore SHALL be initialized correctly.
        """
        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor = ResearchNodeExecutor(max_concurrent=max_concurrent)

        # Semaphore should allow max_concurrent acquisitions
        assert executor._max_concurrent == max_concurrent


class TestSharedContextProperty:
    """Property tests for shared context access (Property 3)."""

    @given(
        store_name=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=20)
    def test_file_search_store_preserved(self, store_name: str) -> None:
        """
        Property 3: Shared Context Access

        For any store name, the executor SHALL preserve the store reference.
        """
        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor = ResearchNodeExecutor(file_search_store=store_name.strip())

        assert executor._file_search_store == store_name.strip()


class TestConcurrencyProperty:
    """Property tests for concurrency limiting."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_tasks(self) -> None:
        """
        Property 2: Parallel Execution with Rate Limiting

        The system SHALL limit concurrent tasks to max_concurrent.
        """
        max_concurrent = 3
        concurrent_count = 0
        max_observed = 0

        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor = ResearchNodeExecutor(max_concurrent=max_concurrent)

        async def mock_execute(chapter: ChapterPlan, company: str, progress: None) -> ChapterResult:
            nonlocal concurrent_count, max_observed
            concurrent_count += 1
            max_observed = max(max_observed, concurrent_count)
            await asyncio.sleep(0.1)  # Simulate work
            concurrent_count -= 1
            return ChapterResult(
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                content="Test content",
                success=True,
            )

        # Patch the internal execute method
        executor._execute_chapter_internal = mock_execute

        # Create 10 chapters
        chapters = [ChapterPlan(i, f"Chapter {i}", f"Prompt {i}") for i in range(1, 11)]

        await executor.execute_all(chapters, "TestCorp", None)

        # Max concurrent should not exceed limit
        assert max_observed <= max_concurrent


class TestGracefulFailureProperty:
    """Property tests for graceful failure handling (Property 6)."""

    @pytest.mark.asyncio
    async def test_continues_after_chapter_failure(self) -> None:
        """
        Property 6: Graceful Failure Handling

        When a chapter task fails, the system SHALL continue with other chapters.
        """
        with patch("primr.ai.research_executor.get_settings") as mock_settings:
            mock_settings.return_value.api.gemini_key = "test-key"
            executor = ResearchNodeExecutor(max_concurrent=3)

        call_count = 0

        async def mock_execute(chapter: ChapterPlan, company: str, progress: None) -> ChapterResult:
            nonlocal call_count
            call_count += 1

            # Fail chapter 2
            if chapter.chapter_number == 2:
                return ChapterResult(
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    content="",
                    success=False,
                    error="Simulated failure",
                )

            return ChapterResult(
                chapter_number=chapter.chapter_number,
                title=chapter.title,
                content="Test content",
                success=True,
            )

        executor._execute_chapter_internal = mock_execute

        chapters = [ChapterPlan(i, f"Chapter {i}", f"Prompt {i}") for i in range(1, 6)]

        result = await executor.execute_all(chapters, "TestCorp", None)

        # All chapters should be attempted
        assert call_count == 5

        # Should have 4 successful and 1 failed
        assert result.successful_chapters == 4
        assert result.failed_chapters == 1
