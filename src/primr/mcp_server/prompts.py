"""
Prompt template definitions for MCP server.

This module provides workflow guidance prompts:
- research_workflow - Guide through company research process
- strategy_selection - Help choose appropriate strategy type

Requirements: 9.1-9.5, 10.1-10.4
"""

from mcp.server import Server
from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent


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
        ]
    
    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None = None) -> list[PromptMessage]:
        """Get a prompt by name."""
        if name == "research_workflow":
            return _get_research_workflow_prompt(arguments or {})
        elif name == "strategy_selection":
            return _get_strategy_selection_prompt(arguments or {})
        
        raise ValueError(f"Unknown prompt: {name}")


def _get_research_workflow_prompt(arguments: dict) -> list[PromptMessage]:
    """
    Get research workflow prompt.
    
    Requirements: 9.1-9.5
    """
    company_name = arguments.get("company_name", "the target company")
    
    content = f"""# Company Research Workflow

## Step 1: Gather Requirements
- Identify the target company name and website URL
- For {company_name}, determine research depth needed:
  - **scrape**: Quick overview from website content (5-10 min, ~$0.05)
  - **deep**: External source validation without site scraping (8-15 min, ~$0.50)
  - **full**: Complete pipeline with all sources (25-40 min, ~$0.75)

## Step 2: Estimate Costs (Recommended)
Before starting research, call `estimate_run` to get cost and time estimates:
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
    cloud_vendor="azure"  # Optional: for AI strategy
)
```
3. Monitor progress through status resource updates

## Step 4: Evaluate Results
1. Read `primr://output/latest` to review the report
2. Check the QA score:
   - 85+: High quality, ready for use
   - 70-84: Acceptable, may need review
   - <70: Consider re-running or manual review

## Step 5: Generate Additional Deliverables
If strategy documents are needed:
1. Use `generate_strategy` with the report path
2. Select appropriate strategy type based on use case

## Decision Points
- Use **scrape** mode for initial reconnaissance
- Use **deep** mode when website is heavily protected or inaccessible
- Use **full** mode for comprehensive analysis
- Add `cloud_vendor` parameter when AI strategy is needed

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
**Requires:** `cloud_vendor` parameter (azure, aws, or gcp)

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

## Cloud Vendor Selection (for ai_strategy)
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
generate_strategy(
    report_path="output/acme_corp/report.md",
    strategy_type="ai_strategy",
    cloud_vendor="azure"
)
```

## Tips
- Read the research report first to understand the company
- Multiple strategies can be generated from the same report
- AI strategy requires cloud_vendor; others don't
- Check QA score after generation to ensure quality
"""
    
    return [
        PromptMessage(
            role="user",
            content=TextContent(type="text", text=content),
        )
    ]
