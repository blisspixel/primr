"""
Unit tests for the deep_research_runner module.

Tests cover:
- PreflightStatus enum
- DeepResearchMode enum
- PreflightCheck and PreflightResult dataclasses
- DeepResearchConfig validation
- DeepResearchResult computed properties
- validate_preflight function
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from primr.core.deep_research_runner import (
    DeepResearchConfig,
    DeepResearchMode,
    DeepResearchResult,
    PreflightCheck,
    PreflightResult,
    PreflightStatus,
    perform_deep_research,
    perform_deep_research_sync,
    validate_preflight,
)

# =============================================================================
# PreflightStatus Enum Tests
# =============================================================================


class TestPreflightStatus:
    """Tests for PreflightStatus enum."""

    def test_status_values(self):
        """Test all status enum values exist."""
        assert PreflightStatus.PASSED.value == "passed"
        assert PreflightStatus.FAILED.value == "failed"
        assert PreflightStatus.WARNING.value == "warning"


# =============================================================================
# DeepResearchMode Enum Tests
# =============================================================================


class TestDeepResearchMode:
    """Tests for DeepResearchMode enum."""

    def test_mode_values(self):
        """Test all mode enum values exist."""
        assert DeepResearchMode.DEEP_RESEARCH.value == "deep-research"
        assert DeepResearchMode.COMPLETE.value == "complete"
        assert DeepResearchMode.HYBRID.value == "hybrid"

    def test_display_names(self):
        """Test mode display names are human-readable."""
        assert DeepResearchMode.DEEP_RESEARCH.display_name == "Deep Research"
        assert DeepResearchMode.COMPLETE.display_name == "Complete (Two-Step)"
        assert DeepResearchMode.HYBRID.display_name == "Hybrid"

    def test_from_string_valid(self):
        """Test creating mode from valid string."""
        assert DeepResearchMode.from_string("deep-research") == DeepResearchMode.DEEP_RESEARCH
        assert DeepResearchMode.from_string("DEEP-RESEARCH") == DeepResearchMode.DEEP_RESEARCH
        assert DeepResearchMode.from_string("complete") == DeepResearchMode.COMPLETE
        assert DeepResearchMode.from_string("hybrid") == DeepResearchMode.HYBRID

    def test_from_string_invalid_returns_default(self):
        """Test invalid string returns DEEP_RESEARCH as default."""
        assert DeepResearchMode.from_string("invalid") == DeepResearchMode.DEEP_RESEARCH
        assert DeepResearchMode.from_string("") == DeepResearchMode.DEEP_RESEARCH


# =============================================================================
# PreflightCheck Tests
# =============================================================================


class TestPreflightCheck:
    """Tests for PreflightCheck dataclass."""

    def test_passed_check(self):
        """Test passed check properties."""
        check = PreflightCheck(
            name="api_key", status=PreflightStatus.PASSED, message="API key configured"
        )
        assert check.passed is True
        assert check.failed is False

    def test_failed_check(self):
        """Test failed check properties."""
        check = PreflightCheck(
            name="api_key",
            status=PreflightStatus.FAILED,
            message="API key not configured",
            guidance="Set GEMINI_API_KEY in .env",
        )
        assert check.passed is False
        assert check.failed is True
        assert check.guidance == "Set GEMINI_API_KEY in .env"

    def test_warning_check(self):
        """Test warning check properties."""
        check = PreflightCheck(
            name="context_file",
            status=PreflightStatus.WARNING,
            message="Large context file may slow processing",
        )
        assert check.passed is False
        assert check.failed is False


# =============================================================================
# PreflightResult Tests
# =============================================================================


class TestPreflightResult:
    """Tests for PreflightResult dataclass."""

    def test_empty_result_is_valid(self):
        """Test empty result is valid."""
        result = PreflightResult()
        assert result.is_valid is True
        assert result.passed_count == 0
        assert result.failed_count == 0

    def test_all_passed_is_valid(self):
        """Test result with all passed checks is valid."""
        result = PreflightResult()
        result.add(PreflightCheck("check1", PreflightStatus.PASSED, "OK"))
        result.add(PreflightCheck("check2", PreflightStatus.PASSED, "OK"))
        assert result.is_valid is True
        assert result.passed_count == 2
        assert result.failed_count == 0

    def test_any_failed_is_invalid(self):
        """Test result with any failed check is invalid."""
        result = PreflightResult()
        result.add(PreflightCheck("check1", PreflightStatus.PASSED, "OK"))
        result.add(PreflightCheck("check2", PreflightStatus.FAILED, "Error"))
        assert result.is_valid is False
        assert result.passed_count == 1
        assert result.failed_count == 1

    def test_errors_list(self):
        """Test errors list contains failed messages."""
        result = PreflightResult()
        result.add(PreflightCheck("check1", PreflightStatus.FAILED, "Error 1"))
        result.add(PreflightCheck("check2", PreflightStatus.PASSED, "OK"))
        result.add(PreflightCheck("check3", PreflightStatus.FAILED, "Error 2"))
        assert result.errors == ["Error 1", "Error 2"]

    def test_warnings_list(self):
        """Test warnings list contains warning messages."""
        result = PreflightResult()
        result.add(PreflightCheck("check1", PreflightStatus.WARNING, "Warning 1"))
        result.add(PreflightCheck("check2", PreflightStatus.PASSED, "OK"))
        assert result.warnings == ["Warning 1"]


# =============================================================================
# DeepResearchConfig Tests
# =============================================================================


class TestDeepResearchConfig:
    """Tests for DeepResearchConfig dataclass."""

    def test_basic_config(self):
        """Test creating basic config."""
        config = DeepResearchConfig(
            company_name="Acme Corp",
            website="https://acme.com",
            mode=DeepResearchMode.DEEP_RESEARCH,
        )
        assert config.company_name == "Acme Corp"
        assert config.website == "https://acme.com"
        assert config.mode == DeepResearchMode.DEEP_RESEARCH
        assert config.ai_strategy is False
        assert config.platform == "agnostic"

    def test_display_name_from_company(self):
        """Test display name uses company name when available."""
        config = DeepResearchConfig(
            company_name="Test Corp", website="https://test.com", mode=DeepResearchMode.COMPLETE
        )
        assert config.display_name == "Test Corp"

    def test_display_name_from_website(self):
        """Test display name uses website when no company name."""
        config = DeepResearchConfig(
            company_name=None, website="https://example.com", mode=DeepResearchMode.COMPLETE
        )
        assert config.display_name == "example.com"

    def test_display_name_unknown(self):
        """Test display name is Unknown when nothing provided."""
        config = DeepResearchConfig(company_name=None, website=None, mode=DeepResearchMode.COMPLETE)
        assert config.display_name == "Unknown"

    def test_from_args(self):
        """Test creating config from CLI arguments."""
        config = DeepResearchConfig.from_args(
            company_name="Test",
            website="https://test.com",
            mode="complete",
            ai_strategy=True,
            platform="azure",
        )
        assert config.company_name == "Test"
        assert config.mode == DeepResearchMode.COMPLETE
        assert config.ai_strategy is True
        assert config.platform == "azure"

    def test_from_args_with_context_files(self):
        """Test creating config with context files."""
        config = DeepResearchConfig.from_args(
            company_name="Test",
            website=None,
            mode="deep-research",
            context_files=["file1.pdf", "file2.txt"],
        )
        assert config.context_files == ("file1.pdf", "file2.txt")

    def test_config_is_frozen(self):
        """Test config is immutable."""
        config = DeepResearchConfig(
            company_name="Test", website=None, mode=DeepResearchMode.DEEP_RESEARCH
        )
        with pytest.raises(AttributeError):
            config.company_name = "Changed"


# =============================================================================
# DeepResearchResult Tests
# =============================================================================


class TestDeepResearchResult:
    """Tests for DeepResearchResult dataclass."""

    def test_successful_result(self):
        """Test successful result properties."""
        result = DeepResearchResult(
            docx_path="/output/report.docx",
            md_path="/output/report.md",
            raw_content="# Report",
            section_results={"intro": "Introduction", "summary": "Summary"},
            citations=["Source 1", "Source 2"],
            duration_seconds=120.5,
        )
        assert result.success is True
        assert result.section_count == 2
        assert result.citation_count == 2
        assert result.error is None

    def test_failed_result(self):
        """Test failed result properties."""
        result = DeepResearchResult(
            docx_path=None,
            md_path=None,
            raw_content="",
            section_results={},
            citations=[],
            duration_seconds=5.0,
            error="API key not configured",
        )
        assert result.success is False
        assert result.section_count == 0
        assert result.citation_count == 0
        assert result.error == "API key not configured"

    def test_result_with_ai_strategy(self):
        """Test result with AI strategy path."""
        result = DeepResearchResult(
            docx_path="/output/report.docx",
            md_path="/output/report.md",
            raw_content="content",
            section_results={"intro": "text"},
            citations=[],
            duration_seconds=300.0,
            ai_strategy_path="/output/strategy.docx",
        )
        assert result.success is True
        assert result.ai_strategy_path == "/output/strategy.docx"


# =============================================================================
# validate_preflight Tests
# =============================================================================


class TestValidatePreflight:
    """Tests for validate_preflight function."""

    def test_valid_config_passes(self):
        """Test valid config passes preflight."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = "test-api-key"
            mock_settings.return_value.api = mock_api

            config = DeepResearchConfig(
                company_name="Test Corp",
                website="https://test.com",
                mode=DeepResearchMode.DEEP_RESEARCH,
            )
            result = validate_preflight(config)
            assert result.is_valid is True

    def test_missing_company_and_website_fails(self):
        """Test missing company and website fails preflight."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = "test-api-key"
            mock_settings.return_value.api = mock_api

            config = DeepResearchConfig(
                company_name=None, website=None, mode=DeepResearchMode.DEEP_RESEARCH
            )
            result = validate_preflight(config)
            assert result.is_valid is False
            assert any("company name or website" in e.lower() for e in result.errors)

    def test_missing_api_key_fails(self):
        """Test missing API key fails preflight."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = None
            mock_settings.return_value.api = mock_api

            config = DeepResearchConfig(
                company_name="Test", website=None, mode=DeepResearchMode.DEEP_RESEARCH
            )
            result = validate_preflight(config)
            assert result.is_valid is False
            assert any("GEMINI_API_KEY" in e for e in result.errors)

    def test_missing_context_file_fails(self):
        """Test missing context file fails preflight."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = "test-key"
            mock_settings.return_value.api = mock_api

            config = DeepResearchConfig(
                company_name="Test",
                website=None,
                mode=DeepResearchMode.DEEP_RESEARCH,
                context_files=("/nonexistent/file.pdf",),
            )
            result = validate_preflight(config)
            assert result.is_valid is False
            assert any("not found" in e for e in result.errors)

    def test_empty_context_file_fails(self):
        """Test empty context file fails preflight."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_file = Path(tmpdir) / "empty.txt"
            empty_file.write_text("")

            with patch("primr.config.settings.get_settings") as mock_settings:
                mock_api = MagicMock()
                mock_api.gemini_key = "test-key"
                mock_settings.return_value.api = mock_api

                config = DeepResearchConfig(
                    company_name="Test",
                    website=None,
                    mode=DeepResearchMode.DEEP_RESEARCH,
                    context_files=(str(empty_file),),
                )
                result = validate_preflight(config)
                assert result.is_valid is False
                assert any("empty" in e for e in result.errors)

    def test_valid_context_file_passes(self):
        """Test valid context file passes preflight."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_file = Path(tmpdir) / "context.txt"
            valid_file.write_text("Some content")

            with patch("primr.config.settings.get_settings") as mock_settings:
                mock_api = MagicMock()
                mock_api.gemini_key = "test-key"
                mock_settings.return_value.api = mock_api

                config = DeepResearchConfig(
                    company_name="Test",
                    website=None,
                    mode=DeepResearchMode.DEEP_RESEARCH,
                    context_files=(str(valid_file),),
                )
                result = validate_preflight(config)
                assert result.is_valid is True


# =============================================================================
# Integration Tests (with mocks)
# =============================================================================


class TestPerformDeepResearch:
    """Tests for perform_deep_research function."""

    @pytest.mark.asyncio
    async def test_preflight_failure_returns_error(self):
        """Test preflight failure returns error result."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = None
            mock_settings.return_value.api = mock_api

            config = DeepResearchConfig(
                company_name="Test", website=None, mode=DeepResearchMode.DEEP_RESEARCH
            )
            result = await perform_deep_research(config)
            assert result.success is False
            assert "GEMINI_API_KEY" in result.error

    def test_sync_wrapper_calls_async(self):
        """Test sync wrapper properly calls async function."""
        with patch("primr.config.settings.get_settings") as mock_settings:
            mock_api = MagicMock()
            mock_api.gemini_key = None
            mock_settings.return_value.api = mock_api

            config = DeepResearchConfig(
                company_name="Test", website=None, mode=DeepResearchMode.DEEP_RESEARCH
            )
            result = perform_deep_research_sync(config)
            assert result.success is False


# =============================================================================
# Property Tests
# =============================================================================


class TestDeepResearchProperties:
    """Property-based tests for deep research runner module."""

    @given(st.sampled_from(list(DeepResearchMode)))
    @settings(deadline=None)
    def test_mode_roundtrip(self, mode):
        """Property: Mode value can roundtrip through from_string."""
        result = DeepResearchMode.from_string(mode.value)
        assert result == mode

    @given(st.sampled_from(list(PreflightStatus)))
    @settings(deadline=None)
    def test_check_status_consistency(self, status):
        """Property: Check passed/failed are mutually exclusive."""
        check = PreflightCheck("test", status, "message")
        # Can't be both passed and failed
        assert not (check.passed and check.failed)

    @given(st.lists(st.sampled_from(list(PreflightStatus)), min_size=0, max_size=10))
    @settings(deadline=None)
    def test_result_counts_match_checks(self, statuses):
        """Property: Result counts match actual checks."""
        result = PreflightResult()
        for i, status in enumerate(statuses):
            result.add(PreflightCheck(f"check_{i}", status, f"message_{i}"))

        expected_passed = sum(1 for s in statuses if s == PreflightStatus.PASSED)
        expected_failed = sum(1 for s in statuses if s == PreflightStatus.FAILED)

        assert result.passed_count == expected_passed
        assert result.failed_count == expected_failed

    @given(
        st.floats(min_value=0, max_value=10000),
        st.dictionaries(
            st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=100), max_size=10
        ),
    )
    @settings(deadline=None)
    def test_result_section_count_matches_dict(self, duration, sections):
        """Property: Section count matches dictionary size."""
        result = DeepResearchResult(
            docx_path=None,
            md_path=None,
            raw_content="",
            section_results=sections,
            citations=[],
            duration_seconds=duration,
        )
        assert result.section_count == len(sections)
