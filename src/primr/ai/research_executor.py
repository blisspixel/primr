"""
Research Node Executor for Parallel Deep Research.

This module provides the ResearchNodeExecutor class that executes multiple
Deep Research tasks in parallel with rate limiting and error handling.

Each research node runs a single chapter of the comprehensive report,
with access to shared context via File Search Store.
"""

import asyncio
from dataclasses import dataclass, field
import time
from typing import Any

try:
    from google import genai as _google_genai

    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as import_error:
    _GENAI_IMPORT_ERROR = import_error

    class _GenAIUnavailable:
        class Client:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("google.genai is unavailable")

    _google_genai = _GenAIUnavailable()  # type: ignore[assignment]
    _FALLBACK_CLIENT_CLASS = _GenAIUnavailable.Client
else:
    _FALLBACK_CLIENT_CLASS = None  # type: ignore[misc]

genai = _google_genai

from primr.ai.report_architect import ChapterPlan
from primr.config.settings import get_settings
from primr.utils.logging_config import get_logger

logger = get_logger("ai.research_executor")


def _require_genai_dependency() -> None:
    if _GENAI_IMPORT_ERROR is None:
        return
    if (
        _FALLBACK_CLIENT_CLASS is not None
        and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS
    ):
        return
    raise RuntimeError(
        "google.genai is not available. Install compatible dependencies "
        "(Python 3.11+ and project requirements)."
    ) from _GENAI_IMPORT_ERROR


@dataclass
class ChapterResult:
    """Result from a single chapter research task."""

    chapter_number: int
    title: str
    content: str
    citations: list[dict[str, str]] = field(default_factory=list)
    duration_seconds: float = 0.0
    success: bool = True
    error: str | None = None
    interaction_id: str = ""

    @property
    def word_count(self) -> int:
        """Approximate word count of the content."""
        return len(self.content.split()) if self.content else 0


@dataclass
class ExecutionResult:
    """Result from executing all chapters."""

    company_name: str
    chapters: list[ChapterResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    successful_chapters: int = 0
    failed_chapters: int = 0

    @property
    def total_word_count(self) -> int:
        """Total word count across all chapters."""
        return sum(ch.word_count for ch in self.chapters if ch.success)

    @property
    def success_rate(self) -> float:
        """Percentage of chapters that completed successfully."""
        total = len(self.chapters)
        return (self.successful_chapters / total * 100) if total > 0 else 0.0


# Research node prompt template with hierarchy of truth
CHAPTER_PROMPT_TEMPLATE = """Task: Write a comprehensive, 2,000-word strategic chapter titled '{chapter_title}'.

Company: {company_name}

Instructions: {chapter_research_prompt}

HIERARCHY OF TRUTH:
1. COMPANY FACTS: Use the File Search Store for baseline company data.
   These are facts from the company's own website - highest authority.
2. EXTERNAL CONTEXT: Use Google Search for market conditions, competitive intel,
   industry trends, and news.
3. SYNTHESIS: Weave internal baseline + external context into cohesive narrative.

FORMATTING RULES:
- Write in full paragraphs, not bullet lists (unless bullets genuinely help clarity)
- Keep bullets single-level only if used, no nested sub-bullets
- No em-dashes or en-dashes, use commas or periods instead
- Include at least 2 Markdown data tables comparing key metrics where appropriate
- Cite every claim using inline citations [cite: N]
- Tone: Professional Strategic Advisory

EPISTEMIC STANDARDS:
- Clearly distinguish facts (with citation) from inferences (labeled as such)
- If data unavailable, state "Not publicly available" rather than estimating
- Frame strategic observations as hypotheses to validate, not conclusions
- Use language like "appears to", "based on available data", "worth exploring"

Output the chapter content in Markdown format. Start with the chapter title as an H2 header."""


class ResearchNodeExecutor:
    """
    Executes parallel Deep Research tasks with rate limiting.

    The executor manages concurrent research tasks, ensuring we don't
    exceed API rate limits while maximizing throughput.

    Example:
        executor = ResearchNodeExecutor(
            file_search_store="stores/abc123",
            max_concurrent=3
        )
        results = await executor.execute_all(chapters, "Acme Corp")
    """

    # Import centralized model config
    from primr.config.models import PrimrModels

    # Deep Research agent identifier - USE CENTRALIZED CONFIG
    AGENT_ID = PrimrModels.DEEP_RESEARCH_AGENT

    # Default concurrency limit (conservative to avoid rate limits)
    # Deep Research has strict quota limits - 2 concurrent is safer
    DEFAULT_MAX_CONCURRENT = 2

    # Polling configuration
    POLL_INTERVAL_FAST = 5.0  # First 60s
    POLL_INTERVAL_NORMAL = 10.0  # 60-300s
    POLL_INTERVAL_SLOW = 20.0  # 300s+

    # Timeout per chapter (15 minutes)
    CHAPTER_TIMEOUT = 15 * 60

    def __init__(
        self,
        file_search_store: str | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        api_key: str | None = None,
    ):
        """
        Initialize the Research Node Executor.

        Args:
            file_search_store: Name of the File Search Store with context
            max_concurrent: Maximum concurrent research tasks
            api_key: Optional API key override
        """
        _require_genai_dependency()
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        self._file_search_store = file_search_store
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

        logger.debug(
            f"Research executor initialized: "
            f"max_concurrent={max_concurrent}, store={file_search_store}"
        )

    async def execute_chapter(
        self,
        chapter: ChapterPlan,
        company_name: str,
        on_progress: Any | None = None,
    ) -> ChapterResult:
        """
        Execute Deep Research for a single chapter.

        Uses the semaphore to limit concurrent executions.

        Args:
            chapter: The chapter plan to execute
            company_name: Name of the company being researched
            on_progress: Optional callback for progress updates

        Returns:
            ChapterResult with content or error
        """
        async with self._semaphore:
            return await self._execute_chapter_internal(chapter, company_name, on_progress)

    async def _execute_chapter_internal(
        self,
        chapter: ChapterPlan,
        company_name: str,
        on_progress: Any | None = None,
    ) -> ChapterResult:
        """Internal chapter execution (already holding semaphore)."""
        start_time = time.time()
        chapter_id = f"Ch{chapter.chapter_number}"

        logger.info(f"[{chapter_id}] Starting: {chapter.title}")

        if on_progress:
            on_progress(f"[{chapter_id}] Starting: {chapter.title}")

        # Build the chapter prompt
        prompt = CHAPTER_PROMPT_TEMPLATE.format(
            chapter_title=chapter.title,
            company_name=company_name,
            chapter_research_prompt=chapter.research_prompt,
        )

        # Retry configuration for quota errors
        max_retries = 3
        base_delay = 60.0  # Start with 60s delay for quota errors

        for attempt in range(max_retries):
            try:
                # Start the research task
                interaction = self._start_research(prompt)
                interaction_id = interaction.id

                logger.info(f"[{chapter_id}] Research started: {interaction_id}")

                # Poll for completion
                while True:
                    elapsed = time.time() - start_time

                    if elapsed > self.CHAPTER_TIMEOUT:
                        logger.warning(f"[{chapter_id}] Timed out after {elapsed:.0f}s")
                        return ChapterResult(
                            chapter_number=chapter.chapter_number,
                            title=chapter.title,
                            content="",
                            duration_seconds=elapsed,
                            success=False,
                            error=f"Timed out after {elapsed:.0f}s",
                            interaction_id=interaction_id,
                        )

                    # Check status
                    interaction = self._get_interaction(interaction_id)
                    status = interaction.status

                    if status == "completed":
                        content = self._extract_content(interaction)
                        citations = self._extract_citations(interaction)
                        duration = time.time() - start_time

                        logger.info(
                            f"[{chapter_id}] Completed in {duration:.0f}s, "
                            f"{len(content.split())} words"
                        )

                        if on_progress:
                            on_progress(f"[{chapter_id}] Completed: {chapter.title}")

                        return ChapterResult(
                            chapter_number=chapter.chapter_number,
                            title=chapter.title,
                            content=content,
                            citations=citations,
                            duration_seconds=duration,
                            success=True,
                            interaction_id=interaction_id,
                        )

                    elif status == "failed":
                        error_msg = getattr(interaction, "error", "Unknown error")
                        duration = time.time() - start_time

                        logger.error(f"[{chapter_id}] Failed: {error_msg}")

                        return ChapterResult(
                            chapter_number=chapter.chapter_number,
                            title=chapter.title,
                            content="",
                            duration_seconds=duration,
                            success=False,
                            error=str(error_msg),
                            interaction_id=interaction_id,
                        )

                    # Still in progress - adaptive polling
                    poll_interval = self._get_poll_interval(elapsed)
                    await asyncio.sleep(poll_interval)

            except Exception as e:
                error_str = str(e)
                is_quota_error = (
                    "429" in error_str
                    or "quota" in error_str.lower()
                    or "too_many_requests" in error_str.lower()
                )

                if is_quota_error and attempt < max_retries - 1:
                    # Exponential backoff for quota errors
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"[{chapter_id}] Quota limit hit, waiting {delay:.0f}s before retry "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    if on_progress:
                        on_progress(f"[{chapter_id}] Rate limited, waiting {int(delay)}s...")
                    await asyncio.sleep(delay)
                    continue

                # Non-quota error or final attempt
                duration = time.time() - start_time
                logger.error(f"[{chapter_id}] Error: {e}")

                return ChapterResult(
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    content="",
                    duration_seconds=duration,
                    success=False,
                    error=error_str,
                )

        # Should not reach here, but just in case
        return ChapterResult(
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            content="",
            duration_seconds=time.time() - start_time,
            success=False,
            error="Max retries exceeded",
        )

    async def execute_all(
        self,
        chapters: list[ChapterPlan],
        company_name: str,
        on_progress: Any | None = None,
    ) -> ExecutionResult:
        """
        Execute all chapters in parallel (with concurrency limit).

        Args:
            chapters: List of chapter plans to execute
            company_name: Name of the company being researched
            on_progress: Optional callback for progress updates

        Returns:
            ExecutionResult with all chapter results
        """
        start_time = time.time()

        logger.info(
            f"Executing {len(chapters)} chapters for {company_name} "
            f"(max {self._max_concurrent} concurrent)"
        )

        if on_progress:
            on_progress(
                f"Starting parallel research: {len(chapters)} chapters, "
                f"{self._max_concurrent} concurrent"
            )

        # Create tasks for all chapters
        tasks = [self.execute_chapter(chapter, company_name, on_progress) for chapter in chapters]

        # Execute all tasks (semaphore limits concurrency)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        chapter_results: list[ChapterResult] = []
        successful = 0
        failed = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Task raised an exception
                chapter = chapters[i]
                chapter_results.append(
                    ChapterResult(
                        chapter_number=chapter.chapter_number,
                        title=chapter.title,
                        content="",
                        success=False,
                        error=str(result),
                    )
                )
                failed += 1
            elif isinstance(result, ChapterResult):
                chapter_results.append(result)
                if result.success:
                    successful += 1
                else:
                    failed += 1

        # Sort by chapter number
        chapter_results.sort(key=lambda x: x.chapter_number)

        total_duration = time.time() - start_time

        logger.info(
            f"Execution complete: {successful}/{len(chapters)} successful, "
            f"{total_duration:.0f}s total"
        )

        return ExecutionResult(
            company_name=company_name,
            chapters=chapter_results,
            total_duration_seconds=total_duration,
            successful_chapters=successful,
            failed_chapters=failed,
        )

    def _start_research(self, prompt: str) -> Any:
        """Start a background research task."""
        tools: list[dict[str, Any]] = []

        # Add file search if store is configured
        if self._file_search_store:
            tools.append(
                {"type": "file_search", "file_search_store_names": [self._file_search_store]}
            )

        create_kwargs: dict[str, Any] = {
            "input": prompt,
            "agent": self.AGENT_ID,
            "background": True,
            "store": True,  # Required for background interactions
        }

        if tools:
            create_kwargs["tools"] = tools

        return self._client.interactions.create(**create_kwargs)

    def _get_interaction(self, interaction_id: str) -> Any:
        """Get the current state of an interaction."""
        return self._client.interactions.get(interaction_id)

    def _extract_content(self, interaction: Any) -> str:
        """Extract the text content from a completed interaction."""
        if hasattr(interaction, "outputs") and interaction.outputs:
            parts = [output.text for output in interaction.outputs if getattr(output, "text", None)]
            return "\n\n".join(parts) if parts else ""
        return ""

    def _extract_citations(self, interaction: Any) -> list[dict[str, str]]:
        """Extract citations from a completed interaction."""
        import re

        citations: list[dict[str, str]] = []

        content = self._extract_content(interaction)
        if not content:
            return citations

        # Look for Sources section
        sources_match = re.search(r"\*\*Sources:\*\*\s*([\s\S]*?)$", content)
        if sources_match:
            sources_text = sources_match.group(1)
            citation_pattern = r"(\d+)\.\s*\[([^\]]+)\]\(([^)]+)\)"
            for match in re.finditer(citation_pattern, sources_text):
                citations.append(
                    {"number": match.group(1), "title": match.group(2), "url": match.group(3)}
                )

        # Count inline citations if no sources section
        if not citations:
            inline_pattern = r"\[cite:\s*([\d,\s]+)\]"
            all_nums = set()
            for match in re.finditer(inline_pattern, content):
                nums = [n.strip() for n in match.group(1).split(",")]
                all_nums.update(nums)
            for num in sorted(all_nums, key=lambda x: int(x) if x.isdigit() else 0):
                citations.append({"number": num, "title": f"Source {num}", "url": ""})

        return citations

    def _get_poll_interval(self, elapsed_seconds: float) -> float:
        """Get adaptive polling interval based on elapsed time."""
        if elapsed_seconds < 60:
            return self.POLL_INTERVAL_FAST
        elif elapsed_seconds < 300:
            return self.POLL_INTERVAL_NORMAL
        else:
            return self.POLL_INTERVAL_SLOW


# =============================================================================
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

import threading

_executor: ResearchNodeExecutor | None = None
_executor_lock = threading.Lock()


def get_research_executor(
    file_search_store: str | None = None,
    max_concurrent: int = ResearchNodeExecutor.DEFAULT_MAX_CONCURRENT,
) -> ResearchNodeExecutor:
    """
    Get a Research Node Executor instance.

    Note: Unlike other singletons, this creates a new instance if
    the file_search_store differs, since each research run may use
    a different store.
    """
    global _executor

    with _executor_lock:
        if _executor is None or _executor._file_search_store != file_search_store:
            _executor = ResearchNodeExecutor(
                file_search_store=file_search_store,
                max_concurrent=max_concurrent,
            )

    return _executor


def reset_research_executor() -> None:
    """Reset the global executor (useful for testing)."""
    global _executor
    with _executor_lock:
        _executor = None
