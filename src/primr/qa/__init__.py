"""
Quality Assurance module for Primr.

This module provides automated quality assessment capabilities for generated reports,
including citation checking, logical consistency analysis, completeness assessment,
and overall quality scoring.
"""

from .analyzer import QAAnalyzer
from .command import QACommand
from .integration import QAIntegration
from .models import ClassifiedIssue, IssueType, QAAnalysis, QAOptions, QAResult, Severity

__all__ = [
    "QAOptions",
    "QAResult",
    "QAAnalysis",
    "ClassifiedIssue",
    "IssueType",
    "Severity",
    "QAIntegration",
    "QAAnalyzer",
    "QACommand",
]
