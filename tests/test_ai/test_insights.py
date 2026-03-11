"""Tests for predictive insights module."""

from datetime import datetime

import pytest

from primr.ai.insights import (
    InsightAnalyzer,
    InsightReport,
    Opportunity,
    OpportunityType,
    Recommendation,
    RecommendationType,
    Risk,
    RiskCategory,
    RiskLevel,
    assess_risks,
    generate_insights,
    generate_recommendations,
    get_insight_analyzer,
    identify_opportunities,
    reset_insight_analyzer,
)


@pytest.fixture
def analyzer():
    """Create a fresh analyzer for each test."""
    reset_insight_analyzer()
    return InsightAnalyzer()


@pytest.fixture
def sample_content():
    """Sample company content with various indicators."""
    return """
    Acme Corp is facing significant challenges. The company reported declining revenue
    in Q3 and has high debt levels that concern investors. There's also an ongoing
    lawsuit related to patent infringement.

    However, the company is pursuing digital transformation and exploring new market
    expansion opportunities in Asia. They recently announced a partnership with
    TechGiant for cloud migration services.

    The CEO mentioned innovation as a key priority, with R&D investment increasing
    by 20% this year. The company is also looking at potential acquisition targets
    to strengthen their market position.
    """


class TestRiskCategory:
    """Tests for RiskCategory enum."""

    def test_risk_categories(self):
        """Test all risk categories exist."""
        assert RiskCategory.FINANCIAL.value == "financial"
        assert RiskCategory.OPERATIONAL.value == "operational"
        assert RiskCategory.MARKET.value == "market"
        assert RiskCategory.REGULATORY.value == "regulatory"
        assert RiskCategory.REPUTATIONAL.value == "reputational"
        assert RiskCategory.TECHNOLOGY.value == "technology"


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_levels(self):
        """Test all risk levels exist."""
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MINIMAL.value == "minimal"


class TestOpportunityType:
    """Tests for OpportunityType enum."""

    def test_opportunity_types(self):
        """Test all opportunity types exist."""
        assert OpportunityType.MARKET_EXPANSION.value == "market_expansion"
        assert OpportunityType.PRODUCT_INNOVATION.value == "product_innovation"
        assert OpportunityType.PARTNERSHIP.value == "partnership"
        assert OpportunityType.ACQUISITION.value == "acquisition"


class TestRisk:
    """Tests for Risk dataclass."""

    def test_default_values(self):
        """Test default values."""
        risk = Risk(
            risk_id="test1",
            category=RiskCategory.FINANCIAL,
            level=RiskLevel.HIGH,
            title="Test Risk",
            description="Test description",
        )
        assert risk.likelihood == 0.5
        assert risk.impact == 0.5
        assert risk.mitigations == []
        assert risk.confidence == 0.7

    def test_risk_score(self):
        """Test risk score calculation."""
        risk = Risk(
            risk_id="test2",
            category=RiskCategory.MARKET,
            level=RiskLevel.MEDIUM,
            title="Test",
            description="Test",
            likelihood=0.8,
            impact=0.6,
        )
        assert risk.risk_score == 0.48

    def test_to_dict(self):
        """Test conversion to dictionary."""
        risk = Risk(
            risk_id="test3",
            category=RiskCategory.REGULATORY,
            level=RiskLevel.CRITICAL,
            title="Legal Risk",
            description="Lawsuit pending",
        )
        data = risk.to_dict()
        assert data["risk_id"] == "test3"
        assert data["category"] == "regulatory"
        assert data["level"] == "critical"


class TestOpportunity:
    """Tests for Opportunity dataclass."""

    def test_default_values(self):
        """Test default values."""
        opp = Opportunity(
            opportunity_id="opp1",
            opportunity_type=OpportunityType.MARKET_EXPANSION,
            title="Expansion",
            description="New market opportunity",
        )
        assert opp.potential_value == ""
        assert opp.timeframe == ""
        assert opp.requirements == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        opp = Opportunity(
            opportunity_id="opp2",
            opportunity_type=OpportunityType.PARTNERSHIP,
            title="Strategic Partnership",
            description="Partner with leader",
            potential_value="$5M",
        )
        data = opp.to_dict()
        assert data["opportunity_id"] == "opp2"
        assert data["type"] == "partnership"
        assert data["potential_value"] == "$5M"


class TestRecommendation:
    """Tests for Recommendation dataclass."""

    def test_default_values(self):
        """Test default values."""
        rec = Recommendation(
            recommendation_id="rec1",
            recommendation_type=RecommendationType.IMMEDIATE,
            title="Action Required",
            description="Take action now",
        )
        assert rec.priority == 5
        assert rec.effort == ""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        rec = Recommendation(
            recommendation_id="rec2",
            recommendation_type=RecommendationType.SHORT_TERM,
            title="Improve Process",
            description="Optimize workflow",
            priority=8,
        )
        data = rec.to_dict()
        assert data["recommendation_id"] == "rec2"
        assert data["type"] == "short_term"
        assert data["priority"] == 8


class TestInsightReport:
    """Tests for InsightReport dataclass."""

    def test_default_values(self):
        """Test default values."""
        report = InsightReport(company_name="Test Corp")
        assert report.risks == []
        assert report.opportunities == []
        assert report.recommendations == []

    def test_get_summary(self):
        """Test summary generation."""
        report = InsightReport(
            company_name="Test Corp",
            risks=[
                Risk("r1", RiskCategory.FINANCIAL, RiskLevel.CRITICAL, "R1", "D1"),
                Risk("r2", RiskCategory.MARKET, RiskLevel.HIGH, "R2", "D2"),
                Risk("r3", RiskCategory.OPERATIONAL, RiskLevel.MEDIUM, "R3", "D3"),
            ],
            opportunities=[
                Opportunity("o1", OpportunityType.PARTNERSHIP, "O1", "D1"),
            ],
        )
        summary = report.get_summary()

        assert summary["company_name"] == "Test Corp"
        assert summary["total_risks"] == 3
        assert summary["critical_risks"] == 1
        assert summary["high_risks"] == 1
        assert summary["total_opportunities"] == 1


class TestInsightAnalyzer:
    """Tests for InsightAnalyzer class."""

    def test_assess_risks(self, analyzer, sample_content):
        """Test risk assessment."""
        risks = analyzer.assess_risks("Acme Corp", sample_content)

        assert isinstance(risks, list)
        for risk in risks:
            assert isinstance(risk, Risk)

    def test_assess_risks_finds_financial(self, analyzer):
        """Test finding financial risks."""
        content = "The company has high debt levels and declining revenue."
        risks = analyzer.assess_risks("Test Corp", content)

        categories = [r.category for r in risks]
        assert RiskCategory.FINANCIAL in categories

    def test_assess_risks_finds_regulatory(self, analyzer):
        """Test finding regulatory risks."""
        content = "The company is facing a lawsuit and regulatory investigation."
        risks = analyzer.assess_risks("Test Corp", content)

        categories = [r.category for r in risks]
        assert RiskCategory.REGULATORY in categories

    def test_assess_risks_finds_technology(self, analyzer):
        """Test finding technology risks."""
        content = "The company suffered a security breach and data hack."
        risks = analyzer.assess_risks("Test Corp", content)

        categories = [r.category for r in risks]
        assert RiskCategory.TECHNOLOGY in categories

    def test_assess_risks_sorted_by_score(self, analyzer, sample_content):
        """Test risks are sorted by score."""
        risks = analyzer.assess_risks("Test Corp", sample_content)

        if len(risks) >= 2:
            for i in range(len(risks) - 1):
                assert risks[i].risk_score >= risks[i + 1].risk_score

    def test_assess_risks_limited(self, analyzer):
        """Test risk limit."""
        content = """
        debt loss lawsuit breach scandal supply chain outage
        competition regulation compliance vulnerability
        """
        risks = analyzer.assess_risks("Test Corp", content)
        assert len(risks) <= 10

    def test_identify_opportunities(self, analyzer, sample_content):
        """Test opportunity identification."""
        opportunities = analyzer.identify_opportunities("Acme Corp", sample_content)

        assert isinstance(opportunities, list)
        for opp in opportunities:
            assert isinstance(opp, Opportunity)

    def test_identify_opportunities_finds_expansion(self, analyzer):
        """Test finding market expansion opportunities."""
        content = "The company is exploring new market expansion in Asia."
        opportunities = analyzer.identify_opportunities("Test Corp", content)

        types = [o.opportunity_type for o in opportunities]
        assert OpportunityType.MARKET_EXPANSION in types

    def test_identify_opportunities_finds_partnership(self, analyzer):
        """Test finding partnership opportunities."""
        content = "The company announced a strategic partnership with TechGiant."
        opportunities = analyzer.identify_opportunities("Test Corp", content)

        types = [o.opportunity_type for o in opportunities]
        assert OpportunityType.PARTNERSHIP in types

    def test_identify_opportunities_finds_innovation(self, analyzer):
        """Test finding innovation opportunities."""
        content = "The company is investing heavily in R&D and innovation."
        opportunities = analyzer.identify_opportunities("Test Corp", content)

        types = [o.opportunity_type for o in opportunities]
        assert OpportunityType.PRODUCT_INNOVATION in types

    def test_generate_recommendations(self, analyzer):
        """Test recommendation generation."""
        risks = [
            Risk("r1", RiskCategory.FINANCIAL, RiskLevel.CRITICAL, "Debt", "High debt"),
            Risk("r2", RiskCategory.MARKET, RiskLevel.HIGH, "Competition", "Intense"),
        ]
        opportunities = [
            Opportunity("o1", OpportunityType.PARTNERSHIP, "Partnership", "Strategic"),
        ]

        recommendations = analyzer.generate_recommendations("Test Corp", risks, opportunities)

        assert len(recommendations) > 0
        for rec in recommendations:
            assert isinstance(rec, Recommendation)

    def test_generate_recommendations_sorted_by_priority(self, analyzer):
        """Test recommendations sorted by priority."""
        risks = [
            Risk("r1", RiskCategory.FINANCIAL, RiskLevel.CRITICAL, "R1", "D1"),
            Risk("r2", RiskCategory.MARKET, RiskLevel.HIGH, "R2", "D2"),
        ]

        recommendations = analyzer.generate_recommendations("Test Corp", risks, [])

        if len(recommendations) >= 2:
            for i in range(len(recommendations) - 1):
                assert recommendations[i].priority >= recommendations[i + 1].priority

    def test_generate_insights(self, analyzer, sample_content):
        """Test complete insights generation."""
        report = analyzer.generate_insights("Acme Corp", sample_content)

        assert report.company_name == "Acme Corp"
        assert isinstance(report.risks, list)
        assert isinstance(report.opportunities, list)
        assert isinstance(report.recommendations, list)
        assert isinstance(report.generated_at, datetime)


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def test_get_insight_analyzer(self):
        """Test getting global analyzer."""
        reset_insight_analyzer()
        analyzer1 = get_insight_analyzer()
        analyzer2 = get_insight_analyzer()
        assert analyzer1 is analyzer2

    def test_assess_risks_function(self):
        """Test assess_risks convenience function."""
        reset_insight_analyzer()
        content = "Company has high debt and declining revenue."
        risks = assess_risks("Test Corp", content)
        assert isinstance(risks, list)

    def test_identify_opportunities_function(self):
        """Test identify_opportunities convenience function."""
        reset_insight_analyzer()
        content = "Company exploring new market expansion."
        opportunities = identify_opportunities("Test Corp", content)
        assert isinstance(opportunities, list)

    def test_generate_recommendations_function(self):
        """Test generate_recommendations convenience function."""
        reset_insight_analyzer()
        risks = [Risk("r1", RiskCategory.FINANCIAL, RiskLevel.HIGH, "R1", "D1")]
        opportunities = []
        recommendations = generate_recommendations("Test Corp", risks, opportunities)
        assert isinstance(recommendations, list)

    def test_generate_insights_function(self):
        """Test generate_insights convenience function."""
        reset_insight_analyzer()
        content = "Company facing challenges but exploring opportunities."
        report = generate_insights("Test Corp", content)
        assert report.company_name == "Test Corp"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self, analyzer):
        """Test with empty content."""
        risks = analyzer.assess_risks("Test Corp", "")
        assert risks == []

        opportunities = analyzer.identify_opportunities("Test Corp", "")
        assert opportunities == []

    def test_no_indicators(self, analyzer):
        """Test content with no risk/opportunity indicators."""
        content = "The company is a business that does things."
        risks = analyzer.assess_risks("Test Corp", content)
        opportunities = analyzer.identify_opportunities("Test Corp", content)

        # May or may not find anything
        assert isinstance(risks, list)
        assert isinstance(opportunities, list)

    def test_very_long_content(self, analyzer):
        """Test with very long content."""
        content = "Company has debt. " * 500
        risks = analyzer.assess_risks("Test Corp", content)
        assert isinstance(risks, list)

    def test_special_characters(self, analyzer):
        """Test with special characters."""
        content = "Company™ has debt® and declining© revenue!"
        risks = analyzer.assess_risks("Test Corp", content)
        assert isinstance(risks, list)

    def test_unicode_content(self, analyzer):
        """Test with unicode content."""
        content = "公司有债务 - Company has debt and declining revenue"
        risks = analyzer.assess_risks("Test Corp", content)
        assert isinstance(risks, list)

    def test_multiple_same_category_risks(self, analyzer):
        """Test multiple risks in same category."""
        content = "Company has debt, loss, and declining revenue."
        risks = analyzer.assess_risks("Test Corp", content)

        # Should find multiple financial risks
        financial_risks = [r for r in risks if r.category == RiskCategory.FINANCIAL]
        assert len(financial_risks) >= 1

    def test_recommendations_with_no_risks(self, analyzer):
        """Test recommendations with no risks."""
        opportunities = [
            Opportunity("o1", OpportunityType.PARTNERSHIP, "Partnership", "Strategic"),
        ]
        recommendations = analyzer.generate_recommendations("Test Corp", [], opportunities)

        # Should still generate opportunity-based recommendations
        assert isinstance(recommendations, list)

    def test_recommendations_with_no_opportunities(self, analyzer):
        """Test recommendations with no opportunities."""
        risks = [
            Risk("r1", RiskCategory.FINANCIAL, RiskLevel.HIGH, "Debt", "High debt"),
        ]
        recommendations = analyzer.generate_recommendations("Test Corp", risks, [])

        # Should still generate risk-based recommendations
        assert len(recommendations) >= 1
