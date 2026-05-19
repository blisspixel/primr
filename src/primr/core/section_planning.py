"""Section sizing, grouping, and reasoning-mode helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.

These pure helpers decide adaptive word targets, max-token budgets,
section-by-part groupings, and whether a section should use
constrained-evidence reasoning when direct company signal is thin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from primr.prompts.loader import SectionConfig


# Part labels used for console output during fast-mode batches.
_PART_LABELS: dict[int, str] = {
    1: "Foundation",
    2: "Industry",
    3: "Strategic",
    4: "Deep Insights",
    5: "Synthesis",
}

# Section IDs that always warrant the 1,200-word target regardless of
# their YAML-declared depth.
_HIGH_DEPTH_SECTION_IDS: frozenset[str] = frozenset(
    {
        "executive_summary",
        "competitive_landscape",
        "company_history",
        "engagement_opportunities",
    }
)


def _get_section_word_target(section: SectionConfig) -> int:
    """Return adaptive word target for a single section.

    - Sections with depth mentioning 'pages'/'comprehensive', or IDs in
      ``_HIGH_DEPTH_SECTION_IDS`` → 1,200 words
    - Framework sections (position == 'framework') → 800 words
    - Everything else → 800 words
    """
    depth_lower = (section.depth or "").lower()
    if (
        section.id in _HIGH_DEPTH_SECTION_IDS
        or "pages" in depth_lower
        or "comprehensive" in depth_lower
    ):
        return 1_200
    if section.position == "framework":
        return 800
    return 800


def _get_section_max_tokens(section: SectionConfig) -> int:
    """Return max_tokens for a single-section Grok call."""
    return 6_000 if _get_section_word_target(section) >= 1_000 else 4_000


def _determine_section_reasoning_mode(
    section: SectionConfig, analysis_workbook: str
) -> str:
    """Use constrained-evidence reasoning when direct company signal is thin."""
    evidence_keywords = {
        "financial_profile": [
            "revenue",
            "profit",
            "margin",
            "funding",
            "valuation",
            "earnings",
        ],
        "company_history": [
            "founded",
            "history",
            "acquisition",
            "pivot",
            "milestone",
        ],
        "industry_outlook": [
            "industry trend",
            "regulation",
            "outlook",
            "forecast",
            "disruption",
        ],
    }
    keywords = evidence_keywords.get(section.id)
    if not keywords:
        return "standard"
    workbook_lower = analysis_workbook.lower() if analysis_workbook else ""
    hits = sum(1 for kw in keywords if kw in workbook_lower)
    return "constrained_evidence" if hits == 0 else "standard"


def _group_sections_by_part() -> list[list[SectionConfig]]:
    """
    Load sections from company_overview.yaml and group by ``part`` number.

    Returns a list of 5 lists (parts 1-5), each containing the
    :class:`SectionConfig` objects that belong to that part.
    """
    from primr.prompts.loader import load_prompt_config

    config = load_prompt_config("company_overview")
    groups: dict[int, list] = {}
    for section in config.sections:
        groups.setdefault(section.part, []).append(section)
    return [groups[p] for p in sorted(groups)]
