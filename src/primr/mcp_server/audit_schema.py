"""Typed, body-free schema and redaction policy for agent audit events."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from primr.a2a.skill_ids import A2A_READ_SKILLS, A2A_RESEARCH_SKILLS, A2A_RESOURCE_READ_SKILLS
from primr.mcp_server.tool_authz import (
    ADMIN_SCOPE,
    DELEGATE_SCOPE,
    LEGACY_WRITE_SCOPE,
    READ_SCOPE,
    REPORT_SCOPE,
    RESEARCH_SCOPE,
    TOOL_REQUIRED_SCOPES,
)

_KNOWN_AUTH_SCOPES = frozenset(
    {
        ADMIN_SCOPE,
        DELEGATE_SCOPE,
        LEGACY_WRITE_SCOPE,
        READ_SCOPE,
        REPORT_SCOPE,
        RESEARCH_SCOPE,
    }
)
_KNOWN_A2A_SKILLS = A2A_READ_SKILLS | A2A_RESEARCH_SKILLS | A2A_RESOURCE_READ_SKILLS
_KNOWN_RESOURCE_KINDS = frozenset(
    {
        "primr://agent/audit/recent",
        "primr://agent/governance",
        "primr://calibration/baseline/inspection",
        "primr://config",
        "primr://context",
        "primr://output/artifacts",
        "primr://output/latest",
        "primr://output/manifest/latest",
        "primr://research/modes",
        "primr://research/next-actions",
        "primr://research/status",
        "primr://roadmap",
        "primr://strategies/available",
    }
)
_RESOURCE_ID_PREFIXES = frozenset(
    {
        "primr://eval/stage_scorecard",
        "primr://memory",
        "primr://output/artifacts/by_job",
        "primr://output/by_job",
        "primr://output/calibration_summary/by_job",
        "primr://output/qa_summary/by_job",
        "primr://output/report/by_job",
        "primr://output/source_summary/by_job",
        "primr://output/trace_summary/by_job",
        "primr://output/usage_summary/by_job",
        "primr://output/verification_summary/by_job",
    }
)


@dataclass(frozen=True)
class MCPAuditEvent:
    """One normalized MCP or A2A governance audit event."""

    schema_version: str
    event_id: str
    request_id: str
    timestamp: str
    transport: str
    tool_name: str
    status: str
    duration_ms: int
    actor: str | None
    client_id_hash: str | None
    authenticated: bool
    auth_scopes: list[str]
    args_hash: str
    event_type: str = "tool_call"
    result_hash: str | None = None
    approval_token_id: str | None = None
    job_id: str | None = None
    resource_kind: str | None = None
    resource_uri_hash: str | None = None
    estimated_cost_usd: float | None = None
    max_estimated_cost_usd: float | None = None
    error_type: str | None = None
    error_code: int | str | None = None


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _otel_span_projection(event: MCPAuditEvent) -> dict[str, Any]:
    """Return a body-free span projection for audit-log consumers."""
    attributes: dict[str, str | int | float | bool] = {
        "primr.request_id": event.request_id,
        "primr.event_id": event.event_id,
        "primr.event_type": event.event_type,
        "primr.transport": event.transport,
        "primr.tool_name": event.tool_name,
        "primr.status": event.status,
        "primr.authenticated": event.authenticated,
        "primr.auth.scope_count": len(event.auth_scopes),
        "primr.duration_ms": event.duration_ms,
    }
    optional_attributes: dict[str, str | int | float | bool | None] = {
        "primr.job_id": event.job_id,
        "primr.resource_kind": event.resource_kind,
        "primr.approval_token_id": event.approval_token_id,
        "primr.estimated_cost_usd": event.estimated_cost_usd,
        "primr.max_estimated_cost_usd": event.max_estimated_cost_usd,
        "primr.error_type": event.error_type,
        "primr.error_code": event.error_code,
    }
    for key, value in optional_attributes.items():
        if value is not None:
            attributes[key] = value
    return {"name": _otel_span_name(event), "attributes": attributes}


def _otel_span_name(event: MCPAuditEvent) -> str:
    normalized_tool = re.sub(r"[^A-Za-z0-9_.:-]+", ".", event.tool_name).strip(".")
    return f"primr.{event.transport}.{event.event_type}.{normalized_tool}"


def _resource_kind(uri: str) -> str:
    parsed = urlparse(uri)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if base in _KNOWN_RESOURCE_KINDS:
        return base
    for prefix in _RESOURCE_ID_PREFIXES:
        if re.fullmatch(rf"{re.escape(prefix)}/[^/]+", base):
            placeholder = "{company}" if prefix == "primr://memory" else "{id}"
            if "/by_job" in prefix:
                placeholder = "{job_id}"
            elif prefix == "primr://eval/stage_scorecard":
                placeholder = "{eval_id}"
            return f"{prefix}/{placeholder}"
    return "unknown_resource"


def _a2a_tool_name(skill_id: str | None) -> str:
    if isinstance(skill_id, str) and skill_id in _KNOWN_A2A_SKILLS:
        return f"a2a/{skill_id}"
    return "a2a/unknown"


def _resource_job_id(uri: str, payload: dict[str, Any]) -> str | None:
    value = _optional_string(payload.get("job_id"))
    if value is not None:
        return value
    if "{job_id}" not in _resource_kind(uri):
        return None
    match = re.search(r"/by_job/([^/?]+)", uri)
    return _optional_string(match.group(1)) if match else None


def _optional_error_code(value: Any) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return _bounded_label(value, fallback="unrecognized_error_code")


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if _is_sha256(value):
        return value
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return _hash_text(value)


def _bounded_label(value: Any, *, fallback: str) -> str | None:
    """Keep known-safe short labels while replacing caller-controlled text."""
    if value is None:
        return None
    text = str(value)
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", text) else fallback


def _mcp_tool_name(tool_name: str) -> str:
    return tool_name if tool_name in TOOL_REQUIRED_SCOPES else "unknown_tool"


def _normalized_transport(transport: str) -> str:
    allowed = {"a2a", "http", "sse", "stdio", "streamable-http"}
    return transport if transport in allowed else "unknown"


def _normalized_scopes(scopes: Sequence[Any]) -> list[str]:
    normalized = {str(scope) for scope in scopes if str(scope) in _KNOWN_AUTH_SCOPES}
    if any(str(scope) not in _KNOWN_AUTH_SCOPES for scope in scopes):
        normalized.add("unknown")
    return sorted(normalized)


def _project_safe_audit_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return only the safe, typed v1 audit schema from one persisted object."""
    if event.get("schema_version") != "1.0":
        return None
    event_type = event.get("event_type")
    status = event.get("status")
    if event_type not in {"resource_read", "tool_call"} or status not in {
        "error",
        "exception",
        "rate_limited",
        "scope_denied",
        "success",
    }:
        return None

    event_id = _optional_string(event.get("event_id"))
    request_id = _optional_string(event.get("request_id"))
    timestamp = _safe_timestamp(event.get("timestamp"))
    tool_name = _safe_persisted_tool_name(event.get("tool_name"), event_type=event_type)
    duration_ms = event.get("duration_ms")
    authenticated = event.get("authenticated")
    scopes = event.get("auth_scopes")
    args_hash = _safe_hash(event.get("args_hash"))
    if (
        event_id is None
        or request_id is None
        or timestamp is None
        or tool_name is None
        or not isinstance(duration_ms, int)
        or isinstance(duration_ms, bool)
        or duration_ms < 0
        or not isinstance(authenticated, bool)
        or not isinstance(scopes, list)
        or args_hash is None
    ):
        return None

    actor = event.get("actor")
    safe_actor = actor if actor in {"a2a", "stdio"} else None
    projected = MCPAuditEvent(
        schema_version="1.0",
        event_id=event_id,
        request_id=request_id,
        timestamp=timestamp,
        transport=_normalized_transport(str(event.get("transport") or "")),
        tool_name=tool_name,
        status=status,
        duration_ms=duration_ms,
        actor=safe_actor,
        client_id_hash=_safe_hash(event.get("client_id_hash")),
        authenticated=authenticated,
        auth_scopes=_normalized_scopes(scopes),
        args_hash=args_hash,
        event_type=event_type,
        result_hash=_safe_hash(event.get("result_hash")),
        approval_token_id=_approval_identifier(event.get("approval_token_id")),
        job_id=_optional_string(event.get("job_id")),
        resource_kind=_safe_resource_kind(event.get("resource_kind")),
        resource_uri_hash=_safe_hash(event.get("resource_uri_hash")),
        estimated_cost_usd=_optional_float(event.get("estimated_cost_usd")),
        max_estimated_cost_usd=_optional_float(event.get("max_estimated_cost_usd")),
        error_type=_bounded_label(event.get("error_type"), fallback="unrecognized_error"),
        error_code=_optional_error_code(event.get("error_code")),
    )
    payload = asdict(projected)
    payload["otel_span"] = _otel_span_projection(projected)
    return payload


def _safe_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if parsed.tzinfo is not None else None


def _safe_persisted_tool_name(value: Any, *, event_type: str) -> str | None:
    if not isinstance(value, str):
        return None
    if event_type == "resource_read":
        return "resources/read" if value == "resources/read" else None
    if value in TOOL_REQUIRED_SCOPES or value == "unknown_tool":
        return value
    if value == "a2a/unknown":
        return value
    if value.startswith("a2a/") and value.removeprefix("a2a/") in _KNOWN_A2A_SKILLS:
        return value
    return None


def _safe_resource_kind(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return "unknown_resource"
    return _resource_kind(value)


def _safe_hash(value: Any) -> str | None:
    return value if isinstance(value, str) and _is_sha256(value) else None


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", value))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _approval_identifier(value: Any) -> str | None:
    """Preserve Primr's fixed-shape token ids and hash every other value."""
    if not isinstance(value, str) or not value:
        return None
    if _is_sha256(value):
        return value
    if re.fullmatch(r"[A-Za-z0-9_-]{22}", value):
        return value
    return _hash_text(value)
