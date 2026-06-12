"""Combined-insights and external-sources assembly (roadmap #23, Batch B).

Extracted verbatim from the stage-2B build in ``perform_fast_research`` — no
behavior change. The same assembly runs twice per run: once after data
collection, and again after the gap-filling phase rebuilds the source pools.
The orchestrator previously duplicated the pattern at both sites; this module
is the single definition, with the only site difference (the empty-parts
fallback string) expressed as a parameter.

Both functions are pure string assembly. File writes (``insights.txt``) stay
in the orchestrator so this module has no I/O.
"""

from __future__ import annotations

NO_RESEARCH_FALLBACK = "No research data collected."
NO_EXTERNAL_SOURCES = "(no external sources)"


def build_combined_insights(
    summarized: str,
    external_text_parts: list[str],
    hiring_block: str,
    *,
    fallback: str = NO_RESEARCH_FALLBACK,
) -> str:
    """Assemble the ``insights.txt`` content from the per-pool summaries.

    The hiring-signals block rides along so it survives every refresh of the
    insights file. ``fallback`` is returned when every part is empty: the
    initial build uses the no-data sentinel, the post-gap rebuild passes the
    previous combined insights so a degenerate rebuild never erases data.
    """
    all_insights_parts = []
    if summarized:
        all_insights_parts.append(f"=== WEBSITE INSIGHTS ===\n{summarized}")
    if external_text_parts:
        all_insights_parts.append("=== EXTERNAL SOURCES ===\n" + "\n\n".join(external_text_parts))
    if hiring_block:
        all_insights_parts.append(hiring_block)
    return "\n\n".join(all_insights_parts) if all_insights_parts else fallback


def build_external_sources_raw(external_raw_parts: list[str], hiring_block: str) -> str:
    """Assemble the raw external-sources bundle handed to Grok prompts.

    Hiring signals ride along so the gap-analysis, workbook, section-writing,
    and cross-validation prompts all see them as available evidence — at the
    initial build and again after the gap-filling refresh.
    """
    parts = list(external_raw_parts)
    if hiring_block:
        parts.append(hiring_block)
    return "\n\n".join(parts) if parts else NO_EXTERNAL_SOURCES
