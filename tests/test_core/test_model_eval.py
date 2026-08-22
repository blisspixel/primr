import json
from pathlib import Path

import pytest

from primr.ai.openai_compatible_client import normalize_openai_base_url
from primr.config.local_eval_models import (
    DEFAULT_LOCAL_EVAL_MODEL_LIST,
    get_local_eval_model_list,
)
from primr.core.model_eval import (
    EvalProfileSlot,
    LLMJudgeMetadata,
    LLMJudgeRow,
    ProfileRecipe,
    _company_similarity,
    _estimated_profile_cost,
    auto_stage_existing_reports,
    evaluate_outputs,
    get_eval_judge_candidate_profiles,
    get_eval_profile,
    list_eval_profile_names,
    list_eval_profiles,
    register_eval_profile,
    unregister_eval_profile,
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


def _write_leaky_report(path: Path, company: str) -> None:
    """Sample report carrying scaffolding leaks the drift gate must surface."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# {company} Strategic Overview

## Executive Summary
{company} operates in enterprise software. (Reported) Per [workbook] the margin is thin.

**What to validate:** confirm the ARR estimate with a primary source.

## Citations
[cite: 1] https://example.com/source-1
""",
        encoding="utf-8",
    )


def test_eval_surfaces_scaffolding_leaks(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-leak-001"
    full_dir = eval_root / eval_id / "full"
    _write_leaky_report(full_dir / "LeakyCo_Strategic_Overview_02-25-2026.md", "LeakyCo")

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("full",),
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=None,
    )

    # Per-report metric carries the leak count (>=2: bare [workbook] + bold validate).
    assert result.metrics[0].scaffolding_leaks >= 2
    # Profile summary aggregates it.
    summary = result.profile_summaries[0]
    assert summary.total_scaffolding_leaks == result.metrics[0].scaffolding_leaks
    # Scorecard MD surfaces the drift signal and CSV has the column.
    md = result.scorecard_md.read_text(encoding="utf-8")
    assert "## Artifact Drift" in md
    assert "DRIFT" in md
    csv_text = result.scorecard_csv.read_text(encoding="utf-8")
    assert "scaffolding_leaks" in csv_text.splitlines()[0]


def test_eval_clean_report_has_no_drift(tmp_path: Path):
    eval_root = tmp_path / "evals"
    eval_id = "eval-clean-001"
    full_dir = eval_root / eval_id / "full"
    _write_sample_report(full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    result = evaluate_outputs(
        eval_id=eval_id,
        eval_root=eval_root,
        profiles=("full",),
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=None,
    )

    assert result.metrics[0].scaffolding_leaks == 0
    assert result.profile_summaries[0].total_scaffolding_leaks == 0
    assert "clean" in result.scorecard_md.read_text(encoding="utf-8")


def _write_calibration_sidecar(
    report_path: Path,
    per_label: dict,
    validation_rubric: dict | None = None,
    judge_agreement: dict | None = None,
) -> None:
    """Persist a `primr calibrate` sidecar next to a staged report."""
    from primr.qa.artifact_fingerprints import artifact_fingerprint
    from primr.qa.calibration_runner import sidecar_path_for

    sidecar_path_for(report_path).write_text(
        json.dumps(
            {
                "report_artifact": artifact_fingerprint(report_path),
                "per_label": per_label,
                "validation_rubric": validation_rubric or {},
                "judge_agreement": judge_agreement or {},
                "claims": [],
            }
        ),
        encoding="utf-8",
    )


def _run_eval(tmp_path: Path, eval_id: str, profiles=("full",)):
    return evaluate_outputs(
        eval_id=eval_id,
        eval_root=tmp_path / "evals",
        profiles=profiles,
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=0.2,
        manifest_path=None,
    )


def test_eval_reads_calibration_sidecar(tmp_path: Path):
    full_dir = tmp_path / "evals" / "eval-calib-001" / "full"
    report = full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md"
    _write_sample_report(report, "ExampleCo")
    _write_calibration_sidecar(
        report,
        {
            "Confirmed": {"traceable": 3, "untraceable": 1, "no_source": 1, "unfetchable": 2},
            "Reported": {"traceable": 4, "untraceable": 0, "no_source": 0},
            "Estimated": {"sampled": 2, "exempt": 1, "source_copied": 1},
            "Hypothesis": {"sampled": 1, "exempt": 1, "source_copied": 0},
        },
        {
            "source_reviews": 5,
            "support": {"supported": 4, "unsupported": 1},
            "contradiction": {"direct": 1, "partial": 0, "none": 4, "unknown": 0},
            "source_independence": {"independent": 3, "first_party": 2, "unknown": 0},
            "source_authority": {"high": 2, "medium": 2, "low": 1, "unknown": 0},
            "reasoning_strength": {"strong": 4, "partial": 1, "weak": 0, "unknown": 0},
            "uncertainty_honesty": {
                "honest": 3,
                "overstated": 1,
                "understated": 1,
                "unknown": 0,
            },
            "business_relevance": {"high": 3, "medium": 2, "low": 0, "unknown": 0},
        },
        {"scope": "report", "local_model": "qwen2.5:14b", "compared": 4, "agreed": 3},
    )

    result = _run_eval(tmp_path, "eval-calib-001")

    metric = result.metrics[0]
    assert metric.calibrated is True
    # unfetchable excluded from decidable: 3 / (3+1+1)
    assert metric.traceability("Confirmed") == pytest.approx(0.6)
    assert metric.traceability("Reported") == pytest.approx(1.0)
    assert metric.evidence_source_reviews == 5
    assert metric.evidence_rate(metric.evidence_supported_reviews) == pytest.approx(0.8)
    assert metric.judge_agreement_compared == 4
    assert metric.judge_agreement_agreed == 3
    assert metric.inference_source_copied == 1
    summary = result.profile_summaries[0]
    assert summary.calibrated_report_count == 1
    assert summary.confirmed_traceability == pytest.approx(0.6)
    assert summary.evidence_support_rate == pytest.approx(0.8)
    assert summary.evidence_strong_reasoning_rate == pytest.approx(0.8)
    assert summary.judge_agreement_compared == 4
    assert summary.judge_agreement_rate == pytest.approx(0.75)
    assert summary.inference_source_copied == 1
    md = result.scorecard_md.read_text(encoding="utf-8")
    assert "## Label Calibration" in md
    assert "## Evidence Review" in md
    assert "## Inference Label Checks" in md
    assert "## Judge Agreement" in md
    assert "60%" in md
    assert "80%" in md
    assert "75%" in md
    header = result.scorecard_csv.read_text(encoding="utf-8").splitlines()[0]
    assert "confirmed_traceability" in header
    assert "evidence_support_rate" in header
    assert "judge_agreement_rate" in header
    assert "inference_source_copied" in header


def test_eval_without_sidecar_reports_no_data(tmp_path: Path):
    full_dir = tmp_path / "evals" / "eval-calib-002" / "full"
    _write_sample_report(full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md", "ExampleCo")

    result = _run_eval(tmp_path, "eval-calib-002")

    assert result.metrics[0].calibrated is False
    assert result.metrics[0].traceability("Confirmed") is None
    summary = result.profile_summaries[0]
    assert summary.calibrated_report_count == 0
    assert summary.confirmed_traceability is None
    assert "no data" in result.scorecard_md.read_text(encoding="utf-8")


def test_eval_corrupt_sidecar_ignored(tmp_path: Path):
    full_dir = tmp_path / "evals" / "eval-calib-003" / "full"
    report = full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md"
    _write_sample_report(report, "ExampleCo")
    from primr.qa.calibration_runner import sidecar_path_for

    sidecar_path_for(report).write_text("{not json", encoding="utf-8")

    result = _run_eval(tmp_path, "eval-calib-003")
    assert result.metrics[0].calibrated is False


@pytest.mark.parametrize("invalid_binding", ["legacy", "stale", "missing_report"])
def test_eval_ignores_sidecars_not_bound_to_current_report(tmp_path: Path, invalid_binding: str):
    from primr.core.eval_calibration import load_calibration_counts
    from primr.qa.calibration_runner import sidecar_path_for

    full_dir = tmp_path / "evals" / f"eval-calib-{invalid_binding}" / "full"
    report = full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md"
    _write_sample_report(report, "ExampleCo")
    _write_calibration_sidecar(report, {"Confirmed": {"traceable": 5}})

    if invalid_binding == "legacy":
        sidecar = sidecar_path_for(report)
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        payload.pop("report_artifact")
        sidecar.write_text(json.dumps(payload), encoding="utf-8")
    elif invalid_binding == "stale":
        report.write_text(report.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
    else:
        report.unlink()

    if invalid_binding == "missing_report":
        assert load_calibration_counts(report) is None
        return

    result = _run_eval(tmp_path, f"eval-calib-{invalid_binding}")
    assert result.metrics[0].calibrated is False
    assert result.profile_summaries[0].calibrated_report_count == 0


def _summary(profile: str, confirmed_traceability: float | None, **overrides):
    from primr.core.model_eval import ProfileSummary

    defaults = {
        "profile": profile,
        "report_count": 1,
        "avg_quality": 80.0,
        "avg_trust": 80.0,
        "avg_decision_utility": 80.0,
        "avg_reuse_quality": 80.0,
        "avg_word_count": 10000.0,
        "avg_pages": 20.0,
        "avg_citation_density": 3.0,
        "avg_utility_per_dollar": 100.0,
        "trust_pass_rate": 1.0,
        "estimated_cost_usd": 1.0,
        "calibrated_report_count": 1,
        "confirmed_traceability": confirmed_traceability,
    }
    defaults.update(overrides)
    return ProfileSummary(**defaults)


def test_calibration_gate_fails_profile_when_armed(tmp_path: Path, monkeypatch):
    from primr.core.model_eval import _decision_table

    monkeypatch.setenv("PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY", "0.8")
    rows = _decision_table(
        [_summary("full", 1.0), _summary("fast", 0.4)],
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=2.0,
    )
    decisions = "\n".join(rows)
    assert "fast: FAIL_CALIBRATION" in decisions
    assert "requires >= 0.80" in decisions

    # And the scorecard surfaces the same breach as BELOW GATE.
    eval_dir = tmp_path / "evals" / "eval-calib-004" / "full"
    report = eval_dir / "ExampleCo_Strategic_Overview_02-25-2026.md"
    _write_sample_report(report, "ExampleCo")
    _write_calibration_sidecar(report, {"Confirmed": {"traceable": 2, "untraceable": 3}})
    result = _run_eval(tmp_path, "eval-calib-004")
    assert "BELOW GATE" in result.scorecard_md.read_text(encoding="utf-8")


def test_calibration_gate_passes_profile_at_or_above_threshold(monkeypatch):
    from primr.core.model_eval import _decision_table

    monkeypatch.setenv("PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY", "0.8")
    rows = _decision_table(
        [_summary("full", 1.0), _summary("fast", 0.8)],
        baseline="full",
        quality_ratio_threshold=0.8,
        cost_ratio_threshold=2.0,
    )
    assert "FAIL_CALIBRATION" not in "\n".join(rows)


def test_calibration_gate_unarmed_is_report_only(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY", raising=False)
    eval_dir = tmp_path / "evals" / "eval-calib-005"
    for profile in ("full", "fast"):
        report = eval_dir / profile / "ExampleCo_Strategic_Overview_02-25-2026.md"
        _write_sample_report(report, "ExampleCo")
        _write_calibration_sidecar(
            report, {"Confirmed": {"traceable": 1, "untraceable": 9}, "Reported": {}}
        )

    result = _run_eval(tmp_path, "eval-calib-005", profiles=("full", "fast"))

    decisions = "\n".join(result.decision_rows)
    assert "FAIL_CALIBRATION" not in decisions
    md = result.scorecard_md.read_text(encoding="utf-8")
    assert "not armed" in md
    assert "BELOW GATE" not in md


def test_calibration_gate_malformed_env_ignored(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY", "ninety")
    full_dir = tmp_path / "evals" / "eval-calib-006" / "full"
    report = full_dir / "ExampleCo_Strategic_Overview_02-25-2026.md"
    _write_sample_report(report, "ExampleCo")
    _write_calibration_sidecar(report, {"Confirmed": {"traceable": 0, "untraceable": 5}})

    result = _run_eval(tmp_path, "eval-calib-006")
    assert "FAIL_CALIBRATION" not in "\n".join(result.decision_rows)


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
    metadata_a = LLMJudgeMetadata(
        provider="local", model="qwen3-coder:30b", base_url="http://localhost:11434/v1"
    )
    metadata_b = LLMJudgeMetadata(
        provider="local", model="qwen2.5:14b", base_url="http://localhost:11434/v1"
    )
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
    report_race = get_local_eval_model_list("4090-report-race")
    assert report_race[0] == "qwen3:32b"
    assert "qwen3.6:35b-a3b" in report_race
    assert len(report_race) < len(models)


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


# =============================================================================
# Profile Slot Registry tests (v1.24.0 prerequisite)
# =============================================================================


class TestProfileSlotRegistry:
    """Tests for the eval profile slot registry.

    The registry is module-level state; tests that register slots clean them
    up via unregister_eval_profile in a try/finally so they don't leak.
    """

    def test_builtin_profiles_pre_registered(self) -> None:
        """The three legacy slots must be registered at module import."""
        names = list_eval_profile_names()
        assert "full" in names
        assert "lite" in names
        assert "fast" in names

    def test_list_eval_profiles_returns_slot_objects(self) -> None:
        """list_eval_profiles returns the full EvalProfileSlot objects, not just names."""
        slots = list_eval_profiles()
        assert all(isinstance(s, EvalProfileSlot) for s in slots)
        builtin_names = {s.name for s in slots if s.is_builtin}
        assert {"full", "lite", "fast"} <= builtin_names

    def test_get_builtin_profile(self) -> None:
        slot = get_eval_profile("full")
        assert slot is not None
        assert slot.name == "full"
        assert slot.is_builtin is True
        # Built-in slots have no per-role recipe - they use mode flags.
        assert slot.recipe is None

    def test_get_unknown_profile_returns_none(self) -> None:
        assert get_eval_profile("does-not-exist-xyz") is None

    def test_register_new_profile(self) -> None:
        slot = EvalProfileSlot(
            name="test-grok43-flashlite",
            recipe=ProfileRecipe(
                reasoning="grok-4.3",
                writing="gemini-3.1-flash-lite",
                utility="gemini-3-flash-preview",
            ),
            estimated_cost_usd=0.65,
            description="Test slot for v1.24.0 sub-$1 candidate recipe",
        )
        try:
            register_eval_profile(slot)
            assert get_eval_profile("test-grok43-flashlite") is slot
            assert "test-grok43-flashlite" in list_eval_profile_names()
        finally:
            unregister_eval_profile("test-grok43-flashlite")

    def test_register_duplicate_raises_without_replace(self) -> None:
        slot = EvalProfileSlot(name="test-duplicate", description="first")
        try:
            register_eval_profile(slot)
            with pytest.raises(ValueError, match="already registered"):
                register_eval_profile(EvalProfileSlot(name="test-duplicate", description="second"))
        finally:
            unregister_eval_profile("test-duplicate")

    def test_register_duplicate_with_replace(self) -> None:
        try:
            register_eval_profile(EvalProfileSlot(name="test-replace", description="first"))
            register_eval_profile(
                EvalProfileSlot(name="test-replace", description="second"),
                replace=True,
            )
            slot = get_eval_profile("test-replace")
            assert slot is not None
            assert slot.description == "second"
        finally:
            unregister_eval_profile("test-replace")

    def test_register_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            register_eval_profile(EvalProfileSlot(name=""))

    @pytest.mark.parametrize("cost", [-0.01, float("nan"), float("inf")])
    def test_register_rejects_invalid_fixed_cost(self, cost: float) -> None:
        with pytest.raises(ValueError, match="finite and non-negative"):
            register_eval_profile(
                EvalProfileSlot(name="test-invalid-cost", estimated_cost_usd=cost)
            )

    def test_register_allows_zero_cost_local_profile(self) -> None:
        slot = EvalProfileSlot(name="test-zero-cost", estimated_cost_usd=0.0)
        try:
            register_eval_profile(slot)
            assert get_eval_profile("test-zero-cost") is slot
        finally:
            unregister_eval_profile("test-zero-cost")

    def test_unregister_builtin_raises(self) -> None:
        """Built-in slots cannot be removed - they're load-bearing for back-compat."""
        with pytest.raises(ValueError, match="built-in"):
            unregister_eval_profile("full")
        # Confirm it's still registered.
        assert get_eval_profile("full") is not None

    def test_unregister_unknown_returns_false(self) -> None:
        assert unregister_eval_profile("never-registered-xyz") is False

    def test_unregister_returns_true_on_success(self) -> None:
        register_eval_profile(EvalProfileSlot(name="test-unreg-target"))
        assert unregister_eval_profile("test-unreg-target") is True
        assert get_eval_profile("test-unreg-target") is None

    def test_estimated_cost_uses_slot_override(self) -> None:
        """When a slot declares estimated_cost_usd, _estimated_profile_cost uses it."""
        slot = EvalProfileSlot(name="test-cost-override", estimated_cost_usd=0.42)
        try:
            register_eval_profile(slot)
            assert _estimated_profile_cost("test-cost-override") == 0.42
        finally:
            unregister_eval_profile("test-cost-override")

    def test_estimated_cost_falls_back_for_legacy_slots(self) -> None:
        """Built-in slots without estimated_cost_usd fall back to the mode-based estimator."""
        # Built-in slots should have estimated_cost_usd=None; cost comes from the legacy path.
        full_slot = get_eval_profile("full")
        assert full_slot is not None
        assert full_slot.estimated_cost_usd is None
        # Cost should be > 0 from the mode-based estimator.
        assert _estimated_profile_cost("full") > 0
        assert _estimated_profile_cost("fast") > 0
        assert _estimated_profile_cost("lite") > 0

    def test_estimated_cost_falls_back_for_unregistered_name(self) -> None:
        """An unregistered profile name uses the legacy mode-based estimator (full default)."""
        # "does-not-exist" hits the else branch → "full"-equivalent estimate.
        assert _estimated_profile_cost("does-not-exist") > 0


class TestProfileRecipe:
    def test_role_assignments_drops_none(self) -> None:
        recipe = ProfileRecipe(
            reasoning="grok-4.3",
            writing="gemini-3.1-flash-lite",
            utility=None,  # not assigned
        )
        roles = recipe.role_assignments()
        assert roles == {
            "reasoning": "grok-4.3",
            "writing": "gemini-3.1-flash-lite",
        }

    def test_role_assignments_includes_extra(self) -> None:
        recipe = ProfileRecipe(
            reasoning="grok-4.3",
            extra={"future_role": "some-model"},
        )
        roles = recipe.role_assignments()
        assert roles["future_role"] == "some-model"

    def test_role_assignments_drops_empty_extra_values(self) -> None:
        recipe = ProfileRecipe(
            reasoning="grok-4.3",
            extra={"future_role": "", "other": "real-model"},
        )
        roles = recipe.role_assignments()
        assert "future_role" not in roles
        assert roles["other"] == "real-model"

    def test_recipe_is_immutable(self) -> None:
        """ProfileRecipe is frozen - mutation should raise."""
        recipe = ProfileRecipe(reasoning="grok-4.3")
        with pytest.raises(AttributeError):
            recipe.reasoning = "claude-opus-4-8"  # type: ignore[misc]
