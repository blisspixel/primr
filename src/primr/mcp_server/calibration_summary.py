"""Job-scoped calibration sidecar summary MCP resource."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import AnyUrl, Resource

from primr.mcp_server.artifact_resources import (
    _artifact_metadata,
    _classify_artifact,
    _job_not_found,
    _json_resource,
    _no_artifacts,
    _owned_job,
)
from primr.mcp_server.resource_summary_utils import (
    safe_float,
    safe_int,
    scalar_or_none,
    sorted_counts,
)
from primr.mcp_server.server_context import MCPServerContext
from primr.qa.calibration_runner import (
    calibration_sidecar_matches_report,
    report_path_for_sidecar,
    sidecar_path_for,
)

if TYPE_CHECKING:
    from mcp.server.lowlevel.helper_types import ReadResourceContents

CALIBRATION_SUMMARY_BY_JOB_URI = "primr://output/calibration_summary/by_job"
CALIBRATION_SUMMARY_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{CALIBRATION_SUMMARY_BY_JOB_URI}/{{job_id}}"),
    name="Calibration Summary by Job ID",
    description=(
        "Compact label-calibration metadata for one owned job. Summarizes "
        "calibration sidecars and inference source-copy counts without returning "
        "raw claims, source URLs, or rationales."
    ),
    mimeType="application/json",
)

_REPORT_ARTIFACT_TYPES = frozenset({"report_markdown", "report_text", "report_docx", "report_pdf"})
_VERDICT_FIELDS = (
    "sampled",
    "traceable",
    "untraceable",
    "no_source",
    "unfetchable",
    "exempt",
    "source_copied",
)
_EVIDENCE_DIMENSIONS = (
    "contradiction",
    "source_independence",
    "source_authority",
    "reasoning_strength",
    "uncertainty_honesty",
    "business_relevance",
)


def read_calibration_summary_by_job_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact calibration summaries for one job, with ownership gating."""
    match = re.match(rf"{re.escape(CALIBRATION_SUMMARY_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid calibration summary URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    sidecar_paths = _calibration_sidecar_paths([Path(path) for path in job.output_paths])
    summaries = [
        _calibration_artifact_summary(index, path) for index, path in enumerate(sidecar_paths)
    ]
    if not summaries:
        return _json_resource(
            {
                "error": "calibration_summary_not_found",
                "message": f"Job {job_id} has no calibration sidecar available",
                "job_id": job_id,
                "status": job.get_status().value,
                "summary_count": 0,
            }
        )

    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": CALIBRATION_SUMMARY_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "summary_count": len(summaries),
            "full_content_included": False,
            "summaries": summaries,
        }
    )


def _calibration_sidecar_paths(output_paths: list[Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for path in output_paths:
        artifact_type = _classify_artifact(path)
        candidates: list[tuple[Path, bool]] = []
        if artifact_type == "calibration_sidecar":
            candidates.append((path, True))
        elif artifact_type in _REPORT_ARTIFACT_TYPES:
            candidates.append((sidecar_path_for(path), False))

        for candidate, explicit in candidates:
            if not explicit and not (candidate.exists() and candidate.is_file()):
                continue
            normalized = candidate.resolve(strict=False)
            if normalized in seen:
                continue
            seen.add(normalized)
            paths.append(candidate)
    return paths


def _calibration_artifact_summary(index: int, path: Path) -> dict[str, Any]:
    metadata = _artifact_metadata(index, path)
    if not metadata["exists"]:
        return _parse_error_summary(metadata, "file_not_found")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _parse_error_summary(metadata, "invalid_calibration_json")
    except UnicodeDecodeError:
        return _parse_error_summary(metadata, "decode_failed")
    except OSError:
        return _parse_error_summary(metadata, "read_failed")

    if not isinstance(payload, dict):
        return _parse_error_summary(metadata, "invalid_calibration_payload")
    try:
        report_path = report_path_for_sidecar(path)
    except ValueError:
        return _parse_error_summary(metadata, "invalid_calibration_sidecar_name")
    if not calibration_sidecar_matches_report(report_path, payload):
        return _parse_error_summary(metadata, "report_artifact_mismatch")

    per_label = _dict_payload(payload.get("per_label"))
    label_summaries = _label_summaries(per_label)
    totals = _label_totals(label_summaries)
    validation_rubric = _validation_rubric_summary(_dict_payload(payload.get("validation_rubric")))

    return {
        **metadata,
        "parsed": True,
        "report_binding_valid": True,
        "full_content_included": False,
        "raw_claims_included": False,
        "claim_text_included": False,
        "source_urls_included": False,
        "evidence_reviews_included": False,
        "rationales_included": False,
        "report_file": scalar_or_none(payload.get("report_file")),
        "max_per_label": _optional_int(payload.get("max_per_label")),
        "judge": _judge_summary(payload.get("judge")),
        "judge_agreement": _judge_agreement_summary(payload.get("judge_agreement")),
        "label_count": len(label_summaries),
        "claim_result_count": _claim_result_count(payload.get("claims")),
        "claims_sampled": totals["sampled"],
        "decidable_claims": totals["decidable"],
        "traceable_count": totals["traceable"],
        "untraceable_count": totals["untraceable"],
        "no_source_count": totals["no_source"],
        "unfetchable_count": totals["unfetchable"],
        "exempt_count": totals["exempt"],
        "source_copied_count": totals["source_copied"],
        "per_label": label_summaries,
        "validation_rubric": validation_rubric,
    }


def _parse_error_summary(metadata: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        **metadata,
        "parsed": False,
        "parse_error": error,
        "full_content_included": False,
        "raw_claims_included": False,
        "claim_text_included": False,
        "source_urls_included": False,
        "evidence_reviews_included": False,
        "rationales_included": False,
    }


def _label_summaries(per_label: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for label, stats in sorted(per_label.items(), key=lambda item: str(item[0])):
        if not isinstance(stats, dict):
            continue
        summary: dict[str, Any] = {"label": str(label)}
        for field in _VERDICT_FIELDS:
            summary[field] = safe_int(stats.get(field))
        summary["decidable"] = summary["traceable"] + summary["untraceable"] + summary["no_source"]
        summary["precision"] = safe_float(stats.get("precision"))
        summaries.append(summary)
    return summaries


def _label_totals(label_summaries: list[dict[str, Any]]) -> dict[str, int]:
    totals = dict.fromkeys((*_VERDICT_FIELDS, "decidable"), 0)
    for summary in label_summaries:
        for field in totals:
            totals[field] += safe_int(summary.get(field))
    return totals


def _validation_rubric_summary(validation_rubric: dict[str, Any]) -> dict[str, Any]:
    dimensions = []
    for dimension in _EVIDENCE_DIMENSIONS:
        counts = _count_summary(validation_rubric.get(dimension))
        if counts:
            dimensions.append({"dimension": dimension, "counts": counts})

    return {
        "claims_with_reviews": safe_int(validation_rubric.get("claims_with_reviews")),
        "source_reviews": safe_int(validation_rubric.get("source_reviews")),
        "support_counts": _count_summary(validation_rubric.get("support")),
        "dimension_counts": dimensions,
    }


def _count_summary(value: Any) -> list[dict[str, int | str]]:
    if not isinstance(value, dict):
        return []
    counts = {str(key): safe_int(count) for key, count in value.items()}
    return sorted_counts({key: count for key, count in counts.items() if count})


def _judge_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    summary = {
        key: scalar_or_none(value.get(key))
        for key in ("kind", "model")
        if scalar_or_none(value.get(key)) is not None
    }
    fallback_count = safe_int(value.get("cloud_fallbacks"))
    if fallback_count:
        summary["cloud_fallbacks"] = fallback_count
    return summary or None


def _judge_agreement_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    compared = safe_int(value.get("compared"))
    agreed = safe_int(value.get("agreed"))
    agreement = safe_float(value.get("agreement"))
    if agreement is None and compared:
        agreement = agreed / compared
    summary = {
        "scope": scalar_or_none(value.get("scope")),
        "local_model": scalar_or_none(value.get("local_model")),
        "compared": compared,
        "agreed": agreed,
        "agreement": agreement,
    }
    return {key: item for key, item in summary.items() if item is not None}


def _claim_result_count(claims: Any) -> int:
    return len(claims) if isinstance(claims, list) else 0


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return safe_int(value)


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
