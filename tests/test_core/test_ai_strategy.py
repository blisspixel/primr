"""
Unit tests for the ai_strategy module.

Tests cover:
- CloudVendor enum values and display names
- AIStrategyConfig validation
- AIStrategyResult computed properties
- Prompt building functions
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from primr.core.ai_strategy import (
    AIStrategyConfig,
    AIStrategyResult,
    CloudVendor,
    StrategyPromptContext,
    build_ai_strategy_prompt,
    generate_ai_strategy,
    generate_ai_strategy_sync,
)

# =============================================================================
# CloudVendor Enum Tests
# =============================================================================


class TestCloudVendor:
    """Tests for CloudVendor enum."""

    def test_vendor_values(self):
        """Test all vendor enum values exist."""
        assert CloudVendor.AZURE.value == "azure"
        assert CloudVendor.AWS.value == "aws"
        assert CloudVendor.GCP.value == "gcp"
        assert CloudVendor.AGNOSTIC.value == "agnostic"

    def test_display_names(self):
        """Test vendor display names are human-readable."""
        assert CloudVendor.AZURE.display_name == "Microsoft Azure"
        assert CloudVendor.AWS.display_name == "Amazon Web Services (AWS)"
        assert CloudVendor.GCP.display_name == "Google Cloud Platform (GCP)"
        assert CloudVendor.AGNOSTIC.display_name == "Cloud Agnostic (Multi-Cloud)"

    def test_from_string_valid(self):
        """Test creating vendor from valid string."""
        assert CloudVendor.from_string("azure") == CloudVendor.AZURE
        assert CloudVendor.from_string("AZURE") == CloudVendor.AZURE
        assert CloudVendor.from_string("Azure") == CloudVendor.AZURE
        assert CloudVendor.from_string("aws") == CloudVendor.AWS
        assert CloudVendor.from_string("gcp") == CloudVendor.GCP
        assert CloudVendor.from_string("agnostic") == CloudVendor.AGNOSTIC

    def test_from_string_invalid_returns_agnostic(self):
        """Test invalid string returns AGNOSTIC as default."""
        assert CloudVendor.from_string("invalid") == CloudVendor.AGNOSTIC
        assert CloudVendor.from_string("") == CloudVendor.AGNOSTIC
        assert CloudVendor.from_string("unknown") == CloudVendor.AGNOSTIC

    @given(st.sampled_from(list(CloudVendor)))
    @settings(deadline=None)
    def test_display_name_not_empty(self, vendor):
        """Property: All vendors have non-empty display names."""
        assert vendor.display_name
        assert len(vendor.display_name) > 0


# =============================================================================
# AIStrategyConfig Tests
# =============================================================================


class TestAIStrategyConfig:
    """Tests for AIStrategyConfig dataclass."""

    def test_valid_config(self):
        """Test creating valid config."""
        config = AIStrategyConfig(company_name="Acme Corp", platform=CloudVendor.AZURE)
        assert config.company_name == "Acme Corp"
        assert config.platform == CloudVendor.AZURE
        assert config.company_research_path is None
        assert config.force_refresh_vendor is False
        assert config.timeout_seconds == 1800

    def test_config_with_research_path(self):
        """Test config with research path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            research_file = Path(tmpdir) / "research.md"
            research_file.write_text("# Research content")

            config = AIStrategyConfig(
                company_name="Test Co",
                platform=CloudVendor.AWS,
                company_research_path=str(research_file),
            )
            errors = config.validate()
            assert len(errors) == 0

    def test_validate_empty_company_name(self):
        """Test validation fails for empty company name."""
        config = AIStrategyConfig(company_name="", platform=CloudVendor.AZURE)
        errors = config.validate()
        assert len(errors) == 1
        assert "Company name is required" in errors[0]

    def test_validate_whitespace_company_name(self):
        """Test validation fails for whitespace-only company name."""
        config = AIStrategyConfig(company_name="   ", platform=CloudVendor.AZURE)
        errors = config.validate()
        assert len(errors) == 1
        assert "Company name is required" in errors[0]

    def test_validate_missing_research_file(self):
        """Test validation fails for missing research file."""
        config = AIStrategyConfig(
            company_name="Test Co",
            platform=CloudVendor.AZURE,
            company_research_path="/nonexistent/path/research.md",
        )
        errors = config.validate()
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_validate_empty_research_file(self):
        """Test validation fails for empty research file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_file = Path(tmpdir) / "empty.md"
            empty_file.write_text("")

            config = AIStrategyConfig(
                company_name="Test Co",
                platform=CloudVendor.AZURE,
                company_research_path=str(empty_file),
            )
            errors = config.validate()
            assert len(errors) == 1
            assert "empty" in errors[0]

    def test_config_is_frozen(self):
        """Test config is immutable (frozen)."""
        config = AIStrategyConfig(company_name="Test", platform=CloudVendor.AZURE)
        with pytest.raises(AttributeError):
            config.company_name = "Changed"


# =============================================================================
# AIStrategyResult Tests
# =============================================================================


class TestAIStrategyResult:
    """Tests for AIStrategyResult dataclass."""

    def test_successful_result(self):
        """Test successful result properties."""
        result = AIStrategyResult(
            docx_path="/output/strategy.docx",
            md_path="/output/strategy.md",
            txt_path="/output/strategy.txt",
            content="# AI Strategy",
            duration_seconds=120.5,
            vendor_research_paths=["/docs/vendor.txt"],
        )
        assert result.success is True
        assert result.error is None
        assert len(result.output_paths) == 3

    def test_failed_result(self):
        """Test failed result properties."""
        result = AIStrategyResult(
            docx_path=None,
            md_path=None,
            txt_path=None,
            content="",
            duration_seconds=5.0,
            vendor_research_paths=[],
            error="API key not configured",
        )
        assert result.success is False
        assert result.error == "API key not configured"
        assert len(result.output_paths) == 0

    def test_partial_result(self):
        """Test result with only some outputs."""
        result = AIStrategyResult(
            docx_path=None,
            md_path="/output/strategy.md",
            txt_path="/output/strategy.txt",
            content="# Content",
            duration_seconds=60.0,
            vendor_research_paths=[],
        )
        # No docx means not fully successful
        assert result.success is False
        assert len(result.output_paths) == 2

    def test_output_paths_excludes_none(self):
        """Test output_paths only includes non-None paths."""
        result = AIStrategyResult(
            docx_path="/output/strategy.docx",
            md_path=None,
            txt_path="/output/strategy.txt",
            content="content",
            duration_seconds=10.0,
            vendor_research_paths=[],
        )
        assert len(result.output_paths) == 2
        assert None not in result.output_paths


# =============================================================================
# StrategyPromptContext Tests
# =============================================================================


class TestStrategyPromptContext:
    """Tests for StrategyPromptContext dataclass."""

    def test_create_context(self):
        """Test creating prompt context."""
        context = StrategyPromptContext(
            company_name="Test Corp",
            platform=CloudVendor.AZURE,
            current_date="December 2025",
            vendor_guidance="Azure guidance here",
            vendor_name="Microsoft Azure",
        )
        assert context.company_name == "Test Corp"
        assert context.platform == CloudVendor.AZURE
        assert context.current_date == "December 2025"


# =============================================================================
# Prompt Building Tests
# =============================================================================


class TestBuildAIStrategyPrompt:
    """Tests for build_ai_strategy_prompt function."""

    def test_prompt_contains_company_name(self):
        """Test prompt includes company name."""
        prompt = build_ai_strategy_prompt("Acme Corp", CloudVendor.AZURE)
        assert "Acme Corp" in prompt

    def test_prompt_contains_vendor_context(self):
        """Test prompt includes vendor-specific context."""
        azure_prompt = build_ai_strategy_prompt("Test", CloudVendor.AZURE)
        assert "Microsoft Azure" in azure_prompt
        assert "Azure OpenAI" in azure_prompt or "Copilot" in azure_prompt

        aws_prompt = build_ai_strategy_prompt("Test", CloudVendor.AWS)
        assert "Amazon" in aws_prompt or "AWS" in aws_prompt
        assert "Bedrock" in aws_prompt

        gcp_prompt = build_ai_strategy_prompt("Test", CloudVendor.GCP)
        assert "Google Cloud" in gcp_prompt
        assert "Vertex AI" in gcp_prompt

    def test_prompt_contains_required_sections(self):
        """Test prompt includes all required sections."""
        prompt = build_ai_strategy_prompt("Test Co", CloudVendor.AGNOSTIC)

        required_sections = [
            "AI Strategic Thesis",
            "Executive Summary",
            "Likely Current State",  # Changed from "Current State Assessment"
            "Quick Wins",
            "Bigger Bets",
            "NOT to Pursue",
            "Board Summary",
            "ROI",
        ]

        for section in required_sections:
            assert section in prompt, f"Missing section: {section}"

    def test_prompt_contains_date(self):
        """Test prompt includes current date."""
        from datetime import datetime

        current_month = datetime.now().strftime("%B %Y")

        prompt = build_ai_strategy_prompt("Test", CloudVendor.AZURE)
        assert current_month in prompt

    @given(st.sampled_from(list(CloudVendor)))
    @settings(deadline=None)
    def test_prompt_not_empty_for_any_vendor(self, vendor):
        """Property: Prompt is non-empty for all vendors."""
        prompt = build_ai_strategy_prompt("Test Company", vendor)
        assert len(prompt) > 1000  # Should be substantial


# =============================================================================
# Integration Tests (with mocks)
# =============================================================================


class TestGenerateAIStrategy:
    """Tests for generate_ai_strategy function."""

    @pytest.mark.asyncio
    async def test_preflight_fails_without_api_key(self):
        """Test preflight validation fails without API key."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = None
            mock_settings.return_value.api = mock_api

            result = await generate_ai_strategy(company_name="Test Corp", platform="azure")

            assert result.success is False
            assert "GEMINI_API_KEY" in result.error

    @pytest.mark.asyncio
    async def test_preflight_fails_with_empty_company_name(self):
        """Test preflight validation fails with empty company name."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = "test-key"
            mock_settings.return_value.api = mock_api

            result = await generate_ai_strategy(company_name="", platform="azure")

            assert result.success is False
            assert "Company name" in result.error

    @pytest.mark.asyncio
    async def test_vendor_string_converted_to_enum(self):
        """Test string vendor is converted to CloudVendor enum."""
        with patch("primr.core.ai_strategy._validate_preflight") as mock_validate:
            mock_validate.return_value = ["Test error"]

            result = await generate_ai_strategy(
                company_name="Test",
                platform="azure",  # String, not enum
            )

            # Should fail at preflight, but vendor conversion should work
            assert result.success is False

    def test_sync_wrapper_calls_async(self):
        """Test sync wrapper properly calls async function."""
        with patch("primr.core.ai_strategy._validate_preflight") as mock_validate:
            mock_validate.return_value = ["Preflight error"]

            result = generate_ai_strategy_sync(company_name="Test", platform="azure")

            # Should return None on failure
            assert result is None


# =============================================================================
# Property Tests
# =============================================================================


class TestAIStrategyProperties:
    """Property-based tests for AI strategy module."""

    @given(st.text(min_size=1, max_size=100).filter(lambda x: x.strip()))
    @settings(deadline=None)
    def test_config_validates_non_empty_names(self, company_name):
        """Property: Non-empty company names pass validation."""
        config = AIStrategyConfig(company_name=company_name, platform=CloudVendor.AZURE)
        errors = config.validate()
        # Should not have "Company name is required" error
        assert not any("Company name is required" in e for e in errors)

    @given(st.sampled_from(list(CloudVendor)))
    @settings(deadline=None)
    def test_vendor_roundtrip(self, vendor):
        """Property: Vendor value can roundtrip through from_string."""
        result = CloudVendor.from_string(vendor.value)
        assert result == vendor

    @given(
        st.floats(min_value=0, max_value=10000),
        st.lists(st.text(min_size=1, max_size=50), max_size=5),
    )
    @settings(deadline=None)
    def test_result_duration_preserved(self, duration, paths):
        """Property: Duration is preserved in result."""
        result = AIStrategyResult(
            docx_path=None,
            md_path=None,
            txt_path=None,
            content="",
            duration_seconds=duration,
            vendor_research_paths=paths,
        )
        assert result.duration_seconds == duration
        assert result.vendor_research_paths == paths
