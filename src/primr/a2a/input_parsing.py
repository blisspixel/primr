"""Input parsing helpers for Primr's A2A executor."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from primr.mcp_server.artifact_resources import ARTIFACT_METADATA_BY_JOB_URI
from primr.mcp_server.report_resources import REPORT_CONTENT_BY_JOB_URI
from primr.mcp_server.stage_scorecard_summary import STAGE_SCORECARD_SUMMARY_URI


def research_arguments_from_a2a_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return MCP-shaped research arguments from A2A-friendly aliases."""
    arguments = dict(params)
    if "company_url" not in arguments and "url" in arguments:
        arguments["company_url"] = arguments["url"]
    if "company_name" not in arguments and "name" in arguments:
        arguments["company_name"] = arguments["name"]
    return arguments


def parse_research_params(text: str) -> dict[str, Any]:
    """Parse research parameters from JSON or simple natural language text."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    params: dict[str, Any] = {}
    words = text.split()
    for word in words:
        if word.startswith(("http://", "https://")):
            params["url"] = word
            break

    for mode in ("scrape", "deep", "full", "premium"):
        if mode in text.lower():
            params["mode"] = mode
            break

    if "url" in params:
        idx = text.find(params["url"])
        if idx > 0:
            name = text[:idx].strip()
            if name.endswith(" at"):
                name = name[:-3].strip()
            if name:
                params["name"] = name

    return params


def parse_eval_id(text: str) -> str:
    """Extract a simple eval id from JSON, URI, or plain text input."""
    return parse_identifier(
        text,
        json_keys=("eval_id", "evalId"),
        uri_prefix=STAGE_SCORECARD_SUMMARY_URI,
    )


def parse_job_id(text: str, *, uri_prefix: str = ARTIFACT_METADATA_BY_JOB_URI) -> str:
    """Extract a simple job id from JSON, URI, or plain text input."""
    return parse_identifier(
        text,
        json_keys=("job_id", "jobId"),
        uri_prefix=uri_prefix,
    )


def report_read_uri_from_text(text: str) -> str:
    """Build a report-resource URI from A2A JSON, URI, or plain job id input."""
    value = text.strip()
    prefix = f"{REPORT_CONTENT_BY_JOB_URI}/"
    if value.startswith(prefix):
        return value

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        job_id = _first_string(parsed, ("job_id", "jobId"))
        if not job_id:
            return ""
        query_values = _report_query_values(parsed)
        query = f"?{urlencode(query_values)}" if query_values else ""
        return f"{prefix}{job_id}{query}"

    job_id = parse_job_id(text, uri_prefix=REPORT_CONTENT_BY_JOB_URI)
    return f"{prefix}{job_id}" if job_id else ""


def parse_identifier(
    text: str,
    *,
    json_keys: tuple[str, ...],
    uri_prefix: str,
) -> str:
    """Extract a resource id from JSON, URI, or plain text input."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        for key in json_keys:
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    value = text.strip()
    prefix = f"{uri_prefix}/"
    if value.startswith(prefix):
        return value[len(prefix) :].strip()
    return value


def _first_string(parsed: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _report_query_values(parsed: dict[str, Any]) -> dict[str, str]:
    query: dict[str, str] = {}
    for source_key, query_key in (
        ("content_mode", "content_mode"),
        ("contentMode", "content_mode"),
        ("artifact_type", "artifact_type"),
        ("artifactType", "artifact_type"),
        ("max_chars", "max_chars"),
        ("maxChars", "max_chars"),
    ):
        value = parsed.get(source_key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            query[query_key] = normalized
    return query
