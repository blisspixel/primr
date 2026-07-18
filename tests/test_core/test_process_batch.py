"""Unit tests for process_batch in primr.core.cli."""

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
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


@pytest.fixture
def small_df():
    df = pd.DataFrame(
        {
            "Account Name": ["ExampleCo"],
            "URL": ["https://a.example"],
            "Sector": ["Tech"],
        }
    )
    col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
    return df, col_map


class TestProcessBatch:
    def test_no_companies_returns_1(self, isolated, monkeypatch):
        # DataFrame with all-empty company names
        df = pd.DataFrame(
            {
                "Account Name": ["", "nan", "  "],
                "URL": ["", "", ""],
                "Sector": ["", "", ""],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        result = process_batch("/path.csv", skip_confirm=True)
        assert result == 1

    def test_dedup_by_lowercase_name(self, isolated, monkeypatch, small_df):
        # Two rows with same name in different case
        df = pd.DataFrame(
            {
                "Account Name": ["ExampleCo", "EXAMPLECO"],
                "URL": ["https://a.example", "https://b.example"],
                "Sector": ["Tech", "Tech"],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # Make perform_research return immediately
        perform_mock = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        # Avoid sleeping
        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        # Should attempt research for only one company (dedup)
        assert perform_mock.call_count == 1
        assert result in (0, 1)

    def test_cancelled_by_user_returns_0(self, isolated, monkeypatch, small_df):
        df, col_map = small_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        # User says no at the prompt
        monkeypatch.setattr("builtins.input", lambda *_a: "n")
        result = process_batch("/path.csv", skip_confirm=False)
        assert result == 0

    def test_skip_confirm_proceeds(self, isolated, monkeypatch, small_df):
        df, col_map = small_df
        monkeypatch.setattr(
            "primr.core.cli_batch_runtime._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        perform_mock = MagicMock(return_value="/output/report.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_research", perform_mock)
        # Make the result file exist for the size check
        out_path = isolated / "output" / "report.docx"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("x" * (20 * 1024), encoding="utf-8")
        perform_mock.return_value = str(out_path)

        monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
        result = process_batch("/path.csv", skip_confirm=True)
        perform_mock.assert_called()
        assert result in (0, 1)
