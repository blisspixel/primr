"""MCP response adapter for the shared authorized QA operation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from primr.mcp_server.artifact_auth import validate_artifact_input
from primr.mcp_server.server_context import MCPServerContext
from primr.mcp_server.types import MCPErrorCode
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


async def handle_run_qa(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle run_qa tool.

    Requirements: 8.1-8.6
    """
    import json

    report_path = arguments.get("report_path")

    # Validate path
    path_result = validate_artifact_input(mcp_server, report_path)
    if not path_result.valid:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": path_result.error_type,
                        "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                        "message": path_result.error_message,
                    }
                ),
            )
        ]

    # Check if file exists
    if not path_result.resolved_path.exists():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "report_not_found",
                        "error_code": MCPErrorCode.REPORT_NOT_FOUND,
                        "message": f"Report not found: {report_path}",
                    }
                ),
            )
        ]

    # Run QA analysis
    try:
        from primr.mcp_server.qa_operations import run_qa_analysis

        result = await run_qa_analysis(
            str(path_result.resolved_path), allowed_roots=mcp_server.path_validator.allowed_roots
        )

        return [
            TextContent(
                type="text",
                text=json.dumps(result),
            )
        ]

    except Exception:
        # Same rationale as the strategy-generation handler: keep the
        # full traceback in the server log, return a generic message.
        logger.exception("QA analysis failed")
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "qa_analysis_failed",
                        "message": "QA analysis failed (see server logs)",
                    }
                ),
            )
        ]
