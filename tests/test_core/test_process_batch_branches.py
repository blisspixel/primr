"""Additional unit tests for process_batch error/retry branches in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from primr.core.cli import process_batch
from primr.core.cli_batch import _ColumnMap


def _research_with_outcomes(report_path, state_path, *, strategy_complete=True):
    def run(*_args, **kwargs):
        from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
        from primr.core.vendor_refresh_outcome import (
            VendorRefreshTracker,
            persist_vendor_refresh_outcome,
        )

        state_path.mkdir(parents=True, exist_ok=True)
        kwargs["run_context"]["working_folder"] = str(state_path)
        strategy = StrategyOutcomeTracker(("ai:azure",) if not strategy_complete else ())
        persist_strategy_outcome(str(state_path), strategy.snapshot())
        persist_vendor_refresh_outcome(str(state_path), VendorRefreshTracker(()).snapshot())
        return str(report_path)

    return run


def _write_bound_run_state(state_path, report_path, *, strategy_complete):
    from primr.core.research_artifact_binding import bind_primary_artifact
    from primr.core.run_state_io import _update_run_state
    from primr.core.strategy_outcome import StrategyOutcomeTracker, persist_strategy_outcome
    from primr.core.vendor_refresh_outcome import (
        VendorRefreshTracker,
        persist_vendor_refresh_outcome,
    )

    state_path.mkdir(parents=True)
    _update_run_state(
        str(state_path),
        status="completed",
        company_name="ExampleCo",
        website="https://a.example",
        mode="complete",
    )
    strategy = StrategyOutcomeTracker(("ai:agnostic",))
    if strategy_complete:
        strategy.mark_completed("ai:agnostic")
    persist_strategy_outcome(str(state_path), strategy.snapshot())
    persist_vendor_refresh_outcome(str(state_path), VendorRefreshTracker(()).snapshot())
    assert bind_primary_artifact(str(state_path), str(report_path)) is True


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("primr.core.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("primr.config.config.WORKING_DIR", str(tmp_path / "working"))
    return tmp_path


@pytest.fixture
def one_company_df():
    df = pd.DataFrame(
        {
            "Account Name": ["ExampleCo"],
            "URL": ["https://a.example"],
            "Sector": ["Tech"],
        }
    )
    col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
    return df, col_map


class TestProcessBatchErrorPaths:
    def test_perform_research_returns_none_logged_as_failure(
        self, isolated, monkeypatch, one_company_df
    ):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(return_value=None),
        )
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        # Failed companies -> exit code 1
        assert result == 1

    def test_billing_exhaustion_is_not_retried_or_slept(
        self, isolated, monkeypatch, one_company_df
    ):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # A second response would succeed, but batch governance permits one attempt only.
        responses = [
            RuntimeError("credits exhausted"),
            "/output/report.docx",
        ]
        perform_mock = MagicMock(side_effect=responses)
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        sleep_mock = MagicMock()
        monkeypatch.setattr("time.sleep", sleep_mock)
        # Make the result file exist so size check passes
        out = isolated / "output"
        out.mkdir()
        (out / "report.docx").write_text("x" * 20_000, encoding="utf-8")
        responses[1] = str(out / "report.docx")
        result = process_batch("/path.csv", skip_confirm=True)
        assert result == 1
        assert perform_mock.call_count == 1
        sleep_mock.assert_not_called()

    def test_quota_error_is_not_automatically_retried(self, isolated, monkeypatch, one_company_df):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # All attempts fail with quota error
        perform_mock = MagicMock(side_effect=RuntimeError("429 quota exceeded"))
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            perform_mock,
        )
        sleep_mock = MagicMock()
        monkeypatch.setattr("time.sleep", sleep_mock)
        result = process_batch("/path.csv", skip_confirm=True)
        assert result == 1
        assert perform_mock.call_count == 1
        sleep_mock.assert_not_called()

    def test_small_report_marked_warning(self, isolated, monkeypatch, one_company_df):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # Generate a tiny report — should be marked as warning, not error
        out = isolated / "output"
        out.mkdir()
        tiny = out / "tiny.docx"
        tiny.write_text("x", encoding="utf-8")  # 1 byte
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(side_effect=_research_with_outcomes(tiny, isolated / "run-state")),
        )
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        # Warning-status reports count as usable -> result is 0
        assert result == 0

    def test_partial_strategy_preserves_report_and_returns_nonzero(
        self, isolated, monkeypatch, one_company_df
    ):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        out = isolated / "output"
        out.mkdir()
        report = out / "report.docx"
        report.write_text("x" * 20_000, encoding="utf-8")
        runner = MagicMock(
            side_effect=_research_with_outcomes(
                report,
                isolated / "partial-run-state",
                strategy_complete=False,
            )
        )
        monkeypatch.setattr("primr.core.research_agent.perform_research", runner)

        result = process_batch("/path.csv", skip_confirm=True)

        assert result == 1
        assert report.exists()
        assert runner.call_args.kwargs["run_context"]["working_folder"]

    def test_existing_report_skipped(self, isolated, monkeypatch, one_company_df):
        from datetime import datetime

        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # Pre-create today's report so the resume logic finds it
        out = isolated / "output"
        out.mkdir()
        today_str = datetime.now().strftime("%m-%d-%Y")
        existing = out / f"ExampleCo_Strategic_Overview_{today_str}.docx"
        existing.write_text("x" * 20_000, encoding="utf-8")
        _write_bound_run_state(
            isolated / "working" / "ExampleCo" / "run-1",
            existing,
            strategy_complete=True,
        )
        # Stub OUTPUT_DIR so the resume check finds the file
        monkeypatch.setattr("primr.core.cli.OUTPUT_DIR", str(out))
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(out))
        perform_mock = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        # Should have skipped research — not called perform_research
        perform_mock.assert_not_called()
        assert result == 0

    def test_partial_existing_report_requires_fresh_approved_attempt(
        self, isolated, monkeypatch, one_company_df
    ):
        from datetime import datetime

        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        out = isolated / "output"
        out.mkdir()
        today_str = datetime.now().strftime("%m-%d-%Y")
        existing = out / f"ExampleCo_Strategic_Overview_{today_str}.docx"
        existing.write_text("x" * 20_000, encoding="utf-8")
        _write_bound_run_state(
            isolated / "working" / "ExampleCo" / "partial-run",
            existing,
            strategy_complete=False,
        )
        runner = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.research_agent.perform_research", runner)

        result = process_batch("/path.csv", skip_confirm=True)

        assert result == 1
        runner.assert_called_once()

    @pytest.mark.parametrize(
        ("request_kwargs", "mutate_artifact"),
        [({"ai_strategy": False}, False), ({}, True)],
    )
    def test_existing_report_is_not_reused_for_changed_request_or_content(
        self,
        isolated,
        monkeypatch,
        one_company_df,
        request_kwargs,
        mutate_artifact,
    ):
        from datetime import datetime

        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        out = isolated / "output"
        out.mkdir()
        today_str = datetime.now().strftime("%m-%d-%Y")
        existing = out / f"ExampleCo_Strategic_Overview_{today_str}.docx"
        existing.write_text("x" * 20_000, encoding="utf-8")
        _write_bound_run_state(
            isolated / "working" / "ExampleCo" / "complete-run",
            existing,
            strategy_complete=True,
        )
        if mutate_artifact:
            existing.write_text("changed" * 4_000, encoding="utf-8")
        runner = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.research_agent.perform_research", runner)

        result = process_batch("/path.csv", skip_confirm=True, **request_kwargs)

        assert result == 1
        runner.assert_called_once()
