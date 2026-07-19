"""Privacy-preserving audit log for MCP tool invocations."""

from __future__ import annotations

import base64
import binascii
import functools
import json
import logging
import os
import stat
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import parse_qs, urlparse

from mcp.server.lowlevel.helper_types import ReadResourceContents

from primr.mcp_server.audit_schema import (
    MCPAuditEvent,
    _a2a_tool_name,
    _approval_identifier,
    _bounded_label,
    _hash_text,
    _mcp_tool_name,
    _normalized_scopes,
    _normalized_transport,
    _optional_error_code,
    _optional_float,
    _optional_string,
    _otel_span_projection,
    _project_safe_audit_event,
    _resource_job_id,
    _resource_kind,
)
from primr.mcp_server.resource_auth import is_local_stdio_context
from primr.mcp_server.tool_authz import (
    ADMIN_SCOPE,
)

if TYPE_CHECKING:
    from mcp.types import TextContent

logger = logging.getLogger(__name__)

_MAX_RECENT_READ_BYTES = 1024 * 1024
_MAX_AUDIT_EVENT_BYTES = 16 * 1024


@dataclass
class _AuditSinkState:
    """Body-free observations about the local audit JSONL sink."""

    file_observed: bool = False
    write_attempted: bool = False
    last_write_succeeded: bool | None = None
    last_write_attempt_at: str | None = None
    last_write_success_at: str | None = None
    last_write_failure_at: str | None = None
    consecutive_write_failures: int = 0
    last_write_error_type: str | None = None
    read_attempted: bool = False
    last_read_succeeded: bool | None = None
    last_read_attempt_at: str | None = None
    last_read_success_at: str | None = None
    last_read_failure_at: str | None = None
    last_read_error_type: str | None = None
    malformed_event_count: int = 0
    read_truncated: bool = False
    incomplete_tail: bool = False


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
        self._health_lock = Lock()
        self._health = _AuditSinkState()
        self._last_write_identity: tuple[int, int] | None = None
        self._last_write_size: int | None = None

    def health_snapshot(self) -> dict[str, Any]:
        """Return sink state without paths, event data, or exception messages."""
        with self._health_lock:
            state = asdict(self._health)
            last_write_identity = self._last_write_identity
            last_write_size = self._last_write_size

        file_replaced_after_write = False
        file_truncated_after_write = False

        if state["write_attempted"] or state["read_attempted"]:
            try:
                metadata = self.path.lstat()
            except FileNotFoundError:
                state["file_observed"] = False
            except OSError as exc:
                observed_at = _utc_timestamp()
                state["file_observed"] = False
                state["read_attempted"] = True
                state["last_read_succeeded"] = False
                state["last_read_attempt_at"] = observed_at
                state["last_read_failure_at"] = observed_at
                state["last_read_error_type"] = type(exc).__name__
            else:
                state["file_observed"] = stat.S_ISREG(metadata.st_mode)
                if not state["file_observed"] and state["last_read_succeeded"] is not False:
                    state["last_read_succeeded"] = False
                    state["last_read_error_type"] = "NonRegularFile"
                elif state["file_observed"] and state["last_write_succeeded"] is True:
                    current_identity = _file_identity(metadata)
                    file_replaced_after_write = (
                        last_write_identity is not None and current_identity != last_write_identity
                    )
                    file_truncated_after_write = (
                        last_write_size is not None and metadata.st_size < last_write_size
                    )

        write_failed = state["write_attempted"] and state["last_write_succeeded"] is False
        read_failed = state["read_attempted"] and state["last_read_succeeded"] is False
        disappeared_after_write = (
            state["write_attempted"]
            and state["last_write_succeeded"] is True
            and not state["file_observed"]
        )
        if (
            write_failed
            or read_failed
            or disappeared_after_write
            or state["malformed_event_count"] > 0
            or state["incomplete_tail"]
            or file_replaced_after_write
            or file_truncated_after_write
        ):
            status = "degraded"
        elif state["last_write_succeeded"] is True or (
            state["last_read_succeeded"] is True and state["file_observed"]
        ):
            status = "ok"
        else:
            status = "not_observed"

        return {
            "schema_version": "1.0",
            "status": status,
            "sink": "jsonl",
            **state,
            "file_replaced_after_successful_write": file_replaced_after_write,
            "file_truncated_after_successful_write": file_truncated_after_write,
        }

    def preflight(self) -> bool:
        """Verify that the real audit sink can be opened and read securely."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                descriptor = _open_regular_audit_fd(
                    self.path,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                )
                metadata = os.fstat(descriptor)
                os.close(descriptor)
                with self._health_lock:
                    self._last_write_identity = _file_identity(metadata)
                    self._last_write_size = metadata.st_size
        except OSError as exc:
            self._record_write_result(succeeded=False, error=exc)
            return False
        self.recent(limit=1)
        return self.health_snapshot()["status"] == "ok"

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
            event_id = str(uuid.uuid4())
            event = MCPAuditEvent(
                schema_version="1.0",
                event_id=event_id,
                request_id=event_id,
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                transport=_normalized_transport(transport),
                tool_name=_mcp_tool_name(tool_name),
                status=_classify_status(result_payload, exception),
                duration_ms=duration_ms,
                actor="stdio" if is_local_stdio_context(transport, auth_context) else None,
                client_id_hash=(
                    None
                    if is_local_stdio_context(transport, auth_context)
                    else _hash_text(client_id)
                ),
                authenticated=bool(getattr(auth_context, "is_authenticated", False)),
                auth_scopes=_normalized_scopes(getattr(auth_context, "scopes", []) or []),
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
            logger.exception("Failed to write MCP audit tool event")

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
            event_id = str(uuid.uuid4())
            event = MCPAuditEvent(
                schema_version="1.0",
                event_id=event_id,
                request_id=event_id,
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                transport=_normalized_transport(transport),
                tool_name="resources/read",
                status=_classify_resource_status(result_payload, exception),
                duration_ms=duration_ms,
                actor="stdio" if is_local_stdio_context(transport, auth_context) else None,
                client_id_hash=(
                    None
                    if is_local_stdio_context(transport, auth_context)
                    else _hash_text(client_id)
                ),
                authenticated=bool(getattr(auth_context, "is_authenticated", False)),
                auth_scopes=_normalized_scopes(getattr(auth_context, "scopes", []) or []),
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

    def record_a2a_skill_call(
        self,
        *,
        skill_id: str | None,
        arguments: dict[str, Any],
        result_payload: dict[str, Any] | None,
        auth_context: Any,
        client_id: str,
        started_at: float,
        exception: BaseException | None = None,
    ) -> None:
        """Persist one A2A skill audit event without raw message text or results."""
        try:
            payload = result_payload or {}
            duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
            authenticated = bool(getattr(auth_context, "is_authenticated", False))
            local_actor = "a2a" if not authenticated and client_id == "a2a" else None
            event_id = str(uuid.uuid4())
            event = MCPAuditEvent(
                schema_version="1.0",
                event_id=event_id,
                request_id=event_id,
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                transport="a2a",
                tool_name=_a2a_tool_name(skill_id),
                status=_classify_status(payload, exception),
                duration_ms=duration_ms,
                actor=local_actor,
                client_id_hash=None if local_actor is not None else _hash_text(client_id),
                authenticated=authenticated,
                auth_scopes=_normalized_scopes(getattr(auth_context, "scopes", []) or []),
                args_hash=_hash_json(arguments),
                result_hash=_hash_json(payload) if result_payload is not None else None,
                approval_token_id=_approval_token_id(arguments, payload),
                job_id=_optional_string(payload.get("job_id")),
                estimated_cost_usd=_optional_float(
                    payload.get("estimated_cost_usd", arguments.get("estimated_cost_usd"))
                ),
                max_estimated_cost_usd=_optional_float(
                    payload.get("max_estimated_cost_usd", arguments.get("max_estimated_cost_usd"))
                ),
                error_type=_error_type(payload, exception),
                error_code=_optional_error_code(payload.get("error_code")),
            )
            self._append(event)
        except Exception:
            logger.exception("Failed to write MCP audit A2A event")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent audit events in file order."""
        bounded_limit = max(1, min(int(limit), 200))
        try:
            path_exists = self.path.exists()
        except OSError as exc:
            self._record_read_result(succeeded=False, error=exc)
            logger.exception("Failed to inspect MCP audit log")
            return []
        if not path_exists:
            self._record_read_result(succeeded=True, file_observed=False)
            return []

        try:
            with self._lock:
                lines, truncated = _read_bounded_tail(self.path)
        except (OSError, UnicodeError) as exc:
            self._record_read_result(succeeded=False, error=exc)
            logger.exception("Failed to read MCP audit log")
            return []

        events: list[dict[str, Any]] = []
        malformed_event_count = 0
        for line in lines:
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > _MAX_AUDIT_EVENT_BYTES:
                malformed_event_count += 1
                continue
            try:
                parsed = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                malformed_event_count += 1
                continue
            safe_event = _project_safe_audit_event(parsed) if isinstance(parsed, dict) else None
            if safe_event is not None:
                events.append(safe_event)
            else:
                malformed_event_count += 1
        incomplete_tail = truncated and not any(line.strip() for line in lines)
        self._record_read_result(
            succeeded=True,
            file_observed=True,
            malformed_event_count=malformed_event_count,
            read_truncated=truncated,
            incomplete_tail=incomplete_tail,
        )
        return events[-bounded_limit:]

    def _append(self, event: MCPAuditEvent) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = asdict(event)
            payload["otel_span"] = _otel_span_projection(event)
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            if len(encoded.encode("utf-8")) > _MAX_AUDIT_EVENT_BYTES:
                raise ValueError("Audit event exceeds the encoded size limit")
            with self._lock:
                descriptor = _open_regular_audit_fd(
                    self.path,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                )
                try:
                    before_write = os.fstat(descriptor)
                    with self._health_lock:
                        expected_identity = self._last_write_identity
                        minimum_size = self._last_write_size
                    if (
                        expected_identity is not None
                        and _file_identity(before_write) != expected_identity
                    ) or (minimum_size is not None and before_write.st_size < minimum_size):
                        raise _UnsafeAuditSinkError(
                            "Audit sink continuity check failed before append"
                        )
                    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                        descriptor = -1
                        handle.write(encoded)
                        handle.flush()
                        metadata = os.fstat(handle.fileno())
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
        except Exception as exc:
            self._record_write_result(succeeded=False, error=exc)
            raise
        self._record_write_result(
            succeeded=True,
            file_identity=_file_identity(metadata),
            file_size=metadata.st_size,
        )
        logger.info(
            "MCP governance event",
            extra={
                "request_id": event.request_id,
                "job_id": event.job_id,
                "tool_name": event.tool_name,
                "duration_ms": event.duration_ms,
            },
        )

    def _record_write_result(
        self,
        *,
        succeeded: bool,
        error: BaseException | None = None,
        file_identity: tuple[int, int] | None = None,
        file_size: int | None = None,
    ) -> None:
        with self._health_lock:
            observed_at = _utc_timestamp()
            self._health.write_attempted = True
            self._health.last_write_succeeded = succeeded
            self._health.last_write_attempt_at = observed_at
            if succeeded:
                if file_identity is None or file_size is None:
                    try:
                        metadata = self.path.lstat()
                    except OSError:
                        metadata = None
                    if metadata is not None and stat.S_ISREG(metadata.st_mode):
                        file_identity = _file_identity(metadata)
                        file_size = metadata.st_size
                self._health.file_observed = True
                self._health.last_write_success_at = observed_at
                self._health.consecutive_write_failures = 0
                self._last_write_identity = file_identity
                self._last_write_size = file_size
            else:
                self._health.last_write_failure_at = observed_at
                self._health.consecutive_write_failures += 1
                self._health.last_write_error_type = type(error).__name__ if error else "Error"

    def _record_read_result(
        self,
        *,
        succeeded: bool,
        file_observed: bool | None = None,
        error: BaseException | None = None,
        malformed_event_count: int = 0,
        read_truncated: bool = False,
        incomplete_tail: bool = False,
    ) -> None:
        with self._health_lock:
            observed_at = _utc_timestamp()
            self._health.read_attempted = True
            self._health.last_read_succeeded = succeeded
            self._health.last_read_attempt_at = observed_at
            if file_observed is not None:
                self._health.file_observed = file_observed
            if succeeded:
                self._health.last_read_success_at = observed_at
            else:
                self._health.last_read_failure_at = observed_at
                self._health.last_read_error_type = type(error).__name__ if error else "Error"
            self._health.malformed_event_count = malformed_event_count
            self._health.read_truncated = read_truncated
            self._health.incomplete_tail = incomplete_tail


class AuditServerContext(Protocol):
    """Minimal server surface required by audit decorators and resources."""

    audit_log: MCPAuditLog

    @property
    def transport(self) -> str:
        raise NotImplementedError


def audit_tool_calls(
    mcp_server_factory: Callable[[], AuditServerContext],
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
            client_id = _client_id(ctx, server.transport)
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
    mcp_server_factory: Callable[[], AuditServerContext],
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
            client_id = _client_id(ctx, server.transport)
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
    mcp_server: AuditServerContext,
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
    audit_sink = mcp_server.audit_log.health_snapshot()
    return [
        _json_resource(
            {
                "schema_version": "1.0",
                "event_count": len(events),
                "events": events,
                "audit_sink": audit_sink,
            }
        )
    ]


def _json_resource(data: dict[str, Any]) -> ReadResourceContents:
    return ReadResourceContents(
        content=json.dumps(data, indent=2),
        mime_type="application/json",
    )


def _resolve_audit_path(
    audit_log_path: str | Path | None,
    journal_path: str | Path | None,
) -> Path:
    if audit_log_path is not None:
        return Path(audit_log_path)
    if journal_path is not None:
        return Path(journal_path).with_name(".mcp_audit_log.jsonl")
    return MCPAuditLog.DEFAULT_PATH


def _read_bounded_tail(path: Path) -> tuple[list[str], bool]:
    """Read at most the configured suffix of an audit JSONL file."""
    with os.fdopen(_open_regular_audit_fd(path, os.O_RDONLY), "rb") as handle:
        handle.seek(0, os.SEEK_END)
        file_size = handle.tell()
        start = max(0, file_size - _MAX_RECENT_READ_BYTES)
        preceding = b"\n"
        if start > 0:
            handle.seek(start - 1)
            preceding = handle.read(1)
        handle.seek(start)
        raw = handle.read(_MAX_RECENT_READ_BYTES)

    truncated = start > 0
    if truncated and preceding != b"\n":
        first_boundary = raw.find(b"\n")
        raw = b"" if first_boundary < 0 else raw[first_boundary + 1 :]
    return raw.decode("utf-8").splitlines(), truncated


class _UnsafeAuditSinkError(OSError):
    """Raised before I/O when the audit sink is not one stable regular file."""


def _open_regular_audit_fd(path: Path, flags: int) -> int:
    """Open one audit file without following or racing symbolic links."""
    create_requested = bool(flags & os.O_CREAT)
    try:
        before = path.lstat()
    except FileNotFoundError:
        if not create_requested:
            raise
    else:
        if not stat.S_ISREG(before.st_mode) or before.st_nlink > 1:
            raise _UnsafeAuditSinkError("Audit sink must be a regular file")

    secure_flags = flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, secure_flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        after = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or opened.st_nlink > 1
            or after.st_nlink > 1
            or _file_identity(opened) != _file_identity(after)
        ):
            raise _UnsafeAuditSinkError("Audit sink changed during secure open")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _file_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _client_id(auth_context: Any, transport: str) -> str:
    if is_local_stdio_context(transport, auth_context):
        return "stdio"
    if auth_context is not None:
        cid = getattr(auth_context, "client_id", None)
        if isinstance(cid, str) and cid:
            return cid
    return "anonymous"


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
    return _bounded_label(value, fallback="unrecognized_error")


def _resource_error_type(
    payload: dict[str, Any],
    exception: BaseException | None,
) -> str | None:
    if exception is not None:
        return exception.__class__.__name__
    value = payload.get("error_type", payload.get("error"))
    if isinstance(value, bool):
        return None
    return _bounded_label(value, fallback="unrecognized_error")


def _approval_token_id(arguments: dict[str, Any], payload: dict[str, Any]) -> str | None:
    result_token_id = _approval_identifier(payload.get("approval_token_id"))
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
    return _approval_identifier(decoded.get("jti"))


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
