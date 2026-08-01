"""Job-scoped claim verification summary MCP resource."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import Resource

from primr.mcp_server.artifact_resources import (
    _artifact_metadata,
    _classify_artifact,
    _job_not_found,
    _json_resource,
    _no_artifacts,
    _owned_job,
)
from primr.mcp_server.resource_summary_utils import safe_float, safe_int, sorted_counts
from primr.mcp_server.server_context import MCPServerContext

if TYPE_CHECKING:
    from mcp.server.lowlevel.helper_types import ReadResourceContents

VERIFICATION_SUMMARY_BY_JOB_URI = "primr://output/verification_summary/by_job"
VERIFICATION_SUMMARY_BY_JOB_RESOURCE = Resource(
    uri=f"{VERIFICATION_SUMMARY_BY_JOB_URI}/{{job_id}}",
    name="Verification Summary by Job ID",
    description=(
        "Compact claim verification metadata for one owned job. Summarizes "
        "verification JSON without returning raw claims, source URLs, or search queries."
    ),
    mime_type="application/json",
)


def read_verification_summary_by_job_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact verification summaries for one job, with ownership gating."""
    match = re.match(rf"{re.escape(VERIFICATION_SUMMARY_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid verification summary URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    summaries = [
        _verification_artifact_summary(index, Path(path))
        for index, path in enumerate(job.output_paths)
        if _classify_artifact(Path(path)) == "verification_summary"
    ]
    if not summaries:
        return _json_resource(
            {
                "error": "verification_summary_not_found",
                "message": f"Job {job_id} has no verification artifact available",
                "job_id": job_id,
                "status": job.get_status().value,
                "summary_count": 0,
            }
        )

    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": VERIFICATION_SUMMARY_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "summary_count": len(summaries),
            "full_content_included": False,
            "summaries": summaries,
        }
    )


def _verification_artifact_summary(index: int, path: Path) -> dict[str, Any]:
    metadata = _artifact_metadata(index, path)
    if not metadata["exists"]:
        return _parse_error_summary(metadata, "file_not_found")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _parse_error_summary(metadata, "invalid_verification_json")
    except UnicodeDecodeError:
        return _parse_error_summary(metadata, "decode_failed")
    except OSError:
        return _parse_error_summary(metadata, "read_failed")

    if not isinstance(payload, dict):
        return _parse_error_summary(metadata, "invalid_verification_payload")

    verified = safe_int(payload.get("verified_count"))
    unverified = safe_int(payload.get("unverified_count"))
    contradicted = safe_int(payload.get("contradicted_count"))
    total = safe_int(payload.get("total_claims")) or verified + unverified + contradicted
    claim_results = payload.get("claim_results")
    status_counts, first_party_downgrades, source_ref_count = _claim_result_counts(claim_results)

    return {
        **metadata,
        "parsed": True,
        "full_content_included": False,
        "raw_claim_results_included": False,
        "source_urls_included": False,
        "search_queries_included": False,
        "trust_score": safe_float(payload.get("trust_score")),
        "trust_percentage": safe_int(payload.get("trust_percentage")),
        "verification_gate": "WARN" if contradicted else "PASS",
        "total_claims": total,
        "verified_count": verified,
        "unverified_count": unverified,
        "contradicted_count": contradicted,
        "duration_seconds": safe_float(payload.get("duration_seconds")),
        "claim_result_count": _claim_result_count(claim_results),
        "claim_status_counts": status_counts,
        "first_party_downgrade_count": first_party_downgrades,
        "source_reference_count": source_ref_count,
    }


def _parse_error_summary(metadata: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        **metadata,
        "parsed": False,
        "parse_error": error,
        "full_content_included": False,
        "raw_claim_results_included": False,
        "source_urls_included": False,
        "search_queries_included": False,
    }


def _claim_result_count(claim_results: Any) -> int:
    return len(claim_results) if isinstance(claim_results, list) else 0


def _claim_result_counts(claim_results: Any) -> tuple[list[dict[str, int | str]], int, int]:
    if not isinstance(claim_results, list):
        return [], 0, 0

    statuses: dict[str, int] = {}
    first_party_downgrades = 0
    source_ref_count = 0
    for item in claim_results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        if item.get("first_party_downgrade"):
            first_party_downgrades += 1
        for key in ("supporting_sources", "evidence_sources"):
            values = item.get(key)
            if isinstance(values, list):
                source_ref_count += len(values)
    return sorted_counts(statuses), first_party_downgrades, source_ref_count
