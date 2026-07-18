"""Fail-closed MCP strategy workspace error payloads."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.types import TextContent

from primr.core.workspace import ActiveRunLeaseError, ResumeLeaseError
from primr.mcp_server.types import MCPErrorCode

logger = logging.getLogger(__name__)


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
    report_path: str,
    strategy_type: str,
    platform: str | None,
) -> list[TextContent]:
    """Run one strategy and render its stable MCP response contract."""
    try:
        result = await runner(
            report_path=report_path,
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
    except Exception:
        logger.exception("Strategy generation failed")
        payload = {
            "error": True,
            "error_type": "strategy_generation_failed",
            "message": "Strategy generation failed (see server logs)",
        }
    return [TextContent(type="text", text=json.dumps(payload))]


__all__ = ["run_strategy_tool", "strategy_workspace_error"]
