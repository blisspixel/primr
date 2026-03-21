import json
from pathlib import Path

from primr.core.local_stage_eval import (
    WebsiteSummaryEvalRow,
    extract_summary_metrics,
    find_latest_website_summary_eval_inputs,
    parse_scraped_content_file,
    write_website_summary_stage_eval_markdown,
    write_website_summary_stage_eval_report,
    write_website_summary_stage_eval_summary,
)


def _write_scraped_content(path: Path, company: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# {company} - Scraped Content
# URL: https://example.com
# Pages: 2

============================================================
URL: https://example.com
============================================================
Home page content with products, partners, and leadership.

============================================================
URL: https://example.com/about
============================================================
About page content with founding date and customer details.
""",
        encoding="utf-8",
    )


def _write_summary(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """## Website Insights for ExampleCo

### Source: https://example.com
- Product facts

### Source: https://example.com/about
- Company history

## Cross-Page Synthesis
### Open Questions To Validate
- How durable is retention?
- Which partner channels matter most?
[Source: https://example.com/about]
""",
        encoding="utf-8",
    )


def test_parse_scraped_content_file_extracts_urls(tmp_path: Path):
    scraped = tmp_path / "scraped_content.txt"
    _write_scraped_content(scraped, "ExampleCo")

    parsed = parse_scraped_content_file(scraped)

    assert list(parsed) == ["https://example.com", "https://example.com/about"]
    assert "Home page content" in parsed["https://example.com"]


def test_extract_summary_metrics_counts_sections_and_questions():
    metrics = extract_summary_metrics(
        """## Website Insights
### Source: https://example.com
- Fact
## Cross-Page Synthesis
### Open Questions To Validate
- One
- Two
[Source: https://example.com]
"""
    )

    assert metrics["source_sections"] == 1
    assert metrics["open_questions"] == 2
    assert metrics["has_synthesis"] is True
    assert metrics["source_citations"] == 1


def test_find_latest_website_summary_eval_inputs_prefers_latest_run(tmp_path: Path):
    older = tmp_path / "ExampleCo" / "2026-03-01_1200"
    newer = tmp_path / "ExampleCo" / "2026-03-02_1200"
    _write_scraped_content(older / "scraped_content.txt", "ExampleCo")
    _write_summary(older / "scraped_website_summary.txt")
    _write_scraped_content(newer / "scraped_content.txt", "ExampleCo")
    _write_summary(newer / "scraped_website_summary.txt")

    rows = find_latest_website_summary_eval_inputs(tmp_path, companies=["ExampleCo"])

    assert len(rows) == 1
    assert rows[0].working_dir == newer


def test_write_website_summary_stage_eval_outputs(tmp_path: Path):
    row = WebsiteSummaryEvalRow(
        company="ExampleCo",
        model="qwen3:30b",
        working_dir="working/ExampleCo/2026-03-02_1200",
        input_pages=2,
        local_summary_path="output/evals/test/qwen3/scraped_website_summary.local.txt",
        baseline_summary_path="working/ExampleCo/2026-03-02_1200/scraped_website_summary.txt",
        baseline_words=100,
        local_words=90,
        baseline_source_sections=2,
        local_source_sections=2,
        baseline_source_citations=1,
        local_source_citations=1,
        baseline_open_questions=2,
        local_open_questions=2,
        baseline_has_synthesis=True,
        local_has_synthesis=True,
        source_section_ratio=100.0,
        citation_ratio=100.0,
        open_questions_ratio=100.0,
        word_ratio=90.0,
        completeness_score=96.0,
    )
    report_path = tmp_path / "stage.qwen3.json"
    summary_json = tmp_path / "website_summary_stage_summary.json"
    summary_md = tmp_path / "website_summary_stage_summary.md"

    write_website_summary_stage_eval_report(
        report_path,
        model="qwen3:30b",
        rows=[row],
        base_url="http://localhost:11434/v1",
        api_key_env="LOCAL_LLM_API_KEY",
    )
    write_website_summary_stage_eval_summary(
        summary_json,
        eval_id="eval-stage-001",
        results=[("qwen3:30b", [row])],
    )
    write_website_summary_stage_eval_markdown(
        summary_md,
        eval_id="eval-stage-001",
        results=[("qwen3:30b", [row])],
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["companies_evaluated"] == 1
    assert payload["avg_completeness_score"] == 96.0

    summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert summary_payload["stage"] == "website-summary"
    assert summary_payload["recommended_models"] == ["qwen3:30b"]

    markdown = summary_md.read_text(encoding="utf-8")
    assert "Local Website Summary Stage Eval" in markdown
    assert "ExampleCo: score=96.00" in markdown
