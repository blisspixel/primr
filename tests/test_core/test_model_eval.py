import json
from pathlib import Path

from primr.ai.openai_compatible_client import normalize_openai_base_url
from primr.config.local_eval_models import (
    DEFAULT_LOCAL_EVAL_MODEL_LIST,
    get_local_eval_model_list,
)
from primr.core.model_eval import (
    LLMJudgeMetadata,
    LLMJudgeRow,
    _company_similarity,
    auto_stage_existing_reports,
    evaluate_outputs,
    get_eval_judge_candidate_profiles,
    write_fast_feedback_guidance,
    write_llm_judge_report,
    write_local_judge_sweep_markdown,
    write_local_judge_sweep_summary,
)


def _write_sample_report(path: Path, company: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# {company} Strategic Overview

## Executive Summary
{company} operates in enterprise software and has visible growth signals. (Reported)

## Products and Services
Primary products include workflow tools and analytics modules. [cite: 1]

## Target Customers
Mid-market and enterprise teams in regulated industries. (Estimated)

## Competitive Landscape
Competition is moderate; differentiation comes from implementation speed. (Hypothesis)

## Financial Profile
Public signals suggest recurring-revenue expansion. [cite: 2]

## SWOT Analysis
Strengths include channel partnerships and retention performance.

## Strategic Positioning
Near-term opportunity is vertical expansion with ecosystem integrations.

## Citations
[cite: 1] https://example.com/source-1
[cite: 2] https://example.com/source-2
""",
        encoding="utf-8",
    )


def test_evaluate_outputs_writes_scorecards(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-test-001"
    full_dir = eval_root / eval_id / "full"
    fast_dir = eval_root / eval_id / "fast"

    _write_sample_report(full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")
    _write_sample_report(fast_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("full", "fast"),
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=None,
    )

    assert result.scorecard_md.exists()
    assert result.scorecard_csv.exists()
    assert len(result.profile_summaries) == 2
    assert len(result.metrics) == 2
    assert result.missing_pairs == []


def test_evaluate_outputs_detects_missing_pairs_from_manifest(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-test-002"
    full_dir = eval_root / eval_id / "full"

    _write_sample_report(full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "company,website\nExampleCo,https://example.com\nSecondCo,https://second.example\n",
        encoding="utf-8",
    )

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("full", "lite"),
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=manifest,
    )

    assert ("SecondCo", "full") in result.missing_pairs
    assert ("ExampleCo", "lite") in result.missing_pairs


def test_auto_stage_existing_reports_for_company(tmp_path: Path):
    source = tmp_path / "output"
    eval_root = tmp_path / "evals"
    usage_file = tmp_path / "logs" / "usage_history.json"
    usage_file.parent.mkdir(parents=True, exist_ok=True)
    usage_file.write_text(
        '[{"mode":"fast","company":"ExampleCo"}]',
        encoding="utf-8",
    )

    _write_sample_report(source / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")
    _write_sample_report(
        source / "ExampleCo Corporation_Strategic_Overview_02-25-2026.md", "ExampleCo Corporation"
    )

    staged = auto_stage_existing_reports(
        eval_id="eval-stage-001",
        eval_root=eval_root,
        source_dir=source,
        profiles=("full", "fast"),
        company="ExampleCo",
        usage_file=usage_file,
    )

    assert len(staged["full"]) == 1
    assert len(staged["fast"]) == 1
    assert (eval_root / "eval-stage-001" / "staging_manifest.json").exists()


def test_auto_stage_skips_fast_without_fast_history(tmp_path: Path):
    source = tmp_path / "output"
    eval_root = tmp_path / "evals"
    usage_file = tmp_path / "logs" / "usage_history.json"
    usage_file.parent.mkdir(parents=True, exist_ok=True)
    usage_file.write_text(
        '[{"mode":"complete","company":"ExampleCo"}]',
        encoding="utf-8",
    )

    _write_sample_report(source / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    staged = auto_stage_existing_reports(
        eval_id="eval-stage-002",
        eval_root=eval_root,
        source_dir=source,
        profiles=("full", "fast"),
        company="ExampleCo",
        usage_file=usage_file,
    )

    assert len(staged["full"]) == 1
    assert len(staged["fast"]) == 0


def test_evaluate_outputs_filters_to_manifest_targets(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-filter-001"
    full_dir = eval_root / eval_id / "full"
    fast_dir = eval_root / eval_id / "fast"

    _write_sample_report(full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")
    _write_sample_report(full_dir / "OtherCo_Strategic_Overview_02-25-2026.md", "OtherCo")
    _write_sample_report(fast_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    manifest = tmp_path / "targets.csv"
    manifest.write_text("company\nExampleCo\n", encoding="utf-8")

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("full", "fast"),
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=manifest,
    )

    assert len(result.metrics) == 2
    assert all(m.company == "ExampleCo" for m in result.metrics)


def test_company_similarity_ignores_legal_suffixes():
    assert _company_similarity("Nulogy", "Nulogy Corporation") >= 0.99


def test_write_fast_feedback_guidance_creates_rules_file(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-feedback-001"
    fast_dir = eval_root / eval_id / "fast"
    _write_sample_report(fast_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("fast",),
        baseline="fast",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=None,
    )

    guidance_path = eval_root / eval_id / "fast_feedback_guidance.md"
    write_fast_feedback_guidance(guidance_path, eval_result=result, judge_rows=[])

    assert guidance_path.exists()
    text = guidance_path.read_text(encoding="utf-8")
    assert "Fast Report Feedback Guidance" in text
    assert "What to validate:" in text


def test_write_llm_judge_report_includes_metadata(tmp_path: Path):
    report_path = tmp_path / "llm_judge.json"
    rows = [
        LLMJudgeRow(
            company="ExampleCo",
            baseline_profile="full",
            candidate_profile="fast",
            winner_profile="full",
            baseline_score=88.0,
            candidate_score=81.0,
            baseline_aspects={"strategic_usefulness": 88.0},
            candidate_aspects={"strategic_usefulness": 81.0},
            passes=1,
            rationale="baseline stronger",
            cost_usd=0.0,
        )
    ]
    metadata = LLMJudgeMetadata(
        provider="local",
        model="qwen2.5:14b-instruct",
        base_url="http://localhost:11434/v1",
        api_key_env="LOCAL_LLM_API_KEY",
    )

    write_llm_judge_report(report_path, rows, total_cost=0.0, metadata=metadata)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["provider"] == "local"
    assert payload["metadata"]["model"] == "qwen2.5:14b-instruct"
    assert payload["metadata"]["base_url"] == "http://localhost:11434/v1"


def test_normalize_openai_base_url_appends_v1():
    assert normalize_openai_base_url("http://localhost:11434") == "http://localhost:11434/v1"
    assert normalize_openai_base_url("http://localhost:11434/v1") == "http://localhost:11434/v1"


def test_write_local_judge_sweep_summary_and_markdown(tmp_path: Path):
    metadata_a = LLMJudgeMetadata(provider="local", model="qwen3-coder:30b", base_url="http://localhost:11434/v1")
    metadata_b = LLMJudgeMetadata(provider="local", model="qwen2.5:14b", base_url="http://localhost:11434/v1")
    rows_a = [
        LLMJudgeRow(
            company="ExampleCo",
            baseline_profile="full",
            candidate_profile="fast",
            winner_profile="full",
            baseline_score=82.0,
            candidate_score=75.0,
            baseline_aspects={"strategic_usefulness": 82.0},
            candidate_aspects={"strategic_usefulness": 75.0},
            passes=1,
            rationale="full wins",
            cost_usd=0.0,
        ),
        LLMJudgeRow(
            company="ExampleCo",
            baseline_profile="full",
            candidate_profile="lite",
            winner_profile="full",
            baseline_score=81.0,
            candidate_score=74.0,
            baseline_aspects={"strategic_usefulness": 81.0},
            candidate_aspects={"strategic_usefulness": 74.0},
            passes=1,
            rationale="full wins again",
            cost_usd=0.0,
        ),
    ]
    rows_b = [
        LLMJudgeRow(
            company="ExampleCo",
            baseline_profile="full",
            candidate_profile="fast",
            winner_profile="tie",
            baseline_score=78.0,
            candidate_score=78.0,
            baseline_aspects={"strategic_usefulness": 78.0},
            candidate_aspects={"strategic_usefulness": 78.0},
            passes=1,
            rationale="tie",
            cost_usd=0.0,
        ),
        LLMJudgeRow(
            company="ExampleCo",
            baseline_profile="full",
            candidate_profile="lite",
            winner_profile="full",
            baseline_score=80.0,
            candidate_score=77.0,
            baseline_aspects={"strategic_usefulness": 80.0},
            candidate_aspects={"strategic_usefulness": 77.0},
            passes=1,
            rationale="full edges out lite",
            cost_usd=0.0,
        ),
    ]
    summary_json = tmp_path / "local_judge_summary.json"
    summary_md = tmp_path / "local_judge_summary.md"

    results = [(metadata_a, rows_a, 0.0), (metadata_b, rows_b, 0.0)]
    write_local_judge_sweep_summary(
        summary_json,
        eval_id="eval-test",
        baseline_profile="full",
        candidate_profiles=["fast", "lite"],
        results=results,
    )
    write_local_judge_sweep_markdown(
        summary_md,
        eval_id="eval-test",
        baseline_profile="full",
        candidate_profiles=["fast", "lite"],
        results=results,
    )

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["models_evaluated"] == 2
    assert payload["candidate_profiles"] == ["fast", "lite"]
    assert payload["winner_counts"]["full"] == 2
    assert payload["majority_winner_profile"] == "full"
    assert payload["recommended_models"]
    assert payload["results"][0]["model"] == "qwen3-coder:30b"
    assert payload["results"][0]["winner_consensus_rate"] == 1.0
    assert payload["results"][0]["candidate_profiles_evaluated"] == ["fast", "lite"]
    assert "avg_aspect_gap" in payload["results"][0]
    assert payload["results"][1]["row_winner_counts"]["tie"] == 1
    markdown = summary_md.read_text(encoding="utf-8")
    assert "qwen3-coder:30b" in markdown
    assert "qwen2.5:14b" in markdown
    assert "## Ranking" in markdown
    assert "Top aspect gaps:" in markdown
    assert "Candidate profiles covered: fast, lite" in markdown


def test_local_eval_model_list_default_and_lookup():
    models = get_local_eval_model_list(DEFAULT_LOCAL_EVAL_MODEL_LIST)
    assert len(models) >= 10
    assert "qwen3:30b" in models
    assert "qwen2.5:14b" in models


def test_get_eval_judge_candidate_profiles_preserves_eval_order(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-order-001"
    full_dir = eval_root / eval_id / "full"
    lite_dir = eval_root / eval_id / "lite"
    fast_dir = eval_root / eval_id / "fast"

    _write_sample_report(full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")
    _write_sample_report(lite_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")
    _write_sample_report(fast_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("full", "lite", "fast"),
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=None,
    )

    assert get_eval_judge_candidate_profiles(result, baseline_profile="full") == ["lite", "fast"]
