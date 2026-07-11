"""
Standalone Accordion Method test runner.

Architecture (validated approach):
1. Phase 1: Deep Research gathers foundational facts (~12 page dossier)
2. Phase 2: Gemini Pro writes each section with context continuity
3. Phase 3: Assembly into cohesive final report

KEY INSIGHT: 1 Deep Research + N Gemini Pro follow-ups is the sweet spot.
- Deep Research excels at gathering comprehensive facts from the web
- Gemini Pro excels at writing detailed, analytical prose from those facts
- Result: ~30+ pages of quality content in ~20 minutes

Testing showed: 12 Deep Research calls = 10x cost/time for only +20% content.
The Gemini Pro follow-ups produce excellent detailed content.

Usage:
    from primr.ai.accordion_test import run_accordion_test
    result = run_accordion_test("Oceanography 2026-2030")
"""

import asyncio
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from primr.ai.genai_factory import default_genai_http_options
from primr.config.config import OUTPUT_DIR
from primr.utils.logging_config import get_logger

logger = get_logger("ai.accordion_test")


@dataclass
class AccordionTestConfig:
    """Configuration for standalone Accordion Method test."""

    topic: str
    target_pages: int = 30  # Quality content typically produces 30-40 pages
    section_delay_seconds: int = 10  # Short delay for Gemini Pro calls
    max_consecutive_failures: int = 3


@dataclass
class AccordionTestResult:
    """Result from standalone Accordion Method test."""

    content: str
    word_count: int
    page_estimate: float
    sections_completed: int
    sections_total: int
    duration_seconds: float
    output_path: str
    success: bool
    error: str | None = None
    section_details: list[dict] = field(default_factory=list)


# Section definitions - focused on depth and insight, not word count
# Key: Each section should flow naturally into the next (cohesive document)
RESEARCH_SECTIONS = [
    {
        "id": "executive_summary",
        "title": "Executive Summary",
        "instructions": """Write an executive summary that synthesizes the most important insights.

Focus on:
- The central thesis: what is the single most important thing to understand?
- 2-3 developments that will shape the next 5 years
- Key decisions facing stakeholders right now
- Any counterintuitive or underappreciated findings

Write with analytical rigor. Every sentence should add insight.
This sets the tone for the entire report - be direct and substantive.""",
    },
    {
        "id": "current_state",
        "title": "Current State of the Field",
        "instructions": """Provide a state-of-the-field analysis for domain experts.

Cover:
- Current scientific/technical consensus and areas of active debate
- Key methodological advances in the last 3-5 years
- Leading institutions and what makes their approach distinctive
- Capability gaps between theory and practice

Include specific data, cite landmark developments.
Build naturally from the executive summary's framing.""",
    },
    {
        "id": "key_trends",
        "title": "Key Trends and Inflection Points",
        "instructions": """Analyze the trends experts are watching most closely.

For each major trend:
- What's driving it (technology, economics, regulation, social)?
- Rate of change - accelerating or decelerating?
- What would cause reversal or acceleration?
- How do trends interact or create feedback loops?

Identify inflection points where the field's trajectory changed.
Connect back to the current state analysis.""",
    },
    {
        "id": "technology_innovation",
        "title": "Technology and Innovation Landscape",
        "instructions": """Technical deep-dive for R&D professionals and investors.

Cover:
- Fundamental principles and theoretical limits
- Engineering challenges between current state and limits
- Competing approaches and their tradeoffs
- Technology readiness levels for emerging tech
- Innovation ecosystem: funding, talent, IP landscape

Include performance metrics and cost curves.
This section should feel like a natural progression from trends.""",
    },
    {
        "id": "challenges_barriers",
        "title": "Critical Challenges and Bottlenecks",
        "instructions": """Analyze challenges with the rigor of a risk assessment.

For each challenge:
- Fundamental constraint vs. engineering problem?
- What would it take to solve (time, money, breakthrough)?
- Who's working on it and what approaches?
- Second-order effects if NOT solved?

Distinguish: technical, economic, institutional, knowledge gaps.
Connect to the technology landscape just discussed.""",
    },
    {
        "id": "market_economics",
        "title": "Economic Analysis and Value Chain",
        "instructions": """Economic analysis at McKinsey/BCG level.

Cover:
- Where value is created and captured in the chain
- Unit economics and how they're changing
- Cost drivers and which are improving fastest
- Market structures emerging (consolidation, platforms)
- Investment thesis and where capital is flowing

Include specific data: market sizes, growth rates, investment figures.
This flows from challenges into economic implications.""",
    },
    {
        "id": "regional_dynamics",
        "title": "Geopolitical and Regional Dynamics",
        "instructions": """Geopolitical analysis for experts and policymakers.

For each major region:
- Strategic rationale driving their approach
- Comparative advantages and disadvantages
- Dependencies and vulnerabilities

International dynamics:
- Where cooperation vs. competition is intensifying
- Key bilateral relationships and tensions
- Implications of different geopolitical scenarios

Connect economic analysis to regional strategies.""",
    },
    {
        "id": "future_outlook",
        "title": "Scenarios and Strategic Outlook",
        "instructions": """Scenario analysis for strategic planning.

Develop 2-3 distinct scenarios:
- Key uncertainties that could drive different outcomes
- For each: trigger, characteristics, implications
- Early warning indicators

For the most likely trajectory:
- Key milestones and decision points
- What needs to happen to achieve potential
- Biggest risks to baseline forecast

Include specific predictions with timeframes.
Build on all previous analysis.""",
    },
    {
        "id": "stakeholder_ecosystem",
        "title": "Stakeholder Ecosystem and Power Dynamics",
        "instructions": """Map the stakeholder ecosystem analytically.

For each major group:
- Core interests and incentives
- Resources and leverage
- Constraints and vulnerabilities
- Alignment or conflict with others

Power dynamics:
- Who sets the agenda and how?
- Key decision points and who controls them?
- Coalitions forming and what would shift balance?

Identify key individuals/institutions shaping the field.""",
    },
    {
        "id": "recommendations",
        "title": "Strategic Implications and Recommendations",
        "instructions": """Recommendations demonstrating deep understanding.

For each stakeholder type, provide recommendations that are:
- Specific and actionable (not generic)
- Grounded in the analysis (explain WHY)
- Realistic about constraints
- Prioritized (what matters most)

Include contrarian recommendations where evidence supports.
What should stakeholders STOP doing?""",
    },
    {
        "id": "synthesis",
        "title": "Synthesis and Key Insights",
        "instructions": """Synthesize into the insights that matter most.

NOT a summary. A synthesis:
- Single most important thing to understand right now
- What this analysis revealed that isn't obvious
- Highest-conviction predictions and what would change them
- Unanswered questions that would most change the picture

End with "so what" - why should a busy expert care?
What should they think or do differently?

Tie back to the executive summary's thesis.""",
    },
]


class AccordionTestRunner:
    """
    Standalone test runner for Accordion Method validation.

    Architecture:
    - Phase 1: Deep Research gathers facts (Lead Researcher role)
    - Phase 2: Gemini Pro writes each section (Writer role)
    - Phase 3: Assembly into cohesive report

    This produces ~30+ pages of quality content in ~20 minutes.
    """

    SECTION_DELAY = 10  # seconds between Gemini Pro calls
    SECTION_DELAY_AFTER_ERROR = 30

    def __init__(self):
        """Initialize the test runner."""
        from google import genai

        from primr.config.settings import get_settings

        settings = get_settings()
        self._api_key = settings.api.gemini_key
        self._client = genai.Client(
            api_key=self._api_key, http_options=default_genai_http_options()
        )
        self._api_call_count = 0

    async def run_test(
        self,
        config: AccordionTestConfig,
        on_progress: Callable[[str], None] | None = None,
    ) -> AccordionTestResult:
        """
        Run standalone Accordion Method test.

        Architecture:
        - Phase 1: Deep Research (dossier) - gathers facts
        - Phase 2: Gemini Pro (sections) - writes detailed content
        - Phase 3: Assembly - cohesive final report
        """
        start_time = time.time()
        self._api_call_count = 0

        written_sections: list[dict] = []
        section_details: list[dict] = []

        if on_progress:
            on_progress(f"Starting Accordion Method: {config.topic}")
            on_progress(f"Architecture: 1 Deep Research + {len(RESEARCH_SECTIONS)} Gemini Pro")
            on_progress("")

        try:
            # ================================================================
            # PHASE 1: Research Dossier (Deep Research as Lead Researcher)
            # ================================================================
            if on_progress:
                on_progress("=" * 60)
                on_progress("PHASE 1: Research Dossier (Deep Research)")
                on_progress("=" * 60)

            dossier_prompt = self._build_dossier_prompt(config.topic)
            dossier_result = await self._execute_deep_research(
                prompt=dossier_prompt,
                on_progress=on_progress,
            )

            if not dossier_result["success"]:
                return AccordionTestResult(
                    content="",
                    word_count=0,
                    page_estimate=0,
                    sections_completed=0,
                    sections_total=len(RESEARCH_SECTIONS),
                    duration_seconds=time.time() - start_time,
                    output_path="",
                    success=False,
                    error=f"Research dossier failed: {dossier_result.get('error', 'Unknown')}",
                )

            research_dossier = dossier_result["content"]
            dossier_words = len(research_dossier.split())

            if on_progress:
                on_progress(f"Phase 1 complete: {dossier_words:,} words of research")
                on_progress("")

            # ================================================================
            # PHASE 2: Section Writing (Gemini Pro)
            # ================================================================
            if on_progress:
                on_progress("=" * 60)
                on_progress(f"PHASE 2: Writing {len(RESEARCH_SECTIONS)} Sections (Gemini Pro)")
                on_progress("=" * 60)
                on_progress("Each section maintains context from previous sections")
                on_progress("")

            consecutive_failures = 0

            for i, section in enumerate(RESEARCH_SECTIONS):
                if consecutive_failures >= config.max_consecutive_failures:
                    if on_progress:
                        on_progress(f"STOPPING: {consecutive_failures} consecutive failures")
                    break

                section_num = i + 1
                if on_progress:
                    on_progress(
                        f"[{section_num}/{len(RESEARCH_SECTIONS)}] Writing: {section['title']}..."
                    )

                # Delay between calls (except first)
                if i > 0:
                    delay = config.section_delay_seconds
                    if on_progress:
                        on_progress(f"Waiting {delay}s before next section...")
                    await asyncio.sleep(delay)

                # Build section prompt with context continuity
                section_prompt = self._build_section_prompt(
                    section=section,
                    topic=config.topic,
                    research_dossier=research_dossier,
                    previous_sections=written_sections,
                    section_index=i,
                    total_sections=len(RESEARCH_SECTIONS),
                )

                # Write section with Gemini Pro
                section_start = time.time()
                result = await self._write_section_gemini(section_prompt)

                if result["success"] and result["content"]:
                    words = len(result["content"].split())
                    written_sections.append(
                        {
                            "id": section["id"],
                            "title": section["title"],
                            "content": result["content"],
                            "words": words,
                        }
                    )
                    section_details.append(
                        {
                            "id": section["id"],
                            "title": section["title"],
                            "words": words,
                            "success": True,
                            "duration": time.time() - section_start,
                        }
                    )
                    consecutive_failures = 0

                    if on_progress:
                        on_progress(f"✓ Written: {words:,} words")
                else:
                    consecutive_failures += 1
                    section_details.append(
                        {
                            "id": section["id"],
                            "title": section["title"],
                            "words": 0,
                            "success": False,
                            "duration": time.time() - section_start,
                        }
                    )
                    if on_progress:
                        on_progress(f"✗ Failed: {result.get('error', 'Unknown')}")

            if on_progress:
                on_progress("")
                on_progress(f"Phase 2 complete: {len(written_sections)} sections written")
                on_progress("")

            # ================================================================
            # PHASE 3: Assembly
            # ================================================================
            if on_progress:
                on_progress("=" * 60)
                on_progress("PHASE 3: Assembling Report")
                on_progress("=" * 60)

            final_content = self._assemble_report(config.topic, written_sections)
            final_words = len(final_content.split())
            final_pages = final_words / 500

            # Save output
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in config.topic[:50])
            output_filename = f"accordion_test_{safe_topic}_{timestamp}.md"
            output_path = os.path.join(OUTPUT_DIR, output_filename)

            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(final_content)

            interaction_id = dossier_result.get("interaction_id", "")
            if isinstance(interaction_id, str) and interaction_id:
                from primr.ai.job_persistence import acknowledge_pending_job_after_outputs

                if not acknowledge_pending_job_after_outputs(interaction_id, [output_path]):
                    logger.warning(
                        "Accordion output was not durable; the pending job remains recoverable"
                    )

            duration = time.time() - start_time

            if on_progress:
                on_progress("")
                on_progress("=" * 60)
                on_progress("RESULTS")
                on_progress("=" * 60)
                on_progress(f"Total words: {final_words:,}")
                on_progress(f"Estimated pages: {final_pages:.1f}")
                on_progress(f"Sections completed: {len(written_sections)}/{len(RESEARCH_SECTIONS)}")
                on_progress(f"Duration: {duration / 60:.1f} minutes")
                on_progress(f"API calls: {self._api_call_count}")
                on_progress(f"Output: {output_path}")
                on_progress("")

                if final_pages >= config.target_pages:
                    on_progress(
                        f"✓ Target met: {final_pages:.1f} pages (target: {config.target_pages})"
                    )
                else:
                    on_progress(f"Note: {final_pages:.1f} pages (target: {config.target_pages})")

            return AccordionTestResult(
                content=final_content,
                word_count=final_words,
                page_estimate=final_pages,
                sections_completed=len(written_sections),
                sections_total=len(RESEARCH_SECTIONS),
                duration_seconds=duration,
                output_path=output_path,
                success=len(written_sections) >= len(RESEARCH_SECTIONS) // 2,
                section_details=section_details,
            )

        except Exception as e:
            logger.error(f"Accordion test error: {e}")
            partial = (
                self._assemble_report(config.topic, written_sections) if written_sections else ""
            )

            return AccordionTestResult(
                content=partial,
                word_count=len(partial.split()) if partial else 0,
                page_estimate=len(partial.split()) / 500 if partial else 0,
                sections_completed=len(written_sections),
                sections_total=len(RESEARCH_SECTIONS),
                duration_seconds=time.time() - start_time,
                output_path="",
                success=False,
                error=str(e),
                section_details=section_details,
            )

    def _build_dossier_prompt(self, topic: str) -> str:
        """Build prompt for Phase 1: Research Dossier."""
        return f"""You are a Lead Researcher compiling a comprehensive research dossier on:

**{topic}**

Your task: Gather RAW FACTS, DATA, and EXPERT INSIGHTS that will support a detailed analytical report.
Do NOT write the final report - compile the research material.

Focus on SUBSTANTIVE FACTS that experts would find valuable:
- Specific numbers, dates, names, and citations
- Note confidence levels (confirmed/estimated/unclear)
- Include sources where available

Compile research on:

1. FOUNDATIONAL FACTS
   - Key definitions and scope boundaries
   - Historical milestones with dates
   - Current scale and scope (quantified)

2. SCIENTIFIC/TECHNICAL STATE
   - Current consensus and areas of debate
   - Key methodologies and limitations
   - Performance benchmarks over time
   - Theoretical limits vs. achieved performance

3. KEY PLAYERS
   - Leading research groups and contributions
   - Major companies and positions
   - Key individuals shaping the field
   - Funding sources and amounts

4. QUANTITATIVE DATA
   - Market sizes, growth rates, projections
   - Cost curves and trends
   - Performance metrics
   - Investment figures

5. CHALLENGES
   - Technical bottlenecks (specific)
   - Economic barriers (quantified)
   - Regulatory landscape
   - Known unknowns

6. RECENT DEVELOPMENTS (2023-2025)
   - Breakthrough announcements
   - Policy changes
   - Major investments
   - Shifts in expert consensus

7. FORWARD-LOOKING
   - Expert predictions (attributed)
   - Expected milestones
   - Scenarios being discussed
   - Early warning indicators

OUTPUT: Detailed bullet points organized by section.
Every fact should have a source or confidence level.
This is RAW RESEARCH MATERIAL - prioritize facts over prose."""

    def _build_section_prompt(
        self,
        section: dict,
        topic: str,
        research_dossier: str,
        previous_sections: list[dict],
        section_index: int,
        total_sections: int,
    ) -> str:
        """
        Build prompt for section writing with context continuity.

        Key insight: The report should feel like ONE cohesive document,
        not 11 separate sections stapled together.
        """
        # Build context from previous sections for narrative flow
        prev_context = ""
        if previous_sections:
            # Include summaries of recent sections for continuity
            recent = previous_sections[-3:]  # Last 3 sections
            summaries = []
            for prev in recent:
                # First 200 words as summary
                summary = " ".join(prev["content"].split()[:200])
                summaries.append(f"**{prev['title']}** (summary): {summary}...")
            prev_context = "\n\n".join(summaries)

        # Position context for narrative flow
        position_guidance = ""
        if section_index == 0:
            position_guidance = """This is the OPENING section. Set the analytical tone for the entire report.
Establish the central thesis that subsequent sections will develop."""
        elif section_index == total_sections - 1:
            position_guidance = """This is the CLOSING section. Tie together all previous analysis.
Reference key insights from earlier sections. Provide closure."""
        else:
            position_guidance = f"""This is section {section_index + 1} of {total_sections}.
Build naturally on the previous sections. Reference earlier points where relevant.
Set up themes that later sections will develop."""

        return f"""You are writing a section of a comprehensive research report on:

**{topic}**

# YOUR SECTION
**{section["title"]}**

# SECTION REQUIREMENTS
{section["instructions"]}

# RESEARCH DOSSIER (Source Material)
Use these facts as your foundation. Expand with analysis and insight.

{research_dossier[:12000]}

# PREVIOUS SECTIONS (for narrative continuity)
{prev_context if prev_context else "This is the first section."}

# NARRATIVE GUIDANCE
{position_guidance}

# WRITING STANDARDS
- Write in flowing prose with clear subheadings
- Every paragraph should contain specific facts, figures, or analysis
- Avoid filler phrases ("it is important to note", "there are many factors")
- Analyze, don't just describe - explain WHY things matter
- Reference previous sections naturally ("As discussed in...", "Building on...")
- Use transitions that connect to the overall narrative
- Include data tables where appropriate (Markdown format)
- Cite sources using [cite: N] format

# COHESION
This section should feel like part of ONE document, not a standalone piece.
- Reference the report's central thesis
- Connect to themes from previous sections
- Set up points that later sections will develop

Write the **{section["title"]}** section now:"""

    async def _write_section_gemini(self, prompt: str) -> dict:
        """Write a section using Gemini 3 Flash."""
        self._api_call_count += 1

        try:
            from primr.config.models import PrimrModels

            response = self._client.models.generate_content(
                model=PrimrModels.FLASH_MODEL,
                contents=prompt,
            )

            content = response.text if hasattr(response, "text") else str(response)

            return {
                "success": True,
                "content": content.strip(),
            }

        except Exception as e:
            logger.error(f"Gemini Pro error: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
            }

    async def _execute_deep_research(
        self,
        prompt: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict:
        """Execute Deep Research API call for the dossier."""
        self._api_call_count += 1
        start_time = time.time()

        # Import centralized model config
        from primr.config.models import PrimrModels

        try:
            if on_progress:
                on_progress("Starting Deep Research...")

            interaction = self._client.interactions.create(
                input=prompt,
                agent=PrimrModels.DEEP_RESEARCH_AGENT,
                background=True,
            )

            interaction_id = interaction.id
            from primr.ai.job_persistence import save_pending_job

            save_pending_job(
                interaction_id=interaction_id,
                job_type="accordion_test",
                description=prompt[:200],
            )
            if on_progress:
                on_progress(f"Research started: {interaction_id[:20]}...")

            # Poll for completion
            poll_count = 0
            while True:
                elapsed = time.time() - start_time

                if elapsed > 1800:  # 30 min timeout
                    return {
                        "success": False,
                        "error": "Research timed out after 30 minutes",
                        "content": "",
                    }

                interaction = self._client.interactions.get(interaction_id)
                status = interaction.status

                if status == "completed":
                    content = ""
                    if hasattr(interaction, "outputs") and interaction.outputs:
                        for output in interaction.outputs:
                            if hasattr(output, "text") and output.text:
                                content += str(output.text) + "\n"

                    words = len(content.split())
                    if on_progress:
                        on_progress(f"Research complete: {words:,} words in {elapsed / 60:.1f} min")

                    return {
                        "success": True,
                        "content": content.strip(),
                        "interaction_id": interaction_id,
                    }

                elif status == "failed":
                    error = getattr(interaction, "error", "Unknown error")
                    return {
                        "success": False,
                        "error": str(error),
                        "content": "",
                        "interaction_id": interaction_id,
                    }

                poll_count += 1
                if on_progress and poll_count % 3 == 0:
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    on_progress(f". Still researching ({mins}m {secs}s)...")

                await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Deep Research error: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": "",
            }

    def _assemble_report(self, topic: str, sections: list[dict]) -> str:
        """
        Assemble sections into cohesive final report.

        Format: Clean, modern header - no table of contents.
        """
        current_date = datetime.now().strftime("%B %Y")

        lines = [
            f"# Research Report: {topic}",
            "",
            f"*{current_date}*",
            "",
        ]

        # Sections - clean flow
        for i, section in enumerate(sections):
            lines.extend(
                [
                    f"## {section['title']}",
                    "",
                    section["content"],
                    "",
                ]
            )
            # Subtle separator every 5 sections
            if i > 0 and (i + 1) % 5 == 0 and i < len(sections) - 1:
                lines.append("---")
                lines.append("")

        return "\n".join(lines)


# =============================================================================
# CLI INTEGRATION
# =============================================================================


async def run_accordion_test_async(
    topic: str,
    target_pages: int = 30,
    section_delay: int = 10,
) -> AccordionTestResult:
    """Run the Accordion Method test asynchronously."""
    from primr.utils.console import console

    runner = AccordionTestRunner()

    def progress_callback(msg: str) -> None:
        console.info(msg)

    return await runner.run_test(
        AccordionTestConfig(
            topic=topic,
            target_pages=target_pages,
            section_delay_seconds=section_delay,
        ),
        on_progress=progress_callback,
    )


def run_accordion_test(
    topic: str,
    target_pages: int = 30,
    section_delay: int = 10,
) -> AccordionTestResult:
    """
    Run the Accordion Method test synchronously.

    Args:
        topic: Research topic
        target_pages: Target page count (default 30)
        section_delay: Delay between Gemini Pro calls in seconds

    Returns:
        AccordionTestResult
    """
    return asyncio.run(run_accordion_test_async(topic, target_pages, section_delay))
