"""
Tests for the AI Strategy Analyzer.

Includes property-based tests for AI opportunity generation.
"""

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from primr.ai.ai_strategy import (
    VENDOR_TECHNOLOGIES,
    AICategory,
    AIOpportunity,
    AIStrategyAnalyzer,
    CloudVendor,
    analyze_ai_strategy,
)

# =============================================================================
# Unit Tests
# =============================================================================

class TestAIStrategyAnalyzer:
    """Unit tests for AIStrategyAnalyzer class."""

    def test_analyze_returns_five_opportunities(self):
        """Analyze always returns exactly 5 opportunities."""
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze("Acme Corp", "technology")

        assert len(opportunities) == 5

    def test_analyze_with_azure_vendor(self):
        """Azure vendor returns Azure-specific technologies."""
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(
            "Acme Corp",
            "technology",
            cloud_vendor=CloudVendor.AZURE
        )

        # All technologies should be from Azure catalog
        azure_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.AZURE].values():
            azure_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in azure_techs, f"Technology {tech} not in Azure catalog"

    def test_analyze_with_aws_vendor(self):
        """AWS vendor returns AWS-specific technologies."""
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(
            "Acme Corp",
            "retail",
            cloud_vendor=CloudVendor.AWS
        )

        aws_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.AWS].values():
            aws_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in aws_techs, f"Technology {tech} not in AWS catalog"

    def test_analyze_with_gcp_vendor(self):
        """GCP vendor returns GCP-specific technologies."""
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(
            "Acme Corp",
            "manufacturing",
            cloud_vendor=CloudVendor.GCP
        )

        gcp_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.GCP].values():
            gcp_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in gcp_techs, f"Technology {tech} not in GCP catalog"

    def test_opportunity_has_all_required_fields(self):
        """Each opportunity has all required fields."""
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze("Acme Corp", "healthcare")

        for opp in opportunities:
            assert opp.title, "Missing title"
            assert opp.description, "Missing description"
            assert opp.category is not None, "Missing category"
            assert len(opp.technologies) > 0, "Missing technologies"
            assert opp.business_impact, "Missing business_impact"

    def test_industry_affects_categories(self):
        """Different industries get different category priorities."""
        analyzer = AIStrategyAnalyzer()

        healthcare_opps = analyzer.analyze("Hospital Inc", "healthcare")
        tech_opps = analyzer.analyze("Tech Corp", "technology")

        healthcare_cats = {o.category for o in healthcare_opps}
        tech_cats = {o.category for o in tech_opps}

        # Healthcare should prioritize automation
        assert AICategory.AUTOMATION in healthcare_cats
        # Tech should prioritize productivity
        assert AICategory.PRODUCTIVITY in tech_cats

    def test_agnostic_vendor_works(self):
        """Agnostic vendor returns generic technologies."""
        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(
            "Acme Corp",
            "retail",
            cloud_vendor=CloudVendor.AGNOSTIC
        )

        assert len(opportunities) == 5
        # Should have generic tech names
        all_techs = []
        for opp in opportunities:
            all_techs.extend(opp.technologies)

        # Agnostic techs shouldn't have vendor-specific names
        vendor_specific = ["Azure", "AWS", "Amazon", "Google", "GCP"]
        for tech in all_techs:
            for vendor_name in vendor_specific:
                assert vendor_name not in tech, f"Agnostic tech {tech} contains vendor name"


class TestConvenienceFunction:
    """Tests for analyze_ai_strategy convenience function."""

    def test_analyze_ai_strategy_basic(self):
        """Convenience function works with basic inputs."""
        opportunities = analyze_ai_strategy("Acme Corp", "retail")

        assert len(opportunities) == 5

    def test_analyze_ai_strategy_with_vendor_string(self):
        """Convenience function accepts vendor as string."""
        opportunities = analyze_ai_strategy(
            "Acme Corp",
            "technology",
            cloud_vendor="azure"
        )

        assert len(opportunities) == 5
        # Should have Azure technologies
        azure_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.AZURE].values():
            azure_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in azure_techs


class TestAIOpportunity:
    """Tests for AIOpportunity dataclass."""

    def test_to_dict(self):
        """to_dict returns proper dictionary."""
        opp = AIOpportunity(
            title="Test Opportunity",
            description="Test description",
            category=AICategory.CONVERSATIONAL,
            technologies=["Tech1", "Tech2"],
            business_impact="High impact",
            implementation_complexity="Medium",
            estimated_timeline="3 months"
        )

        d = opp.to_dict()

        assert d["title"] == "Test Opportunity"
        assert d["category"] == "conversational"
        assert d["technologies"] == ["Tech1", "Tech2"]


# =============================================================================
# Property-Based Tests
# =============================================================================

class TestAIOpportunityCount:
    """
    **Feature: consulting-tier-report, Property 21: AI Opportunity Count**
    **Validates: Requirements 13.2**

    For any AI strategy analysis, the AIStrategyAnalyzer SHALL produce exactly 5 AI opportunities.
    """

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        company=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=['L', 'N', 'S'])),
        industry=st.sampled_from(["healthcare", "retail", "technology", "manufacturing", "financial", ""])
    )
    def test_always_returns_five_opportunities(self, company, industry):
        """Analyzer always returns exactly 5 opportunities."""
        company = company.strip()
        assume(len(company) > 0)

        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(company, industry)

        assert len(opportunities) == 5


class TestAIOpportunityStructure:
    """
    **Feature: consulting-tier-report, Property 22: AI Opportunity Structure**
    **Validates: Requirements 13.7**

    For any generated AI opportunity, it SHALL contain all required fields:
    title, description, category, technologies, business_impact.
    """

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(
        company=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=['L'])),
        vendor=st.sampled_from([CloudVendor.AZURE, CloudVendor.AWS, CloudVendor.GCP, CloudVendor.AGNOSTIC])
    )
    def test_all_opportunities_have_required_fields(self, company, vendor):
        """Every opportunity has all required fields populated."""
        company = company.strip()
        assume(len(company) > 0)

        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(company, "technology", cloud_vendor=vendor)

        for opp in opportunities:
            assert opp.title, "title is required"
            assert len(opp.title) > 0, "title must not be empty"
            assert opp.description, "description is required"
            assert len(opp.description) > 0, "description must not be empty"
            assert opp.category is not None, "category is required"
            assert isinstance(opp.category, AICategory), "category must be AICategory"
            assert opp.technologies, "technologies is required"
            assert len(opp.technologies) > 0, "technologies must not be empty"
            assert opp.business_impact, "business_impact is required"
            assert len(opp.business_impact) > 0, "business_impact must not be empty"


class TestVendorTechnologyAlignment:
    """
    **Feature: consulting-tier-report, Property 23: Vendor Technology Alignment**
    **Validates: Requirements 13.3, 13.4, 13.5**

    For any AI opportunity generated with a specific cloud vendor, the technologies
    list SHALL only contain technologies from that vendor's catalog.
    """

    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    @given(
        company=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=['L'])),
        industry=st.sampled_from(["healthcare", "retail", "technology", "manufacturing"])
    )
    def test_azure_technologies_only(self, company, industry):
        """Azure vendor only returns Azure technologies."""
        company = company.strip()
        assume(len(company) >= 3)

        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(company, industry, cloud_vendor=CloudVendor.AZURE)

        azure_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.AZURE].values():
            azure_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in azure_techs, f"Technology '{tech}' not in Azure catalog"

    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    @given(
        company=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=['L'])),
        industry=st.sampled_from(["healthcare", "retail", "technology", "manufacturing"])
    )
    def test_aws_technologies_only(self, company, industry):
        """AWS vendor only returns AWS technologies."""
        company = company.strip()
        assume(len(company) >= 3)

        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(company, industry, cloud_vendor=CloudVendor.AWS)

        aws_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.AWS].values():
            aws_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in aws_techs, f"Technology '{tech}' not in AWS catalog"

    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    @given(
        company=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=['L'])),
        industry=st.sampled_from(["healthcare", "retail", "technology", "manufacturing"])
    )
    def test_gcp_technologies_only(self, company, industry):
        """GCP vendor only returns GCP technologies."""
        company = company.strip()
        assume(len(company) >= 3)

        analyzer = AIStrategyAnalyzer()
        opportunities = analyzer.analyze(company, industry, cloud_vendor=CloudVendor.GCP)

        gcp_techs = set()
        for cat_techs in VENDOR_TECHNOLOGIES[CloudVendor.GCP].values():
            gcp_techs.update(cat_techs)

        for opp in opportunities:
            for tech in opp.technologies:
                assert tech in gcp_techs, f"Technology '{tech}' not in GCP catalog"
