"""
Data models for the premium report generation system.

This module defines the core dataclasses used throughout the report generation
pipeline, from markdown parsing to document building.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedLine:
    """Represents a single parsed line from markdown content.

    Attributes:
        type: Line type - 'heading', 'subheading', 'bullet', 'numbered',
              'text', 'empty', 'inline_header'
        content: The actual text content (without markdown syntax)
        level: Heading level (1-4) or indent level (0-3) for lists
        raw: Original line for debugging
        metadata: Additional parsing metadata
            - 'header_text': for inline_header type
            - 'bullet_char': the bullet character used (*, -, •)
            - 'number': the number for numbered lists
            - 'detected': True if subheading was detected from context
    """

    type: str
    content: str
    level: int
    raw: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ContentBlock:
    """Represents a group of related parsed lines.

    Attributes:
        type: Block type - 'paragraph', 'bullet_list', 'numbered_list',
              'subheading_group', 'heading'
        lines: List of ParsedLine objects in this block
        properties: Block-level properties
            - 'subheading': str for subheading_group type
            - 'indent_level': int for nested lists
    """

    type: str
    lines: list[ParsedLine]
    properties: dict = field(default_factory=dict)


@dataclass
class SectionContent:
    """Represents a section within a chapter.

    Attributes:
        number: Section number string (e.g., "1.1", "1.2")
        title: Display title (e.g., "Mission & Vision")
        key: Internal key (e.g., "mission_vision")
        blocks: List of ContentBlock objects
        has_content: False if section was empty/missing
    """

    number: str
    title: str
    key: str
    blocks: list[ContentBlock] = field(default_factory=list)
    has_content: bool = True


@dataclass
class ChapterContent:
    """Represents a chapter containing multiple sections.

    Attributes:
        number: Chapter number (1-5)
        title: Chapter title (e.g., "Company Profile")
        icon: Optional visual element (e.g., "🏢")
        sections: List of SectionContent objects
    """

    number: int
    title: str
    icon: str | None = None
    sections: list[SectionContent] = field(default_factory=list)


@dataclass
class CompanySnapshot:
    """Key company information for the snapshot box.

    Attributes:
        company_name: Company name
        website: Company website URL
        industry: Industry classification
        founded: Year founded (extracted from history)
        headquarters: HQ location (extracted from content)
        revenue: Annual revenue (extracted from financial)
        employees: Employee count (extracted from content)
        ticker: Stock ticker symbol (extracted from financial)
    """

    company_name: str
    website: str = ""
    industry: str = ""
    founded: str | None = None
    headquarters: str | None = None
    revenue: str | None = None
    employees: str | None = None
    ticker: str | None = None


@dataclass
class DocumentMetadata:
    """Metadata for the generated document.

    Attributes:
        company_name: Company name
        generation_date: Date the report was generated
        report_title: Title of the report
        confidentiality: Confidentiality notice
        version: Document version
    """

    company_name: str
    generation_date: str = field(default_factory=lambda: datetime.now().strftime("%B %d, %Y"))
    report_title: str = "Strategic Company Overview"
    confidentiality: str = "Confidential"
    version: str = "1.0"


@dataclass
class ExecutiveSummary:
    """Executive summary content.

    Attributes:
        narrative: 3-5 paragraph synthesis using Situation-Complication-Resolution
        key_takeaways: 5-7 bullet points of key insights
        metrics_snapshot: Key numbers for callout display
        risk_factors: Top 3-5 risk factors
        one_liner: Single sentence company summary (dinner test)
    """

    narrative: str = ""
    key_takeaways: list[str] = field(default_factory=list)
    metrics_snapshot: dict[str, str] = field(default_factory=dict)
    risk_factors: list[str] = field(default_factory=list)
    one_liner: str = ""
