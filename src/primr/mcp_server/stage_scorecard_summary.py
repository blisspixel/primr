"""MCP resource for compact stage eval scorecard summaries."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource

STAGE_SCORECARD_SUMMARY_URI = "primr://eval/stage_scorecard"
STAGE_SCORECARD_SUMMARY_RESOURCE = Resource(
    uri=f"{STAGE_SCORECARD_SUMMARY_URI}/{{eval_id}}",
    name="Stage Eval Scorecard Summary by Eval ID",
    description=(
        "Compact routed-stage scorecard summary for one eval id. Returns row-level "
        "routing, quality-score, status, and blocker fields without prompts, "
        "responses, quality-source bodies, report bodies, or raw run-state content."
    ),
    mime_type="application/json",
)
_EVAL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def read_stage_scorecard_summary_resource(uri: str) -> list[ReadResourceContents]:
    """Read a compact stage eval scorecard summary from output/evals/{eval_id}."""

    eval_id = _eval_id_from_uri(uri)
    if eval_id is None:
        return _json_resource(
            {
                "error": "invalid_eval_id",
                "message": "Stage scorecard eval_id must be a simple path segment.",
                "resource": STAGE_SCORECARD_SUMMARY_URI,
                "summary_count": 0,
                "full_content_included": False,
            }
        )

    scorecard_path = Path("output") / "evals" / eval_id / "stage_eval_scorecard.json"
    metadata = _artifact_metadata(scorecard_path)
    if not metadata["exists"]:
        return _json_resource(
            {
                "error": "stage_scorecard_not_found",
                "message": f"Eval {eval_id} has no stage_eval_scorecard.json artifact",
                "resource": STAGE_SCORECARD_SUMMARY_URI,
                "eval_id": eval_id,
                "summary_count": 0,
                "scorecard_path": str(scorecard_path),
                "full_content_included": False,
            }
        )

    payload = _read_json_object(scorecard_path)
    if payload is None:
        return _json_resource(
            {
                "schema_version": "1.0",
                "resource": STAGE_SCORECARD_SUMMARY_URI,
                "eval_id": eval_id,
                "summary_count": 1,
                "full_content_included": False,
                "summary": {
                    **metadata,
                    "parsed": False,
                    "parse_error": "invalid_json_or_non_object",
                    "raw_rows_included": False,
                    "quality_sources_included": False,
                },
            }
        )

    rows = [_row_summary(row) for row in _row_payloads(payload)]
    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": STAGE_SCORECARD_SUMMARY_URI,
            "eval_id": eval_id,
            "summary_count": 1,
            "full_content_included": False,
            "summary": {
                **metadata,
                "parsed": True,
                "raw_rows_included": False,
                "quality_sources_included": False,
                "decision_policy": _scalar_or_none(payload.get("decision_policy")),
                "min_quality_score": _number_or_none(payload.get("min_quality_score")),
                "max_failure_rate": _number_or_none(payload.get("max_failure_rate")),
                "row_count": len(rows),
                "candidate_count": sum(
                    1 for row in rows if row["review_status"] == "candidate_for_human_review"
                ),
                "status_counts": _value_counts(row["review_status"] for row in rows),
                "blocker_counts": _value_counts(
                    blocker for row in rows for blocker in row["blockers"]
                ),
                "stage_counts": _value_counts(row["stage_id"] for row in rows),
                "backend_counts": _value_counts(row["backend_id"] for row in rows),
                "route_totals": _route_totals(rows),
                "quality_score_stats": _quality_score_stats(rows),
                "rows": rows,
            },
        }
    )


def _eval_id_from_uri(uri: str) -> str | None:
    prefix = f"{STAGE_SCORECARD_SUMMARY_URI}/"
    if not uri.startswith(prefix):
        return None
    raw_eval_id = uri[len(prefix) :].split("?", 1)[0]
    if not _EVAL_ID_RE.fullmatch(raw_eval_id):
        return None
    return raw_eval_id


def _artifact_metadata(path: Path) -> dict[str, Any]:
    exists = path.exists() and path.is_file()
    metadata: dict[str, Any] = {
        "artifact_type": "stage_eval_scorecard",
        "file_name": path.name,
        "file_path": str(path),
        "exists": exists,
    }
    if not exists:
        return metadata
    stat = path.stat()
    metadata.update(
        {
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "content_hash": f"sha256:{_hash_file(path)}",
        }
    )
    return metadata


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _row_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _row_summary(row: dict[str, Any]) -> dict[str, Any]:
    blockers = row.get("blockers")
    return {
        "stage_id": _text_or_empty(row.get("stage_id")),
        "backend_id": _text_or_empty(row.get("backend_id")),
        "inference_profile": _text_or_empty(row.get("inference_profile")),
        "review_status": _text_or_empty(row.get("review_status")),
        "blockers": sorted(str(item) for item in blockers) if isinstance(blockers, list) else [],
        "attempts": _int_or_zero(row.get("attempts")),
        "selected_attempts": _int_or_zero(row.get("selected_attempts")),
        "fallback_attempts": _int_or_zero(row.get("fallback_attempts")),
        "failed_attempts": _int_or_zero(row.get("failed_attempts")),
        "failure_rate": _number_or_none(row.get("failure_rate")),
        "actual_cost_usd": _number_or_none(row.get("actual_cost_usd")),
        "avg_duration_seconds": _number_or_none(row.get("avg_duration_seconds")),
        "quality_score": _number_or_none(row.get("quality_score")),
        "quality_sample_size": _int_or_zero(row.get("quality_sample_size")),
    }


def _route_totals(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    return {
        "attempts": sum(row["attempts"] for row in rows),
        "selected_attempts": sum(row["selected_attempts"] for row in rows),
        "fallback_attempts": sum(row["fallback_attempts"] for row in rows),
        "failed_attempts": sum(row["failed_attempts"] for row in rows),
        "actual_cost_usd": round(sum(row["actual_cost_usd"] or 0.0 for row in rows), 8),
    }


def _quality_score_stats(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    scores = [row["quality_score"] for row in rows if row["quality_score"] is not None]
    if not scores:
        return {"count": 0, "min": None, "max": None, "average": None}
    return {
        "count": len(scores),
        "min": min(scores),
        "max": max(scores),
        "average": round(sum(scores) / len(scores), 2),
    }


def _value_counts(values: Any) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _text_or_empty(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _scalar_or_none(value: Any) -> str | int | float | bool | None:
    if isinstance(value, str | int | float | bool):
        return value
    return None


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return None


def _int_or_zero(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    return 0


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _json_resource(data: dict[str, Any]) -> list[ReadResourceContents]:
    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]
