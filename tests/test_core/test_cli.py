"""
Unit tests for the cli module.

Tests cover:
- Command enum
- CLIConfig dataclass
- parse_args function
- Command dispatch
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

from primr.core.cli import (
    CLIConfig,
    Command,
    MODE_MAP,
    main,
    parse_args,
    run_doctor,
)


# =============================================================================
# Command Enum Tests
# =============================================================================

class TestCommand:
    """Tests for Command enum."""

    def test_command_values(self):
        """Test all command enum values exist."""
        assert Command.RESEARCH.value == "research"
        assert Command.DOCTOR.value == "doctor"
        assert Command.LIST_RECENT.value == "list-recent"
        assert Command.CLEAN_TEMP.value == "clean-temp"
        assert Command.CHECK_QUOTA.value == "check-quota"
        assert Command.CHECK_JOBS.value == "check-jobs"
        assert Command.SHOW_USAGE.value == "show-usage"
        assert Command.DRY_RUN.value == "dry-run"
        assert Command.GENERATE_VENDOR.value == "generate-vendor"
        assert Command.BATCH.value == "batch"


# =============================================================================
# CLIConfig Tests
# =============================================================================

class TestCLIConfig:
    """Tests for CLIConfig dataclass."""

    def test_default_config(self):
        """Test default config values."""
        config = CLIConfig(command=Command.RESEARCH)
        assert config.command == Command.RESEARCH
        assert config.company_name is None
        assert config.website is None
        assert config.mode == "complete"
        assert config.citation_style == "numbered"
        assert config.ai_strategy is True
        assert config.cloud_vendor == "azure"
        assert config.skip_confirm is True
        assert config.context_files == ()

    def test_config_with_values(self):
        """Test config with custom values."""
        config = CLIConfig(
            command=Command.RESEARCH,
            company_name="Acme Corp",
            website="https://acme.example",
            mode="deep-research",
            ai_strategy=False,
            cloud_vendor="aws"
        )
        assert config.company_name == "Acme Corp"
        assert config.website == "https://acme.example"
        assert config.mode == "deep-research"
        assert config.ai_strategy is False
        assert config.cloud_vendor == "aws"

    def test_has_company_info_with_name(self):
        """Test has_company_info with company name."""
        config = CLIConfig(command=Command.RESEARCH, company_name="Acme Corp")
        assert config.has_company_info is True

    def test_has_company_info_with_website(self):
        """Test has_company_info with website only."""
        config = CLIConfig(command=Command.RESEARCH, website="https://acme.example")
        assert config.has_company_info is True

    def test_has_company_info_without_either(self):
        """Test has_company_info without company or website."""
        config = CLIConfig(command=Command.RESEARCH)
        assert config.has_company_info is False

    def test_config_is_frozen(self):
        """Test config is immutable."""
        config = CLIConfig(command=Command.RESEARCH)
        with pytest.raises(AttributeError):
            config.company_name = "Changed"


# =============================================================================
# MODE_MAP Tests
# =============================================================================

class TestModeMap:
    """Tests for mode name mapping."""

    def test_new_mode_names(self):
        """Test new mode names map correctly."""
        assert MODE_MAP["scrape"] == "scrape-only"
        assert MODE_MAP["deep"] == "deep-research"
        assert MODE_MAP["full"] == "complete"
        assert MODE_MAP["parallel"] == "hybrid"

    def test_old_mode_names_preserved(self):
        """Test old mode names still work."""
        assert MODE_MAP["structured"] == "structured"
        assert MODE_MAP["deep-research"] == "deep-research"
        assert MODE_MAP["complete"] == "complete"
        assert MODE_MAP["hybrid"] == "hybrid"
        assert MODE_MAP["scrape-only"] == "scrape-only"


# =============================================================================
# parse_args Tests
# =============================================================================

class TestParseArgs:
    """Tests for parse_args function."""

    def test_parse_basic_research(self):
        """Test parsing basic research command."""
        config = parse_args(["Acme Corp", "https://acme.example"])
        assert config.command == Command.RESEARCH
        assert config.company_name == "Acme Corp"
        assert config.website == "https://acme.example"

    def test_parse_doctor_command(self):
        """Test parsing doctor command."""
        config = parse_args(["doctor"])
        assert config.command == Command.DOCTOR

    def test_parse_mode_flag(self):
        """Test parsing mode flag."""
        config = parse_args(["Acme Corp", "acme.example", "--mode", "deep"])
        assert config.mode == "deep-research"  # Mapped from "deep"

    def test_parse_mode_short_flag(self):
        """Test parsing mode with short flag."""
        config = parse_args(["Acme Corp", "acme.example", "-m", "scrape"])
        assert config.mode == "scrape-only"  # Mapped from "scrape"

    def test_parse_no_ai_strategy(self):
        """Test parsing --no-ai-strategy flag."""
        config = parse_args(["Acme Corp", "acme.example", "--no-ai-strategy"])
        assert config.ai_strategy is False

    def test_parse_cloud_vendor(self):
        """Test parsing cloud vendor flag."""
        config = parse_args(["Acme Corp", "acme.example", "--cloud-vendor", "aws"])
        assert config.cloud_vendor == "aws"

    def test_parse_context_files(self):
        """Test parsing context files."""
        config = parse_args(["Acme Corp", "acme.example", "--context", "file1.pdf", "file2.txt"])
        assert config.context_files == ("file1.pdf", "file2.txt")

    def test_parse_csv_batch(self):
        """Test parsing CSV batch mode."""
        config = parse_args(["--csv", "companies.csv"])
        assert config.command == Command.BATCH
        assert config.csv_file == "companies.csv"

    def test_parse_dry_run(self):
        """Test parsing dry-run flag."""
        config = parse_args(["Acme Corp", "acme.example", "--dry-run"])
        assert config.command == Command.DRY_RUN

    def test_parse_show_usage(self):
        """Test parsing show-usage flag."""
        config = parse_args(["--show-usage"])
        assert config.command == Command.SHOW_USAGE

    def test_parse_list_recent(self):
        """Test parsing list-recent flag."""
        config = parse_args(["--list-recent"])
        assert config.command == Command.LIST_RECENT

    def test_parse_check_quota(self):
        """Test parsing check-quota flag."""
        config = parse_args(["--check-quota"])
        assert config.command == Command.CHECK_QUOTA

    def test_parse_generate_vendor(self):
        """Test parsing generate-vendor-research flag."""
        config = parse_args(["--generate-vendor-research", "azure"])
        assert config.command == Command.GENERATE_VENDOR
        assert config.generate_vendor == "azure"

    def test_parse_quiet_flag(self):
        """Test parsing quiet flag."""
        config = parse_args(["Acme Corp", "acme.example", "-q"])
        assert config.quiet is True

    def test_parse_verbose_flag(self):
        """Test parsing verbose flag."""
        config = parse_args(["Acme Corp", "acme.example", "-v"])
        assert config.verbose is True

    def test_parse_confirm_flag(self):
        """Test parsing confirm flag."""
        config = parse_args(["Acme Corp", "acme.example", "--confirm"])
        assert config.skip_confirm is False  # Inverted


# =============================================================================
# main() Tests
# =============================================================================

class TestMain:
    """Tests for main function."""

    def test_main_doctor_returns_exit_code(self):
        """Test main with doctor command returns exit code."""
        with patch("primr.core.cli.run_doctor") as mock_doctor:
            mock_doctor.return_value = 0
            result = main(["doctor"])
            assert result == 0
            mock_doctor.assert_called_once()

    def test_main_show_usage(self):
        """Test main with show-usage flag."""
        with patch("primr.utils.usage_tracker.get_usage_tracker") as mock_tracker:
            mock_tracker.return_value.display_usage_history.return_value = "Usage stats"
            result = main(["--show-usage"])
            assert result == 0

    def test_main_list_recent(self):
        """Test main with list-recent flag."""
        with patch("primr.core.cli.list_recent_outputs") as mock_list:
            result = main(["--list-recent"])
            assert result == 0
            mock_list.assert_called_once()

    def test_main_dry_run(self):
        """Test main with dry-run flag."""
        with patch("primr.utils.cost_estimator.estimate_cost") as mock_estimate:
            mock_estimate.return_value = MagicMock(__str__=lambda x: "Cost estimate")
            result = main(["Acme Corp", "acme.example", "--dry-run"])
            assert result == 0

    def test_main_research_missing_args(self):
        """Test main with missing required args."""
        result = main(["Acme Corp"])  # Missing website
        assert result == 1


# =============================================================================
# run_doctor Tests
# =============================================================================

class TestRunDoctor:
    """Tests for run_doctor function."""

    def test_doctor_returns_exit_code(self):
        """Test doctor returns appropriate exit code."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with patch("primr.core.cli._check_api_connectivity") as mock_api:
                mock_api.return_value = (False, 0)
                result = run_doctor()
                # Should fail without API key
                assert result == 1

    def test_doctor_with_valid_config(self):
        """Test doctor with valid configuration."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AItest1234567890"}):
            with patch("primr.core.cli._check_dependencies") as mock_deps:
                mock_deps.return_value = 0
                with patch("primr.core.cli._check_filesystem") as mock_fs:
                    mock_fs.return_value = (True, 0)
                    with patch("primr.core.cli._check_api_connectivity") as mock_api:
                        mock_api.return_value = (True, 0)
                        result = run_doctor()
                        assert result == 0


# =============================================================================
# Property Tests
# =============================================================================

class TestCLIProperties:
    """Property-based tests for CLI module."""

    @given(st.sampled_from(list(Command)))
    @settings(deadline=None)
    def test_command_has_value(self, command):
        """Property: All commands have string values."""
        assert isinstance(command.value, str)
        assert len(command.value) > 0

    @given(st.text(min_size=1, max_size=50).filter(lambda x: x.strip()))
    @settings(deadline=None)
    def test_config_preserves_company_name(self, company_name):
        """Property: Config preserves company name."""
        config = CLIConfig(command=Command.RESEARCH, company_name=company_name)
        assert config.company_name == company_name

    @given(st.sampled_from(["azure", "aws", "gcp", "agnostic"]))
    @settings(deadline=None)
    def test_parse_args_preserves_vendor(self, vendor):
        """Property: parse_args preserves cloud vendor."""
        config = parse_args(["Test", "test.com", "--cloud-vendor", vendor])
        assert config.cloud_vendor == vendor

    @given(st.sampled_from(["scrape", "deep", "full", "parallel"]))
    @settings(deadline=None)
    def test_mode_mapping_exists(self, mode):
        """Property: All new mode names have mappings."""
        assert mode in MODE_MAP
        assert MODE_MAP[mode] in ["scrape-only", "deep-research", "complete", "hybrid"]
