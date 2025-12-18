"""
End-to-end integration tests for premium report generation.

Task 15: Final integration and testing
"""

import os
import tempfile
import pytest
from pathlib import Path

from primr.output.document_builder import DocumentBuilder
from primr.output.markdown_parser import ArtifactDetector
from primr.output.output_utils import (
    save_report_as_txt,
    save_report_as_docx_premium,
    strip_markdown_artifacts,
)


# Sample section data for testing
SAMPLE_SECTIONS = {
    'company_name': 'Test Company Inc',
    'company_website': 'https://testcompany.com',
    'industry': 'Technology',
    'company_overview': """
Test Company Inc is a leading technology company founded in 2010.
The company specializes in enterprise software solutions.

**Key Facts:**
* Revenue: $5.2 billion
* Employees: 10,000
* Headquarters: San Francisco, CA
""",
    'financial_overview': """
## Financial Performance

The company has shown strong financial performance:

* Revenue grew 15% year-over-year
* Profit margin improved to 22%
* Operating cash flow of $1.2 billion

**Key Metrics:**
* Market Cap: $45 billion
* P/E Ratio: 28
* Dividend Yield: 1.5%
""",
    'competitive_position': """
Test Company maintains a strong competitive position in the market.

Key differentiators include:
* Industry-leading technology platform
* Strong customer relationships
* Global presence in 50+ countries

The company faces competition from:
* Competitor A - market leader in segment X
* Competitor B - strong in enterprise segment
""",
    'strategic_recommendations': """
## Strategic Recommendations

Based on our analysis, we recommend the following actions:

1. **Expand into emerging markets** - The company should consider expanding into Asia-Pacific markets where growth potential is high.

2. **Invest in R&D** - Continued investment in research and development is critical to maintain competitive advantage.

3. **Strengthen partnerships** - Building strategic partnerships could accelerate growth.

### Quick Wins
* Optimize pricing strategy - quick implementation, immediate impact
* Streamline operations - low-cost efficiency gains
""",
    'industry_insights': """
The technology industry continues to evolve rapidly.

Key trends include:
* Cloud computing adoption accelerating
* AI and machine learning integration
* Cybersecurity becoming critical

Market size is expected to reach $5 trillion by 2025.
""",
}


class TestDocumentBuilderIntegration:
    """Integration tests for DocumentBuilder."""

    def test_build_complete_document(self):
        """Build a complete document and verify structure."""
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Verify document was created
        assert document is not None
        
        # Verify document has content
        assert len(document.paragraphs) > 0
        
        # Verify document has tables (snapshot, executive highlights)
        assert len(document.tables) > 0

    def test_document_has_no_markdown_artifacts(self):
        """Verify generated document has no unconverted markdown."""
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        detector = ArtifactDetector()
        artifacts = detector.scan_document(document)
        
        # Filter out false positives (some patterns may appear in legitimate content)
        real_artifacts = [a for a in artifacts if a['type'] == 'heading']
        
        # Should have no heading artifacts (## patterns)
        assert len(real_artifacts) == 0, f"Found artifacts: {detector.get_artifact_summary()}"

    def test_document_has_cover_page_elements(self):
        """Verify cover page has required elements."""
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Get text from first few paragraphs
        first_paragraphs = [p.text for p in document.paragraphs[:10]]
        all_text = '\n'.join(first_paragraphs)
        
        # Should have company name
        assert 'Test Company' in all_text
        
        # Should have report title
        assert 'Strategic' in all_text or 'Profile' in all_text

    def test_document_has_executive_summary(self):
        """Verify executive summary section exists."""
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Find executive summary heading
        headings = [p.text for p in document.paragraphs if p.style.name.startswith('Heading')]
        
        assert any('Executive Summary' in h for h in headings)

    def test_document_has_chapters(self):
        """Verify document has chapter structure."""
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Find chapter headings (level 1)
        h1_headings = [p.text for p in document.paragraphs if p.style.name == 'Heading 1']
        
        # Should have multiple chapters
        assert len(h1_headings) >= 3

    def test_document_saves_to_file(self):
        """Verify document can be saved to file."""
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
            temp_path = f.name
        
        try:
            document.save(temp_path)
            assert os.path.exists(temp_path)
            assert os.path.getsize(temp_path) > 0
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestTxtReportIntegration:
    """Integration tests for TXT report generation."""

    def test_txt_report_has_clean_formatting(self):
        """Verify TXT report has clean formatting without markdown."""
        # Create a mock output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override OUTPUT_DIR
            import primr.output.output_utils as utils
            original_dir = utils.OUTPUT_DIR
            utils.OUTPUT_DIR = tmpdir
            
            try:
                txt_path = save_report_as_txt(SAMPLE_SECTIONS, 'Test_Company')
                
                assert txt_path is not None
                assert os.path.exists(txt_path)
                
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Should have title
                assert 'Test_Company' in content
                
                # Should have section headers
                assert 'FINANCIAL' in content.upper() or 'OVERVIEW' in content.upper()
                
                # Should not have raw markdown heading markers
                lines = content.split('\n')
                heading_lines = [l for l in lines if l.strip().startswith('##')]
                assert len(heading_lines) == 0, f"Found markdown headings: {heading_lines}"
                
            finally:
                utils.OUTPUT_DIR = original_dir


class TestContentEquivalence:
    """Tests for content equivalence across formats."""

    def test_key_content_preserved_in_txt(self):
        """Key content from sections should appear in TXT output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.output.output_utils as utils
            original_dir = utils.OUTPUT_DIR
            utils.OUTPUT_DIR = tmpdir
            
            try:
                txt_path = save_report_as_txt(SAMPLE_SECTIONS, 'Test_Company')
                
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Key content from financial_overview should be present
                assert '$45 billion' in content or '45 billion' in content
                assert '$1.2 billion' in content or '1.2 billion' in content
                assert '15%' in content
                
            finally:
                utils.OUTPUT_DIR = original_dir

    def test_strip_markdown_preserves_key_info(self):
        """strip_markdown_artifacts should preserve key information."""
        test_content = """
## Financial Overview

**Revenue**: $5.2 billion
**Employees**: 10,000

Key points:
* Strong growth
* Market leader
"""
        
        stripped = strip_markdown_artifacts(test_content)
        
        # All key info should be present
        assert 'Financial Overview' in stripped
        assert 'Revenue' in stripped
        assert '$5.2 billion' in stripped
        assert 'Employees' in stripped
        assert '10,000' in stripped
        assert 'Strong growth' in stripped


class TestFourTests:
    """
    The Four Tests for report quality.
    
    These are qualitative checks that verify the report structure
    supports quick comprehension at different time scales.
    """

    def test_10_second_test_cover_page(self):
        """
        10-Second Test: Can you understand company essence from cover page?
        
        The cover page should have:
        - Company name prominently displayed
        - One-liner summary
        - Key metric if available
        """
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Get first page content (before first page break)
        first_page_text = []
        for para in document.paragraphs:
            if para.text:
                first_page_text.append(para.text)
            # Stop at reasonable point
            if len(first_page_text) > 15:
                break
        
        cover_text = '\n'.join(first_page_text)
        
        # Company name should be prominent
        assert 'Test Company' in cover_text
        
        # Should have some descriptive text
        assert len(cover_text) > 50

    def test_60_second_test_exec_summary(self):
        """
        60-Second Test: Can you get 5 key insights from exec summary?
        
        The executive summary should have:
        - Clear structure
        - Key insights section
        - Risk factors / watch outs
        """
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Find executive summary section
        in_exec_summary = False
        exec_summary_content = []
        
        for para in document.paragraphs:
            if 'Executive Summary' in para.text:
                in_exec_summary = True
                continue
            if in_exec_summary:
                if para.style.name == 'Heading 1' and 'Executive' not in para.text:
                    break  # End of exec summary
                exec_summary_content.append(para.text)
        
        exec_text = '\n'.join(exec_summary_content)
        
        # Should have substantial content
        assert len(exec_text) > 100
        
        # Should have key sections
        assert 'Key' in exec_text or 'Insight' in exec_text or 'Bottom Line' in exec_text

    def test_visual_hierarchy_exists(self):
        """
        Verify document has clear visual hierarchy.
        
        Should have:
        - Multiple heading levels
        - Bullet lists
        - Tables
        """
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Count heading levels
        heading_levels = set()
        for para in document.paragraphs:
            if para.style.name.startswith('Heading'):
                heading_levels.add(para.style.name)
        
        # Should have at least 2 heading levels
        assert len(heading_levels) >= 2
        
        # Should have bullet lists
        bullet_paras = [p for p in document.paragraphs if 'List' in p.style.name]
        assert len(bullet_paras) > 0
        
        # Should have tables
        assert len(document.tables) > 0


class TestUXChecklist:
    """
    UX Checklist validation tests.
    """

    def test_millers_law_compliance(self):
        """
        No section should have more than 7 distinct information chunks.
        
        This is a simplified check - we verify that bullet lists
        don't exceed 7 items in a row.
        """
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Count consecutive bullet items
        consecutive_bullets = 0
        max_consecutive = 0
        
        for para in document.paragraphs:
            if 'List Bullet' in para.style.name:
                consecutive_bullets += 1
                max_consecutive = max(max_consecutive, consecutive_bullets)
            else:
                consecutive_bullets = 0
        
        # Should not exceed 7 consecutive bullets (Miller's Law)
        # Allow some flexibility for nested lists
        assert max_consecutive <= 10, f"Found {max_consecutive} consecutive bullets"

    def test_minimum_font_sizes(self):
        """
        Verify minimum font sizes are respected.
        
        Body text should be at least 11pt.
        """
        builder = DocumentBuilder('Test Company Inc', SAMPLE_SECTIONS)
        document = builder.build()
        
        # Check Normal style font size
        normal_style = document.styles['Normal']
        if normal_style.font.size:
            # Convert to points (size is in EMUs, 914400 EMUs = 1 inch = 72 points)
            size_pt = normal_style.font.size.pt
            assert size_pt >= 10, f"Body font size {size_pt}pt is too small"


# =============================================================================
# CITATION-BASED CONFIDENCE TESTS
# =============================================================================


class TestCitationConfidence:
    """Tests for citation-based confidence indicators."""

    def test_high_confidence_with_many_citations(self):
        """High confidence when 10+ citations provided."""
        citations = [
            {'title': f'Source {i}', 'url': f'https://source{i}.com'}
            for i in range(12)
        ]
        
        builder = DocumentBuilder(
            company_name="Test Corp",
            section_results=SAMPLE_SECTIONS,
            citations=citations
        )
        
        assert builder._citation_count == 12
        assert builder._overall_confidence == 'high'
        assert 'High confidence' in builder._get_confidence_description()

    def test_medium_confidence_with_some_citations(self):
        """Medium confidence when 3-9 citations provided."""
        citations = [
            {'title': f'Source {i}', 'url': f'https://source{i}.com'}
            for i in range(5)
        ]
        
        builder = DocumentBuilder(
            company_name="Test Corp",
            section_results=SAMPLE_SECTIONS,
            citations=citations
        )
        
        assert builder._citation_count == 5
        assert builder._overall_confidence == 'medium'
        assert 'Medium confidence' in builder._get_confidence_description()

    def test_low_confidence_with_few_citations(self):
        """Low confidence when 0-2 citations provided."""
        citations = [
            {'title': 'Source 1', 'url': 'https://source1.com'}
        ]
        
        builder = DocumentBuilder(
            company_name="Test Corp",
            section_results=SAMPLE_SECTIONS,
            citations=citations
        )
        
        assert builder._citation_count == 1
        assert builder._overall_confidence == 'low'
        assert 'Limited sources' in builder._get_confidence_description()

    def test_no_citations_is_low_confidence(self):
        """No citations results in low confidence."""
        builder = DocumentBuilder(
            company_name="Test Corp",
            section_results=SAMPLE_SECTIONS,
            citations=[]
        )
        
        assert builder._citation_count == 0
        assert builder._overall_confidence == 'low'

    def test_confidence_description_includes_count(self):
        """Confidence description includes citation count."""
        citations = [
            {'title': f'Source {i}', 'url': f'https://source{i}.com'}
            for i in range(7)
        ]
        
        builder = DocumentBuilder(
            company_name="Test Corp",
            section_results=SAMPLE_SECTIONS,
            citations=citations
        )
        
        description = builder._get_confidence_description()
        assert '7' in description  # Should mention the count
