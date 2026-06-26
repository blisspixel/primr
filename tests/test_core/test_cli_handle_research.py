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


class TestBudgetGate:
    """--budget pre-flight gate and run-budget activation."""

    @pytest.fixture(autouse=True)
    def _valid_inputs(self, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        from primr.utils.run_budget import clear_run_budget

        clear_run_budget()
        yield
        clear_run_budget()

    def test_non_positive_budget_returns_1(self, passing_preflight, perform_research_ok):
        assert _handle_research(_config(premium_mode=True, budget_usd=0.0)) == 1
        perform_research_ok.assert_not_called()

    def test_estimate_over_budget_refuses_to_start(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        from types import SimpleNamespace

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=5.00)),
        )
        assert _handle_research(_config(premium_mode=True, budget_usd=1.00)) == 1
        perform_research_ok.assert_not_called()

    def test_estimate_within_budget_runs_and_clears(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        from types import SimpleNamespace

        from primr.utils.run_budget import get_run_budget

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.79)),
        )

        seen = {}

        def record_active_budget(*args, **kwargs):
            seen["budget"] = get_run_budget()
            return "/fake/path/report.docx"

        monkeypatch.setattr("primr.core.research_agent.perform_research", record_active_budget)

        assert _handle_research(_config(premium_mode=True, budget_usd=2.00)) == 0
        # Budget was active during the run...
        assert seen["budget"] is not None
        assert seen["budget"].max_cost == 2.00
        # ...and cleared afterwards
        assert get_run_budget() is None

    def test_estimate_only_budget_warning_for_premium_path(self, passing_preflight, monkeypatch):
        from types import SimpleNamespace

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.79)),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(return_value="/fake/path/report.docx"),
        )
        warn = MagicMock()
        monkeypatch.setattr("primr.core.cli_budget.console.warn", warn)

        assert _handle_research(_config(premium_mode=True, budget_usd=2.00)) == 0

        assert any("estimate-gated only" in call.args[0] for call in warn.call_args_list)

    def test_budget_cleared_even_when_research_raises(self, passing_preflight, monkeypatch):
        from types import SimpleNamespace

        from primr.utils.run_budget import get_run_budget

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.50)),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(side_effect=RuntimeError("boom")),
        )

        with pytest.raises(RuntimeError):
            _handle_research(_config(premium_mode=True, budget_usd=2.00))
        assert get_run_budget() is None

    def test_no_budget_flag_means_no_active_budget(self, passing_preflight, perform_research_ok):
        from primr.utils.run_budget import get_run_budget

        assert _handle_research(_config(premium_mode=True)) == 0
        assert get_run_budget() is None
