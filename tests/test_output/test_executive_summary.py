"""
Tests for the executive summary generation module.
"""

import pytest

from primr.output.executive_summary import (
    ExecutiveSummaryGenerator,
    ExecutiveSummary,
    KeyFinding,
    FindingCategory,
    ConfidenceIndicator,
    SourceCitation,
    get_summary_generator,
    reset_summary_generator,
    generate_executive_summary,
    generate_one_liner,
    extract_key_points,
    format_executive_summary,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_summary_generator()
    yield
    reset_summary_generator()


@pytest.fixture
def generator():
    """Create a fresh generator."""
    return ExecutiveSummaryGenerator()


@pytest.fixture
def sample_sections():
    """Sample research sections."""
    return {
        "overview": """
        Acme Corporation is a leading technology company founded in 2010.
        The company specializes in cloud computing solutions and has grown
        to become a major player in the enterprise software market.
        Acme is headquartered in San Francisco, California.
        """,
        "financials": """
        Acme reported revenue of $2.5 billion in fiscal year 2024,
        representing 25% year-over-year growth. The company achieved
        profitability for the first time with net income of $150 million.
        Gross margin improved to 72% from 68% in the prior year.
        """,
        "leadership": """
        CEO John Smith has led the company since 2015. Under his leadership,
        Acme has expanded into 50 countries and grown from 500 to 5,000 employees.
        CFO Jane Doe joined in 2020 and has strengthened financial operations.
        """,
        "products": """
        Acme's flagship product is CloudPlatform, an enterprise cloud solution.
        The company launched three new products in 2024: DataSync, SecureVault,
        and AnalyticsHub. These products have been well-received by customers.
        """,
    }


@pytest.fixture
def sample_sources():
    """Sample source list."""
    return [
        {"title": "Acme Official Website", "url": "https://acme.com"},
        {"title": "Bloomberg Profile", "url": "https://bloomberg.com/acme"},
        {"title": "SEC Filing", "url": "https://sec.gov/acme"},
    ]


# =============================================================================
# KEY FINDING TESTS
# =============================================================================

class TestKeyFinding:
    """Tests for KeyFinding dataclass."""
    
    def test_confidence_icon_high(self):
        """Test high confidence icon."""
        finding = KeyFinding(
            category=FindingCategory.FINANCIAL,
            summary="Revenue grew 25%",
            confidence=ConfidenceIndicator.HIGH,
        )
        assert finding.confidence_icon == "✓✓"
    
    def test_confidence_icon_medium(self):
        """Test medium confidence icon."""
        finding = KeyFinding(
            category=FindingCategory.FINANCIAL,
            summary="Revenue grew 25%",
            confidence=ConfidenceIndicator.MEDIUM,
        )
        assert finding.confidence_icon == "✓"
    
    def test_confidence_icon_low(self):
        """Test low confidence icon."""
        finding = KeyFinding(
            category=FindingCategory.FINANCIAL,
            summary="Revenue may grow",
            confidence=ConfidenceIndicator.LOW,
        )
        assert finding.confidence_icon == "?"


# =============================================================================
# SOURCE CITATION TESTS
# =============================================================================

class TestSourceCitation:
    """Tests for SourceCitation dataclass."""
    
    def test_format_inline(self):
        """Test inline citation format."""
        citation = SourceCitation(
            title="Acme Website",
            url="https://acme.com",
        )
        formatted = citation.format_citation("inline")
        assert "[Acme Website]" in formatted
        assert "(https://acme.com)" in formatted
    
    def test_format_footnote(self):
        """Test footnote citation format."""
        citation = SourceCitation(
            title="Acme Website",
            url="https://acme.com",
        )
        formatted = citation.format_citation("footnote")
        assert "Acme Website" in formatted
        assert "Available at:" in formatted


# =============================================================================
# EXECUTIVE SUMMARY TESTS
# =============================================================================

class TestExecutiveSummary:
    """Tests for ExecutiveSummary dataclass."""
    
    def test_swot_available_true(self):
        """Test SWOT available when data exists."""
        summary = ExecutiveSummary(
            company_name="Acme",
            strengths=["Strong brand"],
        )
        assert summary.swot_available is True
    
    def test_swot_available_false(self):
        """Test SWOT not available when empty."""
        summary = ExecutiveSummary(company_name="Acme")
        assert summary.swot_available is False


# =============================================================================
# GENERATOR TESTS
# =============================================================================

class TestExecutiveSummaryGenerator:
    """Tests for ExecutiveSummaryGenerator class."""
    
    def test_generate_basic(self, generator, sample_sections):
        """Test basic summary generation."""
        summary = generator.generate("Acme Corp", sample_sections)
        
        assert isinstance(summary, ExecutiveSummary)
        assert summary.company_name == "Acme Corp"
        assert summary.one_liner != ""
        assert summary.overview != ""
    
    def test_generate_with_sources(self, generator, sample_sections, sample_sources):
        """Test generation with sources."""
        summary = generator.generate("Acme Corp", sample_sections, sample_sources)
        
        assert len(summary.sources) == 3
        assert summary.sources[0].title == "Acme Official Website"
    
    def test_generate_key_findings(self, generator, sample_sections):
        """Test key findings extraction."""
        summary = generator.generate("Acme Corp", sample_sections)
        
        assert len(summary.key_findings) > 0
        assert all(isinstance(f, KeyFinding) for f in summary.key_findings)
    
    def test_generate_recommendations(self, generator, sample_sections):
        """Test recommendations generation."""
        summary = generator.generate("Acme Corp", sample_sections)
        
        assert len(summary.recommendations) > 0
    
    def test_confidence_score(self, generator, sample_sections, sample_sources):
        """Test confidence score calculation."""
        summary = generator.generate("Acme Corp", sample_sections, sample_sources)
        
        assert 0 <= summary.confidence_score <= 1


# =============================================================================
# ONE-LINER TESTS
# =============================================================================

class TestOneLiner:
    """Tests for one-liner generation."""
    
    def test_generate_one_liner(self, generator):
        """Test one-liner generation."""
        content = "Acme Corp is a leading technology company in the cloud computing industry."
        one_liner = generator.generate_one_liner("Acme Corp", content)
        
        assert "Acme" in one_liner
        assert len(one_liner) > 20
    
    def test_one_liner_ends_with_period(self, generator):
        """Test one-liner ends with period."""
        content = "Acme Corp provides enterprise software solutions"
        one_liner = generator.generate_one_liner("Acme Corp", content)
        
        assert one_liner.endswith(".")


# =============================================================================
# KEY POINTS TESTS
# =============================================================================

class TestKeyPoints:
    """Tests for key points extraction."""
    
    def test_extract_key_points(self, generator):
        """Test key points extraction."""
        content = """
        The company reported strong revenue growth of 25%.
        New product launches drove customer acquisition.
        Market share increased to 15% in the enterprise segment.
        The CEO announced expansion plans for Asia.
        """
        points = generator.extract_key_points(content, max_points=3)
        
        assert len(points) <= 3
        assert all(isinstance(p, str) for p in points)
    
    def test_key_points_end_with_period(self, generator):
        """Test key points end with period."""
        content = "Revenue grew 25%. Profits increased. Market share expanded."
        points = generator.extract_key_points(content)
        
        for point in points:
            assert point.endswith(".")
    
    def test_key_points_skip_short(self, generator):
        """Test short sentences are skipped."""
        content = "OK. This is a longer sentence with meaningful content."
        points = generator.extract_key_points(content)
        
        # "OK." should be skipped
        assert not any("OK" == p.strip(".") for p in points)


# =============================================================================
# FORMATTING TESTS
# =============================================================================

class TestFormatting:
    """Tests for summary formatting."""
    
    def test_format_markdown(self, generator, sample_sections):
        """Test markdown formatting."""
        summary = generator.generate("Acme Corp", sample_sections)
        formatted = generator.format_summary(summary, "markdown")
        
        assert "# Executive Summary" in formatted
        assert "## Overview" in formatted
        assert "Acme Corp" in formatted
    
    def test_format_text(self, generator, sample_sections):
        """Test plain text formatting."""
        summary = generator.generate("Acme Corp", sample_sections)
        formatted = generator.format_summary(summary, "text")
        
        assert "EXECUTIVE SUMMARY" in formatted
        assert "OVERVIEW" in formatted
    
    def test_format_html(self, generator, sample_sections):
        """Test HTML formatting."""
        summary = generator.generate("Acme Corp", sample_sections)
        formatted = generator.format_summary(summary, "html")
        
        assert "<div class=\"executive-summary\">" in formatted
        assert "<h1>" in formatted
        assert "Acme Corp" in formatted


# =============================================================================
# CATEGORIZATION TESTS
# =============================================================================

class TestCategorization:
    """Tests for content categorization."""
    
    def test_categorize_financial(self, generator):
        """Test financial content categorization."""
        content = "Revenue grew 25% with strong profit margins."
        category = generator._categorize_content(content)
        
        assert category == FindingCategory.FINANCIAL
    
    def test_categorize_leadership(self, generator):
        """Test leadership content categorization."""
        content = "CEO John Smith announced new executive appointments."
        category = generator._categorize_content(content)
        
        assert category == FindingCategory.LEADERSHIP
    
    def test_categorize_products(self, generator):
        """Test products content categorization."""
        content = "The company launched a new product platform with advanced features."
        category = generator._categorize_content(content)
        
        assert category == FindingCategory.PRODUCTS_SERVICES


# =============================================================================
# CONFIDENCE ESTIMATION TESTS
# =============================================================================

class TestConfidenceEstimation:
    """Tests for confidence estimation."""
    
    def test_high_confidence_indicators(self, generator):
        """Test high confidence detection."""
        text = "The company confirmed revenue of $2 billion."
        confidence = generator._estimate_confidence(text)
        
        assert confidence == ConfidenceIndicator.HIGH
    
    def test_low_confidence_indicators(self, generator):
        """Test low confidence detection."""
        text = "The company may possibly expand into new markets."
        confidence = generator._estimate_confidence(text)
        
        assert confidence == ConfidenceIndicator.LOW
    
    def test_medium_confidence_default(self, generator):
        """Test medium confidence as default."""
        text = "The company operates in the technology sector."
        confidence = generator._estimate_confidence(text)
        
        assert confidence == ConfidenceIndicator.MEDIUM


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""
    
    def test_get_generator_returns_same(self):
        """Test get_summary_generator returns same instance."""
        g1 = get_summary_generator()
        g2 = get_summary_generator()
        assert g1 is g2
    
    def test_reset_generator(self):
        """Test reset creates new instance."""
        g1 = get_summary_generator()
        reset_summary_generator()
        g2 = get_summary_generator()
        assert g1 is not g2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_generate_executive_summary_function(self, sample_sections):
        """Test generate_executive_summary convenience function."""
        summary = generate_executive_summary("Acme Corp", sample_sections)
        assert isinstance(summary, ExecutiveSummary)
    
    def test_generate_one_liner_function(self):
        """Test generate_one_liner convenience function."""
        one_liner = generate_one_liner("Acme", "Acme is a tech company.")
        assert isinstance(one_liner, str)
        assert len(one_liner) > 0
    
    def test_extract_key_points_function(self):
        """Test extract_key_points convenience function."""
        points = extract_key_points("Revenue grew. Profits increased.")
        assert isinstance(points, list)
    
    def test_format_executive_summary_function(self, sample_sections):
        """Test format_executive_summary convenience function."""
        summary = generate_executive_summary("Acme", sample_sections)
        formatted = format_executive_summary(summary, "markdown")
        assert isinstance(formatted, str)
        assert "Acme" in formatted


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_sections(self, generator):
        """Test with empty sections."""
        summary = generator.generate("Acme", {})
        
        assert summary.company_name == "Acme"
        assert summary.one_liner != ""
    
    def test_minimal_content(self, generator):
        """Test with minimal content."""
        sections = {"overview": "Acme is a company."}
        summary = generator.generate("Acme", sections)
        
        assert summary is not None
    
    def test_no_sources(self, generator, sample_sections):
        """Test without sources."""
        summary = generator.generate("Acme", sample_sections, None)
        
        assert summary.sources == []
    
    def test_special_characters_in_name(self, generator, sample_sections):
        """Test company name with special characters."""
        summary = generator.generate("Acme & Co.", sample_sections)
        
        assert summary.company_name == "Acme & Co."
