import json
from pathlib import Path
from types import SimpleNamespace

from primr.core.local_stage_eval import (
    WebsiteSummaryEvalRow,
    WebsiteSummarySemanticEvalRow,
    extract_summary_metrics,
    find_latest_website_summary_eval_inputs,
    parse_scraped_content_file,
    parse_website_summary_semantic_judge_response,
    run_local_website_summary_semantic_eval,
    write_website_summary_semantic_eval_report,
    write_website_summary_semantic_quality_evidence,
    write_website_summary_stage_eval_markdown,
    write_website_summary_stage_eval_report,
    write_website_summary_stage_eval_summary,
    write_website_summary_stage_quality_evidence,
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


def test_write_website_summary_stage_quality_evidence(tmp_path: Path):
    row = WebsiteSummaryEvalRow(
        company="ExampleCo",
        model="qwen3:30b",
        working_dir="working/ExampleCo/2026-03-02_1200",
        input_pages=2,
        local_summary_path="must-not-be-copied.local.txt",
        baseline_summary_path="must-not-be-copied.baseline.txt",
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
    output = tmp_path / "website_summary_stage_quality_evidence.json"

    write_website_summary_stage_quality_evidence(
        output,
        eval_id="eval-stage-001",
        results=[("qwen3:30b", [row])],
    )

    text = output.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert payload["evidence_type"] == "website_summary_stage_quality"
    assert payload["decision_policy"] == "scorecard_input_only"
    assert payload["stage_id"] == "fast.scrape_summary"
    assert "must-not-be-copied" not in text
    assert payload["quality_evidence"] == [
        {
            "stage_id": "fast.scrape_summary",
            "backend_id": "qwen3:30b",
            "quality_score": 96.0,
            "sample_size": 1,
            "source": "website_summary_stage:eval-stage-001:qwen3:30b",
        }
    ]


def test_parse_website_summary_semantic_judge_response_uses_weighted_scores():
    score, aspects, rationale, valid = parse_website_summary_semantic_judge_response(
        """
        {
          "aspects": {
            "strategic_coverage": 90,
            "factual_alignment": 92,
            "evidence_usefulness": 88,
            "uncertainty_calibration": 80
          },
          "rationale": "Candidate is grounded and decision-useful."
        }
        """,
        fallback_score=50.0,
    )

    assert valid is True
    assert score == 88.7
    assert aspects["factual_alignment"] == 92.0
    assert rationale == "Candidate is grounded and decision-useful."


def test_parse_website_summary_semantic_judge_response_falls_back_on_invalid_json():
    score, aspects, rationale, valid = parse_website_summary_semantic_judge_response(
        "not json",
        fallback_score=96.0,
    )

    assert valid is False
    assert score == 96.0
    assert set(aspects.values()) == {96.0}
    assert "fell back to structural completeness" in rationale


def test_parse_website_summary_semantic_judge_response_rejects_scoreless_json():
    score, aspects, rationale, valid = parse_website_summary_semantic_judge_response(
        '{"rationale": "Looks fine."}',
        fallback_score=82.0,
    )

    assert valid is False
    assert score == 82.0
    assert set(aspects.values()) == {82.0}
    assert "omitted numeric scores" in rationale


def test_run_local_website_summary_semantic_eval_invokes_local_judge(
    tmp_path: Path,
    monkeypatch,
):
    baseline = tmp_path / "baseline.txt"
    candidate = tmp_path / "candidate.txt"
    baseline.write_text("Baseline source-linked strategic summary.", encoding="utf-8")
    candidate.write_text("Candidate source-linked strategic summary.", encoding="utf-8")
    row = WebsiteSummaryEvalRow(
        company="ExampleCo",
        model="qwen3:30b",
        working_dir="working/ExampleCo/2026-03-02_1200",
        input_pages=2,
        local_summary_path=str(candidate),
        baseline_summary_path=str(baseline),
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
    captured = {}

    def fake_chat_completion(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            text=json.dumps(
                {
                    "semantic_score": 93,
                    "aspects": {
                        "strategic_coverage": 93,
                        "factual_alignment": 94,
                        "evidence_usefulness": 92,
                        "uncertainty_calibration": 90,
                    },
                    "rationale": "Candidate is grounded.",
                }
            ),
            prompt_tokens=120,
            completion_tokens=35,
        )

    monkeypatch.setattr(
        "primr.ai.openai_compatible_client.chat_completion",
        fake_chat_completion,
    )

    rows = run_local_website_summary_semantic_eval(
        rows=[row],
        judge_model="llama3.1:70b",
        base_url="http://localhost:11434/v1",
        api_key_env="LOCAL_LLM_API_KEY",
    )

    assert rows[0].semantic_score == 93.0
    assert rows[0].response_valid is True
    assert rows[0].input_tokens == 120
    assert captured["kwargs"]["model"] == "llama3.1:70b"
    assert "Baseline summary:" in captured["prompt"]
    assert "Candidate summary:" in captured["prompt"]


def test_write_website_summary_semantic_outputs_are_body_free(tmp_path: Path):
    row = WebsiteSummarySemanticEvalRow(
        company="ExampleCo",
        model="qwen3:30b",
        judge_model="llama3.1:70b",
        working_dir="working/ExampleCo/2026-03-02_1200",
        semantic_score=91.25,
        aspects={
            "strategic_coverage": 91.0,
            "factual_alignment": 95.0,
            "evidence_usefulness": 90.0,
            "uncertainty_calibration": 84.0,
        },
        rationale="Candidate preserves source-linked facts without overclaiming.",
        response_valid=True,
        input_tokens=120,
        output_tokens=80,
    )
    report_path = tmp_path / "website_summary_stage_semantic_eval.json"
    evidence_path = tmp_path / "website_summary_stage_semantic_quality_evidence.json"

    write_website_summary_semantic_eval_report(
        report_path,
        eval_id="eval-stage-001",
        judge_model="llama3.1:70b",
        results=[("qwen3:30b", [row])],
        base_url="http://localhost:11434/v1",
        api_key_env="LOCAL_LLM_API_KEY",
    )
    write_website_summary_semantic_quality_evidence(
        evidence_path,
        eval_id="eval-stage-001",
        results=[("qwen3:30b", [row])],
    )

    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["judge_policy"] == ("single_local_judge_review_signal_not_promotion_gate")
    assert report_payload["avg_semantic_score"] == 91.25

    evidence_text = evidence_path.read_text(encoding="utf-8")
    evidence_payload = json.loads(evidence_text)
    assert evidence_payload["evidence_type"] == "website_summary_semantic_quality"
    assert "Candidate summary:" not in evidence_text
    assert evidence_payload["quality_evidence"] == [
        {
            "stage_id": "fast.scrape_summary",
            "backend_id": "qwen3:30b",
            "quality_score": 91.25,
            "sample_size": 1,
            "source": ("website_summary_semantic:eval-stage-001:qwen3:30b:judge=llama3.1:70b"),
        }
    ]


def test_write_website_summary_semantic_quality_omits_invalid_judge_rows(tmp_path: Path):
    valid_row = WebsiteSummarySemanticEvalRow(
        company="ExampleCo",
        model="qwen3:30b",
        judge_model="llama3.1:70b",
        working_dir="working/ExampleCo/run-001",
        semantic_score=90.0,
        aspects={
            "strategic_coverage": 90.0,
            "factual_alignment": 90.0,
            "evidence_usefulness": 90.0,
            "uncertainty_calibration": 90.0,
        },
        rationale="Valid semantic judgment.",
        response_valid=True,
        input_tokens=120,
        output_tokens=40,
    )
    invalid_row = WebsiteSummarySemanticEvalRow(
        company="ExampleTwo",
        model="qwen3:30b",
        judge_model="llama3.1:70b",
        working_dir="working/ExampleTwo/run-001",
        semantic_score=96.0,
        aspects={
            "strategic_coverage": 96.0,
            "factual_alignment": 96.0,
            "evidence_usefulness": 96.0,
            "uncertainty_calibration": 96.0,
        },
        rationale="Fallback from malformed judge response.",
        response_valid=False,
        input_tokens=120,
        output_tokens=40,
    )
    output = tmp_path / "website_summary_stage_semantic_quality_evidence.json"

    write_website_summary_semantic_quality_evidence(
        output,
        eval_id="eval-stage-001",
        results=[("qwen3:30b", [valid_row, invalid_row])],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["quality_evidence"] == [
        {
            "stage_id": "fast.scrape_summary",
            "backend_id": "qwen3:30b",
            "quality_score": 90.0,
            "sample_size": 1,
            "source": (
                "website_summary_semantic:eval-stage-001:qwen3:30b:"
                "judge=llama3.1:70b:fallback_rows=1"
            ),
        }
    ]
