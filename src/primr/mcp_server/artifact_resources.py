"""Job-scoped artifact metadata MCP resources."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import AnyUrl, Resource

from primr.mcp_server.resource_auth import caller_owns_job_resource
from primr.mcp_server.server_context import MCPServerContext
from primr.output.artifact_inventory import (
    ArtifactRecord,
    classify_artifact,
    inventory_explicit_result,
)

ARTIFACT_METADATA_BY_JOB_URI = "primr://output/artifacts/by_job"
QA_SUMMARY_BY_JOB_URI = "primr://output/qa_summary/by_job"
USAGE_SUMMARY_BY_JOB_URI = "primr://output/usage_summary/by_job"
ARTIFACT_METADATA_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{ARTIFACT_METADATA_BY_JOB_URI}/{{job_id}}"),
    name="Artifact Metadata by Job ID",
    description=(
        "Compact metadata for output artifacts attached to one owned job. "
        "Returns semantic roles, paths, sizes, hashes, and timestamps without "
        "report body content."
    ),
    mimeType="application/json",
)
QA_SUMMARY_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{QA_SUMMARY_BY_JOB_URI}/{{job_id}}"),
    name="QA Summary by Job ID",
    description=(
        "Compact QA result summary for one owned job. Returns score, status, "
        "count, and metadata fields without detailed report body content."
    ),
    mimeType="application/json",
)
USAGE_SUMMARY_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{USAGE_SUMMARY_BY_JOB_URI}/{{job_id}}"),
    name="Usage and Cost Summary by Job ID",
    description=(
        "Compact usage, cost, timing, and approval metadata for one owned job. "
        "Reads run_manifest.json without returning full manifest contents."
    ),
    mimeType="application/json",
)


def read_artifact_metadata_by_job_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact artifact metadata for one job, with ownership gating."""
    match = re.match(rf"{re.escape(ARTIFACT_METADATA_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid artifact metadata URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    inventory = inventory_explicit_result(job.output_paths, expand_adjacent=True, include_hash=True)
    artifacts = [record.as_dict(index=index) for index, record in enumerate(inventory.records)]
    return _json_resource(
        {
            "schema_version": "1.1",
            "resource": ARTIFACT_METADATA_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "artifact_count": len(artifacts),
            "truncated": inventory.truncated,
            "full_content_included": False,
            "artifacts": artifacts,
        }
    )


def read_qa_summary_by_job_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact QA summary artifacts for one job, with ownership gating."""
    match = re.match(rf"{re.escape(QA_SUMMARY_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid QA summary URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    summaries = [
        _qa_artifact_summary(index, Path(path))
        for index, path in enumerate(job.output_paths)
        if _classify_artifact(Path(path)) == "qa_summary"
    ]
    if not summaries:
        return _json_resource(
            {
                "error": "qa_summary_not_found",
                "message": f"Job {job_id} has no attached QA summary artifact",
                "job_id": job_id,
                "status": job.get_status().value,
                "summary_count": 0,
            }
        )

    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": QA_SUMMARY_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "summary_count": len(summaries),
            "full_content_included": False,
            "summaries": summaries,
        }
    )


def read_usage_summary_by_job_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact usage and cost summaries for one job, with ownership gating."""
    match = re.match(rf"{re.escape(USAGE_SUMMARY_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid usage summary URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    manifest_paths = _job_manifest_paths(job.output_paths, job.job_id)
    summaries = [_usage_manifest_summary(index, path) for index, path in enumerate(manifest_paths)]
    if not summaries:
        return _json_resource(
            {
                "error": "usage_summary_not_found",
                "message": f"Job {job_id} has no run manifest available",
                "job_id": job_id,
                "status": job.get_status().value,
                "summary_count": 0,
            }
        )

    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": USAGE_SUMMARY_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "summary_count": len(summaries),
            "full_content_included": False,
            "summaries": summaries,
        }
    )


def _artifact_metadata(index: int, path: Path) -> dict[str, Any]:
    return ArtifactRecord.inspect(path, source="explicit", include_hash=True).as_dict(index=index)


def _job_manifest_paths(output_paths: list[str], job_id: str) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for output_path in output_paths:
        candidate = Path(output_path)
        explicit_manifest = _classify_artifact(candidate) == "run_manifest"
        manifest_path = candidate if explicit_manifest else candidate.parent / "run_manifest.json"
        normalized = manifest_path.resolve(strict=False)
        if normalized in seen or not manifest_path.exists() or not manifest_path.is_file():
            continue
        if not explicit_manifest:
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("job_id") != job_id:
                continue
        seen.add(normalized)
        paths.append(manifest_path)
    return paths


def _usage_manifest_summary(index: int, path: Path) -> dict[str, Any]:
    metadata = _artifact_metadata(index, path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "invalid_json",
            "full_content_included": False,
        }
    except OSError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "read_failed",
            "full_content_included": False,
        }

    if not isinstance(payload, dict):
        return {
            **metadata,
            "parsed": False,
            "parse_error": "non_object_json",
            "full_content_included": False,
        }

    estimate = _dict_payload(payload.get("estimate"))
    approval = _dict_payload(payload.get("approval"))
    budget = _dict_payload(payload.get("budget"))
    budget_enforcement = _dict_payload(budget.get("enforcement"))
    execution = _dict_payload(payload.get("execution"))
    artifacts = payload.get("artifacts")
    return {
        **metadata,
        "parsed": True,
        "full_content_included": False,
        "manifest_schema_version": payload.get("schema_version"),
        "mode": payload.get("mode"),
        "estimate": {
            "cost_usd": _number_or_none(estimate.get("cost_usd")),
            "time_minutes": _number_or_none(estimate.get("time_minutes")),
            "estimated_at": _scalar_or_none(estimate.get("estimated_at")),
        },
        "approval": {
            "approved": bool(approval.get("approved_at") or approval.get("bound_to_estimate")),
            "approved_at": _scalar_or_none(approval.get("approved_at")),
            "bound_to_estimate": bool(approval.get("bound_to_estimate")),
            "approved_by_present": bool(approval.get("approved_by")),
            "token_present": bool(approval.get("token")),
        },
        "budget": {
            "approved_ceiling_usd": _number_or_none(budget.get("approved_ceiling_usd")),
            "runtime_budget_active": bool(budget.get("runtime_budget_active")),
            "preflight": _scalar_or_none(budget_enforcement.get("preflight")),
            "runtime_checkpoints": bool(budget_enforcement.get("runtime_checkpoints")),
            "runtime": _scalar_or_none(budget_enforcement.get("runtime")),
            "checkpointed_stages": _string_list(budget_enforcement.get("checkpointed_stages")),
            "non_interruptible_required_tasks": _string_list(
                budget_enforcement.get("non_interruptible_required_tasks")
            ),
        },
        "execution": {
            "started_at": _scalar_or_none(execution.get("started_at")),
            "completed_at": _scalar_or_none(execution.get("completed_at")),
            "status": _scalar_or_none(execution.get("status")),
            "actual_cost_usd": _number_or_none(execution.get("actual_cost_usd")),
            "actual_time_minutes": _number_or_none(execution.get("actual_time_minutes")),
        },
        "artifact_count": len(artifacts) if isinstance(artifacts, list) else None,
    }


def _qa_artifact_summary(index: int, path: Path) -> dict[str, Any]:
    metadata = _artifact_metadata(index, path)
    if not metadata["exists"]:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "file_not_found",
            "full_content_included": False,
        }

    if path.suffix.lower() != ".json":
        return _qa_text_summary(metadata, path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "invalid_json",
            "full_content_included": False,
        }
    except OSError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "read_failed",
            "full_content_included": False,
        }

    if not isinstance(payload, dict):
        return {
            **metadata,
            "parsed": False,
            "parse_error": "non_object_json",
            "full_content_included": False,
        }

    return {
        **metadata,
        "parsed": True,
        "full_content_included": False,
        "top_level_keys": sorted(str(key) for key in payload),
        "status_fields": _scalar_fields(payload, _STATUS_FIELD_NAMES),
        "score_fields": _numeric_fields(payload, _SCORE_FIELD_NAMES),
        "count_fields": _count_fields(payload),
    }


def _qa_text_summary(metadata: dict[str, Any], path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "read_failed",
            "full_content_included": False,
        }

    status_fields = _status_fields_from_text(text)
    score_fields = _score_fields_from_text(text)
    count_fields = _count_fields_from_text(text)
    if not status_fields and not score_fields and not count_fields:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "summary_fields_not_found",
            "full_content_included": False,
        }

    return {
        **metadata,
        "parsed": True,
        "source_format": "text",
        "full_content_included": False,
        "status_fields": status_fields,
        "score_fields": score_fields,
        "count_fields": count_fields,
    }


_STATUS_FIELD_NAMES = frozenset(
    {
        "status",
        "passed",
        "ready_for_use",
        "needs_attention",
        "confidence_level",
        "grade",
    }
)
_SCORE_FIELD_NAMES = frozenset(
    {
        "overall_score",
        "quality_score",
        "total_score",
        "grade",
        "score",
        "confidence",
        "overall_confidence",
    }
)
_COUNT_KEY_PARTS = ("issue", "finding", "warning", "error", "suggestion", "recommendation")
_TEXT_SCORE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("overall_score", r"Overall Quality Score:\s*(\d+(?:\.\d+)?)\s*/\s*100"),
    ("quality_score", r"Quality Score:\s*(\d+(?:\.\d+)?)\s*/\s*100"),
    ("grade", r"Grade:\s*(\d+(?:\.\d+)?)\s*/\s*100"),
    ("citation_score", r"Citation Score:\s*(\d+(?:\.\d+)?)\s*/\s*100"),
    ("logic_score", r"Logic Score:\s*(\d+(?:\.\d+)?)\s*/\s*100"),
    ("completeness_score", r"Completeness Score:\s*(\d+(?:\.\d+)?)\s*/\s*100"),
)
_TEXT_COUNT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("total_citations", r"Total Citations:\s*(\d+)"),
    ("valid_citations", r"Valid Citations:\s*(\d+)"),
)


def _scalar_fields(payload: dict[str, Any], field_names: frozenset[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in payload.items():
        if key in field_names and isinstance(value, str | int | float | bool) and value is not None:
            fields[key] = value
    return fields


def _numeric_fields(payload: dict[str, Any], field_names: frozenset[str]) -> dict[str, int | float]:
    fields: dict[str, int | float] = {}
    for key, value in payload.items():
        if key in field_names and isinstance(value, int | float) and not isinstance(value, bool):
            fields[key] = value
    return fields


def _count_fields(payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in payload.items():
        key_text = str(key).lower()
        if not any(part in key_text for part in _COUNT_KEY_PARTS):
            continue
        if isinstance(value, list | dict | tuple | set):
            counts[f"{key}_count"] = len(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            counts[key] = value
    return counts


def _score_fields_from_text(text: str) -> dict[str, int | float]:
    scores: dict[str, int | float] = {}
    for field_name, pattern in _TEXT_SCORE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            scores[field_name] = _parse_number(match.group(1))
    return scores


def _status_fields_from_text(text: str) -> dict[str, str | bool]:
    fields: dict[str, str | bool] = {}
    ready_match = re.search(r"Ready for Use:\s*(Yes|No)", text, flags=re.IGNORECASE)
    if ready_match:
        fields["ready_for_use"] = ready_match.group(1).lower() == "yes"

    confidence_match = re.search(
        r"Confidence Level:\s*([A-Za-z]+|\d+(?:\.\d+)?/100)",
        text,
        flags=re.IGNORECASE,
    )
    if confidence_match:
        fields["confidence_level"] = confidence_match.group(1)
    return fields


def _count_fields_from_text(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field_name, pattern in _TEXT_COUNT_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            counts[field_name] = int(match.group(1))
    return counts


def _parse_number(value: str) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return None


def _scalar_or_none(value: Any) -> str | int | float | bool | None:
    if isinstance(value, str | int | float | bool):
        return value
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _owned_job(mcp_server: MCPServerContext, job_id: str, client_id: str) -> Any | None:
    job = mcp_server.job_store.get_by_id(job_id)
    if job is None or not caller_owns_job_resource(mcp_server, job, client_id):
        return None
    return job


def _job_not_found(job_id: str) -> list[ReadResourceContents]:
    return _json_resource(
        {
            "error": "job_not_found",
            "message": f"No job found with ID: {job_id}",
            "job_id": job_id,
        }
    )


def _no_artifacts(job_id: str, status: str) -> list[ReadResourceContents]:
    return _json_resource(
        {
            "error": "no_artifacts",
            "message": f"Job {job_id} has no output artifacts yet",
            "job_id": job_id,
            "status": status,
        }
    )


def _classify_artifact(path: Path) -> str:
    """Compatibility wrapper for modules importing the legacy helper."""
    return classify_artifact(path)


def _json_resource(data: dict[str, Any]) -> list[ReadResourceContents]:
    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]
