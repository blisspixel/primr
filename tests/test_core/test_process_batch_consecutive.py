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
    def test_three_consecutive_research_failures_auto_wait(self, isolated, monkeypatch):
        df, col_map = _three_company_df(
            (
                "https://a1.example",
                "https://a2.example",
                "https://a3.example",
            )
        )
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(return_value=None),  # always None -> failed
        )
        sleep_mock = MagicMock()
        monkeypatch.setattr("time.sleep", sleep_mock)
        result = process_batch("/p.csv", skip_confirm=True)
        # Will have triggered consecutive-failure auto-wait path
        assert sleep_mock.called
        # All companies failed -> exit code 1
        assert result == 1

    def test_missing_website_lookup_fails_marks_skipped(self, isolated, monkeypatch):
        df, col_map = _three_company_df()  # no websites
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # lookup returns None for all three
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            MagicMock(return_value=None),
        )
        # Consecutive-failure branch in the website-missing path uses input()
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")
        sleep_mock = MagicMock()
        monkeypatch.setattr("time.sleep", sleep_mock)
        result = process_batch("/p.csv", skip_confirm=True)
        # All skipped (counted as failed) -> exit code 1
        assert result == 1

    def test_missing_website_then_lookup_succeeds(self, isolated, monkeypatch):
        df = pd.DataFrame(
            {
                "Account Name": ["A1"],
                "URL": [""],
                "Sector": ["Tech"],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            MagicMock(return_value="https://discovered.example"),
        )
        # Successful research
        out = isolated / "output"
        out.mkdir()
        report = out / "report.docx"
        report.write_text("x" * 20_000, encoding="utf-8")
        monkeypatch.setattr(
            "primr.core.research_agent.perform_research",
            MagicMock(return_value=str(report)),
        )
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/p.csv", skip_confirm=True)
        assert result == 0
