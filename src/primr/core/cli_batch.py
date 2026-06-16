"""Batch-mode CLI helpers.

Extracted from `primr.core.cli` for isolated unit testing.

These cover spreadsheet/CSV ingest (`_read_batch_file`,
`_prepare_batch_df`), LLM-driven column classification (`_classify_columns`
+ `_ColumnMap`), URL normalization (`_ensure_valid_url`), and the
CSV-injection sanitization helpers used when writing enriched output.
"""

from __future__ import annotations

import json
import logging
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
    if website.startswith(("http://", "https://")):
        return website
    if website.startswith("www."):
        return f"https://{website}"
    return f"https://{website}"


@dataclass(frozen=True)
class _ColumnMap:
    """Result of LLM-based column classification."""

    company: str
    website: str | None
    industry: str | None
    context: list[str]


def _classify_columns(df: Any) -> _ColumnMap:
    """Use LLM to classify spreadsheet columns into roles."""
    from primr.ai.llm import llm

    columns = list(df.columns)
    if not columns:
        raise ValueError("Spreadsheet has no columns — cannot classify an empty file")

    sample_lines = []
    for _, row in df.head(3).iterrows():
        vals = {
            col: str(row[col]).strip() for col in columns if str(row[col]).strip().lower() != "nan"
        }
        sample_lines.append(json.dumps(vals, ensure_ascii=False))
    samples_text = "\n".join(sample_lines)

    prompt = f"""Classify these spreadsheet columns for a company research tool.

Columns: {json.dumps(columns)}

Sample rows:
{samples_text}

Classify each column into exactly ONE role:
- "company_name": the column containing the company/organization name (exactly one)
- "website": the column containing the company website URL (if any)
- "industry": the column containing industry, sector, or vertical (if any)
- "context": columns useful for identifying the company (region, country, revenue, employees, HQ, etc.)
- "skip": internal CRM fields not useful for identifying the company (owner, sales team, dates, internal IDs, etc.)

Return JSON only, no explanation:
{{"company_name": "column_name", "website": "column_name_or_null", "industry": "column_name_or_null", "context": ["col1", "col2"], "skip": ["col1", "col2"]}}"""

    response = llm(prompt, model_type="fast", streaming=False).strip()

    if response.startswith("```"):
        parts = response.split("\n", 1)
        if len(parts) > 1:
            response = parts[1].rsplit("```", 1)[0].strip()
        else:
            response = response[3:].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        logger.warning("LLM column classification failed to parse, falling back")
        console.warn(
            f"Column detection fell back to '{columns[0]}' — verify this is the company name column"
        )
        return _ColumnMap(company=columns[0], website=None, industry=None, context=[])

    company_col = result.get("company_name")
    if not company_col or company_col not in columns:
        for candidate in ["Account Name", "Company", "company_name", "Name"]:
            if candidate in columns:
                company_col = candidate
                break
        if not company_col:
            company_col = columns[0]

    website_col = result.get("website")
    if website_col and website_col not in columns:
        website_col = None

    industry_col = result.get("industry")
    if industry_col and industry_col not in columns:
        industry_col = None

    context_cols = [c for c in result.get("context", []) if c in columns]

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
) -> tuple[Any, _ColumnMap]:
    """Read batch file, classify columns with LLM, filter, and limit."""
    df = _read_batch_file(file_path)

    console.info("Analyzing columns...")
    col_map = _classify_columns(df)
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
            console.error(f"No rows match industry '{industry}'.")
            console.info(f"Available industries: {', '.join(str(v) for v in unique[:20])}")
            raise SystemExit(1)
    elif industry and not col_map.industry:
        console.error(f"--industry specified but no industry column found in {file_path}")
        console.info(f"Available columns: {', '.join(list(df.columns))}")
        raise SystemExit(1)

    if limit and limit > 0:
        df = df.head(limit)

    return df, col_map
