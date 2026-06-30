"""Explicit report-body resources for MCP output consumption."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import AnyUrl, Resource

from primr.mcp_server.job_responses import build_output_artifact_rows
from primr.mcp_server.resource_auth import (
    caller_can_read_report,
    caller_client_id,
    caller_granted_scopes,
    caller_owns_job_resource,
)
from primr.mcp_server.tool_authz import REPORT_SCOPE
from primr.mcp_server.types import LatestOutput

logger = logging.getLogger(__name__)

REPORT_CONTENT_BY_JOB_URI = "primr://output/report/by_job"
REPORT_CONTENT_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{REPORT_CONTENT_BY_JOB_URI}/{{job_id}}"),
    name="Report Content by Job ID",
    description=(
        "Explicit owned-job report-content read requiring report scope for HTTP callers. "
        "Supports content_mode=metadata|preview|full, artifact_type=report|strategy|all, "
        "and max_chars output negotiation."
    ),
    mimeType="application/json",
)

DEFAULT_PREVIEW_CHARS = 2000
DEFAULT_FULL_CHARS = 200_000
MAX_REPORT_CHARS = 200_000
_CONTENT_MODES = {"metadata", "preview", "full"}
_ARTIFACT_FILTERS = {"report", "strategy", "all"}


def _json_contents(data: object) -> list[ReadResourceContents]:
    return [ReadResourceContents(content=json.dumps(data, indent=2), mime_type="application/json")]


def _parse_job_id(uri: str, base_uri: str) -> str:
    match = re.match(rf"{re.escape(base_uri)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid job ID in URI: {uri}")
    return match.group(1)


def _query(uri: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(uri).query, keep_blank_values=True)


def _single_query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return values[-1].strip().lower() or default


def _parse_max_chars(query: dict[str, list[str]], *, default: int) -> tuple[int, str | None]:
    raw_values = query.get("max_chars")
    if not raw_values:
        return default, None
    raw = raw_values[-1].strip()
    try:
        parsed = int(raw)
    except ValueError:
        return default, "invalid_max_chars"
    if parsed < 1:
        return default, "invalid_max_chars"
    return min(parsed, MAX_REPORT_CHARS), None


def read_report_by_job_resource(
    mcp_server: Any,
    uri: str,
    *,
    client_id: str | None = None,
    can_read_report: bool | None = None,
) -> list[ReadResourceContents]:
    """Read explicit report content for an owned job with scope and size controls."""
    requested_job_id = _parse_job_id(uri, REPORT_CONTENT_BY_JOB_URI)
    resolved_client_id = client_id if client_id is not None else caller_client_id(mcp_server)
    may_read_report = (
        can_read_report if can_read_report is not None else caller_can_read_report(mcp_server)
    )
    if not may_read_report:
        return _json_contents(_report_scope_denied_payload(mcp_server, requested_job_id))

    job = mcp_server.job_store.get_by_id(requested_job_id)
    if job is None or not caller_owns_job_resource(job, resolved_client_id):
        return _json_contents(
            {
                "error": "job_not_found",
                "message": f"No job found with ID: {requested_job_id}",
                "job_id": requested_job_id,
                "full_content_included": False,
                "content_included": False,
            }
        )

    query = _query(uri)
    content_mode = _single_query_value(query, "content_mode", "preview")
    if content_mode not in _CONTENT_MODES:
        return _json_contents(
            {
                "error": "invalid_content_mode",
                "message": "content_mode must be one of metadata, preview, or full",
                "job_id": requested_job_id,
            }
        )
    artifact_filter = _single_query_value(query, "artifact_type", "report")
    if artifact_filter not in _ARTIFACT_FILTERS:
        return _json_contents(
            {
                "error": "invalid_artifact_type",
                "message": "artifact_type must be one of report, strategy, or all",
                "job_id": requested_job_id,
            }
        )

    default_chars = DEFAULT_PREVIEW_CHARS if content_mode == "preview" else DEFAULT_FULL_CHARS
    max_chars, max_chars_error = _parse_max_chars(query, default=default_chars)
    if max_chars_error is not None:
        return _json_contents(
            {
                "error": max_chars_error,
                "message": "max_chars must be a positive integer",
                "job_id": requested_job_id,
            }
        )

    include_content = content_mode in {"preview", "full"}
    rows = build_output_artifact_rows(
        list(job.output_paths or []),
        include_content=include_content,
        artifact_filter=artifact_filter,
        max_chars=max_chars if include_content else None,
    )
    if not rows:
        return _json_contents(
            {
                "error": "report_not_found",
                "message": f"Job {requested_job_id} has no matching report output",
                "job_id": requested_job_id,
                "status": job.get_status().value,
                "full_content_included": False,
                "content_included": False,
            }
        )

    full_content_included = content_mode == "full" and all(
        not row.get("content_truncated", False) for row in rows
    )
    data = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "company_name": job.company_name,
        "status": job.get_status().value,
        "content_mode": content_mode,
        "artifact_type_filter": artifact_filter,
        "max_chars": max_chars if include_content else None,
        "artifact_count": len(rows),
        "content_included": include_content,
        "full_content_included": full_content_included,
        "artifacts": rows,
    }
    return _json_contents(data)


def _report_scope_denied_payload(mcp_server: Any, job_id: str) -> dict[str, object]:
    return {
        "error": "insufficient_scope",
        "message": "Report content requires the report scope.",
        "job_id": job_id,
        "required_scopes": [REPORT_SCOPE],
        "granted_scopes": list(caller_granted_scopes(mcp_server)),
        "full_content_included": False,
        "content_included": False,
    }


def read_latest_output_resource(
    mcp_server: Any,
    uri: str,
    *,
    can_read_report: bool | None = None,
) -> list[ReadResourceContents]:
    """Read the latest output, gating body previews for authenticated report reads."""
    full_content = "full_content=true" in uri.lower()
    may_read_report = (
        can_read_report if can_read_report is not None else caller_can_read_report(mcp_server)
    )

    job = mcp_server.job_store.get_latest_terminal()
    job_id = job.job_id if job else None

    output_dir = Path("output")
    if not output_dir.exists():
        return _json_contents(
            {"message": "No reports available", "report_path": None, "job_id": job_id}
        )

    report_files = list(output_dir.glob("**/report*.md")) + list(output_dir.glob("**/report*.txt"))
    if not report_files:
        return _json_contents(
            {"message": "No reports available", "report_path": None, "job_id": job_id}
        )

    latest_report = max(report_files, key=lambda p: p.stat().st_mtime)
    try:
        content = latest_report.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read report: %s", exc)
        content = ""

    company_name = latest_report.parent.name if latest_report.parent != output_dir else None
    output = LatestOutput(
        report_path=str(latest_report),
        company_name=company_name,
        generation_timestamp=datetime.fromtimestamp(latest_report.stat().st_mtime),
        report_type="markdown" if latest_report.suffix == ".md" else "text",
        content_preview=content[:DEFAULT_PREVIEW_CHARS] if content and may_read_report else None,
        full_content=content if full_content and may_read_report else None,
    )

    data = {
        "job_id": job_id,
        "report_path": output.report_path,
        "company_name": output.company_name,
        "generation_timestamp": output.generation_timestamp.isoformat()
        if output.generation_timestamp
        else None,
        "report_type": output.report_type,
        "content_preview": output.content_preview,
        "content_preview_included": output.content_preview is not None,
        "full_content_included": output.full_content is not None,
    }
    if full_content and not may_read_report:
        data["report_read_required"] = True
        data["required_scopes"] = [REPORT_SCOPE]
    if output.full_content is not None:
        data["full_content"] = output.full_content
    return _json_contents(data)


def read_output_by_job_resource(
    mcp_server: Any,
    uri: str,
    *,
    client_id: str | None = None,
    can_read_report: bool | None = None,
) -> list[ReadResourceContents]:
    """Read owned-job output metadata and gated preview content."""
    requested_job_id = _parse_job_id(uri, "primr://output/by_job")
    resolved_client_id = client_id if client_id is not None else caller_client_id(mcp_server)
    may_read_report = (
        can_read_report if can_read_report is not None else caller_can_read_report(mcp_server)
    )

    job = mcp_server.job_store.get_by_id(requested_job_id)
    if job is None or not caller_owns_job_resource(job, resolved_client_id):
        return _json_contents(
            {
                "error": "job_not_found",
                "message": f"No job found with ID: {requested_job_id}",
                "job_id": requested_job_id,
            }
        )

    if not job.output_paths:
        return _json_contents(
            {
                "error": "no_output",
                "message": f"Job {requested_job_id} has no output yet",
                "job_id": requested_job_id,
                "status": job.get_status().value,
            }
        )

    report_path = next((path for path in job.output_paths if "report" in path.lower()), None)
    if not report_path and job.output_paths:
        report_path = job.output_paths[0]

    content_preview = None
    if report_path and may_read_report:
        try:
            report_file = Path(report_path)
            if report_file.exists():
                content_preview = report_file.read_text(encoding="utf-8")[:DEFAULT_PREVIEW_CHARS]
        except Exception as exc:
            logger.warning("Failed to read report for job %s: %s", requested_job_id, exc)

    return _json_contents(
        {
            "job_id": job.job_id,
            "report_path": report_path,
            "company_name": job.company_name,
            "generation_timestamp": job.completion_time.isoformat()
            if job.completion_time
            else None,
            "report_type": "markdown" if report_path and report_path.endswith(".md") else "text",
            "content_preview": content_preview,
            "content_preview_included": content_preview is not None,
            "report_read_required": not may_read_report,
            "report_read_uri": f"{REPORT_CONTENT_BY_JOB_URI}/{job.job_id}",
            "status": job.get_status().value,
        }
    )
