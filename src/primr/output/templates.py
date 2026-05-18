"""
Report template system for multi-format output.

This module provides:
- Template-based report generation
- Multiple output formats (DOCX, PDF, HTML)
- Customizable styling and branding
- Section-based report structure
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger("output.templates")


class OutputFormat(Enum):
    """Supported output formats."""

    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"
    DOCX = "docx"
    PDF = "pdf"


class SectionType(Enum):
    """Types of report sections."""

    TITLE = "title"
    EXECUTIVE_SUMMARY = "executive_summary"
    TABLE_OF_CONTENTS = "table_of_contents"
    OVERVIEW = "overview"
    FINANCIALS = "financials"
    LEADERSHIP = "leadership"
    PRODUCTS = "products"
    MARKET = "market"
    NEWS = "news"
    SWOT = "swot"
    RECOMMENDATIONS = "recommendations"
    SOURCES = "sources"
    APPENDIX = "appendix"
    CUSTOM = "custom"


@dataclass
class ReportSection:
    """A section of the report."""

    section_type: SectionType
    title: str
    content: str
    subsections: list["ReportSection"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    include_in_toc: bool = True
    page_break_before: bool = False

    @property
    def word_count(self) -> int:
        """Get word count of section."""
        return len(self.content.split())


@dataclass
class ReportStyle:
    """Styling configuration for reports."""

    # Colors
    primary_color: str = "#1a73e8"
    secondary_color: str = "#5f6368"
    accent_color: str = "#34a853"
    background_color: str = "#ffffff"
    text_color: str = "#202124"

    # Fonts
    heading_font: str = "Arial"
    body_font: str = "Georgia"
    code_font: str = "Consolas"

    # Sizes
    title_size: int = 24
    heading1_size: int = 18
    heading2_size: int = 14
    body_size: int = 11

    # Spacing
    line_height: float = 1.5
    paragraph_spacing: int = 12

    # Branding
    logo_path: str | None = None
    company_name: str = ""
    footer_text: str = ""


@dataclass
class ReportMetadata:
    """Metadata for the report."""

    title: str
    subject: str = ""
    author: str = "Primr"
    created_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    version: str = "1.0"
    confidentiality: str = "Internal Use Only"
    keywords: list[str] = field(default_factory=list)


@dataclass
class Report:
    """Complete report structure."""

    metadata: ReportMetadata
    sections: list[ReportSection] = field(default_factory=list)
    style: ReportStyle = field(default_factory=ReportStyle)

    @property
    def total_word_count(self) -> int:
        """Get total word count."""
        return sum(s.word_count for s in self.sections)

    @property
    def section_count(self) -> int:
        """Get number of sections."""
        return len(self.sections)

    def get_section(self, section_type: SectionType) -> ReportSection | None:
        """Get a section by type."""
        for section in self.sections:
            if section.section_type == section_type:
                return section
        return None

    def add_section(self, section: ReportSection) -> None:
        """Add a section to the report."""
        self.sections.append(section)


class ReportTemplate:
    """
    Template for generating reports.

    Example:
        template = ReportTemplate()
        report = template.create_report(
            company_name="Acme Corp",
            sections={"overview": "...", "financials": "..."}
        )
        html = template.render(report, OutputFormat.HTML)
    """

    # Default section order
    DEFAULT_SECTION_ORDER = [
        SectionType.TITLE,
        SectionType.EXECUTIVE_SUMMARY,
        SectionType.TABLE_OF_CONTENTS,
        SectionType.OVERVIEW,
        SectionType.FINANCIALS,
        SectionType.LEADERSHIP,
        SectionType.PRODUCTS,
        SectionType.MARKET,
        SectionType.NEWS,
        SectionType.SWOT,
        SectionType.RECOMMENDATIONS,
        SectionType.SOURCES,
    ]

    # Section title mappings
    SECTION_TITLES = {
        SectionType.TITLE: "Company Research Report",
        SectionType.EXECUTIVE_SUMMARY: "Executive Summary",
        SectionType.TABLE_OF_CONTENTS: "Table of Contents",
        SectionType.OVERVIEW: "Company Overview",
        SectionType.FINANCIALS: "Financial Analysis",
        SectionType.LEADERSHIP: "Leadership & Management",
        SectionType.PRODUCTS: "Products & Services",
        SectionType.MARKET: "Market Position",
        SectionType.NEWS: "Recent News & Developments",
        SectionType.SWOT: "SWOT Analysis",
        SectionType.RECOMMENDATIONS: "Recommendations",
        SectionType.SOURCES: "Sources & References",
    }

    def __init__(self, style: ReportStyle | None = None):
        """
        Initialize the template.

        Args:
            style: Optional custom style
        """
        self._style = style or ReportStyle()
        self._renderers: dict[OutputFormat, Callable] = {
            OutputFormat.MARKDOWN: self._render_markdown,
            OutputFormat.HTML: self._render_html,
            OutputFormat.TEXT: self._render_text,
        }
        logger.debug("ReportTemplate initialized")

    def create_report(
        self,
        company_name: str,
        sections: dict[str, str],
        metadata: ReportMetadata | None = None,
        style: ReportStyle | None = None,
    ) -> Report:
        """
        Create a report from section content.

        Args:
            company_name: Name of the company
            sections: Dictionary of section name to content
            metadata: Optional report metadata
            style: Optional custom style

        Returns:
            Report object
        """
        # Create metadata
        if metadata is None:
            metadata = ReportMetadata(
                title=f"{company_name} - Company Research Report",
                subject=f"Research report on {company_name}",
                keywords=[company_name, "research", "analysis"],
            )

        # Create report
        report = Report(
            metadata=metadata,
            style=style or self._style,
        )

        # Add title section
        report.add_section(
            ReportSection(
                section_type=SectionType.TITLE,
                title=f"{company_name} Research Report",
                content=f"Comprehensive analysis of {company_name}",
                include_in_toc=False,
            )
        )

        # Map content to sections
        section_mapping = {
            "overview": SectionType.OVERVIEW,
            "about": SectionType.OVERVIEW,
            "company_overview": SectionType.OVERVIEW,
            "financials": SectionType.FINANCIALS,
            "financial": SectionType.FINANCIALS,
            "leadership": SectionType.LEADERSHIP,
            "management": SectionType.LEADERSHIP,
            "products": SectionType.PRODUCTS,
            "services": SectionType.PRODUCTS,
            "products_services": SectionType.PRODUCTS,
            "market": SectionType.MARKET,
            "competition": SectionType.MARKET,
            "news": SectionType.NEWS,
            "recent_news": SectionType.NEWS,
            "swot": SectionType.SWOT,
            "recommendations": SectionType.RECOMMENDATIONS,
            "sources": SectionType.SOURCES,
            "references": SectionType.SOURCES,
        }

        # Add content sections
        added_types = set()
        for section_name, content in sections.items():
            section_type = section_mapping.get(section_name.lower(), SectionType.CUSTOM)

            if section_type in added_types and section_type != SectionType.CUSTOM:
                continue

            title = self.SECTION_TITLES.get(section_type, section_name.replace("_", " ").title())

            report.add_section(
                ReportSection(
                    section_type=section_type,
                    title=title,
                    content=content,
                    page_break_before=section_type
                    in (SectionType.OVERVIEW, SectionType.FINANCIALS),
                )
            )

            added_types.add(section_type)

        return report

    def render(
        self,
        report: Report,
        output_format: OutputFormat = OutputFormat.MARKDOWN,
    ) -> str:
        """
        Render the report to a string.

        Args:
            report: Report to render
            output_format: Output format

        Returns:
            Rendered report string
        """
        renderer = self._renderers.get(output_format)
        if renderer is None:
            logger.warning(f"Unsupported format {output_format}, using markdown")
            renderer = self._render_markdown

        return renderer(report)

    def generate_toc(self, report: Report) -> str:
        """
        Generate table of contents.

        Args:
            report: Report to generate TOC for

        Returns:
            Table of contents string
        """
        toc_lines = ["## Table of Contents", ""]

        for i, section in enumerate(report.sections, 1):
            if section.include_in_toc and section.section_type != SectionType.TITLE:
                toc_lines.append(f"{i}. [{section.title}](#{self._slugify(section.title)})")

        return "\n".join(toc_lines)

    def _render_markdown(self, report: Report) -> str:
        """Render report as markdown."""
        lines = []

        for section in report.sections:
            if section.section_type == SectionType.TITLE:
                lines.extend(
                    [
                        f"# {section.title}",
                        "",
                        f"*{section.content}*",
                        "",
                        f"**Date:** {report.metadata.created_date}",
                        f"**Author:** {report.metadata.author}",
                        "",
                        "---",
                        "",
                    ]
                )
            elif section.section_type == SectionType.TABLE_OF_CONTENTS:
                lines.append(self.generate_toc(report))
                lines.extend(["", "---", ""])
            else:
                if section.page_break_before:
                    lines.append("---")
                    lines.append("")

                lines.append(f"## {section.title}")
                lines.append("")
                lines.append(section.content)
                lines.append("")

        # Add footer
        lines.extend(
            [
                "---",
                "",
                f"*{report.metadata.confidentiality}*",
                f"*Generated by {report.metadata.author}*",
            ]
        )

        return "\n".join(lines)

    def _render_html(self, report: Report) -> str:
        """Render report as HTML."""
        style = report.style

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.metadata.title}</title>
    <style>
        body {{
            font-family: {style.body_font}, serif;
            font-size: {style.body_size}pt;
            line-height: {style.line_height};
            color: {style.text_color};
            background-color: {style.background_color};
            max-width: 800px;
            margin: 0 auto;
            padding: 40px;
        }}
        h1 {{
            font-family: {style.heading_font}, sans-serif;
            font-size: {style.title_size}pt;
            color: {style.primary_color};
            border-bottom: 2px solid {style.primary_color};
            padding-bottom: 10px;
        }}
        h2 {{
            font-family: {style.heading_font}, sans-serif;
            font-size: {style.heading1_size}pt;
            color: {style.primary_color};
            margin-top: 30px;
        }}
        h3 {{
            font-family: {style.heading_font}, sans-serif;
            font-size: {style.heading2_size}pt;
            color: {style.secondary_color};
        }}
        p {{
            margin-bottom: {style.paragraph_spacing}px;
        }}
        .metadata {{
            color: {style.secondary_color};
            font-size: 10pt;
            margin-bottom: 20px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .page-break {{
            page-break-before: always;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid {style.secondary_color};
            font-size: 9pt;
            color: {style.secondary_color};
        }}
        .toc {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
        }}
        .toc ul {{
            list-style-type: none;
            padding-left: 0;
        }}
        .toc li {{
            margin: 8px 0;
        }}
        .toc a {{
            color: {style.primary_color};
            text-decoration: none;
        }}
        .toc a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
"""

        for section in report.sections:
            if section.section_type == SectionType.TITLE:
                html += f"""
    <header>
        <h1>{section.title}</h1>
        <p class="metadata">
            <strong>Date:</strong> {report.metadata.created_date}<br>
            <strong>Author:</strong> {report.metadata.author}<br>
            <strong>Version:</strong> {report.metadata.version}
        </p>
    </header>
"""
            elif section.section_type == SectionType.TABLE_OF_CONTENTS:
                html += """
    <nav class="toc">
        <h2>Table of Contents</h2>
        <ul>
"""
                for s in report.sections:
                    if s.include_in_toc and s.section_type != SectionType.TITLE:
                        slug = self._slugify(s.title)
                        html += f'            <li><a href="#{slug}">{s.title}</a></li>\n'
                html += """        </ul>
    </nav>
"""
            else:
                page_break = ' class="page-break"' if section.page_break_before else ""
                slug = self._slugify(section.title)
                content_html = self._text_to_html(section.content)
                html += f"""
    <section{page_break} id="{slug}">
        <h2>{section.title}</h2>
        {content_html}
    </section>
"""

        html += f"""
    <footer class="footer">
        <p>{report.metadata.confidentiality}</p>
        <p>Generated by {report.metadata.author}</p>
    </footer>
</body>
</html>
"""
        return html

    def _render_text(self, report: Report) -> str:
        """Render report as plain text."""
        lines = []

        for section in report.sections:
            if section.section_type == SectionType.TITLE:
                lines.extend(
                    [
                        "=" * 60,
                        section.title.upper(),
                        "=" * 60,
                        "",
                        section.content,
                        "",
                        f"Date: {report.metadata.created_date}",
                        f"Author: {report.metadata.author}",
                        "",
                    ]
                )
            elif section.section_type == SectionType.TABLE_OF_CONTENTS:
                lines.extend(
                    [
                        "TABLE OF CONTENTS",
                        "-" * 30,
                    ]
                )
                for i, s in enumerate(report.sections, 1):
                    if s.include_in_toc and s.section_type != SectionType.TITLE:
                        lines.append(f"  {i}. {s.title}")
                lines.append("")
            else:
                if section.page_break_before:
                    lines.append("")
                    lines.append("=" * 60)
                    lines.append("")

                lines.extend(
                    [
                        section.title.upper(),
                        "-" * len(section.title),
                        "",
                        section.content,
                        "",
                    ]
                )

        lines.extend(
            [
                "=" * 60,
                report.metadata.confidentiality,
                f"Generated by {report.metadata.author}",
            ]
        )

        return "\n".join(lines)

    def _slugify(self, text: str) -> str:
        """Convert text to URL-safe slug."""
        slug = text.lower()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        return slug.strip("-")

    def _text_to_html(self, text: str) -> str:
        """Convert plain text to HTML paragraphs."""
        paragraphs = text.strip().split("\n\n")
        html_parts = []

        for para in paragraphs:
            para = para.strip()
            if para:
                # Escape HTML
                para = para.replace("&", "&amp;")
                para = para.replace("<", "&lt;")
                para = para.replace(">", "&gt;")
                # Convert single newlines to <br>
                para = para.replace("\n", "<br>")
                html_parts.append(f"<p>{para}</p>")

        return "\n        ".join(html_parts)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_template: ReportTemplate | None = None


def get_report_template() -> ReportTemplate:
    """
    Get the global report template instance.

    Returns:
        ReportTemplate instance
    """
    global _template
    if _template is None:
        _template = ReportTemplate()
    return _template


def reset_report_template() -> None:
    """Reset the global template (useful for testing)."""
    global _template
    _template = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_report(
    company_name: str,
    sections: dict[str, str],
    metadata: ReportMetadata | None = None,
) -> Report:
    """
    Create a report from section content.

    Args:
        company_name: Name of the company
        sections: Dictionary of section name to content
        metadata: Optional report metadata

    Returns:
        Report object
    """
    return get_report_template().create_report(company_name, sections, metadata)


def render_report(
    report: Report,
    output_format: OutputFormat = OutputFormat.MARKDOWN,
) -> str:
    """
    Render a report to string.

    Args:
        report: Report to render
        output_format: Output format

    Returns:
        Rendered report string
    """
    return get_report_template().render(report, output_format)


def generate_report(
    company_name: str,
    sections: dict[str, str],
    output_format: OutputFormat = OutputFormat.MARKDOWN,
) -> str:
    """
    Create and render a report in one step.

    Args:
        company_name: Name of the company
        sections: Dictionary of section name to content
        output_format: Output format

    Returns:
        Rendered report string
    """
    report = create_report(company_name, sections)
    return render_report(report, output_format)
