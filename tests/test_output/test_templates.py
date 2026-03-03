"""
Tests for the report template system.
"""

import pytest

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

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_report_template()
    yield
    reset_report_template()


@pytest.fixture
def template():
    """Create a fresh template."""
    return ReportTemplate()


@pytest.fixture
def sample_sections():
    """Sample research sections."""
    return {
        "overview": "Acme Corp is a leading technology company.",
        "financials": "Revenue of $2.5 billion with 25% growth.",
        "leadership": "CEO John Smith leads the company.",
        "products": "CloudPlatform is the flagship product.",
    }


@pytest.fixture
def sample_report(template, sample_sections):
    """Create a sample report."""
    return template.create_report("Acme Corp", sample_sections)


# =============================================================================
# REPORT SECTION TESTS
# =============================================================================

class TestReportSection:
    """Tests for ReportSection dataclass."""

    def test_word_count(self):
        """Test word count calculation."""
        section = ReportSection(
            section_type=SectionType.OVERVIEW,
            title="Overview",
            content="This is a test with five words.",
        )
        assert section.word_count == 7

    def test_empty_content(self):
        """Test empty content word count."""
        section = ReportSection(
            section_type=SectionType.OVERVIEW,
            title="Overview",
            content="",
        )
        assert section.word_count == 0


# =============================================================================
# REPORT STYLE TESTS
# =============================================================================

class TestReportStyle:
    """Tests for ReportStyle dataclass."""

    def test_default_values(self):
        """Test default style values."""
        style = ReportStyle()
        assert style.primary_color == "#1a73e8"
        assert style.body_font == "Georgia"
        assert style.body_size == 11

    def test_custom_values(self):
        """Test custom style values."""
        style = ReportStyle(
            primary_color="#ff0000",
            body_font="Times New Roman",
        )
        assert style.primary_color == "#ff0000"
        assert style.body_font == "Times New Roman"


# =============================================================================
# REPORT METADATA TESTS
# =============================================================================

class TestReportMetadata:
    """Tests for ReportMetadata dataclass."""

    def test_default_values(self):
        """Test default metadata values."""
        metadata = ReportMetadata(title="Test Report")
        assert metadata.title == "Test Report"
        assert metadata.author == "Primr"
        assert metadata.version == "1.0"

    def test_created_date_auto(self):
        """Test created date is auto-generated."""
        metadata = ReportMetadata(title="Test")
        assert metadata.created_date is not None
        assert len(metadata.created_date) == 10  # YYYY-MM-DD


# =============================================================================
# REPORT TESTS
# =============================================================================

class TestReport:
    """Tests for Report dataclass."""

    def test_total_word_count(self, sample_report):
        """Test total word count calculation."""
        assert sample_report.total_word_count > 0

    def test_section_count(self, sample_report):
        """Test section count."""
        assert sample_report.section_count >= 4

    def test_get_section(self, sample_report):
        """Test getting section by type."""
        overview = sample_report.get_section(SectionType.OVERVIEW)
        assert overview is not None
        assert overview.section_type == SectionType.OVERVIEW

    def test_get_section_not_found(self, sample_report):
        """Test getting non-existent section."""
        appendix = sample_report.get_section(SectionType.APPENDIX)
        assert appendix is None

    def test_add_section(self, sample_report):
        """Test adding a section."""
        initial_count = sample_report.section_count
        sample_report.add_section(ReportSection(
            section_type=SectionType.APPENDIX,
            title="Appendix",
            content="Additional information.",
        ))
        assert sample_report.section_count == initial_count + 1


# =============================================================================
# REPORT TEMPLATE TESTS
# =============================================================================

class TestReportTemplate:
    """Tests for ReportTemplate class."""

    def test_create_report(self, template, sample_sections):
        """Test report creation."""
        report = template.create_report("Acme Corp", sample_sections)

        assert isinstance(report, Report)
        assert report.metadata.title == "Acme Corp - Company Research Report"

    def test_create_report_with_metadata(self, template, sample_sections):
        """Test report creation with custom metadata."""
        metadata = ReportMetadata(
            title="Custom Title",
            author="Test Author",
        )
        report = template.create_report("Acme", sample_sections, metadata)

        assert report.metadata.title == "Custom Title"
        assert report.metadata.author == "Test Author"

    def test_create_report_with_style(self, template, sample_sections):
        """Test report creation with custom style."""
        style = ReportStyle(primary_color="#ff0000")
        report = template.create_report("Acme", sample_sections, style=style)

        assert report.style.primary_color == "#ff0000"

    def test_section_mapping(self, template, sample_sections):
        """Test section type mapping."""
        report = template.create_report("Acme", sample_sections)

        # Check sections were mapped correctly
        assert report.get_section(SectionType.OVERVIEW) is not None
        assert report.get_section(SectionType.FINANCIALS) is not None
        assert report.get_section(SectionType.LEADERSHIP) is not None


# =============================================================================
# RENDERING TESTS
# =============================================================================

class TestRendering:
    """Tests for report rendering."""

    def test_render_markdown(self, template, sample_report):
        """Test markdown rendering."""
        output = template.render(sample_report, OutputFormat.MARKDOWN)

        assert "# " in output  # Has heading
        assert "Acme Corp" in output
        assert "## " in output  # Has subheadings

    def test_render_html(self, template, sample_report):
        """Test HTML rendering."""
        output = template.render(sample_report, OutputFormat.HTML)

        assert "<!DOCTYPE html>" in output
        assert "<html" in output
        assert "Acme Corp" in output
        assert "</html>" in output

    def test_render_text(self, template, sample_report):
        """Test plain text rendering."""
        output = template.render(sample_report, OutputFormat.TEXT)

        assert "ACME CORP" in output.upper()
        assert "=" in output  # Has separators

    def test_render_default_markdown(self, template, sample_report):
        """Test default format is markdown."""
        output = template.render(sample_report)

        assert "# " in output


# =============================================================================
# TABLE OF CONTENTS TESTS
# =============================================================================

class TestTableOfContents:
    """Tests for table of contents generation."""

    def test_generate_toc(self, template, sample_report):
        """Test TOC generation."""
        toc = template.generate_toc(sample_report)

        assert "Table of Contents" in toc
        assert "Overview" in toc or "overview" in toc.lower()

    def test_toc_excludes_title(self, template, sample_report):
        """Test TOC excludes title section."""
        toc = template.generate_toc(sample_report)

        # Title section should not be in TOC
        lines = toc.split('\n')
        assert not any("Research Report]" in line for line in lines)


# =============================================================================
# HTML SPECIFIC TESTS
# =============================================================================

class TestHtmlRendering:
    """Tests for HTML-specific rendering."""

    def test_html_has_styles(self, template, sample_report):
        """Test HTML includes styles."""
        output = template.render(sample_report, OutputFormat.HTML)

        assert "<style>" in output
        assert "font-family" in output

    def test_html_uses_style_colors(self, template, sample_sections):
        """Test HTML uses style colors."""
        style = ReportStyle(primary_color="#123456")
        report = template.create_report("Acme", sample_sections, style=style)
        output = template.render(report, OutputFormat.HTML)

        assert "#123456" in output

    def test_html_has_navigation(self, template, sample_report):
        """Test HTML has navigation/TOC."""
        output = template.render(sample_report, OutputFormat.HTML)

        assert "<nav" in output or "toc" in output.lower()

    def test_html_escapes_content(self, template):
        """Test HTML escapes special characters."""
        sections = {"overview": "Test <script>alert('xss')</script>"}
        report = template.create_report("Acme", sections)
        output = template.render(report, OutputFormat.HTML)

        assert "<script>" not in output
        assert "&lt;script&gt;" in output


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""

    def test_get_template_returns_same(self):
        """Test get_report_template returns same instance."""
        t1 = get_report_template()
        t2 = get_report_template()
        assert t1 is t2

    def test_reset_template(self):
        """Test reset creates new instance."""
        t1 = get_report_template()
        reset_report_template()
        t2 = get_report_template()
        assert t1 is not t2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_report_function(self, sample_sections):
        """Test create_report convenience function."""
        report = create_report("Acme", sample_sections)
        assert isinstance(report, Report)

    def test_render_report_function(self, sample_report):
        """Test render_report convenience function."""
        output = render_report(sample_report, OutputFormat.HTML)
        assert "<html" in output

    def test_generate_report_function(self, sample_sections):
        """Test generate_report convenience function."""
        output = generate_report("Acme", sample_sections, OutputFormat.MARKDOWN)
        assert "# " in output
        assert "Acme" in output


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_sections(self, template):
        """Test with empty sections."""
        report = template.create_report("Acme", {})

        assert report is not None
        assert report.section_count >= 1  # At least title

    def test_unknown_section_name(self, template):
        """Test with unknown section name."""
        sections = {"custom_section": "Custom content here."}
        report = template.create_report("Acme", sections)

        # Should create a CUSTOM type section
        custom = None
        for s in report.sections:
            if s.section_type == SectionType.CUSTOM:
                custom = s
                break

        assert custom is not None

    def test_special_characters_in_title(self, template):
        """Test company name with special characters."""
        report = template.create_report("Acme & Co. <Inc>", {"overview": "Test"})

        # Should handle gracefully
        assert report.metadata.title is not None

    def test_long_content(self, template):
        """Test with long content."""
        long_content = "This is a test sentence. " * 1000
        sections = {"overview": long_content}
        report = template.create_report("Acme", sections)

        output = template.render(report, OutputFormat.MARKDOWN)
        assert len(output) > 10000
