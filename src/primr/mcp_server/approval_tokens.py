"""Server-issued approval tokens for cost-incurring MCP tools."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from primr.mcp_server.cost_caps import is_cost_cap_enforced
from primr.mcp_server.platforms import normalize_platform, normalize_platforms
from primr.mcp_server.types import MCPErrorCode

APPROVAL_TOKEN_TTL_SECONDS = 30 * 60
APPROVAL_TOKEN_SCHEMA = {
    "type": "string",
    "description": "Server-issued approval token returned by the matching estimate tool.",
}
_PROCESS_SECRET = secrets.token_bytes(32)
_PROCESS_INSTANCE_ID = secrets.token_urlsafe(24)
_USED_TOKEN_IDS: dict[str, float] = {}
_USED_LOCK = Lock()


def research_approval_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the cost-affecting approval shape for research execution."""
    mode = str(arguments.get("mode") or "full")
    no_ai_strategy = bool(arguments.get("no_ai_strategy", False))
    include_ai_strategy = not no_ai_strategy and mode in {"full", "premium"}
    raw_platforms = arguments.get("platforms")
    if raw_platforms is None and arguments.get("platform"):
        raw_platforms = [arguments["platform"]]
    if raw_platforms is None:
        raw_platforms = ["agnostic"]
    if isinstance(raw_platforms, str):
        raw_platforms = [raw_platforms]
    platforms = normalize_platforms([str(platform) for platform in raw_platforms])
    return {
        "company_url": str(arguments.get("company_url") or "").strip(),
        "mode": mode,
        "no_ai_strategy": no_ai_strategy,
        "platforms": platforms if include_ai_strategy else [],
        "strategy_type": str(arguments.get("strategy_type") or "ai"),
        "verify": bool(arguments.get("verify", False)),
    }


def strategy_approval_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return the cost-affecting approval shape for strategy generation."""
    platform = arguments.get("platform")
    return {
        "strategy_type": str(arguments.get("strategy_type") or ""),
        "platform": normalize_platform(str(platform)) if platform else None,
    }


def skill_pack_approval_args(
    *,
    effective_roles: int,
    skills_per_role: int,
    has_report_path: bool,
    has_operator_role_brief: bool,
    has_career_urls: bool,
    max_refine_iterations: int,
    saved_plan_sha256: str | None,
    saved_plan_prompt_chars: int,
    roles_override: list[str],
    roles_add: list[str],
    roles_skip: list[str],
    remote_icons: bool = False,
) -> dict[str, Any]:
    """Return the cost-affecting approval shape for skill-pack generation."""
    return {
        "effective_roles": int(effective_roles),
        "skills_per_role": int(skills_per_role),
        "uses_existing_report": bool(has_report_path),
        "uses_operator_role_brief": bool(has_operator_role_brief),
        "uses_career_urls": bool(has_career_urls),
        "max_refine_iterations": int(max_refine_iterations),
        "saved_plan_sha256": saved_plan_sha256,
        "saved_plan_prompt_chars": int(saved_plan_prompt_chars),
        "roles_override": list(roles_override),
        "roles_add": list(roles_add),
        "roles_skip": list(roles_skip),
        "remote_icons": bool(remote_icons),
    }


def issue_approval_token(
    *,
    tool_name: str,
    approval_args: dict[str, Any],
    max_cost_usd: float,
) -> dict[str, Any]:
    """Return serializable approval-token fields for an estimate response."""
    now = int(time.time())
    expires_at = now + APPROVAL_TOKEN_TTL_SECONDS
    token_id = secrets.token_urlsafe(16)
    payload = {
        "v": 2,
        "jti": token_id,
        "instance": _PROCESS_INSTANCE_ID,
        "tool": tool_name,
        "args_hash": _hash_approval_args(approval_args),
        "max_cost_usd": round(float(max_cost_usd), 4),
        "iat": now,
        "exp": expires_at,
    }
    encoded_payload = _b64encode_json(payload)
    signature = _sign(encoded_payload)
    return {
        "approval_token": f"{encoded_payload}.{signature}",
        "approval_token_id": token_id,
        "approval_expires_at": _iso_from_epoch(expires_at),
    }


def enforce_approval_token(
    *,
    tool_name: str,
    approval_args: dict[str, Any],
    estimated_cost_usd: float,
    approval_token: object,
) -> dict[str, Any] | None:
    """Return a structured MCP error when an enforced approval token is invalid."""
    if not is_cost_cap_enforced():
        return None
    if not isinstance(approval_token, str) or not approval_token.strip():
        return _approval_error(
            "approval_token_required",
            MCPErrorCode.APPROVAL_TOKEN_REQUIRED,
            (
                "approval_token is required for cost-governed MCP execution; "
                "call the matching estimate tool, get user approval, then pass the "
                "returned approval_token into this tool."
            ),
        )

    try:
        payload = _decode_token(approval_token.strip())
        _validate_payload(payload, tool_name, approval_args, estimated_cost_usd)
        _mark_token_used(str(payload["jti"]), float(payload["exp"]))
    except ValueError as exc:
        return _approval_error(
            "invalid_approval_token",
            MCPErrorCode.INVALID_APPROVAL_TOKEN,
            f"approval_token is invalid: {exc}",
        )
    return None


def approval_token_audit(approval_token: object) -> dict[str, str] | None:
    """Return non-secret issuance metadata from a validated approval token."""
    if not isinstance(approval_token, str) or not approval_token.strip():
        return None
    try:
        payload = _decode_token(approval_token.strip())
        token_id = payload["jti"]
        issued_at = payload["iat"]
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(token_id, str) or not token_id:
        return None
    try:
        issued_at_iso = _iso_from_epoch(int(issued_at))
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    return {"approval_token_id": token_id, "estimated_at": issued_at_iso}


def _hash_approval_args(approval_args: dict[str, Any]) -> str:
    canonical = json.dumps(approval_args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _approval_secret() -> bytes:
    configured = os.getenv("PRIMR_MCP_APPROVAL_TOKEN_SECRET") or os.getenv("MCP_JWT_SECRET")
    if configured:
        return configured.encode("utf-8")
    return _PROCESS_SECRET


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _b64encode_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _b64encode(raw)


def _sign(encoded_payload: str) -> str:
    digest = hmac.new(
        _approval_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _decode_token(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("malformed token")
    encoded_payload, signature = parts
    if not hmac.compare_digest(_sign(encoded_payload), signature):
        raise ValueError("bad signature")
    try:
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("malformed payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("malformed payload")
    return payload


def _validate_payload(
    payload: dict[str, Any],
    tool_name: str,
    approval_args: dict[str, Any],
    estimated_cost_usd: float,
) -> None:
    if payload.get("v") != 2:
        raise ValueError("unsupported token version")
    instance = payload.get("instance")
    if not isinstance(instance, str) or not hmac.compare_digest(
        instance,
        _PROCESS_INSTANCE_ID,
    ):
        raise ValueError("token was issued by another server process; request a new estimate")
    if payload.get("tool") != tool_name:
        raise ValueError("tool mismatch")
    if payload.get("args_hash") != _hash_approval_args(approval_args):
        raise ValueError("approval arguments do not match")

    try:
        expires_at = float(payload["exp"])
        max_cost_usd = float(payload["max_cost_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("malformed payload") from exc
    if time.time() > expires_at:
        raise ValueError("token expired")
    if not math.isfinite(max_cost_usd) or max_cost_usd < 0:
        raise ValueError("invalid approved cost")
    if estimated_cost_usd > max_cost_usd:
        raise ValueError("estimated cost exceeds approved token cost")
    if not isinstance(payload.get("jti"), str) or not payload["jti"]:
        raise ValueError("missing token id")


def _mark_token_used(token_id: str, expires_at: float) -> None:
    now = time.time()
    with _USED_LOCK:
        expired = [jti for jti, exp in _USED_TOKEN_IDS.items() if exp <= now]
        for jti in expired:
            _USED_TOKEN_IDS.pop(jti, None)
        if token_id in _USED_TOKEN_IDS:
            raise ValueError("token already used")
        _USED_TOKEN_IDS[token_id] = expires_at


def _approval_error(error_type: str, error_code: MCPErrorCode, message: str) -> dict[str, Any]:
    return {
        "error": True,
        "error_type": error_type,
        "error_code": error_code,
        "message": message,
    }


def _iso_from_epoch(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")
