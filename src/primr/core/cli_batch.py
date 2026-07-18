"""Batch-mode CLI helpers.

Extracted from `primr.core.cli` for isolated unit testing.

These cover spreadsheet/CSV ingest (`_read_batch_file`,
`_prepare_batch_df`), deterministic column classification (`_classify_columns`
and `_ColumnMap`), URL normalization (`_ensure_valid_url`), and the
CSV-injection sanitization helpers used when writing enriched output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from primr.utils.console import console

logger = logging.getLogger(__name__)


# Cells whose first non-whitespace character is one of these become formulas in
# Excel/Sheets unless prefixed with a single-quote. See OWASP "CSV Injection".
_FORMULA_LEAD_CHARS: tuple[str, ...] = ("=", "+", "-", "@")
# A leading whitespace control char (tab/CR/newline) is itself a danger, even
# when no formula char follows.
_DANGEROUS_LEAD_CHARS: tuple[str, ...] = (*_FORMULA_LEAD_CHARS, "\t", "\r", "\n")


def _csv_safe(value: Any) -> Any:
    """Prefix dangerous strings with a single quote to neutralize CSV injection.

    Neutralizes both a directly-dangerous first character AND a payload like
    ``" =cmd"`` whose first *non-whitespace* character is a formula char (the
    sheet trims leading whitespace before evaluating, so ``value[0]`` alone
    would miss it).
    """
    if (
        isinstance(value, str)
        and value
        and (value[0] in _DANGEROUS_LEAD_CHARS or value.lstrip()[:1] in _FORMULA_LEAD_CHARS)
    ):
        return "'" + value
    return value


def _ensure_valid_url(website: str | None) -> str | None:
    """Ensure URL has proper scheme."""
    if not website:
        return None
    website = website.strip()
    if not website:
        return None
    if website.startswith(("http://", "https://")):
        return website
    if website.startswith("www."):
        return f"https://{website}"
    return f"https://{website}"


@dataclass(frozen=True)
class _ColumnMap:
    """Deterministic spreadsheet column classification."""

    company: str
    website: str | None
    industry: str | None
    context: list[str]


def _normalized_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _first_alias(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {column: _normalized_header(column) for column in columns}
    for alias in aliases:
        for column, header in normalized.items():
            if header == alias:
                return column
    return None


def _looks_like_website_column(df: Any, column: str) -> bool:
    values = [
        str(value).strip().lower()
        for value in df[column].head(5)
        if str(value).strip().lower() not in {"", "nan"}
    ]
    if not values:
        return False
    website_values = sum(
        1
        for value in values
        if "@" not in value
        and (
            value.startswith(("http://", "https://", "www."))
            or bool(re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}(?:/.*)?", value))
        )
    )
    return website_values / len(values) >= 0.6


def _classify_columns(df: Any, *, quiet: bool = False) -> _ColumnMap:
    """Classify common batch headers without model or network activity."""
    columns = list(df.columns)
    if not columns:
        raise ValueError("Spreadsheet has no columns; cannot classify an empty file")

    company_col = _first_alias(
        columns,
        (
            "companyname",
            "accountname",
            "organizationname",
            "organisationname",
            "company",
            "account",
            "organization",
            "organisation",
            "name",
        ),
    )
    if company_col is None:
        company_col = columns[0]
        if not quiet:
            console.warn(
                f"Column detection fell back to '{company_col}'; "
                "verify this is the company name column"
            )

    website_col = _first_alias(
        columns,
        (
            "companywebsite",
            "websiteurl",
            "webaddress",
            "website",
            "domain",
            "url",
        ),
    )
    if website_col is None:
        website_col = next(
            (
                column
                for column in columns
                if column != company_col and _looks_like_website_column(df, column)
            ),
            None,
        )

    industry_col = _first_alias(
        columns,
        ("industry", "industryname", "sector", "vertical", "marketsegment"),
    )

    skip_headers = {
        "id",
        "recordid",
        "internalid",
        "owner",
        "accountowner",
        "salesowner",
        "salesrep",
        "createddate",
        "modifieddate",
        "lastactivitydate",
    }
    assigned = {company_col, website_col, industry_col}
    context_cols = [
        column
        for column in columns
        if column not in assigned and _normalized_header(column) not in skip_headers
    ]

    mapping = _ColumnMap(
        company=company_col,
        website=website_col,
        industry=industry_col,
        context=context_cols,
    )

    logger.debug(f"Column mapping: {mapping}")
    return mapping


def _read_batch_file(file_path: str) -> Any:
    """Read an Excel or CSV file into a pandas DataFrame."""
    import pandas as pd

    if file_path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path, engine="openpyxl")
    return pd.read_csv(file_path, encoding="utf-8")


def _prepare_batch_df(
    file_path: str,
    industry: str | None = None,
    limit: int | None = None,
    *,
    quiet: bool = False,
) -> tuple[Any, _ColumnMap]:
    """Read a batch file, classify columns locally, filter, and limit."""
    df = _read_batch_file(file_path)

    if not quiet:
        console.info("Analyzing columns...")
    col_map = _classify_columns(df, quiet=quiet)
    if not quiet:
        console.info(f"  Company: {col_map.company}")
        if col_map.website:
            console.info(f"  Website: {col_map.website}")
        if col_map.industry:
            console.info(f"  Industry: {col_map.industry}")
        if col_map.context:
            console.info(f"  Context: {', '.join(col_map.context)}")
        console.blank()

    if industry and col_map.industry:
        df = df[df[col_map.industry].astype(str).str.lower() == industry.lower()]
        if df.empty:
            df_full = _read_batch_file(file_path)
            unique = sorted(df_full[col_map.industry].dropna().unique())
            if not quiet:
                console.error(f"No rows match industry '{industry}'.")
                console.info(f"Available industries: {', '.join(str(v) for v in unique[:20])}")
            raise SystemExit(1)
    elif industry and not col_map.industry:
        if not quiet:
            console.error(f"--industry specified but no industry column found in {file_path}")
            console.info(f"Available columns: {', '.join(list(df.columns))}")
        raise SystemExit(1)

    if limit and limit > 0:
        df = df.head(limit)

    return df, col_map
