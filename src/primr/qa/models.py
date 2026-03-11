"""
Data models for the QA system.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class IssueType(Enum):
    """Types of issues that can be identified in QA analysis."""

    FACTUAL = "factual"
    LOGICAL = "logical"
    COMPLETENESS = "completeness"
    CITATION = "citation"


class Severity(Enum):
    """Severity levels for QA issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class QAOptions:
    """Configuration for QA execution."""

    model: str = None  # QA model to use (defaults to PrimrModels.QA_MODEL)
    enabled: bool = True  # QA enabled by default
    verbose_cli: bool = False  # Show detailed CLI output
    save_detailed: bool = True  # Save detailed analysis to workspace


@dataclass
class ClassifiedIssue:
    """A classified QA issue."""

    issue_type: IssueType
    severity: Severity
    section: str
    description: str
    location: str  # Line reference or section identifier
    suggestion: str | None = None  # Recommended fix


@dataclass
class CitationCheckResult:
    """Results of citation accuracy checking."""

    total_citations: int
    valid_citations: int
    broken_links: list[str]
    unsupported_claims: list[str]
    score: int  # 0-100


@dataclass
class LogicCheckResult:
    """Results of logical consistency checking."""

    contradictions_found: list[str]
    unsupported_leaps: list[str]
    score: int  # 0-100


@dataclass
class CompletenessCheckResult:
    """Results of completeness assessment."""

    expected_sections: list[str]
    missing_sections: list[str]
    weak_sections: list[str]
    score: int  # 0-100


@dataclass
class ConfidenceAssessment:
    """Confidence assessment for different parts of the report."""

    section_confidence: dict[str, int]  # section -> confidence score (0-100)
    overall_confidence: int


@dataclass
class ReportMetadata:
    """Metadata about the analyzed report."""

    company_name: str
    generation_date: datetime
    generation_mode: str  # scrape, deep, full
    model_used: str
    file_path: Path


@dataclass
class ReportContent:
    """Loaded report content for analysis."""

    company_name: str
    content: str
    sections: dict[str, str]  # section_name -> content
    citations: list[str]
    metadata: ReportMetadata
    file_path: Path


@dataclass
class QAAnalysis:
    """Complete QA analysis results."""

    overall_score: int  # 0-100
    section_scores: dict[str, int]
    issues: list[ClassifiedIssue]
    citation_check: CitationCheckResult
    logic_check: LogicCheckResult
    completeness_check: CompletenessCheckResult
    confidence_assessment: ConfidenceAssessment
    timestamp: datetime
    model_used: str


@dataclass
class QAResult:
    """QA execution result for CLI display."""

    grade: int  # 0-100 overall score
    summary: str  # Clean CLI summary
    detailed_analysis: QAAnalysis | None  # Full analysis for workspace storage
    needs_attention: bool  # True if grade < 70
    error_message: str | None = None  # Error message if QA failed


@dataclass
class QAReport:
    """Formatted QA report for file output."""

    company_name: str
    analysis: QAAnalysis
    summary: str
    detailed_findings: str
    recommendations: list[str]
    generated_at: datetime
