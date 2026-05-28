"""
QA command-line interface for reviewing and analyzing report quality.
"""

import glob
import logging
import os
from datetime import datetime
from pathlib import Path

from ..config.models import PrimrModels
from .integration import QAIntegration
from .models import QAOptions
from .report_loader import ReportLoader

logger = logging.getLogger(__name__)


class QACommand:
    """Command-line interface for QA operations."""

    def __init__(self, output_dir: Path | None = None):
        """
        Initialize QA command with default options.

        Args:
            output_dir: Override output directory for testing. If None, uses config default.
        """
        # Check if verbose mode is enabled globally
        try:
            from primr.utils.console import console

            verbose_mode = hasattr(console, "verbose") and console.verbose
        except Exception:
            verbose_mode = False

        self.qa_integration = QAIntegration(
            QAOptions(
                enabled=True,
                save_detailed=True,
                model=PrimrModels.QA_MODEL,
                verbose_cli=verbose_mode,
            )
        )
        self.report_loader = ReportLoader()
        self._output_dir = output_dir  # For test isolation

    @property
    def output_dir(self) -> Path:
        """Get output directory, using config default if not overridden."""
        if self._output_dir is not None:
            return self._output_dir
        from primr.config.config import OUTPUT_DIR

        return Path(OUTPUT_DIR)

    @output_dir.setter
    def output_dir(self, value: Path) -> None:
        """Set output directory (for testing)."""
        self._output_dir = value

    def show_detailed_analysis(self, company_name: str) -> int:
        """
        Show detailed QA analysis for a company's most recent report.

        Args:
            company_name: Name of company to analyze

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            print(f"\nQA Analysis for {company_name}")
            print("=" * 60)

            # Find the most recent report for this company
            report_path = self._find_recent_report(company_name)
            if not report_path:
                print(f"No reports found for '{company_name}'")
                print("\nAvailable companies:")
                self._list_available_companies()
                return 1

            print(f"Analyzing: {os.path.basename(report_path)}")
            print(f"Path: {report_path}")
            print()

            # Run QA analysis
            qa_result = self.qa_integration.run_post_generation_qa(Path(report_path), company_name)

            if not qa_result:
                print("QA analysis failed or is disabled")
                return 1

            # Display results
            print("ASSESSMENT RESULTS")
            print("-" * 30)
            print(f"Grade: {qa_result.grade}/100")
            print(f"Summary: {qa_result.summary}")
            print(f"Needs Attention: {'Yes' if qa_result.needs_attention else 'No'}")

            if qa_result.error_message:
                print(f"Error: {qa_result.error_message}")

            # Show detailed analysis if available
            detailed_file = self._find_qa_report(company_name)
            if detailed_file:
                print("\nDetailed analysis:")
                print(f"File: {detailed_file}")
                print()
                self._display_detailed_analysis(detailed_file)

            return 0

        except Exception as e:
            print(f"QA analysis failed: {e}")
            logger.error(f"QA analysis failed for {company_name}: {e}")
            return 1

    def analyze_report_file(self, report_path: str) -> int:
        """
        Analyze a specific report file.

        Args:
            report_path: Path to the report file to analyze

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            report_file = Path(report_path)
            if not report_file.exists():
                print(f"Report file not found: {report_path}")
                return 1

            # Extract company name from filename
            filename = report_file.stem
            company_name = filename.split("_")[0] if "_" in filename else "Unknown Company"

            print("\nQA Analysis for Report File")
            print("=" * 60)
            print(f"File: {report_file.name}")
            print(f"Company: {company_name}")
            print()

            # Run QA analysis
            qa_result = self.qa_integration.run_post_generation_qa(report_file, company_name)

            if not qa_result:
                print("QA analysis failed or is disabled")
                return 1

            # Display results
            print("ASSESSMENT RESULTS")
            print("-" * 30)
            print(f"Grade: {qa_result.grade}/100")
            print(f"Summary: {qa_result.summary}")
            print(f"Needs Attention: {'Yes' if qa_result.needs_attention else 'No'}")

            if qa_result.error_message:
                print(f"Error: {qa_result.error_message}")

            return 0

        except Exception as e:
            print(f"QA analysis failed: {e}")
            logger.error(f"QA analysis failed for {report_path}: {e}")
            return 1

    def show_recent_qa_summary(self, count: int = 5) -> int:
        """
        Show QA summary for recent reports.

        Args:
            count: Number of recent reports to show

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            print(f"\nQA Summary - {count} Most Recent Reports")
            print("=" * 60)

            # Get recent assessments from monitoring
            recent_assessments = self.qa_integration.get_recent_qa_reports(24)

            if not recent_assessments:
                print("No recent QA assessments found")
                print("\nTip: QA assessments are logged when reports are generated")
                return 0

            # Sort by timestamp and take the most recent
            recent_assessments.sort(key=lambda x: x.timestamp, reverse=True)
            recent_assessments = recent_assessments[:count]

            print(f"Found {len(recent_assessments)} recent assessment(s):\n")

            for i, assessment in enumerate(recent_assessments, 1):
                timestamp = datetime.fromisoformat(assessment.timestamp)
                print(f"{i}. {assessment.company_name}")
                print(f"   Grade: {assessment.grade}/100")
                print(f"   Type: {assessment.report_type}")
                print(f"   Confidence: {assessment.confidence_level.title()}")
                print(f"   Ready: {'Yes' if assessment.ready_for_use else 'No'}")
                print(f"   Date: {timestamp.strftime('%Y-%m-%d %H:%M')}")
                if assessment.error_type:
                    print(f"   Error: {assessment.error_type}")
                print()

            # Show system status
            print("SYSTEM STATUS")
            print("-" * 20)
            self.qa_integration.print_qa_status()

            return 0

        except Exception as e:
            print(f"Failed to show QA summary: {e}")
            logger.error(f"Failed to show QA summary: {e}")
            return 1

    def _find_recent_report(self, company_name: str) -> str | None:
        """Find the most recent report for a company.

        Brackets / wildcards in company names (e.g. "Acme [Holdings]") would
        otherwise be interpreted as glob character classes and miss the
        actual filename — same bug fixed for batch resume in commit 793e5d1.
        We escape the name fragments and keep the trailing ``*.docx`` as the
        real wildcard.
        """
        output_dir = self.output_dir

        # Look for various report types
        patterns = [
            f"{glob.escape(company_name)}_*.docx",
            f"{glob.escape(company_name.replace(' ', '_'))}_*.docx",
            f"{glob.escape(company_name.replace(' ', ''))}_*.docx",
        ]

        all_files = []
        for pattern in patterns:
            files = glob.glob(os.path.join(str(output_dir), pattern))
            all_files.extend(files)

        if not all_files:
            return None

        # Return the most recent file
        all_files.sort(key=os.path.getmtime, reverse=True)
        return all_files[0]

    def _find_qa_report(self, company_name: str) -> str | None:
        """Find the most recent QA report for a company.

        See ``_find_recent_report`` for the glob.escape rationale.
        """
        output_dir = self.output_dir

        # Look for QA report files
        patterns = [
            f"{glob.escape(company_name)}_QA_Report_*.txt",
            f"{glob.escape(company_name.replace(' ', '_'))}_QA_Report_*.txt",
            f"{glob.escape(company_name.replace(' ', ''))}_QA_Report_*.txt",
        ]

        all_files = []
        for pattern in patterns:
            files = glob.glob(os.path.join(str(output_dir), pattern))
            all_files.extend(files)

        if not all_files:
            return None

        # Return the most recent file
        all_files.sort(key=os.path.getmtime, reverse=True)
        return all_files[0]

    def _list_available_companies(self) -> None:
        """List companies with available reports."""
        output_dir = self.output_dir

        # Find all report files
        report_files = glob.glob(os.path.join(str(output_dir), "*_*.docx"))

        if not report_files:
            print("  No reports found in output directory")
            return

        # Extract company names
        companies = set()
        for filepath in report_files:
            filename = os.path.basename(filepath)
            # Extract company name (everything before the first underscore)
            if "_" in filename:
                company = filename.split("_")[0]
                companies.add(company)

        if companies:
            for company in sorted(companies):
                print(f"  - {company}")
        else:
            print("  No company reports found")

    def _display_detailed_analysis(self, qa_file_path: str) -> None:
        """Display the contents of a detailed QA analysis file."""
        try:
            with open(qa_file_path, encoding="utf-8") as f:
                content = f.read()

            print("\nDETAILED QA ANALYSIS")
            print("=" * 60)
            print(content)

        except Exception as e:
            print(f"Failed to read detailed analysis: {e}")
