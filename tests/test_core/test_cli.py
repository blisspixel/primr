"""
Unit tests for the cli module.

Tests cover:
- Command enum
- CLIConfig dataclass
- parse_args function
- Command dispatch
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from primr.core.cli import (
    MODE_MAP,
    CLIConfig,
    Command,
    _create_parser,
    _ensure_project_env_file,
    _handle_research,
    _resolve_local_judge_models,
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
        assert Command.INIT.value == "init"
        assert Command.DOCTOR.value == "doctor"
        assert Command.LIST_RECENT.value == "list-recent"
        assert Command.CLEAN_TEMP.value == "clean-temp"
        assert Command.CHECK_QUOTA.value == "check-quota"
        assert Command.CHECK_JOBS.value == "check-jobs"
        assert Command.RESUME_LATEST.value == "resume-latest"
        assert Command.SHOW_USAGE.value == "show-usage"
        assert Command.DRY_RUN.value == "dry-run"
        assert Command.GENERATE_VENDOR.value == "generate-vendor"
        assert Command.BATCH.value == "batch"
        assert Command.IMPROVE.value == "improve"


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
        assert config.cloud_vendor == "agnostic"
        assert config.skip_confirm is True
        assert config.context_files == ()
        assert config.browser_session_mode == "persistent"

    def test_config_with_values(self):
        """Test config with custom values."""
        config = CLIConfig(
            command=Command.RESEARCH,
            company_name="Acme Corp",
            website="https://acme.example",
            mode="deep-research",
            ai_strategy=False,
            platforms=("aws",),
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

    def test_parse_init_command(self):
        """Test parsing init command."""
        config = parse_args(["init", "--non-interactive", "--skip-browsers", "--no-doctor"])
        assert config.command == Command.INIT
        assert config.init_non_interactive is True
        assert config.init_skip_browsers is True
        assert config.init_no_doctor is True

    def test_parse_doctor_fix(self):
        """Test parsing doctor --fix."""
        config = parse_args(["doctor", "--fix"])
        assert config.command == Command.DOCTOR
        assert config.doctor_fix is True

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

    def test_parse_browser_headed(self):
        """Test parsing headed browser flag."""
        config = parse_args(["Acme Corp", "acme.example", "--browser-headed"])
        assert config.browser_headed is True

    def test_parse_browser_session_mode(self):
        """Test parsing browser session mode."""
        config = parse_args(["Acme Corp", "acme.example", "--browser-session", "persistent"])
        assert config.browser_session_mode == "persistent"

    def test_parse_cloud_vendor(self):
        """Test parsing cloud vendor flag."""
        config = parse_args(["Acme Corp", "acme.example", "--cloud-vendor", "aws"])
        assert config.cloud_vendor == "aws"
        assert config.cloud_vendors == ("aws",)

    def test_parse_multiple_cloud_vendors(self):
        """Test parsing multiple cloud vendors."""
        config = parse_args(["Acme Corp", "acme.example", "--cloud-vendor", "aws", "azure"])
        assert config.cloud_vendors == ("aws", "azure")
        assert config.cloud_vendor == "aws"  # backward-compat returns first

    def test_parse_cloud_vendor_deduplicates(self):
        """Test that duplicate cloud vendors are removed."""
        config = parse_args(["Acme Corp", "acme.example", "--cloud-vendor", "aws", "aws"])
        assert config.cloud_vendors == ("aws",)

    def test_parse_context_files(self):
        """Test parsing context files."""
        config = parse_args(["Acme Corp", "acme.example", "--context", "file1.pdf", "file2.txt"])
        assert config.context_files == ("file1.pdf", "file2.txt")

    def test_parse_output_dir(self):
        """Test parsing custom output directory."""
        config = parse_args(["Acme Corp", "acme.example", "--output-dir", "client-output"])
        assert config.output_dir == "client-output"

    def test_parse_csv_batch(self):
        """Test parsing CSV batch mode."""
        config = parse_args(["--csv", "companies.csv"])
        assert config.command == Command.BATCH
        assert config.csv_file == "companies.csv"

    def test_parse_dry_run(self):
        """Test parsing dry-run flag."""
        config = parse_args(["Acme Corp", "acme.example", "--dry-run"])
        assert config.command == Command.DRY_RUN

    def test_parse_batch_dry_run_stays_on_batch_handler(self):
        config = parse_args(["--batch", "companies.csv", "--dry-run"])
        assert config.command == Command.BATCH
        assert config.dry_run_requested is True

    def test_parse_eval_command(self):
        """Test parsing eval command and options."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-02-r1",
                "--eval-profiles",
                "full",
                "fast",
                "--eval-baseline",
                "full",
            ]
        )
        assert config.command == Command.EVAL
        assert config.eval_mode is True
        assert config.eval_id == "eval-2026-02-r1"
        assert config.eval_profiles == ("full", "fast")
        assert config.eval_baseline == "full"

    def test_parse_eval_company_and_no_auto_stage(self):
        """Test eval company targeting and auto-stage toggle."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-02-r1",
                "--eval-company",
                "ExampleCo",
                "--eval-no-auto-stage",
                "--eval-source-dir",
                "output",
            ]
        )
        assert config.command == Command.EVAL
        assert config.eval_company == "ExampleCo"
        assert config.eval_auto_stage is False
        assert config.eval_source_dir == "output"

    def test_parse_eval_llm_judge_options(self):
        """Test eval LLM judge argument parsing."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-02-r1",
                "--eval-llm-judge",
                "--eval-judge-provider",
                "grok",
                "--eval-judge-model",
                "grok-4.3",
                "--eval-judge-max-pairs",
                "1",
                "--eval-judge-passes",
                "1",
                "--eval-judge-max-cost",
                "0.25",
            ]
        )
        assert config.eval_llm_judge is True
        assert config.eval_judge_provider == "grok"
        assert config.eval_judge_model == "grok-4.3"
        assert config.eval_judge_max_pairs == 1
        assert config.eval_judge_passes == 1
        assert config.eval_judge_max_cost == 0.25

    def test_parse_local_eval_judge_model_list(self):
        """Test parsing named local judge model lists."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-03-r1",
                "--eval-llm-judge",
                "--eval-judge-provider",
                "local",
                "--eval-judge-model-list",
                "4090-top10",
            ]
        )
        assert config.eval_llm_judge is True
        assert config.eval_judge_provider == "local"
        assert config.eval_judge_model_list == "4090-top10"

    def test_resolve_local_judge_models_from_named_list(self, monkeypatch):
        """Test resolving a named local judge list against installed Ollama models."""
        config = CLIConfig(
            command=Command.EVAL,
            eval_llm_judge=True,
            eval_judge_provider="local",
            eval_judge_model_list="installed-starter",
        )
        monkeypatch.setattr(
            "primr.core.cli._list_installed_ollama_models",
            lambda: {"qwen3:30b", "qwen2.5:14b"},
        )
        selected, missing = _resolve_local_judge_models(config)
        assert selected == ["qwen3:30b", "qwen2.5:14b"]
        assert "qwen3-coder:30b" in missing
        assert "qwen2.5-coder:32b-instruct-q5_K_M" in missing

    def test_parse_local_stage_eval_options(self):
        """Test parsing local stage eval arguments."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-03-stage",
                "--eval-local-stage",
                "website-summary",
                "--eval-working-root",
                "working",
                "--eval-judge-provider",
                "local",
                "--eval-judge-model-list",
                "installed-starter",
                "--eval-local-stage-semantic-judge",
                "--eval-local-stage-semantic-judge-model",
                "llama3.1:70b",
            ]
        )
        assert config.eval_local_stage == "website-summary"
        assert config.eval_working_root == "working"
        assert config.eval_judge_provider == "local"
        assert config.eval_judge_model_list == "installed-starter"
        assert config.eval_stage_semantic_judge is True
        assert config.eval_stage_semantic_judge_model == "llama3.1:70b"

    def test_parse_stage_scorecard_options(self):
        """Test parsing routed-stage scorecard arguments."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-03-stage",
                "--eval-stage-scorecard",
                "--eval-stage-quality",
                "quality.json",
                "--eval-stage-route-root",
                "working",
                "--eval-stage-id",
                "fast.scrape_summary",
                "--eval-stage-min-quality-score",
                "88",
                "--eval-stage-max-failure-rate",
                "0.1",
            ]
        )

        assert config.eval_stage_scorecard is True
        assert config.eval_stage_quality == "quality.json"
        assert config.eval_stage_route_root == "working"
        assert config.eval_stage_id == "fast.scrape_summary"
        assert config.eval_stage_min_quality_score == 88.0
        assert config.eval_stage_max_failure_rate == 0.1

    def test_parse_source_relevance_fixture_eval_option(self):
        """Test parsing source relevance fixture eval arguments."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-03-stage",
                "--eval-source-relevance-fixture",
                ".agent/source-relevance-fixture.json",
            ]
        )

        assert config.eval_source_relevance_fixture == ".agent/source-relevance-fixture.json"

    def test_parse_page_access_fixture_eval_option(self):
        """Test parsing page access fixture eval arguments."""
        config = parse_args(
            [
                "--eval",
                "--eval-id",
                "eval-2026-03-stage",
                "--eval-page-access-fixture",
                ".agent/page-access-fixture.json",
            ]
        )

        assert config.eval_page_access_fixture == ".agent/page-access-fixture.json"

    def test_parse_improve_flag(self):
        """Test parsing --improve flag."""
        config = parse_args(["--improve", "output/demo.md"])
        assert config.command == Command.IMPROVE
        assert config.improve_path == "output/demo.md"

    def test_parse_improve_positional_command(self):
        """Test parsing positional improve command."""
        config = parse_args(["improve", "output/demo.md", "--in-place", "--improve-agentic"])
        assert config.command == Command.IMPROVE
        assert config.improve_path == "output/demo.md"
        assert config.improve_in_place is True
        assert config.improve_agentic is True

    def test_parse_banner_defaults(self):
        """Test banner defaults for normal runs."""
        config = parse_args(["Acme Corp", "acme.example"])
        assert config.banner_mode == "auto"
        assert config.banner_explicit is False

    def test_parse_banner_explicit(self):
        """Test explicit --banner mode."""
        config = parse_args(["--banner"])
        assert config.banner_mode == "animated"
        assert config.banner_explicit is True

    def test_parse_no_banner(self):
        """Test --no-banner override."""
        config = parse_args(["--no-banner", "Acme Corp", "acme.example"])
        assert config.banner_mode == "off"
        assert config.banner_explicit is True

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

    def test_parse_resume_latest(self):
        """Test parsing resume-latest flag."""
        config = parse_args(["--resume-latest"])
        assert config.command == Command.RESUME_LATEST

    def test_parse_resume_jobs_alias(self):
        """Test parsing resume-jobs alias."""
        config = parse_args(["--resume-jobs"])
        assert config.command == Command.RESUME_LATEST

    def test_parse_resume_local_flag(self):
        """Test parsing resume-local flag."""
        config = parse_args(["ExampleCo", "example.co", "--resume-local"])
        assert config.resume_local is True

    def test_parse_generate_vendor(self):
        """Test parsing generate-vendor-research flag."""
        config = parse_args(["--generate-vendor-research", "azure"])
        assert config.command == Command.GENERATE_VENDOR
        assert config.generate_vendor == "azure"
        assert config.skip_confirm is False

    def test_parse_generate_vendor_skip_confirm_is_explicit_approval(self):
        config = parse_args(["--generate-vendor-research", "azure", "--skip-confirm"])
        assert config.skip_confirm is True

    def test_generate_vendor_help_explains_cost_gate_and_supported_targets(self):
        parser = _create_parser()
        action = next(item for item in parser._actions if item.dest == "generate_vendor_research")
        assert "aggregate estimate" in (action.help or "")
        assert "--dry-run" in (action.help or "")
        assert "private" in action.choices

    def test_parse_quiet_flag(self):
        """Test parsing quiet flag."""
        config = parse_args(["Acme Corp", "acme.example", "-q"])
        assert config.quiet is True

    def test_parse_verbose_flag(self):
        """Test parsing verbose flag."""
        config = parse_args(["Acme Corp", "acme.example", "-v"])
        assert config.verbose is True

    def test_batch_requires_confirmation_by_default(self):
        """Test that batch commands require confirmation (skip_confirm=False) by default."""
        config = parse_args(["--batch", "companies.csv"])
        assert config.skip_confirm is False

    def test_batch_skip_confirm_flag(self):
        """Test that --skip-confirm bypasses batch confirmation."""
        config = parse_args(["--batch", "companies.csv", "--skip-confirm"])
        assert config.skip_confirm is True

    def test_single_company_skips_confirm_by_default(self):
        """Test that single-company research skips confirmation by default."""
        config = parse_args(["Acme Corp", "acme.example"])
        assert config.skip_confirm is True

    def test_parse_fast_mode(self):
        """Test parsing --fast flag."""
        config = parse_args(["Acme Corp", "acme.example", "--fast"])
        assert config.fast_mode is True
        assert config.ai_strategy is True  # AI strategy on by default

    def test_parse_fast_with_cloud_vendors(self):
        """Test parsing --fast with --cloud-vendor aws azure."""
        config = parse_args(
            ["Acme Corp", "acme.example", "--fast", "--cloud-vendor", "aws", "azure"]
        )
        assert config.fast_mode is True
        assert config.cloud_vendors == ("aws", "azure")
        assert config.ai_strategy is True

    def test_parse_fast_no_ai_strategy(self):
        """Test parsing --fast --no-ai-strategy."""
        config = parse_args(["Acme Corp", "acme.example", "--fast", "--no-ai-strategy"])
        assert config.fast_mode is True
        assert config.ai_strategy is False

    def test_parse_fast_with_single_vendor(self):
        """Test parsing --fast with single --cloud-vendor."""
        config = parse_args(["Acme Corp", "acme.example", "--fast", "--cloud-vendor", "aws"])
        assert config.fast_mode is True
        assert config.cloud_vendors == ("aws",)
        assert config.cloud_vendor == "aws"

    def test_handle_research_passes_output_dir_and_auto_platform_none(self, tmp_path):
        """Research handler should pass custom output dir and preserve recon auto-detect."""
        config = parse_args(["Acme Corp", "https://acme.example", "--output-dir", "client-output"])

        def successful_run(*_args, **kwargs):
            from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
            from primr.core.vendor_refresh_outcome import (
                VendorRefreshTracker,
                persist_vendor_refresh_outcome,
            )

            kwargs["run_context"]["working_folder"] = str(tmp_path)
            persist_strategy_outcome(str(tmp_path), StrategyOutcomeTracker(()).snapshot())
            persist_vendor_refresh_outcome(str(tmp_path), VendorRefreshTracker(()).snapshot())
            return "report.docx"

        with (
            patch("primr.core.cli._run_preflight_checks", return_value=(True, [])),
            patch(
                "primr.core.cli._run_network_preflight_checks",
                return_value=(True, []),
            ),
            patch(
                "primr.core.research_agent.perform_research", side_effect=successful_run
            ) as mock_research,
            patch.dict(os.environ, {}, clear=True),
        ):
            result = _handle_research(config)

        assert result == 0
        kwargs = mock_research.call_args.kwargs
        assert kwargs["output_dir"] == "client-output"
        assert kwargs["platforms"] is None


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
            mock_doctor.assert_called_once_with(fix=False)

    def test_main_doctor_fix_passes_flag(self):
        """Test main passes --fix through to doctor."""
        with patch("primr.core.cli.run_doctor") as mock_doctor:
            mock_doctor.return_value = 0
            result = main(["doctor", "--fix"])
            assert result == 0
            mock_doctor.assert_called_once_with(fix=True)

    def test_main_init_runs_guided_setup(self):
        """Test main dispatches init to the guided setup flow."""
        with patch("primr.core.cli._run_init_flow") as mock_init:
            mock_init.return_value = 0
            result = main(["init", "--non-interactive", "--skip-browsers", "--no-doctor"])
            assert result == 0
            mock_init.assert_called_once_with(
                non_interactive=True,
                assume_yes=False,
                skip_browsers=True,
                run_doctor_after=False,
            )

    def test_ensure_project_env_file_creates_safe_template(self, tmp_path, monkeypatch):
        """Project .env creation should not activate placeholder secrets."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env.example").write_text("# example\n", encoding="utf-8")

        created, path = _ensure_project_env_file()

        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert created is True
        assert path == str(tmp_path / ".env")
        assert "# GEMINI_API_KEY=" in content
        assert "# XAI_API_KEY=" in content
        assert "GEMINI_API_KEY=your_" not in content

    def test_main_keys_set_writes_user_config(self, tmp_path, monkeypatch):
        """Test keys command writes to the user-level Primr config file."""
        monkeypatch.setenv("PRIMR_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        result = main(["keys", "set", "xai", "unit-test-value"])

        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert result == 0
        assert content.count("XAI_API_KEY=") == 1
        assert "XAI_API_KEY=unit-test-value" in content
        assert os.environ["XAI_API_KEY"] == "unit-test-value"

    def test_main_keys_set_updates_existing_key(self, tmp_path, monkeypatch):
        """Test keys command updates an existing user config key in place."""
        monkeypatch.setenv("PRIMR_CONFIG_DIR", str(tmp_path))
        (tmp_path / ".env").write_text("GEMINI_API_KEY=old-key\n", encoding="utf-8")

        result = main(["keys", "set", "gemini", "--value", "unit-test-value"])

        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert result == 0
        assert "GEMINI_API_KEY=unit-test-value" in content
        assert "old-key" not in content

    def test_main_keys_unset_removes_user_config_key(self, tmp_path, monkeypatch):
        """Test keys unset removes only the user config assignment."""
        monkeypatch.setenv("PRIMR_CONFIG_DIR", str(tmp_path))
        (tmp_path / ".env").write_text(
            "XAI_API_KEY=unit-test-value\nGEMINI_API_KEY=unit-test-value\n",
            encoding="utf-8",
        )

        result = main(["keys", "unset", "xai"])

        content = (tmp_path / ".env").read_text(encoding="utf-8")
        assert result == 0
        assert "XAI_API_KEY=" not in content
        assert "GEMINI_API_KEY=unit-test-value" in content

    def test_main_show_usage(self):
        """Test main with show-usage flag."""
        with patch("primr.utils.usage_tracker.get_usage_tracker") as mock_tracker:
            mock_tracker.return_value.display_usage_history.return_value = "Usage stats"
            result = main(["--show-usage"])
            assert result == 0

    def test_main_list_recent(self):
        """Test main with list-recent flag."""
        with patch("primr.core.cli.list_recent_outputs", return_value=0) as mock_list:
            result = main(["--list-recent"])
            assert result == 0
            mock_list.assert_called_once()

    def test_main_dry_run(self):
        """Test main with dry-run flag."""
        mock_validation = MagicMock(valid=True, errors=[], warnings=[])
        with (
            patch("primr.utils.config_validation.validate_config", return_value=mock_validation),
            patch("primr.utils.cost_estimator.estimate_cost") as mock_estimate,
            patch("primr.core.cli._run_preflight_checks", return_value=(True, [])),
        ):
            mock_estimate.return_value = MagicMock(__str__=lambda x: "Cost estimate")
            result = main(["Acme Corp", "acme.example", "--dry-run"])
            assert result == 0

    def test_main_research_missing_args(self):
        """Test main with missing required args."""
        result = main(["Acme Corp"])  # Missing website
        assert result == 1

    def test_main_banner_only_returns_exit_code(self):
        """Test main with explicit --banner exits cleanly without research args."""
        mock_validation = MagicMock(valid=True, errors=[], warnings=[])
        with (
            patch("primr.utils.config_validation.validate_config", return_value=mock_validation),
            patch("primr.core.cli.maybe_show_startup_banner") as mock_banner,
            patch("primr.core.cli._handle_research") as mock_research,
        ):
            result = main(["--banner"])
            assert result == 0
            mock_banner.assert_called_once()
            mock_research.assert_not_called()


# =============================================================================
# run_doctor Tests
# =============================================================================


class TestRunDoctor:
    """Tests for run_doctor function."""

    def test_doctor_returns_exit_code(self):
        """Test doctor returns appropriate exit code."""
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": ""}),
            patch("primr.core.cli_doctor._check_api_connectivity") as mock_api,
        ):
            mock_api.return_value = (False, 0)
            result = run_doctor()
            # Should fail without API key
            assert result == 1

    def test_doctor_with_valid_config(self):
        """Test doctor with valid configuration."""
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "unit-test-value"}),
            patch("primr.core.cli_doctor._check_dependencies") as mock_deps,
            patch("primr.core.cli_doctor._check_filesystem") as mock_fs,
            patch("primr.core.cli_doctor._check_api_connectivity") as mock_api,
        ):
            mock_deps.return_value = 0
            mock_fs.return_value = (True, 0)
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


# =============================================================================
# Platform Flag Tests (Task 6.5)
# =============================================================================


class TestPlatformFlag:
    """Tests for --platform flag, --skip-recon, ms shorthand, and backward compat."""

    def test_parse_platform_aws(self):
        """Test --platform aws parsing."""
        config = parse_args(["Acme Corp", "acme.example", "--platform", "aws"])
        assert config.platforms == ("aws",)
        assert config.cloud_vendors == ("aws",)
        assert config.cloud_vendor == "aws"

    def test_parse_platform_multiple(self):
        """Test --platform with multiple values."""
        config = parse_args(["Acme Corp", "acme.example", "--platform", "aws", "azure"])
        assert config.platforms == ("aws", "azure")
        assert config.cloud_vendors == ("aws", "azure")

    def test_parse_platform_ms_expansion(self):
        """Test --platform ms expands to azure private."""
        config = parse_args(["Acme Corp", "acme.example", "--platform", "ms"])
        assert config.platforms == ("azure", "private")
        assert config.cloud_vendors == ("azure", "private")
        assert config.cloud_vendor == "azure"

    def test_parse_platform_ms_deduplicates(self):
        """Test --platform ms azure deduplicates azure."""
        config = parse_args(["Acme Corp", "acme.example", "--platform", "ms", "azure"])
        assert config.platforms == ("azure", "private")

    def test_cloud_vendor_deprecation_warning(self, capsys):
        """Test --cloud-vendor emits deprecation warning on stderr."""
        config = parse_args(["Acme Corp", "acme.example", "--cloud-vendor", "aws"])
        captured = capsys.readouterr()
        assert "deprecated" in captured.err.lower()
        assert "--platform" in captured.err
        assert config.platforms == ("aws",)

    def test_platform_cloud_vendor_mutual_exclusion(self):
        """Test --platform and --cloud-vendor cannot be used together."""
        with pytest.raises(SystemExit):
            parse_args(
                ["Acme Corp", "acme.example", "--platform", "aws", "--cloud-vendor", "azure"]
            )

    def test_skip_recon_flag(self):
        """Test --skip-recon flag parsing."""
        config = parse_args(["Acme Corp", "acme.example", "--skip-recon"])
        assert config.skip_recon is True

    def test_skip_recon_default_false(self):
        """Test --skip-recon defaults to False."""
        config = parse_args(["Acme Corp", "acme.example"])
        assert config.skip_recon is False

    def test_no_platform_flag_sets_none(self):
        """Test that omitting --platform sets platforms to None (auto-detect)."""
        config = parse_args(["Acme Corp", "acme.example"])
        assert config.platforms is None

    def test_cloud_vendors_property_default_when_none(self):
        """Test CLIConfig.cloud_vendors returns one agnostic target by default."""
        config = CLIConfig(command=Command.RESEARCH, platforms=None)
        assert config.cloud_vendors == ("agnostic",)
        assert config.cloud_vendor == "agnostic"

    def test_cloud_vendors_property_with_platforms(self):
        """Test CLIConfig.cloud_vendors returns platforms when set."""
        config = CLIConfig(command=Command.RESEARCH, platforms=("aws", "gcp"))
        assert config.cloud_vendors == ("aws", "gcp")
        assert config.cloud_vendor == "aws"

    def test_platform_private_choice(self):
        """Test --platform private is a valid choice."""
        config = parse_args(["Acme Corp", "acme.example", "--platform", "private"])
        assert config.platforms == ("private",)

    def test_platform_agnostic_choice(self):
        """Test --platform agnostic is a valid choice."""
        config = parse_args(["Acme Corp", "acme.example", "--platform", "agnostic"])
        assert config.platforms == ("agnostic",)


# =============================================================================
# Recon Subcommand Tests
# =============================================================================


class TestReconSubcommand:
    """Tests for ``primr recon`` subcommand dispatch."""

    def test_is_recon_command_with_domain(self):
        """Test that 'recon acme.com' is recognized as a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["recon", "acme.com"]) is True

    def test_is_recon_command_doctor(self):
        """Test that 'recon doctor' is recognized as a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["recon", "doctor"]) is True

    def test_is_recon_command_batch(self):
        """Test that 'recon batch domains.txt' is recognized as a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["recon", "batch", "domains.txt"]) is True

    def test_is_recon_command_with_flags(self):
        """Test that 'recon acme.com --json' is recognized as a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["recon", "acme.com", "--json"]) is True

    def test_is_recon_command_bare(self):
        """Test that bare 'recon' is recognized as a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["recon"]) is True

    def test_is_not_recon_command_research(self):
        """Test that a normal research command is not a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["Acme Corp", "acme.example"]) is False

    def test_is_not_recon_command_doctor(self):
        """Test that 'doctor' alone is not a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command(["doctor"]) is False

    def test_is_not_recon_command_empty(self):
        """Test that empty args is not a recon command."""
        from primr.core.cli import _is_recon_command

        assert _is_recon_command([]) is False

    def test_is_not_recon_command_none_uses_sysargv(self):
        """Test that None falls back to sys.argv[1:]."""
        import sys

        from primr.core.cli import _is_recon_command

        saved = sys.argv
        try:
            sys.argv = ["primr", "recon", "acme.com"]
            assert _is_recon_command(None) is True
        finally:
            sys.argv = saved

    @patch("recon_tool.cli.app")
    def test_run_recon_delegates_to_typer_app(self, mock_app):
        """Test that _run_recon delegates to the recon Typer app."""
        from primr.core.cli import _run_recon

        mock_app.return_value = None
        exit_code = _run_recon(["recon", "acme.com"])
        assert exit_code == 0
        mock_app.assert_called_once_with(standalone_mode=False)

    @patch("recon_tool.cli.app")
    def test_run_recon_doctor(self, mock_app):
        """Test that _run_recon handles 'recon doctor'."""
        from primr.core.cli import _run_recon

        mock_app.return_value = None
        exit_code = _run_recon(["recon", "doctor"])
        assert exit_code == 0
        mock_app.assert_called_once()

    @patch("recon_tool.cli.app")
    def test_run_recon_handles_system_exit(self, mock_app):
        """Test that _run_recon handles SystemExit from Typer."""
        from primr.core.cli import _run_recon

        mock_app.side_effect = SystemExit(2)
        exit_code = _run_recon(["recon", "acme.com"])
        assert exit_code == 2

    @patch("recon_tool.cli.app")
    def test_run_recon_handles_exception(self, mock_app):
        """Test that _run_recon handles unexpected exceptions."""
        from primr.core.cli import _run_recon

        mock_app.side_effect = RuntimeError("boom")
        exit_code = _run_recon(["recon", "acme.com"])
        assert exit_code == 1

    @patch("primr.core.cli._run_recon", return_value=0)
    def test_main_dispatches_recon(self, mock_run_recon):
        """Test that main() dispatches to _run_recon for recon commands."""
        exit_code = main(["recon", "acme.com"])
        assert exit_code == 0
        mock_run_recon.assert_called_once_with(["recon", "acme.com"])

    @patch("primr.core.cli._run_recon", return_value=0)
    def test_main_dispatches_recon_with_flags(self, mock_run_recon):
        """Test that main() dispatches recon with output format flags."""
        exit_code = main(["recon", "acme.com", "--json"])
        assert exit_code == 0
        mock_run_recon.assert_called_once_with(["recon", "acme.com", "--json"])

    @patch("primr.core.cli._run_recon", return_value=0)
    def test_main_dispatches_recon_md_flag(self, mock_run_recon):
        """Test that main() dispatches recon with --md flag."""
        exit_code = main(["recon", "acme.com", "--md"])
        assert exit_code == 0
        mock_run_recon.assert_called_once_with(["recon", "acme.com", "--md"])

    @patch("primr.core.cli._run_recon", return_value=0)
    def test_main_dispatches_recon_batch(self, mock_run_recon):
        """Test that main() dispatches recon batch mode."""
        exit_code = main(["recon", "batch", "domains.txt"])
        assert exit_code == 0
        mock_run_recon.assert_called_once_with(["recon", "batch", "domains.txt"])
