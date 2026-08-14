"""
Prompt template definitions for MCP server.

This module provides workflow guidance prompts:
- research_workflow - Guide through company research process
- strategy_selection - Help choose appropriate strategy type
- governed_execution - Default contract for cost-aware MCP clients

Requirements: 9.1-9.5, 10.1-10.4
"""

from mcp.server import Server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    GetPromptRequestParams,
    GetPromptResult,
    ListPromptsResult,
    PaginatedRequestParams,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
)


def register_prompts(server: Server) -> None:
    """Register all Primr prompt templates with the MCP server."""

    async def list_prompts() -> list[Prompt]:
        """List available prompts."""
        return [
            Prompt(
                name="research_workflow",
                description="Guide through company research process",
                arguments=[
                    PromptArgument(
                        name="company_name",
                        description="Name of the company to research (optional)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="strategy_selection",
                description="Help choose appropriate strategy document type",
                arguments=[
                    PromptArgument(
                        name="context",
                        description="Context about the client or use case (optional)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="governed_execution",
                description="Default estimate, approval, and cost-cap contract for generic MCP clients",
                arguments=[],
            ),
        ]

    async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
        """Get a prompt by name."""
        if name == "research_workflow":
            messages = _get_research_workflow_prompt(arguments or {})
        elif name == "strategy_selection":
            messages = _get_strategy_selection_prompt(arguments or {})
        elif name == "governed_execution":
            messages = _get_governed_execution_prompt()
        else:
            raise MCPError(INVALID_PARAMS, f"Unknown prompt: {name}")
        return GetPromptResult(messages=messages)

    async def _on_list_prompts(
        _ctx: object, _params: PaginatedRequestParams | None
    ) -> ListPromptsResult:
        return ListPromptsResult(prompts=await list_prompts())

    async def _on_get_prompt(_ctx: object, params: GetPromptRequestParams) -> GetPromptResult:
        return await get_prompt(params.name, params.arguments)

    server.add_request_handler("prompts/list", PaginatedRequestParams, _on_list_prompts)
    server.add_request_handler("prompts/get", GetPromptRequestParams, _on_get_prompt)


def _get_research_workflow_prompt(arguments: dict) -> list[PromptMessage]:
    """
    Get research workflow prompt.

    Requirements: 9.1-9.5
    """
    company_name = arguments.get("company_name", "the target company")

    content = f"""# Company Research Workflow

## Step 1: Gather Requirements
- Identify the target company name and website URL
- Read `primr://research/modes` to confirm current mode guidance and defaults
- For {company_name}, choose the lightest mode that still answers the user's question

## Step 2: Estimate Costs (Required)
Before starting research, call `estimate_run` to get mode-specific cost and time estimates. Do not call `research_company` until the user approves that spend:
```
estimate = estimate_run(company_url="https://example.com", mode="full")
# Surface the exact estimate and get explicit user approval.
```

## Step 3: Execute Research
1. Check current status: Read `primr://research/status`
2. If idle, call `research_company` with appropriate parameters:
```
research_company(
    company_name="{company_name}",
    company_url="https://example.com",
    mode="full",
    max_estimated_cost_usd=estimate["estimated_cost_usd"],
    approval_token=estimate["approval_token"]
)
```
Full and premium runs include one vendor-neutral AI Strategy by default. Set
`platform` only when the user wants a specific ecosystem evaluated as an
emphasis. Use `no_ai_strategy=true` only when the approved scope is report-only.
3. For long-running jobs, prefer `wait_for_status_change` or poll `primr://research/status`
4. Expect standard runs to take roughly 34-53 minutes, and premium multi-vendor runs to take up to 75-120 minutes
5. Design the client to resume from job state rather than holding a synchronous request open for the full run

## Step 4: Evaluate Results
1. Read `primr://output/latest` to review the report
2. Check the QA score:
   - 85+: High quality, ready for use
   - 70-84: Acceptable, may need review
   - <70: Consider re-running or manual review

## Step 5: Generate Additional Deliverables
If strategy documents are needed:
1. Read `primr://strategies/available` to pick a strategy
2. Call `estimate_strategy` and surface the cost/time to the user
3. Get explicit approval before calling `generate_strategy`
4. Use `generate_strategy` with the report path

## Decision Points
- Use **scrape** mode for initial reconnaissance
- Use **deep** mode when website is heavily protected or inaccessible
- Use **full** mode for the standard end-to-end workflow
- Use **premium** when the user explicitly wants maximum-depth research
- Omit `platform` for one integrated vendor-neutral AI Strategy
- Set `platform` only for a user-requested ecosystem emphasis

## Error Handling
- **url_unreachable**: Try `mode=deep` which doesn't require site access
- **job_in_progress**: Wait for completion or call `cancel_job`
- **rate_limit_exceeded**: Wait for `retry_after_seconds` then retry
"""

    return [
        PromptMessage(
            role="user",
            content=TextContent(type="text", text=content),
        )
    ]


def _get_strategy_selection_prompt(arguments: dict) -> list[PromptMessage]:
    """
    Get strategy selection prompt.

    Requirements: 10.1-10.4
    """
    context = arguments.get("context", "")
    context_note = f"\n\nContext provided: {context}" if context else ""

    content = f"""# Strategy Document Selection Guide{context_note}

## Available Strategy Types

### ai_strategy
**Use when:** Leaders need business-first decisions about growth, efficiency,
service or product improvement, risk, and where AI can create defensible value
**Focus:** Economic engine, industry art of the possible, prioritized value
portfolio, unit economics, operating model, governance, and workload placement
**Best for:** CEO, CIO, and board decisions across industries
**Standalone requirement:** Pass `platform`; choose `agnostic` unless the user
asked for a specific ecosystem emphasis

### customer_experience
**Use when:** Client needs CX improvement plan
**Focus:** Journey mapping, experience design, touchpoint optimization
**Best for:** B2C companies, service organizations

### modern_security_compliance
**Use when:** Client needs security posture assessment
**Focus:** Guardrails-first governance, risk frameworks, compliance
**Best for:** Regulated industries, enterprise clients

### data_fabric_strategy
**Use when:** Client needs data platform modernization
**Focus:** Semantic layers, intelligent data estates, AI-ready infrastructure
**Best for:** Data-intensive organizations, analytics modernization

## Platform Selection (for ai_strategy)
- **agnostic**: Default integrated evaluation across the complete observed stack
- **azure**, **aws**, or **gcp**: Emphasize that public-cloud ecosystem while
  still evaluating credible alternatives
- **private**: Emphasize private, on-premises, edge, or accelerated infrastructure
  when workload economics, sovereignty, latency, or scale justify it

A platform is an evaluation emphasis, not a predetermined recommendation. The
strategy must start from business outcomes and consider hybrid placement when
the evidence and workload support it.

## Selection Criteria
1. Review the research report for company focus areas
2. Identify primary business challenges mentioned
3. Match challenges to strategy type capabilities
4. Consider industry vertical and regulatory requirements

## Example Usage
```
estimate = estimate_strategy(
    strategy_type="ai_strategy",
    platform="agnostic"
)

generate_strategy(
    report_path="output/acme_corp/report.md",
    strategy_type="ai_strategy",
    platform="agnostic",
    max_estimated_cost_usd=estimate["estimated_cost_usd"],
    approval_token=estimate["approval_token"]
)
```

Assign the `estimate_strategy` result to `estimate`, surface its exact cost,
and get explicit user approval before calling `generate_strategy`.

## Tips
- Read the research report first to understand the company
- Multiple strategies can be generated from the same report
- Full and premium research already include one agnostic AI Strategy by default
- Standalone AI strategy estimates require an explicit platform; use `agnostic`
  unless the user asks for an ecosystem emphasis
- Check QA score after generation to ensure quality
"""

    return [
        PromptMessage(
            role="user",
            content=TextContent(type="text", text=content),
        )
    ]


def _get_governed_execution_prompt() -> list[PromptMessage]:
    """Get governed execution guidance for generic MCP clients."""
    content = """# Governed Execution Contract

Use this contract whenever a Primr MCP client may trigger paid work.

## Required pattern
1. Call `estimate_run` first. Full and premium estimates include one agnostic AI Strategy by default.
2. Tell the user the total cost (research + strategy combined) and get ONE explicit approval.
3. Pass `max_estimated_cost_usd` and the returned `approval_token` into `research_company`; server-side MCP cost enforcement is on by default for every transport.
4. Do NOT call `estimate_strategy` or `generate_strategy` separately for a new full or premium run. Its AI Strategy is included unless `no_ai_strategy=true`.
5. Treat research as a long-running async job; poll `check_jobs` for completion.
6. On completion, local stdio clients receive inline artifact content by default. Authenticated HTTP clients receive metadata and owned-job resource pointers; read those resources for report bodies.

## Standard flow (research + strategy in one approval)
```text
estimate = estimate_run(company_url="https://example.com", mode="full")
# shows combined cost for research plus one agnostic AI Strategy
# user approves once

research_company(company_name="ExampleCo", company_url="https://example.com", mode="full", max_estimated_cost_usd=estimate["estimated_cost_usd"], approval_token=estimate["approval_token"])
# returns job_id immediately

check_jobs(job_id="...")
# local stdio includes artifact content by default
# HTTP returns metadata and owned-job resource pointers
```

## Optional: destination directory
```text
research_company(company_name="ExampleCo", company_url="https://example.com", mode="full", destination="client-deliverables", max_estimated_cost_usd=estimate["estimated_cost_usd"], approval_token=estimate["approval_token"])
# artifacts are also copied to the specified directory
```

## Adding a strategy to an existing report
```text
estimate = estimate_strategy(strategy_type="customer_experience")
generate_strategy(report_path="output/report.md", strategy_type="customer_experience", max_estimated_cost_usd=estimate["estimated_cost_usd"], approval_token=estimate["approval_token"])
```
"""

    return [
        PromptMessage(
            role="user",
            content=TextContent(type="text", text=content),
        )
    ]
