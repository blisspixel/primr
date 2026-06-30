import json
from pathlib import Path

import pytest

from primr.core.stage_eval_scorecard import (
    StageQualityEvidence,
    build_stage_eval_scorecard,
    load_stage_quality_evidence,
    write_stage_eval_scorecard_json,
    write_stage_eval_scorecard_markdown,
)
from primr.core.stage_route_comparison import StageRouteComparisonRow


def _route(
    backend_id: str,
    *,
    attempts: int = 2,
    failed_attempts: int = 0,
    actual_cost_usd: float = 0.001,
) -> StageRouteComparisonRow:
    return StageRouteComparisonRow(
        stage_id="fast.scrape_summary",
        backend_id=backend_id,
        backend_kind="cloud_api",
        billing_mode="api_dollars",
        inference_profile="cloud",
        attempts=attempts,
        selected_attempts=max(0, attempts - failed_attempts),
        fallback_attempts=0,
        failed_attempts=failed_attempts,
        actual_input_tokens=100,
        actual_output_tokens=20,
        actual_cached_input_tokens=10,
        actual_cost_usd=actual_cost_usd,
        avg_duration_seconds=1.25,
    )


def test_stage_eval_scorecard_classifies_review_statuses() -> None:
    rows = build_stage_eval_scorecard(
        route_rows=[
            _route("gemini-flash", actual_cost_usd=0.002),
            _route("local-qwen", failed_attempts=1, actual_cost_usd=0.0),
            _route("openai-nano", actual_cost_usd=0.001),
        ],
        quality_evidence=[
            StageQualityEvidence(
                stage_id="fast.scrape_summary",
                backend_id="gemini-flash",
                quality_score=86.0,
                sample_size=2,
                source="llm-judge",
            ),
            StageQualityEvidence(
                stage_id="fast.scrape_summary",
                backend_id="gemini-flash",
                quality_score=90.0,
                sample_size=1,
                source="human-review",
            ),
            StageQualityEvidence(
                stage_id="fast.scrape_summary",
                backend_id="local-qwen",
                quality_score=92.0,
                sample_size=2,
                source="llm-judge",
            ),
        ],
        min_quality_score=85.0,
    )

    by_backend = {row.backend_id: row for row in rows}
    assert by_backend["gemini-flash"].review_status == "candidate_for_human_review"
    assert by_backend["gemini-flash"].quality_score == 87.33
    assert by_backend["gemini-flash"].quality_sample_size == 3
    assert by_backend["gemini-flash"].quality_sources == ("human-review", "llm-judge")

    assert by_backend["local-qwen"].review_status == "needs_reliability_review"
    assert by_backend["local-qwen"].blockers == ("failure_rate_above_threshold",)
    assert by_backend["openai-nano"].review_status == "needs_quality_eval"
    assert by_backend["openai-nano"].blockers == ("missing_quality_evidence",)


def test_stage_eval_scorecard_writes_body_free_artifacts(tmp_path: Path) -> None:
    rows = build_stage_eval_scorecard(
        route_rows=[_route("gemini-flash")],
        quality_evidence=[
            StageQualityEvidence(
                stage_id="fast.scrape_summary",
                backend_id="gemini-flash",
                quality_score=80.0,
                sample_size=1,
                source="semantic-eval",
            )
        ],
        min_quality_score=85.0,
    )
    json_path = tmp_path / "scorecard.json"
    md_path = tmp_path / "scorecard.md"

    write_stage_eval_scorecard_json(
        json_path,
        rows=rows,
        min_quality_score=85.0,
        max_failure_rate=0.0,
    )
    write_stage_eval_scorecard_markdown(md_path, rows=rows)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["decision_policy"] == "candidate_for_human_review_only"
    assert payload["rows"][0]["review_status"] == "quality_below_bar"
    assert "prompt" not in json_path.read_text(encoding="utf-8")
    assert "response" not in md_path.read_text(encoding="utf-8")
    assert "| fast.scrape_summary | gemini-flash | cloud | quality_below_bar |" in (
        md_path.read_text(encoding="utf-8")
    )


def test_stage_eval_scorecard_prioritizes_missing_route_observations() -> None:
    rows = build_stage_eval_scorecard(
        route_rows=[_route("gemini-flash", attempts=0)],
        quality_evidence=[],
        min_quality_score=85.0,
    )

    assert rows[0].review_status == "needs_route_observations"
    assert rows[0].blockers == (
        "no_route_observations",
        "missing_quality_evidence",
    )


def test_load_stage_quality_evidence_accepts_schema_object(tmp_path: Path) -> None:
    path = tmp_path / "quality.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "quality_evidence": [
                    {
                        "stage_id": "fast.scrape_summary",
                        "backend_id": "gemini-flash",
                        "quality_score": 91.5,
                        "sample_size": 4,
                        "source": "semantic-eval",
                        "prompt": "ignored",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = load_stage_quality_evidence(path)

    assert rows == [
        StageQualityEvidence(
            stage_id="fast.scrape_summary",
            backend_id="gemini-flash",
            quality_score=91.5,
            sample_size=4,
            source="semantic-eval",
        )
    ]


def test_load_stage_quality_evidence_rejects_invalid_score(tmp_path: Path) -> None:
    path = tmp_path / "quality.json"
    path.write_text(
        json.dumps(
            {
                "quality_evidence": [
                    {
                        "stage_id": "fast.scrape_summary",
                        "backend_id": "gemini-flash",
                        "quality_score": 101,
                        "sample_size": 1,
                        "source": "semantic-eval",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="between 0 and 100"):
        load_stage_quality_evidence(path)
