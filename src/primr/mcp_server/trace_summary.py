"""Job-scoped scrape trace summary MCP resource."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import AnyUrl, Resource

from primr.data.scraping.trace import read_trace_file
from primr.data.scraping.trace_stats import THIN_CONTENT_CHARS, percentile
from primr.mcp_server.artifact_resources import (
    _artifact_metadata,
    _classify_artifact,
    _job_not_found,
    _json_resource,
    _no_artifacts,
    _owned_job,
)

if TYPE_CHECKING:
    from mcp.server.lowlevel.helper_types import ReadResourceContents

    from primr.mcp_server.server import PrimrMCPServer

TRACE_SUMMARY_BY_JOB_URI = "primr://output/trace_summary/by_job"
TRACE_SUMMARY_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{TRACE_SUMMARY_BY_JOB_URI}/{{job_id}}"),
    name="Scrape Trace Summary by Job ID",
    description=(
        "Compact scrape trace metadata for one owned job. Summarizes trace JSONL "
        "artifacts without returning URLs, final URLs, raw trace lines, or page content."
    ),
    mimeType="application/json",
)


def read_trace_summary_by_job_resource(
    mcp_server: PrimrMCPServer,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact scrape trace summaries for one job, with ownership gating."""
    match = re.match(rf"{re.escape(TRACE_SUMMARY_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid trace summary URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    summaries = [
        _trace_artifact_summary(index, Path(path))
        for index, path in enumerate(job.output_paths)
        if _classify_artifact(Path(path)) == "scrape_trace"
    ]
    if not summaries:
        return _json_resource(
            {
                "error": "trace_summary_not_found",
                "message": f"Job {job_id} has no scrape trace artifact available",
                "job_id": job_id,
                "status": job.get_status().value,
                "summary_count": 0,
            }
        )

    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": TRACE_SUMMARY_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "summary_count": len(summaries),
            "full_content_included": False,
            "summaries": summaries,
        }
    )


def _trace_artifact_summary(index: int, path: Path) -> dict[str, Any]:
    metadata = _artifact_metadata(index, path)
    if not metadata["exists"]:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "file_not_found",
            "full_content_included": False,
        }

    try:
        header, entries = read_trace_file(path)
    except (AttributeError, TypeError, ValueError):
        return _parse_error_summary(metadata, "invalid_trace_jsonl")
    except OSError:
        return _parse_error_summary(metadata, "read_failed")

    tier_summaries = _tier_summaries(entries)
    text_lengths = [
        int(entry.extracted_text_length)
        for entry in entries
        if entry.success_tier and entry.extracted_text_length is not None
    ]
    validation_counts = _validation_counts(entries)
    status_counts = _status_counts(entries)
    block_counts = _block_counts(entries)

    success_count = sum(1 for entry in entries if entry.success_tier)
    return {
        **metadata,
        "parsed": True,
        "trace_schema_version": header.schema_version,
        "trace_run_id": header.run_id,
        "trace_started_at": header.started_at,
        "full_content_included": False,
        "raw_entries_included": False,
        "urls_included": False,
        "entry_count": len(entries),
        "success_count": success_count,
        "failure_count": len(entries) - success_count,
        "success_rate": _rate(success_count, len(entries)),
        "blocked_count": sum(block_counts.values()),
        "block_type_counts": _sorted_counts(block_counts),
        "http_status_counts": _sorted_counts(status_counts),
        "tier_summaries": tier_summaries,
        "avg_text_length": _average(text_lengths),
        "thin_page_count": sum(1 for length in text_lengths if length < THIN_CONTENT_CHARS),
        "validated_page_count": validation_counts["validated"],
        "valid_page_count": validation_counts["valid"],
        "content_valid_rate": _rate(validation_counts["valid"], validation_counts["validated"]),
    }


def _parse_error_summary(metadata: dict[str, Any], error: str) -> dict[str, Any]:
    return {
        **metadata,
        "parsed": False,
        "parse_error": error,
        "full_content_included": False,
        "raw_entries_included": False,
        "urls_included": False,
    }


def _tier_summaries(entries: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for attempt in entry.tier_attempts or []:
            if not isinstance(attempt, dict):
                continue
            tier = str(attempt.get("tier") or "unknown")
            bucket = buckets.setdefault(tier, {"attempts": 0, "successes": 0, "latencies": []})
            bucket["attempts"] += 1
            if attempt.get("success"):
                bucket["successes"] += 1
            elapsed = attempt.get("elapsed_ms")
            if isinstance(elapsed, int | float) and not isinstance(elapsed, bool) and elapsed >= 0:
                bucket["latencies"].append(float(elapsed))

    summaries: list[dict[str, Any]] = []
    for tier, bucket in buckets.items():
        latencies = bucket["latencies"]
        summaries.append(
            {
                "tier": tier,
                "attempts": bucket["attempts"],
                "successes": bucket["successes"],
                "success_rate": _rate(bucket["successes"], bucket["attempts"]),
                "avg_latency_ms": _average(latencies),
                "p95_latency_ms": percentile(latencies, 95) if latencies else None,
            }
        )
    return sorted(summaries, key=lambda item: (-int(item["attempts"]), str(item["tier"])))


def _validation_counts(entries: list[Any]) -> dict[str, int]:
    counts = {"validated": 0, "valid": 0}
    for entry in entries:
        validation = entry.validation_result
        if isinstance(validation, dict) and "valid" in validation:
            counts["validated"] += 1
            if validation.get("valid"):
                counts["valid"] += 1
    return counts


def _status_counts(entries: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.http_status is None:
            continue
        key = str(entry.http_status)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _block_counts(entries: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if not entry.blocked:
            continue
        block_type = entry.block_type or "blocked"
        counts[block_type] = counts.get(block_type, 0) + 1
    return counts


def _sorted_counts(counts: dict[str, int]) -> list[dict[str, int | str]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _average(values: list[float] | list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
