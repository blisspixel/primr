"""
Core data models for consulting-tier reports.

Provides structured types for source tracking, confidence levels,
insights, and report sections.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceType(Enum):
    """Types of data sources for research."""
    COMPANY_WEBSITE = "company_website"
    NEWS_ARTICLE = "news_article"
    SEC_FILING = "sec_filing"
    LINKEDIN = "linkedin"
    CRUNCHBASE = "crunchbase"
    GLASSDOOR = "glassdoor"
    JOB_POSTING = "job_posting"
    ESTIMATE = "estimate"
    INDUSTRY_REPORT = "industry_report"
    PRESS_RELEASE = "press_release"


class ConfidenceLevel(Enum):
    """Confidence levels for data points."""
    VERIFIED = "verified"      # Direct from official source
    REPORTED = "reported"      # From credible news/reports
    INFERRED = "inferred"      # Derived from multiple signals
    ESTIMATED = "estimated"    # Best guess based on available data


class InsightCategory(Enum):
    """Categories for strategic insights."""
    STRATEGIC = "strategic"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    COMPETITIVE = "competitive"
    TECHNOLOGY = "technology"
    LEADERSHIP = "leadership"


@dataclass
class SourceCitation:
    """A citation to a data source."""
    url: str
    title: str
    source_type: SourceType
    accessed_at: datetime
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "source_type": self.source_type.value,
            "accessed_at": self.accessed_at.isoformat(),
            "excerpt": self.excerpt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceCitation":
        return cls(
            url=data["url"],
            title=data["title"],
            source_type=SourceType(data["source_type"]),
            accessed_at=datetime.fromisoformat(data["accessed_at"]),
            excerpt=data.get("excerpt", ""),
        )


@dataclass
class GatheredData:
    """Data gathered from a source during research."""
    content: str
    source_url: str
    source_type: SourceType
    confidence: float  # 0.0 to 1.0
    gathered_at: datetime
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "source_url": self.source_url,
            "source_type": self.source_type.value,
            "confidence": self.confidence,
            "gathered_at": self.gathered_at.isoformat(),
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatheredData":
        return cls(
            content=data["content"],
            source_url=data["source_url"],
            source_type=SourceType(data["source_type"]),
            confidence=data["confidence"],
            gathered_at=datetime.fromisoformat(data["gathered_at"]),
            title=data.get("title", ""),
        )


@dataclass
class ConfidenceNote:
    """A note about confidence level for a statement."""
    statement: str
    confidence: ConfidenceLevel
    basis: str  # Why this confidence level

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "confidence": self.confidence.value,
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfidenceNote":
        return cls(
            statement=data["statement"],
            confidence=ConfidenceLevel(data["confidence"]),
            basis=data["basis"],
        )


@dataclass
class Insight:
    """A strategic insight extracted from research data."""
    title: str
    description: str
    evidence: list[str]
    confidence: ConfidenceLevel
    category: InsightCategory
    sources: list[str]
    rationale: str = ""  # For recommendations

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "confidence": self.confidence.value,
            "category": self.category.value,
            "sources": self.sources,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Insight":
        return cls(
            title=data["title"],
            description=data["description"],
            evidence=data["evidence"],
            confidence=ConfidenceLevel(data["confidence"]),
            category=InsightCategory(data["category"]),
            sources=data["sources"],
            rationale=data.get("rationale", ""),
        )


@dataclass
class SectionContent:
    """Content for a report section."""
    title: str
    content: str
    sources: list[SourceCitation] = field(default_factory=list)
    confidence_notes: list[ConfidenceNote] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "sources": [s.to_dict() for s in self.sources],
            "confidence_notes": [n.to_dict() for n in self.confidence_notes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectionContent":
        return cls(
            title=data["title"],
            content=data["content"],
            sources=[SourceCitation.from_dict(s) for s in data.get("sources", [])],
            confidence_notes=[ConfidenceNote.from_dict(n) for n in data.get("confidence_notes", [])],
        )


@dataclass
class ReportMetadata:
    """Metadata about a generated report."""
    company_name: str
    website: str
    industry: str
    generated_at: datetime
    research_duration_seconds: float
    sources_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "website": self.website,
            "industry": self.industry,
            "generated_at": self.generated_at.isoformat(),
            "research_duration_seconds": self.research_duration_seconds,
            "sources_count": self.sources_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReportMetadata":
        return cls(
            company_name=data["company_name"],
            website=data["website"],
            industry=data["industry"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            research_duration_seconds=data["research_duration_seconds"],
            sources_count=data["sources_count"],
        )


@dataclass
class Report:
    """A complete research report."""
    metadata: ReportMetadata
    executive_summary: SectionContent
    sections: list[SectionContent]
    sources_appendix: list[SourceCitation]
    insights: list[Insight] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "executive_summary": self.executive_summary.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
            "sources_appendix": [s.to_dict() for s in self.sources_appendix],
            "insights": [i.to_dict() for i in self.insights],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Report":
        return cls(
            metadata=ReportMetadata.from_dict(data["metadata"]),
            executive_summary=SectionContent.from_dict(data["executive_summary"]),
            sections=[SectionContent.from_dict(s) for s in data["sections"]],
            sources_appendix=[SourceCitation.from_dict(s) for s in data["sources_appendix"]],
            insights=[Insight.from_dict(i) for i in data.get("insights", [])],
        )


@dataclass
class QualityScore:
    """Quality assessment for a section."""
    score: float  # 0-10
    issues: list[str]
    suggestions: list[str]
    needs_refinement: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "needs_refinement": self.needs_refinement,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityScore":
        return cls(
            score=data["score"],
            issues=data["issues"],
            suggestions=data["suggestions"],
            needs_refinement=data["needs_refinement"],
        )
