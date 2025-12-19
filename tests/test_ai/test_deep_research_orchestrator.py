"""
Tests for DeepResearchOrchestrator - the production Accordion Method implementation.

This tests the ACTUAL production code in deep_research.py, not test harnesses.

Key components tested:
- Section loading from YAML
- Report assembly with metadata extraction
- Industry/Company Name extraction from Stage 1 context
- Section prompt building
- Retry logic for API errors
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from primr.ai.deep_research import (
    DeepResearchOrchestrator,
    get_deep_research_orchestrator,
    DeepResearchOrchestratorResult,
)


class TestDeepResearchOrchestratorInit:
    """Tests for DeepResearchOrchestrator initialization."""

    def test_orchestrator_has_correct_models(self):
        """Verify correct model IDs are configured."""
        assert DeepResearchOrchestrator.AGENT_ID == "deep-research-pro-preview-12-2025"
        assert DeepResearchOrchestrator.SECTION_MODEL == "gemini-3-flash-preview"

    def test_orchestrator_has_retry_config(self):
        """Verify retry configuration exists."""
        assert DeepResearchOrchestrator.MAX_RETRIES >= 3
        assert DeepResearchOrchestrator.BASE_RETRY_DELAY >= 30


class TestSectionLoadingFromYAML:
    """Tests for loading sections from company_overview.yaml."""

    def test_loads_sections_from_yaml(self):
        """Sections are loaded from YAML, not hardcoded."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        sections = orchestrator._load_sections_from_yaml()
        
        # Should have 20 sections per company_overview.yaml
        assert len(sections) >= 15, f"Expected 15+ sections, got {len(sections)}"
        
        # Each section should have required fields
        for section in sections:
            assert "id" in section, f"Section missing 'id': {section}"
            assert "title" in section, f"Section missing 'title': {section}"

    def test_sections_have_position_field(self):
        """All sections have position field for narrative flow."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        sections = orchestrator._load_sections_from_yaml()
        
        for section in sections:
            assert "position" in section, f"Section missing 'position': {section.get('id')}"
            assert section["position"] in ("opening", "middle", "closing")

    def test_first_section_is_executive_summary(self):
        """First section should be Executive Summary."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        sections = orchestrator._load_sections_from_yaml()
        
        assert sections[0]["id"] == "executive_summary"
        assert sections[0]["position"] == "opening"


class TestIndustryExtraction:
    """Tests for extracting Industry from Stage 1 context."""

    def test_extracts_industry_from_context(self):
        """Extract Industry from Stage 1 markdown context."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        context = """
## Company Name

Bank of Hawaii Corporation

---

## Industry

Regional Banking and Financial Services

---

## Products Services

Banking products...
"""
        
        industry = orchestrator._extract_industry_from_context(context)
        
        assert industry == "Regional Banking and Financial Services"

    def test_extracts_industry_case_insensitive(self):
        """Industry extraction is case-insensitive."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        context = """
## INDUSTRY

Technology Services

---
"""
        
        industry = orchestrator._extract_industry_from_context(context)
        
        assert industry == "Technology Services"

    def test_returns_none_for_missing_industry(self):
        """Returns None if Industry section not found."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        context = """
## Company Name

Test Company

## Products

Some products
"""
        
        industry = orchestrator._extract_industry_from_context(context)
        
        assert industry is None

    def test_returns_none_for_empty_context(self):
        """Returns None for empty or None context."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        assert orchestrator._extract_industry_from_context(None) is None
        assert orchestrator._extract_industry_from_context("") is None


class TestCompanyNameExtraction:
    """Tests for extracting full company name from Stage 1 context."""

    def test_extracts_full_company_name(self):
        """Extract full legal name from Stage 1 context."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        context = """
## Company Name

Bank of Hawaii Corporation

---

## Industry

Banking
"""
        
        full_name = orchestrator._extract_full_company_name(context)
        
        assert full_name == "Bank of Hawaii Corporation"

    def test_returns_none_for_missing_company_name(self):
        """Returns None if Company Name section not found."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        context = """
## Industry

Banking

## Products

Some products
"""
        
        full_name = orchestrator._extract_full_company_name(context)
        
        assert full_name is None


class TestReportAssembly:
    """Tests for _assemble_report method."""

    def test_assembles_report_with_header(self):
        """Report has clean header with metadata."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        sections = [
            {"id": "exec_summary", "title": "Executive Summary", "content": "Summary content."},
            {"id": "products", "title": "Products", "content": "Product content."},
        ]
        
        report = orchestrator._assemble_report(
            company_name="Bank of Hawaii",
            website_url="https://www.boh.com",
            sections=sections,
            industry="Regional Banking",
            full_company_name="Bank of Hawaii Corporation",
        )
        
        # Check header elements
        assert "# Strategic Company Overview: Bank of Hawaii" in report
        assert "**Company Name:** Bank of Hawaii Corporation" in report
        assert "**Website:** https://www.boh.com" in report
        assert "**Industry:** Regional Banking" in report
        
        # Check date is in italics
        current_month = datetime.now().strftime("%B %Y")
        assert f"*{current_month}*" in report

    def test_assembles_report_without_optional_fields(self):
        """Report works without Industry or full company name."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        sections = [
            {"id": "exec_summary", "title": "Executive Summary", "content": "Summary."},
        ]
        
        report = orchestrator._assemble_report(
            company_name="Test Co",
            website_url=None,
            sections=sections,
            industry=None,
            full_company_name=None,
        )
        
        assert "# Strategic Company Overview: Test Co" in report
        assert "**Company Name:** Test Co" in report  # Falls back to user input
        assert "**Website:**" not in report
        assert "**Industry:**" not in report

    def test_assembles_sections_in_order(self):
        """Sections appear in the order provided."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        sections = [
            {"id": "first", "title": "First Section", "content": "First content."},
            {"id": "second", "title": "Second Section", "content": "Second content."},
            {"id": "third", "title": "Third Section", "content": "Third content."},
        ]
        
        report = orchestrator._assemble_report(
            company_name="Test",
            website_url=None,
            sections=sections,
        )
        
        # Check order
        first_pos = report.find("## First Section")
        second_pos = report.find("## Second Section")
        third_pos = report.find("## Third Section")
        
        assert first_pos < second_pos < third_pos

    def test_no_table_of_contents(self):
        """Report should NOT have table of contents (cleaner format)."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        sections = [
            {"id": "exec", "title": "Executive Summary", "content": "Content."},
        ]
        
        report = orchestrator._assemble_report(
            company_name="Test",
            website_url=None,
            sections=sections,
        )
        
        assert "Table of Contents" not in report
        assert "## Contents" not in report


class TestSectionPromptBuilding:
    """Tests for building section prompts."""

    def test_section_prompt_includes_dossier(self):
        """Section prompt includes research dossier."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        # Mock the YAML loading
        with patch.object(orchestrator, '_load_accordion_prompts') as mock_load:
            mock_load.return_value = {
                "section_writing_prompt": "Write {section_title} for {company_name}. Dossier: {research_dossier}",
                "position_guidance": {"middle": "Middle section guidance."}
            }
            
            section = {"id": "test", "title": "Test Section", "instructions": "Write test.", "position": "middle"}
            
            prompt = orchestrator._build_section_prompt(
                section=section,
                company_name="Test Co",
                research_dossier="This is the dossier content.",
                previous_sections=[],
                stage1_context=None,
                section_index=0,
                total_sections=5,
            )
            
            assert "dossier" in prompt.lower() or "This is the dossier content" in prompt

    def test_section_prompt_includes_previous_sections(self):
        """Section prompt includes context from previous sections."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        with patch.object(orchestrator, '_load_accordion_prompts') as mock_load:
            mock_load.return_value = {
                "section_writing_prompt": "{previous_sections}",
                "position_guidance": {"middle": ""}
            }
            
            section = {"id": "test", "title": "Test", "instructions": "", "position": "middle"}
            previous = [
                {"id": "prev1", "title": "Previous One", "content": "Previous content here."}
            ]
            
            prompt = orchestrator._build_section_prompt(
                section=section,
                company_name="Test",
                research_dossier="",
                previous_sections=previous,
                stage1_context=None,
                section_index=1,
                total_sections=5,
            )
            
            assert "Previous One" in prompt or "Previous content" in prompt


class TestRetryLogic:
    """Tests for retry logic on API errors."""

    def test_calculates_exponential_backoff(self):
        """Backoff delay increases exponentially."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator.BASE_RETRY_DELAY = 60.0
        
        delay_0 = orchestrator._calculate_backoff_delay(0)
        delay_1 = orchestrator._calculate_backoff_delay(1)
        delay_2 = orchestrator._calculate_backoff_delay(2)
        
        assert delay_0 == 60.0  # 60 * 2^0
        assert delay_1 == 120.0  # 60 * 2^1
        assert delay_2 == 240.0  # 60 * 2^2


class TestDeepResearchOrchestratorResult:
    """Tests for the result dataclass."""

    def test_result_success(self):
        """Successful result has content."""
        result = DeepResearchOrchestratorResult(
            company_name="Test",
            content="Report content here.",
            citations=[],
            duration_seconds=100.0,
            success=True,
        )
        
        assert result.success is True
        assert result.content == "Report content here."
        assert result.error is None

    def test_result_failure(self):
        """Failed result has error message."""
        result = DeepResearchOrchestratorResult(
            company_name="Test",
            content="",
            citations=[],
            duration_seconds=50.0,
            success=False,
            error="API quota exhausted",
        )
        
        assert result.success is False
        assert result.error == "API quota exhausted"


class TestAccordionPromptLoading:
    """Tests for loading accordion prompts from YAML."""

    def test_loads_accordion_prompts_from_yaml(self):
        """Accordion prompts are loaded from company_overview.yaml."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        prompts = orchestrator._load_accordion_prompts()
        
        assert "research_dossier_prompt" in prompts
        assert "section_writing_prompt" in prompts
        assert "position_guidance" in prompts
        
        # Position guidance should have opening/middle/closing
        assert "opening" in prompts["position_guidance"]
        assert "middle" in prompts["position_guidance"]
        assert "closing" in prompts["position_guidance"]

    def test_research_dossier_prompt_has_placeholders(self):
        """Research dossier prompt has required placeholders."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        orchestrator._settings = Mock()
        orchestrator._settings.api.gemini_key = "test-key"
        
        prompts = orchestrator._load_accordion_prompts()
        dossier_prompt = prompts["research_dossier_prompt"]
        
        assert "{company_name}" in dossier_prompt


class TestFallbackBehavior:
    """Tests for fallback when Deep Research fails."""

    def test_extract_industry_uses_stage1_on_failure(self):
        """When Deep Research fails, Industry is still extracted from Stage 1."""
        orchestrator = DeepResearchOrchestrator.__new__(DeepResearchOrchestrator)
        
        stage1_context = """
## Industry

Regional Banking

---

## Company Name

Test Bank Corp
"""
        
        # Even if Deep Research fails, we can still extract metadata
        industry = orchestrator._extract_industry_from_context(stage1_context)
        full_name = orchestrator._extract_full_company_name(stage1_context)
        
        assert industry == "Regional Banking"
        assert full_name == "Test Bank Corp"
