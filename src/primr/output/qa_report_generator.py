"""
QA report generator for saving detailed analysis.
"""

import logging
from datetime import datetime
from pathlib import Path

from ..qa.models import QAAnalysis, QAReport

logger = logging.getLogger(__name__)


class QAReportGenerator:
    """Generates formatted QA reports."""

    def __init__(self, output_dir: Path | None = None):
        """
        Initialize QA report generator.

        Args:
            output_dir: Directory for output files. Defaults to 'output' in project root.
                       Directory is created lazily when first file is saved.
        """
        self._output_dir = output_dir  # Lazy - don't create until needed

    @property
    def output_dir(self) -> Path:
        """Get output directory, creating default if not set."""
        if self._output_dir is None:
            self._output_dir = Path("output")
        return self._output_dir

    @output_dir.setter
    def output_dir(self, value: Path) -> None:
        """Set output directory."""
        self._output_dir = value

    def _ensure_output_dir(self) -> None:
        """Ensure output directory exists (called before writing)."""
        self.output_dir.mkdir(exist_ok=True)

    def save_detailed_analysis(self, company_name: str, analysis: QAAnalysis) -> Path | None:
        """
        Save detailed QA analysis to file.

        Args:
            company_name: Name of company
            analysis: QA analysis results

        Returns:
            Path to saved file, or None if save failed
        """
        try:
            # Ensure output directory exists before writing
            self._ensure_output_dir()

            # Generate report content
            report = self._generate_detailed_report(company_name, analysis)

            # Create filename with timestamp (use analysis timestamp if available)
            timestamp_to_use = analysis.timestamp if analysis.timestamp else datetime.now()
            timestamp = timestamp_to_use.strftime("%m-%d-%Y_%H-%M-%S")
            clean_company_name = (
                company_name.replace(" ", "_")
                .replace("&", "and")
                .replace("/", "_")
                .replace("\\", "_")
            )
            filename = f"{clean_company_name}_QA_Report_{timestamp}.txt"
            file_path = self.output_dir / filename

            # Save to file
            file_path.write_text(report.detailed_findings, encoding="utf-8")

            logger.info(f"QA report saved: {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"Failed to save QA report for {company_name}: {e}")
            return None

    def _generate_detailed_report(self, company_name: str, analysis: QAAnalysis) -> QAReport:
        """Generate detailed QA report."""

        # Create summary
        summary = f"Overall Quality Score: {analysis.overall_score}/100"
        if analysis.overall_score < 70:
            summary += " ⚠️ NEEDS ATTENTION"

        # Build detailed findings
        findings_parts = [
            f"Quality Assessment Report for {company_name}",
            "=" * 50,
            f"Generated: {analysis.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Analysis Model: {analysis.model_used}",
            "",
            "OVERALL ASSESSMENT",
            "-" * 20,
            f"Quality Score: {analysis.overall_score}/100",
            f"Confidence Level: {analysis.confidence_assessment.overall_confidence}/100",
            "",
        ]

        # Add section scores
        if analysis.section_scores:
            findings_parts.extend(["SECTION SCORES", "-" * 15])
            for section, score in analysis.section_scores.items():
                findings_parts.append(f"{section}: {score}/100")
            findings_parts.append("")

        # Add citation check results
        findings_parts.extend(
            [
                "CITATION ANALYSIS",
                "-" * 18,
                f"Total Citations: {analysis.citation_check.total_citations}",
                f"Valid Citations: {analysis.citation_check.valid_citations}",
                f"Citation Score: {analysis.citation_check.score}/100",
            ]
        )

        if analysis.citation_check.broken_links:
            findings_parts.append("\nBroken Links:")
            for link in analysis.citation_check.broken_links:
                findings_parts.append(f"  - {link}")

        if analysis.citation_check.unsupported_claims:
            findings_parts.append("\nUnsupported Claims:")
            for claim in analysis.citation_check.unsupported_claims:
                findings_parts.append(f"  - {claim}")

        findings_parts.append("")

        # Add logic check results
        findings_parts.extend(
            ["LOGICAL CONSISTENCY", "-" * 19, f"Logic Score: {analysis.logic_check.score}/100"]
        )

        if analysis.logic_check.contradictions_found:
            findings_parts.append("\nContradictions Found:")
            for contradiction in analysis.logic_check.contradictions_found:
                findings_parts.append(f"  - {contradiction}")

        if analysis.logic_check.unsupported_leaps:
            findings_parts.append("\nUnsupported Analytical Leaps:")
            for leap in analysis.logic_check.unsupported_leaps:
                findings_parts.append(f"  - {leap}")

        findings_parts.append("")

        # Add completeness check
        findings_parts.extend(
            [
                "COMPLETENESS ASSESSMENT",
                "-" * 22,
                f"Completeness Score: {analysis.completeness_check.score}/100",
            ]
        )

        if analysis.completeness_check.missing_sections:
            findings_parts.append("\nMissing Sections:")
            for section in analysis.completeness_check.missing_sections:
                findings_parts.append(f"  - {section}")

        if analysis.completeness_check.weak_sections:
            findings_parts.append("\nWeak Sections:")
            for section in analysis.completeness_check.weak_sections:
                findings_parts.append(f"  - {section}")

        findings_parts.append("")

        # Add detailed issues
        if analysis.issues:
            findings_parts.extend(["DETAILED ISSUES", "-" * 15])

            for i, issue in enumerate(analysis.issues, 1):
                findings_parts.extend(
                    [
                        f"\n{i}. {issue.issue_type.value.upper()} - {issue.severity.value.upper()}",
                        f"   Section: {issue.section}",
                        f"   Location: {issue.location}",
                        f"   Description: {issue.description}",
                    ]
                )

                if issue.suggestion:
                    findings_parts.append(f"   Suggestion: {issue.suggestion}")

        # Generate recommendations
        recommendations = self._generate_recommendations(analysis)

        if recommendations:
            findings_parts.extend(["", "RECOMMENDATIONS", "-" * 15])
            for i, rec in enumerate(recommendations, 1):
                findings_parts.append(f"{i}. {rec}")

        detailed_findings = "\n".join(findings_parts)

        return QAReport(
            company_name=company_name,
            analysis=analysis,
            summary=summary,
            detailed_findings=detailed_findings,
            recommendations=recommendations,
            generated_at=analysis.timestamp,
        )

    def _generate_recommendations(self, analysis: QAAnalysis) -> list[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        if analysis.overall_score < 70:
            recommendations.append("Review and address critical issues before using this report")

        if analysis.citation_check.score < 80:
            recommendations.append("Verify and update citations to improve credibility")

        if analysis.logic_check.score < 80:
            recommendations.append(
                "Review logical consistency and strengthen analytical connections"
            )

        if analysis.completeness_check.score < 80:
            recommendations.append("Consider adding missing sections or strengthening weak areas")

        # Count critical and high severity issues
        critical_issues = sum(1 for issue in analysis.issues if issue.severity.value == "critical")
        high_issues = sum(1 for issue in analysis.issues if issue.severity.value == "high")

        if critical_issues > 0:
            recommendations.append(f"Address {critical_issues} critical issue(s) immediately")

        if high_issues > 0:
            recommendations.append(f"Review and fix {high_issues} high-priority issue(s)")

        if not recommendations:
            recommendations.append("Report quality is acceptable for use")

        return recommendations
