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

                # Still in progress - show phase changes only (no repeated messages)
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

                    # Only show progress on phase change (not time intervals)
                    if not hasattr(self, '_last_phase') or self._last_phase != phase:
                        self._last_phase = phase
                        mins = int(elapsed // 60)
                        secs = int(elapsed % 60)
                        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                        on_progress(ResearchProgress(
                            status=ResearchStatus.IN_PROGRESS,
                            message=f"{phase} ({time_str})"
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
        return f"""
RESEARCH REQUEST: Strategic Company Overview for Consulting Prep

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

## SWOT Analysis (Initial Assessment)
Based on public information. Frame as observations to validate with the client:
- Strengths: What appears to be working well?
- Weaknesses: What potential constraints, tradeoffs, or gaps might be worth discussing openly?
- Opportunities: What options might be worth exploring?
- Threats: What risks should we discuss with them?

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
        return f"""
RESEARCH REQUEST: Strategic Deep-Dive (Building on Initial Research)

{query}

CONTEXT: You have access to initial research findings that cover the basics: company overview, products/services, history, and factual information. That foundation is already done. Do not repeat what's in the context files.

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
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

import threading

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
