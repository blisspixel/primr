"""Privacy-preserving audit log for MCP tool invocations."""

from __future__ import annotations

import base64
import binascii
import functools
import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from mcp.server.lowlevel.helper_types import ReadResourceContents

from primr.mcp_server.tool_authz import ADMIN_SCOPE

if TYPE_CHECKING:
    from mcp.types import TextContent

    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPAuditEvent:
    """One MCP governance audit event."""

    schema_version: str
    event_id: str
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


class MCPAuditLog:
    """Append-only JSONL audit log for MCP governance events."""

    DEFAULT_PATH = Path("output/.mcp_audit_log.jsonl")

    def __init__(
        self,
        *,
        audit_log_path: str | Path | None = None,
        journal_path: str | Path | None = None,
    ) -> None:
        self.path = _resolve_audit_path(audit_log_path, journal_path)
        self._lock = Lock()

    def record_tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        result: Sequence[TextContent] | None,
        auth_context: Any,
        client_id: str,
        transport: str,
        started_at: float,
        exception: BaseException | None = None,
    ) -> None:
        """Persist one audit event without raw arguments, outputs, or tokens."""
        try:
            duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
            result_payload = _first_json_text(result)
            event = MCPAuditEvent(
                schema_version="1.0",
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                transport=transport,
                tool_name=tool_name,
                status=_classify_status(result_payload, exception),
                duration_ms=duration_ms,
                actor="stdio" if client_id == "stdio" else None,
                client_id_hash=None if client_id == "stdio" else _hash_text(client_id),
                authenticated=bool(getattr(auth_context, "is_authenticated", False)),
                auth_scopes=sorted(str(s) for s in getattr(auth_context, "scopes", []) or []),
                args_hash=_hash_json(arguments),
                result_hash=_hash_result(result),
                approval_token_id=_approval_token_id(arguments, result_payload),
                job_id=_optional_string(result_payload.get("job_id")),
                estimated_cost_usd=_optional_float(
                    result_payload.get("estimated_cost_usd", arguments.get("estimated_cost_usd"))
                ),
                max_estimated_cost_usd=_optional_float(arguments.get("max_estimated_cost_usd")),
                error_type=_error_type(result_payload, exception),
                error_code=_optional_error_code(result_payload.get("error_code")),
            )
            self._append(event)
        except Exception:
            logger.exception("Failed to write MCP audit event for tool %s", tool_name)

    def record_resource_read(
        self,
        *,
        uri: str,
        result: Sequence[ReadResourceContents] | None,
        auth_context: Any,
        client_id: str,
        transport: str,
        started_at: float,
        exception: BaseException | None = None,
    ) -> None:
        """Persist one resource-read audit event without raw URI values or contents."""
        try:
            duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
            result_payload = _first_json_resource(result)
            event = MCPAuditEvent(
                schema_version="1.0",
                event_id=str(uuid.uuid4()),
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                transport=transport,
                tool_name="resources/read",
                status=_classify_resource_status(result_payload, exception),
                duration_ms=duration_ms,
                actor="stdio" if client_id == "stdio" else None,
                client_id_hash=None if client_id == "stdio" else _hash_text(client_id),
                authenticated=bool(getattr(auth_context, "is_authenticated", False)),
                auth_scopes=sorted(str(s) for s in getattr(auth_context, "scopes", []) or []),
                args_hash=_hash_json({"uri": uri}),
                event_type="resource_read",
                result_hash=_hash_resource_result(result),
                job_id=_resource_job_id(uri, result_payload),
                resource_kind=_resource_kind(uri),
                resource_uri_hash=_hash_text(uri),
                error_type=_resource_error_type(result_payload, exception),
                error_code=_optional_error_code(result_payload.get("error_code")),
            )
            self._append(event)
        except Exception:
            logger.exception("Failed to write MCP audit event for resource read")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent audit events in file order."""
        bounded_limit = max(1, min(int(limit), 200))
        if not self.path.exists():
            return []

        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-bounded_limit:]
        except OSError:
            logger.exception("Failed to read MCP audit log")
            return []

        events: list[dict[str, Any]] = []
        for line in lines:
            with _IgnoreJsonErrors():
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    events.append(parsed)
        return events

    def _append(self, event: MCPAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(asdict(event), sort_keys=True, separators=(",", ":")) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)


def audit_tool_calls(
    mcp_server_factory: Callable[[], PrimrMCPServer],
) -> Callable[
    [Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]]],
    Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]],
]:
    """Decorate an MCP tool dispatcher with structured audit logging."""

    def decorator(
        handler: Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]],
    ) -> Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]]:
        @functools.wraps(handler)
        async def wrapped(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            server = mcp_server_factory()
            ctx = getattr(server, "_auth_context", None)
            client_id = _client_id(ctx)
            started_at = time.perf_counter()
            try:
                result = await handler(name, arguments)
            except Exception as exc:
                server.audit_log.record_tool_call(
                    tool_name=name,
                    arguments=arguments,
                    result=None,
                    auth_context=ctx,
                    client_id=client_id,
                    transport=server.transport,
                    started_at=started_at,
                    exception=exc,
                )
                raise
            server.audit_log.record_tool_call(
                tool_name=name,
                arguments=arguments,
                result=result,
                auth_context=ctx,
                client_id=client_id,
                transport=server.transport,
                started_at=started_at,
            )
            return result

        return wrapped

    return decorator


def audit_resource_reads(
    mcp_server_factory: Callable[[], PrimrMCPServer],
) -> Callable[
    [Callable[[str], Awaitable[list[ReadResourceContents]]]],
    Callable[[str], Awaitable[list[ReadResourceContents]]],
]:
    """Decorate an MCP resource dispatcher with structured audit logging."""

    def decorator(
        handler: Callable[[str], Awaitable[list[ReadResourceContents]]],
    ) -> Callable[[str], Awaitable[list[ReadResourceContents]]]:
        @functools.wraps(handler)
        async def wrapped(uri: str) -> list[ReadResourceContents]:
            server = mcp_server_factory()
            uri_text = str(uri)
            ctx = getattr(server, "_auth_context", None)
            client_id = _client_id(ctx)
            started_at = time.perf_counter()
            try:
                result = await handler(uri_text)
            except Exception as exc:
                server.audit_log.record_resource_read(
                    uri=uri_text,
                    result=None,
                    auth_context=ctx,
                    client_id=client_id,
                    transport=server.transport,
                    started_at=started_at,
                    exception=exc,
                )
                raise
            server.audit_log.record_resource_read(
                uri=uri_text,
                result=result,
                auth_context=ctx,
                client_id=client_id,
                transport=server.transport,
                started_at=started_at,
            )
            return result

        return wrapped

    return decorator


def read_agent_audit_recent_resource(
    mcp_server: PrimrMCPServer,
    uri: str,
    *,
    can_read: bool,
) -> list[ReadResourceContents]:
    """Read recent MCP invocation audit events as an MCP resource payload."""
    if not can_read:
        data = {
            "error": "insufficient_scope",
            "message": "Reading MCP audit events requires admin scope.",
            "required_scopes": [ADMIN_SCOPE],
        }
        return [_json_resource(data)]

    query = parse_qs(urlparse(uri).query)
    raw_limit = query.get("limit", ["50"])[0]
    try:
        limit = int(raw_limit)
    except ValueError:
        limit = 50
    events = mcp_server.audit_log.recent(limit=limit)
    return [
        _json_resource(
            {
                "schema_version": "1.0",
                "event_count": len(events),
                "events": events,
            }
        )
    ]


def _json_resource(data: dict[str, Any]) -> ReadResourceContents:
    return ReadResourceContents(
        content=json.dumps(data, indent=2),
        mime_type="application/json",
    )


class _IgnoreJsonErrors:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, _exc, _tb) -> bool:
        return exc_type is not None and issubclass(exc_type, json.JSONDecodeError)


def _resolve_audit_path(
    audit_log_path: str | Path | None,
    journal_path: str | Path | None,
) -> Path:
    if audit_log_path is not None:
        return Path(audit_log_path)
    if journal_path is not None:
        return Path(journal_path).with_name(".mcp_audit_log.jsonl")
    return MCPAuditLog.DEFAULT_PATH


def _client_id(auth_context: Any) -> str:
    if auth_context is not None:
        cid = getattr(auth_context, "client_id", None)
        if isinstance(cid, str) and cid:
            return cid
    return "stdio"


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _hash_text(canonical)


def _hash_result(result: Sequence[TextContent] | None) -> str | None:
    if result is None:
        return None
    texts = [str(getattr(item, "text", "")) for item in result]
    return _hash_json(texts)


def _hash_resource_result(result: Sequence[ReadResourceContents] | None) -> str | None:
    if result is None:
        return None
    texts = [str(getattr(item, "content", "")) for item in result]
    return _hash_json(texts)


def _first_json_text(result: Sequence[TextContent] | None) -> dict[str, Any]:
    if not result:
        return {}
    text = getattr(result[0], "text", None)
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_json_resource(result: Sequence[ReadResourceContents] | None) -> dict[str, Any]:
    if not result:
        return {}
    text = getattr(result[0], "content", None)
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _classify_status(payload: dict[str, Any], exception: BaseException | None) -> str:
    if exception is not None:
        return "exception"
    if payload.get("error") is not True:
        return "success"
    error_type = str(payload.get("error_type") or "")
    if error_type == "insufficient_scope":
        return "scope_denied"
    if error_type == "rate_limit_exceeded":
        return "rate_limited"
    return "error"


def _classify_resource_status(
    payload: dict[str, Any],
    exception: BaseException | None,
) -> str:
    if exception is not None:
        return "exception"
    error = payload.get("error")
    if error is None or error is False:
        return "success"
    if str(error) == "insufficient_scope":
        return "scope_denied"
    return "error"


def _error_type(payload: dict[str, Any], exception: BaseException | None) -> str | None:
    if exception is not None:
        return exception.__class__.__name__
    value = payload.get("error_type")
    return str(value) if value is not None else None


def _resource_error_type(
    payload: dict[str, Any],
    exception: BaseException | None,
) -> str | None:
    if exception is not None:
        return exception.__class__.__name__
    value = payload.get("error_type", payload.get("error"))
    if isinstance(value, bool):
        return None
    return str(value) if value is not None else None


def _resource_kind(uri: str) -> str:
    parsed = urlparse(uri)
    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    base = re.sub(r"/by_job/[^/?]+", "/by_job/{job_id}", base)
    return base


def _resource_job_id(uri: str, payload: dict[str, Any]) -> str | None:
    value = _optional_string(payload.get("job_id"))
    if value is not None:
        return value
    match = re.search(r"/by_job/([^/?]+)", uri)
    return match.group(1) if match else None


def _optional_error_code(value: Any) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return str(value)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in {float("inf"), float("-inf")} else None


def _approval_token_id(arguments: dict[str, Any], payload: dict[str, Any]) -> str | None:
    result_token_id = _optional_string(payload.get("approval_token_id"))
    if result_token_id is not None:
        return result_token_id

    token = arguments.get("approval_token")
    if not isinstance(token, str) or "." not in token:
        return None
    encoded_payload = token.split(".", 1)[0]
    try:
        raw = _b64decode(encoded_payload)
        decoded = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    return _optional_string(decoded.get("jti"))


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
