"""
Tests for the enhanced Quality Grader.

**Feature: consulting-tier-report**
"""

from datetime import datetime

import pytest

from primr.ai.quality_grader import FILLER_PHRASES, QualityGrader
from primr.core.report_models import SectionContent, SourceCitation, SourceType


def create_section(
    title: str = "Test Section",
    content: str = "This is test content with specific details about Acme Corp's $50M revenue in 2024.",
    sources: list | None = None,
) -> SectionContent:
    """Create a test section."""
    if sources is None:
        sources = [
            SourceCitation(
                url="https://example.com",
                title="Source",
                source_type=SourceType.COMPANY_WEBSITE,
                accessed_at=datetime.now(),
            )
        ]
    return SectionContent(title=title, content=content, sources=sources)


class TestQualityGraderRefinementTrigger:
    """**Property 14: Quality Refinement Trigger** - verify refinement on low scores."""

    def test_triggers_refinement_below_threshold(self):
        """Should trigger refinement when score is below threshold."""
        grader = QualityGrader(refinement_threshold=7.0)

        # Create a low-quality section
        section = create_section(
            content="TBD. In conclusion, this is basically a placeholder.", sources=[]
        )

        score = grader.grade_section(section)

        # Score should be low due to filler and missing sources
        assert score.score < 7.0
        assert score.needs_refinement is True

    def test_no_refinement_above_threshold(self):
        """Should not trigger refinement when score is above threshold."""
        grader = QualityGrader(refinement_threshold=7.0)

        # Create a high-quality section
        section = create_section(
            content="""
            Acme Corporation reported $150M in revenue for Q4 2024, representing
            a 25% year-over-year increase. The company's market share grew to 15%
            in the enterprise software segment. Key growth drivers include their
            new cloud platform, which acquired 500 new enterprise customers.
            CEO John Smith announced plans to expand into European markets in 2025.
            """,
            sources=[
                SourceCitation(
                    url="https://acme.com/investor-relations",
                    title="Acme Q4 2024 Report",
                    source_type=SourceType.COMPANY_WEBSITE,
                    accessed_at=datetime.now(),
                )
            ],
        )

        score = grader.grade_section(section)

        assert score.score >= 7.0
        assert score.needs_refinement is False

    def test_should_trigger_refinement_method(self):
        """should_trigger_refinement should return correct value."""
        grader = QualityGrader(refinement_threshold=7.0)

        from primr.core.report_models import QualityScore

        low_score = QualityScore(score=5.0, issues=[], suggestions=[], needs_refinement=True)
        high_score = QualityScore(score=8.0, issues=[], suggestions=[], needs_refinement=False)

        assert grader.should_trigger_refinement(low_score) is True
        assert grader.should_trigger_refinement(high_score) is False


class TestQualityGraderFillerDetection:
    """**Property 15: No Filler Content** - verify no common filler phrases."""

    @pytest.mark.parametrize("filler_phrase", FILLER_PHRASES[:10])  # Test first 10
    def test_detects_filler_phrases(self, filler_phrase):
        """Should detect common filler phrases."""
        grader = QualityGrader()

        content = f"The company is growing. {filler_phrase}, this is important."
        section = create_section(content=content)

        score = grader.grade_section(section)

        # Should have issues related to filler
        filler_issues = [i for i in score.issues if "filler" in i.lower()]
        assert len(filler_issues) > 0, f"Should detect filler phrase: {filler_phrase}"

    def test_validate_no_filler_returns_true_for_clean_content(self):
        """validate_no_filler should return True for clean content."""
        grader = QualityGrader()

        clean_content = """
        Acme Corporation achieved $50M in revenue during Q3 2024.
        The company expanded into three new markets and hired 200 employees.
        Their flagship product saw 40% adoption growth among enterprise customers.
        """

        assert grader.validate_no_filler(clean_content) is True

    def test_validate_no_filler_returns_false_for_filler_content(self):
        """validate_no_filler should return False when filler is present."""
        grader = QualityGrader()

        filler_content = "In conclusion, it is important to note that the company is growing."

        assert grader.validate_no_filler(filler_content) is False

    def test_detects_placeholder_text(self):
        """Should detect placeholder text like TBD, N/A."""
        grader = QualityGrader()

        section = create_section(content="Revenue: TBD. Market share: N/A.")
        score = grader.grade_section(section)

        assert any("filler" in issue.lower() for issue in score.issues)


class TestQualityGraderFormatting:
    """Test formatting checks."""

    def test_detects_emojis(self):
        """Should detect emoji characters."""
        grader = QualityGrader()

        section = create_section(content="Great results! 🎉 Revenue up 20%!")
        score = grader.grade_section(section)

        assert any("emoji" in issue.lower() for issue in score.issues)

    def test_detects_em_dashes(self):
        """Should detect em-dash characters."""
        grader = QualityGrader()

        section = create_section(content="The company—a leader in tech—grew rapidly.")
        score = grader.grade_section(section)

        assert any("em-dash" in issue.lower() for issue in score.issues)

    def test_detects_numbered_headings(self):
        """Should detect numbered headings."""
        grader = QualityGrader()

        section = create_section(content="1. Executive Summary\nThe company is growing.")
        score = grader.grade_section(section)

        assert any("numbered" in issue.lower() for issue in score.issues)

    def test_check_formatting_returns_all_issues(self):
        """check_formatting should return all formatting issues."""
        grader = QualityGrader()

        text = "1. Summary 🎉\nThe company—a leader—is great."
        issues = grader.check_formatting(text)

        assert len(issues) >= 2  # At least emoji and em-dash


class TestQualityGraderContentLength:
    """Test content length validation."""

    def test_penalizes_short_content(self):
        """Should penalize content that's too short."""
        grader = QualityGrader()

        section = create_section(content="Short.")
        score = grader.grade_section(section)

        assert any("short" in issue.lower() for issue in score.issues)
        assert score.score < 10.0

    def test_accepts_adequate_length(self):
        """Should accept content of adequate length."""
        grader = QualityGrader()

        long_content = """
        Acme Corporation is a leading provider of enterprise software solutions.
        Founded in 2010, the company has grown to serve over 5,000 customers globally.
        Their flagship product, AcmeCloud, generated $150M in revenue in 2024.
        The company employs 2,000 people across offices in New York, London, and Tokyo.
        Recent strategic initiatives include expansion into the healthcare vertical.
        """

        section = create_section(content=long_content)
        score = grader.grade_section(section)

        # Should not have length issues
        assert not any("short" in issue.lower() for issue in score.issues)


class TestQualityGraderSpecificity:
    """Test specificity checking."""

    def test_penalizes_generic_content(self):
        """Should penalize overly generic content."""
        grader = QualityGrader()

        # Very generic content with many buzzwords and no specifics
        generic_content = """
        The company is an innovative, industry-leading organization with
        cutting-edge solutions. They have various products and serve numerous
        customers. Their state-of-the-art technology is best-in-class and
        world-class. They offer significant value through substantial
        improvements and considerable advantages.
        """

        section = create_section(content=generic_content)
        score = grader.grade_section(section)

        # The score should be lower than a specific content section
        # Even if "generic" isn't explicitly in issues, score should reflect it
        assert score.score < 9.0, "Generic content should have lower score"

    def test_rewards_specific_content(self):
        """Should reward specific, data-driven content."""
        grader = QualityGrader()

        specific_content = """
        Acme Corporation reported $150M in revenue for Q4 2024, a 25% increase
        from Q4 2023. The company's market share in the CRM segment grew to 12%.
        CEO Jane Smith announced plans to hire 500 engineers in 2025.
        The company's gross margin improved to 72%, up from 68% in 2023.
        """

        section = create_section(content=specific_content)
        score = grader.grade_section(section)

        # Should not have generic issues
        assert not any("generic" in issue.lower() for issue in score.issues)


class TestQualityGraderCoherence:
    """Test coherence checking across sections."""

    def test_checks_coherence_across_sections(self):
        """Should check coherence across multiple sections."""
        grader = QualityGrader()

        sections = [
            create_section(title="Executive Summary", content="Brief overview of the company."),
            create_section(title="Financial Analysis", content="Revenue was $100M in 2024."),
            create_section(
                title="Competitive Analysis", content="Main competitors include X and Y."
            ),
        ]

        issues = grader.check_coherence(sections)

        # Should return a list (may or may not have issues)
        assert isinstance(issues, list)

    def test_handles_empty_sections(self):
        """Should handle empty section list."""
        grader = QualityGrader()

        issues = grader.check_coherence([])

        assert issues == []


class TestQualityGraderReportGrading:
    """Test full report grading."""

    def test_grades_entire_report(self):
        """Should grade all sections and return average."""
        grader = QualityGrader()

        sections = [
            create_section(
                title="Executive Summary",
                content="Acme Corp achieved $100M revenue in 2024 with 20% growth.",
            ),
            create_section(
                title="Financial Overview",
                content="Q4 2024 revenue was $30M, gross margin 70%, net income $5M.",
            ),
        ]

        avg_score, issues = grader.grade_report(sections)

        assert 0.0 <= avg_score <= 10.0
        assert isinstance(issues, list)

    def test_handles_empty_report(self):
        """Should handle empty report."""
        grader = QualityGrader()

        avg_score, issues = grader.grade_report([])

        assert avg_score == 0.0
        assert "No sections" in issues[0]


class TestQualityGraderInsightValidation:
    """Test insight count validation."""

    def test_validates_minimum_insight_count(self):
        """Should validate minimum insight count."""
        grader = QualityGrader()

        insights = ["insight1", "insight2", "insight3"]

        assert grader.validate_insight_count(insights, minimum=3) is True
        assert grader.validate_insight_count(insights, minimum=5) is False

    def test_handles_empty_insights(self):
        """Should handle empty insight list."""
        grader = QualityGrader()

        assert grader.validate_insight_count([], minimum=1) is False
