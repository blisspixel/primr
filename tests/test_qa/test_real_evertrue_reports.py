"""
Test the enhanced QA system with actual Evertrue LLC reports.
"""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from primr.qa.integration import QAIntegration
from primr.qa.models import QAOptions
from primr.qa.report_loader import ReportLoader


def test_evertrue_reports():
    """Test the QA system with actual Evertrue LLC reports."""

    # Paths to the actual reports
    ai_strategy_path = Path("output/Evertrue LLC_AI_Strategy_12-22-2025.docx")
    strategic_overview_path = Path("output/Evertrue LLC_Strategic_Overview_12-22-2025.docx")

    # Initialize QA components with temp directory to avoid polluting output folder
    with tempfile.TemporaryDirectory() as temp_dir:
        qa_integration = QAIntegration(QAOptions(enabled=True, save_detailed=True), output_dir=Path(temp_dir))
        report_loader = ReportLoader()

        print("Testing Enhanced QA System with Real Evertrue LLC Reports")
        print("=" * 60)

        # Test both reports
        reports_to_test = [
            ("AI Strategy Report", ai_strategy_path),
            ("Strategic Overview Report", strategic_overview_path)
        ]

        for report_name, report_path in reports_to_test:
            print(f"\nAnalyzing: {report_name}")
            print(f"File: {report_path}")

            if not report_path.exists():
                print(f"ERROR: File not found: {report_path}")
                continue

            try:
                # Load the report content
                print("Loading report content...")
                report_content = report_loader.load_report_from_path(report_path)

                if not report_content:
                    print("ERROR: Failed to load report content")
                    continue

                print(f"Loaded report: {len(report_content.content)} characters")
                print(f"Sections: {len(report_content.sections)}")
                print(f"Citations: {len(report_content.citations)}")

                # Run QA analysis
                print("\nRunning QA analysis...")
                qa_result = qa_integration.run_post_generation_qa(report_path, "Evertrue LLC")

                if qa_result:
                    print(f"\nQA Results for {report_name}:")
                    print(f"   Grade: {qa_result.grade}/100")
                    print(f"   Summary: {qa_result.summary}")
                    print(f"   Needs Attention: {'Yes' if qa_result.needs_attention else 'No'}")

                    if qa_result.error_message:
                        print(f"   Error: {qa_result.error_message}")

                    # Get detailed analysis if available
                    analyzer_result = qa_integration.analyzer.assess_report(report_content)
                    if analyzer_result:
                        print("\nDetailed Assessment:")
                        print(f"   Ready for Use: {'Yes' if analyzer_result.ready_for_use else 'No'}")
                        print(f"   Confidence Level: {analyzer_result.confidence_level.title()}")
                        print(f"   Parsing Success: {'Yes' if analyzer_result.parsing_success else 'No'}")

                        if analyzer_result.key_strengths:
                            print(f"\nKey Strengths ({len(analyzer_result.key_strengths)}):")
                            for i, strength in enumerate(analyzer_result.key_strengths, 1):
                                print(f"   {i}. {strength}")

                        if analyzer_result.areas_for_improvement:
                            print(f"\nAreas for Improvement ({len(analyzer_result.areas_for_improvement)}):")
                            for i, improvement in enumerate(analyzer_result.areas_for_improvement, 1):
                                print(f"   {i}. {improvement}")

                        if analyzer_result.recommendation:
                            print("\nRecommendation:")
                            print(f"   {analyzer_result.recommendation}")
                else:
                    print("ERROR: QA analysis returned no result")

            except Exception as e:
                print(f"ERROR analyzing {report_name}: {e}")
                import traceback
                traceback.print_exc()

        print(f"\n{'='*60}")
        print("QA System Test Complete!")


if __name__ == "__main__":
    test_evertrue_reports()
