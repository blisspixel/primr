"""
QA integration handler for automatic post-generation quality assurance.
"""

import logging
from pathlib import Path
from typing import Optional

from .models import QAOptions, QAResult, QAAnalysis
from .analyzer import QAAnalyzer
from .report_loader import ReportLoader
from .issue_classifier import IssueClassifier
from .error_handler import QAFileError, QAErrorHandler, safe_qa_operation

logger = logging.getLogger(__name__)


class QAIntegration:
    """Handles automatic QA integration with report generation pipeline."""
    
    def __init__(self, qa_options: Optional[QAOptions] = None):
        """Initialize QA integration with options."""
        self.options = qa_options or QAOptions()
        self.analyzer = QAAnalyzer(self.options.model)
        self.report_loader = ReportLoader()
        self.error_handler = QAErrorHandler()
    
    @safe_qa_operation("Post-generation QA")
    def run_post_generation_qa(self, report_path: Path, company_name: str) -> Optional[QAResult]:
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
            
            # Run QA analysis with comprehensive error handling
            qa_analysis = self.analyzer.analyze_report(report_content)
            
            # Create result with clean CLI summary
            cli_summary = self.format_cli_summary(qa_analysis.overall_score)
            
            result = QAResult(
                grade=qa_analysis.overall_score,
                summary=cli_summary,
                detailed_analysis=qa_analysis,
                needs_attention=qa_analysis.overall_score < 70
            )
            
            # Save detailed analysis to workspace if enabled
            if self.options.save_detailed:
                try:
                    self._save_detailed_analysis(company_name, qa_analysis)
                except Exception as e:
                    logger.warning(f"Failed to save detailed QA analysis: {e}")
                    # Don't fail the entire QA process if saving fails
            
            logger.info(f"QA completed for {company_name}: Grade {qa_analysis.overall_score}/100")
            return result
            
        except Exception as e:
            error_msg = self.error_handler.handle_analysis_error(e, company_name)
            logger.error(f"QA analysis failed for {company_name}: {error_msg}")
            return self._create_error_result(error_msg)
    
    def format_cli_summary(self, grade: int) -> str:
        """Format clean CLI output: 'Grade: (XX/100)' with warning for low scores"""
        base_summary = f"Grade: ({grade}/100)"
        
        # Add warning indicator for scores below 70 (no emojis, text-based)
        if grade < 70:
            return f"{base_summary} - Needs Attention"
        
        return base_summary
    
    def _save_detailed_analysis(self, company_name: str, analysis: QAAnalysis) -> None:
        """Save detailed QA analysis to workspace."""
        try:
            from ..output.qa_report_generator import QAReportGenerator
            
            generator = QAReportGenerator()
            generator.save_detailed_analysis(company_name, analysis)
            
        except Exception as e:
            logger.error(f"Failed to save detailed QA analysis: {e}")
    def _create_error_result(self, error_message: str) -> QAResult:
        """Create a QA result indicating an error occurred."""
        return QAResult(
            grade=0,
            summary="Grade: QA Failed",
            detailed_analysis=None,
            needs_attention=True,
            error_message=error_message
        )