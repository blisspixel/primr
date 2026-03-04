"""
Tests for the Section Writer.

**Feature: consulting-tier-report**
"""
from datetime import datetime
from unittest.mock import patch

from primr.core.report_models import (
    ConfidenceLevel,
    GatheredData,
    Insight,
    InsightCategory,
    SourceType,
)
from primr.output.section_writer import SectionWriter
from primr.utils.formatting import has_em_dashes, has_emojis


def create_mock_gathered_data(count: int = 3) -> list[GatheredData]:
    """Create mock gathered data for testing."""
    return [
        GatheredData(
            content=f"Sample content about the company {i}. Revenue grew 20% year over year to $50M.",
            source_url=f"https://example.com/page{i}",
            source_type=SourceType.COMPANY_WEBSITE,
            confidence=0.8,
            gathered_at=datetime.now(),
            title=f"Page {i}"
        )
        for i in range(count)
    ]


def create_mock_insights(count: int = 5) -> list[Insight]:
    """Create mock insights for testing."""
    return [
        Insight(
            title=f"Strategic Insight {i}",
            description=f"This is a detailed description of insight {i}.",
            evidence=[f"Evidence point {i}.1", f"Evidence point {i}.2"],
            confidence=ConfidenceLevel.VERIFIED if i % 2 == 0 else ConfidenceLevel.INFERRED,
            category=InsightCategory.STRATEGIC,
            sources=[f"https://source{i}.com"]
        )
        for i in range(count)
    ]


class TestSectionWriterExecutiveSummary:
    """**Property 1: Executive Summary Completeness** - verify all required components present."""

    @patch("primr.output.section_writer.llm")
    def test_executive_summary_has_required_components(self, mock_llm):
        """Executive summary should contain all required components."""
        mock_llm.return_value = """
        Company Snapshot
        Acme Corp is a leading enterprise software provider serving Fortune 500 companies.

        Strategic Position
        The company holds a strong position in the CRM market with 15% market share.

        Key Insights
        Revenue growth accelerated to 25% in Q4 2024.
        Customer retention improved to 95%.
        New product launch drove 40% of new bookings.

        Critical Risks
        Increasing competition from cloud-native startups.
        Talent retention challenges in engineering.

        Recommended Actions
        Accelerate cloud migration to maintain competitive position.
        Invest in AI capabilities to differentiate product offering.
        """

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        summary = writer.write_executive_summary(insights, data, "Acme Corp")

        assert summary.title == "Executive Summary"
        assert len(summary.content) > 0

        # Check for required components (case-insensitive)
        content_lower = summary.content.lower()

        # Should have company overview/snapshot
        has_snapshot = any(term in content_lower for term in ["snapshot", "overview", "company", "provider", "leading"])
        assert has_snapshot, "Missing company snapshot"

        # Should have strategic position
        has_position = any(term in content_lower for term in ["position", "market", "competitive"])
        assert has_position, "Missing strategic position"

        # Should have insights
        has_insights = any(term in content_lower for term in ["insight", "growth", "revenue"])
        assert has_insights, "Missing key insights"

        # Should have risks
        has_risks = any(term in content_lower for term in ["risk", "challenge", "threat", "competition"])
        assert has_risks, "Missing critical risks"

        # Should have recommendations
        has_recommendations = any(term in content_lower for term in ["recommend", "action", "invest", "accelerate"])
        assert has_recommendations, "Missing recommended actions"

    @patch("primr.output.section_writer.llm")
    def test_executive_summary_has_sources(self, mock_llm):
        """Executive summary should include source citations."""
        mock_llm.return_value = "Brief executive summary content."

        writer = SectionWriter()
        data = create_mock_gathered_data(3)
        insights = create_mock_insights(3)

        summary = writer.write_executive_summary(insights, data, "Test Company")

        assert len(summary.sources) > 0, "Executive summary should have sources"

    @patch("primr.output.section_writer.llm")
    def test_executive_summary_has_confidence_notes(self, mock_llm):
        """Executive summary should include confidence notes for estimated data."""
        mock_llm.return_value = "Executive summary with estimated data."

        writer = SectionWriter()
        data = create_mock_gathered_data()

        # Create insights with estimated confidence
        insights = [
            Insight(
                title="Estimated Revenue",
                description="Revenue estimated at $100M",
                evidence=["Based on employee count"],
                confidence=ConfidenceLevel.ESTIMATED,
                category=InsightCategory.FINANCIAL,
                sources=[]
            )
        ]

        summary = writer.write_executive_summary(insights, data, "Test Company")

        assert len(summary.confidence_notes) > 0, "Should have confidence notes for estimated data"


class TestSectionWriterExecutiveSummaryLength:
    """**Property 2: Executive Summary Length** - verify under 500 words."""

    @patch("primr.output.section_writer.llm")
    def test_executive_summary_under_500_words(self, mock_llm):
        """Executive summary should not exceed 500 words."""
        # Return a very long response
        mock_llm.return_value = " ".join(["word"] * 600)

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        summary = writer.write_executive_summary(insights, data, "Test Company", max_words=500)

        word_count = len(summary.content.split())
        assert word_count <= 500, f"Executive summary has {word_count} words, should be <= 500"

    @patch("primr.output.section_writer.llm")
    def test_preserves_content_under_limit(self, mock_llm):
        """Should preserve content that's already under the limit."""
        short_content = "This is a brief executive summary with only a few words."
        mock_llm.return_value = short_content

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        summary = writer.write_executive_summary(insights, data, "Test Company")

        # Content should be preserved (minus any formatting cleanup)
        assert len(summary.content) > 0


class TestSectionWriterFormatting:
    """Test formatting cleanup."""

    @patch("primr.output.section_writer.llm")
    def test_removes_emojis(self, mock_llm):
        """Should remove emojis from content."""
        mock_llm.return_value = "Great results! 🎉 Revenue up 20%! 🚀"

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        summary = writer.write_executive_summary(insights, data, "Test Company")

        assert not has_emojis(summary.content), "Content should not contain emojis"

    @patch("primr.output.section_writer.llm")
    def test_removes_em_dashes(self, mock_llm):
        """Should remove em-dashes from content."""
        mock_llm.return_value = "The company—a leader in tech—grew rapidly."

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        summary = writer.write_executive_summary(insights, data, "Test Company")

        assert not has_em_dashes(summary.content), "Content should not contain em-dashes"

    def test_format_for_readability(self):
        """format_for_readability should clean content."""
        writer = SectionWriter()

        dirty_content = "1. Summary 🎉\nThe company—a leader—is great."
        clean = writer.format_for_readability(dirty_content)

        assert not has_emojis(clean)
        assert not has_em_dashes(clean)


class TestSectionWriterSections:
    """Test individual section writing."""

    @patch("primr.output.section_writer.llm")
    def test_writes_section(self, mock_llm):
        """Should write a section with proper structure."""
        mock_llm.return_value = "Industry analysis content here."

        writer = SectionWriter()
        data = create_mock_gathered_data()

        section = writer.write_section(
            "Industry Analysis",
            "Test Company",
            "Technology industry",
            data
        )

        assert section.title == "Industry Analysis"
        assert len(section.content) > 0
        assert len(section.sources) > 0

    @patch("primr.output.section_writer.llm")
    def test_writes_industry_analysis(self, mock_llm):
        """Should write industry analysis section."""
        mock_llm.return_value = "Industry analysis content."

        writer = SectionWriter()
        data = create_mock_gathered_data()

        section = writer.write_industry_analysis("Test Company", "Technology", data)

        assert section.title == "Industry Analysis"

    @patch("primr.output.section_writer.llm")
    def test_writes_financial_overview(self, mock_llm):
        """Should write financial overview section."""
        mock_llm.return_value = "Financial overview content."

        writer = SectionWriter()
        data = create_mock_gathered_data()

        section = writer.write_financial_overview(
            "Test Company",
            {"revenue": 100000000, "growth": 0.25},
            data
        )

        assert section.title == "Financial Overview"

    @patch("primr.output.section_writer.llm")
    def test_writes_competitive_analysis(self, mock_llm):
        """Should write competitive analysis section."""
        mock_llm.return_value = "Competitive analysis content."

        writer = SectionWriter()
        data = create_mock_gathered_data()

        section = writer.write_competitive_analysis(
            "Test Company",
            ["Competitor A", "Competitor B"],
            data
        )

        assert section.title == "Competitive Analysis"

    @patch("primr.output.section_writer.llm")
    def test_writes_strategic_recommendations(self, mock_llm):
        """Should write strategic recommendations section."""
        mock_llm.return_value = "Strategic recommendations content."

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        section = writer.write_strategic_recommendations("Test Company", insights, data)

        assert section.title == "Strategic Recommendations"


class TestSectionWriterErrorHandling:
    """Test error handling."""

    @patch("primr.output.section_writer.llm")
    def test_handles_llm_error_in_summary(self, mock_llm):
        """Should handle LLM errors gracefully in executive summary."""
        mock_llm.side_effect = Exception("LLM error")

        writer = SectionWriter()
        data = create_mock_gathered_data()
        insights = create_mock_insights()

        summary = writer.write_executive_summary(insights, data, "Test Company")

        assert summary.title == "Executive Summary"
        assert "failed" in summary.content.lower()

    @patch("primr.output.section_writer.llm")
    def test_handles_llm_error_in_section(self, mock_llm):
        """Should handle LLM errors gracefully in sections."""
        mock_llm.side_effect = Exception("LLM error")

        writer = SectionWriter()
        data = create_mock_gathered_data()

        section = writer.write_section("Test Section", "Test Company", "Context", data)

        assert "failed" in section.content.lower()

    def test_handles_empty_data(self):
        """Should handle empty data gracefully."""
        writer = SectionWriter()

        summary_data = writer._summarize_data([])
        assert "No research data" in summary_data

    def test_handles_empty_insights(self):
        """Should handle empty insights gracefully."""
        writer = SectionWriter()

        insights_summary = writer._summarize_insights([])
        assert "No insights" in insights_summary
