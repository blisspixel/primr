"""
Prompt template definitions for MCP server.

This module provides workflow guidance prompts:
- research_workflow - Guide through company research process
- strategy_selection - Help choose appropriate strategy type
- governed_execution - Default contract for cost-aware MCP clients

Requirements: 9.1-9.5, 10.1-10.4
"""

from mcp.server import Server
from mcp.types import GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent


def register_prompts(server: Server) -> None:
    """Register all Primr prompt templates with the MCP server."""

    @server.list_prompts()
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

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
        """Get a prompt by name.

        Wrapped in GetPromptResult so the MCP SDK's pydantic validator
        accepts the response in strict mode. Earlier MCP SDK versions
        accepted a bare ``list[PromptMessage]``; the current SDK validates
        the response shape and rejects the list form.
        """
        if name == "research_workflow":
            messages = _get_research_workflow_prompt(arguments or {})
        elif name == "strategy_selection":
            messages = _get_strategy_selection_prompt(arguments or {})
        elif name == "governed_execution":
            messages = _get_governed_execution_prompt()
        else:
            raise ValueError(f"Unknown prompt: {name}")
        return GetPromptResult(messages=messages)


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

## Step 2: Estimate Costs (Recommended)
Before starting research, call `estimate_run` to get mode-specific cost and time estimates. Do not call `research_company` until the user approves that spend:
```
estimate_run(company_url="https://example.com", mode="full")
```

## Step 3: Execute Research
1. Check current status: Read `primr://research/status`
2. If idle, call `research_company` with appropriate parameters:
```
research_company(
    company_name="{company_name}",
    company_url="https://example.com",
    mode="full",
    platform="azure"  # Optional: for AI strategy
)
```
3. For long-running jobs, prefer `wait_for_status_change` or poll `primr://research/status`
4. Expect standard runs to take roughly 35-45 minutes, and premium multi-vendor runs to take up to 75-120 minutes
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
- Add `platform` parameter when AI strategy is needed

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
**Use when:** Client needs AI/ML transformation roadmap
**Focus:** Agentic AI, organizational design, investment frameworks
**Best for:** Technology companies, digital transformation initiatives
**Requires:** `platform` parameter (azure, aws, or gcp)

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
- **azure**: Microsoft ecosystem, enterprise integration, Copilot focus
- **aws**: Broad service portfolio, startup-friendly, Bedrock/SageMaker
- **gcp**: AI/ML focus, data analytics strength, Vertex AI

## Selection Criteria
1. Review the research report for company focus areas
2. Identify primary business challenges mentioned
3. Match challenges to strategy type capabilities
4. Consider industry vertical and regulatory requirements

## Example Usage
```
estimate_strategy(
    strategy_type="ai_strategy",
    platform="azure"
)

generate_strategy(
    report_path="output/acme_corp/report.md",
    strategy_type="ai_strategy",
    platform="azure"
)
```

## Tips
- Read the research report first to understand the company
- Multiple strategies can be generated from the same report
- AI strategy requires platform; others don't
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
1. Call `estimate_run` first — this includes AI strategy cost when platform is specified.
2. Tell the user the total cost (research + strategy combined) and get ONE explicit approval.
3. Pass `max_estimated_cost_usd` into `research_company`.
4. Do NOT call `estimate_strategy` or `generate_strategy` separately — strategy is included in the research job when `platform` is set.
5. Treat research as a long-running async job; poll `check_jobs` for completion.
6. When `check_jobs` returns status "completed", the response includes full artifact content (report + strategy MD files) inline — no filesystem access needed.

## Standard flow (research + strategy in one approval)
```text
estimate_run(company_url="https://example.com", mode="full", platforms=["azure"])
# → shows combined cost for research + AI strategy
# → user approves once

research_company(company_name="ExampleCo", company_url="https://example.com", mode="full", platform="azure", max_estimated_cost_usd=0.67)
# → returns job_id immediately

check_jobs(job_id="...")
# → when completed, response includes artifacts[].content with full MD files
```

## Optional: destination directory
```text
research_company(company_name="ExampleCo", company_url="https://example.com", platform="azure", destination="/path/to/output")
# → artifacts are also copied to the specified directory
```

## Adding a strategy to an existing report (rare — only when strategy was not part of the original run)
```text
estimate_strategy(strategy_type="customer_experience")
generate_strategy(report_path="output/report.md", strategy_type="customer_experience", max_estimated_cost_usd=0.25)
```
"""

    return [
        PromptMessage(
            role="user",
            content=TextContent(type="text", text=content),
        )
    ]
