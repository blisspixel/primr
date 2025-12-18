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
    result = await client.research("Research Tesla's competitive position")

    # Or with streaming progress
    async for update in client.research_stream("Research Tesla"):
        print(update)
"""

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import google.genai.client as _genai_client
from google import genai

# Acknowledge experimental API - we know it may change, disable the warning
# This is the SDK's own mechanism for one-time warnings
_genai_client._interactions_experimental_warned = True

from primr.config.settings import get_settings
from primr.utils.errors import AIError
from primr.utils.logging_config import get_logger

logger = get_logger("ai.deep_research")


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
            ""
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

    @property
    def success(self) -> bool:
        """Check if research completed successfully."""
        return self.status == ResearchStatus.COMPLETED and bool(self.content)

    def save_thinking_log(self, filepath: str) -> None:
        """Save the thinking log to a file."""
        if self.thinking_log:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.thinking_log.to_markdown())


# =============================================================================
# JOB TRACKING - Save/load interaction IDs for recovery
# =============================================================================

import json
import os


def _get_jobs_file_path() -> str:
    """Get path to the jobs tracking file."""
    from primr.config.config import LOGS_DIR
    return os.path.join(LOGS_DIR, "pending_research_jobs.json")


def save_pending_job(interaction_id: str, job_type: str, description: str) -> None:
    """
    Save a pending research job for later recovery.

    Args:
        interaction_id: The Gemini interaction ID
        job_type: Type of job (e.g., "vendor_research", "company_research", "ai_strategy")
        description: Human-readable description
    """
    jobs_file = _get_jobs_file_path()

    # Load existing jobs
    jobs = {}
    if os.path.exists(jobs_file):
        try:
            with open(jobs_file, encoding='utf-8') as f:
                jobs = json.load(f)
        except (OSError, json.JSONDecodeError):
            jobs = {}

    # Add new job
    jobs[interaction_id] = {
        "type": job_type,
        "description": description,
        "started": datetime.now().isoformat(),
        "status": "pending"
    }

    # Save
    os.makedirs(os.path.dirname(jobs_file), exist_ok=True)
    with open(jobs_file, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2)

    logger.info(f"Saved pending job: {interaction_id} ({job_type})")


def remove_pending_job(interaction_id: str) -> None:
    """Remove a job from the pending list (after completion or failure)."""
    jobs_file = _get_jobs_file_path()

    if not os.path.exists(jobs_file):
        return

    try:
        with open(jobs_file, encoding='utf-8') as f:
            jobs = json.load(f)

        if interaction_id in jobs:
            del jobs[interaction_id]
            with open(jobs_file, 'w', encoding='utf-8') as f:
                json.dump(jobs, f, indent=2)
            logger.info(f"Removed completed job: {interaction_id}")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to remove job {interaction_id}: {e}")


def get_pending_jobs() -> dict[str, dict[str, Any]]:
    """Get all pending research jobs."""
    jobs_file = _get_jobs_file_path()

    if not os.path.exists(jobs_file):
        return {}

    try:
        with open(jobs_file, encoding='utf-8') as f:
            result: dict[str, dict[str, Any]] = json.load(f)
            return result
    except (OSError, json.JSONDecodeError):
        return {}


# =============================================================================
# URL RESOLUTION - Resolve Google redirect URLs to final destinations
# =============================================================================

async def resolve_redirect_url(url: str, timeout: float = 5.0) -> str:
    """
    Resolve a Google grounding redirect URL to its final destination.
    
    The Deep Research API returns URLs like:
    https://vertexaisearch.cloud.google.com/grounding-api-redirect/...
    
    This function follows the redirect chain to get the actual source URL.
    
    Args:
        url: The redirect URL to resolve
        timeout: Maximum time to wait for resolution (seconds)
        
    Returns:
        The final destination URL, or the original URL if resolution fails
    """
    import httpx
    
    # Only resolve Google grounding redirect URLs
    if "vertexaisearch.cloud.google.com/grounding-api-redirect" not in url:
        return url
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            # Use HEAD request to follow redirects without downloading content
            response = await client.head(url)
            # Return the final URL after all redirects
            final_url = str(response.url)
            logger.debug(f"Resolved URL: {url[:50]}... -> {final_url[:80]}...")
            return final_url
    except asyncio.TimeoutError:
        logger.warning(f"URL resolution timed out: {url[:50]}...")
        return url
    except Exception as e:
        logger.warning(f"URL resolution failed: {e}")
        return url


async def resolve_citation_urls(citations: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Resolve all citation URLs in parallel.
    
    Args:
        citations: List of citation dicts with 'url' keys
        
    Returns:
        Updated citations with resolved URLs
    """
    if not citations:
        return citations
    
    # Create tasks for all URL resolutions
    tasks = [resolve_redirect_url(c.get('url', '')) for c in citations]
    
    # Run all resolutions in parallel
    resolved_urls = await asyncio.gather(*tasks)
    
    # Update citations with resolved URLs
    for citation, resolved_url in zip(citations, resolved_urls):
        if resolved_url:
            citation['url'] = resolved_url
    
    return citations


def resolve_citation_urls_sync(citations: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Synchronous wrapper for resolve_citation_urls.
    
    Uses asyncio.run() or gets the existing event loop.
    """
    if not citations:
        return citations
    
    try:
        # Try to get existing event loop
        loop = asyncio.get_running_loop()
        # If we're already in an async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run, 
                resolve_citation_urls(citations)
            )
            return future.result(timeout=30)
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(resolve_citation_urls(citations))


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
            "Research the competitive landscape of EV batteries"
        )
        print(result.content)

        # With custom format
        result = await client.research(
            "Research Tesla",
            output_format="executive_summary"
        )
    """

    # Agent identifier for Deep Research
    AGENT_ID = "deep-research-pro-preview-12-2025"

    # Default polling interval (seconds) - used as base, actual interval is adaptive
    DEFAULT_POLL_INTERVAL = 10

    # Maximum research time (seconds) - API limit is 60 minutes
    MAX_RESEARCH_TIME = 3600

    # Adaptive polling thresholds (seconds)
    POLL_FAST_THRESHOLD = 60      # First 60s: poll every 5s
    POLL_NORMAL_THRESHOLD = 300   # 60-300s: poll every 10s
    # After 300s: poll every 20s

    def __init__(self, api_key: str | None = None):
        """
        Initialize the Deep Research client.

        Args:
            api_key: Optional API key override. Uses settings if not provided.
        """
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
    ) -> ResearchResult:
        """
        Execute a deep research task.

        This method starts a research task and polls for completion.
        Research tasks typically take 5-20 minutes.

        Args:
            query: The research query/prompt
            output_format: Optional format hint (e.g., "executive_summary")
            poll_interval: Seconds between status checks
            timeout: Maximum time to wait for completion
            on_progress: Optional callback for progress updates
            priority_urls: Optional list of URLs to prioritize (e.g., company website)
            context_files: Optional list of file paths to upload as context (PDFs, docs)

        Returns:
            ResearchResult with content and citations

        Raises:
            AIError: If research fails or times out
        """
        # =================================================================
        # PRE-FLIGHT VALIDATION - Check EVERYTHING before expensive API call
        # =================================================================

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
                        with open(f, 'rb') as test_file:
                            test_file.read(1)  # Just read 1 byte to verify access
                    except Exception as e:
                        preflight_errors.append(f"Cannot read context file {f}: {e}")

        # 4. Validate priority URLs format
        if priority_urls:
            for url in priority_urls:
                if not url.startswith(('http://', 'https://')):
                    preflight_errors.append(f"Invalid URL format: {url}")

        # FAIL FAST if any validation errors
        if preflight_errors:
            error_msg = "Pre-flight validation failed:\n  - " + "\n  - ".join(preflight_errors)
            logger.error(error_msg)
            raise AIError(error_msg, model=self.AGENT_ID)

        # 5. Test API connectivity with a lightweight call before expensive operations
        try:
            # Verify we can reach the API (this is cheap)
            _ = self._client.models.get(model="gemini-2.0-flash")
            logger.info("Pre-flight: API connectivity verified")
        except Exception as e:
            raise AIError(f"Pre-flight: API connectivity check failed: {e}", model=self.AGENT_ID) from e

        # 6. Upload context files BEFORE starting research
        # This is a separate API call - if it fails, we haven't started the expensive research yet
        file_store_name = None
        if context_files:
            file_store_name = self._upload_context_files(context_files)
            logger.info(f"Pre-flight: {len(context_files)} context files uploaded to {file_store_name}")

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
            logger.info(f"Starting deep research: {query[:100]}...")
            interaction = self._start_research(prompt, file_store_name=file_store_name)
            interaction_id = interaction.id
            logger.info(f"Research started: {interaction_id}")

            # Save job for recovery if process is interrupted
            save_pending_job(
                interaction_id=interaction_id,
                job_type="deep_research",
                description=query[:200]
            )

            if on_progress:
                on_progress(ResearchProgress(
                    status=ResearchStatus.IN_PROGRESS,
                    message="Research submitted to API"
                ))

            # Poll for completion
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise AIError(
                        f"Research timed out after {elapsed:.0f}s",
                        model=self.AGENT_ID
                    )

                # Check status
                interaction = self._get_interaction(interaction_id)
                status = interaction.status

                if status == "completed":
                    content = self._extract_content(interaction)
                    citations = self._extract_citations(interaction)

                    result = ResearchResult(
                        content=content,
                        citations=citations,
                        interaction_id=interaction_id,
                        duration_seconds=time.time() - start_time,
                        status=ResearchStatus.COMPLETED
                    )

                    # Remove from pending jobs
                    remove_pending_job(interaction_id)

                    logger.info(
                        f"Research completed in {result.duration_seconds:.0f}s"
                    )
                    return result

                elif status == "failed":
                    error_msg = getattr(interaction, 'error', 'Unknown error')
                    logger.error(f"Research failed: {error_msg}")

                    # Remove from pending jobs
                    remove_pending_job(interaction_id)

                    return ResearchResult(
                        content="",
                        interaction_id=interaction_id,
                        duration_seconds=time.time() - start_time,
                        status=ResearchStatus.FAILED,
                        error=str(error_msg)
                    )

                # Still in progress - show phase changes and periodic updates
                if on_progress:
                    # Determine current phase based on elapsed time
                    if elapsed < 60:
                        phase = "Initializing"
                    elif elapsed < 180:
                        phase = "Searching sources"
                    elif elapsed < 360:
                        phase = "Analyzing findings"
                    elif elapsed < 600:
                        phase = "Generating report"
                    else:
                        phase = "Finalizing"

                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

                    # Show progress on phase change OR every 30 seconds for reassurance
                    phase_changed = not hasattr(self, '_last_phase') or self._last_phase != phase
                    time_for_update = (elapsed - getattr(self, '_last_progress_time', 0)) >= 30

                    if phase_changed or time_for_update:
                        self._last_phase = phase
                        self._last_progress_time = elapsed

                        # Add activity indicator for long waits
                        if time_for_update and not phase_changed:
                            message = f". {phase} ({time_str})"
                        else:
                            message = f"{phase} ({time_str})"

                        on_progress(ResearchProgress(
                            status=ResearchStatus.IN_PROGRESS,
                            message=message
                        ))

                # Use adaptive polling interval
                current_interval = self._get_poll_interval(elapsed)
                logger.debug(f"Polling in {current_interval}s (elapsed: {elapsed:.0f}s)")
                await asyncio.sleep(current_interval)

        except Exception as e:
            logger.error(f"Deep research error: {e}")
            raise AIError(
                f"Deep research failed: {e}",
                model=self.AGENT_ID,
                cause=e
            ) from e

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
            async for progress in client.research_stream("Research Tesla"):
                if progress.thought:
                    print(f"Thinking: {progress.thought}")
                if progress.partial_result:
                    print(f"Result: {progress.partial_result}")
        """
        prompt = self._build_prompt(query, output_format)

        try:
            # Start streaming research
            stream = self._start_research_stream(prompt)

            interaction_id = None

            for chunk in stream:
                # Capture interaction ID
                if chunk.event_type == "interaction.start":
                    interaction_id = chunk.interaction.id
                    yield ResearchProgress(
                        status=ResearchStatus.IN_PROGRESS,
                        message=f"Research started: {interaction_id}"
                    )

                # Track event ID for reconnection
                if hasattr(chunk, 'event_id') and chunk.event_id:
                    pass

                # Handle content updates
                if chunk.event_type == "content.delta":
                    if hasattr(chunk.delta, 'type'):
                        if chunk.delta.type == "text":
                            yield ResearchProgress(
                                status=ResearchStatus.IN_PROGRESS,
                                partial_result=chunk.delta.text
                            )
                        elif chunk.delta.type == "thought_summary":
                            yield ResearchProgress(
                                status=ResearchStatus.IN_PROGRESS,
                                thought=chunk.delta.content.text
                            )

                # Handle completion
                if chunk.event_type == "interaction.complete":
                    yield ResearchProgress(
                        status=ResearchStatus.COMPLETED,
                        message="Research complete"
                    )
                    break

                # Handle errors
                if chunk.event_type == "error":
                    yield ResearchProgress(
                        status=ResearchStatus.FAILED,
                        message=f"Research failed: {chunk}"
                    )
                    break

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield ResearchProgress(
                status=ResearchStatus.FAILED,
                message=f"Stream error: {e}"
            )

    def _build_prompt(
        self,
        query: str,
        output_format: str | None = None
    ) -> str:
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

        Structure: Foundational sections first (know them), then strategic analysis (so what).
        """
        from datetime import datetime
        import re
        current_date = datetime.now().strftime("%B %d, %Y")

        # Extract company name from query for header
        # Query format: "Research CompanyName (https://...)" or "Research CompanyName"
        company_match = re.search(r'Research\s+(.+?)(?:\s*\(|$)', query)
        company_name = company_match.group(1).strip() if company_match else "Company"

        return f"""You are a senior strategy consultant preparing pre-meeting research. Generate a comprehensive company overview.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# Strategic Company Overview: {company_name}

**Prepared by:** Primr Research System  
**Date:** {current_date}

---

Then continue with the sections below.

=============================================================================
HARD REQUIREMENTS (Non-Negotiable)
=============================================================================

You MUST output EVERY section header listed below, in the exact order specified.
- Do NOT skip sections.
- Do NOT merge sections.
- Do NOT rename section headers.
- If information is not publicly available for a section, write: "Information not publicly available." Then list 2-3 specific questions we would want to validate in conversation with the client.

=============================================================================
RESEARCH INSTRUCTIONS
=============================================================================

{query}

FORMATTING RULES (follow these exactly):
- Write in full paragraphs unless bullets genuinely help clarity
- Keep bullets single-level only, no nested sub-bullets
- No em-dashes or en-dashes, use commas or periods instead
- Cite sources at the end of each major section, not inline

PURPOSE:
This is pre-meeting research to help consultants deeply understand the company before a discovery conversation. We are gathering publicly available information and forming initial hypotheses. We do NOT have the answers yet. The real insights will come from talking with the client directly. This document should:
- Prime consultants with solid foundational knowledge
- Surface interesting questions and hypotheses to explore
- Demonstrate we've done our homework without pretending we know their business better than they do

Subject-Positive Intent: We assume this company is rational, competent, and generally successful in its context. Our goal is not to critique from the outside, but to understand how they create value today and where thoughtful support could help them go further or move faster.

EPISTEMIC CONTRACT:
This document represents preliminary pattern recognition, not conclusions. Every strategic observation must be expressed as one of:
- A verified fact (with citation)
- An inference (clearly labeled as such)
- A hypothesis to validate in conversation
If a statement cannot be placed cleanly into one of these categories, rewrite it.

TONE AND EPISTEMIC HUMILITY (critical):
- This is research and initial thinking, not conclusions
- Frame strategic observations as "initial hypotheses to explore with the client"
- Use language like "based on public information", "appears to", "worth exploring", "we'd want to validate"
- Clearly distinguish between facts (what we found) and inferences (what we think it might mean)
- Avoid asserting causality or intent without evidence
- Never use absolutist language ("existential threat", "only viable path", "must do", "will definitely")
- Present questions to ask the client, not answers we're telling them
- For any strategic observation, frame it as "something to discuss" not "something we've concluded"
- Frame risks, gaps, or pressures in terms of where support, capability, or focus could unlock value, not as evidence of mismanagement or strategic error
- Do not imply leadership blind spots or strategic naivety unless directly supported by credible evidence. Prefer framing as tradeoffs, constraints, or decisions made under prior conditions.

TRANSFORMATION RULE:
If a sentence implies inevitability, failure, or urgency, rewrite it as a question or scenario comparison.
Example transformation:
- Instead of: "X faces an existential threat from Y"
- Write: "One risk worth exploring is whether Y could materially pressure X's margins over time"

The goal is to walk in informed and curious, not informed and arrogant. We want the client to think "they've done their homework and are asking smart questions" not "they think they already know our business."

KEY METRICS FORMAT (use these exact formats so we can extract them):
- Employees: X,XXX (or "Employees: ~X,XXX estimated")
- Revenue: $X.XB or $XXM (or "Revenue: ~$XXM estimated")
- Founded: YYYY
- Headquarters: City, State

Build this as a consultant-grade overview using publicly available sources (company site, press releases, earnings calls, news, trusted databases). If financials aren't public, use estimates and label them clearly (e.g., "Estimated ~$75M revenue per ZoomInfo").

CRITICAL: Follow this EXACT section order. Do not skip or reorder sections.

## Executive Summary
The "so what" up front. 2-3 paragraphs synthesizing the most critical findings. What does a decision-maker need to know in 60 seconds? Frame key strategic observations as hypotheses worth exploring.

Constraint: The Executive Summary may not introduce new conclusions that are not explored later as questions or hypotheses. The summary should reflect what the company appears to do well, what they seem to care most about, and 2-3 areas where we could likely help them create meaningful impact.

## Detailed Products and Services
What do they actually sell? Product lines, service offerings, how they make money, what customers are buying. This is the foundation for understanding their business.

## Unique Selling Proposition
What appears to differentiate them? Why might customers choose them over alternatives? What seems to be their moat?

## Mission and Vision
What do they say they stand for? What's their stated purpose and direction?

## Company History
Key milestones, founding story, major pivots, acquisitions. How did they get here?

## Key Achievements
Notable wins, awards, milestones, growth markers. What are they proud of?

## Target Audience
Who buys from them? Customer segments, industries served, geographic focus, typical buyer profile.

## Financial Overview
Revenue, growth trajectory, profitability indicators, funding history if private. Use estimates if needed and label them clearly. If truly unavailable, say so.

## Key Business Drivers and Strategic KPIs
What metrics likely matter most to this business? What appears to drive their success? What would their board probably be tracking?

## Strategic Tensions (Derived from SWOT)
Based on public information, use SWOT analysis (Strengths, Weaknesses, Opportunities, Threats) as inputs to identify 3-5 core strategic tensions the organization must actively manage. Frame these as persistent tradeoffs to navigate, not problems to solve.

Examples of tensions:
- Scale vs customization
- Speed vs governance
- Innovation vs operational reliability
- Growth vs profitability
- Centralization vs local autonomy

For each tension, describe:
- The tension: What two valuable things are in natural conflict?
- How they appear to be managing it: What signals suggest their current approach?
- Question to explore: What would we want to understand about their choices?

## Leadership and Culture
Key executives and their backgrounds. Leadership stability (tenure, recent departures). Board composition if relevant. Cultural signals from careers page, press releases, how they talk about their team.

## Industry Context and Dynamics
What's happening in their market? Growth trends, disruption factors, regulatory pressures. Where does the industry appear to be heading? What external forces may be shaping their world?

## Competitive Landscape
Who are the main competitors? How does this company appear to stack up based on public information? Where do they seem to win? Where might they face challenges? (To validate with them - they know their competitive dynamics better than we do.)

## Narrative Gap Analysis
Interesting contrasts we noticed between what the company says and external signals. These are observations to explore, not accusations:
- What they say vs. what external sources suggest
- Stated strategy vs. observable actions

Scenario Framing Requirement: Present gaps as:
- Base case: what happens if current trends persist
- Alternative case: what happens if mitigating factors exist
Do not present a single-path interpretation.

Format each as:
- Claim: [what they say]
- What we observed: [external signals]
- Base case: [if this gap persists]
- Alternative case: [if mitigating factors apply]
- Question to explore: [what we'd want to understand from them]

## Potential Risks to Discuss
Areas that caught our attention, prioritized by apparent severity:
- Competitive considerations
- Operational considerations
- Market/macro factors
- Leadership/execution factors

Scenario Framing Requirement: Risks must be framed as:
- Base case: what happens if current trends persist
- Alternative case: what happens if mitigating factors exist
Do not present a single-path interpretation. Frame as "areas we'd want to understand better" not definitive threats.

## Patterns and Questions
Interesting patterns we noticed. For each, what question does it raise?

Scenario Framing Requirement: Patterns must include:
- Base case interpretation
- Alternative interpretation
Do not present a single-path interpretation.

Format as:
- Observation: [what we found]
- Base case: [one interpretation]
- Alternative case: [another interpretation]
- Question for them: [what we'd want to understand]

Example:
- Observation: "They acquired two companies in 18 months"
- Base case: "Could indicate organic growth challenges requiring inorganic expansion"
- Alternative case: "Could reflect a deliberate market consolidation strategy from a position of strength"
- Question for them: "Can you help us understand the acquisition strategy? How is integration going?"

## Questions for Our First Conversation
The 3-5 most important things we want to understand from them. Based on our research, what are we most curious about? Frame as genuine questions, not conclusions.

=============================================================================
DOWNSTREAM TRANSLATION NOTE
=============================================================================
This output is intended to inform internal thinking and deck creation. When reused externally, conclusions should be softened, hypotheses foregrounded, and language reframed for diplomacy.
"""

    def _build_strategic_layer_prompt(self, query: str) -> str:
        """
        Build a prompt for Step 2 of the complete research pipeline.

        This adds strategic depth on top of the factual foundation from Step 1.
        The context files contain company overview, products, basic info.
        """
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")
        
        return f"""You are a senior strategy consultant adding strategic depth to initial research findings.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# Strategic Deep-Dive Analysis

**Prepared by:** Primr Research System  
**Date:** {current_date}

---

Then continue with the sections below.

=============================================================================
RESEARCH INSTRUCTIONS
=============================================================================

{query}

CONTEXT: You have access to initial research findings that cover the basics: company overview, products/services, history, and factual information. That foundation is already done. Do not repeat what's in the context files.

=============================================================================
HARD REQUIREMENTS (Non-Negotiable)
=============================================================================

You MUST output EVERY section header listed below, in the exact order specified.
- Do NOT skip sections.
- Do NOT merge sections.
- Do NOT rename section headers.
- If information is not publicly available for a section, write: "Information not publicly available." Then list 2-3 specific questions we would want to validate in conversation.

CRITICAL - SECTION BOUNDARIES:
- Do NOT output any sections from the Company Overview document.
- Do NOT include: Executive Summary, Detailed Products and Services, Unique Selling Proposition, Mission and Vision, Company History, Key Achievements, Target Audience, Financial Overview, Key Business Drivers and Strategic KPIs, or Leadership and Culture.
- Those sections belong to the Company Overview. This document is ONLY for strategic analysis.

PURPOSE:
This is the strategic analysis layer of our pre-meeting research. We are NOT providing answers or telling the client what to do. We are:
- Surfacing patterns and questions that warrant discussion
- Forming initial hypotheses based on public information
- Identifying areas where we'd want to dig deeper WITH the client
- Preparing smart questions to ask, not conclusions to deliver

The real strategic insights will come from the actual conversation with leadership. This document helps us walk in informed and curious, ready to explore these topics together.

FORMATTING RULES (follow these exactly):
- Write in full paragraphs unless bullets genuinely help clarity
- Keep bullets single-level only, no nested sub-bullets
- No em-dashes or en-dashes, use commas or periods instead
- Cite sources at the end of each section, not inline

TONE AND EPISTEMIC HUMILITY (critical):
- This is research and initial thinking, NOT conclusions
- Frame everything as "initial observations" and "hypotheses to explore with the client"
- Use language like "based on public sources", "appears to", "worth discussing", "we'd want to understand"
- Clearly separate facts (what we found) from inferences (what we think it might mean)
- Never assert causality or intent without evidence
- Avoid absolutist language ("existential threat", "only viable path", "must do", "will definitely")
- Present questions to explore, not answers we're delivering
- For any strategic observation: "This is worth discussing with leadership to understand [X]"

The goal is to demonstrate we've done thoughtful homework while being genuinely curious about their perspective. We want them to think "these consultants ask great questions" not "these consultants think they already know our business."

SECTION STRUCTURE:

## Narrative Gap Analysis
Compare what the company says about itself vs. external signals.
- Website claims vs. what customers/press actually say
- Stated strategy vs. observable actions and investments
- Financial claims vs. industry benchmarks

Format each gap as:
- Claim: [what they say]
- Evidence: [what external sources suggest]
- Hypothesis: [what this might mean, framed as something to validate]

## Competitive Deep-Dive
Go beyond listing competitors. Analyze the dynamics:
- Where does this company appear to win deals? Where might they lose?
- What seems to be their competitive moat (or potential lack thereof)?
- Who appears to be gaining ground? Who might be an emerging threat?
- Market share trends if available (note confidence level in data)

Frame competitive assessments as hypotheses: "Based on [evidence], we believe [hypothesis]. This would imply [implication]. Worth validating by [method]."

## Industry Dynamics & Pressures
What external forces appear to be shaping their world?
- Industry growth/contraction signals
- Regulatory changes on the horizon
- Technology disruption (AI, automation, platform shifts)
- Supply chain or talent pressures
- What might be keeping their leadership up at night?

## Strategic Assessment
SWOT framed as observations and questions to explore with the client:
- Strengths: What appears difficult to replicate? (to validate with them)
- Weaknesses: What potential gaps did we observe? (to discuss openly)
- Opportunities: What options seem worth exploring? (to prioritize together)
- Threats: What risks should we discuss? (to understand their perspective)

Frame as "based on our research, we'd want to discuss..." not "they are bad at X."

## Risk Analysis
Potential risks we observed, to discuss with leadership:
- Competitive risks
- Operational risks
- Market/macro risks
- Leadership/execution risks

Frame as "areas we'd want to understand better" not definitive threats. Note what's based on solid evidence vs. inference.

## Strategic Options to Explore
3-5 strategic directions worth discussing with the client. These are conversation starters, not recommendations:
- Quick wins: Lower-effort options that might be worth exploring
- Strategic bets: Bigger moves that could be transformational
- Defensive considerations: Risk areas that might warrant attention

For each option, note:
- Why it caught our attention (based on research)
- Questions we'd want to explore with them
- What we'd need to understand before forming a real recommendation

## Second-Order Insights
Patterns and questions that emerged from connecting the dots.
- What patterns did we notice?
- What questions do these patterns raise?
- What would we want to explore with leadership?

Format as:
- Observation: [what we found]
- Initial hypothesis: [what this might suggest]
- Question for the client: [what we'd want to understand from them]

Example:
- Observation: "They've had 3 CFOs in 4 years"
- Initial hypothesis: "This pattern might indicate strategic disagreement, operational challenges, or founder dynamics"
- Question for the client: "We noticed the CFO turnover. Can you help us understand what's been driving that? Is there context we're missing?"

## Questions for Discovery
The 3-5 most important questions to explore in our first conversation. Based on our research, what do we most want to understand from them? Frame as genuine curiosity, not gotcha questions.
"""

    def _upload_context_files(self, file_paths: list[str]) -> str:
        """
        Upload files to a File Search store for context.

        FAILS HARD on any error - do not proceed to expensive API call if upload fails.

        Args:
            file_paths: List of file paths to upload (PDFs, docs, etc.)

        Returns:
            File store name if successful

        Raises:
            AIError: If upload fails for any reason
        """
        import os

        # Validate files exist BEFORE any API calls
        missing_files = [f for f in file_paths if not os.path.exists(f)]
        if missing_files:
            raise AIError(
                f"Context files not found: {missing_files}",
                model=self.AGENT_ID
            )

        valid_files = [f for f in file_paths if os.path.exists(f)]
        if not valid_files:
            raise AIError(
                "No valid context files to upload",
                model=self.AGENT_ID
            )

        logger.info(f"Uploading {len(valid_files)} context file(s)...")

        # MIME type mapping for extensions the API doesn't auto-detect
        mime_types = {
            '.md': 'text/markdown',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.csv': 'text/csv',
            '.pdf': 'application/pdf',
        }

        try:
            # Create a file search store
            store = self._client.file_search_stores.create(
                config={"display_name": f"research_context_{int(time.time())}"}
            )
            store_name: str = store.name or ""
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
                        config=config  # type: ignore[arg-type]
                    )
                    logger.info(f"Uploaded: {file_path}")
                except Exception as upload_err:
                    # FAIL HARD - don't continue with broken uploads
                    raise AIError(
                        f"Failed to upload {file_path}: {upload_err}",
                        model=self.AGENT_ID,
                        cause=upload_err
                    ) from upload_err

            logger.info(f"All {len(valid_files)} files uploaded successfully")
            return store_name

        except AIError:
            raise  # Re-raise our errors
        except Exception as e:
            raise AIError(
                f"Failed to create file store: {e}",
                model=self.AGENT_ID,
                cause=e
            ) from e

    def _start_research(self, prompt: str, file_store_name: str | None = None) -> Any:
        """Start a background research task."""
        # Build tools list
        tools: list[dict[str, Any]] = []
        if file_store_name:
            tools.append({
                "type": "file_search",
                "file_search_store_names": [file_store_name]
            })

        create_kwargs: dict[str, Any] = {
            "input": prompt,
            "agent": self.AGENT_ID,
            "background": True
        }
        if tools:
            create_kwargs["tools"] = tools

        return self._client.interactions.create(**create_kwargs)

    def _start_research_stream(self, prompt: str) -> Any:
        """Start a streaming research task."""
        return self._client.interactions.create(
            input=prompt,
            agent=self.AGENT_ID,
            background=True,
            stream=True,
            agent_config={
                "type": "deep-research",
                "thinking_summaries": "auto"
            }
        )

    def _get_interaction(self, interaction_id: str) -> Any:
        """Get the current state of an interaction."""
        return self._client.interactions.get(interaction_id)

    def _extract_content(self, interaction: Any) -> str:
        """Extract the text content from a completed interaction."""
        if hasattr(interaction, 'outputs') and interaction.outputs:
            return str(interaction.outputs[-1].text)
        return ""

    def _extract_citations(self, interaction: Any) -> list[dict[str, str]]:
        """Extract citations from a completed interaction."""
        import re
        citations: list[dict[str, str]] = []

        # Get the content first
        content = self._extract_content(interaction)
        if not content:
            return citations

        # Look for Sources section at the end of the document
        # Format: 1. [domain.com](url)
        sources_match = re.search(r'\*\*Sources:\*\*\s*([\s\S]*?)$', content)
        if sources_match:
            sources_text = sources_match.group(1)
            # Extract numbered citations: 1. [text](url)
            citation_pattern = r'(\d+)\.\s*\[([^\]]+)\]\(([^)]+)\)'
            for match in re.finditer(citation_pattern, sources_text):
                citations.append({
                    'number': match.group(1),
                    'title': match.group(2),
                    'url': match.group(3)
                })

        # Also count inline citations like [cite: 1, 2, 3]
        if not citations:
            # Count unique citation numbers from inline refs
            inline_pattern = r'\[cite:\s*([\d,\s]+)\]'
            all_nums = set()
            for match in re.finditer(inline_pattern, content):
                nums = [n.strip() for n in match.group(1).split(',')]
                all_nums.update(nums)
            # Create placeholder citations for count
            for num in sorted(all_nums, key=lambda x: int(x) if x.isdigit() else 0):
                citations.append({'number': num, 'title': f'Source {num}', 'url': ''})

        return citations

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
        if elapsed_seconds < self.POLL_FAST_THRESHOLD:
            # First 60s: poll every 5s to catch quick completions
            return 5.0
        elif elapsed_seconds < self.POLL_NORMAL_THRESHOLD:
            # 60-300s: normal polling every 10s
            return 10.0
        else:
            # 300s+: slow polling every 20s for long-running research
            return 20.0

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
            status = interaction.status

            result = {
                "interaction_id": interaction_id,
                "status": status,
                "content": None,
                "error": None
            }

            if status == "completed":
                result["content"] = self._extract_content(interaction)
                result["citations"] = self._extract_citations(interaction)
                remove_pending_job(interaction_id)
            elif status == "failed":
                result["error"] = getattr(interaction, 'error', 'Unknown error')
                remove_pending_job(interaction_id)

            return result

        except Exception as e:
            return {
                "interaction_id": interaction_id,
                "status": "error",
                "content": None,
                "error": str(e)
            }


# =============================================================================
# CONSULTING PROMPT BUILDER
# =============================================================================


class ConsultingPromptBuilder:
    """
    Builds consulting-grade prompts for Deep Research.
    
    Creates comprehensive prompts that include:
    - Consulting persona injection ("Senior Strategy Consultant")
    - All 10 chapter specifications in a single prompt
    - Hierarchy of truth instructions
    - Formatting and epistemic standards
    
    This ensures Deep Research generates a complete, cohesive report
    in a single API call rather than multiple parallel calls.
    """
    
    # The 10 standard chapters for a Strategic Company Overview
    CHAPTERS = [
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
    ]
    
    def __init__(self):
        """Initialize the ConsultingPromptBuilder."""
        pass
    
    def build_comprehensive_prompt(
        self,
        company_name: str,
        website_url: str | None = None,
    ) -> str:
        """
        Build a single prompt requesting the complete 10-chapter report.
        
        Args:
            company_name: Name of the company to research
            website_url: Optional company website URL
            
        Returns:
            Complete prompt string for Deep Research
        """
        current_date = datetime.now().strftime("%B %d, %Y")
        
        website_context = f" ({website_url})" if website_url else ""
        priority_source = f"\n\nPriority Source: Analyze {website_url} first." if website_url else ""
        
        return f"""You are a senior strategy consultant preparing pre-meeting research. Generate a comprehensive company overview for {company_name}{website_context}.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# Strategic Company Overview: {company_name}

**Prepared by:** Primr Research System  
**Date:** {current_date}

---

Then continue with the sections below.

=============================================================================
RESEARCH INSTRUCTIONS
=============================================================================

Research {company_name}{website_context} and produce a comprehensive strategic overview.{priority_source}

{self._get_formatting_rules()}

{self._get_purpose_section()}

{self._get_epistemic_contract()}

{self._get_tone_guidelines()}

{self._get_key_metrics_format()}

{self._get_chapter_specifications(company_name)}

{self._get_downstream_note()}
"""
    
    def _get_formatting_rules(self) -> str:
        """Get the formatting rules section."""
        return """FORMATTING RULES (follow these exactly):
- Write in full paragraphs unless bullets genuinely help clarity
- Keep bullets single-level only, no nested sub-bullets
- No em-dashes or en-dashes, use commas or periods instead
- Cite sources at the end of each major section, not inline"""
    
    def _get_purpose_section(self) -> str:
        """Get the purpose section."""
        return """PURPOSE:
Pre-meeting research to deeply understand the company before discovery. We are forming initial hypotheses from public information. The real insights come from talking with the client.

This document should:
- Prime consultants with solid foundational knowledge
- Surface questions and hypotheses to explore
- Demonstrate homework without pretending we know their business better than they do

Subject-Positive Intent: Assume this company is rational, competent, and successful in its context. Understand how they create value and where support could help them go further."""
    
    def _get_epistemic_contract(self) -> str:
        """Get the epistemic contract section."""
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
        return f"""CRITICAL: Follow this EXACT section order. Do not skip or reorder sections.

## Executive Summary
The "so what" up front. 2-3 paragraphs synthesizing the most critical findings. What does a decision-maker need to know in 60 seconds? Frame key strategic observations as hypotheses worth exploring.

## Detailed Products and Services
What do they actually sell? Product lines, service offerings, how they make money, what customers are buying. This is the foundation for understanding their business.

## Unique Selling Proposition
What appears to differentiate them? Why might customers choose them over alternatives? What seems to be their moat?

## Mission and Vision
What do they say they stand for? What's their stated purpose and direction?

## Company History
Key milestones, founding story, major pivots, acquisitions. How did they get here?

## Key Achievements
Notable wins, awards, milestones, growth markers. What are they proud of?

## Target Audience
Who buys from them? Customer segments, industries served, geographic focus, typical buyer profile.

## Financial Overview
Revenue, growth trajectory, profitability indicators, funding history if private. Use estimates if needed and label them clearly. If truly unavailable, say so.

## Key Business Drivers and Strategic KPIs
What metrics likely matter most to this business? What appears to drive their success? What would their board probably be tracking?

## Strategic Tensions (Derived from SWOT)
Based on public information, use SWOT analysis (Strengths, Weaknesses, Opportunities, Threats) as inputs to identify 3-5 core strategic tensions the organization must actively manage. Frame these as persistent tradeoffs to navigate, not problems to solve.

Examples of tensions:
- Scale vs customization
- Speed vs governance
- Innovation vs operational reliability
- Growth vs profitability
- Centralization vs local autonomy

For each tension, describe:
- The tension: What two valuable things are in natural conflict?
- How they appear to be managing it: What signals suggest their current approach?
- Question to explore: What would we want to understand about their choices?

## Leadership and Culture
Key executives and their backgrounds. Leadership stability (tenure, recent departures). Board composition if relevant. Cultural signals from careers page, press releases, how they talk about their team.

## Industry Context and Dynamics
What's happening in their market? Growth trends, disruption factors, regulatory pressures. Where does the industry appear to be heading?

## Competitive Landscape
Who are the main competitors? How does {company_name} appear to stack up based on public information? Where do they seem to win? Where might they face challenges?

## Underlying Theory of Value Creation (Initial)
Articulate the implied logic of how {company_name} creates and captures value today. This is the business model made explicit.

Describe:
- The core value proposition: What problem do they solve, for whom, better than alternatives?
- Reinforcing mechanisms: What creates flywheel effects or compounding advantages?
- Key assumptions: What must remain true for this model to work?
- Vulnerabilities: Where could the logic break down?

Frame this as an initial theory to be tested in conversation, not a conclusion. The goal is to make the implicit logic explicit so we can have a more productive discussion about where support could strengthen or extend it.

## Strategic Constraints and Degrees of Freedom
Identify structural constraints that limit near-term change, and distinguish them from areas where leadership appears to have genuine degrees of freedom.

Constraints to consider:
- Organizational: Legacy systems, team capabilities, cultural inertia
- Regulatory: Compliance requirements, licensing, industry standards
- Asset-based: Physical infrastructure, contractual obligations, capital structure
- Market: Customer expectations, competitive dynamics, channel dependencies

Degrees of freedom to consider:
- Where do they appear to have flexibility?
- What decisions seem genuinely open?
- Where might small changes have outsized impact?

This prevents overconfident recommendations and signals realism about what's actually changeable.

## Narrative Gap Analysis
Interesting contrasts we noticed between what the company says and external signals. These are observations to explore, not accusations.

Format each as:
- Claim: [what they say]
- What we observed: [external signals]
- Question to explore: [what we'd want to understand from them]

## Areas of Structural Fragility
Identify areas where the business model may be sensitive to shocks, scale, or external change. Frame these as areas to understand more deeply rather than failures or criticisms.

For each fragility:
- The fragility: What aspect of the system appears sensitive?
- Why it matters: What could trigger stress or failure?
- What we'd want to understand: How are they thinking about this?

This is system awareness, not critique. Every business has fragilities; the question is whether they're understood and managed.

## Patterns and Questions
Interesting patterns we noticed. For each, what question does it raise?

Format as:
- Observation: [what we found]
- Question for them: [what we'd want to understand]

## Questions for Our First Conversation
The 3-5 most important things we want to understand from them. Based on our research, what are we most curious about? Frame as genuine questions, not conclusions."""
    
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
        for chapter in self.CHAPTERS:
            if chapter not in prompt:
                return False
        return True
    
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
    - Single API call per report (not parallel chapters)
    - Exponential backoff retry (60s base, 5 attempts max)
    - Adaptive polling (5s → 10s → 20s → 30s)
    - 60-minute timeout
    - Automatic File Search Store cleanup
    
    Usage:
        orchestrator = DeepResearchOrchestrator()
        result = await orchestrator.generate_report(
            company_name="Acme Corp",
            website_url="https://acme.com",
            stage1_context="... structured research from Stage 1 ...",
            on_progress=lambda msg: print(msg)
        )
    """
    
    AGENT_ID = "deep-research-pro-preview-12-2025"
    MAX_RETRIES = 5
    BASE_RETRY_DELAY = 60.0  # 1 minute base delay for exponential backoff
    TIMEOUT_SECONDS = 3600  # 60 minutes
    
    def __init__(self, api_key: str | None = None):
        """
        Initialize the DeepResearchOrchestrator.
        
        Args:
            api_key: Optional API key override. Uses settings if not provided.
        """
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        self._prompt_builder = ConsultingPromptBuilder()
        self._store_manager = FileSearchStoreManager(api_key=api_key)
        self._api_call_count = 0
        logger.debug("DeepResearchOrchestrator initialized")
    
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
            # Build the comprehensive prompt
            prompt = self._prompt_builder.build_comprehensive_prompt(
                company_name=company_name,
                website_url=website_url,
            )
            
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
                    mime_type="text/plain"
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
                
                # Check if it's a quota error (429)
                if "429" in error_str or "quota" in error_str or "rate" in error_str:
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self._calculate_backoff_delay(attempt)
                        logger.warning(
                            f"Quota limit hit, waiting {delay:.0f}s "
                            f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                        )
                        if on_progress:
                            on_progress(
                                f"Quota limit reached. Retrying in {delay:.0f}s "
                                f"(attempt {attempt + 1}/{self.MAX_RETRIES})..."
                            )
                        await asyncio.sleep(delay)
                        continue
                
                # Non-quota error, don't retry
                raise
        
        # All retries exhausted
        error_msg = (
            f"Deep Research quota exhausted after {self.MAX_RETRIES} attempts. "
            "Try --mode scrape instead."
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
        return self.BASE_RETRY_DELAY * (2 ** attempt)
    
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
            tools.append({
                "type": "file_search",
                "file_search_store_names": [store_name]
            })
        
        # Start the research
        create_kwargs: dict[str, Any] = {
            "input": prompt,
            "agent": self.AGENT_ID,
            "background": True
        }
        if tools:
            create_kwargs["tools"] = tools
        
        interaction = self._client.interactions.create(**create_kwargs)
        interaction_id = interaction.id
        logger.info(f"Deep Research started: {interaction_id}")
        
        if on_progress:
            on_progress(f"Research started (ID: {interaction_id[:8]}...)")
        
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
        
        Args:
            interaction_id: The interaction ID to poll
            on_progress: Optional progress callback
            
        Returns:
            ResearchResult when complete
            
        Raises:
            AIError: If research fails or times out
        """
        start_time = time.time()
        last_phase = ""
        last_progress_time = 0.0
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed > self.TIMEOUT_SECONDS:
                raise AIError(
                    f"Deep Research timed out after {self.TIMEOUT_SECONDS}s. "
                    f"ID: {interaction_id}",
                    model=self.AGENT_ID
                )
            
            # Get status
            interaction = self._client.interactions.get(interaction_id)
            status = interaction.status
            
            if status == "completed":
                # Extract content
                content = ""
                if hasattr(interaction, 'outputs') and interaction.outputs:
                    content = str(interaction.outputs[-1].text)
                
                logger.info(f"Deep Research completed in {elapsed:.0f}s")
                
                return ResearchResult(
                    content=content,
                    citations=[],  # TODO: Extract citations
                    interaction_id=interaction_id,
                    duration_seconds=elapsed,
                    status=ResearchStatus.COMPLETED,
                )
            
            elif status == "failed":
                error_msg = getattr(interaction, 'error', 'Unknown error')
                raise AIError(
                    f"Deep Research failed: {error_msg}",
                    model=self.AGENT_ID
                )
            
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
            
            # Adaptive polling interval
            interval = self._get_poll_interval(elapsed)
            await asyncio.sleep(interval)
    
    def _get_phase_name(self, elapsed_seconds: float) -> str:
        """Get the current phase name based on elapsed time."""
        if elapsed_seconds < 60:
            return "Initializing research"
        elif elapsed_seconds < 180:
            return "Searching sources"
        elif elapsed_seconds < 360:
            return "Analyzing findings"
        elif elapsed_seconds < 600:
            return "Generating report"
        else:
            return "Finalizing"
    
    def _get_poll_interval(self, elapsed_seconds: float) -> float:
        """
        Get adaptive polling interval based on elapsed time.
        
        5s → 10s → 20s → 30s
        """
        if elapsed_seconds < 60:
            return 5.0
        elif elapsed_seconds < 180:
            return 10.0
        elif elapsed_seconds < 360:
            return 20.0
        else:
            return 30.0


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
        import re
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
        import re
        
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
        import re
        
        # Check if content already has a clean header
        if content.strip().startswith(f"# Strategic Company Overview: {company_name}"):
            return content
        if content.strip().startswith(f"# Strategic Company Overview"):
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
        import re
        
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
        import re
        
        lines = ["## Table of Contents\n"]
        
        for i, chapter in enumerate(chapters, 1):
            # Create anchor link
            anchor = chapter.lower().replace(" ", "-").replace("&", "and")
            anchor = re.sub(r'[^a-z0-9-]', '', anchor)
            
            # Clean TOC entry - NO status markers
            lines.append(f"{i}. [{chapter}](#{anchor})")
        
        return "\n".join(lines)
    
    def _extract_citations(self, content: str) -> list[dict[str, str]]:
        """Extract citations from content."""
        import re
        
        citations: list[dict[str, str]] = []
        
        # Look for Sources section
        sources_match = re.search(r'\*\*Sources:\*\*\s*([\s\S]*?)$', content)
        if sources_match:
            sources_text = sources_match.group(1)
            # Extract numbered citations: 1. [text](url)
            citation_pattern = r'(\d+)\.\s*\[([^\]]+)\]\(([^)]+)\)'
            for match in re.finditer(citation_pattern, sources_text):
                citations.append({
                    'number': match.group(1),
                    'title': match.group(2),
                    'url': match.group(3)
                })
        
        return citations
    
    def _format_numbered_citations(
        self,
        content: str,
        citations: list[dict[str, str]]
    ) -> str:
        """Apply numbered citation formatting with clickable links and resolved URLs."""
        import re
        from urllib.parse import urlparse
        
        if not citations:
            return content
        
        # Build a mapping of citation numbers to their info (with resolved URLs)
        citation_map = {c.get('number', str(i+1)): c for i, c in enumerate(citations)}
        
        # Convert inline [cite: X, Y, Z] references to clean [1] [2] [3] format
        def replace_cite_ref(match: re.Match) -> str:
            nums_str = match.group(1)
            nums = [n.strip() for n in nums_str.split(',')]
            refs = [f"[{num}]" for num in nums]
            return ' '.join(refs)
        
        content = re.sub(r'\[cite:\s*([\d,\s]+)\]', replace_cite_ref, content)
        
        # Rebuild the Sources section with resolved URLs
        # The citations list now contains resolved URLs (not redirect URLs)
        sources_pattern = r'(\*\*Sources:\*\*\s*)([\s\S]*?)$'
        sources_match = re.search(sources_pattern, content)
        
        if sources_match and citations:
            sources_header = sources_match.group(1)
            
            # Build clean sources list using resolved URLs from citations
            cleaned_lines = []
            for citation in citations:
                num = citation.get('number', '')
                url = citation.get('url', '')
                title = citation.get('title', '')
                
                # Extract clean domain name for display if title is ugly
                if url:
                    parsed = urlparse(url)
                    domain = parsed.netloc.replace('www.', '')
                    # Use domain as display text if title looks like a redirect URL
                    if 'vertexaisearch' in title.lower() or not title:
                        display_text = domain
                    else:
                        display_text = title
                    cleaned_lines.append(f"{num}. [{display_text}]({url})")
                elif title:
                    cleaned_lines.append(f"{num}. {title}")
            
            # Rebuild the sources section with resolved URLs
            new_sources = sources_header + '\n'.join(cleaned_lines)
            content = content[:sources_match.start()] + new_sources
        
        return content
    
    def has_failure_markers(self, content: str) -> bool:
        """Check if content contains failure markers."""
        return "✗" in content or "✓" in content
    
    def has_memo_headers(self, content: str) -> bool:
        """Check if content contains memo-style headers."""
        import re
        memo_patterns = [
            r"RESEARCH REQUEST:",
            r"^TO:\s*",
            r"^FROM:\s*",
            r"^SUBJECT:\s*",
        ]
        for pattern in memo_patterns:
            if re.search(pattern, content, re.MULTILINE):
                return True
        return False
    
    def has_debug_artifacts(self, content: str) -> bool:
        """Check if content contains debug artifacts."""
        debug_patterns = [
            "[DEBUG]",
            "[ERROR]",
            "Traceback (most recent call last)",
            "Exception:",
        ]
        for pattern in debug_patterns:
            if pattern in content:
                return True
        return False
    
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
            store = self._client.file_search_stores.create(
                config={"display_name": f"{display_name}_{int(time.time())}"}
            )
            store_name: str = store.name or ""
            if not store_name:
                raise AIError(
                    "Failed to create file store - no name returned",
                    model="file_search_store"
                )
            logger.info(f"Created File Search Store: {store_name}")
            return store_name
        except AIError:
            raise
        except Exception as e:
            raise AIError(
                f"Failed to create File Search Store: {e}",
                model="file_search_store",
                cause=e
            ) from e
    
    def upload_context(
        self,
        store_name: str,
        content: str,
        filename: str,
        mime_type: str = "text/plain"
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
        import os
        
        # Write content to temp file for upload
        fd, temp_path = tempfile.mkstemp(suffix=f"_{filename}")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self._client.file_search_stores.upload_to_file_search_store(
                file=temp_path,
                file_search_store_name=store_name,
                config={"mime_type": mime_type}  # type: ignore[arg-type]
            )
            logger.info(f"Uploaded {filename} to store {store_name}")
        except Exception as e:
            raise AIError(
                f"Failed to upload context to store: {e}",
                model="file_search_store",
                cause=e
            ) from e
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    
    def upload_file(self, store_name: str, file_path: str) -> None:
        """
        Upload a file to a File Search Store.
        
        Args:
            store_name: Store name from create_store()
            file_path: Path to file to upload
            
        Raises:
            AIError: If upload fails
        """
        import os
        
        if not os.path.exists(file_path):
            raise AIError(
                f"File not found: {file_path}",
                model="file_search_store"
            )
        
        # MIME type mapping
        mime_types = {
            '.md': 'text/markdown',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.csv': 'text/csv',
            '.pdf': 'application/pdf',
        }
        
        ext = os.path.splitext(file_path)[1].lower()
        mime_type = mime_types.get(ext)
        config = {"mime_type": mime_type} if mime_type else None
        
        try:
            self._client.file_search_stores.upload_to_file_search_store(
                file=file_path,
                file_search_store_name=store_name,
                config=config  # type: ignore[arg-type]
            )
            logger.info(f"Uploaded {file_path} to store {store_name}")
        except Exception as e:
            raise AIError(
                f"Failed to upload {file_path}: {e}",
                model="file_search_store",
                cause=e
            ) from e
    
    def delete_store(self, store_name: str) -> None:
        """
        Delete a File Search Store.
        
        Should be called after Deep Research completes (success or failure)
        to clean up temporary context and ensure data governance.
        
        Args:
            store_name: Store name to delete
        """
        try:
            self._client.file_search_stores.delete(name=store_name)
            logger.info(f"Deleted File Search Store: {store_name}")
        except Exception as e:
            # Log but don't raise - cleanup failures shouldn't break the flow
            logger.warning(f"Failed to delete File Search Store {store_name}: {e}")


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
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

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
    **kwargs: Any
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
        query,
        output_format=output_format,
        priority_urls=priority_urls,
        **kwargs
    )


async def research_company(
    company_name: str,
    website: str | None = None,
    **kwargs: Any
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
        query,
        output_format="company_profile",
        priority_urls=priority_urls,
        **kwargs
    )
