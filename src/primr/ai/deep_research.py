"""
Gemini Deep Research Agent client.

This module provides integration with Google's Deep Research Agent,
which autonomously plans, executes, and synthesizes multi-step research tasks.

The Deep Research Agent:
- Plans research strategy automatically
- Searches the web using Google Search
- Reads and analyzes web pages
- Synthesizes findings into structured reports
- Provides citations for all claims

Usage:
    client = DeepResearchClient()
    result = await client.research("Research Acme Corp's competitive position")

    # Or with streaming progress
    async for update in client.research_stream("Research Acme Corp"):
        print(update)
"""

import asyncio
import re
import threading
import time
import warnings
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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

    _google_genai = _GenAIUnavailable()
    _FALLBACK_CLIENT_CLASS = _GenAIUnavailable.Client
else:
    _FALLBACK_CLIENT_CLASS = None

genai = _google_genai

# Suppress the experimental API warning from the Genai SDK
warnings.filterwarnings("ignore", message=".*experimental.*", module="google.genai")

from primr.ai.deep_research_execution import poll_interaction_until_terminal
from primr.ai.deep_research_parsing import (
    extract_citations_from_content,
    extract_interaction_citations,
    extract_interaction_content,
    extract_search_queries_count,
)
from primr.ai.deep_research_polling import (
    phase_name_for_elapsed,
    poll_interval_for_elapsed,
)
from primr.config.settings import get_settings
from primr.utils.errors import AIError
from primr.utils.logging_config import get_logger

logger = get_logger("ai.deep_research")


def _require_genai_dependency() -> None:
    if _GENAI_IMPORT_ERROR is None:
        return
    # Allow tests or callers to inject/patch a working client implementation.
    if (
        _FALLBACK_CLIENT_CLASS is not None
        and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS
    ):
        return
    raise AIError(
        "google.genai is not available. Install compatible dependencies "
        "(Python 3.11+ and project requirements).",
        cause=_GENAI_IMPORT_ERROR,
    ) from _GENAI_IMPORT_ERROR


class ResearchStatus(Enum):
    """Status of a deep research task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ResearchProgress:
    """Progress update from deep research."""

    status: ResearchStatus
    message: str = ""
    thought: str | None = None
    partial_result: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ThinkingLog:
    """Log of agent's thinking/reasoning process."""

    interaction_id: str
    company_name: str
    thoughts: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    sources_visited: list[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    def add_thought(self, thought: str) -> None:
        """Add a thought to the log."""
        self.thoughts.append(f"[{datetime.now().strftime('%H:%M:%S')}] {thought}")

    def add_search(self, query: str) -> None:
        """Add a search query to the log."""
        self.search_queries.append(query)

    def add_source(self, url: str) -> None:
        """Add a visited source to the log."""
        if url not in self.sources_visited:
            self.sources_visited.append(url)

    def to_markdown(self) -> str:
        """Export the thinking log as markdown."""
        lines = [
            "# Deep Research Thinking Log",
            f"**Company:** {self.company_name}",
            f"**Interaction ID:** {self.interaction_id}",
            f"**Started:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Agent Reasoning Process",
            "",
        ]

        for thought in self.thoughts:
            lines.append(f"- {thought}")

        if self.search_queries:
            lines.extend(["", "## Search Queries Executed", ""])
            for i, query in enumerate(self.search_queries, 1):
                lines.append(f"{i}. {query}")

        if self.sources_visited:
            lines.extend(["", "## Sources Analyzed", ""])
            for url in self.sources_visited:
                lines.append(f"- {url}")

        if self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            lines.extend(["", f"**Duration:** {duration:.0f} seconds"])

        return "\n".join(lines)


@dataclass
class ResearchResult:
    """Result from a deep research task."""

    content: str
    citations: list[dict[str, str]] = field(default_factory=list)
    interaction_id: str = ""
    duration_seconds: float = 0.0
    status: ResearchStatus = ResearchStatus.COMPLETED
    error: str | None = None
    thinking_log: ThinkingLog | None = None
    search_queries_count: int = 0  # Actual count from groundingMetadata.webSearchQueries

    @property
    def success(self) -> bool:
        """Check if research completed successfully."""
        return self.status == ResearchStatus.COMPLETED and bool(self.content)

    def save_thinking_log(self, filepath: str) -> None:
        """Save the thinking log to a file."""
        if self.thinking_log:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.thinking_log.to_markdown())


# =============================================================================
# JOB TRACKING - Save/load interaction IDs for recovery
# =============================================================================

import contextlib
import os

from primr.ai.citation_resolution import (
    _extract_domain_from_redirect as _extract_domain_from_redirect,
)
from primr.ai.citation_resolution import (
    resolve_citation_urls as resolve_citation_urls,
)
from primr.ai.citation_resolution import (
    resolve_citation_urls_sync,
)
from primr.ai.citation_resolution import (
    resolve_redirect_url as resolve_redirect_url,
)
from primr.ai.file_search_resources import (
    _DEFAULT_STALE_AGE_SECONDS as _DEFAULT_STALE_AGE_SECONDS,
)
from primr.ai.file_search_resources import (
    _PRIMR_RESOURCE_PREFIX as _PRIMR_RESOURCE_PREFIX,
)
from primr.ai.file_search_resources import (
    _is_primr_owned as _is_primr_owned,
)
from primr.ai.file_search_resources import (
    _resource_age_seconds as _resource_age_seconds,
)
from primr.ai.file_search_resources import (
    cleanup_orphaned_resources as cleanup_orphaned_resources,
)
from primr.ai.job_persistence import (
    _get_jobs_file_path as _get_jobs_file_path,
)
from primr.ai.job_persistence import (
    _jobs_file_lock as _jobs_file_lock,
)
from primr.ai.job_persistence import (
    get_pending_jobs as get_pending_jobs,
)
from primr.ai.job_persistence import (
    remove_pending_job,
    save_pending_job,
)


class DeepResearchClient:
    """
    Client for Gemini Deep Research Agent.

    The Deep Research Agent is designed for complex research tasks that
    require multi-step planning, web searching, and synthesis.

    Key features:
    - Autonomous research planning
    - Built-in Google Search
    - URL context analysis
    - Automatic citations
    - Streaming progress updates

    Example:
        client = DeepResearchClient()

        # Simple research
        result = await client.research(
            "Research the competitive landscape of industrial widgets"
        )
        print(result.content)

        # With custom format
        result = await client.research(
            "Research Acme Corp",
            output_format="executive_summary"
        )
    """

    # Import centralized model config
    from primr.config.models import PrimrModels

    # Agent identifier for Deep Research - USE CENTRALIZED CONFIG
    AGENT_ID = PrimrModels.DEEP_RESEARCH_AGENT

    # Default polling interval (seconds) - used as base, actual interval is adaptive
    DEFAULT_POLL_INTERVAL = 10

    # Maximum research time (seconds) - API limit is 60 minutes
    MAX_RESEARCH_TIME = 3600

    # Adaptive polling thresholds (seconds)
    POLL_FAST_THRESHOLD = 60  # First 60s: poll every 5s
    POLL_NORMAL_THRESHOLD = 300  # 60-300s: poll every 10s
    # After 300s: poll every 20s

    def __init__(self, api_key: str | None = None):
        """
        Initialize the Deep Research client.

        Args:
            api_key: Optional API key override. Uses settings if not provided.
        """
        _require_genai_dependency()
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        logger.debug("Deep Research client initialized")

    async def research(
        self,
        query: str,
        output_format: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = MAX_RESEARCH_TIME,
        on_progress: Callable[[ResearchProgress], None] | None = None,
        priority_urls: list[str] | None = None,
        context_files: list[str] | None = None,
        use_streaming: bool = True,
        job_metadata: dict[str, Any] | None = None,
    ) -> ResearchResult:
        """
        Execute a deep research task.

        This method uses streaming with reconnection by default (more resilient),
        with fallback to polling if streaming fails.

        Research tasks typically take 5-20 minutes.

        Args:
            query: The research query/prompt
            output_format: Optional format hint (e.g., "executive_summary")
            poll_interval: Seconds between status checks (for polling fallback)
            timeout: Maximum time to wait for completion
            on_progress: Optional callback for progress updates
            priority_urls: Optional list of URLs to prioritize (e.g., company website)
            context_files: Optional list of file paths to upload as context (PDFs, docs)
            use_streaming: Use streaming mode (more resilient). Set False for legacy polling.

        Returns:
            ResearchResult with content and citations

        Raises:
            AIError: If research fails or times out
        """
        # Try streaming approach first (more resilient)
        if use_streaming:
            try:
                logger.info("Using resilient streaming mode for Deep Research")
                return await self.research_resilient(
                    query=query,
                    output_format=output_format,
                    timeout=timeout,
                    on_progress=on_progress,
                    priority_urls=priority_urls,
                    context_files=context_files,
                    job_metadata=job_metadata,
                )
            except Exception as e:
                logger.warning(f"Streaming mode failed, falling back to polling: {e}")
                if on_progress:
                    on_progress(
                        ResearchProgress(
                            status=ResearchStatus.IN_PROGRESS,
                            message="Streaming failed, switching to polling mode...",
                        )
                    )
                # Fall through to polling mode

        # =================================================================
        # POLLING MODE (fallback)
        # =================================================================

        # PRE-FLIGHT VALIDATION - Check EVERYTHING before expensive API call
        preflight_errors = []

        # 1. Validate query
        if not query or not query.strip():
            preflight_errors.append("Research query cannot be empty")

        # 2. Validate API key exists
        if not self._api_key:
            preflight_errors.append("No API key configured")

        # 3. Validate context files exist and are readable
        if context_files:
            import os

            for f in context_files:
                if not os.path.exists(f):
                    preflight_errors.append(f"Context file not found: {f}")
                elif not os.path.isfile(f):
                    preflight_errors.append(f"Context path is not a file: {f}")
                elif os.path.getsize(f) == 0:
                    preflight_errors.append(f"Context file is empty: {f}")
                else:
                    # Try to read the file to ensure it's accessible
                    try:
                        with open(f, "rb") as test_file:
                            test_file.read(1)  # Just read 1 byte to verify access
                    except Exception as e:
                        preflight_errors.append(f"Cannot read context file {f}: {e}")

        # 4. Validate priority URLs format
        if priority_urls:
            for url in priority_urls:
                if not url.startswith(("http://", "https://")):
                    preflight_errors.append(f"Invalid URL format: {url}")

        # FAIL FAST if any validation errors
        if preflight_errors:
            error_msg = "Pre-flight validation failed:\n  - " + "\n  - ".join(preflight_errors)
            logger.error(error_msg)
            raise AIError(error_msg, model=self.AGENT_ID)

        # 5. Test API connectivity with a lightweight call before expensive operations
        try:
            # Verify we can reach the API (this is cheap)
            from primr.config.models import PrimrModels

            _ = self._client.models.get(model=PrimrModels.FLASH_MODEL)
            logger.info("Pre-flight: API connectivity verified")
        except Exception as e:
            raise AIError(
                f"Pre-flight: API connectivity check failed: {e}", model=self.AGENT_ID
            ) from e

        # 6. Upload context files BEFORE starting research
        # This is a separate API call - if it fails, we haven't started the expensive research yet
        file_store_name = None
        if context_files:
            file_store_name = self._upload_context_files(context_files)
            logger.info(
                f"Pre-flight: {len(context_files)} context files uploaded to {file_store_name}"
            )

        # 7. Build and validate prompt
        prompt = self._build_prompt(query, output_format)
        if len(prompt) < 10:
            raise AIError("Pre-flight: Generated prompt is too short", model=self.AGENT_ID)

        # Add URL context if priority URLs provided
        if priority_urls:
            url_context = "\n\nPriority Sources (analyze these first):\n"
            for url in priority_urls[:5]:  # Limit to 5 URLs
                url_context += f"- {url}\n"
            prompt += url_context

        logger.info(f"Pre-flight: All checks passed. Prompt length: {len(prompt)} chars")

        # =================================================================
        # PRE-FLIGHT COMPLETE - Now safe to start expensive research
        # =================================================================

        start_time = time.time()

        # Reset phase tracking for clean progress display
        self._last_phase = None
        self._last_progress_time = 0

        try:
            # Start the research task
            logger.info(f"Starting deep research (polling mode): {query[:100]}...")
            interaction = self._start_research(prompt, file_store_name=file_store_name)
            interaction_id = interaction.id
            logger.info(f"Research started: {interaction_id}")

            # Note: Progress callback will show "Research started" message
            # Save job for recovery if process is interrupted
            save_pending_job(
                interaction_id=interaction_id,
                job_type="deep_research",
                description=query[:200],
                metadata=job_metadata,
            )

            if on_progress:
                on_progress(
                    ResearchProgress(
                        status=ResearchStatus.IN_PROGRESS, message="Research submitted to API"
                    )
                )

            # Poll for completion with retry for transient errors
            consecutive_poll_errors = 0
            max_poll_errors = 5  # Allow up to 5 consecutive poll failures

            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise AIError(f"Research timed out after {elapsed:.0f}s", model=self.AGENT_ID)

                # Check status with retry for transient errors
                try:
                    interaction = self._get_interaction(interaction_id)
                    consecutive_poll_errors = 0  # Reset on success
                except Exception as e:
                    error_str = str(e).lower()
                    is_transient = (
                        "500" in error_str
                        or "internal server error" in error_str
                        or "503" in error_str
                        or "service unavailable" in error_str
                        or "connection" in error_str
                        or "timeout" in error_str
                    )

                    if is_transient and consecutive_poll_errors < max_poll_errors:
                        consecutive_poll_errors += 1
                        wait_time = 10 * consecutive_poll_errors  # 10s, 20s, 30s, etc.
                        logger.warning(
                            f"Transient error during polling (attempt {consecutive_poll_errors}/{max_poll_errors}), "
                            f"waiting {wait_time}s: {e}"
                        )
                        # Only show progress on first retry to reduce noise
                        if on_progress and consecutive_poll_errors == 1:
                            on_progress(
                                ResearchProgress(
                                    status=ResearchStatus.IN_PROGRESS,
                                    message="API delays detected, retrying...",
                                )
                            )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Non-transient or too many failures
                        raise AIError(
                            f"Deep research polling failed: {e}", model=self.AGENT_ID
                        ) from e

                status = interaction.status

                if status == "completed":
                    content = self._extract_content(interaction)
                    citations = self._extract_citations(interaction)
                    search_count = self._extract_search_queries_count(interaction)

                    result = ResearchResult(
                        content=content,
                        citations=citations,
                        interaction_id=interaction_id,
                        duration_seconds=time.time() - start_time,
                        status=ResearchStatus.COMPLETED,
                        search_queries_count=search_count,
                    )

                    # Remove from pending jobs
                    remove_pending_job(interaction_id)

                    logger.info(
                        f"Research completed in {result.duration_seconds:.0f}s, {search_count} searches"
                    )
                    return result

                elif status == "failed":
                    error_msg = getattr(interaction, "error", "Unknown error")
                    logger.error(f"Research failed: {error_msg}")

                    # Remove from pending jobs
                    remove_pending_job(interaction_id)

                    return ResearchResult(
                        content="",
                        interaction_id=interaction_id,
                        duration_seconds=time.time() - start_time,
                        status=ResearchStatus.FAILED,
                        error=str(error_msg),
                    )

                # Still in progress - show phase changes and periodic updates
                if on_progress:
                    phase = phase_name_for_elapsed(elapsed)

                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

                    # Show progress on phase change OR every 60 seconds (less frequent)
                    phase_changed = not hasattr(self, "_last_phase") or self._last_phase != phase
                    time_for_update = (elapsed - getattr(self, "_last_progress_time", 0)) >= 60

                    if phase_changed or time_for_update:
                        self._last_phase = phase
                        self._last_progress_time = elapsed

                        # Only show time on phase changes, not periodic updates
                        if phase_changed:
                            message = f"{phase} ({time_str})"
                        else:
                            message = f"  {phase}..."  # Minimal update

                        on_progress(
                            ResearchProgress(status=ResearchStatus.IN_PROGRESS, message=message)
                        )

                # Use adaptive polling interval
                current_interval = self._get_poll_interval(elapsed)
                logger.debug(f"Polling in {current_interval}s (elapsed: {elapsed:.0f}s)")
                await asyncio.sleep(current_interval)

        except Exception as e:
            logger.error(f"Deep research error: {e}")
            raise AIError(f"Deep research failed: {e}", model=self.AGENT_ID, cause=e) from e
        finally:
            # CRITICAL: Always cleanup File Search Store to prevent billing leaks
            # Per Gemini docs: "There is no TTL for embeddings and files; they persist until manually deleted"
            if file_store_name:
                self._cleanup_file_store(file_store_name)

    async def research_stream(
        self,
        query: str,
        output_format: str | None = None,
    ) -> AsyncIterator[ResearchProgress]:
        """
        Execute deep research with streaming progress.

        Yields progress updates including thought summaries as the
        research progresses.

        Args:
            query: The research query/prompt
            output_format: Optional format hint

        Yields:
            ResearchProgress updates

        Example:
            async for progress in client.research_stream("Research Acme Corp"):
                if progress.thought:
                    print(f"Thinking: {progress.thought}")
                if progress.partial_result:
                    print(f"Result: {progress.partial_result}")
        """
        prompt = self._build_prompt(query, output_format)

        try:
            # Start streaming research
            stream = self._start_research_stream(prompt)

            for chunk in stream:
                # Capture interaction ID
                if chunk.event_type == "interaction.start":
                    # Skip - parent callback already showed "Research started"
                    pass

                # Track event ID for reconnection
                if hasattr(chunk, "event_id") and chunk.event_id:
                    pass

                # Handle content updates
                if chunk.event_type == "content.delta":
                    if hasattr(chunk.delta, "type"):
                        if chunk.delta.type == "text":
                            yield ResearchProgress(
                                status=ResearchStatus.IN_PROGRESS, partial_result=chunk.delta.text
                            )
                        elif chunk.delta.type == "thought_summary":
                            yield ResearchProgress(
                                status=ResearchStatus.IN_PROGRESS, thought=chunk.delta.content.text
                            )

                # Handle completion
                if chunk.event_type == "interaction.complete":
                    yield ResearchProgress(
                        status=ResearchStatus.COMPLETED, message="Research complete"
                    )
                    break

                # Handle errors
                if chunk.event_type == "error":
                    yield ResearchProgress(
                        status=ResearchStatus.FAILED, message=f"Research failed: {chunk}"
                    )
                    break

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield ResearchProgress(status=ResearchStatus.FAILED, message=f"Stream error: {e}")

    def _build_prompt(self, query: str, output_format: str | None = None) -> str:
        """Build the research prompt with format instructions."""
        if output_format == "company_profile":
            return self._build_company_profile_prompt(query)
        elif output_format == "strategic_layer":
            return self._build_strategic_layer_prompt(query)
        elif output_format == "executive_summary":
            return f"""
{query}

Format the output as an executive summary with:
1. Key Findings (3-5 bullet points)
2. Analysis (2-3 paragraphs)
3. Recommendations (3-5 actionable items)

Formatting: Use single-level bullets only, no em-dashes, write in clear paragraphs.
Cite all sources.
"""
        elif output_format == "competitive_analysis":
            return f"""
{query}

Format the output as a competitive analysis with:
1. Market Overview
2. Key Players (include a comparison table)
3. Competitive Positioning
4. Strengths and Weaknesses
5. Strategic Implications

Formatting: Use single-level bullets only, no em-dashes, write in clear paragraphs. Tables should be simple markdown.
Cite all sources.
"""
        else:
            return query

    def _build_company_profile_prompt(self, query: str) -> str:
        """
        Build a structured company profile prompt for consulting-grade research.

        Structure: Foundational sections first (know them), then strategic analysis (so what),
        then frameworks and hypotheses at the end.

        Uses externalized YAML configuration from src/primr/prompts/company_overview.yaml
        """

        from primr.prompts import build_company_overview_prompt

        # Extract company name from query for header
        company_match = re.search(r"Research\s+(.+?)(?:\s*\(|$)", query)
        company_name = company_match.group(1).strip() if company_match else "Company"

        # Extract website URL if present in query
        url_match = re.search(r"\((https?://[^\)]+)\)", query)
        website_url = url_match.group(1) if url_match else None

        return build_company_overview_prompt(
            company_name=company_name,
            query=query,
            website_url=website_url,
        )

    def _build_strategic_layer_prompt(self, query: str) -> str:
        """
        Build a prompt for Step 2 of the complete research pipeline.

        This adds strategic depth on top of the factual foundation from Step 1.
        The context files contain company overview, products, basic info.

        Prompt is loaded from strategic_layer.yaml via PromptComposer.
        """
        from datetime import datetime

        from primr.prompts.composer import PromptComposer
        from primr.prompts.schema import PromptContext

        try:
            composer = PromptComposer()
            context = PromptContext(
                company_name="Company",  # Will be extracted from query
                current_date=datetime.now().strftime("%B %d, %Y"),
            )
            composed = composer.compose("strategic_layer", context)

            # Insert the query into the prompt
            return composed.content.replace("{query}", query)

        except Exception as e:
            logger.warning(f"Failed to load strategic_layer from YAML: {e}, using fallback")
            # Fallback to minimal prompt
            return f"""You are a senior strategy consultant adding strategic depth to initial research findings.

{query}

Provide strategic analysis including:
- Narrative Gap Analysis
- Competitive Deep-Dive
- Industry Dynamics
- Strategic Assessment (SWOT)
- Risk Analysis
- Strategic Options
- Discovery Questions

Frame everything as hypotheses to explore, not conclusions."""

    def _cleanup_file_store(self, store_name: str) -> None:
        """
        Clean up a File Search Store by deleting documents then the store.

        CRITICAL: Per Gemini docs, "There is no TTL for embeddings and files;
        they persist until manually deleted." We MUST delete documents first,
        then the store, or we leak money.

        Args:
            store_name: Name of the store to delete
        """
        # Step 1: Delete all documents inside the store first
        try:
            docs = list(self._client.file_search_stores.documents.list(parent=store_name))
            for doc in docs:
                try:
                    # Try with config for force delete (deletes chunks too)
                    self._client.file_search_stores.documents.delete(
                        name=doc.name, config={"force": True}
                    )
                except TypeError:
                    # SDK doesn't support config, try without
                    self._client.file_search_stores.documents.delete(name=doc.name)
            if docs:
                logger.debug(f"Deleted {len(docs)} document(s) from {store_name}")
        except Exception as e:
            logger.warning(f"Could not delete documents from {store_name}: {e}")

        # Step 2: Now delete the empty store
        try:
            self._client.file_search_stores.delete(name=store_name)
            logger.debug(f"Cleaned up File Search Store: {store_name}")
        except Exception as e:
            error_str = str(e).lower()
            if "failed_precondition" in error_str or "non-empty" in error_str:
                logger.error(
                    f"CLEANUP FAILED: Store {store_name} still not empty after doc deletion!"
                )
            else:
                logger.warning(f"Could not delete File Search Store {store_name}: {e}")

    def _upload_context_files(self, file_paths: list[str]) -> str:
        """
        Upload files to a File Search store for context.

        FAILS HARD on any error - do not proceed to expensive API call if upload fails.
        CLEANS UP on failure - if upload fails after store creation, we delete the store.

        Args:
            file_paths: List of file paths to upload (PDFs, docs, etc.)

        Returns:
            File store name if successful

        Raises:
            AIError: If upload fails for any reason
        """

        # Validate files exist BEFORE any API calls
        missing_files = [f for f in file_paths if not os.path.exists(f)]
        if missing_files:
            raise AIError(f"Context files not found: {missing_files}", model=self.AGENT_ID)

        valid_files = [f for f in file_paths if os.path.exists(f)]
        if not valid_files:
            raise AIError("No valid context files to upload", model=self.AGENT_ID)

        logger.info(f"Uploading {len(valid_files)} context file(s)...")

        # MIME type mapping for extensions the API doesn't auto-detect
        mime_types = {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".json": "application/json",
            ".csv": "text/csv",
            ".pdf": "application/pdf",
        }

        store_name: str = ""
        try:
            # Create a file search store. Every Primr-created store carries
            # the ``primr-`` display_name prefix so cleanup_orphaned_resources
            # can recognise our own resources and refuse to delete anything
            # belonging to a different application sharing this API key.
            store = self._client.file_search_stores.create(
                config={"display_name": f"primr-research_context_{int(time.time())}"}
            )
            store_name = store.name or ""
            if not store_name:
                raise AIError("Failed to create file store - no name returned", model=self.AGENT_ID)
            logger.info(f"Created file store: {store_name}")

            # Upload each file with explicit MIME type via config
            # FAIL on first error - don't waste money on partial uploads
            for file_path in valid_files:
                logger.info(f"Uploading: {file_path}")
                try:
                    # Get MIME type from extension
                    ext = os.path.splitext(file_path)[1].lower()
                    mime_type = mime_types.get(ext)

                    # Build config with mime_type if we have one
                    config = {"mime_type": mime_type} if mime_type else None

                    self._client.file_search_stores.upload_to_file_search_store(
                        file=file_path,
                        file_search_store_name=store_name or "",
                        config=config,  # type: ignore[arg-type]
                    )
                    logger.info(f"Uploaded: {file_path}")
                except Exception as upload_err:
                    # FAIL HARD - don't continue with broken uploads
                    # But first, clean up the store we created!
                    if store_name:
                        logger.warning(f"Upload failed, cleaning up store {store_name}")
                        self._cleanup_file_store(store_name)
                    raise AIError(
                        f"Failed to upload {file_path}: {upload_err}",
                        model=self.AGENT_ID,
                        cause=upload_err,
                    ) from upload_err

            logger.info(f"All {len(valid_files)} files uploaded successfully")
            return store_name

        except AIError:
            raise  # Re-raise our errors (cleanup already done if needed)
        except Exception as e:
            # Clean up on any other error
            if store_name:
                logger.warning(f"Error occurred, cleaning up store {store_name}")
                self._cleanup_file_store(store_name)
            raise AIError(f"Failed to create file store: {e}", model=self.AGENT_ID, cause=e) from e

    def _start_research(self, prompt: str, file_store_name: str | None = None) -> Any:
        """Start a background research task."""
        # Build tools list
        tools: list[dict[str, Any]] = []
        if file_store_name:
            tools.append({"type": "file_search", "file_search_store_names": [file_store_name]})

        create_kwargs: dict[str, Any] = {
            "input": prompt,
            "agent": self.AGENT_ID,
            "background": True,
            # Interactions API requirement for background jobs.
            "store": True,
        }
        if tools:
            create_kwargs["tools"] = tools

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return self._client.interactions.create(**create_kwargs)

    def _start_research_stream(self, prompt: str) -> Any:
        """Start a streaming research task."""
        return self._client.interactions.create(
            input=prompt,
            agent=self.AGENT_ID,
            background=True,
            store=True,
            stream=True,
            agent_config={"type": "deep-research", "thinking_summaries": "auto"},
        )

    @staticmethod
    def _format_interaction_error(interaction: Any) -> str:
        """Extract a readable provider-side error message from an interaction."""
        fields = (
            "error",
            "error_message",
            "error_status",
            "status_message",
            "failure_reason",
            "last_error",
        )
        for attr_name in fields:
            value = getattr(interaction, attr_name, None)
            if value:
                return str(value)

        try:
            payload = interaction.to_dict() if hasattr(interaction, "to_dict") else {}
        except Exception:
            payload = {}

        for key in (
            "error",
            "errorMessage",
            "error_status",
            "errorStatus",
            "status_message",
            "statusMessage",
            "failure_reason",
            "failureReason",
        ):
            value = payload.get(key)
            if value:
                return str(value)

        details = payload.get("metadata") or payload.get("diagnostics")
        if details:
            return str(details)

        return "Provider reported terminal error with no details"

    def _get_interaction(self, interaction_id: str) -> Any:
        """Get the current state of an interaction."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return self._client.interactions.get(interaction_id)

    def _extract_content(self, interaction: Any) -> str:
        """Extract the text content from a completed interaction.

        The Deep Research API may return multiple output parts.
        We concatenate all text outputs to ensure we capture the full response.
        """
        return extract_interaction_content(interaction)

    def _extract_citations(self, interaction: Any) -> list[dict[str, str]]:
        """Extract citations from a completed interaction."""
        return extract_interaction_citations(interaction)

    def _extract_search_queries_count(self, interaction: Any) -> int:
        """
        Extract the count of actual search queries from groundingMetadata.

        The Gemini API exposes billable search queries in the response via
        groundingMetadata.webSearchQueries. This is the actual count of
        external search calls, NOT the number of "thinking steps".

        Typical reports use 10-30 searches. After Jan 5, 2026, each search
        costs $0.035 ($35/1000 queries).

        Args:
            interaction: The completed interaction object

        Returns:
            Count of search queries, or 0 if not available
        """
        count = extract_search_queries_count(interaction)
        if count == 0:
            logger.debug("No grounding metadata found in interaction response")
        return count

    def _get_poll_interval(self, elapsed_seconds: float) -> float:
        """
        Get adaptive polling interval based on elapsed time.

        Polls more frequently early (to catch quick completions),
        less frequently later (to reduce API calls for long runs).

        Args:
            elapsed_seconds: Time elapsed since research started

        Returns:
            Polling interval in seconds
        """
        return poll_interval_for_elapsed(
            elapsed_seconds,
            schedule=(
                (self.POLL_FAST_THRESHOLD, 5.0),
                (self.POLL_NORMAL_THRESHOLD, 10.0),
            ),
            default_interval=20.0,
        )

    def check_job(self, interaction_id: str) -> dict[str, Any]:
        """
        Check the status of a pending research job.

        Args:
            interaction_id: The interaction ID to check

        Returns:
            Dict with status, content (if completed), and error (if failed)
        """
        try:
            interaction = self._get_interaction(interaction_id)
            status = str(getattr(interaction, "status", "unknown")).lower()

            result = {
                "interaction_id": interaction_id,
                "status": status,
                "content": None,
                "error": None,
                "terminal": False,
                "error_source": None,
            }

            if status == "completed":
                result["content"] = self._extract_content(interaction)
                result["citations"] = self._extract_citations(interaction)
                result["terminal"] = True
                remove_pending_job(interaction_id)
            elif status in {"failed", "error", "cancelled", "canceled", "expired"}:
                result["error"] = self._format_interaction_error(interaction)
                result["terminal"] = True
                result["error_source"] = "provider"
                remove_pending_job(interaction_id)

            return result

        except Exception as e:
            return {
                "interaction_id": interaction_id,
                "status": "check_error",
                "content": None,
                "error": str(e),
                "terminal": False,
                "error_source": "local",
            }

    async def research_resilient(
        self,
        query: str,
        output_format: str | None = None,
        timeout: float = MAX_RESEARCH_TIME,
        on_progress: Callable[[ResearchProgress], None] | None = None,
        priority_urls: list[str] | None = None,
        context_files: list[str] | None = None,
        job_metadata: dict[str, Any] | None = None,
    ) -> ResearchResult:
        """
        Execute deep research with maximum resilience using background job + polling.

        This is the correct implementation that:
        1. Starts a background job (runs async on Google's servers)
        2. Saves the interaction_id for recovery
        3. Polls for completion with exponential backoff
        4. Handles transient errors gracefully
        5. Allows job recovery with `primr --check-jobs`

        Deep Research jobs run asynchronously - if connection drops, the job
        continues running and can be retrieved later.

        Args:
            query: The research query/prompt
            output_format: Optional format hint
            timeout: Maximum time to wait for completion
            on_progress: Optional callback for progress updates
            priority_urls: Optional list of URLs to prioritize
            context_files: Optional list of file paths to upload as context

        Returns:
            ResearchResult with content and citations
        """
        # Pre-flight validation
        preflight_errors = []
        if not query or not query.strip():
            preflight_errors.append("Research query cannot be empty")
        if not self._api_key:
            preflight_errors.append("No API key configured")
        if context_files:
            import os

            for f in context_files:
                if not os.path.exists(f):
                    preflight_errors.append(f"Context file not found: {f}")
        if preflight_errors:
            error_msg = "Pre-flight validation failed:\n  - " + "\n  - ".join(preflight_errors)
            raise AIError(error_msg, model=self.AGENT_ID)

        # Upload context files if provided
        file_store_name = None
        if context_files:
            file_store_name = self._upload_context_files(context_files)

        # Build prompt
        prompt = self._build_prompt(query, output_format)
        if priority_urls:
            url_context = "\n\nPriority Sources (analyze these first):\n"
            for url in priority_urls[:5]:
                url_context += f"- {url}\n"
            prompt += url_context

        start_time = time.time()

        if on_progress:
            on_progress(
                ResearchProgress(
                    status=ResearchStatus.IN_PROGRESS,
                    message="Starting research (background mode)...",
                )
            )

        # Start background job (NO streaming - job runs async on Google's servers)
        interaction_id = None
        job_still_running = False
        try:
            interaction = self._start_research(prompt, file_store_name=file_store_name)
            interaction_id = interaction.id
            logger.info(f"Research started: {interaction_id}")

            # Note: Progress callback will show "Research started" message
            # Save job for recovery
            save_pending_job(
                interaction_id=interaction_id,
                job_type="deep_research",
                description=query[:200],
                metadata=job_metadata,
            )

            if on_progress:
                # Skip - parent callback already showed "Research started"
                pass
        except Exception as e:
            # Clean up store if we created one but failed to start research
            if file_store_name:
                self._cleanup_file_store(file_store_name)
            raise AIError(f"Failed to start research: {e}", model=self.AGENT_ID, cause=e) from e

        # Poll for completion with shared execution engine
        max_poll_errors = 5
        last_progress_update = 0.0
        try:

            def _on_poll(interaction: Any, elapsed: float) -> None:
                nonlocal last_progress_update
                if str(getattr(interaction, "status", "")).lower() in {
                    "completed",
                    "failed",
                    "error",
                    "cancelled",
                    "canceled",
                    "expired",
                }:
                    return
                if on_progress and (elapsed - last_progress_update) >= 60:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                    on_progress(
                        ResearchProgress(
                            status=ResearchStatus.IN_PROGRESS,
                            message=f"Research in progress ({time_str})...",
                        )
                    )
                    last_progress_update = elapsed

            def _on_transient_retry(
                consecutive: int,
                max_allowed: int,
                wait_time: float,
                error: Exception,
            ) -> None:
                logger.warning(
                    f"Transient polling error (attempt {consecutive}/{max_allowed}), "
                    f"waiting {wait_time}s: {error}"
                )
                if on_progress:
                    on_progress(
                        ResearchProgress(
                            status=ResearchStatus.IN_PROGRESS,
                            message=f"API hiccup, retrying in {wait_time}s...",
                        )
                    )

            try:
                interaction, elapsed = await poll_interaction_until_terminal(
                    get_interaction=self._get_interaction,
                    interaction_id=interaction_id,
                    timeout_seconds=timeout,
                    max_poll_errors=max_poll_errors,
                    poll_interval_for_elapsed=self._get_poll_interval,
                    on_poll=_on_poll,
                    on_transient_retry=_on_transient_retry,
                    build_timeout_error=lambda elapsed_s: TimeoutError(
                        f"Research timed out after {elapsed_s:.0f}s"
                    ),
                    build_poll_error=lambda e: AIError(
                        f"Failed to poll research status: {e}",
                        model=self.AGENT_ID,
                        cause=e,
                    ),
                )
            except TimeoutError:
                elapsed = time.time() - start_time
                logger.warning(f"Research polling timed out after {elapsed:.0f}s")
                if on_progress:
                    on_progress(
                        ResearchProgress(
                            status=ResearchStatus.IN_PROGRESS,
                            message=f"Still running after {elapsed:.0f}s. Check later with: primr --check-jobs",
                        )
                    )
                # Don't remove from pending jobs - it may still complete.
                job_still_running = True
                return ResearchResult(
                    content="",
                    interaction_id=interaction_id,
                    duration_seconds=elapsed,
                    status=ResearchStatus.IN_PROGRESS,
                    error=f"Polling timed out after {elapsed:.0f}s. Job may still be running. Use 'primr --check-jobs' to check status.",
                )

            if interaction.status == "completed":
                content = self._extract_content(interaction)
                citations = self._extract_citations(interaction)
                search_count = self._extract_search_queries_count(interaction)
                remove_pending_job(interaction_id)

                logger.info(
                    f"Research completed in {time.time() - start_time:.0f}s, {search_count} searches"
                )
                return ResearchResult(
                    content=content,
                    citations=citations,
                    interaction_id=interaction_id,
                    duration_seconds=elapsed,
                    status=ResearchStatus.COMPLETED,
                    search_queries_count=search_count,
                )

            error_msg = getattr(interaction, "error", "Unknown error")
            remove_pending_job(interaction_id)
            logger.error(f"Research failed: {error_msg}")
            return ResearchResult(
                content="",
                interaction_id=interaction_id,
                duration_seconds=elapsed,
                status=ResearchStatus.FAILED,
                error=str(error_msg),
            )
        finally:
            # CRITICAL: Always cleanup File Search Store to prevent billing leaks
            # Per Gemini docs: "There is no TTL for embeddings and files; they persist until manually deleted"
            # But skip cleanup if job is still running — it may still need the file store
            if file_store_name and not job_still_running:
                self._cleanup_file_store(file_store_name)
            elif file_store_name and job_still_running:
                logger.warning(
                    f"Skipping file store cleanup — job {interaction_id} may still be running"
                )

    def _extract_citations_from_text(self, content: str) -> list[dict[str, str]]:
        """Extract citations from text content (for streaming results)."""
        return extract_citations_from_content(content)


# =============================================================================
# CONSULTING PROMPT BUILDER
# =============================================================================


class ConsultingPromptBuilder:
    """
    Builds consulting-grade prompts for Deep Research.

    Creates comprehensive prompts that include:
    - Consulting persona injection ("Senior Strategy Consultant")
    - All chapter specifications in a single prompt
    - Hierarchy of truth instructions
    - Formatting and epistemic standards

    This ensures Deep Research generates a complete, cohesive report
    in a single API call rather than multiple parallel calls.

    Note: This class now delegates to PromptComposer for consistency.
    The YAML-based configuration in company_overview.yaml is the source of truth.
    This class is maintained for backward compatibility.
    """

    # The standard chapters for a Strategic Company Overview
    # Note: Actual sections are defined in company_overview.yaml
    CHAPTERS = [
        "Executive Summary",
        "Products and Services",
        "Target Customers",
        "Competitive Differentiation",
        "Financial Profile",
        "Company History and Evolution",
        "Leadership and Organization",
        "Industry Dynamics",
        "Competitive Landscape",
        "Business Model and Value Creation",
        "SWOT Analysis",
        "Strategic Tensions",
        "Constraints and Degrees of Freedom",
        "Narrative Gap Analysis",
        "Areas of Potential Fragility",
        "Patterns Worth Exploring",
        "Discovery Questions",
        "Porter's Five Forces Assessment",
        "Value Chain Analysis",
        "Strategic Positioning Hypothesis",
    ]

    def __init__(self):
        """Initialize the ConsultingPromptBuilder."""

    def build_comprehensive_prompt(
        self,
        company_name: str,
        website_url: str | None = None,
    ) -> str:
        """
        Build a single prompt requesting a comprehensive strategic overview.

        This method delegates to PromptComposer.compose("company_overview", context)
        for consistency with the YAML-based prompt architecture.

        Args:
            company_name: Name of the company to research
            website_url: Optional company website URL

        Returns:
            Complete prompt string for Deep Research
        """
        from primr.prompts.composer import PromptComposer
        from primr.prompts.schema import PromptContext

        # Create context for the composer
        context = PromptContext(
            company_name=company_name,
            website_url=website_url,
            has_stage1_context=False,  # Company overview is stage 1, no prior context
        )

        # Use PromptComposer to build the prompt
        composer = PromptComposer()
        composed = composer.compose("company_overview", context)

        return composed.content

    def _get_formatting_rules(self) -> str:
        """
        Get the formatting rules section.

        Note: This method is kept for backward compatibility.
        The actual formatting rules are now defined in shared/formatting.yaml.
        """
        return """FORMATTING RULES (follow these exactly):
- Write in full, detailed paragraphs - this is a comprehensive research document, not a summary
- Use bullets only when listing specific items (products, competitors, etc.)
- Keep bullets single-level only, no nested sub-bullets
- No em-dashes or en-dashes, use commas or periods instead
- Cite sources at the end of each major section using [cite: X, Y, Z] format
- Include data tables where they add clarity (financials, competitors, timeline)
- Every section should have substantial depth - multiple paragraphs with specific evidence"""

    def _get_purpose_section(self) -> str:
        """
        Get the purpose section.

        Note: This method is kept for backward compatibility.
        The actual purpose is now defined in company_overview.yaml.
        """
        return """PURPOSE:
Pre-meeting research to deeply understand the company before discovery. We are forming initial hypotheses from public information. The real insights come from talking with the client.

This document should:
- Prime consultants with solid foundational knowledge
- Surface questions and hypotheses to explore
- Demonstrate homework without pretending we know their business better than they do

Subject-Positive Intent: Assume this company is rational, competent, and successful in its context. Understand how they create value and where support could help them go further."""

    def _get_epistemic_contract(self) -> str:
        """
        Get the epistemic contract section.

        Note: This method is kept for backward compatibility.
        The actual epistemic rules are now defined in shared/epistemic_rules.yaml.
        """
        return """EPISTEMIC CONTRACT:
Every strategic observation must be expressed as one of:
- A verified fact (with citation)
- An inference (clearly labeled)
- A hypothesis to validate in conversation

If a statement cannot be placed cleanly into one of these categories, rewrite it.

TRANSFORMATION RULE:
If a sentence implies inevitability, failure, or urgency, rewrite it as a question or scenario comparison.
Example: Instead of "X faces an existential threat from Y", write "One area worth exploring is whether Y could pressure X's margins over time"

TONE: Walk in informed and curious, not informed and arrogant. Use language like "appears to", "worth exploring", "we'd want to validate". Frame risks as areas where support could unlock value, not as evidence of mismanagement."""

    def _get_tone_guidelines(self) -> str:
        """Get the tone and epistemic humility guidelines."""
        return """TONE AND EPISTEMIC HUMILITY (critical):
- This is research and initial thinking, not conclusions
- Frame strategic observations as "initial hypotheses to explore with the client"
- Use language like "based on public information", "appears to", "worth exploring", "we'd want to validate"
- Clearly distinguish between facts (what we found) and inferences (what we think it might mean)
- Avoid asserting causality or intent without evidence
- Never use absolutist language ("existential threat", "only viable path", "must do", "will definitely")
- Present questions to ask the client, not answers we're telling them
- For any strategic observation, frame it as "something to discuss" not "something we've concluded"
- Frame risks, gaps, or pressures in terms of where support could unlock value, not as evidence of mismanagement
- Do not imply leadership blind spots or strategic naivety unless directly supported by credible evidence"""

    def _get_key_metrics_format(self) -> str:
        """Get the key metrics format section."""
        return """KEY METRICS FORMAT (use these exact formats so we can extract them):
- Employees: X,XXX (or "Employees: ~X,XXX estimated")
- Revenue: $X.XB or $XXM (or "Revenue: ~$XXM estimated")
- Founded: YYYY
- Headquarters: City, State

Build this as a consultant-grade overview using publicly available sources (company site, press releases, earnings calls, news, trusted databases). If financials aren't public, use estimates and label them clearly."""

    def _get_chapter_specifications(self, company_name: str) -> str:
        """Get the complete chapter specifications."""
        return f"""
=============================================================================
LENGTH AND DEPTH REQUIREMENTS (CRITICAL)
=============================================================================

This document must be COMPREHENSIVE and DETAILED. Target 15,000-20,000 words (40-60 pages).
- Each section requires THOROUGH analysis, not brief summaries
- Include specific examples, data points, quotes, and evidence throughout
- Provide multiple paragraphs per section with substantive analysis
- Include tables and structured data where appropriate
- Do NOT write superficial overviews - write detailed analysis a consultant can actually use
- Every claim must be supported with specific evidence and citations

CRITICAL: Follow this EXACT section order. Do not skip or reorder sections.

## Executive Summary
The "so what" up front. 5-7 paragraphs synthesizing the most critical findings. Include:
- Company positioning and market context (1-2 paragraphs)
- Key financial metrics and growth trajectory (1 paragraph)
- Strategic priorities and recent major initiatives (1-2 paragraphs)
- 3-5 areas where consulting support could create meaningful impact (1-2 paragraphs)
Frame key strategic observations as hypotheses worth exploring.

## Detailed Products and Services
COMPREHENSIVE breakdown of their entire offering. Write 8-10 paragraphs covering:
- Complete product/service catalog organized by category with specific product names
- Revenue contribution by product line (if available, estimate if not)
- Pricing models and go-to-market approach for each major offering
- Recent product launches, discontinuations, or pivots (last 2-3 years)
- Technology or platform underpinning their offerings
- Service delivery model and fulfillment approach
- How products/services have evolved over time
- Competitive positioning of each major product line

## Unique Selling Proposition
Deep analysis of competitive differentiation. Write 5-6 paragraphs covering:
- Primary value proposition and core messaging
- Specific capabilities that competitors demonstrably lack
- Customer testimonials, case studies, or reviews that illustrate differentiation
- Evidence of differentiation from third-party sources (analysts, press, awards)
- Potential vulnerabilities or erosion risks in their differentiation
- How their USP has evolved over time

## Mission and Vision
What do they say they stand for? Write 3-4 paragraphs covering:
- Official mission and vision statements (quoted directly)
- How these have evolved over time (compare current to historical if available)
- Alignment or gaps between stated values and observable actions
- Cultural artifacts that reinforce or contradict the mission

## Company History
Detailed chronological narrative. Write 6-8 paragraphs covering:
- Founding story and original business model
- Key pivots or strategic shifts with context on why
- ALL significant acquisitions with dates, deal sizes (if known), and strategic rationale
- Major leadership transitions and their impact
- Funding rounds, investors, and valuation milestones
- Geographic expansion timeline
- Major crises, setbacks, or turnaround moments
Include a timeline table if helpful.

## Key Achievements
Comprehensive list with context. Write 4-5 paragraphs covering:
- Revenue and growth milestones with specific numbers
- Industry awards and recognition (with dates)
- Major customer wins or strategic partnerships
- Innovation achievements, patents, or technology milestones
- Employee or culture awards
- Market share gains or competitive wins

## Target Audience
Detailed customer segmentation. Write 5-6 paragraphs covering:
- Primary customer segments with size estimates
- Detailed customer personas and buying behavior
- Geographic distribution of customer base
- Industry verticals served with relative importance
- Enterprise vs. SMB vs. consumer mix
- Channel partners and distribution strategy
- Customer concentration risks (if discernible)

## Financial Overview
Thorough financial analysis. Write 6-8 paragraphs covering:
- Revenue (actual or estimated with source and confidence level)
- Revenue growth rate and multi-year trajectory
- Profitability indicators (margins, EBITDA, net income if available)
- Complete funding history with investors, dates, and amounts
- Valuation (current and historical if known)
- Key financial ratios vs. industry benchmarks
- Recent financial news, analyst commentary, or credit ratings
- Capital structure and debt profile
Include a financial summary table.

## Key Business Drivers and Strategic KPIs
Analysis of what drives their business. Write 4-5 paragraphs covering:
- Primary revenue drivers and their relative importance
- Unit economics (if discernible from public information)
- Operational KPIs they likely track based on their business model
- Leading indicators of business health
- Metrics that would concern their board
- How KPIs likely differ across business units

## Strategic Tensions (Derived from SWOT)
First, provide a COMPLETE SWOT analysis with 5-8 items per quadrant. Then identify 4-6 core strategic tensions. Write 8-10 paragraphs total covering:

SWOT Analysis (be thorough):
- Strengths: Internal capabilities, assets, advantages (5-8 specific items with evidence)
- Weaknesses: Internal gaps, limitations, vulnerabilities (5-8 specific items with evidence)
- Opportunities: External market shifts, trends, openings (5-8 specific items with evidence)
- Threats: External risks, competitive pressures, macro factors (5-8 specific items with evidence)

Then derive 4-6 strategic tensions from the SWOT. For each tension:
- The tension: What two valuable things are in natural conflict?
- Evidence: What signals suggest this tension exists?
- How they appear to be managing it: What's their current approach?
- Question to explore: What would we want to understand about their choices?

## Leadership and Culture
Comprehensive leadership analysis. Write 6-8 paragraphs covering:
- Complete C-suite profiles with backgrounds, tenure, and previous roles
- Board composition and notable directors
- Leadership stability analysis (recent departures, average tenure)
- Organizational structure insights
- Cultural signals from careers page, press releases, employee reviews
- Leadership communication style and strategic messaging
- Succession planning signals (if any)
- Diversity and inclusion indicators

## Industry Context and Dynamics
Thorough industry analysis. Write 6-8 paragraphs covering:
- Industry size, growth rate, and trajectory
- Key industry trends and disruption factors
- Regulatory environment and upcoming changes
- Technology shifts affecting the industry
- Consolidation or fragmentation trends
- Geographic dynamics (regional differences)
- Supply chain and input cost factors
- Labor market dynamics in the industry
Include industry data tables where helpful.

## Competitive Landscape
Detailed competitive analysis. Write 8-10 paragraphs covering:
- Complete list of direct competitors with brief profiles
- Market share estimates (with sources)
- Competitive positioning map or framework
- Head-to-head comparison on key dimensions (price, quality, service, technology)
- Where {company_name} appears to win deals and why
- Where {company_name} appears to lose deals and why
- Emerging competitors or disruptors to watch
- Competitive dynamics and intensity
- Barriers to entry and competitive moats
Include a competitor comparison table.

## Underlying Theory of Value Creation (Initial)
Articulate the implied logic of how {company_name} creates and captures value. Write 5-6 paragraphs covering:
- The core value proposition: What problem do they solve, for whom, better than alternatives?
- Revenue model: How exactly do they make money? What are the unit economics?
- Reinforcing mechanisms: What creates flywheel effects or compounding advantages?
- Key assumptions: What must remain true for this model to work?
- Vulnerabilities: Where could the logic break down?
- Evolution: How has their value creation model changed over time?

Frame this as an initial theory to be tested in conversation, not a conclusion.

## Strategic Constraints and Degrees of Freedom
Identify structural constraints and areas of flexibility. Write 5-6 paragraphs covering:

Constraints (with specific evidence for each):
- Organizational: Legacy systems, team capabilities, cultural inertia
- Regulatory: Compliance requirements, licensing, industry standards
- Asset-based: Physical infrastructure, contractual obligations, capital structure
- Market: Customer expectations, competitive dynamics, channel dependencies

Degrees of freedom (with specific evidence for each):
- Where do they appear to have genuine flexibility?
- What decisions seem genuinely open?
- Where might small changes have outsized impact?
- What resources or capabilities are underutilized?

## Narrative Gap Analysis
Identify 4-6 interesting contrasts between what the company says and external signals. Write 4-5 paragraphs. For each gap:
- Claim: [what they say - with specific quote or source]
- What we observed: [external signals - with specific evidence]
- Possible explanations: [why this gap might exist]
- Question to explore: [what we'd want to understand from them]

These are observations to explore, not accusations.

## Areas of Structural Fragility
Identify 4-6 areas where the business model may be sensitive to shocks. Write 4-5 paragraphs. For each fragility:
- The fragility: What aspect of the system appears sensitive?
- Evidence: What signals suggest this fragility exists?
- Why it matters: What could trigger stress or failure?
- Severity assessment: How material is this risk?
- What we'd want to understand: How are they thinking about this?

This is system awareness, not critique.

## Patterns and Questions
Identify 5-8 interesting patterns from the research. Write 4-5 paragraphs. For each pattern:
- Observation: [what we found - with specific evidence]
- Why it's interesting: [what makes this pattern notable]
- Possible interpretations: [what it might mean]
- Question for them: [what we'd want to understand]

## Questions for Our First Conversation
The 8-10 most important questions to explore with them. Write 3-4 paragraphs introducing the questions, then list them. For each question:
- The question itself (specific and thoughtful)
- Why we're asking (what research finding prompted this)
- What we hope to learn (how the answer would inform our thinking)

Frame as genuine curiosity, not gotcha questions."""

    def _get_downstream_note(self) -> str:
        """Get the downstream translation note."""
        return """=============================================================================
DOWNSTREAM TRANSLATION NOTE
=============================================================================
This output is intended to inform internal thinking and deck creation. When reused externally, conclusions should be softened, hypotheses foregrounded, and language reframed for diplomacy."""

    def contains_all_chapters(self, prompt: str) -> bool:
        """
        Check if a prompt contains specifications for all 10 chapters.

        Args:
            prompt: The prompt text to check

        Returns:
            True if all chapters are present
        """
        return all(chapter in prompt for chapter in self.CHAPTERS)

    def contains_consulting_persona(self, prompt: str) -> bool:
        """
        Check if a prompt contains the consulting persona.

        Args:
            prompt: The prompt text to check

        Returns:
            True if consulting persona is present
        """
        return "senior strategy consultant" in prompt.lower()


# =============================================================================
# DEEP RESEARCH ORCHESTRATOR
# =============================================================================


@dataclass
class DeepResearchOrchestratorResult:
    """Result from DeepResearchOrchestrator report generation."""

    company_name: str
    content: str
    citations: list[dict[str, str]]
    duration_seconds: float
    success: bool
    error: str | None = None
    interaction_id: str = ""
    api_calls: int = 1  # Always 1 for single-call architecture
    sections_written: int = 0  # Number of sections successfully written
    search_queries_count: int = 0  # Actual search count from groundingMetadata

    @property
    def word_count(self) -> int:
        """Approximate word count of the content."""
        return len(self.content.split()) if self.content else 0


class DeepResearchOrchestrator:
    """
    Orchestrates a single Deep Research API call for complete report generation.

    This is the core component of the cohesive report architecture. Instead of
    making 10 parallel API calls (which fail with 429 quota errors), this
    orchestrator makes a single comprehensive call that generates the entire
    report in one invocation.

    Key features:
    - Pre-flight validation before expensive operations
    - Single API call per report (not parallel chapters)
    - Exponential backoff retry (60s base, 5 attempts max)
    - Adaptive polling (5s → 10s → 20s → 30s)
    - 60-minute timeout
    - Automatic File Search Store cleanup
    - Fallback to Stage 1 context if Deep Research fails

    Usage:
        orchestrator = DeepResearchOrchestrator()

        # Validate before starting (recommended)
        validation = await orchestrator.validate_prerequisites()
        if not validation["success"]:
            print(f"Pre-flight failed: {validation['errors']}")
            return

        result = await orchestrator.generate_report(
            company_name="Acme Corp",
            website_url="https://acme.com",
            stage1_context="... structured research from Stage 1 ...",
            on_progress=lambda msg: print(msg)
        )
    """

    # Import centralized model config
    from primr.config.models import PrimrModels

    AGENT_ID = PrimrModels.DEEP_RESEARCH_AGENT
    SECTION_MODEL = PrimrModels.FLASH_MODEL  # For section writing (cheap, fast)
    MAX_RETRIES = 5
    BASE_RETRY_DELAY = 60.0  # 1 minute base delay for exponential backoff
    TIMEOUT_SECONDS = 3600  # 60 minutes

    def __init__(self, api_key: str | None = None):
        """
        Initialize the DeepResearchOrchestrator.

        Args:
            api_key: Optional API key override. Uses settings if not provided.
        """
        _require_genai_dependency()
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        self._prompt_builder = ConsultingPromptBuilder()  # Legacy, kept for compatibility
        self._store_manager = FileSearchStoreManager(api_key=api_key)
        self._api_call_count = 0
        logger.debug("DeepResearchOrchestrator initialized")

    async def validate_prerequisites(
        self,
        company_name: str | None = None,
        website_url: str | None = None,
        mode: str = "full",
        on_progress: Callable[[str], None] | None = None,
    ) -> dict:
        """
        Run pre-flight validation before starting expensive operations.

        This is a convenience wrapper around PreflightValidator.
        For more control, use PreflightValidator directly.

        Args:
            company_name: Target company name (unused, kept for compatibility)
            website_url: Target website URL
            mode: Research mode - "full", "deep", or "scrape"
            on_progress: Optional progress callback

        Returns:
            dict with success, errors, warnings, details
        """
        from primr.ai.preflight import PreflightValidator

        validator = PreflightValidator()
        result = await validator.validate(
            mode=mode,
            website_url=website_url,
            on_progress=on_progress,
        )

        # Convert to dict for backward compatibility
        return {
            "success": result.success,
            "errors": result.errors,
            "warnings": result.warnings,
            "details": result.checks,
            "estimated_duration": result.estimated_duration,
            "estimated_cost": result.estimated_cost,
        }

    async def generate_report(
        self,
        company_name: str,
        website_url: str | None = None,
        stage1_context: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> DeepResearchOrchestratorResult:
        """
        Generate a complete strategic report using Deep Research.

        Makes a single Deep Research API call with comprehensive prompt
        and optional Stage 1 context. Handles retries with exponential
        backoff and ensures cleanup of temporary resources.

        Args:
            company_name: Target company name
            website_url: Optional company website URL
            stage1_context: Optional structured research from Stage 1
            on_progress: Optional progress callback

        Returns:
            DeepResearchOrchestratorResult with complete report or error
        """
        start_time = time.time()
        store_name: str | None = None
        self._api_call_count = 0

        try:
            # Build the comprehensive prompt using PromptComposer
            from primr.prompts.composer import PromptComposer
            from primr.prompts.schema import PromptContext

            composer = PromptComposer()
            context = PromptContext(
                company_name=company_name,
                website_url=website_url,
                has_stage1_context=stage1_context is not None,
            )
            composed = composer.compose("company_overview", context)
            prompt = composed.content

            if on_progress:
                on_progress("Building comprehensive research prompt...")

            # Upload Stage 1 context if provided
            if stage1_context:
                if on_progress:
                    on_progress("Uploading Stage 1 context to File Search Store...")
                store_name = self._store_manager.create_store(f"research_{company_name}")
                self._store_manager.upload_context(
                    store_name=store_name,
                    content=stage1_context,
                    filename="stage1_research.txt",
                    mime_type="text/plain",
                )

            # Execute with retry
            if on_progress:
                on_progress("Starting Deep Research (single comprehensive call)...")

            result = await self._execute_with_retry(
                prompt=prompt,
                store_name=store_name,
                on_progress=on_progress,
            )

            return DeepResearchOrchestratorResult(
                company_name=company_name,
                content=result.content,
                citations=result.citations,
                duration_seconds=time.time() - start_time,
                success=result.success,
                error=result.error,
                interaction_id=result.interaction_id,
                api_calls=self._api_call_count,
                search_queries_count=result.search_queries_count,
            )

        except Exception as e:
            logger.error(f"DeepResearchOrchestrator error: {e}")
            return DeepResearchOrchestratorResult(
                company_name=company_name,
                content="",
                citations=[],
                duration_seconds=time.time() - start_time,
                success=False,
                error=str(e),
                api_calls=self._api_call_count,
            )
        finally:
            # Always cleanup the File Search Store
            if store_name:
                if on_progress:
                    on_progress("Cleaning up File Search Store...")
                self._store_manager.delete_store(store_name)

    async def _execute_with_retry(
        self,
        prompt: str,
        store_name: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> ResearchResult:
        """
        Execute Deep Research with exponential backoff retry.

        Handles retryable errors:
        - 429: Quota/rate limit errors
        - 500: Internal server errors (transient)
        - 503: Service unavailable
        - Connection errors

        Args:
            prompt: The research prompt
            store_name: Optional File Search Store name
            on_progress: Optional progress callback

        Returns:
            ResearchResult from the API
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                self._api_call_count += 1
                return await self._execute_single(
                    prompt=prompt,
                    store_name=store_name,
                    on_progress=on_progress,
                )
            except AIError as e:
                last_error = e
                error_str = str(e).lower()

                # Check if it's a retryable error
                is_retryable = (
                    "429" in error_str
                    or "quota" in error_str
                    or "rate" in error_str
                    or "500" in error_str
                    or "internal server error" in error_str
                    or "503" in error_str
                    or "service unavailable" in error_str
                    or "connection" in error_str
                    or "timeout" in error_str
                )

                if is_retryable and attempt < self.MAX_RETRIES - 1:
                    delay = self._calculate_backoff_delay(attempt)

                    # Categorize the error for logging
                    if "429" in error_str or "quota" in error_str or "rate" in error_str:
                        error_type = "Rate limit"
                    elif "500" in error_str or "internal server error" in error_str:
                        error_type = "Server error (500)"
                    elif "503" in error_str or "service unavailable" in error_str:
                        error_type = "Service unavailable (503)"
                    else:
                        error_type = "Connection error"

                    logger.warning(
                        f"{error_type}, waiting {delay:.0f}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )
                    if on_progress:
                        on_progress(
                            f"{error_type}. Retrying in {delay:.0f}s "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})..."
                        )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error or max retries reached
                if attempt >= self.MAX_RETRIES - 1:
                    logger.error(f"Max retries ({self.MAX_RETRIES}) exhausted: {e}")
                raise
            except Exception as e:
                # Catch any other exceptions and check if retryable
                last_error = e
                error_str = str(e).lower()

                is_retryable = (
                    "500" in error_str
                    or "internal server error" in error_str
                    or "connection" in error_str
                    or "timeout" in error_str
                )

                if is_retryable and attempt < self.MAX_RETRIES - 1:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f"Transient error, waiting {delay:.0f}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    if on_progress:
                        on_progress(
                            f"Transient error. Retrying in {delay:.0f}s "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})..."
                        )
                    await asyncio.sleep(delay)
                    continue

                raise

        # All retries exhausted
        error_msg = (
            f"Deep Research failed after {self.MAX_RETRIES} attempts. Last error: {last_error}"
        )
        logger.error(error_msg)
        return ResearchResult(
            content="",
            status=ResearchStatus.FAILED,
            error=error_msg,
        )

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.

        delay = base_delay * 2^attempt

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        return self.BASE_RETRY_DELAY * (2**attempt)

    async def _execute_single(
        self,
        prompt: str,
        store_name: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> ResearchResult:
        """
        Execute a single Deep Research API call.

        Args:
            prompt: The research prompt
            store_name: Optional File Search Store name
            on_progress: Optional progress callback

        Returns:
            ResearchResult from the API
        """
        # Build tools list
        tools: list[dict[str, Any]] = []
        if store_name:
            tools.append({"type": "file_search", "file_search_store_names": [store_name]})

        # Start the research
        create_kwargs: dict[str, Any] = {
            "input": prompt,
            "agent": self.AGENT_ID,
            "background": True,
            # Background interactions must be stored for reliable resume/poll.
            "store": True,
        }
        if tools:
            create_kwargs["tools"] = tools

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            interaction = self._client.interactions.create(**create_kwargs)
        interaction_id = interaction.id
        logger.info(f"Deep Research started: {interaction_id}")

        # Show single "Research started" message
        if on_progress:
            on_progress("Research started")

        # Poll for completion with adaptive intervals
        return await self._poll_for_completion(
            interaction_id=interaction_id,
            on_progress=on_progress,
        )

    async def _poll_for_completion(
        self,
        interaction_id: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> ResearchResult:
        """
        Poll for research completion with adaptive intervals and timeout.

        Polling intervals: 5s → 10s → 20s → 30s based on elapsed time.
        Handles transient 500/503 errors during polling with retry.

        Args:
            interaction_id: The interaction ID to poll
            on_progress: Optional progress callback

        Returns:
            ResearchResult when complete

        Raises:
            AIError: If research fails or times out
        """
        last_phase = ""
        last_progress_time = 0.0
        poll_count = 0
        max_poll_errors = 5  # Allow up to 5 consecutive poll failures

        def _on_poll(interaction: Any, elapsed: float) -> None:
            nonlocal poll_count, last_phase, last_progress_time
            poll_count += 1

            # Log status periodically for diagnostics
            if poll_count % 5 == 0:
                logger.info(
                    f"Deep Research polling: status={interaction.status}, "
                    f"elapsed={elapsed:.0f}s, polls={poll_count}"
                )

            if str(getattr(interaction, "status", "")).lower() in {
                "completed",
                "failed",
                "error",
                "cancelled",
                "canceled",
                "expired",
            }:
                return

            # Still in progress - show phase changes and periodic updates
            if on_progress:
                phase = self._get_phase_name(elapsed)
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

                # Show progress on phase change OR every 30 seconds
                phase_changed = phase != last_phase
                time_for_update = (elapsed - last_progress_time) >= 30

                if phase_changed or time_for_update:
                    last_phase = phase
                    last_progress_time = elapsed

                    # Add activity indicator for long waits
                    if time_for_update and not phase_changed:
                        on_progress(f". {phase} ({time_str})")
                    else:
                        on_progress(f"{phase} ({time_str})")

        def _on_transient_retry(
            consecutive: int,
            max_allowed: int,
            wait_time: float,
            error: Exception,
        ) -> None:
            logger.warning(
                f"Transient error during polling (attempt {consecutive}/{max_allowed}), "
                f"waiting {wait_time}s: {error}"
            )
            # Only show progress on first retry to reduce noise
            if on_progress and consecutive == 1:
                on_progress("API delays detected, retrying...")

        interaction, elapsed = await poll_interaction_until_terminal(
            get_interaction=self._client.interactions.get,
            interaction_id=interaction_id,
            timeout_seconds=self.TIMEOUT_SECONDS,
            max_poll_errors=max_poll_errors,
            poll_interval_for_elapsed=self._get_poll_interval,
            on_poll=_on_poll,
            on_transient_retry=_on_transient_retry,
            build_timeout_error=lambda _: AIError(
                f"Deep Research timed out after {self.TIMEOUT_SECONDS}s. ID: {interaction_id}",
                model=self.AGENT_ID,
            ),
            build_poll_error=lambda e: AIError(
                f"Deep Research polling failed: {e}",
                model=self.AGENT_ID,
            ),
        )

        status = interaction.status
        if status == "completed":
            content = self._extract_content(interaction)
            citations = self._extract_citations(interaction)
            search_queries_count = self._extract_search_queries_count(interaction)

            logger.info(f"Deep Research completed in {elapsed:.0f}s")

            return ResearchResult(
                content=content,
                citations=citations,
                interaction_id=interaction_id,
                duration_seconds=elapsed,
                status=ResearchStatus.COMPLETED,
                search_queries_count=search_queries_count,
            )

        error_msg = getattr(interaction, "error", "Unknown error")
        raise AIError(f"Deep Research failed: {error_msg}", model=self.AGENT_ID)

    def _get_phase_name(self, elapsed_seconds: float) -> str:
        """Get the current phase name based on elapsed time."""
        return phase_name_for_elapsed(elapsed_seconds)

    def _get_poll_interval(self, elapsed_seconds: float) -> float:
        """
        Get adaptive polling interval based on elapsed time.

        5s → 10s → 20s → 30s
        """
        return poll_interval_for_elapsed(
            elapsed_seconds,
            schedule=(
                (60.0, 5.0),
                (180.0, 10.0),
                (360.0, 20.0),
            ),
            default_interval=30.0,
        )

    def _extract_content(self, interaction: Any) -> str:
        """Extract all output text content from a completed interaction."""
        return extract_interaction_content(interaction)

    def _extract_citations(self, interaction: Any) -> list[dict[str, str]]:
        """Extract citations from completed interaction outputs."""
        return extract_interaction_citations(interaction)

    def _extract_search_queries_count(self, interaction: Any) -> int:
        """Extract search query count from grounding metadata."""
        return extract_search_queries_count(interaction)

    # =========================================================================
    # ACCORDION METHOD - Generate 30+ page reports
    # =========================================================================
    #
    # Architecture (from docs/more deep research guidance.txt):
    # 1. Deep Research = Lead Researcher (gather facts, NOT write final report)
    # 2. Blueprint = Detailed outline with word count targets
    # 3. Section-by-Section Writing = Write each section with context continuity
    #
    # This avoids "Middle Muddle" and hallucination spirals that occur when
    # asking for 50 pages at once.

    # Sections and prompts are loaded dynamically from company_overview.yaml
    # This allows the report structure to be modified without code changes
    _sections_cache: list[dict] | None = None
    _accordion_prompts_cache: dict | None = None

    @classmethod
    def _load_accordion_prompts(cls) -> dict:
        """
        Load Accordion Method prompts from company_overview.yaml.

        Returns dict with:
        - research_dossier_prompt: Template for Phase 1 (gathering raw facts)
        - section_writing_prompt: Template for Phase 2 (writing sections)
        - position_guidance: Dict of opening/middle/closing guidance
        """
        if cls._accordion_prompts_cache is not None:
            return cls._accordion_prompts_cache

        from primr.prompts.composer import PromptComposer

        try:
            composer = PromptComposer()
            config = composer._load_config("company_overview")

            accordion = config.raw_config.get("accordion_method", {})

            cls._accordion_prompts_cache = {
                "research_dossier_prompt": accordion.get("research_dossier_prompt", ""),
                "section_writing_prompt": accordion.get("section_writing_prompt", ""),
                "position_guidance": accordion.get("position_guidance", {}),
            }

            logger.info("Loaded Accordion Method prompts from company_overview.yaml")
            return cls._accordion_prompts_cache

        except Exception as e:
            logger.warning(f"Failed to load accordion prompts from YAML: {e}")
            return cls._get_default_accordion_prompts()

    @classmethod
    def _get_default_accordion_prompts(cls) -> dict:
        """Fallback default accordion prompts if YAML loading fails."""
        return {
            "research_dossier_prompt": """You are a Lead Researcher compiling a research dossier on {company_name}{website_context}.
Compile comprehensive facts about the company including basics, products, customers, competitors, financials, leadership, and industry context.
Do NOT write polished prose - this is raw research material.""",
            "section_writing_prompt": """Write the content for the **{section_title}** section with depth and analytical rigor.

## CRITICAL FORMATTING INSTRUCTION

The section title **{section_title}** will be added as a heading automatically by the framework.

DO NOT write:
- "## {section_title}"
- "### {section_title}"
- Any heading that repeats or closely matches "{section_title}"

INSTEAD, start immediately with:
- The first paragraph of analysis
- OR a descriptive subtitle that adds context

Example of WRONG approach:
```
### Executive Summary

MRI Software stands at a critical juncture...
```

Example of CORRECT approach:
```
MRI Software stands at a critical juncture...
```

OR with descriptive subtitle:
```
### Strategic Position and Value Creation

MRI Software stands at a critical juncture...
```

Instructions: {section_instructions}

Write the content now, following the formatting rules above.""",
            "position_guidance": {
                "opening": "This is the OPENING section. Set the analytical tone for the entire report.",
                "middle": "Build naturally on the previous sections.",
                "closing": "This is the CLOSING section. Tie together all previous analysis.",
            },
        }

    @classmethod
    def _load_sections_from_yaml(cls) -> list[dict]:
        """
        Load report sections from company_overview.yaml.

        Converts SectionSpec objects to the dict format needed for section writing.
        Sections are cached after first load.

        The YAML defines:
        - id: unique section identifier
        - name: display title
        - part: grouping (1-5)
        - position: opening, middle, or closing (for narrative flow)
        - purpose: what this section accomplishes
        - covers: bullet points of what to include
        - depth: guidance on level of detail
        """
        if cls._sections_cache is not None:
            return cls._sections_cache

        from primr.prompts.composer import PromptComposer

        try:
            composer = PromptComposer()
            config = composer._load_config("company_overview")

            sections = []
            for section in config.sections:
                # Build instructions from purpose, covers, and depth
                instructions_parts = []
                if section.purpose:
                    instructions_parts.append(section.purpose)
                if section.covers:
                    instructions_parts.append("\nCover:")
                    for item in section.covers:
                        instructions_parts.append(f"- {item}")
                if section.depth:
                    instructions_parts.append(f"\n{section.depth}")

                # Get position from YAML (defaults to 'middle' if not specified)
                position = getattr(section, "position", "middle") or "middle"

                sections.append(
                    {
                        "id": section.id,
                        "title": section.name,
                        "instructions": "\n".join(instructions_parts),
                        "part": section.part,
                        "position": position,
                    }
                )

            cls._sections_cache = sections
            logger.info(f"Loaded {len(sections)} sections from company_overview.yaml")
            return sections

        except Exception as e:
            logger.warning(f"Failed to load sections from YAML: {e}, using defaults")
            return cls._get_default_sections()

    @classmethod
    def _get_default_sections(cls) -> list[dict]:
        """Fallback default sections if YAML loading fails."""
        return [
            {
                "id": "executive_summary",
                "title": "Executive Summary",
                "instructions": "Write the executive summary synthesizing key insights.",
                "part": 1,
                "position": "opening",
            },
            {
                "id": "products_services",
                "title": "Products and Services",
                "instructions": "Analyze what they sell and how they make money.",
                "part": 1,
                "position": "middle",
            },
            {
                "id": "competitive_landscape",
                "title": "Competitive Landscape",
                "instructions": "Analyze competitors and market position.",
                "part": 2,
                "position": "middle",
            },
            {
                "id": "strategic_assessment",
                "title": "Strategic Assessment",
                "instructions": "Provide SWOT analysis and strategic tensions.",
                "part": 3,
                "position": "middle",
            },
            {
                "id": "discovery_questions",
                "title": "Discovery Questions",
                "instructions": "Key questions for the first conversation.",
                "part": 4,
                "position": "closing",
            },
        ]

    @property
    def REPORT_SECTIONS(self) -> list[dict]:
        """Get report sections (loaded from YAML)."""
        return self._load_sections_from_yaml()

    # Delay between section writes (seconds)
    SECTION_WRITE_DELAY = 10
    SECTION_WRITE_DELAY_AFTER_ERROR = 30

    async def generate_comprehensive_report(
        self,
        company_name: str,
        website_url: str | None = None,
        stage1_context: str | None = None,
        on_progress: Callable[[str], None] | None = None,
        target_pages: int = 30,
    ) -> DeepResearchOrchestratorResult:
        """
        Generate a comprehensive 30+ page report using the Accordion Method.

        Architecture (from docs/more deep research guidance.txt):

        Phase 1: Research Dossier
            - Use Deep Research as Lead Researcher to gather facts
            - NOT to write the final report
            - Output: Raw research with citations

        Phase 2: Section-by-Section Writing
            - Write each section using previous_interaction_id
            - Pass context from previous sections for consistency
            - One API call per section (not parallel)

        This avoids:
        - "Middle Muddle" (pages 10-40 becoming vague)
        - Hallucination spirals (errors compounding)
        - 429 quota errors (sequential, not parallel)

        Args:
            company_name: Target company name
            website_url: Optional company website URL
            stage1_context: Optional structured research from Stage 1
            on_progress: Optional progress callback
            target_pages: Target page count (default 30)

        Returns:
            DeepResearchOrchestratorResult with comprehensive report
        """
        start_time = time.time()
        store_name: str | None = None
        self._api_call_count = 0
        current_delay = self.SECTION_WRITE_DELAY

        # Track written sections for context continuity
        written_sections: list[dict[str, str]] = []
        all_citations: list[dict[str, str]] = []
        total_search_queries = 0  # Accumulate search queries from all phases

        try:
            # ================================================================
            # PHASE 1: Research Dossier (Deep Research as Lead Researcher)
            # ================================================================
            if on_progress:
                on_progress("Phase 1: Gathering research dossier...")
                on_progress("  Deep Research will compile facts, NOT write the final report")

            # Build research dossier prompt - asking for RAW FACTS, not polished prose
            dossier_prompt = self._build_research_dossier_prompt(company_name, website_url)

            # Upload Stage 1 context if provided
            if stage1_context:
                if on_progress:
                    on_progress("  Uploading Stage 1 context to File Search Store...")
                store_name = self._store_manager.create_store(f"research_{company_name}")
                self._store_manager.upload_context(
                    store_name=store_name,
                    content=stage1_context,
                    filename="stage1_research.txt",
                    mime_type="text/plain",
                )

            # Execute Deep Research for dossier
            dossier_result = await self._execute_with_retry(
                prompt=dossier_prompt,
                store_name=store_name,
                on_progress=on_progress,
            )

            # FALLBACK: If Deep Research fails but we have Stage 1 context, use that
            if not dossier_result.success:
                if stage1_context:
                    if on_progress:
                        on_progress(f"  Deep Research failed: {dossier_result.error}")
                        on_progress("  FALLBACK: Using Stage 1 context as research dossier")
                    research_dossier = stage1_context
                    base_interaction_id = ""  # No interaction ID for fallback
                    # Continue to Phase 2 with Stage 1 data as the dossier
                else:
                    # No fallback available
                    return DeepResearchOrchestratorResult(
                        company_name=company_name,
                        content="",
                        citations=[],
                        duration_seconds=time.time() - start_time,
                        success=False,
                        error=f"Research dossier failed and no Stage 1 context available: {dossier_result.error}",
                        api_calls=self._api_call_count,
                    )
            else:
                research_dossier = dossier_result.content
                base_interaction_id = dossier_result.interaction_id
                all_citations.extend(dossier_result.citations)
                total_search_queries += dossier_result.search_queries_count

            dossier_words = len(research_dossier.split())
            if on_progress:
                on_progress(
                    f"Phase 1 complete: Research dossier gathered ({dossier_words:,} words)"
                )

            # ================================================================
            # PHASE 2: Section-by-Section Writing
            # ================================================================
            if on_progress:
                on_progress(f"Phase 2: Writing {len(self.REPORT_SECTIONS)} sections...")
                on_progress("  Each section maintains context from previous sections")

            successful_sections = 0
            failed_sections = 0
            consecutive_failures = 0

            for i, section in enumerate(self.REPORT_SECTIONS):
                # Stop if too many consecutive failures
                if consecutive_failures >= 3:
                    if on_progress:
                        on_progress(f"Stopping: {consecutive_failures} consecutive failures")
                        on_progress("  API quota may be exhausted. Returning partial report.")
                    break

                section_num = i + 1
                total_sections = len(self.REPORT_SECTIONS)

                if on_progress:
                    on_progress(f"Writing: {section['title']} ({section_num}/{total_sections})...")

                # Add delay between sections (except first)
                if i > 0:
                    # Brief delay between sections (no verbose output)
                    await asyncio.sleep(current_delay)

                # Build section prompt with full context (Stage 1 + dossier + previous sections)
                section_prompt = self._build_section_prompt(
                    section=section,
                    company_name=company_name,
                    research_dossier=research_dossier,
                    previous_sections=written_sections,
                    stage1_context=stage1_context,
                    section_index=i,
                    total_sections=total_sections,
                )

                # Write section using direct Gemini Pro generation
                # This is the proven approach from AccordionTestRunner:
                # - Pass dossier + previous sections in the prompt
                # - Use generate_content() directly (not interactions API)
                max_retries = 3
                section_success = False

                for retry in range(max_retries):
                    try:
                        result = await self._execute_direct_generation(
                            prompt=section_prompt,
                            on_progress=None,  # Don't spam progress for retries
                        )

                        if result.success and result.content:
                            words = len(result.content.split())
                            # Accept any substantive content (at least 100 words)
                            min_words = 100

                            if words >= min_words:
                                written_sections.append(
                                    {
                                        "id": section["id"],
                                        "title": section["title"],
                                        "content": result.content,
                                        "words": words,
                                    }
                                )
                                all_citations.extend(result.citations)
                                successful_sections += 1
                                consecutive_failures = 0
                                section_success = True

                                # Reduce delay on success
                                current_delay = max(8, current_delay - 2)

                                if on_progress:
                                    on_progress(f"  {section['title']}: {words:,} words")
                                break
                            else:
                                logger.warning(
                                    f"Section too short: {words} words (min {min_words})"
                                )
                                if retry < max_retries - 1:
                                    await asyncio.sleep(5)
                                    continue
                        else:
                            error_msg = result.error or "No content"
                            logger.warning(f"Section failed: {error_msg}")

                            # Check for rate limiting
                            if "429" in str(error_msg) or "quota" in str(error_msg).lower():
                                current_delay = min(60, current_delay + 15)
                                if on_progress:
                                    on_progress(f"  Rate limited. Delay now {current_delay}s")

                            if retry < max_retries - 1:
                                wait = self.SECTION_WRITE_DELAY_AFTER_ERROR
                                if on_progress:
                                    on_progress(f"  Retrying in {wait}s...")
                                await asyncio.sleep(wait)
                                continue

                    except Exception as e:
                        logger.warning(f"Section error: {e}")
                        if retry < max_retries - 1:
                            await asyncio.sleep(self.SECTION_WRITE_DELAY_AFTER_ERROR)
                            continue

                if not section_success:
                    failed_sections += 1
                    consecutive_failures += 1
                    current_delay = min(60, current_delay + 10)
                    if on_progress:
                        on_progress(f"  Skipped after {max_retries} attempts")

            if on_progress:
                on_progress(
                    f"Phase 2 complete: {successful_sections} sections written, {failed_sections} skipped"
                )

            # ================================================================
            # PHASE 3: Assemble Final Report
            # ================================================================
            if on_progress:
                on_progress("Phase 3: Assembling final report...")

            # Extract metadata from Stage 1 context (if available)
            industry = self._extract_industry_from_context(stage1_context)
            full_company_name = self._extract_full_company_name(stage1_context)

            final_content = self._assemble_report(
                company_name=company_name,
                website_url=website_url,
                sections=written_sections,
                industry=industry,
                full_company_name=full_company_name,
            )

            final_words = len(final_content.split())
            final_pages = final_words // 500

            if on_progress:
                on_progress(f"Report complete: ~{final_pages} pages ({final_words:,} words)")
                on_progress(
                    f"API calls: {self._api_call_count} (1 research + {successful_sections} sections)"
                )

            # Success if we got at least half the sections
            success = successful_sections >= len(self.REPORT_SECTIONS) // 2

            return DeepResearchOrchestratorResult(
                company_name=company_name,
                content=final_content,
                citations=all_citations,
                duration_seconds=time.time() - start_time,
                success=success,
                error=None
                if success
                else f"Only {successful_sections}/{len(self.REPORT_SECTIONS)} sections completed",
                interaction_id=base_interaction_id,
                api_calls=self._api_call_count,
                sections_written=successful_sections,
                search_queries_count=total_search_queries,
            )

        except Exception as e:
            logger.error(f"Report generation error: {e}")
            # Return partial report if we have sections
            industry = (
                self._extract_industry_from_context(stage1_context) if stage1_context else None
            )
            full_name = self._extract_full_company_name(stage1_context) if stage1_context else None
            partial = (
                self._assemble_report(
                    company_name, website_url, written_sections, industry, full_name
                )
                if written_sections
                else ""
            )
            return DeepResearchOrchestratorResult(
                company_name=company_name,
                content=partial,
                citations=all_citations,
                duration_seconds=time.time() - start_time,
                success=bool(written_sections),
                error=str(e),
                api_calls=self._api_call_count,
                sections_written=len(written_sections),
                search_queries_count=total_search_queries,
            )
        finally:
            if store_name:
                if on_progress:
                    on_progress("Cleaning up...")
                self._store_manager.delete_store(store_name)

    def _build_research_dossier_prompt(self, company_name: str, website_url: str | None) -> str:
        """
        Build prompt for Phase 1: Research Dossier.

        This asks Deep Research to gather RAW FACTS, not write polished prose.
        The dossier becomes the source material for section-by-section writing.

        Prompt is loaded from company_overview.yaml accordion_method.research_dossier_prompt
        """
        website_context = f" (website: {website_url})" if website_url else ""

        # Load prompt template from YAML
        accordion_prompts = self._load_accordion_prompts()
        prompt_template = accordion_prompts.get("research_dossier_prompt", "")

        if not prompt_template:
            # Fallback if YAML loading fails
            prompt_template = self._get_default_accordion_prompts()["research_dossier_prompt"]

        return prompt_template.format(
            company_name=company_name,
            website_context=website_context,
        )

    def _build_section_prompt(
        self,
        section: dict,
        company_name: str,
        research_dossier: str,
        previous_sections: list[dict[str, str]],
        stage1_context: str | None = None,
        section_index: int = 0,
        total_sections: int = 1,
    ) -> str:
        """
        Build prompt for writing a single section with full context continuity.

        Prompt template is loaded from company_overview.yaml accordion_method.section_writing_prompt
        Position guidance is loaded from accordion_method.position_guidance
        """
        # Load prompts from YAML
        accordion_prompts = self._load_accordion_prompts()
        position_guidance_templates = accordion_prompts.get("position_guidance", {})

        # Build previous section context (summaries, not full text)
        prev_context = "This is the first section."
        if previous_sections:
            prev_summaries = []
            for prev in previous_sections[-3:]:  # Last 3 sections for context
                # First 200 words as summary
                summary = " ".join(prev["content"].split()[:200])
                prev_summaries.append(f"**{prev['title']}** (excerpt): {summary}...")
            prev_context = "\n\n".join(prev_summaries)

        # Position guidance for narrative flow - use position from YAML
        position = section.get("position", "middle")
        position_guidance = position_guidance_templates.get(position, "")

        # Format position guidance with section numbers if needed
        if position == "middle" and "{section_number}" in position_guidance:
            position_guidance = position_guidance.format(
                section_number=section_index + 1,
                total_sections=total_sections,
            )

        # Include Stage 1 context if available (ground truth from website)
        stage1_section = ""
        if stage1_context:
            # Truncate Stage 1 context to key portions
            stage1_truncated = (
                stage1_context[:6000] if len(stage1_context) > 6000 else stage1_context
            )
            stage1_section = f"""## STAGE 1 RESEARCH (Website Analysis - Ground Truth)
This is verified information from the company's own website and public sources.
Prioritize this data when it conflicts with external research.

{stage1_truncated}

---
"""

        # Get section writing prompt template from YAML
        prompt_template = accordion_prompts.get("section_writing_prompt", "")

        if prompt_template:
            # Use YAML template with variable substitution
            return prompt_template.format(
                company_name=company_name,
                stage1_context=stage1_section,
                research_dossier=research_dossier[:8000],
                previous_sections=prev_context,
                section_title=section["title"],
                section_instructions=section["instructions"],
                position_guidance=position_guidance,
            )
        else:
            # Fallback to inline prompt if YAML loading fails
            return f"""You are writing a section of a strategic company overview for {company_name}.

{stage1_section}## RESEARCH DOSSIER (Deep Research Findings)
{research_dossier[:8000]}

## PREVIOUS SECTIONS
{prev_context}

## YOUR TASK
Write the **{section["title"]}** section with depth and analytical rigor.

Instructions:
{section["instructions"]}

## NARRATIVE GUIDANCE
{position_guidance}

Write the content for the **{section["title"]}** section now. Do NOT repeat the section
title as a heading - it will be added automatically. Do NOT start with a heading that
matches or closely resembles the section title. Start directly with the content or
use a descriptive subtitle if needed."""

    def _extract_industry_from_context(self, stage1_context: str | None) -> str | None:
        """Extract Industry from Stage 1 context if present."""
        if not stage1_context:
            return None


        # Look for "## Industry" section in the context
        match = re.search(
            r"##\s*Industry\s*\n+(.+?)(?=\n##|\n---|\Z)", stage1_context, re.IGNORECASE | re.DOTALL
        )
        if match:
            industry = match.group(1).strip()
            # Clean up - take first line if multi-line
            industry = industry.split("\n")[0].strip()
            if industry and len(industry) < 200:  # Sanity check
                return industry
        return None

    def _extract_full_company_name(self, stage1_context: str | None) -> str | None:
        """Extract full legal company name from Stage 1 context if present."""
        if not stage1_context:
            return None


        # Look for "## Company Name" section in the context
        match = re.search(
            r"##\s*Company\s*Name\s*\n+(.+?)(?=\n##|\n---|\Z)",
            stage1_context,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            full_name = match.group(1).strip()
            # Clean up - take first line if multi-line
            full_name = full_name.split("\n")[0].strip()
            if full_name and len(full_name) < 200:  # Sanity check
                return full_name
        return None

    def _assemble_report(
        self,
        company_name: str,
        website_url: str | None,
        sections: list[dict[str, str]],
        industry: str | None = None,
        full_company_name: str | None = None,
    ) -> str:
        """
        Assemble written sections into final report.

        Format: Clean, modern header with metadata, then sections.
        No table of contents (clutters the document).

        Args:
            company_name: User-provided name (used in title)
            website_url: Company website
            sections: Written section content
            industry: Industry classification from Stage 1
            full_company_name: Full legal name from Stage 1 (e.g., "Bank of Hawaii Corporation")
        """
        from datetime import datetime

        current_date = datetime.now().strftime("%B %Y")

        # Use full legal name if available, otherwise user-provided name
        display_name = full_company_name or company_name

        # Clean header - modern format, not 90s Word template
        lines = [
            f"# Strategic Company Overview: {company_name}",  # Title uses user input
            "",
            f"*{current_date}*",
            "",
            f"**Company Name:** {display_name}",  # Metadata uses full legal name
            "",
        ]

        # Website
        if website_url:
            lines.extend(
                [
                    f"**Website:** {website_url}",
                    "",
                ]
            )

        # Industry (from Stage 1 analysis)
        if industry:
            lines.extend(
                [
                    f"**Industry:** {industry}",
                    "",
                ]
            )

        # Sections - clean flow, no horizontal rules between every section
        for i, section in enumerate(sections):
            lines.append(f"## {section['title']}")
            lines.append("")
            lines.append(section["content"])
            lines.append("")
            # Only add separator between major parts (every 4-5 sections)
            if i > 0 and (i + 1) % 5 == 0 and i < len(sections) - 1:
                lines.append("---")
                lines.append("")

        return "\n".join(lines)

    async def _execute_followup(
        self,
        previous_interaction_id: str,
        prompt: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> ResearchResult:
        """
        Execute a follow-up interaction using previous_interaction_id.

        This uses the Gemini 3 Pro model (not Deep Research agent) for
        follow-up elaboration, which is faster and doesn't hit the same
        rate limits as the Deep Research agent.

        Per the Gemini docs:
        "You can continue the conversation after the agent returns the final
        report by using the previous_interaction_id. This lets you ask for
        clarification, summarization or elaboration on specific sections of
        the research without restarting the entire task."

        Args:
            previous_interaction_id: ID from the initial Deep Research call
            prompt: The elaboration prompt
            on_progress: Optional progress callback

        Returns:
            ResearchResult with elaborated content
        """
        self._api_call_count += 1
        start_time = time.time()

        try:
            logger.debug(
                f"Follow-up call with previous_interaction_id: {previous_interaction_id[:20]}..."
            )

            # Use Pro model for follow-up (faster, no Deep Research rate limits)
            # The previous_interaction_id provides context from the original research
            from primr.config.models import PrimrModels

            interaction = self._client.interactions.create(
                input=prompt,
                model=PrimrModels.PRO_MODEL,
                previous_interaction_id=previous_interaction_id,
            )

            # Extract content - handle multiple output formats
            content = ""
            if hasattr(interaction, "outputs") and interaction.outputs:
                # Concatenate all text outputs
                text_parts = []
                for output in interaction.outputs:
                    if hasattr(output, "text") and output.text:
                        text_parts.append(str(output.text))
                content = "\n".join(text_parts)

            duration = time.time() - start_time
            word_count = len(content.split()) if content else 0

            logger.info(f"Follow-up completed: {word_count} words in {duration:.1f}s")

            if not content:
                logger.warning("Follow-up returned empty content")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error="Empty response from follow-up call",
                )

            return ResearchResult(
                content=content,
                citations=[],
                interaction_id=interaction.id if hasattr(interaction, "id") else "",
                duration_seconds=duration,
                status=ResearchStatus.COMPLETED,
            )

        except Exception as e:
            error_str = str(e).lower()
            duration = time.time() - start_time

            # Check for specific error types
            if "429" in error_str or "quota" in error_str or "rate" in error_str:
                logger.warning(f"Follow-up rate limited: {e}")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error=f"Rate limited: {e}",
                    duration_seconds=duration,
                )
            elif "previous_interaction_id" in error_str or "invalid" in error_str:
                logger.warning(f"Follow-up interaction ID issue: {e}")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error=f"Interaction ID issue: {e}",
                    duration_seconds=duration,
                )
            else:
                logger.warning(f"Follow-up interaction failed: {e}")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error=str(e),
                    duration_seconds=duration,
                )

    async def _execute_direct_generation(
        self,
        prompt: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> ResearchResult:
        """
        Execute direct Gemini Pro generation (no interaction context).

        This is used as a fallback when Deep Research fails and we don't have
        a previous_interaction_id. Uses the same approach as the validated
        AccordionTestRunner: direct generate_content() calls.

        Args:
            prompt: The generation prompt
            on_progress: Optional progress callback

        Returns:
            ResearchResult with generated content
        """
        self._api_call_count += 1
        start_time = time.time()

        try:
            logger.debug("Direct Flash generation (fallback mode)...")

            # Use Flash model for direct generation (fast, intelligent)
            from primr.config.models import PrimrModels

            response = self._client.models.generate_content(
                model=PrimrModels.FLASH_MODEL,
                contents=prompt,
            )

            # Extract content
            content = ""
            if hasattr(response, "text") and response.text:
                content = response.text.strip()
            elif hasattr(response, "parts"):
                text_parts = []
                for part in response.parts:
                    if hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
                content = "\n".join(text_parts).strip()

            duration = time.time() - start_time
            word_count = len(content.split()) if content else 0

            logger.info(f"Direct generation completed: {word_count} words in {duration:.1f}s")

            if not content:
                logger.warning("Direct generation returned empty content")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error="Empty response from direct generation",
                )

            return ResearchResult(
                content=content,
                citations=[],
                interaction_id="",  # No interaction ID for direct calls
                duration_seconds=duration,
                status=ResearchStatus.COMPLETED,
            )

        except Exception as e:
            error_str = str(e).lower()
            duration = time.time() - start_time

            # Check for rate limiting
            if "429" in error_str or "quota" in error_str or "rate" in error_str:
                logger.warning(f"Direct generation rate limited: {e}")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error=f"Rate limited: {e}",
                    duration_seconds=duration,
                )
            else:
                logger.warning(f"Direct generation failed: {e}")
                return ResearchResult(
                    content="",
                    citations=[],
                    status=ResearchStatus.FAILED,
                    error=str(e),
                    duration_seconds=duration,
                )


# Singleton instance for DeepResearchOrchestrator
_orchestrator: DeepResearchOrchestrator | None = None
_orchestrator_lock = threading.Lock()


def get_deep_research_orchestrator() -> DeepResearchOrchestrator:
    """Get the global DeepResearchOrchestrator instance (thread-safe)."""
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = DeepResearchOrchestrator()
    return _orchestrator


# =============================================================================
# REPORT FORMATTER
# =============================================================================


@dataclass
class FormattedReport:
    """Formatted report ready for output."""

    markdown: str
    table_of_contents: str
    chapters: list[str]
    citations: list[dict[str, str]]
    company_name: str
    word_count: int

    @property
    def estimated_pages(self) -> int:
        """Estimate page count (assuming ~500 words per page)."""
        return max(1, self.word_count // 500)


class ReportFormatter:
    """
    Formats Deep Research output into clean report deliverables.

    Key responsibilities:
    - Generate clean Table of Contents (no ✓/✗ markers)
    - Apply consistent citation formatting
    - Remove any debug artifacts
    - Ensure no memo-style headers remain

    This formatter is designed for the single-call architecture where
    Deep Research generates a complete report in one invocation.
    """

    # Patterns that should NOT appear in output
    PROHIBITED_PATTERNS = [
        r"RESEARCH REQUEST:",
        r"^TO:\s*",
        r"^FROM:\s*",
        r"^SUBJECT:\s*",
        r"^DATE:\s*\w+\s+\d{4}",  # DATE: Month YYYY
        r"✓",  # Success marker
        r"✗",  # Failure marker
        r"\[DEBUG\]",
        r"\[ERROR\]",
        r"Traceback \(most recent call last\)",
    ]

    # Standard chapters for TOC generation
    STANDARD_CHAPTERS = [
        "Executive Summary",
        "Detailed Products and Services",
        "Unique Selling Proposition",
        "Mission and Vision",
        "Company History",
        "Key Achievements",
        "Target Audience",
        "Financial Overview",
        "Key Business Drivers and Strategic KPIs",
        "SWOT Analysis",
        "Leadership and Culture",
        "Industry Context and Dynamics",
        "Competitive Landscape",
        "Narrative Gap Analysis",
        "Potential Risks to Discuss",
        "Patterns and Questions",
        "Questions for Our First Conversation",
    ]

    def __init__(self):
        """Initialize the ReportFormatter."""

        self._prohibited_re = [re.compile(p, re.MULTILINE) for p in self.PROHIBITED_PATTERNS]

    def format_report(
        self,
        raw_content: str,
        company_name: str,
        citation_style: str = "numbered",
    ) -> FormattedReport:
        """
        Format raw Deep Research output into clean Markdown.

        Args:
            raw_content: Raw content from Deep Research
            company_name: Company name for header
            citation_style: Citation formatting style

        Returns:
            FormattedReport with clean content
        """

        # Clean the content
        content = self._remove_prohibited_patterns(raw_content)
        content = self._ensure_clean_header(content, company_name)

        # Extract chapters
        chapters = self._extract_chapters(content)

        # Generate clean TOC
        toc = self._generate_clean_toc(chapters)

        # Extract citations
        citations = self._extract_citations(content)

        # Resolve redirect URLs to final destinations (for trust/readability)
        if citations:
            logger.info(f"Resolving {len(citations)} citation URLs...")
            citations = resolve_citation_urls_sync(citations)
            logger.info("Citation URLs resolved")

        # Apply citation formatting (with resolved URLs)
        if citation_style == "numbered":
            content = self._format_numbered_citations(content, citations)

        # Calculate word count
        word_count = len(content.split())

        return FormattedReport(
            markdown=content,
            table_of_contents=toc,
            chapters=chapters,
            citations=citations,
            company_name=company_name,
            word_count=word_count,
        )

    def _remove_prohibited_patterns(self, content: str) -> str:
        """Remove prohibited patterns from content."""
        for pattern in self._prohibited_re:
            content = pattern.sub("", content)
        return content

    def _ensure_clean_header(self, content: str, company_name: str) -> str:
        """Ensure the document has a clean professional header."""

        # Check if content already has a clean header
        if content.strip().startswith(f"# Strategic Company Overview: {company_name}"):
            return content
        if content.strip().startswith("# Strategic Company Overview"):
            return content
        if content.strip().startswith(f"# AI Strategy: {company_name}"):
            return content

        # If no clean header, check for memo-style and replace
        memo_patterns = [
            r"^RESEARCH REQUEST:.*?\n",
            r"^DATE:.*?\n",
            r"^TO:.*?\n",
            r"^FROM:.*?\n",
            r"^SUBJECT:.*?\n",
        ]

        for pattern in memo_patterns:
            content = re.sub(pattern, "", content, flags=re.MULTILINE)

        return content.strip()

    def _extract_chapters(self, content: str) -> list[str]:
        """Extract chapter titles from content."""

        chapters = []
        # Match ## headers (level 2)
        pattern = r"^##\s+(.+?)$"
        for match in re.finditer(pattern, content, re.MULTILINE):
            title = match.group(1).strip()
            # Remove any numbering prefix like "1. " or "1) "
            title = re.sub(r"^\d+[\.\)]\s*", "", title)
            if title and title not in chapters:
                chapters.append(title)

        return chapters

    def _generate_clean_toc(self, chapters: list[str]) -> str:
        """Generate a clean Table of Contents without status markers."""

        lines = ["## Table of Contents\n"]

        for i, chapter in enumerate(chapters, 1):
            # Create anchor link
            anchor = chapter.lower().replace(" ", "-").replace("&", "and")
            anchor = re.sub(r"[^a-z0-9-]", "", anchor)

            # Clean TOC entry - NO status markers
            lines.append(f"{i}. [{chapter}](#{anchor})")

        return "\n".join(lines)

    def _extract_citations(self, content: str) -> list[dict[str, str]]:
        """Extract ALL citations from content (from all Sources sections)."""
        return extract_citations_from_content(
            content,
            all_sources_sections=True,
            dedupe_urls=True,
        )

    def _format_numbered_citations(self, content: str, citations: list[dict[str, str]]) -> str:
        """Apply numbered citation formatting with clickable links and resolved URLs."""
        from urllib.parse import urlparse

        if not citations:
            return content

        # Convert inline [cite: X, Y, Z] references to clean [1] [2] [3] format
        def replace_cite_ref(match: re.Match) -> str:
            nums_str = match.group(1)
            nums = [n.strip() for n in nums_str.split(",")]
            refs = [f"[{num}]" for num in nums]
            return " ".join(refs)

        content = re.sub(r"\[cite:\s*([\d,\s]+)\]", replace_cite_ref, content)

        # REMOVE all inline **Sources:** blocks - we'll add ONE consolidated section at the end
        # This makes the document much more readable
        # Pattern 1: **Sources:** followed by numbered markdown links
        sources_pattern = r"\n*\*\*Sources:\*\*\s*(?:\d+\.\s*\[[^\]]+\]\([^)]+\)\s*)+"
        content = re.sub(sources_pattern, "", content)

        # Pattern 2: **Sources:** followed by just [1] [2] [3] style refs
        sources_refs_pattern = r"\n*\*\*Sources:\*\*\s*(?:\[\d+\]\s*)+"
        content = re.sub(sources_refs_pattern, "", content)

        # Remove standalone lines that are just citation references like "[1] [2] [3]"
        content = re.sub(r"\n\s*(?:\[\d+\]\s*)+\s*\n", "\n\n", content)

        # Clean up multiple blank lines
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Move KEY METRICS to after Executive Summary (if it exists at the end)
        content = self._relocate_key_metrics(content)

        # Build consolidated References section at the very end
        if citations:
            # Deduplicate and renumber citations
            seen_urls: dict[str, dict] = {}
            for citation in citations:
                url = citation.get("url", "")
                if url and url not in seen_urls:
                    seen_urls[url] = citation

            # Build clean references list
            ref_lines = ["\n\n---\n\n## References\n"]
            for i, citation in enumerate(seen_urls.values(), 1):
                url = citation.get("url", "")
                title = citation.get("title", "")

                if url:
                    # Check if URL is still an unresolved redirect
                    if "vertexaisearch.cloud.google.com/grounding-api-redirect" in url:
                        # Show just the title/domain without the broken link
                        display_text = (
                            title if title and "vertexaisearch" not in title.lower() else "Source"
                        )
                        ref_lines.append(f"{i}. {display_text} (link unavailable)")
                    else:
                        parsed = urlparse(url)
                        domain = parsed.netloc.replace("www.", "")
                        # Use domain as display text if title looks like a redirect URL
                        if "vertexaisearch" in title.lower() or not title:
                            display_text = domain
                        else:
                            display_text = title
                        ref_lines.append(f"{i}. [{display_text}]({url})")
                elif title:
                    ref_lines.append(f"{i}. {title}")

            content = content.rstrip() + "\n".join(ref_lines)

        return content

    def _relocate_key_metrics(self, content: str) -> str:
        """Move KEY METRICS section to after Executive Summary for better readability."""

        # Find KEY METRICS block (usually at the end)
        # Pattern: **KEY METRICS:** followed by bullet points until next section or end
        metrics_pattern = r"\n*\*\*KEY METRICS:\*\*\s*((?:[-*]\s*[^\n]+\n?)+)"
        metrics_match = re.search(metrics_pattern, content, re.IGNORECASE)

        if not metrics_match:
            return content

        # Extract the metrics block
        metrics_block = metrics_match.group(0).strip()

        # Remove it from original location
        content = re.sub(metrics_pattern, "", content, flags=re.IGNORECASE)

        # Find the end of Executive Summary section
        # Look for the next ## header after Executive Summary
        exec_summary_end = re.search(
            r"(## Executive Summary.*?)(\n## )", content, re.DOTALL | re.IGNORECASE
        )

        if exec_summary_end:
            # Insert metrics after Executive Summary, before next section
            insert_pos = exec_summary_end.end(1)
            content = content[:insert_pos] + "\n\n" + metrics_block + "\n" + content[insert_pos:]

        return content

    def has_failure_markers(self, content: str) -> bool:
        """Check if content contains failure markers."""
        return "✗" in content or "✓" in content

    def has_memo_headers(self, content: str) -> bool:
        """Check if content contains memo-style headers."""

        memo_patterns = [
            r"RESEARCH REQUEST:",
            r"^TO:\s*",
            r"^FROM:\s*",
            r"^SUBJECT:\s*",
        ]
        return any(re.search(pattern, content, re.MULTILINE) for pattern in memo_patterns)

    def has_debug_artifacts(self, content: str) -> bool:
        """Check if content contains debug artifacts."""
        debug_patterns = [
            "[DEBUG]",
            "[ERROR]",
            "Traceback (most recent call last)",
            "Exception:",
        ]
        return any(pattern in content for pattern in debug_patterns)

    def count_chapters(self, content: str) -> int:
        """Count the number of chapters in content."""
        return len(self._extract_chapters(content))


# =============================================================================
# FILE SEARCH STORE MANAGER
# =============================================================================


class FileSearchStoreManager:
    """
    Manages File Search Store lifecycle for Deep Research context.

    Handles creation, upload, and cleanup of temporary stores used to provide
    context to Deep Research API calls. Ensures proper cleanup to avoid
    orphaned stores and data governance issues.

    Usage:
        manager = FileSearchStoreManager()
        store_name = manager.create_store("company_research")
        manager.upload_context(store_name, content, "research.txt")
        # ... use store in Deep Research ...
        manager.delete_store(store_name)  # Always cleanup!
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize the FileSearchStoreManager.

        Args:
            api_key: Optional API key override. Uses settings if not provided.
        """
        _require_genai_dependency()
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        logger.debug("FileSearchStoreManager initialized")

    def create_store(self, display_name: str) -> str:
        """
        Create a new File Search Store.

        Args:
            display_name: Human-readable name for the store

        Returns:
            Store name (ID) for use in subsequent operations

        Raises:
            AIError: If store creation fails
        """
        try:
            # ``primr-`` prefix is load-bearing for cleanup_orphaned_resources:
            # without it, post-run cleanup would refuse to delete this store
            # and the operator would accumulate paying-for-nothing artifacts.
            store = self._client.file_search_stores.create(
                config={"display_name": f"primr-{display_name}_{int(time.time())}"}
            )
            store_name: str = store.name or ""
            if not store_name:
                raise AIError(
                    "Failed to create file store - no name returned", model="file_search_store"
                )
            logger.info(f"Created File Search Store: {store_name}")
            return store_name
        except AIError:
            raise
        except Exception as e:
            raise AIError(
                f"Failed to create File Search Store: {e}", model="file_search_store", cause=e
            ) from e

    def upload_context(
        self, store_name: str, content: str, filename: str, mime_type: str = "text/plain"
    ) -> None:
        """
        Upload text content to a File Search Store.

        Args:
            store_name: Store name from create_store()
            content: Text content to upload
            filename: Name for the uploaded file
            mime_type: MIME type of the content

        Raises:
            AIError: If upload fails
        """
        import tempfile

        # Write content to temp file for upload
        fd, temp_path = tempfile.mkstemp(suffix=f"_{filename}")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            self._client.file_search_stores.upload_to_file_search_store(
                file=temp_path,
                file_search_store_name=store_name,
                config={"mime_type": mime_type},  # type: ignore[arg-type]
            )
            logger.info(f"Uploaded {filename} to store {store_name}")
        except Exception as e:
            raise AIError(
                f"Failed to upload context to store: {e}", model="file_search_store", cause=e
            ) from e
        finally:
            # Clean up temp file
            with contextlib.suppress(OSError):
                os.unlink(temp_path)

    def upload_file(self, store_name: str, file_path: str) -> None:
        """
        Upload a file to a File Search Store.

        Args:
            store_name: Store name from create_store()
            file_path: Path to file to upload

        Raises:
            AIError: If upload fails
        """

        if not os.path.exists(file_path):
            raise AIError(f"File not found: {file_path}", model="file_search_store")

        # MIME type mapping
        mime_types = {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".json": "application/json",
            ".csv": "text/csv",
            ".pdf": "application/pdf",
        }

        ext = os.path.splitext(file_path)[1].lower()
        mime_type = mime_types.get(ext)
        config = {"mime_type": mime_type} if mime_type else None

        try:
            self._client.file_search_stores.upload_to_file_search_store(
                file=file_path,
                file_search_store_name=store_name,
                config=config,  # type: ignore[arg-type]
            )
            logger.info(f"Uploaded {file_path} to store {store_name}")
        except Exception as e:
            raise AIError(
                f"Failed to upload {file_path}: {e}", model="file_search_store", cause=e
            ) from e

    def delete_store(self, store_name: str) -> None:
        """
        Delete a File Search Store and all its contents.

        Should be called after Deep Research completes (success or failure)
        to clean up temporary context and ensure data governance.

        IMPORTANT: Per Gemini docs, "There is no TTL for embeddings and files;
        they persist until manually deleted." We MUST delete documents first,
        then the store.

        Args:
            store_name: Store name to delete
        """
        # Step 1: Delete all documents inside the store first
        try:
            docs = list(self._client.file_search_stores.documents.list(parent=store_name))
            for doc in docs:
                try:
                    # Try with config for force delete (deletes chunks too)
                    self._client.file_search_stores.documents.delete(
                        name=doc.name, config={"force": True}
                    )
                except TypeError:
                    # SDK doesn't support config, try without
                    self._client.file_search_stores.documents.delete(name=doc.name)
            if docs:
                logger.debug(f"Deleted {len(docs)} document(s) from {store_name}")
        except Exception as e:
            logger.warning(f"Could not delete documents from {store_name}: {e}")

        # Step 2: Now delete the empty store
        try:
            self._client.file_search_stores.delete(name=store_name)
            logger.info(f"Deleted File Search Store: {store_name}")
        except Exception as e:
            error_str = str(e).lower()
            if "failed_precondition" in error_str or "non-empty" in error_str:
                # This shouldn't happen after deleting docs, but log it loudly
                logger.error(
                    f"CLEANUP FAILED: Store {store_name} still not empty after doc deletion!"
                )
            else:
                logger.warning(f"Could not delete File Search Store {store_name}: {e}")


# Singleton instance for FileSearchStoreManager
_store_manager: FileSearchStoreManager | None = None
_store_manager_lock = threading.Lock()


def get_file_search_store_manager() -> FileSearchStoreManager:
    """Get the global FileSearchStoreManager instance (thread-safe)."""
    global _store_manager
    if _store_manager is None:
        with _store_manager_lock:
            if _store_manager is None:
                _store_manager = FileSearchStoreManager()
    return _store_manager


# =============================================================================
# ORPHANED RESOURCE CLEANUP
# =============================================================================


# Don't touch stores younger than this — they may belong to a concurrent
# Primr run on the same API key. Configurable via env for operators who
# want a tighter or looser window.

_client: DeepResearchClient | None = None
_client_lock = threading.Lock()


def get_deep_research_client() -> DeepResearchClient:
    """
    Get the global Deep Research client instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety
    while minimizing lock contention.
    """
    global _client
    if _client is None:
        with _client_lock:
            # Double-check after acquiring lock
            if _client is None:
                _client = DeepResearchClient()
    return _client


def reset_deep_research_client() -> None:
    """Reset the global client (useful for testing)."""
    global _client
    with _client_lock:
        _client = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def deep_research(
    query: str,
    output_format: str | None = None,
    priority_urls: list[str] | None = None,
    **kwargs: Any,
) -> ResearchResult:
    """
    Convenience function for deep research.

    Args:
        query: The research query
        output_format: Optional format (company_profile, executive_summary, etc.)
        priority_urls: Optional list of URLs to prioritize as sources
        **kwargs: Additional arguments passed to research()

    Returns:
        ResearchResult
    """
    client = get_deep_research_client()
    return await client.research(
        query, output_format=output_format, priority_urls=priority_urls, **kwargs
    )


async def research_company(
    company_name: str, website: str | None = None, **kwargs: Any
) -> ResearchResult:
    """
    Research a company using Deep Research Agent.

    Args:
        company_name: Name of the company
        website: Optional company website URL (used as priority source)
        **kwargs: Additional arguments

    Returns:
        ResearchResult with structured company profile
    """
    query = f"Research {company_name}"
    if website:
        query += f" ({website})"

    # Pass website as priority URL for URL Context
    priority_urls = [website] if website else None

    return await deep_research(
        query, output_format="company_profile", priority_urls=priority_urls, **kwargs
    )
