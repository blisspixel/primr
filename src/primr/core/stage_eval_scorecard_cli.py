"""CLI-facing helpers for routed-stage eval scorecards."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from primr.core.stage_eval_scorecard import (
    build_stage_eval_scorecard,
    load_stage_quality_evidence,
    write_stage_eval_scorecard_json,
    write_stage_eval_scorecard_markdown,
)
from primr.core.stage_route_comparison import (
    compare_stage_routes,
    find_run_state_files,
    load_stage_route_records,
)


@dataclass(frozen=True)
class StageEvalScorecardArtifacts:
    json_path: Path
    markdown_path: Path
    route_files: int
    route_rows: int
    quality_evidence_rows: int
    scorecard_rows: int


def write_stage_eval_scorecard_from_files(
    *,
    route_root: Path,
    quality_path: Path,
    output_dir: Path,
    stage_id: str | None,
    min_quality_score: float,
    max_failure_rate: float,
) -> StageEvalScorecardArtifacts:
    """Write review-only scorecard artifacts from route ledgers and eval evidence."""

    route_files = find_run_state_files(route_root)
    route_records = load_stage_route_records(route_files)
    route_rows = compare_stage_routes(route_records, stage_id=stage_id)
    quality_evidence = load_stage_quality_evidence(quality_path)
    scorecard_rows = build_stage_eval_scorecard(
        route_rows=route_rows,
        quality_evidence=quality_evidence,
        min_quality_score=min_quality_score,
        max_failure_rate=max_failure_rate,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stage_eval_scorecard.json"
    markdown_path = output_dir / "stage_eval_scorecard.md"
    write_stage_eval_scorecard_json(
        json_path,
        rows=scorecard_rows,
        min_quality_score=min_quality_score,
        max_failure_rate=max_failure_rate,
    )
    title = "Stage Eval Scorecard" if stage_id is None else f"Stage Eval Scorecard: {stage_id}"
    write_stage_eval_scorecard_markdown(markdown_path, rows=scorecard_rows, title=title)
    return StageEvalScorecardArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        route_files=len(route_files),
        route_rows=len(route_rows),
        quality_evidence_rows=len(quality_evidence),
        scorecard_rows=len(scorecard_rows),
    )
