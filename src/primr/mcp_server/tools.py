"""
Tool handler implementations for MCP server.

This module provides executable tools for research operations:
- estimate_run - Cost/time estimates
- estimate_strategy - Strategy cost/time estimates
- research_company - Initiate research pipeline
- generate_strategy - Generate strategy documents
- check_jobs - Check Deep Research job status
- run_qa - Run quality assessment
- doctor - System health check
- clear_jobs - Clear stale jobs
- cancel_job - Cancel active job

Agentic tools (from agentic_tools.py):
- query_roadmap - Query roadmap for version status, blockers, features
- get_hypotheses - Retrieve hypotheses for a company
- save_hypothesis - Save or update a hypothesis

Requirements: 5.1-5.13, 6.1-6.7, 7.1-7.6, 8.1-8.6, 18.1-18.12
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from mcp.server import Server
from mcp.types import TextContent, Tool

from primr.mcp_server.agentic_tools import handle_agentic_tool, register_agentic_tools
from primr.mcp_server.approval_tokens import (
    APPROVAL_TOKEN_SCHEMA,
    enforce_approval_token,
    issue_approval_token,
    research_approval_args,
    strategy_approval_args,
)
from primr.mcp_server.audit_log import audit_tool_calls
from primr.mcp_server.job_store import JobInProgressError, ResearchJobState
from primr.mcp_server.platforms import normalize_platform, normalize_platforms
from primr.mcp_server.skill_pack_tools import handle_skill_pack_tool, register_skill_pack_tools
from primr.mcp_server.tool_authz import authorize_tool_call, scope_denied_response
from primr.mcp_server.types import MCPErrorCode, ResearchStage

if TYPE_CHECKING:
    from primr.mcp_server.server import PrimrMCPServer

logger = logging.getLogger(__name__)
_normalize_platform = normalize_platform
_normalize_platforms = normalize_platforms


def register_tools(server: Server, mcp_server: "PrimrMCPServer") -> None:
    """Register all Primr tools with the MCP server."""

    # Get agentic tools
    agentic_tools = register_agentic_tools(server, mcp_server)
    # Get skill-pack tools (estimate_skill_pack, generate_skill_pack)
    skill_pack_tools = register_skill_pack_tools(server, mcp_server)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        base_tools = [
            Tool(
                name="estimate_run",
                description="Estimate cost and time for a research run without executing. Call this before any cost-incurring research run.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company_url": {
                            "type": "string",
                            "description": "Company website URL",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["scrape", "deep", "full", "premium"],
                            "default": "full",
                            "description": "Research mode: full (standard Grok pipeline, default), premium (Gemini + Deep Research), scrape, deep",
                        },
                        "platforms": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "azure",
                                    "aws",
                                    "gcp",
                                    "agnostic",
                                    "private",
                                    "microsoft",
                                    "amazon",
                                    "google",
                                    "nvidia",
                                    "ms",
                                ],
                            },
                            "description": "Platform(s) for AI strategy (CLI: --platform). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private. Each adds a separate strategy document and ~3-6 min + ~$0.10-0.15 per vendor. Default: single agnostic strategy.",
                        },
                        "strategy_type": {
                            "type": "string",
                            "enum": [
                                "ai",
                                "customer_experience",
                                "modern_security_compliance",
                                "data_fabric_strategy",
                                "skills",
                            ],
                            "default": "ai",
                            "description": "Type of strategy to generate alongside the research report",
                        },
                        "no_ai_strategy": {
                            "type": "boolean",
                            "default": False,
                            "description": "Skip AI strategy generation entirely (report only)",
                        },
                        "verify": {
                            "type": "boolean",
                            "default": False,
                            "description": "Run post-QA claim verification (~$0.01, 3-5 min)",
                        },
                        "max_estimated_cost_usd": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Optional hard ceiling for estimated run cost. The server rejects execution if the estimate exceeds this cap.",
                        },
                    },
                    "required": ["company_url"],
                },
            ),
            Tool(
                name="estimate_strategy",
                description="Estimate cost and time for a strategy document without executing. Call this before any cost-incurring strategy generation.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "strategy_type": {
                            "type": "string",
                            "enum": [
                                "ai_strategy",
                                "customer_experience",
                                "modern_security_compliance",
                                "data_fabric_strategy",
                                "skills",
                            ],
                            "description": "Type of strategy to estimate",
                        },
                        "platform": {
                            "type": "string",
                            "enum": [
                                "azure",
                                "aws",
                                "gcp",
                                "agnostic",
                                "private",
                                "microsoft",
                                "amazon",
                                "google",
                                "nvidia",
                                "ms",
                            ],
                            "description": "Platform for AI strategy (CLI: --platform). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private.",
                        },
                    },
                    "required": ["strategy_type"],
                },
            ),
            Tool(
                name="research_company",
                description="Initiate company research pipeline (async - returns job_id immediately). Includes AI strategy generation when platform is specified — no separate strategy call needed. This incurs real API cost and should only be called after the user approves an estimate from estimate_run.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company_name": {
                            "type": "string",
                            "description": "Display name for the company",
                        },
                        "company_url": {
                            "type": "string",
                            "description": "Company website URL (must be valid HTTP/HTTPS)",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["scrape", "deep", "full", "premium"],
                            "default": "full",
                            "description": "Research mode: full (standard Grok pipeline, default), premium (Gemini + Deep Research), scrape, deep",
                        },
                        "platform": {
                            "type": "string",
                            "enum": [
                                "azure",
                                "aws",
                                "gcp",
                                "agnostic",
                                "private",
                                "microsoft",
                                "amazon",
                                "google",
                                "nvidia",
                                "ms",
                            ],
                            "description": "Platform for AI strategy (CLI: --platform). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private. When set, strategy is generated as part of this job (no separate generate_strategy call needed). Default: agnostic.",
                        },
                        "skip_qa": {
                            "type": "boolean",
                            "default": False,
                            "description": "Skip quality assessment",
                        },
                        "verify": {
                            "type": "boolean",
                            "default": False,
                            "description": "Run post-QA claim verification (~$0.01, 3-5 min)",
                        },
                        "destination": {
                            "type": "string",
                            "description": "Optional destination directory for output files. If not specified, uses the default output/ directory.",
                        },
                        "approval_token": APPROVAL_TOKEN_SCHEMA,
                    },
                    "required": ["company_name", "company_url"],
                },
            ),
            Tool(
                name="generate_strategy",
                description="Generate strategy document from an existing report AFTER the fact. Only needed when adding a strategy to a previously completed research run. For new research, use research_company with platform instead — strategy is included automatically.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_path": {
                            "type": "string",
                            "description": "Path to existing research report",
                        },
                        "strategy_type": {
                            "type": "string",
                            "enum": [
                                "ai_strategy",
                                "customer_experience",
                                "modern_security_compliance",
                                "data_fabric_strategy",
                                "skills",
                            ],
                            "description": "Type of strategy to generate",
                        },
                        "platform": {
                            "type": "string",
                            "enum": [
                                "azure",
                                "aws",
                                "gcp",
                                "agnostic",
                                "private",
                                "microsoft",
                                "amazon",
                                "google",
                                "nvidia",
                                "ms",
                            ],
                            "description": "Platform for AI strategy (CLI: --platform). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private. Default: agnostic.",
                        },
                        "max_estimated_cost_usd": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Optional hard ceiling for estimated strategy cost. The server rejects execution if the estimate exceeds this cap.",
                        },
                        "approval_token": APPROVAL_TOKEN_SCHEMA,
                    },
                    "required": ["report_path", "strategy_type"],
                },
            ),
            Tool(
                name="check_jobs",
                description="Check status of research jobs. When a job is completed, returns full artifact content (report + strategy MD files) inline so you can consume them directly without filesystem access.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "Specific job ID to check (optional)",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="run_qa",
                description="Run quality assessment on a report. This may incur real API cost depending on the configured QA path.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_path": {
                            "type": "string",
                            "description": "Path to report file (txt, md, docx)",
                        },
                    },
                    "required": ["report_path"],
                },
            ),
            Tool(
                name="doctor",
                description="Check system health and configuration",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name="clear_jobs",
                description="Clear stale pending jobs",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "older_than_hours": {
                            "type": "integer",
                            "default": 24,
                            "description": "Clear jobs older than this (default: 24)",
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="cancel_job",
                description="Attempt best-effort cancellation of an active job",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to cancel",
                        },
                    },
                    "required": ["job_id"],
                },
            ),
            Tool(
                name="wait_for_status_change",
                description="Wait for a job status to change (blocks until change or timeout)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The job ID to monitor",
                        },
                        "timeout_seconds": {
                            "type": "number",
                            "default": 60,
                            "minimum": 1,
                            "maximum": 300,
                            "description": "Maximum seconds to wait (default: 60, max: 300)",
                        },
                    },
                    "required": ["job_id"],
                },
            ),
            Tool(
                name="show_usage",
                description="Check your current spending and remaining budget. Shows daily, monthly, and all-time costs with remaining limits.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
        ]

        # Add A2A delegate tool if a2a-sdk is available
        try:
            from primr.a2a.client import A2AClient  # noqa: F401

            base_tools.append(
                Tool(
                    name="delegate_to_agent",
                    description="Delegate a task to an external A2A agent",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_url": {
                                "type": "string",
                                "description": "URL of the A2A agent to call",
                            },
                            "message": {
                                "type": "string",
                                "description": "Message to send to the agent",
                            },
                            "skill_id": {
                                "type": "string",
                                "description": "Optional skill ID to target on the remote agent",
                            },
                        },
                        "required": ["agent_url", "message"],
                    },
                ),
            )
        except ImportError:
            pass

        # Include agentic + skill_pack tools
        return base_tools + agentic_tools + skill_pack_tools

    @server.call_tool()
    @audit_tool_calls(lambda: mcp_server)
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        import json

        # Rate limiting and authz use stdio locally, or the bridged HTTP context.
        client_id = "stdio"
        ctx = getattr(mcp_server, "_auth_context", None)
        if ctx is not None:
            _cid = getattr(ctx, "client_id", None)
            if isinstance(_cid, str) and _cid:
                client_id = _cid

        if not (authz := authorize_tool_call(name, ctx)).allowed:
            return scope_denied_response(name, authz)

        rate_result = mcp_server.rate_limiter.check_and_record(client_id, name)
        if not rate_result.allowed:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": "rate_limit_exceeded",
                            "error_code": MCPErrorCode.RATE_LIMIT_EXCEEDED,
                            "message": "Rate limit exceeded",
                            "retry_after_seconds": rate_result.retry_after_seconds,
                        }
                    ),
                )
            ]

        # Try agentic tools first
        agentic_result = await handle_agentic_tool(name, arguments, mcp_server)
        if agentic_result is not None:
            return agentic_result

        # Try skill_pack tools
        skill_pack_result = await handle_skill_pack_tool(name, arguments, mcp_server)
        if skill_pack_result is not None:
            return skill_pack_result

        # Dispatch to handler
        if name == "estimate_run":
            return await _handle_estimate_run(mcp_server, arguments)
        elif name == "estimate_strategy":
            return await _handle_estimate_strategy(arguments)
        elif name == "research_company":
            return await _handle_research_company(mcp_server, arguments, client_id)
        elif name == "generate_strategy":
            return await _handle_generate_strategy(mcp_server, arguments)
        elif name == "check_jobs":
            return await _handle_check_jobs(mcp_server, arguments, client_id)
        elif name == "run_qa":
            return await _handle_run_qa(mcp_server, arguments)
        elif name == "doctor":
            return await _handle_doctor(mcp_server, arguments)
        elif name == "clear_jobs":
            return await _handle_clear_jobs(mcp_server, arguments, client_id)
        elif name == "cancel_job":
            return await _handle_cancel_job(mcp_server, arguments, client_id)
        elif name == "wait_for_status_change":
            return await _handle_wait_for_status_change(mcp_server, arguments, client_id)
        elif name == "delegate_to_agent":
            return await _handle_delegate_to_agent(mcp_server, arguments)
        elif name == "show_usage":
            return await _handle_show_usage(mcp_server, client_id)

        raise ValueError(f"Unknown tool: {name}")


def _parse_max_duration(duration_str: str, default: int = 30) -> int:
    """Parse the max minutes from a duration string like '5-10 min'."""
    try:
        parts = duration_str.split("-")
        if len(parts) >= 2:
            return int(parts[1].split()[0])
        return int(parts[0].split()[0])
    except (ValueError, IndexError):
        return default


def _is_cost_cap_enforced() -> bool:
    from primr.mcp_server.cost_caps import is_cost_cap_enforced

    return is_cost_cap_enforced()


def _build_research_estimate(arguments: dict[str, Any]) -> dict[str, Any]:
    import os

    from primr.utils.cost_estimator import estimate_cost

    mode = arguments.get("mode", "full")
    mode_mapping = {
        "scrape": "scrape-only",
        "deep": "deep-research",
        "full": "complete",
        "premium": "complete",
    }
    estimator_mode = mode_mapping.get(mode, "complete")
    verify = arguments.get("verify", False)
    premium_mode = mode == "premium"
    fast_mode = mode == "full" and bool(os.environ.get("XAI_API_KEY"))
    from primr.core.budget_policy import describe_budget_enforcement

    # Strategy configuration
    no_ai_strategy = arguments.get("no_ai_strategy", False)
    include_ai_strategy = not no_ai_strategy and mode in ("full", "premium")
    platforms = arguments.get("platforms", ["agnostic"])
    if isinstance(platforms, str):
        platforms = [platforms]
    platforms = _normalize_platforms(platforms)
    num_vendors = len(platforms) if include_ai_strategy else 0

    cost_estimate = estimate_cost(
        estimator_mode,
        include_ai_strategy=include_ai_strategy,
        use_historical=True,
        verify=verify,
        premium_mode=premium_mode,
        fast_mode=fast_mode,
        num_vendors=max(num_vendors, 1) if include_ai_strategy else 1,
    )
    pages = 20 if mode in ("scrape", "full", "premium") else 0
    max_duration = _parse_max_duration(cost_estimate.duration_minutes)
    result: dict[str, Any] = {
        "estimated_cost_usd": round(cost_estimate.total_cost, 2),
        "estimated_time_minutes": max_duration,
        "estimated_time_range": cost_estimate.duration_minutes,
        "planned_pages": pages,
        "mode": mode,
        "budget_enforcement": describe_budget_enforcement(
            mode=estimator_mode,
            fast_mode=fast_mode,
            premium_mode=premium_mode,
        ).as_dict(),
    }
    if include_ai_strategy:
        result["ai_strategy"] = True
        result["platforms"] = platforms
        result["strategy_type"] = arguments.get("strategy_type", "ai")
    else:
        result["ai_strategy"] = False
    return result


def _enforce_cost_cap(
    estimated_cost: float,
    max_estimated_cost_usd: float | None,
    operation_name: str,
) -> dict[str, Any] | None:
    if max_estimated_cost_usd is None:
        if _is_cost_cap_enforced():
            return {
                "error": True,
                "error_type": "cost_cap_required",
                "error_code": MCPErrorCode.COST_CAP_REQUIRED,
                "message": (
                    f"{operation_name} requires max_estimated_cost_usd when PRIMR_ENFORCE_MCP_COST_CAPS is enabled"
                ),
            }
        return None

    # Coerce the cap to a finite, non-negative float before comparing. MCP
    # input schemas are advisory and the packaged OpenClaw workflows pass the
    # estimate through quoted interpolation, so this value can arrive as a
    # string (e.g. "0.30") or another non-numeric JSON type. A raw
    # `estimated_cost > max_estimated_cost_usd` would then raise TypeError (or
    # silently mis-compare against NaN/Infinity). Return a structured error so
    # the cost governor fails closed instead of bubbling an opaque tool error.
    try:
        cap = float(max_estimated_cost_usd)
    except (TypeError, ValueError):
        return {
            "error": True,
            "error_type": "invalid_cost_cap",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "message": (
                f"max_estimated_cost_usd must be a number for {operation_name}, "
                f"got {max_estimated_cost_usd!r}"
            ),
        }
    if not math.isfinite(cap) or cap < 0:
        return {
            "error": True,
            "error_type": "invalid_cost_cap",
            "error_code": MCPErrorCode.INVALID_PARAMS,
            "message": (
                f"max_estimated_cost_usd must be a finite, non-negative number for "
                f"{operation_name}, got {max_estimated_cost_usd!r}"
            ),
        }

    if estimated_cost > cap:
        return {
            "error": True,
            "error_type": "cost_cap_exceeded",
            "error_code": MCPErrorCode.COST_CAP_EXCEEDED,
            "message": (
                f"Estimated cost ${estimated_cost:.2f} exceeds approved cap ${cap:.2f} for {operation_name}"
            ),
            "estimated_cost_usd": estimated_cost,
            "max_estimated_cost_usd": cap,
        }
    return None


async def _handle_estimate_run(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle estimate_run tool.

    Requirements: 18.1, 18.2, 18.3
    """
    import json

    company_url = arguments.get("company_url")

    # Validate URL
    url_result = mcp_server.url_validator.validate(company_url)
    if not url_result.valid:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": url_result.error_type,
                        "error_code": {
                            "invalid_url": MCPErrorCode.INVALID_URL,
                            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
                            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
                        }.get(url_result.error_type, MCPErrorCode.INVALID_URL),
                        "message": url_result.error_message,
                    }
                ),
            )
        ]

    estimate = _build_research_estimate(arguments)
    estimate.update(
        issue_approval_token(
            tool_name="research_company",
            approval_args=research_approval_args(arguments),
            max_cost_usd=float(estimate["estimated_cost_usd"]),
        )
    )

    return [
        TextContent(
            type="text",
            text=json.dumps(estimate),
        )
    ]


async def _handle_estimate_strategy(arguments: dict[str, Any]) -> list[TextContent]:
    """Handle estimate_strategy tool."""
    import json

    from primr.mcp_server.resources import get_strategy_catalog

    strategy_type = arguments.get("strategy_type")
    platform = arguments.get("platform")
    if platform:
        platform = _normalize_platform(platform)

    strategy = next((item for item in get_strategy_catalog() if item["id"] == strategy_type), None)
    if strategy is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "invalid_strategy_type",
                        "message": f"Unknown strategy type: {strategy_type}",
                    }
                ),
            )
        ]

    if strategy["requires_platform"] and not platform:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "missing_platform",
                        "message": "platform is required for ai_strategy estimates",
                    }
                ),
            )
        ]

    estimated_cost_usd = float(cast("float", strategy["estimated_cost_usd"]))
    payload = {
        "strategy_type": strategy["id"],
        "estimated_cost_usd": estimated_cost_usd,
        "estimated_time_minutes": strategy["estimated_time_minutes"],
        "requires_platform": strategy["requires_platform"],
        "platform": platform,
        "cost_warning": (
            "Strategy generation incurs real API charges. Get explicit user approval "
            "before generate_strategy."
        ),
    }
    payload.update(
        issue_approval_token(
            tool_name="generate_strategy",
            approval_args=strategy_approval_args(arguments),
            max_cost_usd=estimated_cost_usd,
        )
    )
    return [TextContent(type="text", text=json.dumps(payload))]


async def _handle_research_company(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle research_company tool.

    Returns immediately with job_id (async model).
    Starts background task to run research pipeline (unless disabled for testing).

    Requirements: 5.1-5.13
    """
    import asyncio
    import json

    company_name = arguments.get("company_name")
    company_url = arguments.get("company_url")
    mode = arguments.get("mode", "full")
    platform = arguments.get("platform")
    skip_qa = arguments.get("skip_qa", False)
    verify = arguments.get("verify", False)
    max_estimated_cost_usd = arguments.get("max_estimated_cost_usd")
    destination = arguments.get("destination")

    # The fast pipeline uses company_name in report and working-folder paths.
    # Reject traversal and drive prefixes before artifacts are written.
    from primr.utils.validators import InputValidationError, validate_company_name

    try:
        company_name = validate_company_name(company_name or "")
    except InputValidationError as e:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "invalid_company_name",
                        "message": e.reason,
                    }
                ),
            )
        ]

    # destination is documented as output/-scoped, so validate it through the
    # same path guard used for report_path tools before mkdir()/copy2().
    if destination is not None:
        dest_result = mcp_server.path_validator.validate(destination, client_id)
        if not dest_result.valid:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": dest_result.error_type,
                            "error_code": MCPErrorCode.PATH_TRAVERSAL_BLOCKED,
                            "message": f"Invalid destination: {dest_result.error_message}",
                        }
                    ),
                )
            ]
        destination = str(dest_result.resolved_path)

    # Keep execution shape aligned with the estimate: no_ai_strategy lowers the
    # approved cost, so it must also suppress platform-driven strategy work.
    no_ai_strategy = bool(arguments.get("no_ai_strategy", False))
    if no_ai_strategy:
        platform = None

    # Validate URL
    url_result = mcp_server.url_validator.validate(company_url)
    if not url_result.valid:
        error_code = {
            "invalid_url": MCPErrorCode.INVALID_URL,
            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
        }.get(url_result.error_type, MCPErrorCode.INVALID_URL)

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": url_result.error_type,
                        "error_code": error_code,
                        "message": url_result.error_message,
                    }
                ),
            )
        ]

    estimate = _build_research_estimate(arguments)
    cost_cap_error = _enforce_cost_cap(
        estimated_cost=float(estimate["estimated_cost_usd"]),
        max_estimated_cost_usd=max_estimated_cost_usd,
        operation_name="research_company",
    )
    if cost_cap_error is not None:
        return [TextContent(type="text", text=json.dumps(cost_cap_error))]
    approval_error = enforce_approval_token(
        tool_name="research_company",
        approval_args=research_approval_args(arguments),
        estimated_cost_usd=float(estimate["estimated_cost_usd"]),
        approval_token=arguments.get("approval_token"),
    )
    if approval_error is not None:
        return [TextContent(type="text", text=json.dumps(approval_error))]
    budget_usd = float(max_estimated_cost_usd) if max_estimated_cost_usd is not None else None

    # Try to create job
    try:
        job = mcp_server.job_store.create(
            company_name=company_name,
            mode=mode,
            owner_client_id=client_id,
        )
    except JobInProgressError as e:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_in_progress",
                        "error_code": MCPErrorCode.JOB_IN_PROGRESS,
                        "message": f"Job {e.active_job_id} already in progress",
                        "active_job_id": e.active_job_id,
                    }
                ),
            )
        ]

    # Start background task to run research pipeline
    # Skip if _skip_background_tasks is set (for testing)
    if not getattr(mcp_server, "_skip_background_tasks", False):
        from primr.mcp_server.pipeline_runner import PipelineRunner

        runner = PipelineRunner(mcp_server)
        task = asyncio.create_task(
            runner.run_research(
                job=job,
                company_url=company_url,
                mode=mode,
                platform=platform,
                skip_qa=skip_qa,
                verify=verify,
                destination=destination,
                budget_usd=budget_usd,
            )
        )
        # Track task for graceful shutdown
        mcp_server._track_task(task)

    logger.info("Created research job %s for %s", job.job_id, company_name)

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "job_id": job.job_id,
                    "accepted": True,
                    "status_uri": "primr://research/status",
                }
            ),
        )
    ]


async def _handle_generate_strategy(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle generate_strategy tool.

    Requirements: 6.1-6.7
    """
    import json

    report_path = arguments.get("report_path")
    strategy_type = arguments.get("strategy_type")
    platform = arguments.get("platform")
    max_estimated_cost_usd = arguments.get("max_estimated_cost_usd")

    estimate_result = await _handle_estimate_strategy(arguments)
    estimate_payload = json.loads(estimate_result[0].text)
    if estimate_payload.get("error"):
        return estimate_result
    cost_cap_error = _enforce_cost_cap(
        estimated_cost=float(estimate_payload["estimated_cost_usd"]),
        max_estimated_cost_usd=max_estimated_cost_usd,
        operation_name="generate_strategy",
    )
    if cost_cap_error is not None:
        return [TextContent(type="text", text=json.dumps(cost_cap_error))]

    # Validate path
    path_result = mcp_server.path_validator.validate(report_path)
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

    # Check if file exists (only after path validation passes)
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

    approval_error = enforce_approval_token(
        tool_name="generate_strategy",
        approval_args=strategy_approval_args(arguments),
        estimated_cost_usd=float(estimate_payload["estimated_cost_usd"]),
        approval_token=arguments.get("approval_token"),
    )
    if approval_error is not None:
        return [TextContent(type="text", text=json.dumps(approval_error))]

    # Run strategy generation
    try:
        from primr.mcp_server.pipeline_runner import run_strategy_generation

        result = await run_strategy_generation(
            report_path=str(path_result.resolved_path),
            strategy_type=strategy_type,
            platform=platform,
        )

        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": True,
                        "output_path": result["output_path"],
                        "strategy_type": result["strategy_type"],
                        "qa_score": result.get("qa_score"),
                    }
                ),
            )
        ]

    except Exception:
        # Full traceback is in the server log. The user-facing message
        # intentionally omits exception text because provider errors can
        # contain internal hostnames, file paths under OUTPUT_DIR, and
        # occasionally API-key fragments.
        logger.exception("Strategy generation failed")
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "strategy_generation_failed",
                        "message": "Strategy generation failed (see server logs)",
                    }
                ),
            )
        ]


def _caller_owns_job(job: "ResearchJobState", client_id: str) -> bool:
    """Whether ``client_id`` is allowed to read this job's metadata + artifacts.

    stdio transport is implicitly single-user, so it sees everything. For HTTP
    clients we require an exact match against the recorded owner. Legacy jobs
    with no recorded owner (created before owner tracking landed, or by a
    shutdown-recovery path) are treated as non-readable to fail closed.
    """
    if client_id == "stdio":
        return True
    return job.owner_client_id is not None and job.owner_client_id == client_id


async def _handle_check_jobs(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle check_jobs tool.

    When a job is completed, returns artifact content inline so the agent
    client does not need filesystem access to read the output files. Access
    is gated by owner_client_id so one HTTP client cannot read another's
    completed report.

    Requirements: 7.1-7.6
    """
    import json

    job_id = arguments.get("job_id")

    jobs = []

    if job_id:
        # Check specific job
        job = mcp_server.job_store.get(job_id)
        # Return 404 whether the job is missing OR owned by someone else, so
        # the caller cannot probe for the existence of another client's jobs.
        if not job or not _caller_owns_job(job, client_id):
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": True,
                            "error_type": "job_not_found",
                            "error_code": MCPErrorCode.JOB_NOT_FOUND,
                            "message": f"Job not found: {job_id}",
                        }
                    ),
                )
            ]
        jobs.append(_build_job_response(job))
    else:
        # Return active + latest terminal — but only if owned by this client.
        active = mcp_server.job_store.get_active()
        if active and _caller_owns_job(active, client_id):
            jobs.append(_build_job_response(active))

        terminal = mcp_server.job_store.get_latest_terminal()
        if (
            terminal
            and _caller_owns_job(terminal, client_id)
            and (not active or terminal.job_id != active.job_id)
        ):
            jobs.append(_build_job_response(terminal))

    return [
        TextContent(
            type="text",
            text=json.dumps({"jobs": jobs}),
        )
    ]


def _build_job_response(job: "ResearchJobState") -> dict[str, Any]:
    """
    Build a job response dict.

    For completed jobs, includes full artifact content inline so agent
    clients can consume the output without filesystem access.
    """
    from pathlib import Path

    status = job.get_status().value
    response: dict[str, Any] = {
        "job_id": job.job_id,
        "status": status,
        "company_name": job.company_name,
        "output_path": job.output_paths[0] if job.output_paths else None,
        "error_type": job.error_type,
        "error_message": job.error_message,
    }

    # For completed jobs, include artifact content inline
    if status == "completed" and job.output_paths:
        artifacts = []
        for artifact_path in job.output_paths:
            p = Path(artifact_path)
            if not p.exists():
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:
                continue

            # Classify artifact type from filename
            name_lower = p.stem.lower()
            if "ai_strategy" in name_lower or "ai-strategy" in name_lower:
                artifact_type = "ai_strategy"
            elif "customer_experience" in name_lower:
                artifact_type = "customer_experience_strategy"
            elif "security" in name_lower:
                artifact_type = "security_strategy"
            elif "data_fabric" in name_lower:
                artifact_type = "data_fabric_strategy"
            elif "strategic_overview" in name_lower or "report" in name_lower:
                artifact_type = "strategic_overview"
            else:
                artifact_type = "report"

            artifacts.append(
                {
                    "type": artifact_type,
                    "filename": p.name,
                    "content": content,
                }
            )

        response["artifacts"] = artifacts

    return response


async def _handle_run_qa(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle run_qa tool.

    Requirements: 8.1-8.6
    """
    import json

    report_path = arguments.get("report_path")

    # Validate path
    path_result = mcp_server.path_validator.validate(report_path)
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
        from primr.mcp_server.pipeline_runner import run_qa_analysis

        result = await run_qa_analysis(str(path_result.resolved_path))

        return [
            TextContent(
                type="text",
                text=json.dumps(result),
            )
        ]

    except Exception:
        # Same rationale as the strategy-generation handler — keep the
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


async def _handle_doctor(
    _mcp_server: "PrimrMCPServer",
    _arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle doctor tool.

    In local mode: returns existing system health status.
    In cloud mode: adds Azure service diagnostics (Container App health,
    Cosmos DB, Blob Storage, Service Bus, App Insights, Cost Governor).

    Requirements: 18.4, 18.5, 10.7
    """
    import json

    from primr.mcp_server.cloud_detect import is_cloud_mode
    from primr.mcp_server.pipeline_runner import get_doctor_status

    result = get_doctor_status()

    if is_cloud_mode():
        result["cloud_mode"] = True
        result["cloud_diagnostics"] = await _get_cloud_diagnostics()
    else:
        result["cloud_mode"] = False

    return [
        TextContent(
            type="text",
            text=json.dumps(result),
        )
    ]


async def _get_cloud_diagnostics() -> dict[str, Any]:
    """
    Gather cloud-specific diagnostics for the doctor tool.

    Checks: Container App health, Cosmos DB, Blob Storage,
    Service Bus (if configured), Application Insights (if configured),
    and Cost Governor limits.

    Requirements: 10.7
    """
    import os

    diagnostics: dict[str, Any] = {}

    # 1. Container App health (call /healthz)
    control_plane_url = os.environ.get("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{control_plane_url}/healthz")
            diagnostics["container_app_health"] = {
                "status": "ok" if resp.status_code == 200 else "error",
                "http_status": resp.status_code,
                "detail": resp.json(),
            }
    except Exception:
        logger.exception("Cloud diagnostics: Container App health check failed")
        diagnostics["container_app_health"] = {
            "status": "error",
            "detail": "connectivity check failed",
        }

    # 2. Cosmos DB connectivity and RU consumption
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
    if cosmos_endpoint:
        try:
            diagnostics["cosmos_db"] = {
                "status": "ok",
                "endpoint": cosmos_endpoint,
            }
        except Exception:
            logger.exception("Cloud diagnostics: Cosmos DB check failed")
            diagnostics["cosmos_db"] = {
                "status": "error",
                "detail": "connectivity check failed",
            }
    else:
        diagnostics["cosmos_db"] = {"status": "not_configured"}

    # 3. Blob Storage connectivity
    storage_account = os.environ.get("STORAGE_ACCOUNT_NAME")
    if storage_account:
        try:
            diagnostics["blob_storage"] = {
                "status": "ok",
                "account": storage_account,
            }
        except Exception:
            logger.exception("Cloud diagnostics: Blob Storage check failed")
            diagnostics["blob_storage"] = {
                "status": "error",
                "detail": "connectivity check failed",
            }
    else:
        diagnostics["blob_storage"] = {"status": "not_configured"}

    # 4. Service Bus queue depth (if configured)
    servicebus_conn = os.environ.get("SERVICEBUS_CONNECTION_STRING")
    if servicebus_conn:
        try:
            diagnostics["service_bus"] = {
                "status": "ok",
                "configured": True,
            }
        except Exception:
            logger.exception("Cloud diagnostics: Service Bus check failed")
            diagnostics["service_bus"] = {
                "status": "error",
                "detail": "connectivity check failed",
            }
    else:
        diagnostics["service_bus"] = {"status": "not_configured"}

    # 5. Application Insights availability (if configured)
    appinsights_conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if appinsights_conn:
        diagnostics["application_insights"] = {
            "status": "ok",
            "configured": True,
        }
    else:
        diagnostics["application_insights"] = {"status": "not_configured"}

    # 6. Cost Governor limits with current usage
    try:
        max_job_cost = float(os.environ.get("PRIMR_MAX_JOB_COST_USD", "1.0"))
        max_daily_cost = float(os.environ.get("PRIMR_MAX_DAILY_COST_USD", "10.0"))
        max_monthly_cost = float(os.environ.get("PRIMR_MAX_MONTHLY_COST_USD", "100.0"))
        diagnostics["cost_governor"] = {
            "status": "ok",
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
            "detail": "configuration check failed",
        }

    return diagnostics


async def _handle_clear_jobs(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle clear_jobs tool.

    Owner-gated: HTTP clients can only clear jobs they own. Without this
    check, any authenticated HTTP caller could wipe another tenant's
    terminal job from the store (denial-of-service against the legitimate
    owner's job history). stdio retains full access.

    Requirements: 18.6, 18.7
    """
    import json

    older_than_hours = arguments.get("older_than_hours", 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

    cleared_count = 0

    # In single-job model, just check if the job is old and terminal
    job = mcp_server.job_store.get_latest_terminal()
    if (
        job
        and job.completion_time
        and job.completion_time < cutoff
        and _caller_owns_job(job, client_id)
    ):
        mcp_server.job_store.clear()
        cleared_count = 1

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": True,
                    "cleared_count": cleared_count,
                }
            ),
        )
    ]


async def _handle_cancel_job(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle cancel_job tool.

    Requirements: 18.8-18.11
    """
    import json

    job_id = arguments.get("job_id")

    # Get the job
    job = mcp_server.job_store.get(job_id)
    if not job:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_not_found",
                        "error_code": MCPErrorCode.JOB_NOT_FOUND,
                        "message": f"Job not found: {job_id}",
                    }
                ),
            )
        ]

    # Check if already terminal
    if job.is_terminal():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_already_terminal",
                        "message": f"Job {job_id} is already {job.get_status().value}",
                    }
                ),
            )
        ]

    # Check authorization (in HTTP mode, only owner can cancel).
    # In stdio mode, always allowed (implicit single-user).
    # Fail closed for legacy jobs with no recorded owner: an HTTP client
    # could otherwise cancel any pre-owner-tracking job by id, which is
    # the same authorization shape we already deny in
    # resource_auth.caller_owns_job_resource and tools._caller_owns_job.
    is_owner = job.owner_client_id is not None and job.owner_client_id == client_id
    if client_id != "stdio" and not is_owner:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "cancel_not_authorized",
                        "error_code": MCPErrorCode.CANCEL_NOT_AUTHORIZED,
                        "message": "Only the job owner or admin can cancel this job",
                    }
                ),
            )
        ]

    # Cancel the job
    job.advance_stage(ResearchStage.CANCELLED)
    job.error_type = "user_cancelled"
    job.error_message = f"Cancelled by {client_id}"
    mcp_server.job_store.update(job)

    logger.info("Job %s cancelled by %s", job_id, client_id)

    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "success": True,
                    "job_id": job_id,
                    "status": "cancelled",
                    "message": "Job cancelled. Any partial artifacts have been preserved.",
                }
            ),
        )
    ]


async def _handle_wait_for_status_change(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
    client_id: str,
) -> list[TextContent]:
    """
    Handle wait_for_status_change tool.

    Blocks until job status changes or timeout occurs. Ownership-gated like
    check_jobs: cross-client subscriptions to another user's job (which
    leaked progress, output_path, and error_message) return 404.
    """
    import json

    job_id = arguments.get("job_id")
    timeout_seconds = min(arguments.get("timeout_seconds", 60), 300)  # Cap at 5 minutes

    # Get current job state. Return 404 whether the job is missing OR owned
    # by someone else, so an attacker can't probe for live job IDs.
    job = mcp_server.job_store.get(job_id)
    if not job or not _caller_owns_job(job, client_id):
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_not_found",
                        "error_code": MCPErrorCode.JOB_NOT_FOUND,
                        "message": f"Job not found: {job_id}",
                    }
                ),
            )
        ]

    current_status = job.get_status()

    # If already terminal, return immediately
    if job.is_terminal():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "job_id": job_id,
                        "status": current_status.value,
                        "changed": False,
                        "message": "Job is already in terminal state",
                        "output_path": job.output_paths[0] if job.output_paths else None,
                    }
                ),
            )
        ]

    # Wait for status change
    changed, new_status = await mcp_server.job_store.wait_for_status_change(
        job_id=job_id,
        current_status=current_status,
        timeout_seconds=timeout_seconds,
    )

    # Get updated job info
    job = mcp_server.job_store.get(job_id)
    if job is None:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "job_not_found",
                        "message": "Job disappeared while waiting",
                    }
                ),
            )
        ]

    result = {
        "job_id": job_id,
        "status": job.get_status().value,
        "previous_status": current_status.value,
        "changed": changed,
        "current_stage": job.current_stage.value,
        "stage_progress_percent": job.stage_progress_percent,
    }

    if job.is_terminal():
        result["output_path"] = job.output_paths[0] if job.output_paths else None
        if job.error_message:
            result["error_message"] = job.error_message

    if not changed:
        result["message"] = f"Timeout after {timeout_seconds}s, status unchanged"

    return [
        TextContent(
            type="text",
            text=json.dumps(result),
        )
    ]


async def _handle_show_usage(
    mcp_server: "PrimrMCPServer",
    client_id: str,
) -> list[TextContent]:
    """
    Handle show_usage tool.

    In local mode (no cloud env vars), returns a message that budget tracking
    is only available in cloud deployment.
    In cloud mode, queries the Control Plane API's /usage/{api_key_hash} endpoint.

    Requirements: 6.8
    """
    import hashlib
    import json
    import os

    from primr.mcp_server.cloud_detect import is_cloud_mode

    if not is_cloud_mode():
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "message": "Budget tracking available in cloud deployment. Local usage is not tracked.",
                    }
                ),
            )
        ]

    # Cloud mode: query the Control Plane API
    control_plane_url = os.environ.get("PRIMR_CONTROL_PLANE_URL", "http://localhost:8000")
    api_key_hash = f"sha256:{hashlib.sha256(client_id.encode()).hexdigest()}"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            resp = await http_client.get(f"{control_plane_url}/usage/{api_key_hash}")
            resp.raise_for_status()
            usage_data = resp.json()

        return [
            TextContent(
                type="text",
                text=json.dumps(usage_data),
            )
        ]
    except Exception:
        logger.exception("Failed to fetch usage data")
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "usage_fetch_failed",
                        "message": "Failed to fetch usage data. Please try again later.",
                    }
                ),
            )
        ]


async def _handle_delegate_to_agent(
    mcp_server: "PrimrMCPServer",
    arguments: dict[str, Any],
) -> list[TextContent]:
    """
    Handle delegate_to_agent tool — call an external A2A agent.

    Guarded by ImportError: only available when primr[a2a] is installed.
    """
    import json

    try:
        from primr.a2a.client import A2AClient
    except ImportError:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "missing_dependency",
                        "message": "A2A support not installed. Run: pip install primr[a2a]",
                    }
                ),
            )
        ]

    agent_url = arguments.get("agent_url", "")
    message = arguments.get("message", "")
    skill_id = arguments.get("skill_id")

    # Validate URL via SSRF protection
    url_result = mcp_server.url_validator.validate(agent_url)
    if not url_result.valid:
        error_code = {
            "invalid_url": MCPErrorCode.INVALID_URL,
            "ssrf_blocked": MCPErrorCode.SSRF_BLOCKED,
            "url_unreachable": MCPErrorCode.URL_UNREACHABLE,
        }.get(url_result.error_type, MCPErrorCode.INVALID_URL)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": url_result.error_type,
                        "error_code": error_code,
                        "message": f"Agent URL blocked: {url_result.error_message}",
                    }
                ),
            )
        ]

    try:
        async with A2AClient(agent_url=agent_url) as client:
            result = await client.send_message(message=message, skill_id=skill_id)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception:
        logger.exception("A2A delegation failed: %s", agent_url)
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": True,
                        "error_type": "a2a_delegation_failed",
                        "message": "A2A delegation failed. Check server logs for details.",
                    }
                ),
            )
        ]
