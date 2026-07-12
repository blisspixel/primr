"""Shared QA operation for MCP and A2A transports."""

from __future__ import annotations

from pathlib import Path
from typing import Any


async def run_qa_analysis(report_path: str) -> dict[str, Any]:
    """Analyze one existing report and return the transport-neutral summary."""
    from primr.qa.analyzer import QAAnalyzer
    from primr.qa.report_loader import ReportLoader

    report = ReportLoader().load_report_from_path(Path(report_path))
    if not report:
        raise RuntimeError(f"Could not load report: {report_path}")

    analysis = QAAnalyzer().analyze_report(report)
    return {
        "overall_score": analysis.overall_score,
        "category_scores": {
            "completeness": analysis.completeness_score,
            "accuracy": analysis.accuracy_score,
            "clarity": analysis.clarity_score,
            "actionability": analysis.actionability_score,
        },
        "improvement_suggestions": [issue.description for issue in analysis.issues[:5]]
        if analysis.issues
        else [],
    }


__all__ = ["run_qa_analysis"]
