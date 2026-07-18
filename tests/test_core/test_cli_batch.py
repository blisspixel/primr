"""Unit tests for primr.core.cli_batch.

Focused tests for the column-classification helpers, file readers,
CSV-injection sanitizer, and URL normalizer extracted from cli.py.
"""

from __future__ import annotations

import pandas as pd
import pytest

from primr.core.cli_batch import (
    _DANGEROUS_LEAD_CHARS,
    _classify_columns,
    _ColumnMap,
    _csv_safe,
    _ensure_valid_url,
    _prepare_batch_df,
    _read_batch_file,
)

# ---------------------------------------------------------------------------
# _DANGEROUS_LEAD_CHARS / _csv_safe
# ---------------------------------------------------------------------------


class TestCsvSafe:
    @pytest.mark.parametrize("lead", list(_DANGEROUS_LEAD_CHARS))
    def test_dangerous_leads_get_quote_prefix(self, lead):
        result = _csv_safe(f'{lead}WEBSERVICE("https://attacker")')
        assert result.startswith("'")

    def test_safe_strings_unchanged(self):
        assert _csv_safe("Acme Corp") == "Acme Corp"
        assert _csv_safe("https://example.com") == "https://example.com"

    def test_non_strings_unchanged(self):
        assert _csv_safe(42) == 42
        assert _csv_safe(None) is None
        assert _csv_safe(3.14) == 3.14

    def test_empty_string_unchanged(self):
        assert _csv_safe("") == ""


# ---------------------------------------------------------------------------
# _ensure_valid_url
# ---------------------------------------------------------------------------


class TestEnsureValidUrl:
    def test_none_returns_none(self):
        assert _ensure_valid_url(None) is None

    def test_empty_returns_none(self):
        assert _ensure_valid_url("") is None

    def test_whitespace_only_returns_none(self):
        assert _ensure_valid_url("   ") is None

    def test_https_preserved(self):
        assert _ensure_valid_url("https://acme.example") == "https://acme.example"

    def test_http_preserved(self):
        assert _ensure_valid_url("http://acme.example") == "http://acme.example"

    def test_www_gets_https(self):
        assert _ensure_valid_url("www.acme.example") == "https://www.acme.example"

    def test_bare_domain_gets_https(self):
        assert _ensure_valid_url("acme.example") == "https://acme.example"

    def test_strips_whitespace(self):
        assert _ensure_valid_url("  https://x.example  ") == "https://x.example"


# ---------------------------------------------------------------------------
# _ColumnMap
# ---------------------------------------------------------------------------


class TestColumnMap:
    def test_is_frozen(self):
        from dataclasses import FrozenInstanceError

        m = _ColumnMap(company="C", website=None, industry=None, context=[])
        with pytest.raises(FrozenInstanceError):
            m.company = "X"  # type: ignore[misc]

    def test_carries_all_fields(self):
        m = _ColumnMap(
            company="Account Name",
            website="URL",
            industry="Sector",
            context=["Region", "Revenue"],
        )
        assert m.company == "Account Name"
        assert m.website == "URL"
        assert m.industry == "Sector"
        assert m.context == ["Region", "Revenue"]


# ---------------------------------------------------------------------------
# _classify_columns
# ---------------------------------------------------------------------------


class TestClassifyColumns:
    def test_raises_on_empty_columns(self):
        df = pd.DataFrame()
        with pytest.raises(ValueError, match="empty file"):
            _classify_columns(df)

    def test_common_headers_are_classified_locally(self):
        df = pd.DataFrame(
            {
                "Account Name": ["ExampleCo", "OtherCo"],
                "URL": ["https://a.example", "https://b.example"],
                "Sector": ["Tech", "Retail"],
                "Region": ["US", "EU"],
            }
        )
        result = _classify_columns(df)
        assert result.company == "Account Name"
        assert result.website == "URL"
        assert result.industry == "Sector"
        assert result.context == ["Region"]

    def test_name_alias_is_classified(self):
        df = pd.DataFrame({"Name": ["A"], "Owner": ["internal"]})
        result = _classify_columns(df)
        assert result.company == "Name"
        assert result.context == []

    def test_unknown_headers_fall_back_to_first_column(self):
        df = pd.DataFrame({"First": ["A"], "Second": ["B"]})
        result = _classify_columns(df)
        assert result.company == "First"
        assert result.website is None
        assert result.context == ["Second"]

    def test_website_values_are_detected_when_header_is_unknown(self):
        df = pd.DataFrame(
            {
                "Organization": ["A", "B"],
                "Homepage": ["a.example", "https://b.example"],
            }
        )
        result = _classify_columns(df)
        assert result.website == "Homepage"


# ---------------------------------------------------------------------------
# _read_batch_file
# ---------------------------------------------------------------------------


class TestReadBatchFile:
    def test_reads_csv(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("company_name,website\nExampleCo,https://a.example\n")
        df = _read_batch_file(str(path))
        assert list(df.columns) == ["company_name", "website"]
        assert df.iloc[0]["company_name"] == "ExampleCo"

    def test_reads_xlsx(self, tmp_path):
        # We use the openpyxl write engine if available; skip if not.
        openpyxl = pytest.importorskip("openpyxl")  # noqa: F841

        path = tmp_path / "data.xlsx"
        pd.DataFrame({"company_name": ["ExampleCo"], "website": ["https://x.example"]}).to_excel(
            path, index=False, engine="openpyxl"
        )
        df = _read_batch_file(str(path))
        assert df.iloc[0]["company_name"] == "ExampleCo"


# ---------------------------------------------------------------------------
# _prepare_batch_df
# ---------------------------------------------------------------------------


class TestPrepareBatchDf:
    def _write_csv(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text(
            "Account Name,URL,Sector\n"
            "ExampleCo,https://a.example,Tech\n"
            "OtherCo,https://b.example,Retail\n"
            "ThirdCo,https://c.example,Tech\n",
            encoding="utf-8",
        )
        return str(path)

    def test_returns_df_and_column_map(self, tmp_path):
        path = self._write_csv(tmp_path)
        df, col_map = _prepare_batch_df(path)
        assert len(df) == 3
        assert col_map.company == "Account Name"

    def test_industry_filter(self, tmp_path):
        path = self._write_csv(tmp_path)
        df, _ = _prepare_batch_df(path, industry="tech")
        # case-insensitive match -> 2 rows
        assert len(df) == 2

    def test_industry_filter_no_match_raises_systemexit(self, tmp_path):
        path = self._write_csv(tmp_path)
        with pytest.raises(SystemExit):
            _prepare_batch_df(path, industry="nonexistent_industry")

    def test_limit_applied(self, tmp_path):
        path = self._write_csv(tmp_path)
        df, _ = _prepare_batch_df(path, limit=2)
        assert len(df) == 2

    def test_industry_filter_without_industry_column_raises(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("Account Name\nExampleCo\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            _prepare_batch_df(str(path), industry="tech")
