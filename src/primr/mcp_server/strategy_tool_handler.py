"""Validated execution boundary for the MCP generate_strategy tool."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.types import TextContent

from primr.mcp_server.approval_tokens import (
    bind_runtime_budget,
    enforce_approval_token,
    strategy_approval_args,
)
from primr.mcp_server.research_policy import coerce_budget_usd, enforce_cost_cap
from primr.mcp_server.server_context import MCPServerContext
from primr.mcp_server.strategy_responses import (
    run_strategy_tool,
    validate_strategy_report,
)
from primr.mcp_server.types import MCPErrorCode

EstimateHandler = Callable[[dict[str, Any]], Awaitable[list[TextContent]]]
StrategyRunner = Callable[..., Awaitable[dict[str, Any]]]


def _text(payload: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload))]


async def handle_generate_strategy(
    mcp_server: MCPServerContext,
    arguments: dict[str, Any],
    *,
    estimate_handler: EstimateHandler,
    strategy_runner: StrategyRunner,
) -> list[TextContent]:
    """Validate, authorize, and generate one strategy document."""
    report_path = arguments.get("report_path")
    strategy_type = arguments.get("strategy_type")
    platform = arguments.get("platform")

    estimate_result = await estimate_handler(arguments)
    estimate_payload = json.loads(estimate_result[0].text)
    if estimate_payload.get("error"):
        return estimate_result
    estimated_cost = float(estimate_payload["estimated_cost_usd"])
    cost_cap_error = enforce_cost_cap(
        estimated_cost=estimated_cost,
        max_estimated_cost_usd=arguments.get("max_estimated_cost_usd"),
        operation_name="generate_strategy",
    )
    if cost_cap_error is not None:
        return _text(cost_cap_error)

    path_result = mcp_server.path_validator.validate(report_path)
    if not path_result.valid:
        return _text(
            {
                "error": True,
                "error_type": path_result.error_type,
                "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                "message": path_result.error_message,
            }
        )
    if not path_result.resolved_path.exists():
        return _text(
            {
                "error": True,
                "error_type": "report_not_found",
                "error_code": MCPErrorCode.REPORT_NOT_FOUND,
                "message": f"Report not found: {report_path}",
            }
        )

    trusted_report, report_error = validate_strategy_report(
        path_result.resolved_path,
        allowed_roots=mcp_server.path_validator.allowed_roots,
    )
    if report_error is not None:
        return _text(report_error)
    assert trusted_report is not None

    approval_error = enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=strategy_approval_args(arguments),
        estimated_cost_usd=estimated_cost,
        approval_token=arguments.get("approval_token"),
    )
    if approval_error is not None:
        return _text(approval_error)

    from primr.utils.run_budget import clear_run_budget, set_run_budget

    budget_usd = bind_runtime_budget(
        coerce_budget_usd(arguments.get("max_estimated_cost_usd")),
        arguments.get("approval_token"),
    )
    budget_active = False
    clear_run_budget()
    try:
        if budget_usd is not None and budget_usd > 0:
            set_run_budget(budget_usd)
            budget_active = True
        return await run_strategy_tool(
            strategy_runner,
            trusted_report=trusted_report,
            strategy_type=strategy_type,
            platform=platform,
        )
    finally:
        if budget_active:
            clear_run_budget()


__all__ = ["handle_generate_strategy"]
