"""
Data models for the QA system.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


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
    suggestion: Optional[str] = None  # Recommended fix


@dataclass
class CitationCheckResult:
    """Results of citation accuracy checking."""
    total_citations: int
    valid_citations: int
    broken_links: List[str]
    unsupported_claims: List[str]
    score: int  # 0-100


@dataclass
class LogicCheckResult:
    """Results of logical consistency checking."""
    contradictions_found: List[str]
    unsupported_leaps: List[str]
    score: int  # 0-100


@dataclass
class CompletenessCheckResult:
    """Results of completeness assessment."""
    expected_sections: List[str]
    missing_sections: List[str]
    weak_sections: List[str]
    score: int  # 0-100


@dataclass
class ConfidenceAssessment:
    """Confidence assessment for different parts of the report."""
    section_confidence: Dict[str, int]  # section -> confidence score (0-100)
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
    sections: Dict[str, str]  # section_name -> content
    citations: List[str]
    metadata: ReportMetadata
    file_path: Path


@dataclass
class QAAnalysis:
    """Complete QA analysis results."""
    overall_score: int  # 0-100
    section_scores: Dict[str, int]
    issues: List[ClassifiedIssue]
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
    detailed_analysis: Optional[QAAnalysis]  # Full analysis for workspace storage
    needs_attention: bool  # True if grade < 70
    error_message: Optional[str] = None  # Error message if QA failed


@dataclass
class QAReport:
    """Formatted QA report for file output."""
    company_name: str
    analysis: QAAnalysis
    summary: str
    detailed_findings: str
    recommendations: List[str]
    generated_at: datetime