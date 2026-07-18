"""Sanitized, bounded cloud diagnostics shared by agent transports."""

from __future__ import annotations

import logging
import math
import os
from typing import Any

logger = logging.getLogger(__name__)


async def get_cloud_diagnostics() -> dict[str, Any]:
    """Gather live control-plane health and configuration-only cloud checks."""
    diagnostics: dict[str, Any] = {}

    def configuration_status(value: str | None) -> dict[str, Any]:
        configured = bool(value and value.strip())
        result: dict[str, Any] = {
            "status": "configured" if configured else "not_configured",
            "configured": configured,
            "probe_performed": False,
        }
        if configured:
            result["detail"] = "Configuration present; connectivity was not tested."
        return result

    control_plane_url = os.environ.get("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{control_plane_url}/healthz")
            diagnostics["container_app_health"] = {
                "status": "ok" if response.status_code == 200 else "error",
                "configured": True,
                "probe_performed": True,
                "http_status": response.status_code,
                "detail": (
                    "Health endpoint responded successfully."
                    if response.status_code == 200
                    else "Health endpoint returned a non-success status."
                ),
            }
    except Exception:
        logger.exception("Cloud diagnostics: Container App health check failed")
        diagnostics["container_app_health"] = {
            "status": "error",
            "configured": True,
            "probe_performed": True,
            "detail": "connectivity check failed",
        }

    diagnostics["cosmos_db"] = configuration_status(os.environ.get("COSMOS_ENDPOINT"))
    diagnostics["blob_storage"] = configuration_status(os.environ.get("STORAGE_ACCOUNT_NAME"))
    diagnostics["service_bus"] = configuration_status(
        os.environ.get("SERVICEBUS_CONNECTION_STRING")
    )
    diagnostics["application_insights"] = configuration_status(
        os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    )

    try:
        max_job_cost = float(os.environ.get("PRIMR_MAX_JOB_COST_USD", "1.0"))
        max_daily_cost = float(os.environ.get("PRIMR_MAX_DAILY_COST_USD", "10.0"))
        max_monthly_cost = float(os.environ.get("PRIMR_MAX_MONTHLY_COST_USD", "100.0"))
        if not all(
            math.isfinite(value) and value >= 0
            for value in (max_job_cost, max_daily_cost, max_monthly_cost)
        ):
            raise ValueError("Cost Governor limits must be finite and non-negative")
        diagnostics["cost_governor"] = {
            "status": "configured",
            "configured": True,
            "probe_performed": False,
            "limits": {
                "max_job_cost_usd": max_job_cost,
                "max_daily_cost_usd": max_daily_cost,
                "max_monthly_cost_usd": max_monthly_cost,
            },
        }
    except Exception:
        logger.exception("Cloud diagnostics: Cost Governor check failed")
        diagnostics["cost_governor"] = {
            "status": "error",
            "configured": True,
            "probe_performed": False,
            "detail": "configuration check failed",
        }

    return diagnostics
