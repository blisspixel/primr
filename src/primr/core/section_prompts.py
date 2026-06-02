"""Prompt builders for fast-mode research.

Extracted from `primr.core.research_agent` for isolated unit testing.

These pure builders take run inputs (company name, scraped corpus,
external sources, etc.) and produce the long-form text prompts handed to
the Grok LLM for link selection, analysis-workbook generation, batch
section writing, and single-section writing.

The only side effect is `_load_fast_feedback_guidance`, which reads a
persisted rules file produced by eval feedback loops.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from primr.config.config import FAST_FEEDBACK_RULES_PATH
from primr.core.section_planning import _get_section_word_target
from primr.data.scraping.org_profile import get_focus_areas_for_org_type
from primr.qa.report_analyzer import SCAFFOLDING_PROHIBITION_GUIDANCE

if TYPE_CHECKING:
    from primr.output.final_artifact import GeneratedSection
    from primr.prompts.loader import SectionConfig

logger = logging.getLogger(__name__)


def _load_fast_feedback_guidance() -> str:
    """Load persisted fast-mode guidance generated from eval feedback loops."""
    path = Path(FAST_FEEDBACK_RULES_PATH)
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as e:
        logger.debug("Failed to load fast feedback guidance from %s: %s", path, e)
        return ""
    if not text:
        return ""
    # Bound prompt growth.
    return text[:4000]


def _build_link_selection_prompt(
    company_name: str,
    website: str,
    links_text: str,
    max_links: int,
    organization_type: str,
) -> str:
    focus_areas = "\n".join(
        f"- {focus}" for focus in get_focus_areas_for_org_type(organization_type)
    )
    return (
        f"You are selecting pages for intelligence gathering on {company_name} ({website}).\n\n"
        f"Organization type: {organization_type}.\n"
        "Choose only from the discovered URLs below. Do not invent, normalize, or rewrite URLs.\n\n"
        "Prioritize pages that help explain the organization through these focus areas:\n"
        f"{focus_areas}\n\n"
        "Discovered URLs:\n"
        f"{links_text}\n\n"
        f"Return only URLs from the discovered list, up to {max_links}, one per line."
    )


def _build_fast_analysis_prompt(
    company_name: str,
    website: str | None,
    raw_corpus: str,
    external_sources: str,
) -> str:
    """Build the Phase 2 analysis workbook prompt for Grok fast mode."""
    current_date = datetime.now().strftime("%B %d, %Y")

    return f"""**Company:** {company_name}
**Website:** {website or "N/A"}
**Date:** {current_date}

Below is raw data scraped from the company's website and external sources.
Analyze it and produce a Structured Analysis Workbook.

=== RAW WEBSITE DATA ===
{raw_corpus}

=== EXTERNAL SOURCES ===
{external_sources}

---

Produce a **Structured Analysis Workbook** with the following sections.
Use bullet points, tables, and short paragraphs. This is working notes, not prose.

CRITICAL: You are doing PRE-ENGAGEMENT ANALYSIS for a consulting firm, not summarizing
the company's marketing. Separate what {company_name} CLAIMS from what external evidence
SUPPORTS. Be conservative on financial estimates — use wide ranges and note confidence.

1. **Company Basics**
   - Official name, headquarters, founding date, employee count
   - Ownership structure (public/private, investors)
   - Label each fact: (Confirmed), (Reported), (Estimated), or (Hypothesis)

2. **Products & Services Catalog**
   - Every product/service found, organized by category
   - Pricing models, contract structures if visible
   - Recent launches or pivots (last 2-3 years)
   - Distinguish what's live/adopted vs. what's announced/marketing

3. **Customer Segments & Market Positioning**
   - Primary segments with evidence
   - Geographic distribution
   - Enterprise vs SMB vs consumer mix
   - Go-to-market approach
   - Flag any logo references that lack depth (vague "powered by" vs. detailed case)

4. **Competitive Landscape**
   - At least 5 competitors with: name, estimated size, key differentiator
   - Where {company_name} appears to win and lose (from external evidence, not their claims)
   - Emerging disruptors
   - Include competitors the company DOESN'T mention but should

5. **Financial Profile**
   - Revenue (actual or estimated with WIDE ranges and LOW confidence if inferred)
   - Growth rate and trajectory
   - Profitability indicators
   - Funding history / capital structure
   - Include a summary table
   - AVOID aggressive inferences — if data is thin, say so explicitly

6. **Leadership Profiles**
   - C-suite with backgrounds, tenure, previous roles
   - Board composition
   - Recent departures or hires

7. **Industry Dynamics**
   - Industry size, growth rate
   - Key trends and disruption factors
   - Regulatory environment

8. **Strategic Hypotheses** (3-5)
   For each:
   - Hypothesis statement
   - Supporting evidence (with sources)
   - Counter-evidence or alternative explanation
   - Confidence level
   - What question would you ask in discovery to TEST this?

9. **Strategic Tensions** (3-5)
   For each:
   - The tension (a tradeoff they must manage, e.g., "Scale vs Customization")
   - Evidence from the data
   - How they appear to be managing it currently

10. **Narrative Gaps** (3-5)
    For each:
    - What they claim (with quote/source from THEIR marketing)
    - Contradicting or complicating EXTERNAL signals
    - Question to explore
    These should be genuine stress-tests of their story, not minor wording quibbles.

11. **Areas of Potential Fragility** (3-4)
    Focus on systemic risks: single points of failure, concentration risks,
    dependencies that could break under stress.

12. **Patterns Worth Exploring** (3-5)
    Novel observations: surprising correlations, timing signals, behavioral
    patterns that don't fit the narrative.

13. **Discovery Questions** (6-8)
    For each:
    - The question
    - Why we're asking (what evidence prompted it)
    - What we hope to learn
    These should be questions a CONSULTING PARTNER would ask in a first meeting —
    sharp, grounded in evidence, testing specific hypotheses.
"""


def _build_fast_batch_prompt(
    company_name: str,
    website: str | None,
    analysis_workbook: str,
    raw_corpus_subset: str,
    external_sources: str,
    source_urls: list[str],
    sections: list[SectionConfig],
    previous_sections: list[GeneratedSection],
    batch_number: int,
    total_batches: int,
) -> str:
    """Build the prompt for writing one batch of report sections."""
    current_date = datetime.now().strftime("%B %d, %Y")

    section_parts: list[str] = []
    for section in sections:
        covers_text = "\n".join(f"      - {item}" for item in section.covers)
        depth_text = section.depth.strip() if section.depth else "Thorough analysis"
        position_label = section.position or "middle"
        section_parts.append(
            f"### {section.name}\n"
            f"**Purpose:** {section.purpose}\n"
            f"**Position:** {position_label}\n"
            f"**Must cover:**\n{covers_text}\n"
            f"**Depth:** {depth_text}"
        )
    section_block = "\n\n".join(section_parts)

    rolling_context = ""
    if previous_sections:
        recent = previous_sections[-7:]
        context_parts: list[str] = []
        for s in recent:
            words = s.content.split()
            summary = " ".join(words[:400])
            if len(words) > 400:
                summary += " ..."
            context_parts.append(f"**{s.title}** (completed):\n{summary}")
        rolling_context = "\n\n".join(context_parts)

    rolling_block = (
        f"## PREVIOUS SECTIONS (for narrative continuity)\n{rolling_context}"
        if rolling_context
        else "## PREVIOUS SECTIONS\n(This is the first batch — no prior sections.)"
    )

    sources_text = (
        "\n".join(f"[{i}] {url}" for i, url in enumerate(source_urls, start=1))
        if source_urls
        else "(no external sources)"
    )
    word_target = len(sections) * 800
    feedback_guidance = _load_fast_feedback_guidance()
    feedback_block = (
        f"=== FAST FEEDBACK GUIDANCE (from prior evals) ===\n{feedback_guidance}\n"
        if feedback_guidance
        else ""
    )
    return f"""**Company:** {company_name}
**Website:** {website or "N/A"}
**Date:** {current_date}
**Batch:** {batch_number + 1} of {total_batches}

You are writing batch {batch_number + 1} of {total_batches} for a Strategic Company Overview.
This batch contains {len(sections)} sections. Write each section under its own ## heading.

{rolling_block}

=== ANALYSIS WORKBOOK ===
{analysis_workbook}

=== RAW DATA (for evidence and citations) ===
{raw_corpus_subset}

=== EXTERNAL SOURCES ===
{external_sources}

{feedback_block}

SOURCES CONSULTED:
{sources_text}

---

Write the following sections. Each section MUST start with a ## heading matching the section name exactly.

{section_block}

REQUIREMENTS:
- Write at least {word_target:,} words total across all sections in this batch
- Use specific facts, numbers, examples, and strategic comparisons — cite sources with [cite: N]
- Be analytical and hypothesis-driven, not just descriptive
- Label claims with confidence levels (Confirmed/Reported/Estimated/Hypothesis)
- If direct evidence is limited, still write a deep section by anchoring on observed facts,
  extending with defensible inference, and making the strategic implication explicit
- Build on the previous sections' narrative (see rolling context above)
- For framework sections (SWOT, Porter's, Value Chain): organize insights from
  earlier sections, don't introduce wholly new observations
- Include tables where instructed (financials, competitors, timelines)
- Each section should have substantive depth — multiple paragraphs with evidence
- If a numeric claim cannot be supported by a cited source, replace it with
  "Not publicly disclosed", a bounded qualitative range, or a clearly labeled low-confidence directional statement
- Do not invent market sizes, CAGR, revenue ranges, headcount ranges, or shares
  unless directly grounded in one or more cited sources or a transparent comparative heuristic
- End each section with a short "What to validate:" line containing one concrete
  discovery question or data point to confirm in client interviews
- ZERO REPETITION: Before writing a section, review the rolling context above.
  If an insight, data point, or hypothesis already appeared in a prior section,
  do NOT restate it. Reference the earlier section instead ("as noted in the
  Executive Summary...") or build on it with new evidence.
- AI/TECHNOLOGY INTEGRATION: When relevant, explicitly connect AI or technology
  use cases to the company's specific business challenges. Don't just mention
  "AI could help" — specify which AI capability (NLP, computer vision, predictive
  analytics, etc.) maps to which concrete business problem identified in this report.

CONSULTING RIGOR (critical):
- Do NOT paraphrase the company's marketing. When you cite their claims, immediately
  stress-test them against external evidence or flag what's unverifiable.
- For each major hypothesis or insight, include "What to validate": a specific question
  or data point a consultant should probe in discovery.
- Be CONSERVATIVE on financial estimates. If you're inferring revenue from employee
  count, say "highly uncertain" and use wide ranges. Never state inferences as fact.
- Frame "why now" for the company — what transition or inflection point makes this
  moment interesting? Platform shifts, PE investment, leadership changes, etc.
- Think like a buyer, not a narrator. Where does this company win deals? Where does
  it lose? What would a competitor say about them?
- When direct evidence is sparse, go deeper on likely economics, buyer behavior,
  operating constraints, strategic tradeoffs, scenario paths, and the decisions leadership faces.
- When direct evidence is sparse, go deeper on likely economics, buyer behavior, operating
  constraints, strategic tradeoffs, scenario paths, and the decisions leadership likely faces.

CITATION FORMAT (strict):
- The SOURCES CONSULTED block above is a numbered citation key: [N] URL
- Inline claims must reference citations as [cite: N], where N matches the
  number assigned to that URL in the SOURCES CONSULTED block
- Reuse the same N every time you cite the same URL
- Do NOT emit [Source: URL] inline; use [cite: N] only
- Do NOT invent citation numbers — only cite N values present in the key above

{SCAFFOLDING_PROHIBITION_GUIDANCE}

OUTPUT CONTRACT (strict):
- Preferred format: emit each section inside a lightweight XML envelope:
  <section><title>Exact Section Name</title><body>Section body here</body></section>
- If you do not use the XML envelope, start each section with exactly one ## heading matching the requested section name
- Do not add a ## Sources, ## References, or ## Citations subsection inside section output
- Include exactly one What to validate: line per section, and make it the final line of that section
- Write that line as plain text — no bold, no italics, no bullet prefix (it is prose, not a label)
- Do not include any preamble or commentary outside the requested section bodies
"""


def _build_fast_section_prompt(
    company_name: str,
    website: str | None,
    analysis_workbook: str,
    raw_corpus_subset: str,
    external_sources: str,
    source_urls: list[str],
    section: SectionConfig,
    written_sections: list[GeneratedSection],
    section_index: int,
    all_section_names: list[str],
    reasoning_mode: str = "standard",
) -> str:
    """Build prompt for writing a single report section."""
    current_date = datetime.now().strftime("%B %d, %Y")
    word_target = _get_section_word_target(section)

    covers_text = "\n".join(f"      - {item}" for item in section.covers)
    depth_text = section.depth.strip() if section.depth else "Thorough analysis"
    position_label = section.position or "middle"
    section_block = (
        f"### {section.name}\n"
        f"**Purpose:** {section.purpose}\n"
        f"**Position:** {position_label}\n"
        f"**Must cover:**\n{covers_text}\n"
        f"**Depth:** {depth_text}"
    )

    toc_parts: list[str] = []
    for idx, name in enumerate(all_section_names):
        if idx < section_index:
            toc_parts.append(f"  [DONE] {name}")
        elif idx == section_index:
            toc_parts.append(f"  [NOW]  {name}")
        else:
            toc_parts.append(f"  [TODO] {name}")
    toc_block = "## REPORT TABLE OF CONTENTS\n" + "\n".join(toc_parts)

    rolling_context = ""
    if written_sections:
        if section.position == "framework" or section.id == "executive_summary":
            context_parts = [f"**{s.title}** (completed):\n{s.content}" for s in written_sections]
        else:
            recent = written_sections[-5:]
            context_parts = []
            for s in recent:
                words = s.content.split()
                summary = " ".join(words[:300])
                if len(words) > 300:
                    summary += " ..."
                context_parts.append(f"**{s.title}** (completed):\n{summary}")
        rolling_context = "\n\n".join(context_parts)

    rolling_block = (
        f"## PREVIOUS SECTIONS (for narrative continuity)\n{rolling_context}"
        if rolling_context
        else "## PREVIOUS SECTIONS\n(This is the first section — no prior sections.)"
    )

    sources_text = (
        "\n".join(f"[{i}] {url}" for i, url in enumerate(source_urls, start=1))
        if source_urls
        else "(no external sources)"
    )
    feedback_guidance = _load_fast_feedback_guidance()
    feedback_block = (
        f"=== FAST FEEDBACK GUIDANCE (from prior evals) ===\n{feedback_guidance}\n"
        if feedback_guidance
        else ""
    )

    reasoning_guidance = (
        "CONSTRAINED-EVIDENCE MODE: Direct company-specific evidence for this section is limited. "
        "Do NOT collapse into a thin fact check. Use the website, news, industry structure, competitor "
        "analogs, and operating logic to build a deep strategic section. Separate what is observed, what "
        "is inferred, what is hypothesis, and what the strategic implication is."
        if reasoning_mode == "constrained_evidence"
        else "STANDARD-EVIDENCE MODE: Use the strongest available mix of direct evidence, external research, "
        "and strategic inference."
    )

    return f"""**Company:** {company_name}
**Website:** {website or "N/A"}
**Date:** {current_date}
**Section:** {section_index + 1} of {len(all_section_names)} — {section.name}

{toc_block}

You are writing ONE section of a Strategic Company Overview.
Write this section under a single ## heading matching the section name exactly.

{rolling_block}

=== ANALYSIS WORKBOOK ===
{analysis_workbook}

=== RAW DATA (for evidence and citations) ===
{raw_corpus_subset}

=== EXTERNAL SOURCES ===
{external_sources}

{feedback_block}

REASONING MODE:
{reasoning_guidance}

SOURCES CONSULTED:
{sources_text}

---

Write the following section. It MUST start with a ## heading matching the section name exactly.

{section_block}

REQUIREMENTS:
- Write at least {word_target:,} words for this section
- Use specific facts, numbers, examples, and strategic comparisons — cite sources with [cite: N]
- Be analytical and hypothesis-driven, not just descriptive
- Label claims with confidence levels (Confirmed/Reported/Estimated/Hypothesis)
- If direct evidence is limited, still write a deep section by anchoring on observed facts,
  extending with defensible inference, and making the strategic implication explicit
- Build on the previous sections' narrative (see rolling context above)
- For framework sections (SWOT, Porter's, Value Chain): organize insights from
  earlier sections, don't introduce wholly new observations
- Include tables where instructed (financials, competitors, timelines)
- This section should have substantive depth — multiple paragraphs with evidence
- If a numeric claim cannot be supported by a cited source, replace it with
  "Not publicly disclosed", a bounded qualitative range, or a clearly labeled low-confidence directional statement
- Do not invent market sizes, CAGR, revenue ranges, headcount ranges, or shares
  unless directly grounded in one or more cited sources or a transparent comparative heuristic
- End the section with a short "What to validate:" line containing one concrete
  discovery question or data point to confirm in client interviews
- ZERO REPETITION: Before writing, review the rolling context and TOC above.
  If an insight, data point, or hypothesis already appeared in a prior section,
  do NOT restate it. Reference the earlier section instead ("as noted in the
  Executive Summary...") or build on it with new evidence.
- AI/TECHNOLOGY INTEGRATION: When relevant, explicitly connect AI or technology
  use cases to the company's specific business challenges. Don't just mention
  "AI could help" — specify which AI capability maps to which concrete problem.
- CITATION HYGIENE: Keep citations compact. Prefer paragraph-end citation clusters over
  interrupting every sentence, and let the final Sources appendix carry the dense reference load.

CONSULTING RIGOR (critical):
- Do NOT paraphrase the company's marketing. When you cite their claims, immediately
  stress-test them against external evidence or flag what's unverifiable.
- For each major hypothesis or insight, include "What to validate": a specific question
  or data point a consultant should probe in discovery.
- Be CONSERVATIVE on financial estimates. If you're inferring revenue from employee
  count, say "highly uncertain" and use wide ranges. Never state inferences as fact.
- Frame "why now" for the company — what transition or inflection point makes this
  moment interesting? Platform shifts, PE investment, leadership changes, etc.
- Think like a buyer, not a narrator. Where does this company win deals? Where does
  it lose? What would a competitor say about them?

CITATION FORMAT (strict):
- The SOURCES CONSULTED block above is a numbered citation key: [N] URL
- Inline claims must reference citations as [cite: N], where N matches the
  number assigned to that URL in the SOURCES CONSULTED block
- Reuse the same N every time you cite the same URL
- Do NOT emit [Source: URL] inline; use [cite: N] only
- Do NOT invent citation numbers — only cite N values present in the key above

{SCAFFOLDING_PROHIBITION_GUIDANCE}

OUTPUT CONTRACT (strict):
- Preferred format: emit each section inside a lightweight XML envelope:
  <section><title>Exact Section Name</title><body>Section body here</body></section>
- If you do not use the XML envelope, start each section with exactly one ## heading matching the requested section name
- Do not add a ## Sources, ## References, or ## Citations subsection inside section output
- Include exactly one What to validate: line per section, and make it the final line of that section
- Write that line as plain text — no bold, no italics, no bullet prefix (it is prose, not a label)
- Do not include any preamble or commentary outside the requested section bodies
"""
