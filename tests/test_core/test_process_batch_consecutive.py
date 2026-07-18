"""Tests for process_batch consecutive-failure handling and website lookup paths."""

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


def _three_company_df(websites: tuple[str | None, str | None, str | None] = (None, None, None)):
    df = pd.DataFrame(
        {
            "Account Name": ["A1", "A2", "A3"],
            "URL": [w or "" for w in websites],
            "Sector": ["Tech", "Tech", "Tech"],
        }
    )
    col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
    return df, col_map


class TestConsecutiveFailures:
    def test_three_consecutive_research_failures_stop_without_wait(self, isolated, monkeypatch):
        df, col_map = _three_company_df(
            (
                "https://a1.example",
                "https://a2.example",
                "https://a3.example",
            )
        )
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(return_value=None),  # always None -> failed
        )
        sleep_mock = MagicMock()
        monkeypatch.setattr("time.sleep", sleep_mock)
        result = process_batch("/p.csv", skip_confirm=True)
        sleep_mock.assert_not_called()
        # All companies failed -> exit code 1
        assert result == 1

    def test_missing_websites_fail_before_any_lookup_or_wait(self, isolated, monkeypatch):
        df, col_map = _three_company_df()  # no websites
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        lookup_mock = MagicMock(return_value=None)
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            lookup_mock,
        )
        sleep_mock = MagicMock()
        monkeypatch.setattr("time.sleep", sleep_mock)
        result = process_batch("/p.csv", skip_confirm=True)
        assert result == 1
        lookup_mock.assert_not_called()
        sleep_mock.assert_not_called()

    def test_missing_website_never_triggers_hidden_lookup_or_research(self, isolated, monkeypatch):
        df = pd.DataFrame(
            {
                "Account Name": ["A1"],
                "URL": [""],
                "Sector": ["Tech"],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        lookup_mock = MagicMock(return_value="https://discovered.example")
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            lookup_mock,
        )
        # Successful research
        out = isolated / "output"
        out.mkdir()
        report = out / "report.docx"
        report.write_text("x" * 20_000, encoding="utf-8")
        perform_mock = MagicMock(return_value=str(report))
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            perform_mock,
        )
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/p.csv", skip_confirm=True)
        assert result == 1
        lookup_mock.assert_not_called()
        perform_mock.assert_not_called()
