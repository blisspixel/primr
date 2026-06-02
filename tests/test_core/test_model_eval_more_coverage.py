"""Additional coverage for primr.core.model_eval.

Focuses on pure data/formatting + control-flow paths that the existing suite
leaves uncovered: the LLM-judge loop (via an injected ``invoke`` callable),
the public judge wrappers (with their network clients mocked), profile-cost
recipe resolution, decision-gate branches, eval-id/company sanitization, and
degenerate-input handling. No real company names; all I/O is to tmp_path and
all model calls are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from primr.core.model_eval import (
    EvalProfileSlot,
    EvaluationResult,
    JudgeCallResult,
    LLMJudgeMetadata,
    LLMJudgeRow,
    ProfileRecipe,
    ProfileSummary,
    ReportMetrics,
    _company_similarity,
    _compute_missing_pairs,
    _decision_table,
    _estimated_profile_cost,
    _extract_company_from_filename,
    _find_profile_reports,
    _load_fast_companies_from_usage,
    _load_manifest_targets,
    _model_slug,
    _normalize_company_key,
    _run_llm_judge,
    _safe_eval_dir,
    _sanitize_target_company,
    _summarize_profile,
    _winner_majority_label,
    register_eval_profile,
    run_grok_judge,
    run_local_judge,
    unregister_eval_profile,
    write_fast_feedback_guidance,
    write_local_judge_sweep_markdown,
    write_local_judge_sweep_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _metric(
    *,
    company: str = "ExampleCo",
    profile: str = "full",
    report_path: Path | None = None,
    quality_score: float = 80.0,
    word_count: int = 5000,
    citations_total: int = 20,
    trust_score: float = 90.0,
    decision_utility_score: float = 90.0,
    reuse_quality_score: float = 70.0,
    trust_gate_passed: bool = True,
    confidence_labels: int = 30,
    citation_density: float = 2.0,
    scaffolding_leaks: int = 0,
) -> ReportMetrics:
    return ReportMetrics(
        company=company,
        profile=profile,
        report_path=report_path or Path("unused.md"),
        quality_score=quality_score,
        word_count=word_count,
        estimated_pages=word_count / 500.0,
        citation_density=citation_density,
        citations_total=citations_total,
        key_sections_found=7,
        key_sections_total=8,
        confidence_labels=confidence_labels,
        trust_score=trust_score,
        decision_utility_score=decision_utility_score,
        reuse_quality_score=reuse_quality_score,
        trust_gate_passed=trust_gate_passed,
        utility_per_dollar=0.0,
        scaffolding_leaks=scaffolding_leaks,
    )


def _eval_result_with_pair(tmp_path: Path) -> EvaluationResult:
    """Build an EvaluationResult with a matched baseline/candidate pair on disk."""
    base_path = tmp_path / "base.md"
    cand_path = tmp_path / "cand.md"
    base_path.write_text("# ExampleCo baseline report\nLots of detail.\n", encoding="utf-8")
    cand_path.write_text("# ExampleCo candidate report\nLess detail.\n", encoding="utf-8")
    base = _metric(profile="full", report_path=base_path, quality_score=88.0)
    cand = _metric(profile="fast", report_path=cand_path, quality_score=80.0)
    return EvaluationResult(
        eval_id="eval-judge",
        eval_root=tmp_path,
        baseline="full",
        profile_summaries=[
            ProfileSummary(
                profile="full",
                report_count=1,
                avg_quality=88.0,
                avg_trust=90.0,
                avg_decision_utility=90.0,
                avg_reuse_quality=70.0,
                avg_word_count=5000.0,
                avg_pages=10.0,
                avg_citation_density=2.0,
                avg_utility_per_dollar=100.0,
                trust_pass_rate=1.0,
                estimated_cost_usd=0.9,
            ),
            ProfileSummary(
                profile="fast",
                report_count=1,
                avg_quality=80.0,
                avg_trust=88.0,
                avg_decision_utility=85.0,
                avg_reuse_quality=65.0,
                avg_word_count=4000.0,
                avg_pages=8.0,
                avg_citation_density=1.8,
                avg_utility_per_dollar=200.0,
                trust_pass_rate=1.0,
                estimated_cost_usd=0.4,
            ),
        ],
        metrics=[base, cand],
        missing_pairs=[],
        decision_rows=[],
        scorecard_md=tmp_path / "scorecard.md",
        scorecard_csv=tmp_path / "scorecard.csv",
    )


def _judge_json(baseline: float, candidate: float, rationale: str = "ok") -> str:
    aspects = lambda v: {  # noqa: E731
        "strategic_usefulness": v,
        "evidence_quality": v,
        "clarity_coherence": v,
        "actionability": v,
        "uncertainty_calibration": v,
        "coverage_completeness": v,
    }
    return json.dumps(
        {
            "winner_profile": "baseline",
            "baseline_aspects": aspects(baseline),
            "candidate_aspects": aspects(candidate),
            "rationale": rationale,
        }
    )


# ---------------------------------------------------------------------------
# _run_llm_judge core loop
# ---------------------------------------------------------------------------


def test_run_llm_judge_baseline_wins(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)
    calls: list[str] = []

    def invoke(prompt: str) -> JudgeCallResult:
        calls.append(prompt)
        return JudgeCallResult(
            text=_judge_json(90.0, 70.0), input_tokens=100, output_tokens=50, cost_usd=0.01
        )

    rows, total = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=10,
        passes=1,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.winner_profile == "full"
    assert row.baseline_score > row.candidate_score
    assert row.passes == 1
    assert total == pytest.approx(0.01)
    assert calls  # prompt was built and the report excerpts read


def test_run_llm_judge_candidate_wins(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)

    def invoke(prompt: str) -> JudgeCallResult:
        return JudgeCallResult(
            text=_judge_json(60.0, 95.0), input_tokens=1, output_tokens=1, cost_usd=0.0
        )

    rows, _ = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=10,
        passes=1,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    assert rows[0].winner_profile == "fast"


def test_run_llm_judge_tie_within_one_point(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)

    def invoke(prompt: str) -> JudgeCallResult:
        return JudgeCallResult(
            text=_judge_json(80.0, 80.0), input_tokens=1, output_tokens=1, cost_usd=0.0
        )

    rows, _ = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=10,
        passes=1,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    assert rows[0].winner_profile == "tie"


def test_run_llm_judge_averages_multiple_passes(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)
    payloads = [_judge_json(90.0, 70.0), _judge_json(70.0, 90.0)]
    idx = {"i": 0}

    def invoke(prompt: str) -> JudgeCallResult:
        text = payloads[idx["i"] % len(payloads)]
        idx["i"] += 1
        return JudgeCallResult(text=text, input_tokens=1, output_tokens=1, cost_usd=0.005)

    rows, total = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=10,
        passes=2,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    # Two opposing passes average to a tie; both passes counted.
    assert rows[0].passes == 2
    assert rows[0].winner_profile == "tie"
    assert total == pytest.approx(0.01)


def test_run_llm_judge_cost_cap_stops_passes(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)
    n_calls = {"n": 0}

    def invoke(prompt: str) -> JudgeCallResult:
        n_calls["n"] += 1
        return JudgeCallResult(
            text=_judge_json(90.0, 70.0), input_tokens=1, output_tokens=1, cost_usd=5.0
        )

    rows, total = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=10,
        passes=5,
        max_cost_usd=1.0,  # exceeded after first pass
        invoke=invoke,
    )
    # First pass runs, then the cap short-circuits the remaining passes.
    assert n_calls["n"] == 1
    assert rows[0].passes == 1
    assert total == pytest.approx(5.0)


def test_run_llm_judge_malformed_json_falls_back_to_quality(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)

    def invoke(prompt: str) -> JudgeCallResult:
        return JudgeCallResult(
            text="not json at all", input_tokens=1, output_tokens=1, cost_usd=0.0
        )

    rows, _ = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=10,
        passes=1,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    # Falls back to each metric's quality_score (88 vs 80) -> baseline wins.
    assert rows[0].winner_profile == "full"
    assert rows[0].baseline_score == pytest.approx(88.0)
    assert rows[0].candidate_score == pytest.approx(80.0)


def test_run_llm_judge_skips_when_candidate_missing(tmp_path: Path):
    result = _eval_result_with_pair(tmp_path)

    def invoke(prompt: str) -> JudgeCallResult:  # pragma: no cover - must not run
        raise AssertionError("invoke should not be called when candidate missing")

    rows, total = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="lite",  # no lite metric in fixture
        max_pairs=10,
        passes=1,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    assert rows == []
    assert total == 0.0


def test_run_llm_judge_respects_max_pairs(tmp_path: Path):
    # Two companies in baseline + candidate, but max_pairs=1.
    base_a = tmp_path / "a_base.md"
    cand_a = tmp_path / "a_cand.md"
    base_b = tmp_path / "b_base.md"
    cand_b = tmp_path / "b_cand.md"
    for p in (base_a, cand_a, base_b, cand_b):
        p.write_text("# report\n", encoding="utf-8")
    metrics = [
        _metric(company="AlphaCo", profile="full", report_path=base_a),
        _metric(company="AlphaCo", profile="fast", report_path=cand_a),
        _metric(company="BetaCo", profile="full", report_path=base_b),
        _metric(company="BetaCo", profile="fast", report_path=cand_b),
    ]
    result = EvaluationResult(
        eval_id="e",
        eval_root=tmp_path,
        baseline="full",
        profile_summaries=[],
        metrics=metrics,
        missing_pairs=[],
        decision_rows=[],
        scorecard_md=tmp_path / "s.md",
        scorecard_csv=tmp_path / "s.csv",
    )

    def invoke(prompt: str) -> JudgeCallResult:
        return JudgeCallResult(
            text=_judge_json(90.0, 70.0), input_tokens=1, output_tokens=1, cost_usd=0.0
        )

    rows, _ = _run_llm_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=1,
        passes=1,
        max_cost_usd=0.0,
        invoke=invoke,
    )
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Public judge wrappers (network clients mocked)
# ---------------------------------------------------------------------------


def test_run_grok_judge_wraps_invoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _eval_result_with_pair(tmp_path)

    usage = {"input_tokens": 0, "output_tokens": 0}

    import primr.ai.grok_client as grok_client

    def fake_usage() -> dict[str, int]:
        return dict(usage)

    def fake_grok_llm(prompt: str, *, model: str, temperature: float, max_tokens: int) -> str:
        usage["input_tokens"] += 1000
        usage["output_tokens"] += 500
        return _judge_json(90.0, 70.0)

    monkeypatch.setattr(grok_client, "get_grok_session_usage", fake_usage)
    monkeypatch.setattr(grok_client, "grok_llm", fake_grok_llm)

    rows, total = run_grok_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=5,
        passes=1,
        max_cost_usd=0.0,
        model="grok-4.3",
    )
    assert len(rows) == 1
    assert rows[0].winner_profile == "full"
    # Token delta produced a positive Grok cost.
    assert total > 0.0


def test_run_local_judge_wraps_invoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _eval_result_with_pair(tmp_path)

    import primr.ai.openai_compatible_client as oai

    class FakeResult:
        text = _judge_json(60.0, 95.0)
        prompt_tokens = 10
        completion_tokens = 5

    def fake_chat_completion(prompt: str, **kwargs: Any) -> FakeResult:
        return FakeResult()

    monkeypatch.setattr(oai, "chat_completion", fake_chat_completion)

    rows, total = run_local_judge(
        eval_result=result,
        baseline_profile="full",
        candidate_profile="fast",
        max_pairs=5,
        passes=1,
        max_cost_usd=0.0,
        model="qwen2.5:14b",
        base_url="http://localhost:11434/v1",
    )
    assert len(rows) == 1
    assert rows[0].winner_profile == "fast"
    # Local judging is free.
    assert total == 0.0


# ---------------------------------------------------------------------------
# _estimated_profile_cost recipe path
# ---------------------------------------------------------------------------


def test_estimated_profile_cost_recipe_slot_without_explicit_cost():
    """A registered recipe slot with no explicit cost falls through to the
    legacy mode-based estimator (still returns a positive number)."""
    slot = EvalProfileSlot(
        name="test-recipe-no-cost",
        recipe=ProfileRecipe(reasoning="grok-4.3", writing="gemini-3.1-flash-lite"),
        estimated_cost_usd=None,
    )
    try:
        register_eval_profile(slot)
        assert _estimated_profile_cost("test-recipe-no-cost") > 0
    finally:
        unregister_eval_profile("test-recipe-no-cost")


# ---------------------------------------------------------------------------
# _summarize_profile aggregation + utility_per_dollar backfill
# ---------------------------------------------------------------------------


def test_summarize_profile_empty_returns_zeroed_summary():
    summary = _summarize_profile("full", [])
    assert summary.report_count == 0
    assert summary.avg_quality == 0.0
    assert summary.trust_pass_rate == 0.0
    # Cost is still resolved even with no reports.
    assert summary.estimated_cost_usd > 0


def test_summarize_profile_backfills_utility_per_dollar():
    metrics = [
        _metric(decision_utility_score=90.0, trust_gate_passed=True),
        _metric(decision_utility_score=60.0, trust_gate_passed=False),
    ]
    summary = _summarize_profile("fast", metrics)
    assert summary.report_count == 2
    assert summary.avg_decision_utility == pytest.approx(75.0)
    assert summary.trust_pass_rate == pytest.approx(0.5)
    # Per-row utility_per_dollar was backfilled from 0.0.
    assert all(m.utility_per_dollar > 0 for m in metrics)
    expected = round(90.0 / max(0.01, summary.estimated_cost_usd), 2)
    assert metrics[0].utility_per_dollar == expected


# ---------------------------------------------------------------------------
# _decision_table branches
# ---------------------------------------------------------------------------


def _summary(profile: str, **kw: Any) -> ProfileSummary:
    base: dict[str, Any] = {
        "profile": profile,
        "report_count": 1,
        "avg_quality": 80.0,
        "avg_trust": 90.0,
        "avg_decision_utility": 90.0,
        "avg_reuse_quality": 70.0,
        "avg_word_count": 5000.0,
        "avg_pages": 10.0,
        "avg_citation_density": 2.0,
        "avg_utility_per_dollar": 100.0,
        "trust_pass_rate": 1.0,
        "estimated_cost_usd": 1.0,
    }
    base.update(kw)
    return ProfileSummary(**base)  # type: ignore[arg-type]


def test_decision_table_no_baseline_reports():
    rows = _decision_table([_summary("full", report_count=0)], "full", 0.8, 0.5)
    assert rows == ["Baseline has no reports. Generate or place baseline outputs first."]


def test_decision_table_missing_candidate():
    summaries = [_summary("full"), _summary("fast", report_count=0)]
    rows = _decision_table(summaries, "full", 0.8, 0.5)
    assert any("baseline" in r for r in rows)
    assert any("MISSING" in r for r in rows)


def test_decision_table_fail_trust():
    summaries = [_summary("full"), _summary("fast", trust_pass_rate=0.5)]
    rows = _decision_table(summaries, "full", 0.8, 0.5)
    assert any("FAIL_TRUST" in r for r in rows)


def test_decision_table_pass_when_cheaper_and_useful():
    summaries = [
        _summary("full", avg_decision_utility=90.0, estimated_cost_usd=1.0),
        _summary("fast", avg_decision_utility=85.0, estimated_cost_usd=0.4),
    ]
    rows = _decision_table(summaries, "full", 0.8, 0.5)
    fast_row = next(r for r in rows if r.startswith("fast:"))
    assert "PASS" in fast_row


def test_decision_table_fail_when_too_expensive():
    summaries = [
        _summary("full", avg_decision_utility=90.0, estimated_cost_usd=1.0),
        _summary("fast", avg_decision_utility=85.0, estimated_cost_usd=0.9),
    ]
    rows = _decision_table(summaries, "full", 0.8, 0.5)
    fast_row = next(r for r in rows if r.startswith("fast:"))
    assert "FAIL" in fast_row
    assert "FAIL_TRUST" not in fast_row


# ---------------------------------------------------------------------------
# eval-id / company sanitization
# ---------------------------------------------------------------------------


def test_safe_eval_dir_accepts_clean_id(tmp_path: Path):
    out = _safe_eval_dir(tmp_path, "eval-2026.05")
    assert out == (tmp_path / "eval-2026.05").resolve()


@pytest.mark.parametrize("bad", ["../escape", "a/b", "", "x" * 129, "with space"])
def test_safe_eval_dir_rejects_unsafe_id(tmp_path: Path, bad: str):
    with pytest.raises(ValueError):
        _safe_eval_dir(tmp_path, bad)


def test_sanitize_target_company_strips_separators_and_glob():
    assert _sanitize_target_company("a/b\\c") == "a_b_c"
    assert _sanitize_target_company("../etc") == "__etc"
    assert _sanitize_target_company("Foo*[bar]?") == "Foo__bar__"
    assert _sanitize_target_company("") == "Unknown_Company"
    assert _sanitize_target_company("   ") == "Unknown_Company"


# ---------------------------------------------------------------------------
# manifest + usage loaders, missing pairs, company helpers
# ---------------------------------------------------------------------------


def test_load_manifest_targets_dedupes_and_supports_alt_column(tmp_path: Path):
    manifest = tmp_path / "m.csv"
    manifest.write_text(
        "company_name\nAlphaCo\nAlphaCo\nBetaCo\n",
        encoding="utf-8",
    )
    assert _load_manifest_targets(manifest) == ["AlphaCo", "BetaCo"]


def test_load_manifest_targets_missing_file(tmp_path: Path):
    assert _load_manifest_targets(tmp_path / "nope.csv") == []


def test_load_fast_companies_filters_mode_and_dedupes(tmp_path: Path):
    usage = tmp_path / "usage.json"
    usage.write_text(
        json.dumps(
            [
                {"mode": "fast", "company": "AlphaCo"},
                {"mode": "complete", "company": "BetaCo"},
                {"mode": "FAST", "company": "AlphaCo"},
                {"mode": "fast", "company": "GammaCo"},
            ]
        ),
        encoding="utf-8",
    )
    assert _load_fast_companies_from_usage(usage) == ["AlphaCo", "GammaCo"]


def test_load_fast_companies_missing_file(tmp_path: Path):
    assert _load_fast_companies_from_usage(tmp_path / "absent.json") == []


def test_load_fast_companies_malformed_json_returns_empty(tmp_path: Path):
    usage = tmp_path / "bad.json"
    usage.write_text("{not valid json", encoding="utf-8")
    assert _load_fast_companies_from_usage(usage) == []


def test_compute_missing_pairs_marks_absent_combinations():
    metrics = [_metric(company="AlphaCo", profile="full")]
    missing = _compute_missing_pairs(["AlphaCo", "BetaCo"], ("full", "fast"), metrics)
    assert ("AlphaCo", "fast") in missing
    assert ("BetaCo", "full") in missing
    assert ("BetaCo", "fast") in missing
    assert ("AlphaCo", "full") not in missing


def test_extract_company_from_filename_strips_markers(tmp_path: Path):
    p = tmp_path / "Alpha_Co_AI_Strategy_02-25-2026.md"
    assert _extract_company_from_filename(p) == "Alpha Co"
    p2 = tmp_path / "Beta_Co_Strategic_Overview.md"
    assert _extract_company_from_filename(p2) == "Beta Co"


def test_normalize_company_key_collapses_whitespace():
    assert _normalize_company_key("  Alpha   Co  ") == "alpha co"


def test_company_similarity_disjoint_is_zero():
    assert _company_similarity("Alpha", "Beta") == 0.0


def test_company_similarity_empty_inputs_zero():
    assert _company_similarity("", "Alpha") == 0.0


def test_model_slug_normalizes():
    assert _model_slug("Qwen2.5:14b-Instruct") == "qwen2-5-14b-instruct"
    assert _model_slug("///") == "model"


# ---------------------------------------------------------------------------
# _find_profile_reports degenerate inputs
# ---------------------------------------------------------------------------


def test_find_profile_reports_missing_dir_returns_empty(tmp_path: Path):
    assert _find_profile_reports(tmp_path / "nope", "full") == []


def test_find_profile_reports_ignores_non_strategic_files(tmp_path: Path):
    d = tmp_path / "full"
    d.mkdir()
    (d / "random_notes.md").write_text("# notes\n", encoding="utf-8")
    assert _find_profile_reports(d, "full") == []


# ---------------------------------------------------------------------------
# _winner_majority_label
# ---------------------------------------------------------------------------


def test_winner_majority_label_empty():
    assert _winner_majority_label({}) == "unknown"


def test_winner_majority_label_prefers_non_tie_on_tiebreak():
    # Equal counts: non-tie label should win the tiebreak.
    assert _winner_majority_label({"tie": 2, "full": 2}) == "full"


def test_winner_majority_label_highest_count():
    assert _winner_majority_label({"full": 3, "fast": 1}) == "full"


# ---------------------------------------------------------------------------
# sweep writers with empty rows (degenerate)
# ---------------------------------------------------------------------------


def test_sweep_summary_handles_empty_rows(tmp_path: Path):
    out = tmp_path / "summary.json"
    metadata = LLMJudgeMetadata(provider="local", model="qwen2.5:14b")
    write_local_judge_sweep_summary(
        out,
        eval_id="e",
        baseline_profile="full",
        candidate_profiles=[],
        results=[(metadata, [], 0.0)],
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["models_evaluated"] == 1
    assert payload["winner_counts"]["unknown"] == 1
    assert payload["results"][0]["rows"] == 0


def test_sweep_markdown_handles_empty_rows(tmp_path: Path):
    out = tmp_path / "summary.md"
    metadata = LLMJudgeMetadata(provider="local", model="qwen2.5:14b")
    write_local_judge_sweep_markdown(
        out,
        eval_id="e",
        baseline_profile="full",
        candidate_profiles=[],
        results=[(metadata, [], 0.0)],
    )
    text = out.read_text(encoding="utf-8")
    assert "Local Judge Sweep" in text
    assert "qwen2.5:14b" in text


# ---------------------------------------------------------------------------
# write_fast_feedback_guidance branch coverage
# ---------------------------------------------------------------------------


def test_fast_feedback_guidance_noop_without_fast_profile(tmp_path: Path):
    """When there are no fast metrics, the guidance file is not written."""
    out = tmp_path / "guidance.md"
    result = EvaluationResult(
        eval_id="e",
        eval_root=tmp_path,
        baseline="full",
        profile_summaries=[_summary("full")],
        metrics=[_metric(profile="full")],
        missing_pairs=[],
        decision_rows=[],
        scorecard_md=tmp_path / "s.md",
        scorecard_csv=tmp_path / "s.csv",
    )
    write_fast_feedback_guidance(out, eval_result=result, judge_rows=[])
    assert not out.exists()


def test_fast_feedback_guidance_emits_quality_gap_rules(tmp_path: Path):
    """Low-signal fast metrics trigger the conditional improvement rules and
    judge insights get folded in."""
    out = tmp_path / "guidance.md"
    fast_summary = _summary(
        "fast",
        avg_quality=60.0,
        avg_trust=80.0,
        avg_decision_utility=70.0,
    )
    fast_metric = _metric(
        profile="fast",
        word_count=3000,  # < 7200 -> depth rule
        citations_total=5,  # < 18 -> citation rule
        confidence_labels=10,  # < 24 -> calibration rule
        citation_density=0.5,  # < 1.2 -> citation rule
    )
    judge_rows = [
        LLMJudgeRow(
            company="AlphaCo",
            baseline_profile="full",
            candidate_profile="fast",
            winner_profile="full",
            baseline_score=88.0,
            candidate_score=70.0,
            baseline_aspects={"strategic_usefulness": 88.0},
            candidate_aspects={"strategic_usefulness": 60.0},  # < 80 -> insight
            passes=1,
            rationale="needs sharper recommendations",
            cost_usd=0.0,
        )
    ]
    result = EvaluationResult(
        eval_id="eval-fast",
        eval_root=tmp_path,
        baseline="full",
        profile_summaries=[fast_summary],
        metrics=[fast_metric],
        missing_pairs=[],
        decision_rows=[],
        scorecard_md=tmp_path / "s.md",
        scorecard_csv=tmp_path / "s.csv",
    )
    write_fast_feedback_guidance(out, eval_result=result, judge_rows=judge_rows)
    text = out.read_text(encoding="utf-8")
    assert "Fast Report Feedback Guidance" in text
    assert "citation density" in text
    assert "uncertainty calibration" in text.lower()
    assert "analytical depth" in text
    assert "decision utility" in text
    assert "trust discipline" in text
    # Judge insight about the low aspect score was incorporated.
    assert "strategic_usefulness" in text
