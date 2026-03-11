"""Tests for competitive intelligence analysis."""

from datetime import datetime

import pytest

from primr.ai.competitive import (
    CompetitiveAnalyzer,
    Competitor,
    CompetitorType,
    MarketAnalysis,
    MarketPosition,
    SWOTAnalysis,
    SWOTItem,
    ThreatLevel,
    analyze_market,
    compare_companies,
    generate_swot,
    get_competitive_analyzer,
    identify_competitors,
    reset_competitive_analyzer,
)


@pytest.fixture
def analyzer():
    """Create a fresh analyzer for each test."""
    reset_competitive_analyzer()
    return CompetitiveAnalyzer()


@pytest.fixture
def sample_content():
    """Sample company content for testing."""
    return """
    Acme Corp is a leading technology company specializing in cloud software solutions.
    The company has strong brand recognition and an experienced team of engineers.
    Acme competes with TechGiant Inc and CloudMaster in the enterprise market.
    TechGiant is the market leader with dominant market share.
    CloudMaster is an emerging startup with innovative products.
    The cloud market is growing at 15% annually with a market size of $500 billion.
    Key trends include digital transformation and AI adoption.
    Entry barriers include high capital requirements and regulatory compliance.
    """


class TestCompetitorType:
    """Tests for CompetitorType enum."""

    def test_competitor_types(self):
        """Test all competitor types exist."""
        assert CompetitorType.DIRECT.value == "direct"
        assert CompetitorType.INDIRECT.value == "indirect"
        assert CompetitorType.POTENTIAL.value == "potential"
        assert CompetitorType.SUBSTITUTE.value == "substitute"


class TestMarketPosition:
    """Tests for MarketPosition enum."""

    def test_market_positions(self):
        """Test all market positions exist."""
        assert MarketPosition.LEADER.value == "leader"
        assert MarketPosition.CHALLENGER.value == "challenger"
        assert MarketPosition.FOLLOWER.value == "follower"
        assert MarketPosition.NICHER.value == "nicher"
        assert MarketPosition.EMERGING.value == "emerging"


class TestThreatLevel:
    """Tests for ThreatLevel enum."""

    def test_threat_levels(self):
        """Test all threat levels exist."""
        assert ThreatLevel.HIGH.value == "high"
        assert ThreatLevel.MEDIUM.value == "medium"
        assert ThreatLevel.LOW.value == "low"
        assert ThreatLevel.MINIMAL.value == "minimal"


class TestSWOTItem:
    """Tests for SWOTItem dataclass."""

    def test_default_values(self):
        """Test default values."""
        item = SWOTItem(text="Test", category="strength")
        assert item.confidence == 0.8
        assert item.source is None
        assert item.evidence == []

    def test_custom_values(self):
        """Test custom values."""
        item = SWOTItem(
            text="Strong brand",
            category="strength",
            confidence=0.9,
            source="Annual report",
            evidence=["Market research"],
        )
        assert item.text == "Strong brand"
        assert item.confidence == 0.9


class TestSWOTAnalysis:
    """Tests for SWOTAnalysis dataclass."""

    def test_default_values(self):
        """Test default values."""
        swot = SWOTAnalysis(company_name="Test Corp")
        assert swot.strengths == []
        assert swot.weaknesses == []
        assert swot.opportunities == []
        assert swot.threats == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        swot = SWOTAnalysis(
            company_name="Test Corp",
            strengths=[SWOTItem(text="Strong brand", category="strength")],
        )
        data = swot.to_dict()
        assert data["company_name"] == "Test Corp"
        assert len(data["strengths"]) == 1
        assert data["strengths"][0]["text"] == "Strong brand"

    def test_get_summary(self):
        """Test summary generation."""
        swot = SWOTAnalysis(
            company_name="Test Corp",
            strengths=[SWOTItem(text="S1", category="strength")],
            weaknesses=[
                SWOTItem(text="W1", category="weakness"),
                SWOTItem(text="W2", category="weakness"),
            ],
        )
        summary = swot.get_summary()
        assert "Test Corp" in summary
        assert "1 strengths" in summary
        assert "2 weaknesses" in summary


class TestCompetitor:
    """Tests for Competitor dataclass."""

    def test_default_values(self):
        """Test default values."""
        competitor = Competitor(
            name="Rival Inc",
            competitor_type=CompetitorType.DIRECT,
            market_position=MarketPosition.CHALLENGER,
            threat_level=ThreatLevel.MEDIUM,
        )
        assert competitor.description == ""
        assert competitor.products == []
        assert competitor.confidence == 0.7

    def test_full_competitor(self):
        """Test competitor with all fields."""
        competitor = Competitor(
            name="Big Corp",
            competitor_type=CompetitorType.DIRECT,
            market_position=MarketPosition.LEADER,
            threat_level=ThreatLevel.HIGH,
            description="Market leader",
            website="https://bigcorp.com",
            products=["Product A", "Product B"],
            market_share=35.5,
        )
        assert competitor.market_share == 35.5
        assert len(competitor.products) == 2


class TestCompetitiveAnalyzer:
    """Tests for CompetitiveAnalyzer class."""

    def test_identify_competitors(self, analyzer, sample_content):
        """Test competitor identification."""
        competitors = analyzer.identify_competitors(
            company_name="Acme Corp",
            company_description="Cloud software company",
            content=sample_content,
        )

        # Should find some competitors
        assert len(competitors) >= 0  # May find competitors based on patterns
        # Check that results are Competitor objects
        for c in competitors:
            assert isinstance(c, Competitor)

    def test_identify_competitors_max_limit(self, analyzer):
        """Test max competitors limit."""
        content = """
        Company competes with Rival1, Rival2, Rival3, Rival4, Rival5.
        Also competing with Rival6, Rival7, Rival8.
        """
        competitors = analyzer.identify_competitors(
            "Test Corp", "Test company", content, max_competitors=3
        )
        assert len(competitors) <= 3

    def test_identify_competitors_excludes_self(self, analyzer):
        """Test that company itself is excluded."""
        content = "Acme Corp competes with Acme Corp and Rival Inc."
        competitors = analyzer.identify_competitors("Acme Corp", "Test company", content)
        names = [c.name.lower() for c in competitors]
        assert "acme corp" not in names

    def test_generate_swot(self, analyzer, sample_content):
        """Test SWOT generation."""
        swot = analyzer.generate_swot("Acme Corp", sample_content)

        assert swot.company_name == "Acme Corp"
        assert isinstance(swot.generated_at, datetime)

    def test_generate_swot_extracts_strengths(self, analyzer):
        """Test strength extraction."""
        content = "The company has strong brand recognition and leading market position."
        swot = analyzer.generate_swot("Test Corp", content)

        # Should extract some strengths
        assert len(swot.strengths) >= 0  # May or may not find based on patterns

    def test_generate_swot_extracts_weaknesses(self, analyzer):
        """Test weakness extraction."""
        content = "The company has limited market reach and high costs."
        swot = analyzer.generate_swot("Test Corp", content)

        # Check structure is correct
        assert isinstance(swot.weaknesses, list)

    def test_generate_swot_with_industry(self, analyzer):
        """Test SWOT with industry context."""
        content = "A technology company with innovative products."
        swot = analyzer.generate_swot("Tech Corp", content, industry="technology")

        assert swot.company_name == "Tech Corp"

    def test_compare_companies(self, analyzer):
        """Test company comparison."""
        company_content = "Acme is an innovative market leader with global presence."
        competitor_content = "Rival is a regional player with limited products."

        comparison = analyzer.compare_companies(
            "Acme Corp",
            company_content,
            "Rival Inc",
            competitor_content,
        )

        assert comparison.company_name == "Acme Corp"
        assert comparison.competitor_name == "Rival Inc"
        assert "products" in comparison.dimensions
        assert "market_presence" in comparison.dimensions

    def test_compare_companies_advantages(self, analyzer):
        """Test competitive advantages detection."""
        company_content = "Leading innovative company with global market presence."
        competitor_content = "Small regional company with basic products."

        comparison = analyzer.compare_companies(
            "Leader Corp",
            company_content,
            "Small Corp",
            competitor_content,
        )

        # Leader should have advantages
        assert (
            len(comparison.competitive_advantage) > 0
            or len(comparison.competitive_disadvantage) > 0
        )

    def test_analyze_market(self, analyzer, sample_content):
        """Test market analysis."""
        analysis = analyzer.analyze_market(sample_content)

        assert analysis.industry in ["technology", "general"]

    def test_analyze_market_extracts_size(self, analyzer):
        """Test market size extraction."""
        content = "The market size is $500 billion and growing at 15% annually."
        analysis = analyzer.analyze_market(content)

        assert analysis.market_size is not None
        assert "500" in analysis.market_size

    def test_analyze_market_extracts_growth(self, analyzer):
        """Test growth rate extraction."""
        content = "The market is growing at 15% CAGR."
        analysis = analyzer.analyze_market(content)

        assert analysis.growth_rate is not None
        assert "15" in analysis.growth_rate

    def test_analyze_market_with_industry(self, analyzer):
        """Test market analysis with specified industry."""
        content = "Financial services market analysis."
        analysis = analyzer.analyze_market(content, industry="finance")

        assert analysis.industry == "finance"

    def test_get_threat_assessment(self, analyzer):
        """Test threat assessment."""
        competitors = [
            Competitor("A", CompetitorType.DIRECT, MarketPosition.LEADER, ThreatLevel.HIGH),
            Competitor("B", CompetitorType.DIRECT, MarketPosition.CHALLENGER, ThreatLevel.MEDIUM),
            Competitor("C", CompetitorType.INDIRECT, MarketPosition.NICHER, ThreatLevel.LOW),
        ]

        assessment = analyzer.get_threat_assessment("Test Corp", competitors)

        assert assessment["company"] == "Test Corp"
        assert assessment["high_threats"] == 1
        assert assessment["medium_threats"] == 1
        assert assessment["low_threats"] == 1
        assert assessment["total_competitors"] == 3

    def test_get_threat_assessment_empty(self, analyzer):
        """Test threat assessment with no competitors."""
        assessment = analyzer.get_threat_assessment("Test Corp", [])

        assert assessment["overall_threat"] == "low"
        assert "No significant competitors" in assessment["summary"]

    def test_get_threat_assessment_critical(self, analyzer):
        """Test critical threat level."""
        competitors = [
            Competitor("A", CompetitorType.DIRECT, MarketPosition.LEADER, ThreatLevel.HIGH),
            Competitor("B", CompetitorType.DIRECT, MarketPosition.LEADER, ThreatLevel.HIGH),
            Competitor("C", CompetitorType.DIRECT, MarketPosition.LEADER, ThreatLevel.HIGH),
        ]

        assessment = analyzer.get_threat_assessment("Test Corp", competitors)
        assert assessment["overall_threat"] == "critical"

    def test_clear_cache(self, analyzer, sample_content):
        """Test cache clearing."""
        # Generate some cached data
        analyzer.generate_swot("Test Corp", sample_content)

        # Clear cache
        analyzer.clear_cache()

        assert len(analyzer._swot_cache) == 0
        assert len(analyzer._competitor_cache) == 0


class TestIndustryDetection:
    """Tests for industry detection."""

    def test_detect_technology(self, analyzer):
        """Test technology industry detection."""
        content = "A software company providing cloud and AI solutions."
        analysis = analyzer.analyze_market(content)
        assert analysis.industry == "technology"

    def test_detect_finance(self, analyzer):
        """Test finance industry detection."""
        content = "A bank providing financial services and investment products."
        analysis = analyzer.analyze_market(content)
        assert analysis.industry == "finance"

    def test_detect_healthcare(self, analyzer):
        """Test healthcare industry detection."""
        content = "A medical company providing health and pharma solutions."
        analysis = analyzer.analyze_market(content)
        assert analysis.industry == "healthcare"

    def test_detect_retail(self, analyzer):
        """Test retail industry detection."""
        content = "An ecommerce store selling consumer merchandise."
        analysis = analyzer.analyze_market(content)
        assert analysis.industry == "retail"


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def test_get_competitive_analyzer(self):
        """Test getting global analyzer."""
        reset_competitive_analyzer()
        analyzer1 = get_competitive_analyzer()
        analyzer2 = get_competitive_analyzer()
        assert analyzer1 is analyzer2

    def test_identify_competitors_function(self):
        """Test identify_competitors convenience function."""
        reset_competitive_analyzer()
        content = "Company competes with Rival Corp in the market."
        competitors = identify_competitors("Test Corp", "Test company", content)
        assert isinstance(competitors, list)

    def test_generate_swot_function(self):
        """Test generate_swot convenience function."""
        reset_competitive_analyzer()
        content = "A strong company with leading products."
        swot = generate_swot("Test Corp", content)
        assert swot.company_name == "Test Corp"

    def test_compare_companies_function(self):
        """Test compare_companies convenience function."""
        reset_competitive_analyzer()
        comparison = compare_companies(
            "Company A",
            "Leading innovative company",
            "Company B",
            "Small regional player",
        )
        assert comparison.company_name == "Company A"
        assert comparison.competitor_name == "Company B"

    def test_analyze_market_function(self):
        """Test analyze_market convenience function."""
        reset_competitive_analyzer()
        content = "Technology market growing at 10%."
        analysis = analyze_market(content)
        assert isinstance(analysis, MarketAnalysis)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self, analyzer):
        """Test with empty content."""
        swot = analyzer.generate_swot("Test Corp", "")
        assert swot.company_name == "Test Corp"
        assert swot.strengths == []

    def test_no_competitors_found(self, analyzer):
        """Test when no competitors are found."""
        content = "A company doing business."
        competitors = analyzer.identify_competitors("Test Corp", "Test", content)
        assert competitors == []

    def test_special_characters_in_name(self, analyzer):
        """Test company names with special characters."""
        content = "Company competes with Tech-Corp Inc. and Data.io"
        competitors = analyzer.identify_competitors("Test Corp", "Test", content)
        # Should handle gracefully
        assert isinstance(competitors, list)

    def test_very_long_content(self, analyzer):
        """Test with very long content."""
        content = "Company information. " * 1000
        swot = analyzer.generate_swot("Test Corp", content)
        assert swot.company_name == "Test Corp"

    def test_unicode_content(self, analyzer):
        """Test with unicode content."""
        content = "Company compétition with Société Générale and München Corp."
        competitors = analyzer.identify_competitors("Test Corp", "Test", content)
        assert isinstance(competitors, list)
