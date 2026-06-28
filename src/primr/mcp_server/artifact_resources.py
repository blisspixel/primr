"""Job-scoped artifact metadata MCP resources."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import AnyUrl, Resource

from primr.mcp_server.resource_auth import caller_owns_job_resource

if TYPE_CHECKING:
    from primr.mcp_server.server import PrimrMCPServer

ARTIFACT_METADATA_BY_JOB_URI = "primr://output/artifacts/by_job"
ARTIFACT_METADATA_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{ARTIFACT_METADATA_BY_JOB_URI}/{{job_id}}"),
    name="Artifact Metadata by Job ID",
    description=(
        "Compact metadata for output artifacts attached to one owned job. "
        "Returns paths, sizes, hashes, and timestamps without report body content."
    ),
    mimeType="application/json",
)


def read_artifact_metadata_by_job_resource(
    mcp_server: PrimrMCPServer,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact artifact metadata for one job, with ownership gating."""
    match = re.match(rf"{re.escape(ARTIFACT_METADATA_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid artifact metadata URI: {uri}")

    job_id = match.group(1)
    job = mcp_server.job_store.get_by_id(job_id)
    if job is None or not caller_owns_job_resource(job, client_id):
        return _json_resource(
            {
                "error": "job_not_found",
                "message": f"No job found with ID: {job_id}",
                "job_id": job_id,
            }
        )

    if not job.output_paths:
        return _json_resource(
            {
                "error": "no_artifacts",
                "message": f"Job {job_id} has no output artifacts yet",
                "job_id": job_id,
                "status": job.get_status().value,
            }
        )

    artifacts = [
        _artifact_metadata(index, Path(path)) for index, path in enumerate(job.output_paths)
    ]
    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": ARTIFACT_METADATA_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "artifact_count": len(artifacts),
            "full_content_included": False,
            "artifacts": artifacts,
        }
    )


def _artifact_metadata(index: int, path: Path) -> dict[str, Any]:
    exists = path.exists() and path.is_file()
    data: dict[str, Any] = {
        "index": index,
        "artifact_type": _classify_artifact(path),
        "file_name": path.name,
        "file_path": str(path),
        "exists": exists,
    }
    if not exists:
        return data

    stat = path.stat()
    data.update(
        {
            "size_bytes": stat.st_size,
            "modified_at": _format_mtime(stat.st_mtime),
            "content_hash": f"sha256:{_hash_file(path)}",
        }
    )
    return data


def _classify_artifact(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name.endswith(".calibration.json"):
        return "calibration_sidecar"
    if name == "run_manifest.json":
        return "run_manifest"
    if name.endswith("_run_state.json"):
        return "run_state"
    if name.endswith(("_qa.json", "_qa_report.json")):
        return "qa_summary"
    if name.endswith(("_verify.json", "_verification.json")):
        return "verification_summary"
    if suffix == ".md":
        return "report_markdown"
    if suffix == ".txt":
        return "report_text"
    if suffix == ".docx":
        return "report_docx"
    if suffix == ".pdf":
        return "report_pdf"
    if suffix == ".json":
        return "json_artifact"
    return "artifact"


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _format_mtime(timestamp: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _json_resource(data: dict[str, Any]) -> list[ReadResourceContents]:
    return [
        ReadResourceContents(
            content=json.dumps(data, indent=2),
            mime_type="application/json",
        )
    ]
