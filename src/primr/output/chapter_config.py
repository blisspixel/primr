"""
Chapter configuration for premium report generation.

Defines the logical grouping of sections into chapters, fields for the
company snapshot box, and sources for executive summary generation.
"""


# =============================================================================
# Sections extracted for Company Snapshot (not rendered as chapters)
# =============================================================================
SNAPSHOT_FIELDS: list[str] = [
    "company_name",
    "company_website",
    "industry",
]

# =============================================================================
# Sections used to generate Executive Summary (content synthesized, not duplicated)
# =============================================================================
EXECUTIVE_SUMMARY_SOURCES: list[str] = [
    "unique_selling_proposition",
    "financial_overview",
    "strategic_recommendations",
    "value_theory",
]

# =============================================================================
# Chapter structure for main document body
# =============================================================================
CHAPTER_CONFIG: dict[str, dict] = {
    "Company Profile": {
        "icon": None,
        "sections": [
            ("Mission & Vision", "mission_vision"),
            ("Company History", "company_history"),
            ("Key Achievements", "key_achievements"),
        ]
    },
    "Products & Market Position": {
        "icon": None,
        "sections": [
            ("Products & Services", "detailed_products_services"),
            ("Unique Value Proposition", "unique_selling_proposition"),
            ("Target Customers", "target_audience"),
            ("User Personas", "main_types_of_users"),
        ]
    },
    "Financial & Operational Analysis": {
        "icon": None,
        "sections": [
            ("Financial Overview", "financial_overview"),
            ("Business Drivers & KPIs", "business_drivers_and_kpis"),
            ("Technology & Data Sources", "primary_apps_sources_of_data"),
        ]
    },
    "Industry & Competitive Landscape": {
        "icon": None,
        "sections": [
            ("Industry Analysis", "industry_insights"),
            ("Competitive Position", "potential_business_value"),
            ("Market Drivers", "potential_business_drivers"),
        ]
    },
    "Strategic Assessment": {
        "icon": None,
        "sections": [
            ("Leadership Priorities", "board_of_directors_concerns"),
            ("Value Creation Theory", "value_theory"),
            ("Strategic Recommendations", "strategic_recommendations"),
        ]
    },
}

# =============================================================================
# Hidden/internal sections (used for context but not rendered directly)
# =============================================================================
INTERNAL_SECTIONS: list[str] = [
    "scraped_website_summary",  # Raw scrape data, used for context
]

# =============================================================================
# Helper functions for chapter configuration
# =============================================================================

def get_chapter_for_section(section_key: str) -> tuple[str | None, int]:
    """
    Get the chapter name and number for a given section key.

    Args:
        section_key: The internal section key (e.g., "mission_vision")

    Returns:
        Tuple of (chapter_name, chapter_number) or (None, -1) if not found
    """
    for chapter_num, (chapter_name, chapter_data) in enumerate(CHAPTER_CONFIG.items(), 1):
        for _section_title, key in chapter_data["sections"]:
            if key == section_key:
                return chapter_name, chapter_num
    return None, -1


def get_section_number(section_key: str) -> str:
    """
    Get the full section number (e.g., "1.2") for a given section key.

    Args:
        section_key: The internal section key (e.g., "company_history")

    Returns:
        Section number string (e.g., "1.2") or empty string if not found
    """
    for chapter_num, (_chapter_name, chapter_data) in enumerate(CHAPTER_CONFIG.items(), 1):
        for section_idx, (_section_title, key) in enumerate(chapter_data["sections"], 1):
            if key == section_key:
                return f"{chapter_num}.{section_idx}"
    return ""


def get_all_section_keys() -> list[str]:
    """
    Get all section keys in chapter order.

    Returns:
        List of section keys in the order they appear in chapters
    """
    keys = []
    for chapter_data in CHAPTER_CONFIG.values():
        for _section_title, key in chapter_data["sections"]:
            keys.append(key)
    return keys


def is_section_in_chapters(section_key: str) -> bool:
    """
    Check if a section key is included in the chapter structure.

    Args:
        section_key: The internal section key

    Returns:
        True if the section is in a chapter, False otherwise
    """
    return get_section_number(section_key) != ""
