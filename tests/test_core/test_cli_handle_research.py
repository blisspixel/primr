"""Unit tests for _handle_research in primr.core.cli.

Mocks perform_research, preflight checks, and context-file validation
to exercise each early-return branch and the mode-resolution logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command, _handle_research


def _config(**overrides):
    defaults = {
        "command": Command.RESEARCH,
        "company_name": "Acme Corp",
        "website": "https://acme.example",
        "mode": "complete",
        "skip_confirm": True,
        "skip_recon": True,
    }
    defaults.update(overrides)
    return CLIConfig(**defaults)


@pytest.fixture
def passing_preflight(monkeypatch):
    """Make _run_preflight_checks always return (True, [])."""
    monkeypatch.setattr(
        "primr.core.cli._run_preflight_checks",
        MagicMock(return_value=(True, [])),
    )


@pytest.fixture
def perform_research_ok(monkeypatch):
    """Stub perform_research to return a fake path."""
    mock = MagicMock(return_value="/fake/path/report.docx")
    monkeypatch.setattr("primr.core.research_agent.perform_research", mock)
    return mock


class TestEarlyValidation:
    def test_no_company_returns_1(self, passing_preflight):
        result = _handle_research(_config(company_name=None))
        assert result == 1

    def test_no_website_returns_1(self, passing_preflight):
        result = _handle_research(_config(website=None))
        assert result == 1

    def test_invalid_company_name_returns_1(self, passing_preflight, monkeypatch):
        from primr.utils.validators import InputValidationError

        def reject(_name):
            raise InputValidationError(field="company_name", reason="too long")

        monkeypatch.setattr("primr.utils.validators.validate_company_name", reject)
        assert _handle_research(_config(company_name="x" * 1000)) == 1

    def test_invalid_website_returns_1(self, passing_preflight, monkeypatch):
        from primr.utils.validators import InputValidationError

        monkeypatch.setattr(
            "primr.utils.validators.validate_company_name",
            lambda x: x,
        )

        def reject_url(_url):
            raise InputValidationError(field="website", reason="bad scheme")

        monkeypatch.setattr("primr.utils.validators.validate_url", reject_url)
        assert _handle_research(_config(website="ftp://bad")) == 1


class TestPreflightFailures:
    def test_failed_preflight_returns_1(self, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.setattr(
            "primr.core.cli._run_preflight_checks",
            MagicMock(return_value=(False, ["missing API key"])),
        )
        assert _handle_research(_config()) == 1


class TestModeIncompatibilities:
    def test_fast_and_premium_together_returns_1(self, passing_preflight, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        assert _handle_research(_config(fast_mode=True, premium_mode=True)) == 1

    def test_premium_with_wrong_mode_returns_1(self, passing_preflight, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        assert _handle_research(_config(premium_mode=True, mode="scrape-only")) == 1

    def test_fast_with_wrong_mode_returns_1(self, passing_preflight, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        assert _handle_research(_config(fast_mode=True, mode="scrape-only")) == 1

    def test_fast_without_xai_key_returns_1(self, passing_preflight, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        assert _handle_research(_config(fast_mode=True, mode="complete")) == 1


class TestSuccessPath:
    def test_returns_zero_when_research_succeeds(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        # Avoid the fast-mode preflight by passing premium_mode=True
        result = _handle_research(_config(premium_mode=True))
        assert result == 0
        perform_research_ok.assert_called_once()

    def test_returns_one_when_research_returns_none(self, passing_preflight, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        mock = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.research_agent.perform_research", mock)
        assert _handle_research(_config(premium_mode=True)) == 1

    def test_opens_file_when_open_after_set(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        open_mock = MagicMock()
        monkeypatch.setattr("primr.core.cli.open_file", open_mock)
        _handle_research(_config(premium_mode=True, open_after=True))
        open_mock.assert_called_once_with("/fake/path/report.docx")


class TestContextFiles:
    def test_invalid_context_file_returns_1(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)

        result_obj = MagicMock()
        result_obj.invalid_files = [("bad.txt", "not found")]
        result_obj.valid_files = []
        result_obj.warnings = []
        monkeypatch.setattr(
            "primr.core.workspace.validate_context_files",
            MagicMock(return_value=result_obj),
        )
        result = _handle_research(_config(premium_mode=True, context_files=("bad.txt",)))
        assert result == 1
        perform_research_ok.assert_not_called()

    def test_context_folder_consolidation_failure_returns_1(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.setattr(
            "primr.core.workspace.consolidate_working_folder",
            MagicMock(side_effect=ValueError("folder missing")),
        )
        result = _handle_research(_config(premium_mode=True, context_folder="/some/folder"))
        assert result == 1
