"""Unit tests for parse_args in primr.core.cli.

Exercises the argument-parsing pathways: positional args, flag aliases,
platform expansion, banner mode, mode resolution, skip-confirm defaults,
continuous-reasoning toggle.
"""

from __future__ import annotations

from primr.core.cli import Command, parse_args


class TestPositionalArgs:
    def test_company_and_website(self):
        config = parse_args(["Acme Corp", "https://acme.example"])
        assert config.company_name == "Acme Corp"
        assert config.website == "https://acme.example"
        assert config.command == Command.RESEARCH

    def test_doctor_positional_routes_to_doctor(self):
        config = parse_args(["doctor"])
        assert config.command == Command.DOCTOR

    def test_init_positional_routes_to_init(self):
        config = parse_args(["init"])
        assert config.command == Command.INIT


class TestPlatformExpansion:
    def test_alias_microsoft_becomes_azure(self):
        config = parse_args(["Acme", "https://acme.example", "--platform", "microsoft"])
        assert config.platforms == ("azure",)

    def test_alias_amazon_becomes_aws(self):
        config = parse_args(["Acme", "https://acme.example", "--platform", "amazon"])
        assert config.platforms == ("aws",)

    def test_alias_google_becomes_gcp(self):
        config = parse_args(["Acme", "https://acme.example", "--platform", "google"])
        assert config.platforms == ("gcp",)

    def test_ms_shorthand_expands_to_azure_and_private(self):
        config = parse_args(["Acme", "https://acme.example", "--platform", "ms"])
        assert config.platforms == ("azure", "private")

    def test_multiple_platforms_dedup(self):
        config = parse_args(["Acme", "https://acme.example", "--platform", "aws", "azure", "aws"])
        assert config.platforms == ("aws", "azure")


class TestModeResolution:
    def test_default_mode(self):
        config = parse_args(["Acme", "https://acme.example"])
        # Default mode is "complete" or similar
        assert config.mode is not None


class TestBannerMode:
    def test_default_is_auto(self):
        config = parse_args(["Acme", "https://acme.example"])
        assert config.banner_mode == "auto"
        assert config.banner_explicit is False

    def test_no_banner_sets_off(self):
        config = parse_args(["Acme", "https://acme.example", "--no-banner"])
        assert config.banner_mode == "off"
        assert config.banner_explicit is True


class TestContinuousReasoning:
    def test_default_is_on(self):
        config = parse_args(["Acme", "https://acme.example"])
        assert config.continuous_reasoning is True

    def test_no_continuous_reasoning_disables(self):
        config = parse_args(["Acme", "https://acme.example", "--no-continuous-reasoning"])
        assert config.continuous_reasoning is False


class TestSkipConfirm:
    def test_non_batch_skips_confirm_by_default(self):
        config = parse_args(["Acme", "https://acme.example"])
        # Non-batch commands skip confirmation by default
        assert config.skip_confirm is True

    def test_batch_requires_confirm_by_default(self, tmp_path):
        # Create a fake batch file so argparse path-check passes
        batch_file = tmp_path / "fake.csv"
        batch_file.write_text("company\nAcme\n")
        config = parse_args(["--batch", str(batch_file)])
        # Batch commands require confirmation unless --skip-confirm is passed
        assert config.skip_confirm is False

    def test_batch_skip_confirm_flag_honored(self, tmp_path):
        batch_file = tmp_path / "fake.csv"
        batch_file.write_text("company\nAcme\n")
        config = parse_args(["--batch", str(batch_file), "--skip-confirm"])
        assert config.skip_confirm is True


class TestFlagCommands:
    def test_list_recent_command(self):
        config = parse_args(["--list-recent"])
        assert config.command == Command.LIST_RECENT

    def test_clean_temp_command(self):
        config = parse_args(["--clean-temp"])
        assert config.command == Command.CLEAN_TEMP

    def test_check_jobs_command(self):
        config = parse_args(["--check-jobs"])
        assert config.command == Command.CHECK_JOBS

    def test_resume_latest_command(self):
        config = parse_args(["--resume-latest"])
        assert config.command == Command.RESUME_LATEST

    def test_show_usage_command(self):
        config = parse_args(["--show-usage"])
        assert config.command == Command.SHOW_USAGE

    def test_list_strategies_command(self):
        config = parse_args(["--list-strategies"])
        assert config.command == Command.LIST_STRATEGIES

    def test_dry_run_command(self):
        config = parse_args(["Acme", "https://acme.example", "--dry-run"])
        assert config.command == Command.DRY_RUN


class TestPremiumMode:
    def test_mode_premium_sets_premium_mode(self):
        # --mode premium is documented as the Gemini + Deep Research pipeline,
        # so it must enable premium_mode (it maps to the "complete" internal mode).
        config = parse_args(["Acme", "https://acme.example", "--mode", "premium"])
        assert config.premium_mode is True
        assert config.mode == "complete"

    def test_premium_flag_sets_premium_mode(self):
        config = parse_args(["Acme", "https://acme.example", "--premium"])
        assert config.premium_mode is True

    def test_full_mode_does_not_set_premium(self):
        config = parse_args(["Acme", "https://acme.example", "--mode", "full"])
        assert config.premium_mode is False


class TestBudgetFlag:
    def test_budget_maps_to_config(self):
        config = parse_args(["Acme", "https://acme.example", "--budget", "1.50"])
        assert config.budget_usd == 1.50

    def test_budget_defaults_to_none(self):
        config = parse_args(["Acme", "https://acme.example"])
        assert config.budget_usd is None


class TestResearchFramingArgs:
    """Tradecraft Step 1b: framing flags parse into CLIConfig, and the
    research-input flags moved into cli_parser still work (regression)."""

    def test_framing_flags_map_to_config(self):
        config = parse_args(
            [
                "Acme",
                "https://acme.example",
                "--purpose",
                "diligence",
                "--audience",
                "the IC",
                "--decision",
                "go / no-go",
                "--question",
                "durable moat?",
            ]
        )
        assert config.framing_purpose == "diligence"
        assert config.framing_audience == "the IC"
        assert config.framing_decision == "go / no-go"
        assert config.framing_question == "durable moat?"

    def test_framing_flags_default_none(self):
        config = parse_args(["Acme", "https://acme.example"])
        assert config.framing_purpose is None
        assert config.framing_audience is None
        assert config.framing_decision is None
        assert config.framing_question is None

    def test_strategy_type_still_parses(self):
        config = parse_args(["Acme", "https://acme.example", "--strategy-type", "ai"])
        assert config.strategy_type == "ai"

    def test_strategy_type_defaults_to_ai(self):
        config = parse_args(["Acme", "https://acme.example"])
        assert config.strategy_type == "ai"

    def test_discovery_notes_still_parses(self):
        config = parse_args(["Acme", "https://acme.example", "--discovery-notes", "notes.md"])
        assert config.discovery_notes_path == "notes.md"

    def test_context_still_parses(self):
        config = parse_args(["Acme", "https://acme.example", "--context", "a.md", "b.md"])
        assert config.context_files == ("a.md", "b.md")


class TestJsonFlag:
    def test_json_flag_maps_to_config(self):
        config = parse_args(["Acme", "https://acme.example", "--json"])
        assert config.json_output is True

    def test_json_defaults_false(self):
        config = parse_args(["Acme", "https://acme.example"])
        assert config.json_output is False

    def test_dry_run_json_emits_estimate(self, capsys):
        import json

        from primr.core.cli_dryrun import run_dry_run

        config = parse_args(["Acme", "https://acme.example", "--dry-run", "--json", "--fast"])
        rc = run_dry_run(config)
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)  # stdout must be pure JSON
        assert "total_cost" in payload
        assert payload["mode_label"].startswith("standard")

    def test_dry_run_json_includes_budget_policy_when_budget_is_set(self, capsys):
        import json

        from primr.core.cli_dryrun import run_dry_run

        config = parse_args(
            ["Acme", "https://acme.example", "--dry-run", "--json", "--premium", "--budget", "5"]
        )
        rc = run_dry_run(config)

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["budget_enforcement"]["runtime_checkpoints"] is True
        assert payload["budget_enforcement"]["checkpointed_stages"] == [
            "optional strategy generation"
        ]
        assert (
            "required Deep Research task cannot be stopped"
            in payload["budget_enforcement"]["runtime"]
        )
