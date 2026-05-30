"""Additional unit tests for process_batch error/retry branches in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from primr.core.cli import process_batch
from primr.core.cli_batch import _ColumnMap


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("primr.core.cli.OUTPUT_DIR", str(tmp_path / "output"))
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
            "primr.core.cli._prepare_batch_df",
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

    def test_billing_exhausted_with_skip_confirm_pauses_and_retries(
        self, isolated, monkeypatch, one_company_df
    ):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # First call: billing error; second call: success
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
        # Should have slept for billing pause
        assert sleep_mock.called
        assert result in (0, 1)

    def test_quota_error_retries_then_fails(self, isolated, monkeypatch, one_company_df):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # All attempts fail with quota error
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(side_effect=RuntimeError("429 quota exceeded")),
        )
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        assert result == 1

    def test_small_report_marked_warning(self, isolated, monkeypatch, one_company_df):
        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # Generate a tiny report — should be marked as warning, not error
        out = isolated / "output"
        out.mkdir()
        tiny = out / "tiny.docx"
        tiny.write_text("x", encoding="utf-8")  # 1 byte
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(return_value=str(tiny)),
        )
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        # Warning-status reports count as usable -> result is 0
        assert result == 0

    def test_existing_report_skipped(self, isolated, monkeypatch, one_company_df):
        from datetime import datetime

        df, col_map = one_company_df
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # Pre-create today's report so the resume logic finds it
        out = isolated / "output"
        out.mkdir()
        today_str = datetime.now().strftime("%m-%d-%Y")
        existing = out / f"ExampleCo_Strategic_Overview_{today_str}.docx"
        existing.write_text("x" * 20_000, encoding="utf-8")
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
