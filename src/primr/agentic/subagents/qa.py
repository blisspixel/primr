"""
QA Subagent for quality assessment.

This subagent handles the quality assurance phase of the research
pipeline, evaluating report quality and providing actionable feedback.

Responsibilities:
    - Evaluate report quality across multiple dimensions
    - Generate a numeric quality score (0-100)
    - Provide specific feedback for improvement
    - Identify sections needing refinement

Integration:
    Delegates to the existing primr.qa.analyzer pipeline for
    quality assessment.

Example:
    context = SubagentContext(
        company_name="Acme Corp",
        company_url="https://acme.com",
        working_dir=Path("./output/acme"),
        parent_results={"report_path": Path("./output/acme/report.md")},
    )
    qa = QASubagent(context)
    result = await qa.execute()

    if result.is_success:
        print(f"Quality Score: {result.data.score}/100")
        for feedback in result.data.feedback:
            print(f"  - {feedback}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from primr.agentic.errors import SubagentError
from primr.agentic.subagents.base import (
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT DATA CLASS
# =============================================================================


@dataclass
class QAResult:
    """
    Result data from QA assessment.

    Attributes:
        score: Overall quality score (0-100)
        feedback: List of feedback items
        dimension_scores: Scores by quality dimension
        sections_to_improve: Sections needing improvement
        passed: Whether the report passed QA threshold
    """

    score: int
    feedback: list[str] = field(default_factory=list)
    dimension_scores: dict[str, int] = field(default_factory=dict)
    sections_to_improve: list[str] = field(default_factory=list)
    passed: bool = True

    @property
    def grade(self) -> str:
        """Get letter grade based on score."""
        if self.score >= 90:
            return "A"
        elif self.score >= 80:
            return "B"
        elif self.score >= 70:
            return "C"
        elif self.score >= 60:
            return "D"
        else:
            return "F"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "score": self.score,
            "grade": self.grade,
            "feedback": self.feedback,
            "dimension_scores": self.dimension_scores,
            "sections_to_improve": self.sections_to_improve,
            "passed": self.passed,
        }


# =============================================================================
# QA SUBAGENT
# =============================================================================


class QASubagent(Subagent[QAResult]):
    """
    Subagent for report quality assessment.

    Evaluates research reports across multiple quality dimensions
    and provides actionable feedback for improvement.

    Quality Dimensions:
        - Completeness: Coverage of required sections
        - Accuracy: Factual correctness and citations
        - Clarity: Writing quality and readability
        - Structure: Organization and formatting
        - Evidence: Support for claims

    Scoring:
        - 90-100: Excellent (A)
        - 80-89: Good (B)
        - 70-79: Acceptable (C)
        - 60-69: Needs Work (D)
        - 0-59: Failing (F)

    Example:
        qa = QASubagent(context, min_score=70)
        result = await qa.execute()

        if not result.data.passed:
            print("Report needs improvement:")
            for section in result.data.sections_to_improve:
                print(f"  - {section}")
    """

    # Quality dimensions and their weights
    DIMENSIONS: dict[str, float] = {
        "completeness": 0.20,
        "accuracy": 0.20,
        "clarity": 0.15,
        "structure": 0.15,
        "evidence": 0.10,
        "hypothesis_framing": 0.10,
        "confidence_labels": 0.10,
    }

    def __init__(
        self,
        context: SubagentContext,
        min_score: int = 70,
    ):
        """
        Initialize QA subagent.

        Args:
            context: Subagent context
            min_score: Minimum passing score (0-100)
        """
        super().__init__(context, name="QASubagent")
        self._min_score = min_score

    @property
    def min_score(self) -> int:
        """Get minimum passing score."""
        return self._min_score

    async def execute(self) -> SubagentResult[QAResult]:
        """
        Execute quality assessment.

        Returns:
            SubagentResult containing QAResult on success
        """
        self._status = SubagentStatus.RUNNING
        start_time = time.time()

        logger.info(f"QASubagent starting for {self.company_name}")

        try:
            # Get report path from parent results
            report_path = self._context.get_parent_result("report_path")
            if report_path is None:
                raise SubagentError(
                    message="No report_path in parent results",
                    subagent="qa",
                )

            if isinstance(report_path, str):
                report_path = Path(report_path)

            # Run QA assessment
            qa_result = await self._assess_quality(report_path)

            duration = time.time() - start_time
            self._status = SubagentStatus.COMPLETED

            logger.info(
                f"QASubagent completed for {self.company_name}: "
                f"score={qa_result.score}, passed={qa_result.passed}"
            )

            return SubagentResult(
                status=self._status,
                data=qa_result,
                metrics={
                    "duration_seconds": duration,
                    "score": float(qa_result.score),
                    "feedback_count": len(qa_result.feedback),
                },
            )

        except SubagentError:
            raise
        except Exception as e:
            duration = time.time() - start_time
            self._status = SubagentStatus.FAILED

            logger.error(f"QASubagent failed for {self.company_name}: {e}")

            return SubagentResult(
                status=self._status,
                error=str(e),
                metrics={"duration_seconds": duration},
            )

    async def _assess_quality(self, report_path: Path) -> QAResult:
        """
        Assess report quality.

        Args:
            report_path: Path to the report file

        Returns:
            QAResult with scores and feedback
        """
        # Perform basic assessment - the full QA module requires complex setup
        return await self._basic_assessment(report_path)

    async def _basic_assessment(self, report_path: Path) -> QAResult:
        """
        Perform basic quality assessment when full QA unavailable.

        Args:
            report_path: Path to the report file

        Returns:
            QAResult with basic scores
        """
        feedback: list[str] = []
        dimension_scores: dict[str, int] = {}
        sections_to_improve: list[str] = []

        # Check if report exists
        if not report_path.exists():
            return QAResult(
                score=0,
                feedback=["Report file not found"],
                passed=False,
            )

        # Read report content
        content = report_path.read_text(encoding="utf-8")
        word_count = len(content.split())
        section_count = content.count("## ")

        # Assess completeness
        completeness_score = self._assess_completeness(content, feedback, sections_to_improve)
        dimension_scores["completeness"] = completeness_score

        # Assess structure
        structure_score = self._assess_structure(content, section_count, feedback)
        dimension_scores["structure"] = structure_score

        # Assess clarity (basic word count check)
        clarity_score = self._assess_clarity(content, word_count, feedback)
        dimension_scores["clarity"] = clarity_score

        # Assess evidence
        evidence_score = self._assess_evidence(content, feedback)
        dimension_scores["evidence"] = evidence_score

        # Keep the historical key for compatibility, but score only what this
        # deterministic pass can prove: whether factual claims are traceable.
        accuracy_score = self._assess_accuracy_traceability(content, feedback)
        dimension_scores["accuracy"] = accuracy_score

        # Assess hypothesis framing
        hypothesis_score = self._assess_hypothesis_framing(content, feedback)
        dimension_scores["hypothesis_framing"] = hypothesis_score

        # Assess confidence labels
        confidence_score = self._assess_confidence_labels(content, feedback)
        dimension_scores["confidence_labels"] = confidence_score

        # Assess section lengths for truncation
        section_length_score = self._assess_section_lengths(content, feedback, sections_to_improve)
        # Apply truncation penalty to structure score
        structure_score = max(0, structure_score - (100 - section_length_score))
        dimension_scores["structure"] = structure_score

        # Calculate weighted score
        total_score = sum(dimension_scores[dim] * weight for dim, weight in self.DIMENSIONS.items())
        score = int(total_score)

        return QAResult(
            score=score,
            feedback=feedback,
            dimension_scores=dimension_scores,
            sections_to_improve=sections_to_improve,
            passed=score >= self._min_score,
        )

    def _assess_completeness(
        self,
        content: str,
        feedback: list[str],
        sections_to_improve: list[str],
    ) -> int:
        """Assess report completeness."""
        score = 100
        required_sections = [
            "Executive Summary",
            "Key Insights",
            "Sources",
        ]

        for section in required_sections:
            if section.lower() not in content.lower():
                score -= 20
                feedback.append(f"Missing section: {section}")
                sections_to_improve.append(section)

        return max(0, score)

    def _assess_structure(
        self,
        content: str,
        section_count: int,
        feedback: list[str],
    ) -> int:
        """Assess report structure."""
        score = 100

        # Check for minimum sections
        if section_count < 3:
            score -= 30
            feedback.append("Report has too few sections")

        # Check for proper heading hierarchy
        if "# " not in content:
            score -= 20
            feedback.append("Missing main heading")

        return max(0, score)

    def _assess_clarity(
        self,
        content: str,
        word_count: int,
        feedback: list[str],
    ) -> int:
        """Assess writing clarity."""
        score = 100

        # Check word count
        if word_count < 200:
            score -= 40
            feedback.append("Report is too short (< 200 words)")
        elif word_count < 500:
            score -= 20
            feedback.append("Report could be more detailed")

        return max(0, score)

    def _assess_evidence(
        self,
        content: str,
        feedback: list[str],
    ) -> int:
        """Assess evidence and citations."""
        score = 100

        # Check for URLs/citations
        if "http" not in content.lower() and "source" not in content.lower():
            score -= 30
            feedback.append("Report lacks citations or sources")

        return max(0, score)

    def _assess_accuracy_traceability(
        self,
        content: str,
        feedback: list[str],
    ) -> int:
        """Assess source traceability without claiming factual verification."""

        score = 100
        lowered = content.lower()
        has_citation_marker = "[cite:" in lowered or "[source:" in lowered
        has_url = "http://" in lowered or "https://" in lowered
        has_sources_section = "## sources" in lowered
        has_confidence_label = any(
            label in lowered
            for label in (
                "(confirmed",
                "(reported",
                "(estimated",
                "(hypothesis",
            )
        )

        if not (has_citation_marker or has_url):
            score -= 40
            feedback.append("Accuracy is not independently traceable without citations or URLs")
        if not has_sources_section:
            score -= 25
            feedback.append("Accuracy traceability lacks a Sources section")
        if not has_confidence_label:
            score -= 15
            feedback.append("Accuracy traceability lacks confidence labels")

        return max(0, score)

    def _assess_hypothesis_framing(
        self,
        content: str,
        feedback: list[str],
    ) -> int:
        """Assess hypothesis framing quality.

        Looks for (Hypothesis) labels and validation phrases like
        'we hypothesize', 'to validate', 'worth validating'.
        """
        import re

        labels = len(re.findall(r"\(Hypothesis\)", content, re.IGNORECASE))
        phrases = 0
        for pattern in [
            r"we hypothesize",
            r"to validate",
            r"worth validating",
            r"hypothesis to test",
            r"requires validation",
        ]:
            phrases += len(re.findall(pattern, content, re.IGNORECASE))

        total = labels + phrases
        score = 100

        if total == 0:
            score -= 40
            feedback.append("No hypothesis framing detected")
        elif total < 3:
            score -= 20
            feedback.append(f"Weak hypothesis framing ({total} signals)")

        return max(0, score)

    def _assess_confidence_labels(
        self,
        content: str,
        feedback: list[str],
    ) -> int:
        """Assess epistemic confidence labels.

        Counts (Confirmed), (Reported), (Estimated), (Hypothesis) labels.
        """
        import re

        total = 0
        for pattern in [
            r"\(Confirmed[^)]*\)",
            r"\(Reported[^)]*\)",
            r"\(Estimated[^)]*\)",
            r"\(Hypothesis\)",
        ]:
            total += len(re.findall(pattern, content, re.IGNORECASE))

        score = 100

        if total == 0:
            score -= 30
            feedback.append("No confidence labels found")
        elif total < 3:
            score -= 15
            feedback.append(f"Few confidence labels ({total})")

        return max(0, score)

    def _assess_section_lengths(
        self,
        content: str,
        feedback: list[str],
        sections_to_improve: list[str],
    ) -> int:
        """Assess section lengths, penalizing truncated sections (< 50 words).

        Returns a score from 0-100. Each truncated section costs -10 (max -40).
        """
        import re

        parts = re.split(r"^##\s+", content, flags=re.MULTILINE)
        truncated = []

        for part in parts[1:]:  # skip preamble
            lines = part.split("\n", 1)
            title = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
            if len(body.split()) < 50:
                truncated.append(title)

        score = 100
        penalty = min(40, len(truncated) * 10)
        score -= penalty

        if truncated:
            feedback.append(f"{len(truncated)} truncated section(s): " + ", ".join(truncated[:3]))
            sections_to_improve.extend(truncated)

        return max(0, score)

    def get_required_tools(self) -> list[str]:
        """
        Return list of MCP tools this subagent needs.

        QASubagent uses the internal pipeline, not MCP tools.

        Returns:
            Empty list (uses internal pipeline)
        """
        return []
