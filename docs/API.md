# Primr API Reference

This document describes how to use Primr programmatically as a Python library.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
import asyncio
from primr.core.research_orchestrator import ResearchOrchestrator, ResearchMode

async def main():
    orchestrator = ResearchOrchestrator()
    result = await orchestrator.research(
        "Tesla",
        "https://tesla.com",
        mode=ResearchMode.COMPLETE
    )
    
    if result.success:
        print(f"Generated {len(result.section_results)} sections")
        print(f"Duration: {result.duration_seconds:.0f}s")
    else:
        print(f"Error: {result.error}")

asyncio.run(main())
```

## Core Classes

### ResearchOrchestrator

The main entry point for running research.

```python
from primr.core.research_orchestrator import (
    ResearchOrchestrator,
    ResearchMode,
    ResearchConfig,
    OrchestratorResult
)
```

#### Constructor

```python
orchestrator = ResearchOrchestrator()
```

No arguments required. The orchestrator lazy-loads clients as needed.

#### research()

Execute company research using the specified mode.

```python
async def research(
    company_name: str,
    website: str | None = None,
    mode: ResearchMode = ResearchMode.STRUCTURED,
    config: ResearchConfig | None = None,
    on_progress: Callable[[str], None] | None = None,
    context_files: list[str] | None = None,
) -> OrchestratorResult
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `company_name` | str | Name of the company to research |
| `website` | str or None | Company website URL |
| `mode` | ResearchMode | Research mode (STRUCTURED, DEEP_RESEARCH, COMPLETE) |
| `config` | ResearchConfig or None | Optional configuration overrides |
| `on_progress` | Callable or None | Progress callback function |
| `context_files` | list or None | Additional context files (PDFs, docs) |

**Returns:** `OrchestratorResult`

**Example with progress callback:**

```python
def on_progress(message: str):
    print(f"Progress: {message}")

result = await orchestrator.research(
    "Tesla",
    "https://tesla.com",
    mode=ResearchMode.COMPLETE,
    on_progress=on_progress
)
```

### ResearchMode

Available research modes.

```python
from primr.core.research_orchestrator import ResearchMode

ResearchMode.STRUCTURED      # Website scraping + Google search
ResearchMode.DEEP_RESEARCH   # Autonomous web research
ResearchMode.COMPLETE        # Two-step: structured then deep
```

### ResearchConfig

Configuration for a research task.

```python
from primr.core.research_orchestrator import ResearchConfig

config = ResearchConfig(
    mode=ResearchMode.COMPLETE,
    timeout=3600,              # Max duration in seconds
    poll_interval=10,          # Seconds between status checks
    include_website_scrape=True,
    include_web_search=True,
    sections=None              # Specific sections to research (or None for all)
)
```

### OrchestratorResult

Result from the research orchestrator.

```python
@dataclass
class OrchestratorResult:
    company_name: str
    website: str | None
    mode: ResearchMode
    section_results: dict[str, str]  # Section key -> content
    raw_content: str
    citations: list
    duration_seconds: float
    success: bool
    error: str | None
    timestamp: datetime
```

**Accessing results:**

```python
result = await orchestrator.research("Tesla", "https://tesla.com")

if result.success:
    # Access individual sections
    overview = result.section_results.get("company_overview", "")
    products = result.section_results.get("detailed_products_services", "")
    
    # Get all section keys
    print(result.section_results.keys())
    
    # Access raw content (for Complete mode)
    full_report = result.raw_content
    
    # Access citations
    for citation in result.citations:
        print(f"{citation['number']}: {citation['url']}")
```

## Core Modules

The `primr.core` package contains specialized modules for different aspects of research. These can be imported directly for more granular control.

### Workspace Management

Working folder creation and file operations.

```python
from primr.core.workspace import (
    create_working_folder,
    consolidate_working_folder,
    save_section_output,
    validate_context_files,
    WorkspaceConfig,
    ConsolidationResult,
)
```

```python
# Create a working folder for research
folder = create_working_folder("Tesla")
print(f"Working folder: {folder}")

# Save section output
save_section_output(folder, "company_overview", "Tesla is an electric vehicle company...")

# Consolidate all sections into a single file
result = consolidate_working_folder(folder)
print(f"Consolidated {result.section_count} sections")
```

### AI Strategy Generation

Generate AI strategy recommendations with cloud vendor context.

```python
from primr.core.ai_strategy import (
    generate_ai_strategy_sync,
    CloudVendor,
    AIStrategyConfig,
    AIStrategyResult,
)
```

```python
# Generate AI strategy for a company
config = AIStrategyConfig(
    company_name="Tesla",
    cloud_vendor=CloudVendor.AWS,
    working_folder=Path("working/Tesla"),
)

result = generate_ai_strategy_sync(config)
if result.success:
    print(result.content)
```

**CloudVendor enum:**

```python
CloudVendor.AWS      # Amazon Web Services
CloudVendor.AZURE    # Microsoft Azure
CloudVendor.GCP      # Google Cloud Platform
```

### Deep Research Runner

Execute Deep Research with preflight validation.

```python
from primr.core.deep_research_runner import (
    perform_deep_research,
    validate_preflight,
    DeepResearchConfig,
    DeepResearchMode,
    PreflightResult,
    PreflightStatus,
)
```

```python
# Validate before running expensive operations
preflight = validate_preflight()
if preflight.status == PreflightStatus.READY:
    config = DeepResearchConfig(
        company_name="Tesla",
        prompt="Research Tesla's competitive position",
        mode=DeepResearchMode.STANDARD,
    )
    result = await perform_deep_research(config)
else:
    print(f"Preflight failed: {preflight.message}")
```

### CLI Module

Command-line interface components for programmatic use.

```python
from primr.core.cli import (
    main,
    run_doctor,
    parse_args,
    process_csv,
    Command,
    CLIConfig,
)
```

```python
# Run system check programmatically
success = run_doctor()

# Parse CLI arguments
config = parse_args(["Tesla", "https://tesla.com", "--mode", "deep"])
print(f"Company: {config.company_name}")
print(f"Mode: {config.mode}")
```

### Structured Research

Website scraping pipeline with section-by-section analysis.

```python
from primr.core.structured_research import (
    run_research,
    research_section,
    generate_initial_overview,
    ScrapedData,
    AnalysisResult,
    ResearchContext,
)
```

### Vendor Research

Cloud vendor AI capabilities research.

```python
from primr.core.vendor_research import (
    get_or_generate_vendor_research,
    get_or_generate_vendor_research_sync,
    VendorResearchFile,
    VendorResearchResult,
)
```

### Backward Compatibility

For existing code, all functions remain available from `research_agent.py`:

```python
# These imports still work (delegate to new modules internally)
from primr.core.research_agent import (
    main,
    run_doctor,
    create_working_folder,
    consolidate_working_folder,
    run_research,
    research_section,
    CloudVendor,
    DeepResearchConfig,
    DeepResearchMode,
)
```

## AI Client

Direct access to the AI client for custom prompts.

```python
from primr.ai import AIClient, get_client
```

### Using the singleton

```python
client = get_client()
response = client.generate("What is Python?")
```

### Creating a new instance

```python
client = AIClient(api_key="your-api-key")
response = client.generate(
    "Analyze this company",
    model_type="research",
    thinking_level="high"
)
```

### generate()

Generate content with automatic retries.

```python
def generate(
    prompt: str,
    model_type: str = "research",
    temperature: float = 1.0,
    thinking_level: str = "high",
    max_retries: int | None = None,
    timeout: float | None = None,
) -> str
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `prompt` | str | The prompt to send |
| `model_type` | str | "research" or "report" |
| `temperature` | float | Sampling temperature (0.0-2.0) |
| `thinking_level` | str | "low" or "high" |
| `max_retries` | int or None | Override default retry count |
| `timeout` | float or None | Request timeout in seconds |

### generate_fast()

Fast generation with minimal thinking.

```python
response = client.generate_fast("Summarize this text")
```

### Token usage tracking

```python
client = AIClient(track_usage=True)

# Make some calls
client.generate("First prompt")
client.generate("Second prompt")

# Get usage summary
usage = client.get_usage_summary()
print(f"Total tokens: {usage['total_tokens']}")
print(f"Estimated cost: ${usage['total_cost']:.4f}")

# Reset counters
client.reset_usage()
```

## Deep Research Client

Direct access to Gemini's Deep Research Agent.

```python
from primr.ai import DeepResearchClient, ResearchResult, ResearchProgress
```

### Basic usage

```python
client = DeepResearchClient()
result = await client.research(
    "Research Tesla's competitive position in the EV market"
)

print(result.content)
for citation in result.citations:
    print(f"Source: {citation['url']}")
```

### With progress callback

```python
def on_progress(progress: ResearchProgress):
    print(f"Status: {progress.status.value}")
    print(f"Message: {progress.message}")
    if progress.thought:
        print(f"Thinking: {progress.thought}")

result = await client.research(
    "Research Tesla",
    on_progress=on_progress
)
```

### Output formats

```python
# Company profile format
result = await client.research(
    "Research Tesla",
    output_format="company_profile"
)

# Executive summary format
result = await client.research(
    "Research Tesla",
    output_format="executive_summary"
)

# Competitive analysis format
result = await client.research(
    "Research Tesla",
    output_format="competitive_analysis"
)
```

### With priority URLs

```python
result = await client.research(
    "Research Tesla",
    priority_urls=["https://tesla.com", "https://ir.tesla.com"]
)
```

### Job Management

Deep Research jobs run asynchronously. If a connection drops, the job continues on Google's servers.

```python
from primr.ai.deep_research import (
    get_deep_research_client,
    get_pending_jobs,
    save_pending_job,
    remove_pending_job,
)

# Check status of a specific job
client = get_deep_research_client()
result = client.check_job("v1_abc123...")
print(f"Status: {result['status']}")  # in_progress, completed, failed
if result['content']:
    print(f"Content: {result['content'][:500]}...")

# List all pending jobs
jobs = get_pending_jobs()
for job_id, info in jobs.items():
    print(f"{job_id}: {info['description']} ({info['status']})")

# Manually save a job for later recovery
save_pending_job(
    interaction_id="v1_abc123...",
    job_type="ai_strategy",
    description="AI Strategy for Tesla"
)

# Remove a completed job from tracking
remove_pending_job("v1_abc123...")
```

**CLI commands for job management:**
```bash
primr --check-jobs   # Check status of all pending jobs
primr --clear-jobs   # Clear stale/old pending jobs
```

## Scraping

Direct access to the scraping engine.

```python
from primr.data.scrape import (
    scrape_with_requests,
    scrape_with_httpx,
    scrape_with_playwright,
    scrape_with_playwright_aggressive,
    get_cached_content,
    cache_content,
    clear_cache
)
```

### Tiered scraping

```python
url = "https://example.com"

# Try each tier in order
content, error = scrape_with_requests(url)
if content is None:
    content, error = scrape_with_httpx(url)
if content is None:
    content, error = scrape_with_playwright(url)
if content is None:
    content, error = scrape_with_playwright_aggressive(url)

if content:
    print(f"Scraped {len(content)} characters")
else:
    print(f"All tiers failed: {error}")
```

### Caching

```python
url = "https://example.com"

# Check cache first
cached = get_cached_content(url)
if cached:
    print("Using cached content")
else:
    content, error = scrape_with_requests(url)
    if content:
        cache_content(url, content)

# Clear old cache entries
clear_cache(max_age_hours=24)

# Clear all cache
clear_cache()
```

### Parallel scraping

```python
from primr.data import ParallelScraper, get_parallel_scraper

scraper = get_parallel_scraper()
results = await scraper.scrape_urls([
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3"
])

for result in results:
    if result.success:
        print(f"{result.url}: {len(result.content)} chars")
    else:
        print(f"{result.url}: {result.error}")
```

## Report Generation

Generate reports from research results.

```python
from primr.output import DocumentBuilder
from pathlib import Path

builder = DocumentBuilder()

# Build DOCX from sections
doc_path = builder.build_docx(
    sections=result.section_results,
    company_name="Tesla",
    output_dir=Path("output")
)

print(f"Report saved to: {doc_path}")
```

## Configuration

### Accessing settings

```python
from primr.config import get_settings, configure

# Get current settings
settings = get_settings()
print(f"Research model: {settings.ai.research_model}")
print(f"Scrape timeout: {settings.scraping.timeout}")

# Validate settings
settings.validate_all(include_api_keys=True)
```

### Custom configuration

```python
from primr.config import configure
from pathlib import Path

settings = configure(
    project_root=Path("/custom/path"),
    verbose=True,
    debug=True
)
```

### Configuration classes

```python
from primr.config import (
    TimeoutConfig,
    CacheConfig,
    ScrapingConfig,
    AIConfig,
    SearchConfig,
    PathConfig,
    PricingConfig
)

# Example: Custom timeout config
timeout = TimeoutConfig(
    connect=10.0,
    read=30.0,
    total=60.0
)
timeout.validate()  # Raises ValueError if invalid
```

## Type Definitions

Primr provides comprehensive type definitions for type-safe code.

```python
from primr.types import (
    # Type aliases
    URL,
    FilePath,
    HTMLContent,
    TextContent,
    
    # Enums
    AIModelType,
    ThinkingLevel,
    ScrapeTier,
    OutputFormat,
    
    # TypedDicts
    SearchResult,
    ScrapedPage,
    GradeResult,
    ReportSection,
    CompanyInfo,
    ResearchContext,
    
    # Protocols
    AIClientProtocol,
    ScraperProtocol,
    SearchProtocol,
    CacheProtocol,
    
    # Generic types
    Result,
    
    # Type guards
    is_valid_url,
    is_search_result,
    is_scraped_page
)
```

### Using the Result type

```python
from primr.types import Result

def fetch_data(url: str) -> Result[str]:
    try:
        content = scrape(url)
        return Result.ok(content)
    except Exception as e:
        return Result.err(e)

result = fetch_data("https://example.com")
if result.is_ok:
    print(result.value)
else:
    print(f"Error: {result.error}")

# Or use unwrap_or for default value
content = result.unwrap_or("No content available")
```

## Error Handling

```python
from primr.utils.errors import (
    ResearchError,
    AIError,
    ScrapingError,
    ConfigurationError,
    ValidationError,
    retry_on_failure,
    safe_call
)
```

### Custom error handling

```python
from primr.utils.errors import AIError, retry_on_failure

@retry_on_failure(max_retries=3, delay=1.0)
def call_api():
    # Your code here
    pass

# Or use safe_call for exception wrapping
result = safe_call(risky_function, default_value="fallback")
```

### Error context

```python
from primr.utils.errors import error_context

with error_context("fetching company data", company="Tesla"):
    # Operations here will have context in error messages
    data = fetch_data()
```

## Logging

```python
from primr.utils.logging_config import get_logger, setup_logging

# Get a module-specific logger
logger = get_logger("my_module")
logger.info("Starting operation")
logger.debug("Debug details")
logger.error("Something went wrong")

# Configure logging
setup_logging(level="DEBUG", log_file="primr.log")
```

## Console Output

```python
from primr.utils.console import console

console.step("Starting research...")
console.ok("Research complete")
console.warn("Some sections had low quality")
console.error("Failed to scrape website")
console.progress(5, 10, "Processing sections")
console.progress_done()
```

## Observability

```python
from primr.utils.observability import (
    operation_context,
    timed,
    Metrics,
    emit_metrics
)

# Track operation duration
with operation_context("research", company="Tesla"):
    # Operations here are tracked
    pass

# Decorator for timing
@timed("my_operation")
def slow_function():
    pass

# Emit custom metrics
metrics = Metrics(
    operation="custom_op",
    duration_seconds=5.0,
    success=True,
    metadata={"key": "value"}
)
emit_metrics(metrics)
```

## Complete Example

```python
import asyncio
from pathlib import Path
from primr.core.research_orchestrator import ResearchOrchestrator, ResearchMode
from primr.output import DocumentBuilder
from primr.utils.console import console
from primr.utils.logging_config import setup_logging

async def research_company(name: str, website: str):
    # Setup
    setup_logging(level="INFO")
    
    # Progress callback
    def on_progress(msg: str):
        console.step(msg)
    
    # Run research
    console.step(f"Starting research for {name}")
    orchestrator = ResearchOrchestrator()
    
    result = await orchestrator.research(
        name,
        website,
        mode=ResearchMode.COMPLETE,
        on_progress=on_progress
    )
    
    if not result.success:
        console.error(f"Research failed: {result.error}")
        return None
    
    console.ok(f"Research complete in {result.duration_seconds:.0f}s")
    
    # Generate report
    builder = DocumentBuilder()
    output_path = builder.build_docx(
        sections=result.section_results,
        company_name=name,
        output_dir=Path("output")
    )
    
    console.ok(f"Report saved to {output_path}")
    return output_path

if __name__ == "__main__":
    asyncio.run(research_company("Tesla", "https://tesla.com"))
```

## Prompt Architecture

The prompt system (v1.2.5+) externalizes prompts to YAML configuration files.

```python
from primr.prompts import (
    PromptComposer,
    PromptContext,
    ComposedPrompt,
    StrategyModuleRegistry,
    get_registry,
    load_prompt_config,
    build_company_overview_prompt,
    build_ai_strategy_prompt,
    get_available_prompts,
)
```

### PromptComposer

Build prompts from YAML configurations with variable substitution.

```python
from primr.prompts import PromptComposer, PromptContext

composer = PromptComposer()
context = PromptContext(
    company_name="Tesla",
    website_url="https://tesla.com",
    cloud_vendor="azure",
)

# Compose a standard prompt
result = composer.compose("company_overview", context)
print(result.content)
print(f"Sections: {result.section_count}")
print(f"Words: {result.word_count}")

# Compose a strategy prompt
result = composer.compose_strategy("ai", context)
print(result.content)
```

### StrategyModuleRegistry

Discover and manage strategy modules.

```python
from primr.prompts import get_registry

registry = get_registry()

# List available strategies
for name in registry.list_names():
    print(name)  # ai, cloud, data

# Get strategy details
strategy = registry.get("ai")
print(strategy.display_name)  # "AI Strategy"
print(strategy.description)

# Get context files for a strategy (for File Search Store)
files = registry.get_context_files("ai", vendor="azure")
for f in files:
    print(f)  # docs/vendor-research-azure-2025-12.txt
```

### Legacy Prompt Builders

For backward compatibility, the original functions still work:

```python
from primr.prompts import (
    build_company_overview_prompt,
    build_ai_strategy_prompt,
    get_available_prompts,
)

# List available prompts
prompts = get_available_prompts()  # ['ai_strategy', 'company_overview', ...]

# Build prompts (delegates to PromptComposer internally)
prompt = build_company_overview_prompt("Tesla", website_url="https://tesla.com")
prompt = build_ai_strategy_prompt("Tesla", cloud_vendor="azure")
```

### Custom Exceptions

```python
from primr.prompts import (
    PromptConfigError,
    PromptConfigNotFoundError,
    PromptConfigValidationError,
    StrategyModuleNotFoundError,
    DataSourceNotFoundError,
)

try:
    composer.compose("nonexistent", context)
except PromptConfigNotFoundError as e:
    print(f"Not found: {e.prompt_name}")
    print(f"Searched: {e.searched_paths}")
    print(f"Available: {e.available_prompts}")
```

## Singleton Management

Most components use thread-safe singletons. For testing or custom configurations, you can reset them:

```python
from primr.ai import reset_client
from primr.data import reset_cache
from primr.config import reset_settings

# Reset all singletons
reset_client()
reset_cache()
reset_settings()
```

## MCP Server

Primr includes a Model Context Protocol (MCP) server that enables AI agents to drive company research programmatically. The MCP server exposes Primr's functionality through a standardized protocol that AI assistants like Claude Desktop can use.

### Quick Start

```bash
# Run with stdio transport (for Claude Desktop)
primr-mcp --stdio

# Run with HTTP transport
primr-mcp --http --port 8000

# Development mode (no auth)
primr-mcp --http --port 8000 --no-auth --allow-plaintext
```

### Claude Desktop Integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "primr": {
      "command": "primr-mcp",
      "args": ["--stdio"]
    }
  }
}
```

### Programmatic Usage

```python
import asyncio
from primr.mcp_server import create_mcp_server

async def main():
    # Create server with stdio transport
    server = create_mcp_server(transport="stdio")
    await server.run()

    # Or with HTTP transport
    server = create_mcp_server(
        transport="streamable-http",
        port=8000,
        host="127.0.0.1",
        require_auth=True,
    )
    await server.run()

asyncio.run(main())
```

### Tools

The MCP server exposes 8 tools for research operations:

#### estimate_run

Get cost and time estimates before running research.

```json
{
  "name": "estimate_run",
  "arguments": {
    "company_url": "https://tesla.com",
    "mode": "full"
  }
}
```

Response:
```json
{
  "estimated_cost_usd": 0.75,
  "estimated_time_minutes": 30,
  "planned_pages": 20,
  "mode": "full"
}
```

#### research_company

Initiate company research (async - returns job_id immediately).

```json
{
  "name": "research_company",
  "arguments": {
    "company_name": "Tesla",
    "company_url": "https://tesla.com",
    "mode": "full",
    "cloud_vendor": "azure",
    "skip_qa": false
  }
}
```

Response:
```json
{
  "job_id": "job_abc123",
  "accepted": true,
  "status_uri": "primr://research/status"
}
```

#### generate_strategy

Generate strategy document from existing report.

```json
{
  "name": "generate_strategy",
  "arguments": {
    "report_path": "output/Tesla_Strategic_Overview.md",
    "strategy_type": "customer_experience",
    "cloud_vendor": "azure"
  }
}
```

Strategy types: `ai_strategy`, `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`

#### check_jobs

Check status of research jobs.

```json
{
  "name": "check_jobs",
  "arguments": {
    "job_id": "job_abc123"
  }
}
```

Response:
```json
{
  "jobs": [
    {
      "job_id": "job_abc123",
      "status": "in_progress",
      "company_name": "Tesla",
      "output_path": null
    }
  ]
}
```

#### run_qa

Run quality assessment on a report.

```json
{
  "name": "run_qa",
  "arguments": {
    "report_path": "output/Tesla_Strategic_Overview.md"
  }
}
```

#### doctor

Check system health and configuration.

```json
{
  "name": "doctor",
  "arguments": {}
}
```

#### clear_jobs

Clear stale pending jobs.

```json
{
  "name": "clear_jobs",
  "arguments": {
    "older_than_hours": 24
  }
}
```

#### cancel_job

Cancel an active research job.

```json
{
  "name": "cancel_job",
  "arguments": {
    "job_id": "job_abc123"
  }
}
```

### Resources

The MCP server exposes 4 read-only resources:

#### primr://research/status

Current research job status with progress information.

```json
{
  "status": "in_progress",
  "job_id": "job_abc123",
  "company_name": "Tesla",
  "mode": "full",
  "current_stage": "deep_research",
  "stage_progress_percent": 45,
  "stage_expected_minutes": 15,
  "possibly_stuck": false
}
```

#### primr://output/latest

Most recent research output. Add `?full_content=true` for complete content.

```json
{
  "report_path": "output/Tesla_Strategic_Overview.md",
  "company_name": "Tesla",
  "generation_timestamp": "2026-02-02T10:30:00",
  "report_type": "markdown",
  "content_preview": "# Tesla Strategic Overview..."
}
```

#### primr://output/artifacts

Pipeline stage artifacts (scraped_content, insights, dossier, reports).

```json
{
  "job_id": "job_abc123",
  "job_status": "completed",
  "artifacts": [
    {
      "artifact_type": "scraped_content",
      "file_path": "output/tesla/scraped_content.txt",
      "size_bytes": 125000,
      "preview": "Tesla, Inc. designs...",
      "content_hash": "sha256:abc123..."
    }
  ]
}
```

#### primr://config

Current configuration (no secrets exposed).

```json
{
  "available_modes": ["scrape", "deep", "full"],
  "available_strategies": {
    "ai_strategy": "AI/ML transformation roadmap",
    "customer_experience": "CX improvement plan",
    "modern_security_compliance": "Security posture assessment",
    "data_fabric_strategy": "Data platform modernization"
  },
  "configured_vendors": ["azure", "aws", "gcp"]
}
```

#### primr://strategies/available

List of available strategy types with metadata for Open Claw integration.

```json
{
  "schema_version": "1.0",
  "strategies": [
    {
      "id": "ai_strategy",
      "name": "AI Strategy",
      "description": "AI/ML transformation roadmap with quick wins and bigger bets",
      "requires_cloud_vendor": true,
      "estimated_time_minutes": 15,
      "estimated_cost_usd": 0.30
    },
    {
      "id": "customer_experience",
      "name": "Customer Experience Strategy",
      "description": "CX transformation and digital experience improvement plan",
      "requires_cloud_vendor": false,
      "estimated_time_minutes": 12,
      "estimated_cost_usd": 0.25
    },
    {
      "id": "modern_security_compliance",
      "name": "Security & Compliance Strategy",
      "description": "Zero Trust architecture and compliance posture assessment",
      "requires_cloud_vendor": false,
      "estimated_time_minutes": 12,
      "estimated_cost_usd": 0.25
    },
    {
      "id": "data_fabric_strategy",
      "name": "Data Fabric Strategy",
      "description": "Modern data platform for agentic AI and semantic layers",
      "requires_cloud_vendor": false,
      "estimated_time_minutes": 12,
      "estimated_cost_usd": 0.25
    }
  ]
}
```

#### primr://output/by_job/{job_id}

Job-scoped artifact retrieval for provenance tracking. Ensures the returned report corresponds to a specific approved job.

```json
{
  "job_id": "abc123",
  "report_path": "output/acme_corp/report.md",
  "company_name": "Acme Corp",
  "generation_timestamp": "2026-02-15T10:31:00Z",
  "report_type": "markdown",
  "content_preview": "# Acme Corp Strategic Overview...",
  "manifest_path": "output/acme_corp/run_manifest.json"
}
```

#### primr://output/manifest/latest

Run manifest for the most recent completed job. Provides audit trail for compliance and debugging.

```json
{
  "schema_version": "1.0",
  "job_id": "abc123",
  "company_name": "Acme Corp",
  "company_url": "https://acme.example",
  "mode": "full",
  "estimate": {
    "cost_usd": 0.75,
    "time_minutes": 30,
    "estimated_at": "2026-02-15T10:00:00Z"
  },
  "approval": {
    "token": "ABC123",
    "approved_at": "2026-02-15T10:01:00Z",
    "approved_by": "stdio",
    "bound_to_estimate": true
  },
  "execution": {
    "started_at": "2026-02-15T10:01:05Z",
    "completed_at": "2026-02-15T10:31:00Z",
    "status": "completed",
    "actual_cost_usd": 0.72,
    "actual_time_minutes": 30
  },
  "artifacts": [
    "output/acme_corp/report.md",
    "output/acme_corp/scraped_content.txt",
    "output/acme_corp/insights.txt"
  ]
}
```

### Prompt Templates

Two prompt templates are available for guided workflows:

#### research_workflow

Guides through the complete research process.

#### strategy_selection

Helps select appropriate strategy types based on company context.

### Security

The MCP server includes comprehensive security features:

#### Path Validation

All file paths are validated to prevent path traversal attacks:
- Paths must be relative to workspace root
- Symlinks are resolved and checked
- `..` sequences are blocked

#### URL Validation

URLs are validated to prevent SSRF attacks:
- Only HTTP/HTTPS schemes allowed
- Private/internal IPs blocked (10.x, 172.16-31.x, 192.168.x, 127.x)
- DNS rebinding protection

#### Rate Limiting

Per-tool rate limits prevent abuse:
- `estimate_run`: 30 requests/minute
- `research_company`: 2 requests/minute
- Other tools: 10 requests/minute

#### Authentication (HTTP mode)

JWT authentication for HTTP transport:
- Tokens verified via JWKS endpoint or shared secret
- Admin policy: `role=admin` claim or `MCP_ADMIN_TOKENS` env var
- Client ID extracted for rate limiting and job ownership

```python
# Configure auth via environment
MCP_JWT_SECRET=your-secret-key
MCP_ADMIN_TOKENS=token1,token2
```

### Job Store

The MCP server uses a single-job model with journal persistence:

```python
from primr.mcp_server.job_store import SingleJobStore

store = SingleJobStore(journal_path="logs/mcp_journal.json")

# Create a job
job = store.create(company_name="Tesla", mode="full", owner_client_id="client1")

# Update progress
job.advance_stage(ResearchStage.DEEP_RESEARCH)
job.heartbeat(progress=50)
store.update(job)

# Check for stuck jobs
if job.is_possibly_stuck():
    print("Job may be stuck - no heartbeat in 5+ minutes")

# Get active job
active = store.get_active()

# Get latest completed job
terminal = store.get_latest_terminal()
```

### Graceful Shutdown

The server handles shutdown gracefully:
1. Waits up to 5 seconds for current work to complete
2. Force-cancels remaining tasks after timeout
3. Marks in-progress jobs as failed with `error_type="server_shutdown"`
4. Flushes journal to disk
5. Total shutdown timeout: 10 seconds

### Error Codes

Standard error codes returned by tools:

| Code | Description |
|------|-------------|
| `INVALID_URL` | URL format invalid |
| `SSRF_BLOCKED` | URL blocked for security |
| `URL_UNREACHABLE` | URL could not be reached |
| `PATH_TRAVERSAL_BLOCKED` | Path traversal attempt blocked |
| `REPORT_NOT_FOUND` | Report file not found |
| `JOB_NOT_FOUND` | Job ID not found |
| `JOB_IN_PROGRESS` | Another job already running |
| `RATE_LIMIT_EXCEEDED` | Rate limit exceeded |
| `CANCEL_NOT_AUTHORIZED` | Not authorized to cancel job |
