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
from primr.output.final_artifact import (
    FinalDocument,
    FinalSection,
    GeneratedSection,
    canonicalize_final_markdown,
    parse_final_markdown,
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
    "CHAPTER_CONFIG",
    "EXECUTIVE_SUMMARY_SOURCES",
    "SNAPSHOT_FIELDS",
    "ArtifactDetector",
    "ChapterContent",
    "CompanySnapshot",
    "ConfidenceIndicator",
    "ContentBlock",
    "ContentPatternDetector",
    "DataConfidenceIndicator",
    "DocumentBuilder",
    "DocumentDisclaimer",
    "DocumentMetadata",
    "DualCodingEnhancer",
    "ExecutiveSummary",
    "ExecutiveSummaryGenerator",
    "FinalDocument",
    "FinalSection",
    "GeneratedSection",
    "FinancialDashboard",
    "FindingCategory",
    "KeyFinding",
    "KeyImplicationsBox",
    "MarkdownParser",
    "OneLinerSummary",
    "OutputFormat",
    "ParsedLine",
    "PremiumExecutiveSummaryGenerator",
    "QuickWinsSection",
    "Report",
    "ReportAssembler",
    "ReportMetadata",
    "ReportSection",
    "ReportStyle",
    "ReportTemplate",
    "SectionContent",
    "SectionType",
    "SectionWriter",
    "SourceCitation",
    "StrategicRecommendationFormatter",
    "StyleEngine",
    "TableBuilder",
    "canonicalize_final_markdown",
    "create_report",
    "extract_key_points",
    "format_executive_summary",
    "generate_executive_summary",
    "generate_one_liner",
    "generate_report",
    "get_report_template",
    "get_summary_generator",
    "parse_final_markdown",
    "render_report",
    "reset_report_template",
    "reset_summary_generator",
]
