"""
Issue classification and scoring system for QA analysis.
"""

import logging

from .models import ClassifiedIssue, IssueType, QAAnalysis, Severity

logger = logging.getLogger(__name__)


class IssueClassifier:
    """Classifies and scores QA issues for comprehensive quality assessment."""

    def __init__(self):
        """Initialize the issue classifier."""
        self.severity_weights = {
            Severity.CRITICAL: 1.0,
            Severity.HIGH: 0.7,
            Severity.MEDIUM: 0.4,
            Severity.LOW: 0.1
        }

        self.issue_type_weights = {
            IssueType.FACTUAL: 1.0,
            IssueType.LOGICAL: 0.8,
            IssueType.CITATION: 0.6,
            IssueType.COMPLETENESS: 0.5
        }

    def classify_issues(self, issues: list[ClassifiedIssue]) -> dict[str, list[ClassifiedIssue]]:
        """
        Classify issues by type and severity.

        Args:
            issues: List of classified issues

        Returns:
            Dictionary mapping classification keys to issue lists
        """
        classification = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "factual": [],
            "logical": [],
            "citation": [],
            "completeness": []
        }

        for issue in issues:
            # Classify by severity
            severity_key = issue.severity.value
            if severity_key in classification:
                classification[severity_key].append(issue)

            # Classify by type
            type_key = issue.issue_type.value
            if type_key in classification:
                classification[type_key].append(issue)

        return classification

    def calculate_severity_impact(self, issues: list[ClassifiedIssue]) -> float:
        """
        Calculate the overall severity impact of issues.

        Args:
            issues: List of classified issues

        Returns:
            Severity impact score (0.0 to 1.0, where 1.0 is maximum impact)
        """
        if not issues:
            return 0.0

        total_impact = 0.0
        max_possible_impact = len(issues) * self.severity_weights[Severity.CRITICAL]

        for issue in issues:
            severity_weight = self.severity_weights.get(issue.severity, 0.1)
            type_weight = self.issue_type_weights.get(issue.issue_type, 0.5)

            # Combined impact considers both severity and type importance
            issue_impact = severity_weight * type_weight
            total_impact += issue_impact

        # Normalize to 0-1 range
        if max_possible_impact > 0:
            return min(total_impact / max_possible_impact, 1.0)

        return 0.0

    def calculate_overall_score(self, analysis: QAAnalysis) -> int:
        """
        Calculate overall quality score based on all analysis components.

        Args:
            analysis: Complete QA analysis

        Returns:
            Overall score (0-100)
        """
        # Component scores with weights
        component_scores = {
            'citation': (analysis.citation_check.score, 0.25),
            'logic': (analysis.logic_check.score, 0.25),
            'completeness': (analysis.completeness_check.score, 0.25),
            'confidence': (analysis.confidence_assessment.overall_confidence, 0.15),
            'issues': (self._calculate_issues_score(analysis.issues), 0.10)
        }

        # Calculate weighted average
        weighted_sum = 0.0
        total_weight = 0.0

        for _component, (score, weight) in component_scores.items():
            if score is not None and 0 <= score <= 100:
                weighted_sum += score * weight
                total_weight += weight

        if total_weight > 0:
            base_score = weighted_sum / total_weight
        else:
            base_score = 50  # Neutral score if no valid components

        # Apply issue severity penalty
        severity_impact = self.calculate_severity_impact(analysis.issues)
        severity_penalty = severity_impact * 20  # Up to 20 point penalty

        final_score = max(0, min(100, base_score - severity_penalty))
        return round(final_score)

    def _calculate_issues_score(self, issues: list[ClassifiedIssue]) -> int:
        """
        Calculate a score based on the number and severity of issues.

        Args:
            issues: List of classified issues

        Returns:
            Issues score (0-100, where 100 means no significant issues)
        """
        if not issues:
            return 100

        # Count issues by severity
        severity_counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0
        }

        for issue in issues:
            severity_counts[issue.severity] += 1

        # Calculate penalty based on issue counts and severity
        penalty = 0
        penalty += severity_counts[Severity.CRITICAL] * 25  # 25 points per critical
        penalty += severity_counts[Severity.HIGH] * 15     # 15 points per high
        penalty += severity_counts[Severity.MEDIUM] * 8    # 8 points per medium
        penalty += severity_counts[Severity.LOW] * 3       # 3 points per low

        # Cap penalty at 90 points (minimum score of 10)
        penalty = min(penalty, 90)

        return max(10, 100 - penalty)

    def ensure_score_consistency(self, analysis: QAAnalysis) -> QAAnalysis:
        """
        Ensure score consistency across section-level and overall assessments.

        Args:
            analysis: QA analysis to check for consistency

        Returns:
            Updated analysis with consistent scores
        """
        # Calculate overall score using our algorithm
        calculated_overall = self.calculate_overall_score(analysis)

        # Check if the existing overall score is reasonable
        if abs(analysis.overall_score - calculated_overall) > 15:
            logger.info(f"Adjusting overall score from {analysis.overall_score} to {calculated_overall} for consistency")
            analysis.overall_score = calculated_overall

        # Ensure section scores are reasonable relative to overall score
        if analysis.section_scores:
            section_average = sum(analysis.section_scores.values()) / len(analysis.section_scores)

            # If section average is very different from overall, log a warning
            if abs(section_average - analysis.overall_score) > 20:
                logger.warning(f"Section score average ({section_average:.1f}) differs significantly from overall score ({analysis.overall_score})")

        return analysis

    def get_issue_location_specificity(self, issues: list[ClassifiedIssue]) -> dict[str, int]:
        """
        Analyze how specific issue locations are.

        Args:
            issues: List of classified issues

        Returns:
            Dictionary with location specificity metrics
        """
        if not issues:
            return {
                "total_issues": 0,
                "specific_locations": 0,
                "vague_locations": 0,
                "specificity_score": 100
            }

        specific_count = 0
        vague_count = 0

        # Keywords that indicate specific locations
        specific_keywords = ["line", "paragraph", "page", "table", "figure", "citation"]

        # Keywords that indicate vague locations (check these first)
        vague_keywords = ["general", "overall", "throughout", "various", "multiple", "many"]

        for issue in issues:
            location_lower = issue.location.lower()

            # Check vague keywords first (they take precedence)
            if any(keyword in location_lower for keyword in vague_keywords):
                vague_count += 1
            elif any(keyword in location_lower for keyword in specific_keywords):
                specific_count += 1
            elif len(issue.location.strip()) < 10:  # Very short location descriptions
                vague_count += 1
            else:
                specific_count += 1  # Assume specific if not obviously vague

        total_issues = len(issues)
        specificity_score = int((specific_count / total_issues) * 100) if total_issues > 0 else 100

        return {
            "total_issues": total_issues,
            "specific_locations": specific_count,
            "vague_locations": vague_count,
            "specificity_score": specificity_score
        }
