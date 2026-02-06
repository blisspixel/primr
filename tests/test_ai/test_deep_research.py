"""
Tests for the Deep Research client.

These tests use mocks to avoid actual API calls.
Real API integration tests should be run separately.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from primr.ai.deep_research import (
    DeepResearchClient,
    ResearchStatus,
    ResearchProgress,
    ResearchResult,
    get_deep_research_client,
    reset_deep_research_client,
)
from primr.utils.errors import AIError


class TestResearchStatus:
    """Tests for ResearchStatus enum."""

    def test_status_values(self):
        """Verify all status values exist."""
        assert ResearchStatus.PENDING.value == "pending"
        assert ResearchStatus.IN_PROGRESS.value == "in_progress"
        assert ResearchStatus.COMPLETED.value == "completed"
        assert ResearchStatus.FAILED.value == "failed"


class TestResearchProgress:
    """Tests for ResearchProgress dataclass."""

    def test_progress_creation(self):
        """Create progress with required fields."""
        progress = ResearchProgress(
            status=ResearchStatus.IN_PROGRESS,
            message="Processing..."
        )
        
        assert progress.status == ResearchStatus.IN_PROGRESS
        assert progress.message == "Processing..."
        assert progress.thought is None
        assert progress.partial_result is None
        assert isinstance(progress.timestamp, datetime)

    def test_progress_with_thought(self):
        """Create progress with thought summary."""
        progress = ResearchProgress(
            status=ResearchStatus.IN_PROGRESS,
            thought="Analyzing competitive landscape..."
        )
        
        assert progress.thought == "Analyzing competitive landscape..."


class TestResearchResult:
    """Tests for ResearchResult dataclass."""

    def test_result_success(self):
        """Successful result has content."""
        result = ResearchResult(
            content="Research findings...",
            interaction_id="test-123",
            duration_seconds=120.5,
            status=ResearchStatus.COMPLETED
        )
        
        assert result.success is True
        assert result.content == "Research findings..."
        assert result.error is None

    def test_result_failure(self):
        """Failed result has error."""
        result = ResearchResult(
            content="",
            interaction_id="test-456",
            status=ResearchStatus.FAILED,
            error="API error"
        )
        
        assert result.success is False
        assert result.error == "API error"

    def test_result_with_citations(self):
        """Result can include citations."""
        result = ResearchResult(
            content="Content",
            citations=[
                {"text": "Source 1", "url": "https://example.com"}
            ]
        )
        
        assert len(result.citations) == 1

    def test_result_with_search_queries_count(self):
        """Result tracks actual search query count from API."""
        result = ResearchResult(
            content="Research findings...",
            interaction_id="test-789",
            duration_seconds=300.0,
            status=ResearchStatus.COMPLETED,
            search_queries_count=15,  # Actual count from groundingMetadata
        )
        
        assert result.success is True
        assert result.search_queries_count == 15


class TestDeepResearchClient:
    """Tests for DeepResearchClient class."""

    @patch.object(DeepResearchClient, '__init__', lambda self, api_key=None: None)
    def test_agent_id(self):
        """Verify agent ID constant."""
        assert DeepResearchClient.AGENT_ID == "deep-research-pro-preview-12-2025"

    def test_build_prompt_default(self):
        """Build prompt without format returns query."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_prompt("Research Acme Corp", None)
        assert prompt == "Research Acme Corp"

    def test_build_prompt_company_profile(self):
        """Build prompt with company_profile format extracts company name."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_prompt("Research Acme Corp", "company_profile")

        # The company_profile format extracts company name from query
        # and builds a structured prompt from YAML configuration
        assert "Acme Corp" in prompt
        # Check for key sections from the YAML-based prompt
        assert "Executive Summary" in prompt or "strategy consultant" in prompt
        assert "Products" in prompt or "services" in prompt.lower()
        assert "Financial" in prompt or "financial" in prompt.lower()
        assert "Competitive" in prompt or "competitive" in prompt.lower()

    def test_build_prompt_executive_summary(self):
        """Build prompt with executive_summary format."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_prompt("Research Acme Corp", "executive_summary")

        assert "Research Acme Corp" in prompt
        assert "Key Findings" in prompt
        assert "Recommendations" in prompt

    def test_build_prompt_competitive_analysis(self):
        """Build prompt with competitive_analysis format."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_prompt("Research Acme Corp", "competitive_analysis")

        assert "Research Acme Corp" in prompt
        assert "Market Overview" in prompt
        assert "Key Players" in prompt


class TestSingletonAccess:
    """Tests for singleton pattern."""

    def test_reset_clears_global(self):
        """reset_deep_research_client clears the global."""
        # Just test the reset function works without error
        reset_deep_research_client()
        # The function should complete without raising
        assert True


class TestPromptFormats:
    """Tests for different prompt format outputs."""

    def test_company_profile_has_all_sections(self):
        """Company profile prompt includes all required sections."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_company_profile_prompt("Research Acme Corp")
        
        required_sections = [
            "Executive Summary",
            "Products and Services",
            "Competitive Differentiation",
            "Company History",
            "Financial Profile",
            "SWOT Analysis",
            "Competitive Landscape",
            "Discovery Questions",
        ]
        
        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"

    def test_prompt_includes_citation_instruction(self):
        """Prompts include instruction to cite sources."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        
        for format_type in ["company_profile", "executive_summary", "competitive_analysis"]:
            prompt = client._build_prompt("Research test", format_type)
            assert "cite" in prompt.lower() or "source" in prompt.lower()


class TestExtractContent:
    """Tests for content extraction from interactions."""

    def test_extract_content_from_outputs(self):
        """Extract text from interaction outputs."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        
        # Mock interaction with outputs
        mock_interaction = Mock()
        mock_output = Mock()
        mock_output.text = "Research findings here"
        mock_interaction.outputs = [mock_output]
        
        content = client._extract_content(mock_interaction)
        assert content == "Research findings here"

    def test_extract_content_empty_outputs(self):
        """Handle interaction with no outputs."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        
        mock_interaction = Mock()
        mock_interaction.outputs = []
        
        content = client._extract_content(mock_interaction)
        assert content == ""

    def test_extract_content_no_outputs_attr(self):
        """Handle interaction without outputs attribute."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        
        mock_interaction = Mock(spec=[])  # No outputs attribute
        
        content = client._extract_content(mock_interaction)
        assert content == ""


# =============================================================================
# THINKING LOG TESTS
# =============================================================================

from primr.ai.deep_research import ThinkingLog


class TestThinkingLog:
    """Tests for ThinkingLog dataclass."""

    def test_thinking_log_creation(self):
        """Create thinking log with required fields."""
        log = ThinkingLog(
            interaction_id="test-123",
            company_name="Acme Corp"
        )
        
        assert log.interaction_id == "test-123"
        assert log.company_name == "Acme Corp"
        assert log.thoughts == []
        assert log.search_queries == []
        assert log.sources_visited == []

    def test_add_thought(self):
        """Add thoughts to the log."""
        log = ThinkingLog(
            interaction_id="test-123",
            company_name="Acme Corp"
        )
        
        log.add_thought("Analyzing company website")
        log.add_thought("Searching for financial data")
        
        assert len(log.thoughts) == 2
        assert "Analyzing company website" in log.thoughts[0]
        assert "Searching for financial data" in log.thoughts[1]

    def test_add_search(self):
        """Add search queries to the log."""
        log = ThinkingLog(
            interaction_id="test-123",
            company_name="Acme Corp"
        )
        
        log.add_search("Acme Corp revenue 2024")
        log.add_search("Acme Corp competitors")
        
        assert len(log.search_queries) == 2
        assert "Acme Corp revenue 2024" in log.search_queries

    def test_add_source_deduplicates(self):
        """Adding same source twice only stores once."""
        log = ThinkingLog(
            interaction_id="test-123",
            company_name="Acme Corp"
        )
        
        log.add_source("https://acme.com")
        log.add_source("https://acme.com")
        log.add_source("https://other.com")
        
        assert len(log.sources_visited) == 2

    def test_to_markdown(self):
        """Export thinking log as markdown."""
        log = ThinkingLog(
            interaction_id="test-123",
            company_name="Acme Corp"
        )
        
        log.add_thought("Starting research")
        log.add_search("Acme Corp overview")
        log.add_source("https://acme.com")
        
        markdown = log.to_markdown()
        
        assert "# Deep Research Thinking Log" in markdown
        assert "Acme Corp" in markdown
        assert "test-123" in markdown
        assert "Starting research" in markdown
        assert "Acme Corp overview" in markdown
        assert "https://acme.com" in markdown


class TestCulturePrompt:
    """Tests for culture/leadership section in prompts."""

    def test_company_profile_has_culture_section(self):
        """Company profile prompt includes culture analysis."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_company_profile_prompt("Research Acme Corp")
        
        assert "Culture" in prompt or "Leadership" in prompt
        # Should NOT reference Glassdoor/Reddit (unreliable)
        assert "Glassdoor" not in prompt
        assert "Reddit" not in prompt

    def test_culture_focuses_on_official_sources(self):
        """Culture analysis focuses on official/observable sources."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_company_profile_prompt("Research Acme Corp")
        
        # Should reference official sources
        official_signals = [
            "website",
            "press release",
            "leadership",
            "careers",
        ]
        
        prompt_lower = prompt.lower()
        found_any = any(signal in prompt_lower for signal in official_signals)
        assert found_any, "Should reference official sources for culture analysis"

    def test_patterns_and_questions_section(self):
        """Prompt includes patterns section for exploring observations."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        prompt = client._build_company_profile_prompt("Research Acme Corp")
        
        assert "Patterns Worth Exploring" in prompt
        assert "question" in prompt.lower()


# =============================================================================
# FILE SEARCH TESTS
# =============================================================================


class TestFileSearch:
    """Tests for File Search (context file upload) functionality."""

    def test_upload_context_files_with_no_files(self):
        """Upload with empty list raises AIError (fail fast)."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        client._client = Mock()
        client.AGENT_ID = "deep-research-pro-preview-12-2025"
        
        with pytest.raises(AIError, match="No valid context files"):
            client._upload_context_files([])

    def test_upload_context_files_with_nonexistent_files(self):
        """Upload with nonexistent files raises AIError (fail fast)."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        client._client = Mock()
        client.AGENT_ID = "deep-research-pro-preview-12-2025"
        
        with pytest.raises(AIError, match="Context files not found"):
            client._upload_context_files([
                "/nonexistent/path/file1.pdf",
                "/nonexistent/path/file2.pdf"
            ])

    @patch('os.path.exists')
    def test_upload_context_files_creates_store(self, mock_exists):
        """Upload creates file search store and uploads files."""
        mock_exists.return_value = True
        
        client = DeepResearchClient.__new__(DeepResearchClient)
        mock_client = Mock()
        mock_store = Mock()
        mock_store.name = "test-store-123"
        mock_client.file_search_stores.create.return_value = mock_store
        client._client = mock_client
        
        result = client._upload_context_files(["/path/to/file.pdf"])
        
        assert result == "test-store-123"
        mock_client.file_search_stores.create.assert_called_once()
        mock_client.file_search_stores.upload_to_file_search_store.assert_called_once()

    @patch('os.path.exists')
    def test_upload_context_files_handles_error(self, mock_exists):
        """Upload raises AIError on API errors (fail fast)."""
        mock_exists.return_value = True
        
        client = DeepResearchClient.__new__(DeepResearchClient)
        client.AGENT_ID = "deep-research-pro-preview-12-2025"
        mock_client = Mock()
        mock_client.file_search_stores.create.side_effect = Exception("API Error")
        client._client = mock_client
        
        with pytest.raises(AIError, match="Failed to create file store"):
            client._upload_context_files(["/path/to/file.pdf"])

    def test_start_research_without_file_store(self):
        """Start research without file store uses default config."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        mock_client = Mock()
        mock_interaction = Mock()
        mock_interaction.id = "interaction-123"
        mock_client.interactions.create.return_value = mock_interaction
        client._client = mock_client
        
        result = client._start_research("Research query")
        
        # Should not include tools parameter
        call_kwargs = mock_client.interactions.create.call_args[1]
        assert "tools" not in call_kwargs or not call_kwargs.get("tools")

    def test_start_research_with_file_store(self):
        """Start research with file store includes file_search tool."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        mock_client = Mock()
        mock_interaction = Mock()
        mock_interaction.id = "interaction-123"
        mock_client.interactions.create.return_value = mock_interaction
        client._client = mock_client
        
        result = client._start_research("Research query", file_store_name="store-123")
        
        # Should include tools parameter with file_search
        call_kwargs = mock_client.interactions.create.call_args[1]
        assert "tools" in call_kwargs
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["type"] == "file_search"
        assert "store-123" in call_kwargs["tools"][0]["file_search_store_names"]


class TestResearchWithContextFiles:
    """Tests for research method with context files parameter.
    
    Note: The research method now does strict pre-flight validation.
    Context files must exist and be readable BEFORE any API calls.
    This is intentional "fail fast" behavior to avoid wasting money.
    """

    @pytest.mark.asyncio
    async def test_research_fails_fast_on_missing_context_files(self):
        """Research raises AIError if context files don't exist (fail fast)."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        client._api_key = "test-key"
        client._client = Mock()
        client.AGENT_ID = "deep-research-pro-preview-12-2025"
        
        with pytest.raises(AIError, match="Context file not found"):
            await client.research(
                "Research Acme Corp",
                context_files=["/path/to/internal_doc.pdf"]
            )

    @pytest.mark.asyncio
    async def test_research_fails_fast_on_nonexistent_files(self):
        """Research raises AIError for nonexistent files (fail fast)."""
        client = DeepResearchClient.__new__(DeepResearchClient)
        client._api_key = "test-key"
        client._client = Mock()
        client.AGENT_ID = "deep-research-pro-preview-12-2025"

        with pytest.raises(AIError, match="Context file not found"):
            await client.research(
                "Research Acme Corp",
                context_files=["/nonexistent/file.pdf"]
            )
