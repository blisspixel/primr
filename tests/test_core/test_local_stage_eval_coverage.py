"""
Coverage-focused tests for primr.core.local_stage_eval.

Exercises the helper math, the no-filter discovery path, and the
``run_local_website_summary_stage_eval`` driver with a mocked local LLM
summarizer (no network calls).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from primr.core.local_stage_eval import (
    WebsiteSummaryEvalInput,
    _display_company_name,
    _ratio_pct,
    _website_summary_completeness_score,
    extract_summary_metrics,
    find_latest_website_summary_eval_inputs,
    parse_scraped_content_file,
    run_local_website_summary_stage_eval,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_scraped(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """============================================================
URL: https://example.com
============================================================
Home page content.

============================================================
URL: https://example.com/about
============================================================
About content.
""",
        encoding="utf-8",
    )


def _write_summary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """## Website Insights

### Source: https://example.com
- Fact one [Source: https://example.com]

## Cross-Page Synthesis
### Open Questions To Validate
- Question one
- Question two
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# helper math
# ---------------------------------------------------------------------------


def test_ratio_pct_normal():
    assert _ratio_pct(5, 10) == 50.0


def test_ratio_pct_capped_at_100():
    assert _ratio_pct(20, 10) == 100.0


def test_ratio_pct_zero_baseline_positive_local():
    assert _ratio_pct(3, 0) == 100.0


def test_ratio_pct_zero_baseline_negative_local():
    assert _ratio_pct(-1, 0) == 0.0


def test_display_company_name_normalizes_underscores_and_spaces():
    assert _display_company_name("Acme_Corp__Inc") == "Acme Corp Inc"
    assert _display_company_name("  spaced   out  ") == "spaced out"


def test_completeness_score_perfect_match():
    metrics = {
        "source_sections": 2,
        "source_citations": 1,
        "open_questions": 2,
        "words": 100,
        "has_synthesis": True,
    }
    score = _website_summary_completeness_score(baseline=metrics, local=dict(metrics))
    assert score == 100.0


def test_completeness_score_synthesis_mismatch_lowers_score():
    baseline = {
        "source_sections": 2,
        "source_citations": 1,
        "open_questions": 2,
        "words": 100,
        "has_synthesis": True,
    }
    local = dict(baseline)
    local["has_synthesis"] = False
    score = _website_summary_completeness_score(baseline=baseline, local=local)
    # synthesis component (20%) is lost
    assert score == 80.0


# ---------------------------------------------------------------------------
# parsing / metrics
# ---------------------------------------------------------------------------


def test_extract_summary_metrics_no_synthesis_block():
    metrics = extract_summary_metrics("## Header\nSome words here\n")
    assert metrics["has_synthesis"] is False
    assert metrics["source_sections"] == 0
    assert metrics["open_questions"] == 0
    assert metrics["words"] > 0


def test_parse_scraped_content_file_skips_empty(tmp_path: Path):
    scraped = tmp_path / "scraped_content.txt"
    _write_scraped(scraped)
    parsed = parse_scraped_content_file(scraped)
    assert set(parsed) == {"https://example.com", "https://example.com/about"}


# ---------------------------------------------------------------------------
# discovery without a companies filter (the unfiltered loop branch)
# ---------------------------------------------------------------------------


def test_find_inputs_no_filter_returns_sorted(tmp_path: Path):
    for name in ("Zeta_Co", "Alpha_Co"):
        run = tmp_path / name / "2026-01-01_0900"
        _write_scraped(run / "scraped_content.txt")
        _write_summary(run / "scraped_website_summary.txt")

    rows = find_latest_website_summary_eval_inputs(tmp_path)
    assert [r.company for r in rows] == ["Alpha Co", "Zeta Co"]


def test_find_inputs_nonexistent_root_returns_empty(tmp_path: Path):
    rows = find_latest_website_summary_eval_inputs(tmp_path / "missing")
    assert rows == []


def test_find_inputs_filter_no_match_returns_empty(tmp_path: Path):
    run = tmp_path / "Alpha_Co" / "2026-01-01_0900"
    _write_scraped(run / "scraped_content.txt")
    _write_summary(run / "scraped_website_summary.txt")
    rows = find_latest_website_summary_eval_inputs(
        tmp_path, companies=["Completely Different Name XYZ"]
    )
    assert rows == []


# ---------------------------------------------------------------------------
# eval driver with mocked local summarizer
# ---------------------------------------------------------------------------


def test_run_eval_with_mocked_summarizer(tmp_path: Path):
    run = tmp_path / "ExampleCo" / "2026-01-01_0900"
    _write_scraped(run / "scraped_content.txt")
    _write_summary(run / "scraped_website_summary.txt")

    item = WebsiteSummaryEvalInput(
        company="ExampleCo",
        working_dir=run,
        scraped_content_path=run / "scraped_content.txt",
        baseline_summary_path=run / "scraped_website_summary.txt",
    )

    local_text = (run / "scraped_website_summary.txt").read_text(encoding="utf-8")

    with patch(
        "primr.core.local_stage_eval.summarize_scraped_content_local",
        return_value=local_text,
    ) as mock_sum:
        rows = run_local_website_summary_stage_eval(
            inputs=[item],
            model="qwen3:30b",
            output_root=tmp_path / "out",
        )

    assert mock_sum.called
    assert len(rows) == 1
    row = rows[0]
    assert row.company == "ExampleCo"
    assert row.input_pages == 2
    assert row.completeness_score == 100.0


def test_run_eval_skips_empty_scraped_file(tmp_path: Path):
    run = tmp_path / "ExampleCo" / "2026-01-01_0900"
    empty = run / "scraped_content.txt"
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("no url markers here", encoding="utf-8")
    _write_summary(run / "scraped_website_summary.txt")

    item = WebsiteSummaryEvalInput(
        company="ExampleCo",
        working_dir=run,
        scraped_content_path=empty,
        baseline_summary_path=run / "scraped_website_summary.txt",
    )

    with patch(
        "primr.core.local_stage_eval.summarize_scraped_content_local",
        return_value="ignored",
    ) as mock_sum:
        rows = run_local_website_summary_stage_eval(
            inputs=[item],
            model="qwen3:30b",
            output_root=tmp_path / "out",
        )

    assert rows == []
    assert not mock_sum.called


def test_eval_report_round_trip(tmp_path: Path):
    run = tmp_path / "ExampleCo" / "2026-01-01_0900"
    _write_scraped(run / "scraped_content.txt")
    _write_summary(run / "scraped_website_summary.txt")
    item = WebsiteSummaryEvalInput(
        company="ExampleCo",
        working_dir=run,
        scraped_content_path=run / "scraped_content.txt",
        baseline_summary_path=run / "scraped_website_summary.txt",
    )
    local_text = (run / "scraped_website_summary.txt").read_text(encoding="utf-8")
    with patch(
        "primr.core.local_stage_eval.summarize_scraped_content_local",
        return_value=local_text,
    ):
        rows = run_local_website_summary_stage_eval(
            inputs=[item], model="m1", output_root=tmp_path / "out"
        )

    from primr.core.local_stage_eval import write_website_summary_stage_eval_report

    report = tmp_path / "report.json"
    write_website_summary_stage_eval_report(
        report, model="m1", rows=rows, base_url=None, api_key_env="LOCAL_LLM_API_KEY"
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["companies_evaluated"] == 1
