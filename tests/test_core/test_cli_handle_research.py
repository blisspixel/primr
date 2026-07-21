"""Unit tests for _handle_research in primr.core.cli.

Mocks perform_research, preflight checks, and context-file validation
to exercise each early-return branch and the mode-resolution logic.
"""

from __future__ import annotations

import json
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
    """Make local and network preflight checks pass without external calls."""
    network = MagicMock(return_value=(True, []))
    monkeypatch.setattr(
        "primr.core.cli._run_preflight_checks",
        MagicMock(return_value=(True, [])),
    )
    monkeypatch.setattr("primr.core.cli._run_network_preflight_checks", network)
    return network


@pytest.fixture
def perform_research_ok(monkeypatch, tmp_path):
    """Stub a successful run with the same outcome state as production."""
    from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
    from primr.core.vendor_refresh_outcome import (
        VendorRefreshTracker,
        persist_vendor_refresh_outcome,
    )

    def successful_run(*_args, **kwargs):
        kwargs["run_context"]["working_folder"] = str(tmp_path)
        persist_strategy_outcome(str(tmp_path), StrategyOutcomeTracker(()).snapshot())
        persist_vendor_refresh_outcome(str(tmp_path), VendorRefreshTracker(()).snapshot())
        return "/fake/path/report.docx"

    mock = MagicMock(side_effect=successful_run)
    monkeypatch.setattr("primr.core.research_agent.perform_research", mock)
    return mock


class TestEarlyValidation:
    def test_no_company_returns_1(self, passing_preflight):
        result = _handle_research(_config(company_name=None))
        assert result == 1

    def test_no_website_returns_1(self, passing_preflight):
        result = _handle_research(_config(website=None))
        assert result == 1

    @pytest.mark.parametrize("missing", ["company_name", "website"])
    def test_missing_inputs_json_is_one_error_object(self, missing, capsys):
        result = _handle_research(_config(json_output=True, **{missing: None}))

        assert result == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "schema_version": "primr.command-error.v1",
            "operation": "research",
            "error": True,
            "error_type": "missing_research_input",
            "message": "Both company name and website are required",
            "hints": [
                'Usage: primr "Company Name" https://company.com',
                "Run 'primr doctor' to check system configuration",
            ],
        }

    def test_human_missing_inputs_preserves_guidance(self, capsys):
        assert _handle_research(_config(company_name=None)) == 1

        output = capsys.readouterr().out
        assert "Both company name and website are required" in output
        assert 'Usage: primr "Company Name" https://company.com' in output
        assert "primr doctor" in output

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

    @pytest.mark.parametrize("field", ["company", "website"])
    def test_invalid_inputs_json_is_one_error_object(self, field, monkeypatch, capsys):
        from primr.utils.validators import InputValidationError

        if field == "company":
            monkeypatch.setattr(
                "primr.utils.validators.validate_company_name",
                MagicMock(side_effect=InputValidationError(field="company_name", reason="bad")),
            )
        else:
            monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda value: value)
            monkeypatch.setattr(
                "primr.utils.validators.validate_url",
                MagicMock(side_effect=InputValidationError(field="website", reason="bad")),
            )

        assert _handle_research(_config(json_output=True)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["error"] is True
        assert (
            payload["error_type"]
            == f"invalid_{'company_name' if field == 'company' else 'website_url'}"
        )


class TestPreflightFailures:
    def test_failed_preflight_returns_1(self, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.setattr(
            "primr.core.cli._run_preflight_checks",
            MagicMock(return_value=(False, ["missing API key"])),
        )
        assert _handle_research(_config()) == 1

    def test_preflight_failure_json_is_one_error_object(self, monkeypatch, capsys):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda value: value)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda value: value)
        monkeypatch.setattr(
            "primr.core.cli._run_preflight_checks",
            MagicMock(return_value=(False, ["missing provider"])),
        )

        assert _handle_research(_config(json_output=True)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["error_type"] == "preflight_failed"
        assert payload["hints"][0] == "missing provider"


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

    def test_fast_without_xai_key_returns_1(self, monkeypatch):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.setattr(
            "primr.core.cli._run_preflight_checks",
            MagicMock(return_value=(False, ["XAI_API_KEY not configured"])),
        )
        assert _handle_research(_config(fast_mode=True, mode="complete")) == 1

    def test_mode_conflict_json_skips_preflight(self, monkeypatch, capsys):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda value: value)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda value: value)
        preflight = MagicMock()
        monkeypatch.setattr("primr.core.cli._run_preflight_checks", preflight)

        assert _handle_research(_config(json_output=True, fast_mode=True, premium_mode=True)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["error_type"] == "incompatible_mode_options"
        preflight.assert_not_called()

    @pytest.mark.parametrize(
        "overrides",
        [
            {"strategy_type": "customer_experience"},
            {"platforms": ("aws", "azure")},
        ],
    )
    def test_nonfast_structured_unsupported_shape_skips_preflight(
        self, monkeypatch, capsys, overrides
    ):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda value: value)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda value: value)
        preflight = MagicMock()
        monkeypatch.setattr("primr.core.cli._run_preflight_checks", preflight)

        assert (
            _handle_research(
                _config(
                    json_output=True,
                    mode="structured",
                    **overrides,
                )
            )
            == 1
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_type"] == "unsupported_strategy_runtime"
        preflight.assert_not_called()

    def test_inference_pair_json_is_one_error_object(self, monkeypatch, capsys):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda value: value)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda value: value)

        assert (
            _handle_research(_config(json_output=True, acknowledge_host_agent_may_bill=True)) == 1
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["error_type"] == "invalid_inference_options"


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

    def test_partial_strategy_returns_nonzero_with_completed_report_json(
        self, passing_preflight, monkeypatch, tmp_path, capsys
    ):
        from primr.core.strategy_outcome import (
            StrategyOutcomeTracker,
            persist_strategy_outcome,
        )
        from primr.core.vendor_refresh_outcome import (
            VendorRefreshTracker,
            persist_vendor_refresh_outcome,
        )

        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        report = tmp_path / "report.md"
        report.write_text("base report", encoding="utf-8")

        def partial_run(*_args, **kwargs):
            kwargs["run_context"]["working_folder"] = str(tmp_path)
            tracker = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
            tracker.mark_completed("ai:azure")
            persist_strategy_outcome(str(tmp_path), tracker.snapshot())
            persist_vendor_refresh_outcome(str(tmp_path), VendorRefreshTracker(()).snapshot())
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_research", partial_run)

        assert _handle_research(_config(premium_mode=True, json_output=True)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "completed"
        assert payload["report_path"] == str(report.resolve())
        assert payload["strategy_status"] == "partial"
        assert payload["strategy_completed_targets"] == ["ai:azure"]
        assert payload["strategy_failed_targets"] == ["ai:aws"]
        assert payload["fulfillment_status"] == "partial"
        assert payload["outcome_state_status"] == "available"

    def test_partial_explicit_vendor_refresh_returns_nonzero_with_report_json(
        self, passing_preflight, monkeypatch, tmp_path, capsys
    ):
        from primr.core.strategy_outcome import (
            StrategyOutcomeTracker,
            persist_strategy_outcome,
        )
        from primr.core.vendor_refresh_outcome import (
            VendorRefreshTracker,
            persist_vendor_refresh_outcome,
        )

        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        report = tmp_path / "report.md"
        report.write_text("base report", encoding="utf-8")

        def partial_refresh(*_args, **kwargs):
            kwargs["run_context"]["working_folder"] = str(tmp_path)
            strategy = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
            strategy.mark_completed("ai:azure")
            strategy.mark_completed("ai:aws")
            persist_strategy_outcome(str(tmp_path), strategy.snapshot())
            refresh = VendorRefreshTracker(("azure", "aws"))
            refresh.observe("azure", "started")
            refresh.observe("azure", "completed")
            refresh.observe("aws", "started")
            refresh.observe("aws", "failed")
            persist_vendor_refresh_outcome(str(tmp_path), refresh.snapshot())
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_research", partial_refresh)

        assert (
            _handle_research(
                _config(
                    premium_mode=True,
                    json_output=True,
                    refresh_vendor_research=True,
                    platforms=("azure", "aws"),
                )
            )
            == 1
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "completed"
        assert payload["strategy_status"] == "completed"
        assert payload["vendor_refresh_status"] == "partial"
        assert payload["vendor_refresh_failed"] == ["aws"]
        assert payload["fulfillment_status"] == "partial"

    def test_partial_strategy_human_handoff_names_targets_and_state(
        self, passing_preflight, monkeypatch, tmp_path, capsys
    ):
        from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
        from primr.core.vendor_refresh_outcome import (
            VendorRefreshTracker,
            persist_vendor_refresh_outcome,
        )

        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        report = tmp_path / "report.docx"
        report.write_bytes(b"PK\x03\x04")

        def partial_run(*_args, **kwargs):
            kwargs["run_context"]["working_folder"] = str(tmp_path)
            strategy = StrategyOutcomeTracker(("ai:azure", "ai:aws"))
            strategy.mark_completed("ai:azure")
            strategy.mark_skipped("ai:aws")
            persist_strategy_outcome(str(tmp_path), strategy.snapshot())
            persist_vendor_refresh_outcome(str(tmp_path), VendorRefreshTracker(()).snapshot())
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_research", partial_run)

        assert _handle_research(_config(premium_mode=True)) == 1
        output = capsys.readouterr().out
        assert "Strategy fulfillment PARTIAL" in output
        assert "Completed: ai:azure" in output
        assert "Skipped: ai:aws" in output
        assert str(tmp_path / "_run_state.json") in output
        assert "fresh dry-run" in output

    def test_unreadable_outcome_state_fails_closed_with_json_detail(
        self, passing_preflight, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        report = tmp_path / "report.docx"
        report.write_bytes(b"PK\x03\x04\x80\xff")

        def run_without_state(*_args, **kwargs):
            kwargs["run_context"]["working_folder"] = str(tmp_path)
            return str(report)

        monkeypatch.setattr("primr.core.research_agent.perform_research", run_without_state)

        assert _handle_research(_config(premium_mode=True, json_output=True)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "completed"
        assert payload["fulfillment_status"] == "unknown"
        assert payload["outcome_state_status"] == "unavailable"
        assert payload["run_state_path"] == str((tmp_path / "_run_state.json").resolve())
        assert payload["word_count"] is None

    def test_busy_company_is_actionable_without_traceback(
        self, passing_preflight, monkeypatch, capsys
    ):
        from primr.core.workspace import ActiveRunLeaseError

        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(side_effect=ActiveRunLeaseError("active company run")),
        )

        assert _handle_research(_config(premium_mode=True)) == 1
        output = capsys.readouterr().out
        assert "active company run" in output
        assert "Wait for the active run to finish" in output
        assert "Traceback" not in output

    @pytest.mark.parametrize(
        "exception_name,expected_type",
        [
            ("active", "active_run"),
            ("workspace", "workspace_lease"),
        ],
    )
    def test_workspace_lease_failures_are_one_json_object(
        self,
        passing_preflight,
        monkeypatch,
        capsys,
        exception_name,
        expected_type,
    ):
        from primr.core.workspace import ActiveRunLeaseError, ResumeLeaseError

        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda value: value)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda value: value)
        failure = (
            ActiveRunLeaseError("active run")
            if exception_name == "active"
            else ResumeLeaseError("workspace unavailable")
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(side_effect=failure),
        )

        assert _handle_research(_config(premium_mode=True, json_output=True)) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema_version"] == "primr.command-error.v1"
        assert payload["error_type"] == expected_type

    def test_opens_file_when_open_after_set(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        open_mock = MagicMock()
        monkeypatch.setattr("primr.core.cli.open_file", open_mock)
        _handle_research(_config(premium_mode=True, open_after=True))
        open_mock.assert_called_once_with("/fake/path/report.docx")

    def test_exports_inference_profile_for_routed_stages(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.delenv("PRIMR_INFERENCE_PROFILE", raising=False)
        monkeypatch.delenv("PRIMR_ACKNOWLEDGE_HOST_AGENT_MAY_BILL", raising=False)

        result = _handle_research(
            _config(
                premium_mode=True,
                inference_profile="hybrid",
                acknowledge_host_agent_may_bill=True,
            )
        )

        assert result == 0
        assert perform_research_ok.called
        assert __import__("os").environ["PRIMR_INFERENCE_PROFILE"] == "hybrid"
        assert __import__("os").environ["PRIMR_ACKNOWLEDGE_HOST_AGENT_MAY_BILL"] == "1"

    def test_non_acknowledged_run_clears_stale_host_billing_consent(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)
        monkeypatch.setenv("PRIMR_ACKNOWLEDGE_HOST_AGENT_MAY_BILL", "1")

        result = _handle_research(_config(premium_mode=True, inference_profile="cloud"))

        assert result == 0
        assert "PRIMR_ACKNOWLEDGE_HOST_AGENT_MAY_BILL" not in __import__("os").environ

    def test_billing_acknowledgment_without_hybrid_is_rejected(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)

        result = _handle_research(_config(premium_mode=True, acknowledge_host_agent_may_bill=True))

        assert result == 1
        perform_research_ok.assert_not_called()


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

    def test_invalid_context_json_includes_warning_without_console_noise(
        self, passing_preflight, perform_research_ok, monkeypatch, capsys
    ):
        monkeypatch.setattr("primr.utils.validators.validate_company_name", lambda x: x)
        monkeypatch.setattr("primr.utils.validators.validate_url", lambda x: x)

        result_obj = MagicMock(
            invalid_files=[("bad.txt", "not found")],
            valid_files=[],
            warnings=["context warning"],
        )
        monkeypatch.setattr(
            "primr.core.workspace.validate_context_files",
            MagicMock(return_value=result_obj),
        )

        result = _handle_research(
            _config(
                premium_mode=True,
                context_files=("bad.txt",),
                json_output=True,
            )
        )

        assert result == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["hints"] == [
            "context warning",
            "Invalid context file: bad.txt - not found",
        ]
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
        passing_preflight.assert_not_called()

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
            return perform_research_ok(*args, **kwargs)

        monkeypatch.setattr("primr.core.research_agent.perform_research", record_active_budget)

        assert _handle_research(_config(premium_mode=True, budget_usd=2.00)) == 0
        # Budget was active during the run...
        assert seen["budget"] is not None
        assert seen["budget"].max_cost == 2.00
        # ...and cleared afterwards
        assert get_run_budget() is None

    def test_budget_runtime_info_for_premium_strategy_checkpoint(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        from types import SimpleNamespace

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.79)),
        )
        warn = MagicMock()
        monkeypatch.setattr("primr.core.cli_budget.console.warn", warn)

        assert _handle_research(_config(premium_mode=True, budget_usd=2.00)) == 0

        assert warn.call_args_list == []

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

    def test_budget_cleared_when_network_preflight_fails(
        self, passing_preflight, perform_research_ok, monkeypatch
    ):
        from types import SimpleNamespace

        from primr.utils.run_budget import get_run_budget

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.50)),
        )
        passing_preflight.return_value = (False, ["provider unreachable"])

        assert _handle_research(_config(premium_mode=True, budget_usd=2.00)) == 1
        perform_research_ok.assert_not_called()
        assert get_run_budget() is None

    def test_budget_cleared_when_network_preflight_raises(self, passing_preflight, monkeypatch):
        from types import SimpleNamespace

        from primr.utils.run_budget import get_run_budget

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.50)),
        )
        passing_preflight.side_effect = RuntimeError("network checker failed")

        with pytest.raises(RuntimeError, match="network checker failed"):
            _handle_research(_config(premium_mode=True, budget_usd=2.00))
        assert get_run_budget() is None

    def test_budget_cleared_when_activation_raises_after_setting_state(
        self, passing_preflight, monkeypatch
    ):
        from primr.utils.run_budget import get_run_budget, set_run_budget

        def fail_activation(*_args, **_kwargs):
            set_run_budget(2.0)
            raise RuntimeError("activation failed")

        monkeypatch.setattr("primr.core.cli_budget.activate_run_budget", fail_activation)

        with pytest.raises(RuntimeError, match="activation failed"):
            _handle_research(_config(premium_mode=True, budget_usd=2.00))
        assert get_run_budget() is None

    def test_budget_cleared_when_company_is_busy(self, passing_preflight, monkeypatch):
        from types import SimpleNamespace

        from primr.core.workspace import ActiveRunLeaseError
        from primr.utils.run_budget import get_run_budget

        monkeypatch.setattr(
            "primr.utils.cost_estimator.estimate_cost",
            MagicMock(return_value=SimpleNamespace(total_cost=0.50)),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(side_effect=ActiveRunLeaseError("active company run")),
        )

        assert _handle_research(_config(premium_mode=True, budget_usd=2.00)) == 1
        assert get_run_budget() is None

    def test_no_budget_flag_means_no_active_budget(self, passing_preflight, perform_research_ok):
        from primr.utils.run_budget import get_run_budget

        assert _handle_research(_config(premium_mode=True)) == 0
        assert get_run_budget() is None
