"""
Tests for the Deep Research result normalizer.

These tests verify that Deep Research output is correctly
normalized to the section format expected by report generation.
"""

from primr.ai.result_normalizer import (
    ResultNormalizer,
    normalize_deep_research,
)


class TestResultNormalizer:
    """Tests for ResultNormalizer class."""

    def test_normalize_empty_content(self):
        """Empty content returns empty dict."""
        normalizer = ResultNormalizer()
        result = normalizer.normalize("")
        assert result == {}

    def test_normalize_simple_sections(self):
        """Parse simple markdown sections."""
        content = """
## Executive Summary

This is the executive summary.

## Products & Services

The company offers various products.

## Financial Analysis

Revenue is $5 billion.
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'company_overview' in result
        assert 'executive summary' in result['company_overview'].lower() or 'This is the executive summary' in result['company_overview']
        assert 'detailed_products_services' in result
        assert 'financial_overview' in result

    def test_normalize_with_subsections(self):
        """Parse content with H3 subsections."""
        content = """
## Company Overview

Main overview content.

### History

Founded in 2010.

### Mission

To innovate.
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'company_overview' in result
        # Subsections should be included in parent
        assert 'History' in result['company_overview'] or 'Founded' in result['company_overview']

    def test_normalize_competitive_section(self):
        """Map competitive landscape to correct section."""
        content = """
## Competitive Landscape

Key competitors include:
- Competitor A
- Competitor B
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'competitive_position' in result
        assert 'Competitor A' in result['competitive_position']

    def test_normalize_strategic_section(self):
        """Map strategic assessment to recommendations."""
        content = """
## Strategic Assessment

### Opportunities
- Market expansion
- New products

### Risks
- Competition
- Regulation
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'strategic_recommendations' in result

    def test_normalize_no_sections_uses_overview(self):
        """Content without sections goes to company_overview."""
        content = """
This is just plain text without any markdown headers.
It should all go into the company overview section.
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'company_overview' in result
        assert 'plain text' in result['company_overview']

    def test_clean_content_removes_extra_whitespace(self):
        """Clean content removes excessive blank lines."""
        normalizer = ResultNormalizer()
        content = """
Line 1


Line 2



Line 3
"""
        cleaned = normalizer._clean_content(content)

        # Should not have more than one consecutive blank line
        assert '\n\n\n' not in cleaned

    def test_map_header_variations(self):
        """Various header phrasings map correctly."""
        normalizer = ResultNormalizer()

        test_cases = [
            ('Executive Summary', 'company_overview'),
            ('Company Overview', 'company_overview'),
            ('Products & Services', 'detailed_products_services'),
            ('Products and Services', 'detailed_products_services'),
            ('Financial Analysis', 'financial_overview'),
            ('Financials', 'financial_overview'),
            ('Competitive Landscape', 'competitive_position'),
            ('Competition', 'competitive_position'),
            ('Industry Analysis', 'industry_insights'),
            ('Strategic Recommendations', 'strategic_recommendations'),
            ('Company History', 'company_history'),
            ('Mission and Vision', 'mission_vision'),
        ]

        for header, expected_key in test_cases:
            result = normalizer._map_header_to_section(header)
            assert result == expected_key, f"Header '{header}' should map to '{expected_key}', got '{result}'"


class TestCitationExtraction:
    """Tests for citation extraction."""

    def test_extract_markdown_links(self):
        """Extract [text](url) style citations."""
        normalizer = ResultNormalizer()
        content = """
According to [Company Website](https://example.com), revenue grew 15%.
See also [Annual Report](https://example.com/report.pdf).
"""
        citations = normalizer.extract_citations(content)

        assert len(citations) == 2
        assert citations[0].text == 'Company Website'
        assert citations[0].url == 'https://example.com'

    def test_extract_source_citations(self):
        """Extract Source: url style citations."""
        normalizer = ResultNormalizer()
        content = """
Revenue data from Source: https://example.com/data
"""
        citations = normalizer.extract_citations(content)

        assert len(citations) >= 1

    def test_no_citations(self):
        """Content without citations returns empty list."""
        normalizer = ResultNormalizer()
        content = "Just plain text without any citations."
        citations = normalizer.extract_citations(content)

        assert citations == []


class TestConvenienceFunction:
    """Tests for normalize_deep_research function."""

    def test_normalize_deep_research_function(self):
        """Convenience function works correctly."""
        content = """
## Executive Summary

Test content.
"""
        result = normalize_deep_research(content)

        assert isinstance(result, dict)
        assert 'company_overview' in result


class TestSectionTitleMapping:
    """Tests for section title retrieval."""

    def test_get_section_title(self):
        """Get display title for section key."""
        normalizer = ResultNormalizer()

        # Known section
        title = normalizer.get_section_title('financial_overview')
        assert title  # Should return something

        # Unknown section
        title = normalizer.get_section_title('unknown_section')
        assert title == 'Unknown Section'


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_content(self):
        """Handle unicode characters in content."""
        content = """
## Company Overview

Revenue: $5.2B
Growth: 15%
Employees: 10,000
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'company_overview' in result
        assert '$5.2B' in result['company_overview']

    def test_special_characters_in_headers(self):
        """Handle special characters in headers."""
        content = """
## Products & Services (2024)

Product list here.
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'detailed_products_services' in result

    def test_very_long_content(self):
        """Handle very long content."""
        long_text = "This is a test. " * 1000
        content = f"""
## Executive Summary

{long_text}
"""
        normalizer = ResultNormalizer()
        result = normalizer.normalize(content)

        assert 'company_overview' in result
        assert len(result['company_overview']) > 1000
