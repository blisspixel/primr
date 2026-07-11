"""Shared job response helpers for MCP status and report reads."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from primr.mcp_server.tool_authz import REPORT_SCOPE


def parse_bool(value: Any, *, default: bool = False) -> bool:
    """Parse permissive JSON-ish booleans from MCP tool arguments."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def include_artifacts_requested(arguments: dict[str, Any], *, client_id: str) -> bool:
    """Return whether `check_jobs` should include inline artifact bodies."""
    return parse_bool(arguments.get("include_artifacts"), default=client_id == "stdio")


def classify_output_artifact(path: Path) -> str:
    """Classify a report output path using the existing MCP artifact labels."""
    name_lower = path.stem.lower()
    if "ai_strategy" in name_lower or "ai-strategy" in name_lower:
        return "ai_strategy"
    if "customer_experience" in name_lower:
        return "customer_experience_strategy"
    if "security" in name_lower:
        return "security_strategy"
    if "data_fabric" in name_lower:
        return "data_fabric_strategy"
    if "strategic_overview" in name_lower or "report" in name_lower:
        return "strategic_overview"
    return "report"


def artifact_matches_filter(artifact_type: str, artifact_filter: str) -> bool:
    """Return whether an artifact belongs in a negotiated report response."""
    if artifact_filter == "all":
        return True
    if artifact_filter == "strategy":
        return artifact_type.endswith("_strategy") or artifact_type == "ai_strategy"
    return artifact_type in {"strategic_overview", "report"}


def build_output_artifact_rows(
    output_paths: list[str],
    *,
    include_content: bool,
    artifact_filter: str = "all",
    max_chars: int | None = None,
) -> list[dict[str, Any]]:
    """Build safe artifact rows, optionally including bounded text content."""
    rows: list[dict[str, Any]] = []
    for artifact_path in output_paths:
        path = Path(artifact_path)
        if not path.exists() or not path.is_file():
            continue

        artifact_type = classify_output_artifact(path)
        if not artifact_matches_filter(artifact_type, artifact_filter):
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue

        encoded = content.encode("utf-8")
        row: dict[str, Any] = {
            "type": artifact_type,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "content_hash": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
            "content_included": include_content,
        }
        if include_content:
            limit = max_chars if max_chars is not None else len(content)
            truncated = len(content) > limit
            row.update(
                {
                    "content": content[:limit],
                    "content_chars": min(len(content), limit),
                    "content_truncated": truncated,
                    "full_content_included": not truncated,
                }
            )
        rows.append(row)
    return rows


def build_job_response(
    job: Any,
    *,
    include_artifacts: bool,
    include_report_content: bool,
    report_scope_granted: bool = False,
) -> dict[str, Any]:
    """Build a `check_jobs` response without leaking report bodies by default."""
    status = job.get_status().value
    from primr.job_status import build_job_status

    response: dict[str, Any] = build_job_status(
        job_id=job.job_id,
        source="agent_job",
        status=status,
        company_name=job.company_name,
        mode=job.mode,
        stage=job.current_stage,
        percent=job.stage_progress_percent,
        possibly_stuck=job.is_possibly_stuck() if not job.is_terminal() else False,
        started_at=job.start_time,
        updated_at=job.last_heartbeat_time,
        completed_at=job.completion_time,
        artifacts_available=bool(job.output_paths) if status == "completed" else None,
        error_message=job.error_message,
        error_code=job.error_type,
        error_source="agent_job" if job.error_message else None,
    )
    response.update(
        {
            "job_id": job.job_id,
            "status": status,
            "company_name": job.company_name,
            "output_path": job.output_paths[0] if job.output_paths else None,
            "error_type": job.error_type,
            "error_message": job.error_message,
        }
    )

    if status != "completed" or not job.output_paths:
        return response

    response.update(
        {
            "artifacts_content_included": False,
            "include_artifacts_requested": include_artifacts,
            "artifact_metadata_uri": f"primr://output/artifacts/by_job/{job.job_id}",
            "report_read_uri": f"primr://output/report/by_job/{job.job_id}",
        }
    )

    if include_artifacts and include_report_content:
        response["artifacts"] = build_output_artifact_rows(
            job.output_paths,
            include_content=True,
            artifact_filter="all",
        )
        response["artifacts_content_included"] = True
    elif include_artifacts:
        response.update(
            {
                "report_read_required": True,
                "message": (
                    "Inline report content is only returned on the local stdio "
                    "compatibility path. Use "
                    f"primr://output/report/by_job/{job.job_id} for explicit report reads."
                ),
            }
        )
        if not report_scope_granted:
            response["required_scopes"] = [REPORT_SCOPE]

    return response
