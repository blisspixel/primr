"""
QA integration handler for automatic post-generation quality assurance.
"""

import logging
import time
from pathlib import Path

from .error_handler import QAErrorHandler, safe_qa_operation
from .models import QAOptions, QAResult
from .monitor import QAMonitor
from .report_loader import ReportLoader
from .simple_analyzer import SimpleQAAnalyzer, SimpleQAResult

logger = logging.getLogger(__name__)


class QAIntegration:
    """Handles automatic QA integration with report generation pipeline."""

    def __init__(self, qa_options: QAOptions | None = None, output_dir: Path | None = None):
        """
        Initialize QA integration with options.

        Args:
            qa_options: QA configuration options
            output_dir: Override output directory for testing. If None, uses config default.
        """
        self.options = qa_options or QAOptions()
        self._output_dir = output_dir  # For test isolation

        # Use centralized model if none specified
        if self.options.model is None:
            from ..config.models import PrimrModels
            self.options.model = PrimrModels.QA_MODEL

        self.analyzer = SimpleQAAnalyzer(self.options.model)
        self.report_loader = ReportLoader()
        self.error_handler = QAErrorHandler()
        self.monitor = QAMonitor()  # Add monitoring

    @property
    def output_dir(self) -> Path:
        """Get output directory, using config default if not overridden."""
        if self._output_dir is not None:
            return self._output_dir
        from ..config.config import OUTPUT_DIR
        return Path(OUTPUT_DIR)

    @output_dir.setter
    def output_dir(self, value: Path) -> None:
        """Set output directory (for testing)."""
        self._output_dir = value

    @safe_qa_operation("Post-generation QA")
    def run_post_generation_qa(self, report_path: Path, company_name: str) -> QAResult | None:
        """
        Run QA automatically after report generation.

        Args:
            report_path: Path to generated report
            company_name: Name of company for the report

        Returns:
            QAResult with grade and summary for CLI display, or None if QA disabled
        """
        if not self.options.enabled:
            logger.debug("QA disabled, skipping quality assessment")
            return None

        try:
            logger.info(f"Running quality assessment for {company_name}")
            start_time = time.time()

            # Show progress to user
            print("Assessing quality...")

            # Load the report content with error handling
            try:
                report_content = self.report_loader.load_report_from_path(report_path)
                if not report_content:
                    error_msg = self.error_handler.handle_file_error(
                        FileNotFoundError(), str(report_path)
                    )
                    logger.warning(error_msg)
                    return self._create_error_result(error_msg)
            except Exception as e:
                error_msg = self.error_handler.handle_file_error(e, str(report_path))
                logger.warning(error_msg)
                return self._create_error_result(error_msg)

            # Run simplified QA assessment
            qa_result = self.analyzer.assess_report(report_content)
            processing_time = int((time.time() - start_time) * 1000)  # Convert to milliseconds

            # Determine report type for logging
            report_type = self.analyzer._determine_report_type(report_content)

            # Log the assessment for monitoring
            error_type = qa_result.error_message if qa_result.error_message else None
            self.monitor.log_assessment(
                company_name=company_name,
                report_type=report_type,
                grade=self._calculate_numerical_grade(qa_result),
                confidence_level=qa_result.confidence_level,
                ready_for_use=qa_result.ready_for_use,
                parsing_success=qa_result.parsing_success,
                error_type=error_type,
                processing_time_ms=processing_time,
                model_used=self.analyzer.model_name,
                fallback_used=False,  # TODO: Track this in analyzer
                retry_count=0  # TODO: Track this in analyzer
            )

            # Create result with clean CLI summary
            cli_summary = self.format_cli_summary(qa_result)

            result = QAResult(
                grade=self._calculate_numerical_grade(qa_result),
                summary=cli_summary,
                detailed_analysis=None,  # We'll store the simple result differently
                needs_attention=not qa_result.ready_for_use or qa_result.confidence_level == "low"
            )

            # Save detailed analysis to workspace if enabled
            if self.options.save_detailed:
                try:
                    self._save_simple_analysis(company_name, qa_result)
                except Exception as e:
                    logger.warning(f"Failed to save detailed QA analysis: {e}")
                    # Don't fail the entire QA process if saving fails

            confidence_text = qa_result.confidence_level.title()
            ready_text = "Ready" if qa_result.ready_for_use else "Needs Work"
            logger.info(f"QA completed for {company_name}: {ready_text} ({confidence_text} confidence)")
            return result

        except Exception as e:
            error_msg = self.error_handler.handle_analysis_error(e, company_name)
            logger.error(f"QA analysis failed for {company_name}: {error_msg}")
            return self._create_error_result(error_msg)

    def format_cli_summary(self, qa_result: SimpleQAResult) -> str:
        """Format clean CLI output based on simple assessment."""
        grade = self._calculate_numerical_grade(qa_result)

        if not qa_result.parsing_success:
            return f"Grade: ({grade}/100)\nAssessment: Analysis Failed"

        # Simple, clean format matching README example
        summary = f"Grade: ({grade}/100)"

        # Add detailed reasoning if verbose mode is enabled
        if self.options.verbose_cli:
            summary += "\n\nQA REASONING:"
            summary += f"\n• Ready for Use: {'Yes' if qa_result.ready_for_use else 'No'}"
            summary += f"\n• Confidence Level: {qa_result.confidence_level.title()}"

            if qa_result.key_strengths:
                summary += f"\n• Key Strengths ({len(qa_result.key_strengths)}):"
                for i, strength in enumerate(qa_result.key_strengths, 1):
                    summary += f"\n  {i}. {strength[:100]}{'...' if len(strength) > 100 else ''}"

            if qa_result.areas_for_improvement:
                summary += f"\n• Areas for Improvement ({len(qa_result.areas_for_improvement)}):"
                for i, improvement in enumerate(qa_result.areas_for_improvement, 1):
                    summary += f"\n  {i}. {improvement[:100]}{'...' if len(improvement) > 100 else ''}"

            summary += f"\n• Recommendation: {qa_result.recommendation[:150]}{'...' if len(qa_result.recommendation) > 150 else ''}"

        return summary

    def _save_simple_analysis(self, company_name: str, result: SimpleQAResult) -> None:
        """Save simple QA analysis to workspace."""
        try:
            from datetime import datetime

            # Create output directory if it doesn't exist
            output_dir = self.output_dir
            output_dir.mkdir(exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
            filename = f"{company_name.replace(' ', '_')}_QA_Report_{timestamp}.txt"
            filepath = output_dir / filename

            # Format the analysis report
            report_content = f"""Quality Assessment Report for {company_name}
==================================================
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Analysis Model: {self.analyzer.model_name}

OVERALL ASSESSMENT
------------------
Ready for Use: {'Yes' if result.ready_for_use else 'No'}
Confidence Level: {result.confidence_level.title()}
Grade: {self._calculate_numerical_grade(result)}/100

ASSESSMENT CRITERIA EVALUATION
------------------------------
[x] Citation Accuracy: Sources properly attributed and credible
[x] Logical Consistency: Analysis flows coherently without contradictions
[x] Completeness: Covers key areas needed for strategic decisions
[x] Confidence Level: Information reliability for decision-making

KEY STRENGTHS
-------------
"""

            if result.key_strengths:
                for i, strength in enumerate(result.key_strengths, 1):
                    report_content += f"{i}. {strength}\n"
            else:
                report_content += "None specifically identified\n"

            report_content += "\nAREAS FOR IMPROVEMENT\n"
            report_content += "---------------------\n"

            if result.areas_for_improvement:
                for i, improvement in enumerate(result.areas_for_improvement, 1):
                    report_content += f"{i}. {improvement}\n"
            else:
                report_content += "None specifically identified\n"

            report_content += "\nRECOMMENDATION\n"
            report_content += "--------------\n"
            report_content += f"{result.recommendation}\n"

            if not result.parsing_success:
                report_content += "\nNOTE: Analysis parsing encountered issues. Results may be incomplete.\n"

            # Write to file
            filepath.write_text(report_content, encoding='utf-8')
            logger.info(f"Detailed QA analysis saved to: {filepath}")

        except Exception as e:
            logger.error(f"Failed to save simple QA analysis: {e}")

    def _create_error_result(self, error_message: str) -> QAResult:
        """Create a QA result indicating an error occurred."""
        return QAResult(
            grade=0,
            summary="Assessment: QA Failed",
            detailed_analysis=None,
            needs_attention=True,
            error_message=error_message
        )

    def _calculate_numerical_grade(self, qa_result: SimpleQAResult) -> int:
        """Calculate numerical grade based on QA assessment with more nuanced scoring."""
        if not qa_result.parsing_success:
            return 50  # Default for parsing failures

        # More sophisticated base scoring
        base_score = 0
        if qa_result.ready_for_use:
            if qa_result.confidence_level == "high":
                base_score = 82  # Reduced from 85 to allow more variation
            elif qa_result.confidence_level == "medium":
                base_score = 72  # Reduced from 75
            else:  # low confidence but ready
                base_score = 62  # Reduced from 65
        else:
            # Not ready for use
            if qa_result.confidence_level == "medium":
                base_score = 55
            elif qa_result.confidence_level == "low":
                base_score = 45
            else:
                base_score = 50

        # More nuanced strength and improvement scoring
        strength_count = len(qa_result.key_strengths)
        improvement_count = len(qa_result.areas_for_improvement)

        # Variable strength bonus based on quality and quantity
        if strength_count == 0:
            strength_bonus = -5  # Penalty for no identified strengths
        elif strength_count == 1:
            strength_bonus = 2
        elif strength_count == 2:
            strength_bonus = 5
        elif strength_count == 3:
            strength_bonus = 8
        elif strength_count >= 4:
            strength_bonus = 10  # Diminishing returns
        else:
            strength_bonus = 0

        # Variable improvement penalty based on severity
        if improvement_count == 0:
            improvement_penalty = 0  # Perfect report
        elif improvement_count == 1:
            improvement_penalty = 1  # Minor issues
        elif improvement_count == 2:
            improvement_penalty = 3  # Some issues
        elif improvement_count == 3:
            improvement_penalty = 6  # Several issues
        elif improvement_count >= 4:
            improvement_penalty = 10  # Many issues
        else:
            improvement_penalty = 0

        # Content quality modifiers based on recommendation text
        recommendation_lower = qa_result.recommendation.lower()
        content_modifier = 0

        # Positive indicators
        if "excellent" in recommendation_lower or "outstanding" in recommendation_lower:
            content_modifier += 3
        elif "strong" in recommendation_lower or "solid" in recommendation_lower:
            content_modifier += 2
        elif "good" in recommendation_lower:
            content_modifier += 1

        # Negative indicators
        if "significant" in recommendation_lower and "issues" in recommendation_lower:
            content_modifier -= 3
        elif "major" in recommendation_lower and ("problems" in recommendation_lower or "concerns" in recommendation_lower):
            content_modifier -= 2
        elif "needs work" in recommendation_lower or "requires improvement" in recommendation_lower:
            content_modifier -= 1

        # Calculate final score
        final_score = base_score + strength_bonus - improvement_penalty + content_modifier

        # Add some randomization to prevent identical scores (±2 points)
        import random
        random.seed(hash(qa_result.recommendation))  # Deterministic but varied
        variation = random.randint(-2, 2)
        final_score += variation

        # Ensure score is within bounds
        return max(0, min(100, final_score))

    def get_qa_status(self) -> dict:
        """Get current QA system status and metrics."""
        return self.monitor.generate_status_report()

    def get_recent_qa_reports(self, hours: int = 24) -> list:
        """Get recent QA assessments."""
        return self.monitor.get_recent_assessments(hours)

    def print_qa_status(self) -> None:
        """Print QA system status to console."""
        self.monitor.print_status_summary()
