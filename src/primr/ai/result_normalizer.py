"""
Result Normalizer for Deep Research output.

Converts Deep Research Agent output into the section format
expected by the report generation system.
"""

import re
from dataclasses import dataclass

from primr.config.sections_config import SECTION_KEY_MAP
from primr.utils.logging_config import get_logger

logger = get_logger("ai.result_normalizer")


@dataclass
class Citation:
    """A citation extracted from research content."""
    text: str
    url: str
    title: str | None = None


@dataclass
class NormalizedSection:
    """A normalized section with content and metadata."""
    key: str
    title: str
    content: str
    citations: list[Citation]


class ResultNormalizer:
    """
    Normalizes Deep Research output to section format.

    The Deep Research Agent produces markdown-formatted reports.
    This class parses that output and maps it to the section
    structure expected by DocumentBuilder.

    Example:
        normalizer = ResultNormalizer()
        sections = normalizer.normalize(deep_research_content)
        # sections = {'company_overview': '...', 'financial_overview': '...'}
    """

    # Mapping from Deep Research headers to section keys
    HEADER_MAPPINGS = {
        # Executive/Overview sections
        'executive summary': 'company_overview',
        'company overview': 'company_overview',
        'overview': 'company_overview',
        'about': 'company_overview',
        'introduction': 'company_overview',

        # Products/Services
        'products & services': 'detailed_products_services',
        'products and services': 'detailed_products_services',
        'products': 'detailed_products_services',
        'services': 'detailed_products_services',
        'offerings': 'detailed_products_services',

        # Financial
        'financial analysis': 'financial_overview',
        'financial overview': 'financial_overview',
        'financials': 'financial_overview',
        'financial performance': 'financial_overview',
        'revenue': 'financial_overview',

        # Competitive
        'competitive landscape': 'competitive_position',
        'competitive analysis': 'competitive_position',
        'competition': 'competitive_position',
        'competitors': 'competitive_position',
        'market position': 'competitive_position',

        # Industry
        'industry analysis': 'industry_insights',
        'industry overview': 'industry_insights',
        'industry': 'industry_insights',
        'market analysis': 'industry_insights',
        'market overview': 'industry_insights',

        # Strategic
        'strategic assessment': 'strategic_recommendations',
        'strategy': 'strategic_recommendations',
        'recommendations': 'strategic_recommendations',
        'strategic recommendations': 'strategic_recommendations',
        'opportunities': 'strategic_recommendations',

        # History/Background
        'history': 'company_history',
        'company history': 'company_history',
        'background': 'company_history',
        'founding': 'company_history',

        # Mission/Vision
        'mission': 'mission_vision',
        'vision': 'mission_vision',
        'mission and vision': 'mission_vision',
        'mission & vision': 'mission_vision',
        'values': 'mission_vision',

        # Leadership
        'leadership': 'board_of_directors_concerns',
        'management': 'board_of_directors_concerns',
        'executive team': 'board_of_directors_concerns',
        'leadership team': 'board_of_directors_concerns',

        # Customers/Users
        'target market': 'target_audience',
        'target audience': 'target_audience',
        'customers': 'main_types_of_users',
        'users': 'main_types_of_users',
        'customer segments': 'main_types_of_users',

        # Value Proposition
        'value proposition': 'unique_selling_proposition',
        'unique value': 'unique_selling_proposition',
        'differentiation': 'unique_selling_proposition',
        'competitive advantage': 'unique_selling_proposition',

        # KPIs/Metrics
        'kpis': 'business_drivers_and_kpis',
        'key metrics': 'business_drivers_and_kpis',
        'business drivers': 'business_drivers_and_kpis',
        'performance metrics': 'business_drivers_and_kpis',

        # Risks
        'risks': 'potential_business_value',
        'challenges': 'potential_business_value',
        'threats': 'potential_business_value',

        # Achievements
        'achievements': 'key_achievements',
        'milestones': 'key_achievements',
        'accomplishments': 'key_achievements',
    }

    # Citation patterns
    CITATION_PATTERNS = [
        # [Source](url)
        re.compile(r'\[([^\]]+)\]\(([^)]+)\)'),
        # Source: url
        re.compile(r'Source:\s*(\S+)'),
        # (Source: url)
        re.compile(r'\(Source:\s*([^)]+)\)'),
    ]

    def __init__(self):
        """Initialize the normalizer."""
        self._reverse_section_map = {v: k for k, v in SECTION_KEY_MAP.items()}

    def normalize(self, content: str) -> dict[str, str]:
        """
        Normalize Deep Research content to section format.

        Args:
            content: Raw markdown content from Deep Research

        Returns:
            Dict mapping section_key to content
        """
        if not content:
            return {}

        # Parse sections from markdown
        parsed_sections = self._parse_markdown_sections(content)

        # Map to standard section keys
        normalized = {}
        for header, section_content in parsed_sections.items():
            section_key = self._map_header_to_section(header)
            if section_key:
                # Clean the content
                cleaned = self._clean_content(section_content)
                if cleaned:
                    normalized[section_key] = cleaned

        # If no sections were parsed, use entire content as overview
        if not normalized:
            normalized['company_overview'] = self._clean_content(content)

        logger.info(f"Normalized {len(normalized)} sections from Deep Research")
        return normalized

    def _parse_markdown_sections(self, content: str) -> dict[str, str]:
        """Parse markdown content into sections by headers."""
        sections: dict[str, str] = {}
        current_header: str | None = None
        current_content: list[str] = []

        for line in content.split('\n'):
            # Check for H2 headers (## Header)
            if line.startswith('## '):
                # Save previous section
                if current_header is not None:
                    sections[current_header] = '\n'.join(current_content)

                # Start new section
                current_header = line[3:].strip()
                current_content = []

            # Check for H3 headers (### Header) - treat as subsection
            elif line.startswith('### ') and current_header:
                # Include as part of current section
                current_content.append(line)

            else:
                current_content.append(line)

        # Save last section
        if current_header is not None:
            sections[current_header] = '\n'.join(current_content)

        return sections

    def _map_header_to_section(self, header: str) -> str | None:
        """Map a markdown header to a section key."""
        header_lower = header.lower().strip()

        # Direct mapping
        if header_lower in self.HEADER_MAPPINGS:
            return self.HEADER_MAPPINGS[header_lower]

        # Partial matching
        for pattern, section_key in self.HEADER_MAPPINGS.items():
            if pattern in header_lower or header_lower in pattern:
                return section_key

        # Generate a key from the header
        generated_key = header_lower.replace(' ', '_').replace('&', 'and')
        generated_key = re.sub(r'[^a-z0-9_]', '', generated_key)

        logger.debug(f"No mapping for header '{header}', using '{generated_key}'")
        return generated_key

    def _clean_content(self, content: str) -> str:
        """Clean and normalize content."""
        if not content:
            return ""

        # Remove excessive whitespace
        lines = content.split('\n')
        cleaned_lines = []
        prev_empty = False

        for line in lines:
            stripped = line.rstrip()
            is_empty = not stripped

            # Skip multiple consecutive empty lines
            if is_empty and prev_empty:
                continue

            cleaned_lines.append(stripped)
            prev_empty = is_empty

        return '\n'.join(cleaned_lines).strip()

    def extract_citations(self, content: str) -> list[Citation]:
        """Extract citations from content."""
        citations = []

        for pattern in self.CITATION_PATTERNS:
            for match in pattern.finditer(content):
                if len(match.groups()) >= 2:
                    citations.append(Citation(
                        text=match.group(1),
                        url=match.group(2)
                    ))
                elif len(match.groups()) == 1:
                    url = match.group(1)
                    citations.append(Citation(
                        text=url,
                        url=url
                    ))

        return citations

    def get_section_title(self, section_key: str) -> str:
        """Get the display title for a section key."""
        return self._reverse_section_map.get(section_key, section_key.replace('_', ' ').title())


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def normalize_deep_research(content: str) -> dict[str, str]:
    """
    Convenience function to normalize Deep Research content.

    Args:
        content: Raw markdown from Deep Research

    Returns:
        Dict mapping section_key to content
    """
    normalizer = ResultNormalizer()
    return normalizer.normalize(content)
