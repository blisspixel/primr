"""
Demo script showing the enhanced QA system integration in the pipeline.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from primr.qa.integration import QAIntegration
from primr.qa.models import QAOptions


def demo_qa_pipeline():
    """Demonstrate the QA system as integrated in the main pipeline."""
    
    print("Primr QA System - Pipeline Integration Demo")
    print("=" * 50)
    
    # Initialize QA integration (as it would be in the main pipeline)
    qa_integration = QAIntegration(QAOptions(
        enabled=True,
        save_detailed=True,
        model="gemini-2.0-flash-thinking-exp"
    ))
    
    print("\n1. QA System Status:")
    qa_integration.print_qa_status()
    
    print("\n2. Simulating report generation completion...")
    print("   Company: Demo Corp")
    print("   Report: output/Demo_Corp_Strategic_Overview.docx")
    print("   ... research process completed ...")
    
    # This is where the main pipeline would call QA
    print("\n3. Quality Assessment:")
    print("   Assessing quality...")
    
    # In the real pipeline, this would be:
    # qa_result = qa_integration.run_post_generation_qa(report_path, company_name)
    # if qa_result:
    #     print(f"   {qa_result.summary}")
    
    # For demo, show what the output would look like
    print("   Grade: (87/100)")
    
    print("\n4. QA Report Generated:")
    print("   Detailed analysis saved to: output/Demo_Corp_QA_Report_12-23-2025_14-30-15.txt")
    
    print("\n5. QA Monitoring:")
    print("   Assessment logged for performance tracking")
    print("   Metrics updated in logs/qa/qa_metrics.json")
    
    print(f"\n{'='*50}")
    print("QA Integration Complete!")
    print("\nKey Features:")
    print("• Clean CLI output with simple grade display")
    print("• Detailed QA reports saved automatically")
    print("• Performance monitoring and metrics tracking")
    print("• Seamless integration - no user action required")
    print("• Use --no-qa to skip, --verbose for details")


if __name__ == "__main__":
    demo_qa_pipeline()