"""Fail-closed MCP strategy workspace error payloads."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.types import TextContent

from primr.core.trusted_report import (
    ReportSnapshotError,
    TrustedReport,
    validate_trusted_report,
)
from primr.core.workspace import ActiveRunLeaseError, ResumeLeaseError
from primr.mcp_server.types import MCPErrorCode

logger = logging.getLogger(__name__)


def validate_strategy_report(
    path: Path,
    *,
    allowed_roots: list[Path],
) -> tuple[TrustedReport | None, dict[str, Any] | None]:
    """Return a root-bound trusted report or one body-safe MCP error."""
    try:
        return validate_trusted_report(path, allowed_roots=allowed_roots), None
    except FileNotFoundError:
        return None, {
            "error": True,
            "error_type": "report_not_found",
            "error_code": MCPErrorCode.REPORT_NOT_FOUND,
            "message": "Report not found",
        }
    except (OSError, RuntimeError):
        logger.warning("Strategy generation refused because report validation was unavailable")
        return None, {
            "error": True,
            "error_type": "report_not_stable",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "message": "Report must be one stable, regular, non-linked file",
        }


def strategy_workspace_error(error: ResumeLeaseError) -> dict[str, Any]:
    """Return a stable operator-facing payload for a strategy lease failure."""
    if isinstance(error, ActiveRunLeaseError):
        logger.info("Strategy generation refused because the company workspace is busy")
        return {
            "error": True,
            "error_type": "strategy_workspace_busy",
            "error_code": MCPErrorCode.JOB_IN_PROGRESS,
            "message": (
                "Another active run is publishing artifacts for this company. "
                "Wait for it to finish, then retry."
            ),
        }

    logger.warning("Strategy generation could not verify company workspace ownership")
    return {
        "error": True,
        "error_type": "strategy_workspace_unavailable",
        "error_code": MCPErrorCode.INTERNAL_ERROR,
        "message": (
            "Could not safely claim this company workspace. "
            "Inspect its ownership record before retrying."
        ),
    }


async def run_strategy_tool(
    runner: Callable[..., Awaitable[dict[str, Any]]],
    *,
    trusted_report: TrustedReport,
    strategy_type: str,
    platform: str | None,
) -> list[TextContent]:
    """Run one strategy and render its stable MCP response contract."""
    try:
        result = await runner(
            trusted_report=trusted_report,
            strategy_type=strategy_type,
            platform=platform,
        )
        payload = {
            "success": True,
            "output_path": result["output_path"],
            "strategy_type": result["strategy_type"],
            "qa_score": result.get("qa_score"),
        }
    except ResumeLeaseError as error:
        payload = strategy_workspace_error(error)
    except ReportSnapshotError:
        logger.warning("Strategy generation refused because report identity changed")
        payload = {
            "error": True,
            "error_type": "report_changed_after_validation",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "message": "The report changed after validation. Request a new estimate and retry.",
        }
    except Exception:
        logger.exception("Strategy generation failed")
        payload = {
            "error": True,
            "error_type": "strategy_generation_failed",
            "message": "Strategy generation failed (see server logs)",
        }
    return [TextContent(type="text", text=json.dumps(payload))]


__all__ = ["run_strategy_tool", "strategy_workspace_error", "validate_strategy_report"]
