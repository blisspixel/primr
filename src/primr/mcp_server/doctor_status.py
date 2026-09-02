"""Shared, dependency-light system health operation."""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

logger = logging.getLogger(__name__)

DIRECT_PROVIDER_KEY_ENV_VARS = (
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
)


class AuditHealthProvider(Protocol):
    """Minimal body-free audit health contract used by agent transports."""

    def health_snapshot(self) -> dict[str, Any]:
        """Return the current redacted audit-sink state."""
        raise NotImplementedError


def get_doctor_status(*, audit_log: AuditHealthProvider | None = None) -> dict[str, Any]:
    """Return configuration and output-directory health for agent transports."""
    from primr.config.config import OUTPUT_DIR

    warnings: list[str] = []
    api_keys_configured = any(os.environ.get(name) for name in DIRECT_PROVIDER_KEY_ENV_VARS)
    if not api_keys_configured:
        warnings.append(
            "No direct LLM provider key configured "
            "(provider-backed research unavailable; keyless prep and recon remain available)"
        )

    config_valid = True
    try:
        from primr.config.config import validate_config

        result = validate_config()
        hard_errors = [error for error in result.errors if error != "GEMINI_API_KEY not set"]
        config_valid = not hard_errors
        if not config_valid:
            logger.error("Agent health configuration errors: %s", hard_errors)
            warnings.append(
                f"Configuration validation reported {len(hard_errors)} error(s); "
                "inspect the server log."
            )
    except Exception as exc:
        config_valid = False
        logger.exception("Agent health configuration validation failed")
        warnings.append(
            f"Configuration validation failed ({type(exc).__name__}); inspect the server log."
        )

    output_directory_exists = os.path.isdir(OUTPUT_DIR)
    if not output_directory_exists:
        logger.error("Agent health output directory is unavailable: %s", OUTPUT_DIR)
        warnings.append("Output directory is unavailable; inspect the server log.")

    checks: list[dict[str, Any]] = [
        {"component": "configuration", "status": "ok" if config_valid else "error"},
        {
            "component": "provider_keys",
            "status": "configured" if api_keys_configured else "not_configured",
        },
        {
            "component": "output_directory",
            "status": "ok" if output_directory_exists else "missing",
        },
    ]
    audit_health: dict[str, Any] | None = None
    if audit_log is not None:
        try:
            audit_health = audit_log.health_snapshot()
        except Exception as exc:
            audit_health = {
                "schema_version": "1.0",
                "status": "degraded",
                "sink": "jsonl",
                "health_error_type": type(exc).__name__,
            }
        audit_status = str(audit_health.get("status") or "degraded")
        checks.append({"component": "audit_log", "status": audit_status})
        if audit_status != "ok":
            if audit_status == "not_observed":
                warnings.append("Audit persistence has not been observed yet.")
            else:
                warnings.append("Audit persistence is degraded; inspect the MCP/A2A server log.")

    if not config_valid:
        status = "unhealthy"
    elif warnings:
        status = "degraded"
    else:
        status = "healthy"

    response: dict[str, Any] = {
        "status": status,
        "checks": checks,
        "orphaned_stores_count": 0,
        "config_valid": config_valid,
        "api_keys_configured": api_keys_configured,
        "warnings": warnings,
    }
    if audit_health is not None:
        response["audit_log"] = audit_health
    return response


def attach_cloud_diagnostics(
    response: dict[str, Any], diagnostics: dict[str, Any]
) -> dict[str, Any]:
    """Attach sanitized cloud checks and fold observed failures into overall health."""
    response["cloud_mode"] = True
    response["cloud_diagnostics"] = diagnostics
    checks = response.setdefault("checks", [])
    warnings = response.setdefault("warnings", [])
    cloud_failed = False
    allowed_statuses = {"ok", "configured", "not_configured", "error"}

    for component, detail in diagnostics.items():
        raw_status = detail.get("status") if isinstance(detail, dict) else None
        status = str(raw_status) if raw_status in allowed_statuses else "error"
        checks.append({"component": f"cloud.{component}", "status": status})
        if status == "error":
            cloud_failed = True

    if cloud_failed:
        warnings.append("One or more cloud health checks failed; inspect the server log.")
        if response.get("status") == "healthy":
            response["status"] = "degraded"
    return response


__all__ = [
    "DIRECT_PROVIDER_KEY_ENV_VARS",
    "AuditHealthProvider",
    "attach_cloud_diagnostics",
    "get_doctor_status",
]
