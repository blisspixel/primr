"""Job-scoped source appendix summary MCP resource."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from mcp.types import AnyUrl, Resource

from primr.mcp_server.artifact_resources import (
    _artifact_metadata,
    _classify_artifact,
    _job_not_found,
    _json_resource,
    _no_artifacts,
    _owned_job,
)
from primr.mcp_server.server_context import MCPServerContext
from primr.utils.validators import validate_and_normalize_url

if TYPE_CHECKING:
    from mcp.server.lowlevel.helper_types import ReadResourceContents

SOURCE_SUMMARY_BY_JOB_URI = "primr://output/source_summary/by_job"
SOURCE_SUMMARY_BY_JOB_RESOURCE = Resource(
    uri=AnyUrl(f"{SOURCE_SUMMARY_BY_JOB_URI}/{{job_id}}"),
    name="Source Appendix Summary by Job ID",
    description=(
        "Compact source appendix and citation-integrity metadata for one owned job. "
        "Reads report artifacts without returning report body content."
    ),
    mimeType="application/json",
)

_SOURCE_HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,6})\s+"
    r"(?P<title>sources|citations|references|source appendix|citation appendix)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ANY_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+\S.*$", re.MULTILINE)
_CITE_TOKEN_RE = re.compile(r"\[cite:\s*([0-9,\s]+)\]", re.IGNORECASE)
_BRACKET_REF_RE = re.compile(r"\[(\d+)\]")
_URL_RE = re.compile(r"https?://[^\s<>\])]+", re.IGNORECASE)


@dataclass(frozen=True)
class _SourceSection:
    text: str
    body_without_section: str
    present: bool


@dataclass(frozen=True)
class _SourceDefinition:
    reference: int
    url: str
    domain: str
    title: str | None


def read_source_summary_by_job_resource(
    mcp_server: MCPServerContext,
    uri: str,
    *,
    client_id: str,
) -> list[ReadResourceContents]:
    """Read compact source appendix summaries for one job, with ownership gating."""
    match = re.match(rf"{re.escape(SOURCE_SUMMARY_BY_JOB_URI)}/([^/?]+)", uri)
    if not match:
        raise ValueError(f"Invalid source summary URI: {uri}")

    job_id = match.group(1)
    job = _owned_job(mcp_server, job_id, client_id)
    if job is None:
        return _job_not_found(job_id)

    if not job.output_paths:
        return _no_artifacts(job_id, job.get_status().value)

    summaries = [
        _source_artifact_summary(index, Path(path))
        for index, path in enumerate(job.output_paths)
        if _classify_artifact(Path(path)) in {"report_markdown", "report_text"}
    ]
    if not summaries:
        return _json_resource(
            {
                "error": "source_summary_not_found",
                "message": f"Job {job_id} has no report artifact available for source summary",
                "job_id": job_id,
                "status": job.get_status().value,
                "summary_count": 0,
            }
        )

    return _json_resource(
        {
            "schema_version": "1.0",
            "resource": SOURCE_SUMMARY_BY_JOB_URI,
            "job_id": job.job_id,
            "status": job.get_status().value,
            "company_name": job.company_name,
            "summary_count": len(summaries),
            "full_content_included": False,
            "summaries": summaries,
        }
    )


def _source_artifact_summary(index: int, path: Path) -> dict[str, Any]:
    metadata = _artifact_metadata(index, path)
    if not metadata["exists"]:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "file_not_found",
            "full_content_included": False,
        }

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "decode_failed",
            "full_content_included": False,
        }
    except OSError:
        return {
            **metadata,
            "parsed": False,
            "parse_error": "read_failed",
            "full_content_included": False,
        }

    section = _split_source_section(text)
    referenced = _referenced_numbers(section.body_without_section)
    definitions, invalid_count = _source_definitions(section.text)
    definition_numbers = {definition.reference for definition in definitions}
    duplicate_url_count = _duplicate_url_count(definitions)
    domains = _domain_counts(definitions)

    return {
        **metadata,
        "parsed": True,
        "source_format": "markdown" if path.suffix.lower() == ".md" else "text",
        "source_section_present": section.present,
        "full_content_included": False,
        "inline_reference_count": len(referenced),
        "referenced_numbers": sorted(set(referenced)),
        "definition_count": len(definitions),
        "valid_source_count": len(definitions),
        "invalid_source_count": invalid_count,
        "duplicate_url_count": duplicate_url_count,
        "missing_definition_numbers": sorted(set(referenced) - definition_numbers),
        "unused_definition_numbers": sorted(definition_numbers - set(referenced)),
        "domains": domains,
        "sources": [
            {
                "reference": definition.reference,
                "url": definition.url,
                "domain": definition.domain,
                "title": definition.title,
            }
            for definition in definitions
        ],
    }


def _split_source_section(text: str) -> _SourceSection:
    matches = list(_SOURCE_HEADING_RE.finditer(text))
    if not matches:
        return _SourceSection(text="", body_without_section=text, present=False)

    heading = matches[-1]
    level = len(heading.group("hashes"))
    end = len(text)
    for next_heading in _ANY_HEADING_RE.finditer(text, heading.end()):
        if len(next_heading.group("hashes")) <= level:
            end = next_heading.start()
            break

    return _SourceSection(
        text=text[heading.end() : end],
        body_without_section=text[: heading.start()] + text[end:],
        present=True,
    )


def _referenced_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    for match in _CITE_TOKEN_RE.finditer(text):
        numbers.extend(int(value) for value in re.findall(r"\d+", match.group(1)))
    numbers.extend(int(match.group(1)) for match in _BRACKET_REF_RE.finditer(text))
    return numbers


def _source_definitions(section_text: str) -> tuple[list[_SourceDefinition], int]:
    definitions: list[_SourceDefinition] = []
    invalid_count = 0
    pending_ref: tuple[int, str | None] | None = None

    for line in section_text.splitlines():
        reference = _reference_from_line(line)
        if reference is not None:
            if pending_ref is not None:
                invalid_count += 1
            pending_ref = (reference, _title_from_line(line))

        url_match = _URL_RE.search(line)
        if url_match is None or pending_ref is None:
            continue

        raw_url = _strip_trailing_url_punctuation(url_match.group(0))
        is_valid, normalized_url, _error = validate_and_normalize_url(raw_url)
        if not is_valid:
            invalid_count += 1
            pending_ref = None
            continue

        domain = _domain_from_url(normalized_url)
        if domain is None:
            invalid_count += 1
            pending_ref = None
            continue

        definitions.append(
            _SourceDefinition(
                reference=pending_ref[0],
                url=normalized_url,
                domain=domain,
                title=pending_ref[1],
            )
        )
        pending_ref = None

    if pending_ref is not None:
        invalid_count += 1

    return definitions, invalid_count


def _reference_from_line(line: str) -> int | None:
    patterns = (
        r"\[cite:\s*(\d+)\]",
        r"^\s*(?:[-*]\s*)?\[(\d+)\]",
        r"^\s*(?:[-*]\s*)?(\d+)[.)]\s+",
    )
    for pattern in patterns:
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _title_from_line(line: str) -> str | None:
    without_ref = re.sub(
        r"^\s*(?:[-*]\s*)?(?:\[cite:\s*\d+\]|\[\d+\]|\d+[.)])\s*",
        "",
        line,
        flags=re.IGNORECASE,
    )
    without_url = _URL_RE.sub("", without_ref)
    title = without_url.strip(" -:\t")
    if not title:
        return None
    return title[:160]


def _strip_trailing_url_punctuation(url: str) -> str:
    return url.rstrip(".,;:")


def _domain_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return None
    return host.lower().removeprefix("www.")


def _duplicate_url_count(definitions: list[_SourceDefinition]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for definition in definitions:
        if definition.url in seen:
            duplicates += 1
            continue
        seen.add(definition.url)
    return duplicates


def _domain_counts(definitions: list[_SourceDefinition]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for definition in definitions:
        counts[definition.domain] = counts.get(definition.domain, 0) + 1
    return [
        {"domain": domain, "count": count}
        for domain, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
