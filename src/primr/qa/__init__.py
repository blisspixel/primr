"""
Quality Assurance module for Primr.

This module provides automated quality assessment capabilities for generated reports,
including citation checking, logical consistency analysis, completeness assessment,
and overall quality scoring.
"""

from .models import QAOptions, QAResult, QAAnalysis, ClassifiedIssue, IssueType, Severity
from .integration import QAIntegration
from .analyzer import QAAnalyzer
from .command import QACommand

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