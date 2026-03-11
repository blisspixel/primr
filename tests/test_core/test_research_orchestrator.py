"""
Tests for the Research Orchestrator.

These tests verify the orchestrator correctly manages
both research engines.
"""

from datetime import datetime
from unittest.mock import Mock, patch

from primr.core.research_orchestrator import (
    OrchestratorResult,
    ResearchConfig,
    ResearchMode,
    ResearchOrchestrator,
    get_orchestrator,
    reset_orchestrator,
)


class TestResearchMode:
    """Tests for ResearchMode enum."""

    def test_mode_values(self):
        """Verify all mode values exist."""
        assert ResearchMode.STRUCTURED.value == "structured"
        assert ResearchMode.DEEP_RESEARCH.value == "deep-research"
        assert ResearchMode.HYBRID.value == "hybrid"


class TestResearchConfig:
    """Tests for ResearchConfig dataclass."""

    def test_default_config(self):
        """Default config uses structured mode."""
        config = ResearchConfig()

        assert config.mode == ResearchMode.STRUCTURED
        assert config.timeout == 3600
        assert config.poll_interval == 10
        assert config.include_website_scrape is True
        assert config.include_web_search is True

    def test_custom_config(self):
        """Create config with custom values."""
        config = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH, timeout=1800, poll_interval=5)

        assert config.mode == ResearchMode.DEEP_RESEARCH
        assert config.timeout == 1800
        assert config.poll_interval == 5


class TestOrchestratorResult:
    """Tests for OrchestratorResult dataclass."""

    def test_successful_result(self):
        """Create successful result."""
        result = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.STRUCTURED,
            section_results={"company_overview": "Content"},
            success=True,
        )

        assert result.success is True
        assert result.company_name == "Acme Corp"
        assert "company_overview" in result.section_results

    def test_failed_result(self):
        """Create failed result with error."""
        result = OrchestratorResult(
            company_name="Acme Corp",
            website=None,
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={},
            success=False,
            error="API timeout",
        )

        assert result.success is False
        assert result.error == "API timeout"

    def test_result_has_timestamp(self):
        """Result includes timestamp."""
        result = OrchestratorResult(
            company_name="Test", website=None, mode=ResearchMode.STRUCTURED, section_results={}
        )

        assert isinstance(result.timestamp, datetime)

    def test_result_tracks_search_queries(self):
        """Result tracks actual search query count."""
        result = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={"strategic_overview": "Content"},
            success=True,
            search_queries_count=22,  # Actual count from API
        )

        assert result.search_queries_count == 22


class TestResearchOrchestrator:
    """Tests for ResearchOrchestrator class."""

    def test_orchestrator_initialization(self):
        """Orchestrator initializes correctly."""
        orchestrator = ResearchOrchestrator()
        assert orchestrator._deep_research_client is None

    def test_lazy_load_deep_research_client(self):
        """Deep research client is lazy loaded."""
        with patch("primr.core.research_orchestrator.DeepResearchClient") as mock_client:
            orchestrator = ResearchOrchestrator()

            # Not loaded yet
            assert orchestrator._deep_research_client is None

            # Access triggers load
            _ = orchestrator.deep_research_client
            mock_client.assert_called_once()


class TestHeaderMapping:
    """Tests for header to section mapping."""

    def test_map_executive_summary(self):
        """Map executive summary header."""
        orchestrator = ResearchOrchestrator()

        result = orchestrator._map_header_to_section("executive summary")
        assert result == "company_overview"

    def test_map_products_services(self):
        """Map products & services header."""
        orchestrator = ResearchOrchestrator()

        result = orchestrator._map_header_to_section("products & services")
        assert result == "detailed_products_services"

    def test_map_financial(self):
        """Map financial headers."""
        orchestrator = ResearchOrchestrator()

        assert orchestrator._map_header_to_section("financial analysis") == "financial_overview"
        # "financials" maps via partial match
        result = orchestrator._map_header_to_section("financials")
        assert result == "financial_overview" or "financial" in result

    def test_map_competitive(self):
        """Map competitive headers."""
        orchestrator = ResearchOrchestrator()

        assert (
            orchestrator._map_header_to_section("competitive landscape") == "competitive_position"
        )
        assert orchestrator._map_header_to_section("competition") == "competitive_position"

    def test_map_unknown_header(self):
        """Unknown headers generate key from text."""
        orchestrator = ResearchOrchestrator()

        result = orchestrator._map_header_to_section("Custom Section Name")
        assert result == "custom_section_name"


class TestNormalizeDeepResearchResult:
    """Tests for normalizing Deep Research output."""

    def test_normalize_simple_content(self):
        """Normalize content with clear sections."""
        orchestrator = ResearchOrchestrator()

        mock_result = Mock()
        mock_result.content = """
## Executive Summary

This is the summary.

## Products & Services

Product details here.
"""
        mock_result.citations = []

        sections = orchestrator._normalize_deep_research_result(mock_result)

        assert "company_overview" in sections
        assert "detailed_products_services" in sections

    def test_normalize_no_sections(self):
        """Content without sections goes to overview."""
        orchestrator = ResearchOrchestrator()

        mock_result = Mock()
        mock_result.content = "Just plain text without headers."
        mock_result.citations = []

        sections = orchestrator._normalize_deep_research_result(mock_result)

        assert "company_overview" in sections
        assert "plain text" in sections["company_overview"]

    def test_normalize_empty_content(self):
        """Empty content returns overview with empty string."""
        orchestrator = ResearchOrchestrator()

        mock_result = Mock()
        mock_result.content = ""
        mock_result.citations = []

        sections = orchestrator._normalize_deep_research_result(mock_result)

        assert "company_overview" in sections


class TestSingletonAccess:
    """Tests for singleton pattern."""

    def test_get_orchestrator_returns_same_instance(self):
        """get_orchestrator returns same instance."""
        reset_orchestrator()

        orch1 = get_orchestrator()
        orch2 = get_orchestrator()

        assert orch1 is orch2

        reset_orchestrator()

    def test_reset_orchestrator(self):
        """reset_orchestrator clears instance."""
        orch1 = get_orchestrator()
        reset_orchestrator()
        orch2 = get_orchestrator()

        assert orch1 is not orch2

        reset_orchestrator()


class TestModeSelection:
    """Tests for research mode selection."""

    def test_default_mode_is_structured(self):
        """Default mode is structured."""
        config = ResearchConfig()
        assert config.mode == ResearchMode.STRUCTURED

    def test_mode_from_string(self):
        """Mode can be set from enum."""
        config = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)
        assert config.mode == ResearchMode.DEEP_RESEARCH


class TestCompleteMode:
    """Tests for the COMPLETE (two-step sequential) research mode."""

    def test_complete_mode_exists(self):
        """Verify COMPLETE mode is defined."""
        assert ResearchMode.COMPLETE.value == "complete"

    def test_complete_mode_in_config(self):
        """Config accepts COMPLETE mode."""
        config = ResearchConfig(mode=ResearchMode.COMPLETE)
        assert config.mode == ResearchMode.COMPLETE

    def test_prepare_step1_context_creates_file(self):
        """_prepare_step1_context creates a markdown file."""
        import os
        import time

        orchestrator = ResearchOrchestrator()

        section_results = {
            "company_overview": "Test company overview content",
            "products_services": "Test products content",
        }

        filepath = orchestrator._prepare_step1_context("TestCo", section_results)

        try:
            assert os.path.exists(filepath)
            assert filepath.endswith(".txt")  # Changed from .md for MIME type compatibility

            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            assert "TestCo" in content
            assert "Test company overview content" in content
            assert "Test products content" in content
        finally:
            # Cleanup with retry for Windows file locking
            for _ in range(3):
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def test_prepare_step1_context_includes_all_sections(self):
        """_prepare_step1_context includes all section content."""
        import os
        import time

        orchestrator = ResearchOrchestrator()

        section_results = {
            "section_a": "Content A",
            "section_b": "Content B",
            "section_c": "Content C",
        }

        filepath = orchestrator._prepare_step1_context("TestCo", section_results)

        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()

            assert "Content A" in content
            assert "Content B" in content
            assert "Content C" in content
        finally:
            # Cleanup with retry for Windows file locking
            for _ in range(3):
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    break
                except PermissionError:
                    time.sleep(0.1)

    def test_merge_research_results_step1_priority(self):
        """Step 1 sections take priority for factual data."""
        orchestrator = ResearchOrchestrator()

        step1 = {
            "company_overview": "Step 1 overview (ground truth)",
            "detailed_products_services": "Step 1 products",
        }
        step2 = {
            "company_overview": "Step 2 overview (should be ignored)",
            "competitive_position": "Step 2 competitive analysis",
        }

        merged = orchestrator._merge_research_results(step1, step2)

        # Step 1 priority sections should use Step 1 content
        assert merged["company_overview"] == "Step 1 overview (ground truth)"
        assert merged["detailed_products_services"] == "Step 1 products"

        # Step 2 priority sections should use Step 2 content
        assert merged["competitive_position"] == "Step 2 competitive analysis"

    def test_merge_research_results_step2_priority(self):
        """Step 2 sections take priority for strategic analysis."""
        orchestrator = ResearchOrchestrator()

        step1 = {
            "competitive_position": "Step 1 basic competitors",
            "strategic_recommendations": "Step 1 basic recs",
        }
        step2 = {
            "competitive_position": "Step 2 deep competitive analysis",
            "strategic_recommendations": "Step 2 strategic recs",
        }

        merged = orchestrator._merge_research_results(step1, step2)

        # Step 2 priority sections should use Step 2 content
        assert merged["competitive_position"] == "Step 2 deep competitive analysis"
        assert merged["strategic_recommendations"] == "Step 2 strategic recs"

    def test_merge_research_results_combines_unique_sections(self):
        """Merge includes unique sections from both steps."""
        orchestrator = ResearchOrchestrator()

        step1 = {"company_overview": "Overview", "unique_step1_section": "Only in step 1"}
        step2 = {"competitive_position": "Competition", "unique_step2_section": "Only in step 2"}

        merged = orchestrator._merge_research_results(step1, step2)

        assert "unique_step1_section" in merged
        assert "unique_step2_section" in merged
        assert merged["unique_step1_section"] == "Only in step 1"
        assert merged["unique_step2_section"] == "Only in step 2"

    def test_merge_research_results_empty_step1(self):
        """Merge handles empty Step 1 results."""
        orchestrator = ResearchOrchestrator()

        step1 = {}
        step2 = {
            "company_overview": "Step 2 overview",
            "competitive_position": "Step 2 competition",
        }

        merged = orchestrator._merge_research_results(step1, step2)

        assert merged["company_overview"] == "Step 2 overview"
        assert merged["competitive_position"] == "Step 2 competition"

    def test_merge_research_results_empty_step2(self):
        """Merge handles empty Step 2 results."""
        orchestrator = ResearchOrchestrator()

        step1 = {
            "company_overview": "Step 1 overview",
            "detailed_products_services": "Step 1 products",
        }
        step2 = {}

        merged = orchestrator._merge_research_results(step1, step2)

        assert merged["company_overview"] == "Step 1 overview"
        assert merged["detailed_products_services"] == "Step 1 products"


class TestStrategicLayerPrompt:
    """Tests for the strategic layer prompt used in Step 2."""

    def test_strategic_layer_prompt_exists(self):
        """Verify strategic_layer output format is supported."""
        from primr.ai.deep_research import DeepResearchClient

        client = DeepResearchClient.__new__(DeepResearchClient)
        client._api_key = "test"

        prompt = client._build_prompt("Research TestCo", output_format="strategic_layer")

        assert "strategic analysis" in prompt.lower() or "strategic" in prompt.lower()

    def test_strategic_layer_prompt_has_gap_analysis(self):
        """Strategic layer prompt includes gap analysis instructions."""
        from primr.ai.deep_research import DeepResearchClient

        client = DeepResearchClient.__new__(DeepResearchClient)
        client._api_key = "test"

        prompt = client._build_prompt("Research TestCo", output_format="strategic_layer")

        assert "gap" in prompt.lower()

    def test_strategic_layer_prompt_avoids_repetition(self):
        """Strategic layer prompt instructs to avoid repeating facts."""
        from primr.ai.deep_research import DeepResearchClient

        client = DeepResearchClient.__new__(DeepResearchClient)
        client._api_key = "test"

        prompt = client._build_prompt("Research TestCo", output_format="strategic_layer")

        assert "repeat" in prompt.lower() or "do not" in prompt.lower()
