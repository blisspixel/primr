"""Shared QA operation for MCP and A2A transports."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from primr.core.trusted_report import stable_report_snapshot, validate_trusted_report


async def run_qa_analysis(
    report_path: str, *, allowed_roots: Iterable[str | Path] | None = None
) -> dict[str, Any]:
    """Analyze one existing report and return the transport-neutral summary."""
    return await asyncio.to_thread(_run_qa_analysis, report_path, allowed_roots)


def _run_qa_analysis(
    report_path: str, allowed_roots: Iterable[str | Path] | None
) -> dict[str, Any]:
    from primr.qa.analyzer import QAAnalyzer
    from primr.qa.report_loader import ReportLoader

    trusted = validate_trusted_report(
        report_path, allowed_roots=allowed_roots, max_bytes=8 * 1024 * 1024
    )
    with (
        tempfile.TemporaryDirectory(prefix="primr-qa-context-") as directory,
        stable_report_snapshot(trusted, directory) as snapshot,
    ):
        report = ReportLoader().load_report_from_path(snapshot, display_path=trusted.path)
        if not report:
            raise RuntimeError(f"Could not load report: {report_path}")
        analysis = QAAnalyzer().analyze_report(report)
    return {
        "overall_score": analysis.overall_score,
        "category_scores": {
            "completeness": analysis.completeness_check.score,
            "citation_accuracy": analysis.citation_check.score,
            "logical_consistency": analysis.logic_check.score,
            "confidence": analysis.confidence_assessment.overall_confidence,
        },
        "improvement_suggestions": [issue.description for issue in analysis.issues[:5]]
        if analysis.issues
        else [],
    }


__all__ = ["run_qa_analysis"]
