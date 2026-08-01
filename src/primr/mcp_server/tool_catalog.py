"""Base MCP tool catalog for the Primr server.

Split from tools.py to keep the dispatcher under its pinned line ceiling.
Schema-only definitions live here; dispatch and policy stay in tools.py.
"""

from mcp.types import Tool

from primr.mcp_server.approval_tokens import APPROVAL_TOKEN_SCHEMA


def build_base_tools() -> list[Tool]:
    """Return the base tool list, including the optional A2A delegate tool."""
    base_tools = [
        Tool(
            name="estimate_run",
            description="Estimate cost and time for a research run without executing. Call this before any cost-incurring research run.",
            input_schema={
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
                        "minItems": 1,
                        "maxItems": 1,
                        "uniqueItems": True,
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
                            ],
                        },
                        "description": "Exactly one platform for the integrated AI strategy (CLI: --platform). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private. Default: agnostic. Add other platform documents later with estimate_strategy and generate_strategy.",
                    },
                    "strategy_type": {
                        "type": "string",
                        "enum": ["ai"],
                        "default": "ai",
                        "description": "Integrated research strategy type. Other modules use estimate_strategy and generate_strategy after the report completes.",
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
            input_schema={
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
            description="Initiate the supervised company research pipeline and return a job_id after the worker is ready. Full and premium include an agnostic AI Strategy by default unless no_ai_strategy is true. This incurs real API cost and should only be called after the user approves an estimate from estimate_run.",
            input_schema={
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
                        ],
                        "description": "Platform for AI strategy (CLI: --platform). Aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private. When set, strategy is generated as part of this job (no separate generate_strategy call needed). Default: agnostic.",
                    },
                    "no_ai_strategy": {
                        "type": "boolean",
                        "default": False,
                        "description": "Skip AI strategy generation entirely (report only)",
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
                    "max_estimated_cost_usd": {
                        "anyOf": [
                            {"type": "number", "minimum": 0},
                            {"type": "string"},
                        ],
                        "description": "Optional hard ceiling for estimated run cost. The server rejects execution if the estimate exceeds this cap and uses it as the runtime budget.",
                    },
                    "approval_token": APPROVAL_TOKEN_SCHEMA,
                },
                "required": ["company_name", "company_url"],
            },
        ),
        Tool(
            name="generate_strategy",
            description="Generate strategy document from an existing report AFTER the fact. Only needed when adding a strategy to a previously completed research run. For new research, use research_company with platform instead; strategy is included automatically.",
            input_schema={
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
            description=(
                "Check research job status. Completed jobs return output pointers by default; "
                "inline report artifacts require include_artifacts=true and report scope for "
                "authenticated HTTP callers. Local stdio keeps legacy inline artifact behavior."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Specific job ID to check (optional)",
                    },
                    "include_artifacts": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "Include inline report and strategy artifacts. Requires report scope "
                            "for authenticated HTTP callers; defaults to true only for local stdio "
                            "compatibility."
                        ),
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="run_qa",
            description="Run quality assessment on a report. This may incur real API cost depending on the configured QA path.",
            input_schema={
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
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="clear_jobs",
            description="Clear stale pending jobs",
            input_schema={
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
            description="Cancel an active local research job. A cancelled response is returned only after the supervised worker exits; remote provider work may remain unknown when the provider has no cancellation API.",
            input_schema={
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
            input_schema={
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
            input_schema={
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
                input_schema={
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

    return base_tools
