"""Unit tests for enrich_batch in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from primr.core.cli import enrich_batch
from primr.core.cli_batch import _ColumnMap


@pytest.fixture
def fake_batch_df():
    """Build a DataFrame with company + website + industry columns."""
    df = pd.DataFrame(
        {
            "Account Name": ["ExampleCo", "OtherCo", "ThirdCo"],
            "URL": ["https://a.example", "", "https://c.example"],
            "Sector": ["Tech", "Retail", "Tech"],
        }
    )
    col_map = _ColumnMap(
        company="Account Name",
        website="URL",
        industry="Sector",
        context=[],
    )
    return df, col_map


class TestEnrichBatch:
    def test_happy_path_returns_zero(self, fake_batch_df, tmp_path, monkeypatch):
        df, col_map = fake_batch_df
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            MagicMock(return_value="https://b.example"),
        )
        monkeypatch.chdir(tmp_path)
        result = enrich_batch(str(tmp_path / "batch.csv"))
        assert result == 0
        # Should have written an enriched CSV
        outputs = list(tmp_path.glob("*_enriched.csv"))
        assert len(outputs) == 1

    def test_dedup_by_company_name(self, tmp_path, monkeypatch):
        df = pd.DataFrame(
            {
                "Account Name": ["ExampleCo", "examplecoo", "EXAMPLECO"],
                "URL": ["https://a.example", "https://b.example", "https://c.example"],
                "Sector": ["Tech", "Tech", "Tech"],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.chdir(tmp_path)
        enrich_batch(str(tmp_path / "batch.csv"))
        # Check the output CSV has only 2 unique entries (ExampleCo + examplecoo are different,
        # ExampleCo == EXAMPLECO same)
        out = next(tmp_path.glob("*_enriched.csv"))
        out_df = pd.read_csv(out)
        # Should have 2 rows because casing duplicates are dropped
        assert len(out_df) == 2

    def test_filters_nan_company_names(self, tmp_path, monkeypatch):
        df = pd.DataFrame(
            {
                "Account Name": ["ExampleCo", "nan", "", "ThirdCo"],
                "URL": ["", "", "", ""],
                "Sector": ["Tech", "Tech", "Tech", "Tech"],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            MagicMock(return_value=None),
        )
        monkeypatch.chdir(tmp_path)
        enrich_batch(str(tmp_path / "batch.csv"))
        out = next(tmp_path.glob("*_enriched.csv"))
        out_df = pd.read_csv(out)
        # ExampleCo and ThirdCo only
        assert len(out_df) == 2

    def test_writes_industry_filename_suffix(self, tmp_path, monkeypatch, fake_batch_df):
        df, col_map = fake_batch_df
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.setattr(
            "primr.data.search_utils.lookup_company_website",
            MagicMock(return_value="https://b.example"),
        )
        monkeypatch.chdir(tmp_path)
        enrich_batch(str(tmp_path / "batch.csv"), industry="Tech")
        # Output filename should include "tech" suffix
        out = next(tmp_path.glob("*_enriched.csv"))
        assert "tech" in out.name.lower()

    def test_csv_injection_sanitization(self, tmp_path, monkeypatch):
        """Lines starting with =, +, -, @, \\t, \\r get single-quote prefix."""
        df = pd.DataFrame(
            {
                "Account Name": ['=WEBSERVICE("https://attacker")'],
                "URL": ["+1234567890"],
                "Sector": ["Tech"],
            }
        )
        col_map = _ColumnMap(company="Account Name", website="URL", industry="Sector", context=[])
        monkeypatch.setattr(
            "primr.core.cli._prepare_batch_df",
            MagicMock(return_value=(df, col_map)),
        )
        monkeypatch.chdir(tmp_path)
        enrich_batch(str(tmp_path / "batch.csv"))
        out = next(tmp_path.glob("*_enriched.csv"))
        content = out.read_text(encoding="utf-8")
        # Dangerous leads should have been prefixed with a single quote
        assert "'=WEBSERVICE" in content
