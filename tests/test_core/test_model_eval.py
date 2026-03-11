from pathlib import Path

from primr.core.model_eval import (
    _company_similarity,
    auto_stage_existing_reports,
    evaluate_outputs,
    write_fast_feedback_guidance,
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
