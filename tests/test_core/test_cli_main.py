"""Unit tests for primr.core.cli.main dispatch."""

from __future__ import annotations

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
