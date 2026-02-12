"""
Output module - Report generation and formatting.

This module provides premium consultant-grade report generation capabilities
including professional document structure, styling, and content synthesis.
"""

from primr.output.chapter_config import (
    CHAPTER_CONFIG,
    EXECUTIVE_SUMMARY_SOURCES,
    SNAPSHOT_FIELDS,
)
from primr.output.content_pattern_detector import ContentPatternDetector
from primr.output.document_builder import DocumentBuilder
from primr.output.executive_summary import (
    ConfidenceIndicator,
    ExecutiveSummary,
    ExecutiveSummaryGenerator,
    FindingCategory,
    KeyFinding,
    SourceCitation,
    extract_key_points,
    format_executive_summary,
    generate_executive_summary,
    generate_one_liner,
    get_summary_generator,
    reset_summary_generator,
)
from primr.output.executive_summary_generator import (
    ExecutiveSummaryGenerator as PremiumExecutiveSummaryGenerator,
)
from primr.output.markdown_parser import ArtifactDetector, MarkdownParser

# Premium report generation components
from primr.output.models import (
    ChapterContent,
    CompanySnapshot,
    ContentBlock,
    DocumentMetadata,
    ParsedLine,
    SectionContent,
)
from primr.output.polish_elements import (
    DataConfidenceIndicator,
    DocumentDisclaimer,
    FinancialDashboard,
    KeyImplicationsBox,
    OneLinerSummary,
    QuickWinsSection,
    StrategicRecommendationFormatter,
)
from primr.output.report_assembler import ReportAssembler
from primr.output.section_writer import SectionWriter
from primr.output.style_engine import DualCodingEnhancer, StyleEngine
from primr.output.table_builder import TableBuilder
from primr.output.templates import (
    OutputFormat,
    Report,
    ReportMetadata,
    ReportSection,
    ReportStyle,
    ReportTemplate,
    SectionType,
    create_report,
    generate_report,
    get_report_template,
    render_report,
    reset_report_template,
)

__all__ = [
    # Executive summary
    "ExecutiveSummaryGenerator",
    "ExecutiveSummary",
    "KeyFinding",
    "FindingCategory",
    "ConfidenceIndicator",
    "SourceCitation",
    "get_summary_generator",
    "reset_summary_generator",
    "generate_executive_summary",
    "generate_one_liner",
    "extract_key_points",
    "format_executive_summary",
    # Templates
    "ReportTemplate",
    "Report",
    "ReportSection",
    "ReportStyle",
    "ReportMetadata",
    "OutputFormat",
    "SectionType",
    "get_report_template",
    "reset_report_template",
    "create_report",
    "render_report",
    "generate_report",
    # Consulting-tier components
    "SectionWriter",
    "ReportAssembler",
    # Premium report generation
    "DocumentBuilder",
    "StyleEngine",
    "DualCodingEnhancer",
    "MarkdownParser",
    "ArtifactDetector",
    "TableBuilder",
    "ContentPatternDetector",
    "PremiumExecutiveSummaryGenerator",
    "ParsedLine",
    "ContentBlock",
    "ChapterContent",
    "SectionContent",
    "CompanySnapshot",
    "DocumentMetadata",
    "CHAPTER_CONFIG",
    "SNAPSHOT_FIELDS",
    "EXECUTIVE_SUMMARY_SOURCES",
    # Polish elements
    "OneLinerSummary",
    "DocumentDisclaimer",
    "KeyImplicationsBox",
    "StrategicRecommendationFormatter",
    "QuickWinsSection",
    "FinancialDashboard",
    "DataConfidenceIndicator",
]
