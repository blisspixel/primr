"""
Enhanced Quality Grader for consulting-tier reports.

Evaluates section quality, checks for filler content, validates formatting,
and triggers refinement when needed.
"""

import re

from primr.core.report_models import QualityScore, SectionContent
from primr.utils.formatting import (
    has_em_dashes,
    has_emojis,
    has_nested_numbering,
    has_numbered_headings,
)
from primr.utils.logging_config import get_logger

logger = get_logger("quality_grader")


# Common filler phrases to detect
FILLER_PHRASES = [
    "in conclusion",
    "it is important to note",
    "as mentioned above",
    "as previously stated",
    "needless to say",
    "it goes without saying",
    "at the end of the day",
    "moving forward",
    "going forward",
    "in today's world",
    "in this day and age",
    "it should be noted",
    "it is worth noting",
    "as we all know",
    "obviously",
    "clearly",
    "basically",
    "essentially",
    "fundamentally",
    "TBD",
    "N/A",
    "to be determined",
    "information not available",
    "[placeholder]",
    "[insert",
    "lorem ipsum",
]

# Minimum content length by section type
MIN_CONTENT_LENGTH = {
    "executive_summary": 200,
    "industry_analysis": 300,
    "financial_overview": 200,
    "competitive_analysis": 300,
    "strategic_recommendations": 250,
    "default": 150,
}


class QualityGrader:
    """Evaluates and grades report section quality."""

    def __init__(self, refinement_threshold: float = 7.0):
        """
        Initialize the quality grader.

        Args:
            refinement_threshold: Score below which refinement is triggered (0-10)
        """
        self.refinement_threshold = refinement_threshold

    def grade_section(self, content: SectionContent, section_type: str = "default") -> QualityScore:
        """
        Grade a section's quality.

        Args:
            content: The section content to grade
            section_type: Type of section for context-specific grading

        Returns:
            QualityScore with score, issues, and suggestions
        """
        issues = []
        suggestions = []
        score = 10.0

        text = content.content

        # Check content length
        min_length = MIN_CONTENT_LENGTH.get(section_type, MIN_CONTENT_LENGTH["default"])
        if len(text) < min_length:
            issues.append(f"Content too short ({len(text)} chars, minimum {min_length})")
            suggestions.append("Add more detailed analysis and supporting information")
            score -= 2.0

        # Check for filler content
        filler_found = self._check_filler_content(text)
        if filler_found:
            issues.extend([f"Contains filler phrase: '{phrase}'" for phrase in filler_found])
            suggestions.append("Remove generic filler phrases and add specific insights")
            score -= len(filler_found) * 0.5

        # Check formatting issues
        formatting_issues = self.check_formatting(text)
        if formatting_issues:
            issues.extend(formatting_issues)
            suggestions.append("Clean up formatting issues (emojis, em-dashes, numbered headings)")
            score -= len(formatting_issues) * 0.3

        # Check for source citations
        if not content.sources and section_type not in ["executive_summary"]:
            issues.append("No source citations provided")
            suggestions.append("Add source citations to support claims")
            score -= 1.0

        # Check for specificity (avoid generic statements)
        generic_score = self._check_specificity(text)
        if generic_score <= 0.6:
            issues.append("Content appears too generic")
            suggestions.append("Add company-specific details and concrete examples")
            score -= 2.0

        # Ensure score stays in valid range
        score = max(0.0, min(10.0, score))

        return QualityScore(
            score=score,
            issues=issues,
            suggestions=suggestions,
            needs_refinement=score < self.refinement_threshold,
        )

    def _check_filler_content(self, text: str) -> list[str]:
        """
        Check for common filler phrases.

        Args:
            text: Content to check

        Returns:
            List of filler phrases found
        """
        found = []
        text_lower = text.lower()

        for phrase in FILLER_PHRASES:
            if phrase.lower() in text_lower:
                found.append(phrase)

        return found

    def _check_specificity(self, text: str) -> float:
        """
        Check how specific the content is (vs generic).

        Args:
            text: Content to check

        Returns:
            Specificity score from 0.0 (generic) to 1.0 (specific)
        """
        # Indicators of specific content
        specific_indicators = [
            r"\$[\d,]+",  # Dollar amounts
            r"\d+%",  # Percentages
            r"\d{4}",  # Years
            r"Q[1-4]\s*\d{4}",  # Quarters
            r"[A-Z][a-z]+\s+[A-Z][a-z]+",  # Proper names
            r"\d+\s*(million|billion|thousand|M|B|K)",  # Numbers with units
        ]

        # Generic phrases that reduce specificity
        generic_phrases = [
            "various",
            "several",
            "many",
            "some",
            "numerous",
            "significant",
            "substantial",
            "considerable",
            "industry-leading",
            "best-in-class",
            "world-class",
            "innovative",
            "cutting-edge",
            "state-of-the-art",
        ]

        specific_count = 0
        for pattern in specific_indicators:
            specific_count += len(re.findall(pattern, text, re.IGNORECASE))

        generic_count = 0
        text_lower = text.lower()
        for phrase in generic_phrases:
            generic_count += text_lower.count(phrase)

        # Calculate score based on ratio
        # If lots of generic phrases and few specifics, score low
        if generic_count > 3 and specific_count < 2:
            return 0.2

        total = specific_count + generic_count
        if total == 0:
            return 0.5  # Neutral if no indicators

        return min(1.0, specific_count / (total + 1))

    def check_formatting(self, text: str) -> list[str]:
        """
        Check for formatting issues.

        Args:
            text: Content to check

        Returns:
            List of formatting issues found
        """
        issues = []

        if has_emojis(text):
            issues.append("Contains emoji characters")

        if has_em_dashes(text):
            issues.append("Contains em-dash characters")

        if has_numbered_headings(text):
            issues.append("Contains numbered headings")

        if has_nested_numbering(text):
            issues.append("Contains nested numbering schemes")

        return issues

    def check_coherence(self, sections: list[SectionContent]) -> list[str]:
        """
        Check coherence across multiple sections.

        Args:
            sections: List of sections to check

        Returns:
            List of coherence issues found
        """
        issues: list[str] = []

        if not sections:
            return issues

        # Check for contradictory information
        # This is a simplified check - could be enhanced with NLP
        key_facts: dict[str, str] = {}

        for section in sections:
            # Extract potential facts (numbers, percentages)
            numbers = re.findall(
                r"(\$?[\d,]+(?:\.\d+)?)\s*(million|billion|M|B|%)?", section.content
            )

            for match in numbers:
                value, unit = match
                # Store for comparison (simplified)
                key = f"{value}{unit}"
                if key in key_facts:
                    if key_facts[key] != section.title:
                        # Same number appears in different contexts - might be ok
                        pass
                else:
                    key_facts[key] = section.title

        # Check for missing cross-references
        section_titles = [s.title.lower() for s in sections]

        # Check if executive summary references key sections
        exec_summary = next((s for s in sections if "executive" in s.title.lower()), None)
        if exec_summary:
            key_topics = ["financial", "competitive", "strategic", "risk"]
            for topic in key_topics:
                if topic not in exec_summary.content.lower():
                    if any(topic in title for title in section_titles):
                        issues.append(
                            f"Executive summary may not adequately cover {topic} analysis"
                        )

        return issues

    def validate_no_filler(self, content: str) -> bool:
        """
        Validate that content contains no filler phrases.

        Args:
            content: Text to validate

        Returns:
            True if no filler found, False otherwise
        """
        return len(self._check_filler_content(content)) == 0

    def validate_insight_count(self, insights: list, minimum: int = 3) -> bool:
        """
        Validate minimum insight count.

        Args:
            insights: List of insights
            minimum: Minimum required count

        Returns:
            True if count meets minimum
        """
        return len(insights) >= minimum

    def should_trigger_refinement(self, score: QualityScore) -> bool:
        """
        Determine if refinement should be triggered.

        Args:
            score: Quality score to evaluate

        Returns:
            True if refinement needed
        """
        return score.needs_refinement

    def grade_report(self, sections: list[SectionContent]) -> tuple[float, list[str]]:
        """
        Grade an entire report.

        Args:
            sections: All sections in the report

        Returns:
            Tuple of (average score, list of all issues)
        """
        if not sections:
            return 0.0, ["No sections to grade"]

        total_score = 0.0
        all_issues = []

        for section in sections:
            section_type = self._infer_section_type(section.title)
            score = self.grade_section(section, section_type)
            total_score += score.score
            all_issues.extend(score.issues)

        # Add coherence issues
        coherence_issues = self.check_coherence(sections)
        all_issues.extend(coherence_issues)

        avg_score = total_score / len(sections)

        return avg_score, all_issues

    def _infer_section_type(self, title: str) -> str:
        """Infer section type from title."""
        title_lower = title.lower()

        if "executive" in title_lower or "summary" in title_lower:
            return "executive_summary"
        elif "industry" in title_lower:
            return "industry_analysis"
        elif "financial" in title_lower:
            return "financial_overview"
        elif "competitive" in title_lower or "competitor" in title_lower:
            return "competitive_analysis"
        elif "strategic" in title_lower or "recommendation" in title_lower:
            return "strategic_recommendations"
        else:
            return "default"
