"""Unit tests for primr.core.cli.main dispatch."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from primr.core.cli import main


@pytest.fixture
def passing_validation(monkeypatch):
    """Make validate_config always pass."""
    result = MagicMock()
    result.valid = True
    result.errors = []
    monkeypatch.setattr("primr.utils.config_validation.validate_config", lambda **kw: result)
    monkeypatch.setattr("primr.utils.config_validation.reset_config", lambda: None)


@pytest.fixture
def stub_logging(monkeypatch):
    """Skip log setup side effects."""
    monkeypatch.setattr("primr.utils.logging_config.setup_logging", lambda **kw: None)


class TestMainDispatch:
    def test_recon_subcommand_dispatches(self, monkeypatch):
        recon_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._run_recon", recon_mock)
        result = main(["recon", "acme.example"])
        assert result == 0
        recon_mock.assert_called_once()

    def test_keys_subcommand_dispatches(self, monkeypatch):
        keys_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.run_keys", keys_mock)
        result = main(["keys", "list"])
        assert result == 0
        keys_mock.assert_called_once()

    def test_mcp_subcommand_dispatches(self, monkeypatch):
        mcp_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.run_mcp", mcp_mock)
        result = main(["mcp"])
        assert result == 0
        mcp_mock.assert_called_once()


class TestMainHandlerRouting:
    def test_doctor_routes_to_handler(self, passing_validation, stub_logging, monkeypatch):
        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._handle_doctor", handler)
        result = main(["doctor"])
        assert result == 0
        handler.assert_called_once()

    def test_init_routes_to_handler(self, passing_validation, stub_logging, monkeypatch):
        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._handle_init", handler)
        assert main(["init"]) == 0

    def test_list_recent_routes(self, passing_validation, stub_logging, monkeypatch):
        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._handle_list_recent", handler)
        assert main(["--list-recent"]) == 0

    def test_list_strategies_routes(self, passing_validation, stub_logging, monkeypatch):
        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._handle_list_strategies", handler)
        assert main(["--list-strategies"]) == 0

    def test_show_usage_routes(self, passing_validation, stub_logging, monkeypatch):
        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._handle_show_usage", handler)
        assert main(["--show-usage"]) == 0

    def test_vendor_json_stays_one_object_when_provider_reports_progress(
        self, passing_validation, stub_logging, monkeypatch, capsys
    ):
        from primr.utils.console import get_console, set_console

        original_console = get_console()
        monkeypatch.setattr("primr.utils.banner.maybe_show_startup_banner", lambda **kw: None)
        monkeypatch.setattr(
            "primr.core.vendor_research._validate_vendor_research_preflight",
            lambda _vendor: [],
        )

        def generate(vendor, *, emit_console):
            assert emit_console is False
            if emit_console:
                get_console().error(f"PROGRESS-{vendor}")
            return f"/cache/{vendor}.md"

        monkeypatch.setattr(
            "primr.core.vendor_research.generate_vendor_research_sync",
            generate,
        )
        try:
            result = main(
                [
                    "--generate-vendor-research",
                    "aws",
                    "--json",
                    "--skip-confirm",
                ]
            )
        finally:
            set_console(original_console)

        payload = json.loads(capsys.readouterr().out)
        assert result == 0
        assert payload["status"] == "completed"
        assert payload["artifacts"] == [{"vendor": "aws", "path": "/cache/aws.md"}]

    def test_invalid_configuration_json_is_one_structured_error(self, monkeypatch, capsys):
        result = MagicMock(valid=False, errors=["provider key missing"])
        monkeypatch.setattr(
            "primr.utils.config_validation.validate_config",
            lambda **_kwargs: result,
        )

        assert main(["Acme Corp", "https://acme.example", "--json"]) == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["operation"] == "research"
        assert payload["error_type"] == "configuration_invalid"
        assert payload["hints"] == ["provider key missing"]

    @pytest.mark.parametrize(
        ("gemini_key", "expected_hint"),
        [
            (None, "GEMINI_API_KEY not configured"),
            ("short", "GEMINI_API_KEY appears invalid (too short)"),
        ],
    )
    def test_vendor_json_invalid_key_is_one_structured_error(
        self,
        passing_validation,
        stub_logging,
        monkeypatch,
        capsys,
        gemini_key,
        expected_hint,
    ):
        from primr.config.settings import reset_settings
        from primr.utils.console import get_console, set_console

        original_console = get_console()
        generate = MagicMock()
        if gemini_key is None:
            monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        else:
            monkeypatch.setenv("GEMINI_API_KEY", gemini_key)
        reset_settings()
        monkeypatch.setattr("primr.utils.banner.maybe_show_startup_banner", lambda **kw: None)
        monkeypatch.setattr(
            "primr.core.vendor_research.check_dir_atomic_writable",
            lambda _path: (True, None),
        )
        monkeypatch.setattr(
            "primr.core.vendor_research.generate_vendor_research_sync",
            generate,
        )
        try:
            result = main(["--generate-vendor-research", "aws", "--json"])
        finally:
            reset_settings()
            set_console(original_console)

        payload = json.loads(capsys.readouterr().out)
        assert result == 1
        assert payload["error_type"] == "preflight_failed"
        assert payload["hints"] == [expected_hint]
        generate.assert_not_called()

    def test_calibration_decision_bypasses_api_key_validation(self, stub_logging, monkeypatch):
        validation_calls = []

        def validate_config(**kwargs):
            validation_calls.append(kwargs)
            result = MagicMock()
            result.valid = True
            result.errors = []
            result.warnings = []
            return result

        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.utils.config_validation.validate_config", validate_config)
        monkeypatch.setattr("primr.utils.config_validation.reset_config", lambda: None)
        monkeypatch.setattr("primr.core.cli._handle_calibrate", handler)

        assert (
            main(
                [
                    "calibrate",
                    "--baseline-decision-from",
                    "baseline.json",
                    "--baseline-decision-out",
                    "decision.json",
                    "--baseline-decision",
                    "keep_report_only",
                    "--baseline-decision-reviewer",
                    "qa-owner",
                    "--baseline-decision-rationale",
                    "Keep report-only after review.",
                ]
            )
            == 0
        )
        assert validation_calls[0]["include_api_keys"] is False
        handler.assert_called_once()

    def test_calibration_decision_inspection_bypasses_api_key_validation(
        self, stub_logging, monkeypatch
    ):
        validation_calls = []

        def validate_config(**kwargs):
            validation_calls.append(kwargs)
            result = MagicMock()
            result.valid = True
            result.errors = []
            result.warnings = []
            return result

        handler = MagicMock(return_value=0)
        monkeypatch.setattr("primr.utils.config_validation.validate_config", validate_config)
        monkeypatch.setattr("primr.utils.config_validation.reset_config", lambda: None)
        monkeypatch.setattr("primr.core.cli._handle_calibrate", handler)

        assert main(["calibrate", "--inspect-baseline-decision", "decision.json"]) == 0
        assert validation_calls[0]["include_api_keys"] is False
        handler.assert_called_once()


class TestMainValidationFailure:
    def test_invalid_config_returns_1(self, stub_logging, monkeypatch):
        result = MagicMock()
        result.valid = False
        result.errors = ["bad config"]
        monkeypatch.setattr("primr.utils.config_validation.validate_config", lambda **kw: result)
        # Make non-interactive so we don't get into the prompt path
        monkeypatch.setattr(
            "primr.core.cli._should_offer_interactive_key_setup",
            lambda r: False,
        )
        assert main(["doctor"]) == 1


class TestBannerOnlyMode:
    def test_banner_with_no_args_returns_0(self, passing_validation, stub_logging, monkeypatch):
        monkeypatch.setattr("primr.utils.banner.maybe_show_startup_banner", lambda **kw: None)
        result = main(["--banner", "static"])
        assert result == 0
