"""
Tests for the Report Assembler.

**Feature: consulting-tier-report**
"""
import pytest
from datetime import datetime
import tempfile
import os

from primr.output.report_assembler import ReportAssembler
from primr.core.report_models import (
    Report, ReportMetadata, SectionContent, SourceCitation,
    Insight, ConfidenceLevel, InsightCategory, SourceType, ConfidenceNote
)


def create_source_citation(url: str = "https://example.com", title: str = "Test Source") -> SourceCitation:
    """Create a test source citation."""
    return SourceCitation(
        url=url,
        title=title,
        source_type=SourceType.COMPANY_WEBSITE,
        accessed_at=datetime.now(),
        excerpt="Sample excerpt from the source."
    )


def create_section(
    title: str = "Test Section",
    content: str = "Test content",
    sources: list = None
) -> SectionContent:
    """Create a test section."""
    if sources is None:
        sources = [create_source_citation()]
    return SectionContent(title=title, content=content, sources=sources)


def create_insight() -> Insight:
    """Create a test insight."""
    return Insight(
        title="Test Insight",
        description="Test description",
        evidence=["Evidence 1"],
        confidence=ConfidenceLevel.VERIFIED,
        category=InsightCategory.STRATEGIC,
        sources=["https://example.com"]
    )


class TestReportAssemblerSourcesAppendix:
    """**Property 9: Sources Appendix** - verify appendix contains all URLs with timestamps."""
    
    def test_sources_appendix_contains_all_urls(self):
        """Sources appendix should contain all referenced URLs."""
        assembler = ReportAssembler()
        
        # Create sections with different sources
        exec_summary = create_section(
            title="Executive Summary",
            sources=[create_source_citation("https://source1.com", "Source 1")]
        )
        
        sections = [
            create_section(
                title="Section 1",
                sources=[create_source_citation("https://source2.com", "Source 2")]
            ),
            create_section(
                title="Section 2",
                sources=[create_source_citation("https://source3.com", "Source 3")]
            ),
        ]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[create_insight()],
            research_duration=60.0
        )
        
        # Check all sources are in appendix
        source_urls = [s.url for s in report.sources_appendix]
        assert "https://source1.com" in source_urls
        assert "https://source2.com" in source_urls
        assert "https://source3.com" in source_urls
    
    def test_sources_appendix_has_timestamps(self):
        """Each source should have an access timestamp."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary")
        sections = [create_section(title="Section 1")]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[],
            research_duration=60.0
        )
        
        for source in report.sources_appendix:
            assert source.accessed_at is not None
            assert isinstance(source.accessed_at, datetime)
    
    def test_sources_appendix_deduplicates(self):
        """Should not duplicate sources with same URL."""
        assembler = ReportAssembler()
        
        same_source = create_source_citation("https://same.com", "Same Source")
        
        exec_summary = create_section(title="Executive Summary", sources=[same_source])
        sections = [create_section(title="Section 1", sources=[same_source])]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[],
            research_duration=60.0
        )
        
        # Should only have one instance of the source
        source_urls = [s.url for s in report.sources_appendix]
        assert source_urls.count("https://same.com") == 1
    
    def test_generate_sources_appendix_format(self):
        """Generated appendix should have proper format."""
        assembler = ReportAssembler()
        
        sources = [
            create_source_citation("https://example1.com", "Example 1"),
            create_source_citation("https://example2.com", "Example 2"),
        ]
        
        appendix = assembler.generate_sources_appendix(sources)
        
        assert "Sources" in appendix
        assert "https://example1.com" in appendix
        assert "https://example2.com" in appendix
        assert "Accessed:" in appendix


class TestReportAssemblerConfidenceMarking:
    """**Property 8: Confidence Marking** - verify estimated data has confidence indicators."""
    
    def test_confidence_notes_preserved(self):
        """Confidence notes should be preserved in assembled report."""
        assembler = ReportAssembler()
        
        confidence_note = ConfidenceNote(
            statement="Revenue estimate",
            confidence=ConfidenceLevel.ESTIMATED,
            basis="Based on employee count"
        )
        
        exec_summary = SectionContent(
            title="Executive Summary",
            content="Summary content",
            sources=[create_source_citation()],
            confidence_notes=[confidence_note]
        )
        
        sections = [create_section()]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[],
            research_duration=60.0
        )
        
        assert len(report.executive_summary.confidence_notes) > 0
        assert report.executive_summary.confidence_notes[0].confidence == ConfidenceLevel.ESTIMATED
    
    def test_markdown_includes_confidence_notes(self):
        """Markdown export should include confidence notes."""
        assembler = ReportAssembler()
        
        confidence_note = ConfidenceNote(
            statement="Revenue estimate",
            confidence=ConfidenceLevel.ESTIMATED,
            basis="Based on employee count"
        )
        
        section = SectionContent(
            title="Financial Overview",
            content="Financial content",
            sources=[create_source_citation()],
            confidence_notes=[confidence_note]
        )
        
        exec_summary = create_section(title="Executive Summary")
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=[section],
            insights=[],
            research_duration=60.0
        )
        
        markdown = assembler.to_markdown(report)
        
        assert "Confidence Notes" in markdown
        assert "estimated" in markdown.lower()


class TestReportAssemblerAssembly:
    """Test report assembly."""
    
    def test_assembles_complete_report(self):
        """Should assemble a complete report with all components."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary", content="Summary content")
        sections = [
            create_section(title="Industry Analysis", content="Industry content"),
            create_section(title="Financial Overview", content="Financial content"),
        ]
        insights = [create_insight()]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=insights,
            research_duration=120.0
        )
        
        assert report.metadata.company_name == "Test Company"
        assert report.metadata.website == "https://test.com"
        assert report.metadata.industry == "Technology"
        assert report.metadata.research_duration_seconds == 120.0
        assert report.executive_summary.title == "Executive Summary"
        assert len(report.sections) == 2
        assert len(report.insights) == 1
    
    def test_generates_toc(self):
        """Should generate table of contents."""
        assembler = ReportAssembler()
        
        sections = [
            create_section(title="Industry Analysis"),
            create_section(title="Financial Overview"),
            create_section(title="Competitive Analysis"),
        ]
        
        toc = assembler.generate_toc(sections)
        
        assert "Table of Contents" in toc
        assert "Executive Summary" in toc
        assert "Industry Analysis" in toc
        assert "Financial Overview" in toc
        assert "Competitive Analysis" in toc
        assert "Sources" in toc


class TestReportAssemblerMarkdown:
    """Test Markdown export."""
    
    def test_exports_to_markdown(self):
        """Should export report to Markdown format."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary", content="Summary content")
        sections = [create_section(title="Section 1", content="Section content")]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[],
            research_duration=60.0
        )
        
        markdown = assembler.to_markdown(report)
        
        assert "# Test Company Company Research Report" in markdown
        assert "## Executive Summary" in markdown
        assert "## Section 1" in markdown
        assert "## Sources" in markdown
    
    def test_markdown_includes_metadata(self):
        """Markdown should include report metadata."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary")
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=[],
            insights=[],
            research_duration=60.0
        )
        
        markdown = assembler.to_markdown(report)
        
        assert "Technology" in markdown
        assert "https://test.com" in markdown


class TestReportAssemblerValidation:
    """Test report validation."""
    
    def test_validates_complete_report(self):
        """Should validate a complete report as valid."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary", content="Content")
        sections = [create_section(title="Section 1", content="Content")]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[],
            research_duration=60.0
        )
        
        is_valid, issues = assembler.validate_report(report)
        
        assert is_valid
        assert len(issues) == 0
    
    def test_detects_missing_company_name(self):
        """Should detect missing company name."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary")
        
        report = assembler.assemble(
            company_name="",  # Empty
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=[create_section()],
            insights=[],
            research_duration=60.0
        )
        
        is_valid, issues = assembler.validate_report(report)
        
        assert not is_valid
        assert any("company name" in issue.lower() for issue in issues)
    
    def test_detects_empty_executive_summary(self):
        """Should detect empty executive summary."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary", content="")
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=[create_section()],
            insights=[],
            research_duration=60.0
        )
        
        is_valid, issues = assembler.validate_report(report)
        
        assert not is_valid
        assert any("executive summary" in issue.lower() for issue in issues)
    
    def test_detects_no_sections(self):
        """Should detect report with no sections."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary", content="Content")
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=[],  # No sections
            insights=[],
            research_duration=60.0
        )
        
        is_valid, issues = assembler.validate_report(report)
        
        assert not is_valid
        assert any("no sections" in issue.lower() for issue in issues)
    
    def test_detects_no_sources(self):
        """Should detect report with no sources."""
        assembler = ReportAssembler()
        
        exec_summary = create_section(title="Executive Summary", content="Content", sources=[])
        sections = [create_section(title="Section 1", content="Content", sources=[])]
        
        report = assembler.assemble(
            company_name="Test Company",
            website="https://test.com",
            industry="Technology",
            executive_summary=exec_summary,
            sections=sections,
            insights=[],
            research_duration=60.0
        )
        
        is_valid, issues = assembler.validate_report(report)
        
        assert not is_valid
        assert any("sources" in issue.lower() for issue in issues)
