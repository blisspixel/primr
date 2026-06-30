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
        "Acme Corp",
        "https://acme.example",
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
    "Acme Corp",
    "https://acme.example",
    mode=ResearchMode.COMPLETE,
    on_progress=on_progress
)
```

### ResearchMode

Available research modes.

```python
from primr.core.research_orchestrator import ResearchMode

ResearchMode.STRUCTURED      # Website scraping + web search
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
result = await orchestrator.research("Acme Corp", "https://acme.example")

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
folder = create_working_folder("Acme Corp")
print(f"Working folder: {folder}")

# Save section output
save_section_output(folder, "company_overview", "Acme Corp is a technology company...")

# Consolidate all sections into a single file
result = consolidate_working_folder(folder)
print(f"Consolidated {result.section_count} sections")
```

### AI Strategy Generation

Generate AI strategy recommendations with platform context.

```python
from primr.core.ai_strategy import (
    generate_ai_strategy_sync,
    Platform,
    AIStrategyConfig,
    AIStrategyResult,
)
```

```python
# Generate AI strategy for a company
config = AIStrategyConfig(
    company_name="Acme Corp",
    platform=Platform.AWS,
    working_folder=Path("working/Acme Corp"),
)

result = generate_ai_strategy_sync(config)
if result.success:
    print(result.content)
```

**Platform enum**:

```python
Platform.AWS      # Amazon Web Services
Platform.AZURE    # Microsoft Azure
Platform.GCP      # Google Cloud Platform
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
        company_name="Acme Corp",
        prompt="Research Acme Corp's competitive position in the market",
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
config = parse_args(["Acme Corp", "https://acme.example", "--mode", "deep"])
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

Platform AI capabilities research.

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
    Platform,
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
    "Research Acme Corp's competitive position in the market"
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
    "Research Acme Corp",
    on_progress=on_progress
)
```

### Output formats

```python
# Company profile format
result = await client.research(
    "Research Acme Corp",
    output_format="company_profile"
)

# Executive summary format
result = await client.research(
    "Research Acme Corp",
    output_format="executive_summary"
)

# Competitive analysis format
result = await client.research(
    "Research Acme Corp",
    output_format="competitive_analysis"
)
```

### With priority URLs

```python
result = await client.research(
    "Research Acme Corp",
    priority_urls=["https://acme.example", "https://ir.acme.example"]
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
    description="AI Strategy for Acme Corp"
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
    company_name="Acme Corp",
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

with error_context("fetching company data", company="Acme Corp"):
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
with operation_context("research", company="Acme Corp"):
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
    asyncio.run(research_company("Acme Corp", "https://acme.example"))
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
    company_name="Acme Corp",
    website_url="https://acme.example",
    platform="azure",
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
    print(f)  # vendor-research/vendor-research-azure-2025-12.txt
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
prompt = build_company_overview_prompt("Acme Corp", website_url="https://acme.example")
prompt = build_ai_strategy_prompt("Acme Corp", platform="azure")
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

The MCP server exposes 10 tools for research operations:

#### estimate_run

Get cost and time estimates before running research. For stricter agent governance, pass the approved estimate into `research_company.max_estimated_cost_usd`.

```json
{
  "name": "estimate_run",
  "arguments": {
    "company_url": "https://acme.example",
    "mode": "full",
    "platforms": ["azure"],
    "strategy_type": "ai",
    "no_ai_strategy": false
  }
}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `company_url` | string | Yes | Company website URL |
| `mode` | string | No | Research mode: `full` (default), `premium`, `scrape`, `deep` |
| `platforms` | array of strings | No | Platform(s) for AI strategy. Each adds ~3-6 min + ~$0.10-0.15. Values: `azure`, `aws`, `gcp`, `agnostic`, `private`. Default: `["agnostic"]` |
| `strategy_type` | string | No | Strategy type: `ai` (default), `customer_experience`, `modern_security_compliance`, `data_fabric_strategy` |
| `no_ai_strategy` | boolean | No | Skip AI strategy generation entirely (report only). Default: `false` |
| `verify` | boolean | No | Run post-QA claim verification (~$0.01, 3-5 min). Default: `false` |
| `max_estimated_cost_usd` | number | No | Hard ceiling for estimated run cost |

Response:
```json
{
  "estimated_cost_usd": 0.75,
  "estimated_time_minutes": 30,
  "estimated_time_range": "35-50 min",
  "planned_pages": 20,
  "mode": "full",
  "ai_strategy": true,
  "platforms": ["azure"],
  "strategy_type": "ai"
}
```

#### estimate_strategy

Get cost and time estimates before generating a strategy document. For stricter agent governance, pass the approved estimate into `generate_strategy.max_estimated_cost_usd`.

```json
{
  "name": "estimate_strategy",
  "arguments": {
    "strategy_type": "customer_experience"
  }
}
```

Response:
```json
{
  "strategy_type": "customer_experience",
  "estimated_cost_usd": 0.25,
  "estimated_time_minutes": 12,
  "requires_platform": false,
  "platform": null,
  "cost_warning": "Strategy generation incurs real API charges. Get explicit user approval before generate_strategy."
}
```

#### research_company

Initiate company research (async - returns job_id immediately). Includes AI strategy generation when `platform` is specified - no separate `generate_strategy` call needed. This should only be called after `estimate_run` and explicit user approval.

```json
{
  "name": "research_company",
  "arguments": {
    "company_name": "Acme Corp",
    "company_url": "https://acme.example",
    "mode": "full",
    "platform": "azure",
    "skip_qa": false,
    "max_estimated_cost_usd": 0.67
  }
}
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `company_name` | string | Yes | Display name for the company |
| `company_url` | string | Yes | Company website URL (must be valid HTTP/HTTPS) |
| `mode` | string | No | Research mode: `full` (default), `premium`, `scrape`, `deep` |
| `platform` | string | No | Platform for AI strategy. When set, strategy is generated as part of this job. Values: `azure`, `aws`, `gcp`, `agnostic`, `private`. |
| `skip_qa` | boolean | No | Skip quality assessment. Default: `false` |
| `verify` | boolean | No | Run post-QA claim verification. Default: `false` |
| `destination` | string | No | Optional destination directory for output files. Artifacts are copied here in addition to the default output/ directory. |
| `max_estimated_cost_usd` | number | No | Hard ceiling for estimated run cost |

Response:
```json
{
  "job_id": "job_abc123",
  "accepted": true,
  "status_uri": "primr://research/status"
}
```

#### generate_strategy

Generate strategy document from an existing report after the fact. Only needed when adding a strategy to a previously completed research run. For new research, use `research_company` with `platform` instead - strategy is included automatically.

```json
{
  "name": "generate_strategy",
  "arguments": {
    "report_path": "output/Acme_Corp_Strategic_Overview.md",
    "strategy_type": "customer_experience",
    "platform": "azure",
    "max_estimated_cost_usd": 0.30
  }
}
```

Strategy types: `ai_strategy`, `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`

#### check_jobs

Check status of research jobs. When a job is completed, returns full artifact content (report + strategy MD files) inline so the agent client can consume them directly without filesystem access.

```json
{
  "name": "check_jobs",
  "arguments": {
    "job_id": "job_abc123"
  }
}
```

Response (in progress):
```json
{
  "jobs": [
    {
      "job_id": "job_abc123",
      "status": "in_progress",
      "company_name": "Acme Corp",
      "output_path": null
    }
  ]
}
```

Response (completed - includes artifact content):
```json
{
  "jobs": [
    {
      "job_id": "job_abc123",
      "status": "completed",
      "company_name": "Acme Corp",
      "output_path": "output/Acme_Corp_Strategic_Overview_04-08-2026.md",
      "artifacts": [
        {
          "type": "strategic_overview",
          "filename": "Acme_Corp_Strategic_Overview_04-08-2026.md",
          "content": "# Acme Corp Strategic Overview\n\n..."
        },
        {
          "type": "ai_strategy",
          "filename": "Acme_Corp_AI_Strategy_AZURE_04-08-2026.md",
          "content": "# AI Strategy (Azure)\n\n..."
        }
      ]
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
    "report_path": "output/Acme_Corp_Strategic_Overview.md"
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

#### delegate_to_agent

Delegate a task to an external A2A agent. Requires `pip install primr[a2a]`.

```json
{
  "name": "delegate_to_agent",
  "arguments": {
    "agent_url": "https://remote-agent.example.com",
    "message": "Research Acme Corp competitive landscape",
    "skill_id": "research_company"
  }
}
```

Response (success):
```json
{
  "status": {"state": "completed"},
  "artifacts": [...]
}
```

Response (error):
```json
{
  "error": true,
  "error_type": "a2a_delegation_failed",
  "message": "Connection refused"
}
```

SSRF protection validates all agent URLs. Private IPs, metadata endpoints, and non-HTTP schemes are blocked.

### Prompts

#### governed_execution

Use this prompt when building a generic cost-aware MCP client. It encodes the default contract: estimate first, tell the user the action costs money, get explicit approval, pass `max_estimated_cost_usd` into spend tools, and treat research as a long-running async job.

#### research_workflow

Guided workflow for company research.

#### strategy_selection

Guided workflow for selecting and generating strategy documents.

### A2A Server

Primr can also expose its capabilities via the A2A (Agent-to-Agent) protocol, allowing other agents to discover and invoke Primr's research tools.

```bash
# Install A2A support
pip install primr[a2a]

# Standalone A2A server (auth on; binds to 127.0.0.1 by default)
primr-a2a

# Local-development shortcut. --no-auth is refused unless --host is loopback,
# so accidentally exposing the A2A skill set on a public interface fails closed.
primr-a2a --host 127.0.0.1 --no-auth

# Co-hosted with MCP server
primr-mcp --http --a2a --a2a-port 9000
```

**Agent Card** (served at `/.well-known/agent.json`):
```bash
curl http://localhost:9000/.well-known/agent.json
```

Authenticated A2A requests use the same bearer-token identity and legacy
scope compatibility as MCP HTTP. `read` can estimate, inspect job status, and
check health. `research` is required to start paid work, run QA, or cancel an
A2A research task. Legacy `write` tokens still satisfy `research` for
compatibility.

**Skills available via A2A:**

| Skill ID | Required scope | Description |
|----------|----------------|-------------|
| `estimate_research` | `read` | Cost/time estimate plus approval-token fields for a research run |
| `research_company` | `research` | Start async research (SSE streaming progress); when cost-cap enforcement is active, requires `max_estimated_cost_usd` and the matching `approval_token` from `estimate_research` |
| `check_jobs` | `read` | Current job status |
| `run_qa` | `research` | Quality assessment on completed reports |
| `read_artifacts_by_job` | `read` | Compact owned-job artifact metadata without report body content |
| `read_qa_summary_by_job` | `read` | Compact owned-job QA summary metadata without detailed QA/report bodies |
| `read_usage_summary_by_job` | `read` | Compact owned-job usage/cost metadata without approval tokens or report bodies |
| `read_source_summary_by_job` | `read` | Compact owned-job source appendix metadata without report bodies |
| `read_trace_summary_by_job` | `read` | Compact owned-job scrape trace metadata without URLs, raw trace entries, or page content |
| `read_verification_summary_by_job` | `read` | Compact owned-job claim verification metadata without raw claims or source URLs |
| `read_calibration_summary_by_job` | `read` | Compact owned-job label-calibration metadata without raw claims, source URLs, evidence reviews, or rationales |
| `read_stage_scorecard` | `read` | Compact eval scorecard metadata by eval id |
| `system_health` | `read` | System diagnostics |

**Example A2A estimate message:**
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "{\"url\": \"https://acme.com\", \"mode\": \"full\"}"}],
      "metadata": {"skillId": "estimate_research"}
    }
  }
}
```

Use the returned `estimated_cost_usd` as `max_estimated_cost_usd` and pass the
returned `approval_token` into `research_company` when cost-cap enforcement is
active.

**Example A2A research message:**
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "{\"url\": \"https://acme.com\", \"name\": \"Acme\", \"mode\": \"full\", \"max_estimated_cost_usd\": 0.67, \"approval_token\": \"<token from estimate_research>\"}"}],
      "metadata": {"skillId": "research_company"}
    }
  }
}
```

The A2A server shares the MCP server's `SingleJobStore`, rate limiter, auth
context, and security middleware. The single-job model is enforced across both
protocols. Authenticated A2A jobs are owned by the token `client_id`; local
unauthenticated loopback jobs keep the legacy `a2a` owner id.
Skill invocations and task cancellation write privacy-preserving audit events
to the shared audit JSONL. Events include transport, skill name, outcome,
hashed message/result payloads, hashed caller id, granted scopes, duration,
job id when present, and sanitized estimate/cap metadata. They do not store
raw A2A message text, task ids, company URLs, report paths, approval tokens,
raw results, or caller ids.

### Resources

The MCP server exposes primary read-only resources for job state, governance, audit, and output discovery. For agent clients, assume research is long-running and monitor/resume from job state rather than blocking on one request:

#### primr://research/status

Current research job status with progress information.

```json
{
  "status": "in_progress",
  "job_id": "job_abc123",
  "company_name": "Acme Corp",
  "mode": "full",
  "current_stage": "deep_research",
  "stage_progress_percent": 45,
  "stage_expected_minutes": 15,
  "possibly_stuck": false
}
```

#### primr://research/next-actions

Recommended next action for the active or latest job.

```json
{
  "job_source": "active",
  "job_id": "job_abc123",
  "status": "in_progress",
  "recommended_action": "monitor_job",
  "message": "Research is still running. Monitor status instead of relaunching the job.",
  "follow_up": [
    "Read primr://research/status",
    "Use wait_for_status_change for short blocking waits",
    "Reconnect and resume monitoring if the client session drops"
  ]
}
```

#### primr://agent/governance

Default governance contract for generic MCP clients.

```json
{
  "schema_version": "1.0",
  "principles": [
    "Call estimate tools before any cost-incurring tool",
    "Tell the user the action incurs real API charges",
    "Get explicit approval before execution",
    "Pass max_estimated_cost_usd into cost-incurring tools when possible"
  ],
  "research_flow": {
    "estimate_tool": "estimate_run",
    "execute_tool": "research_company",
    "cap_argument": "max_estimated_cost_usd"
  },
  "strategy_flow": {
    "estimate_tool": "estimate_strategy",
    "execute_tool": "generate_strategy",
    "cap_argument": "max_estimated_cost_usd"
  }
}
```

#### primr://agent/audit/recent

Recent privacy-preserving agent audit events for MCP tool calls, MCP resource
reads, and A2A skill calls. Local stdio callers can read this directly; HTTP
callers need `admin` scope. Events include hashes and metadata, not raw tool
arguments, raw tool results, raw A2A message text, task ids, raw resource URI
query values, raw resource bodies, raw caller ids, report paths, URLs, or
approval tokens.

```json
{
  "schema_version": "1.0",
  "event_count": 2,
  "events": [
    {
      "schema_version": "1.0",
      "event_type": "tool_call",
      "tool_name": "estimate_run",
      "status": "success",
      "transport": "stdio",
      "actor": "stdio",
      "client_id_hash": null,
      "auth_scopes": [],
      "args_hash": "sha256:...",
      "result_hash": "sha256:...",
      "approval_token_id": "tok_...",
      "estimated_cost_usd": 0.89,
      "duration_ms": 8
    },
    {
      "schema_version": "1.0",
      "event_type": "tool_call",
      "tool_name": "a2a/check_jobs",
      "status": "success",
      "transport": "a2a",
      "actor": null,
      "client_id_hash": "sha256:...",
      "auth_scopes": ["read"],
      "args_hash": "sha256:...",
      "result_hash": "sha256:...",
      "duration_ms": 3
    },
    {
      "schema_version": "1.0",
      "event_type": "resource_read",
      "tool_name": "resources/read",
      "status": "success",
      "transport": "http",
      "actor": null,
      "client_id_hash": "sha256:...",
      "auth_scopes": ["read"],
      "args_hash": "sha256:...",
      "result_hash": "sha256:...",
      "resource_kind": "primr://output/calibration_summary/by_job/{job_id}",
      "resource_uri_hash": "sha256:...",
      "job_id": "job_abc123",
      "duration_ms": 4
    }
  ]
}
```

#### primr://research/modes

Current mode guidance for integrations.

```json
{
  "schema_version": "1.0",
  "default_mode": "full",
  "default_mode_behavior": "Standard research pipeline. When XAI_API_KEY is available, Primr uses the Grok hybrid path by default. Use premium to force Gemini Deep Research.",
  "cost_warning": "Research runs incur real API charges. Call estimate_run first and get explicit user approval before research_company.",
  "search_defaults": {
    "provider": "duckduckgo",
    "search_api_key_required": false,
    "google_custom_search_optional": true
  }
}
```

#### primr://output/latest

Most recent research output. Add `?full_content=true` for complete content.

```json
{
  "report_path": "output/Acme_Corp_Strategic_Overview.md",
  "company_name": "Acme Corp",
  "generation_timestamp": "2026-02-02T10:30:00",
  "report_type": "markdown",
  "content_preview": "# Acme Corp Strategic Overview..."
}
```

#### primr://output/artifacts

Pipeline stage artifacts for the active job or latest terminal job. This
legacy resource includes short previews and is useful for local interactive
review. Prefer `primr://output/artifacts/by_job/{job_id}` for agent automation
that only needs a compact inventory, and
`primr://output/qa_summary/by_job/{job_id}` when the client only needs QA
metadata, and `primr://output/usage_summary/by_job/{job_id}` when the client
only needs cost, timing, approval, or artifact-count metadata, and
`primr://output/source_summary/by_job/{job_id}` when the client only needs
citation/source appendix metadata, and
`primr://output/trace_summary/by_job/{job_id}` when the client only needs
scrape trace health metadata, and
`primr://output/verification_summary/by_job/{job_id}` when the client only
needs claim verification metadata, and
`primr://output/calibration_summary/by_job/{job_id}` when the client only
needs label-calibration metadata, including report-only inference source-copy
counts.

```json
{
  "job_id": "job_abc123",
  "job_status": "completed",
  "artifacts": [
    {
      "artifact_type": "scraped_content",
      "file_path": "output/acme_corp/scraped_content.txt",
      "size_bytes": 125000,
      "preview": "Acme Corp designs...",
      "content_hash": "sha256:abc123..."
    }
  ]
}
```

#### primr://output/artifacts/by_job/{job_id}

Compact, ownership-gated artifact metadata for one job. This resource returns
file names, paths, sizes, hashes, timestamps, classifications, and missing-file
state without report body content. Use it before requesting full report content
or broad output previews.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/artifacts/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "artifact_count": 3,
  "full_content_included": false,
  "artifacts": [
    {
      "index": 0,
      "artifact_type": "report_markdown",
      "file_name": "Acme_Corp_Strategic_Overview_06-28-2026.md",
      "file_path": "output/acme_corp/Acme_Corp_Strategic_Overview_06-28-2026.md",
      "exists": true,
      "size_bytes": 184320,
      "modified_at": "2026-06-28T18:30:00+00:00",
      "content_hash": "sha256:abc123..."
    },
    {
      "index": 1,
      "artifact_type": "run_manifest",
      "file_name": "run_manifest.json",
      "file_path": "output/acme_corp/run_manifest.json",
      "exists": true,
      "size_bytes": 4096,
      "modified_at": "2026-06-28T18:30:01+00:00",
      "content_hash": "sha256:def456..."
    },
    {
      "index": 2,
      "artifact_type": "report_docx",
      "file_name": "Acme_Corp_Strategic_Overview_06-28-2026.docx",
      "file_path": "output/acme_corp/Acme_Corp_Strategic_Overview_06-28-2026.docx",
      "exists": false
    }
  ]
}
```

Error responses:

```json
{
  "error": "job_not_found",
  "message": "No job found with ID: job_abc123",
  "job_id": "job_abc123"
}
```

```json
{
  "error": "no_artifacts",
  "message": "Job job_abc123 has no output artifacts yet",
  "job_id": "job_abc123",
  "status": "running"
}
```

#### primr://output/qa_summary/by_job/{job_id}

Compact, ownership-gated QA artifact summary for one job. This resource reads
attached QA JSON sidecars and current text QA reports classified as
`qa_summary`, then returns score, status, count, parse, hash, timestamp, and
top-level-key metadata without returning detailed issue, recommendation, or
report body text.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids. Malformed QA JSON returns metadata plus `parse_error`
without echoing the malformed body.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/qa_summary/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "summary_count": 1,
  "full_content_included": false,
  "summaries": [
    {
      "index": 2,
      "artifact_type": "qa_summary",
      "file_name": "Acme_Corp_QA_Report.json",
      "file_path": "output/acme_corp/Acme_Corp_QA_Report.json",
      "exists": true,
      "size_bytes": 2048,
      "modified_at": "2026-06-28T18:45:00+00:00",
      "content_hash": "sha256:abc123...",
      "parsed": true,
      "full_content_included": false,
      "top_level_keys": ["issues", "overall_score", "ready_for_use", "status"],
      "status_fields": {
        "ready_for_use": true,
        "status": "passed"
      },
      "score_fields": {
        "overall_score": 91
      },
      "count_fields": {
        "issues_count": 0
      }
    }
  ]
}
```

No QA summary response:

```json
{
  "error": "qa_summary_not_found",
  "message": "Job job_abc123 has no attached QA summary artifact",
  "job_id": "job_abc123",
  "status": "completed",
  "summary_count": 0
}
```

#### primr://output/usage_summary/by_job/{job_id}

Compact, ownership-gated usage and cost summary for one job. This resource
reads `run_manifest.json` files adjacent to the owned job's output artifacts
and returns cost, timing, approval, execution, parse, hash, timestamp, and
artifact-count metadata without returning company URL, approval token, the
manifest artifact list, or full manifest content.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids. Malformed manifests return metadata plus `parse_error`
without echoing the malformed body.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/usage_summary/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "summary_count": 1,
  "full_content_included": false,
  "summaries": [
    {
      "index": 0,
      "artifact_type": "run_manifest",
      "file_name": "run_manifest.json",
      "file_path": "output/acme_corp/run_manifest.json",
      "exists": true,
      "size_bytes": 4096,
      "modified_at": "2026-06-28T20:30:00+00:00",
      "content_hash": "sha256:abc123...",
      "parsed": true,
      "full_content_included": false,
      "manifest_schema_version": "1.0",
      "mode": "full",
      "estimate": {
        "cost_usd": 0.76,
        "time_minutes": 42,
        "estimated_at": "2026-06-28T19:00:00Z"
      },
      "approval": {
        "approved": true,
        "approved_at": "2026-06-28T19:01:00Z",
        "bound_to_estimate": true,
        "approved_by_present": true,
        "token_present": false
      },
      "execution": {
        "started_at": "2026-06-28T19:02:00Z",
        "completed_at": "2026-06-28T19:44:00Z",
        "status": "completed",
        "actual_cost_usd": 0.72,
        "actual_time_minutes": 42
      },
      "artifact_count": 3
    }
  ]
}
```

No manifest response:

```json
{
  "error": "usage_summary_not_found",
  "message": "Job job_abc123 has no run manifest available",
  "job_id": "job_abc123",
  "status": "completed",
  "summary_count": 0
}
```

#### primr://output/source_summary/by_job/{job_id}

Compact, ownership-gated source appendix summary for one job. This resource
reads owned markdown and text report artifacts, parses the source appendix, and
returns citation counts, source definition counts, missing and unused citation
numbers, duplicate URL counts, source domains, and source URLs without
returning report body content.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/source_summary/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "summary_count": 1,
  "full_content_included": false,
  "summaries": [
    {
      "index": 0,
      "artifact_type": "report_markdown",
      "file_name": "Acme_Corp_Strategic_Overview_06-28-2026.md",
      "file_path": "output/acme_corp/Acme_Corp_Strategic_Overview_06-28-2026.md",
      "exists": true,
      "size_bytes": 184320,
      "modified_at": "2026-06-28T20:30:00+00:00",
      "content_hash": "sha256:abc123...",
      "parsed": true,
      "source_format": "markdown",
      "source_section_present": true,
      "full_content_included": false,
      "inline_reference_count": 12,
      "referenced_numbers": [1, 2, 3],
      "definition_count": 3,
      "valid_source_count": 3,
      "invalid_source_count": 0,
      "duplicate_url_count": 0,
      "missing_definition_numbers": [],
      "unused_definition_numbers": [],
      "domains": [
        {"domain": "acme.example", "count": 2},
        {"domain": "sec.gov", "count": 1}
      ],
      "sources": [
        {
          "reference": 1,
          "url": "https://acme.example/news",
          "domain": "acme.example",
          "title": "Acme newsroom"
        }
      ]
    }
  ]
}
```

No report artifact response:

```json
{
  "error": "source_summary_not_found",
  "message": "Job job_abc123 has no report artifact available for source summary",
  "job_id": "job_abc123",
  "status": "completed",
  "summary_count": 0
}
```

#### primr://output/trace_summary/by_job/{job_id}

Compact, ownership-gated scrape trace summary for one job. Same-run trace JSONL
files are attached to job metadata when present. This resource parses those
trace artifacts and returns tier attempts, success rates, latency summaries,
block counts, HTTP status counts, and validation health without returning URLs,
final URLs, raw trace entries, or page content.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/trace_summary/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "summary_count": 1,
  "full_content_included": false,
  "summaries": [
    {
      "index": 0,
      "artifact_type": "scrape_trace",
      "file_name": "Acme_Corp_20260628_213000.jsonl",
      "file_path": "logs/scrape_traces/Acme_Corp_20260628_213000.jsonl",
      "exists": true,
      "size_bytes": 8192,
      "modified_at": "2026-06-28T21:30:00+00:00",
      "content_hash": "sha256:abc123...",
      "parsed": true,
      "trace_schema_version": "1.1",
      "trace_run_id": "trace-run-1",
      "trace_started_at": "2026-06-28T21:00:00",
      "full_content_included": false,
      "raw_entries_included": false,
      "urls_included": false,
      "entry_count": 12,
      "success_count": 10,
      "failure_count": 2,
      "success_rate": 0.8333333333333334,
      "blocked_count": 1,
      "block_type_counts": [{"value": "hard_block", "count": 1}],
      "http_status_counts": [{"value": "200", "count": 10}],
      "tier_summaries": [
        {
          "tier": "requests",
          "attempts": 12,
          "successes": 8,
          "success_rate": 0.6666666666666666,
          "avg_latency_ms": 125.0,
          "p95_latency_ms": 250.0
        }
      ],
      "avg_text_length": 4200.0,
      "thin_page_count": 1,
      "validated_page_count": 9,
      "valid_page_count": 8,
      "content_valid_rate": 0.8888888888888888
    }
  ]
}
```

No trace artifact response:

```json
{
  "error": "trace_summary_not_found",
  "message": "Job job_abc123 has no scrape trace artifact available",
  "job_id": "job_abc123",
  "status": "completed",
  "summary_count": 0
}
```

#### primr://output/verification_summary/by_job/{job_id}

Compact, ownership-gated claim verification summary for one job. Same-run
`verification.json` artifacts are attached to job metadata when MCP
verification runs, including fast-mode MCP runs. This resource parses those
verification artifacts and returns trust score, claim counts, status counts,
first-party downgrade counts, and source-reference counts without returning
raw claims, source URLs, search queries, explanations, or report body content.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/verification_summary/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "summary_count": 1,
  "full_content_included": false,
  "summaries": [
    {
      "index": 1,
      "artifact_type": "verification_summary",
      "file_name": "verification.json",
      "file_path": "output/acme_corp/verification.json",
      "exists": true,
      "size_bytes": 4096,
      "modified_at": "2026-06-28T21:45:00+00:00",
      "content_hash": "sha256:abc123...",
      "parsed": true,
      "full_content_included": false,
      "raw_claim_results_included": false,
      "source_urls_included": false,
      "search_queries_included": false,
      "trust_score": 0.88,
      "trust_percentage": 88,
      "verification_gate": "PASS",
      "total_claims": 25,
      "verified_count": 22,
      "unverified_count": 3,
      "contradicted_count": 0,
      "claim_result_count": 25,
      "claim_status_counts": [
        {"value": "verified", "count": 22},
        {"value": "unverified", "count": 3}
      ],
      "first_party_downgrade_count": 1,
      "source_reference_count": 47
    }
  ]
}
```

No verification artifact response:

```json
{
  "error": "verification_summary_not_found",
  "message": "Job job_abc123 has no verification summary artifact available",
  "job_id": "job_abc123",
  "status": "completed",
  "summary_count": 0
}
```

#### primr://output/calibration_summary/by_job/{job_id}

Compact, ownership-gated label-calibration summary for one job. This resource
summarizes attached `.calibration.json` artifacts, plus calibration sidecars
adjacent to owned report artifacts using the standard
`<report filename>.calibration.json` naming convention. It returns per-label
traceability counts, report-only inference source-copy counts, evidence-review
count buckets, judge provenance, and cloud-vs-local judge-agreement metadata
without returning raw claims, source URLs, evidence reviews, rationales, or
report body content.

HTTP callers can read only jobs owned by the authenticated client. Missing jobs
and unowned jobs return the same `job_not_found` shape so clients cannot probe
for other job ids.

```json
{
  "schema_version": "1.0",
  "resource": "primr://output/calibration_summary/by_job",
  "job_id": "job_abc123",
  "status": "completed",
  "company_name": "Acme Corp",
  "summary_count": 1,
  "full_content_included": false,
  "summaries": [
    {
      "index": 0,
      "artifact_type": "calibration_sidecar",
      "file_name": "Acme_Corp_Strategic_Overview_06-28-2026.md.calibration.json",
      "file_path": "output/acme_corp/Acme_Corp_Strategic_Overview_06-28-2026.md.calibration.json",
      "exists": true,
      "size_bytes": 6144,
      "modified_at": "2026-06-28T22:00:00+00:00",
      "content_hash": "sha256:abc123...",
      "parsed": true,
      "full_content_included": false,
      "raw_claims_included": false,
      "claim_text_included": false,
      "source_urls_included": false,
      "evidence_reviews_included": false,
      "rationales_included": false,
      "report_file": "Acme_Corp_Strategic_Overview_06-28-2026.md",
      "max_per_label": 10,
      "judge": {
        "kind": "local",
        "model": "qwen2.5:14b"
      },
      "judge_agreement": {
        "scope": "report",
        "local_model": "qwen2.5:14b",
        "compared": 4,
        "agreed": 3,
        "agreement": 0.75
      },
      "label_count": 2,
      "claim_result_count": 5,
      "claims_sampled": 5,
      "decidable_claims": 3,
      "traceable_count": 2,
      "untraceable_count": 1,
      "no_source_count": 0,
      "unfetchable_count": 0,
      "exempt_count": 1,
      "source_copied_count": 1,
      "per_label": [
        {
          "label": "Confirmed",
          "sampled": 3,
          "traceable": 2,
          "untraceable": 1,
          "no_source": 0,
          "unfetchable": 0,
          "exempt": 0,
          "source_copied": 0,
          "decidable": 3,
          "precision": 0.667
        },
        {
          "label": "Hypothesis",
          "sampled": 2,
          "traceable": 0,
          "untraceable": 0,
          "no_source": 0,
          "unfetchable": 0,
          "exempt": 1,
          "source_copied": 1,
          "decidable": 0,
          "precision": null
        }
      ],
      "validation_rubric": {
        "claims_with_reviews": 3,
        "source_reviews": 5,
        "support_counts": [
          {"value": "supported", "count": 4},
          {"value": "unsupported", "count": 1}
        ],
        "dimension_counts": [
          {
            "dimension": "reasoning_strength",
            "counts": [
              {"value": "strong", "count": 4},
              {"value": "partial", "count": 1}
            ]
          }
        ]
      }
    }
  ]
}
```

No calibration sidecar response:

```json
{
  "error": "calibration_summary_not_found",
  "message": "Job job_abc123 has no calibration sidecar available",
  "job_id": "job_abc123",
  "status": "completed",
  "summary_count": 0
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
  "configured_vendors": ["azure", "aws", "gcp", "private"]
}
```

#### primr://strategies/available

List of available strategy types with metadata for Open Claw integration.

```json
{
  "schema_version": "1.0",
  "cost_warning": "Strategy generation incurs real API charges. Surface the current estimate and get explicit user approval before generate_strategy.",
  "strategies": [
    {
      "id": "ai_strategy",
      "name": "AI Strategy",
      "description": "AI/ML transformation roadmap with quick wins and bigger bets",
      "requires_platform": true,
      "estimated_time_minutes": 15,
      "estimated_cost_usd": 0.30
    },
    {
      "id": "customer_experience",
      "name": "Customer Experience Strategy",
      "description": "CX transformation and digital experience improvement plan",
      "requires_platform": false,
      "estimated_time_minutes": 12,
      "estimated_cost_usd": 0.25
    },
    {
      "id": "modern_security_compliance",
      "name": "Security & Compliance Strategy",
      "description": "Zero Trust architecture and compliance posture assessment",
      "requires_platform": false,
      "estimated_time_minutes": 12,
      "estimated_cost_usd": 0.25
    },
    {
      "id": "data_fabric_strategy",
      "name": "Data Fabric Strategy",
      "description": "Modern data platform for agentic AI and semantic layers",
      "requires_platform": false,
      "estimated_time_minutes": 12,
      "estimated_cost_usd": 0.25
    }
  ]
}
```

#### primr://output/by_job/{job_id}

Job-scoped report preview retrieval for provenance tracking. Ensures the
returned report preview corresponds to a specific approved job. Use
`primr://output/artifacts/by_job/{job_id}` first when a client only needs
artifact metadata and not report text. Use
`primr://output/qa_summary/by_job/{job_id}` first when a client only needs QA
outcome metadata. Use `primr://output/usage_summary/by_job/{job_id}` first
when a client only needs run cost, timing, approval, or artifact-count metadata.
Use `primr://output/source_summary/by_job/{job_id}` first when a client only
needs citation/source appendix metadata.
Use `primr://output/trace_summary/by_job/{job_id}` first when a client only
needs scrape trace health metadata without URLs, raw trace entries, or page
content.
Use `primr://output/verification_summary/by_job/{job_id}` first when a client
only needs claim verification metadata without raw claims, source URLs, search
queries, explanations, or report body content.
Use `primr://output/calibration_summary/by_job/{job_id}` first when a client
only needs label-calibration metadata, including inference source-copy counts,
without raw claims, source URLs, evidence reviews, rationales, or report body
content.

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
- `estimate_strategy`: 30 requests/minute
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
job = store.create(company_name="Acme Corp", mode="full", owner_client_id="client1")

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

## Agentic Architecture (v1.7.0)

Primr v1.7.0 introduces an agentic architecture that enables AI agents to drive research workflows with persistent memory, hypothesis tracking, and governance hooks.

### Research Memory

Track hypotheses across research sessions with confidence levels.

```python
from primr.agentic.memory import ResearchMemory, Hypothesis, ConfidenceLevel
from pathlib import Path

# Initialize memory
memory = ResearchMemory(storage_path=Path("./logs/research_memory"))

# Save a hypothesis
hypothesis = Hypothesis(
    id="h_001",
    company="Acme Corp",
    statement="Acme is expanding into AI-powered logistics",
    confidence=ConfidenceLevel.MEDIUM,
    evidence="CEO mentioned AI initiatives in Q3 earnings call",
    source="https://acme.example/investor-relations",
    topic="strategy",
)
memory.save_hypothesis(hypothesis)

# Retrieve hypotheses
hypotheses = memory.get_hypotheses("Acme Corp")
for h in hypotheses:
    print(f"[{h.confidence.value}] {h.statement}")

# Update confidence as evidence emerges
hypothesis.confidence = ConfidenceLevel.HIGH
hypothesis.evidence += "; Confirmed by press release 2026-01-15"
memory.save_hypothesis(hypothesis)

# List all companies with memory
companies = memory.list_companies()
```

#### Confidence Levels

| Level | Description |
|-------|-------------|
| `LOW` | Initial hypothesis, needs validation |
| `MEDIUM` | Some supporting evidence found |
| `HIGH` | Strong evidence from multiple sources |
| `VALIDATED` | Confirmed through direct sources |

### Roadmap API

Query the development roadmap programmatically.

```python
from primr.agentic.roadmap_api import RoadmapAPI
from primr.agentic.models import VersionStatus

api = RoadmapAPI()

# Get current version
current = api.get_current_version()
print(f"Current: v{current.number} - {current.title}")

# Get next planned version
next_ver = api.get_next_version()

# List versions by status
completed = api.list_by_status(VersionStatus.COMPLETED)
planned = api.list_by_status(VersionStatus.PLANNED)

# Get specific version details
v170 = api.get_version("1.7.0")
for feature in v170.features:
    print(f"  - {feature.name}: {feature.description}")

# Search features
results = api.search_features("memory")
for version, feature in results:
    print(f"v{version.number}: {feature.name}")
```

### Hook System

Register governance hooks for cost control and security.

```python
from primr.agentic.hooks import (
    HookSystem,
    CostGuardHook,
    SSRFGuardHook,
    HookContext,
    HookResult,
)

# Create hook system
hooks = HookSystem()

# Register cost guard (blocks operations exceeding budget)
hooks.register(CostGuardHook(max_cost_usd=5.0))

# Register SSRF guard (blocks internal URLs)
hooks.register(SSRFGuardHook())

# Execute hooks before an operation
context = HookContext(
    operation="scrape",
    target_url="https://acme.example",
    estimated_cost=2.50,
)
result = await hooks.execute_pre_hooks(context)

if result.blocked:
    print(f"Operation blocked: {result.reason}")
else:
    # Proceed with operation
    pass
```

#### Custom Hooks

```python
from primr.agentic.hooks import Hook, HookContext, HookResult

class AuditHook(Hook):
    """Log all operations for audit trail."""
    
    name = "audit"
    
    async def pre_execute(self, context: HookContext) -> HookResult:
        logger.info(f"Operation: {context.operation} on {context.target_url}")
        return HookResult(blocked=False)
    
    async def post_execute(self, context: HookContext, result: Any) -> None:
        logger.info(f"Completed: {context.operation}, success={result.success}")

hooks.register(AuditHook())
```

### Subagent Architecture

Specialized subagents for different research tasks.

```python
from primr.agentic.subagents import (
    ScraperSubagent,
    AnalystSubagent,
    WriterSubagent,
    QASubagent,
)
from primr.agentic.subagents.base import SubagentContext, SubagentResult

# Create subagent
scraper = ScraperSubagent()

# Execute with context
context = SubagentContext(
    company_name="Acme Corp",
    company_url="https://acme.example",
    working_dir=Path("./working/acme"),
)
result: SubagentResult = await scraper.execute(context)

if result.success:
    print(f"Scraped {result.artifacts['page_count']} pages")
else:
    print(f"Failed: {result.error}")
```

#### Available Subagents

| Subagent | Purpose |
|----------|---------|
| `ScraperSubagent` | Website scraping with tier escalation |
| `AnalystSubagent` | Deep research and hypothesis generation |
| `WriterSubagent` | Report generation from research data |
| `QASubagent` | Quality assessment and scoring |

### Research Orchestrator

Coordinate subagents through the research pipeline.

```python
from primr.agentic.orchestrator import (
    ResearchOrchestrator,
    OrchestratorConfig,
    OrchestratorResult,
)
from primr.agentic.memory import ResearchMemory
from primr.agentic.hooks import HookSystem, CostGuardHook

# Configure orchestrator
config = OrchestratorConfig(
    output_dir=Path("./output"),
    fail_fast=False,  # Continue on non-critical failures
)

# Initialize with memory and hooks
memory = ResearchMemory(storage_path=Path("./logs/research_memory"))
hooks = HookSystem()
hooks.register(CostGuardHook(max_cost_usd=10.0))

orchestrator = ResearchOrchestrator(
    config=config,
    memory=memory,
    hook_system=hooks,
)

# Run orchestrated research
result: OrchestratorResult = await orchestrator.research(
    company_name="Acme Corp",
    company_url="https://acme.example",
    mode="full",
)

if result.is_success:
    print(f"Report: {result.report_path}")
    print(f"Hypotheses: {len(result.hypotheses)}")
    print(f"Stages: {result.completed_stages}")
else:
    print(f"Errors: {result.errors}")
```

### MCP Agentic Tools

Additional MCP tools for agentic workflows.

#### query_roadmap

Query roadmap versions and features.

```json
{
  "name": "query_roadmap",
  "arguments": {
    "version": "1.7.0"
  }
}
```

Response:
```json
{
  "version": "1.7.0",
  "status": "completed",
  "title": "Agentic Architecture",
  "features": [
    {"name": "Research Memory", "description": "Persistent hypothesis tracking"},
    {"name": "Hook System", "description": "Governance and cost control"},
    {"name": "Subagent Architecture", "description": "Specialized research agents"}
  ]
}
```

#### get_hypotheses

Retrieve hypotheses for a company from research memory.

```json
{
  "name": "get_hypotheses",
  "arguments": {
    "company": "Acme Corp",
    "min_confidence": "medium"
  }
}
```

Response:
```json
{
  "company": "Acme Corp",
  "hypotheses": [
    {
      "id": "h_001",
      "statement": "Acme is expanding into AI-powered logistics",
      "confidence": "high",
      "evidence": "CEO mentioned AI initiatives in Q3 earnings call",
      "topic": "strategy"
    }
  ],
  "count": 1
}
```

#### save_hypothesis

Save a hypothesis to research memory.

```json
{
  "name": "save_hypothesis",
  "arguments": {
    "company": "Acme Corp",
    "statement": "Acme plans to acquire a logistics startup",
    "confidence": "low",
    "evidence": "Rumored in industry newsletter",
    "topic": "m&a"
  }
}
```

### MCP Agentic Resources

Additional MCP resources for agentic workflows.

#### primr://roadmap

Current roadmap with versions and features.

```json
{
  "current_version": "1.7.0",
  "next_version": "1.8.0",
  "versions": [
    {
      "number": "1.7.0",
      "status": "completed",
      "title": "Agentic Architecture",
      "feature_count": 6
    },
    {
      "number": "1.8.0",
      "status": "planned",
      "title": "QA-Driven Research",
      "feature_count": 4
    }
  ]
}
```

#### primr://memory/{company}

Research memory for a specific company.

```json
{
  "company": "Acme Corp",
  "hypothesis_count": 5,
  "hypotheses": [
    {
      "id": "h_001",
      "statement": "Acme is expanding into AI-powered logistics",
      "confidence": "high",
      "topic": "strategy",
      "created_at": "2026-01-15T10:30:00Z"
    }
  ],
  "confidence_distribution": {
    "low": 1,
    "medium": 2,
    "high": 2,
    "validated": 0
  }
}
```

#### primr://context

CLAUDE.md context map for AI agents.

```json
{
  "quick_start": {
    "research": "primr \"Company\" https://company.com",
    "doctor": "primr doctor",
    "memory": "primr memory \"Company\""
  },
  "architecture": {
    "entry_point": "src/primr/core/cli.py",
    "orchestrator": "src/primr/core/research_orchestrator.py",
    "agentic": "src/primr/agentic/"
  },
  "verification": {
    "tests": "python -m pytest tests/ -v",
    "types": "python -m mypy src/primr/",
    "lint": "python -m ruff check src/primr/"
  }
}
```

### CLI Commands

New CLI commands for agentic workflows:

```bash
# Research memory
primr memory "Acme Corp"              # View hypotheses for a company
primr --memory-list                   # List all companies with memory

# Orchestrated research
primr orchestrate "Acme Corp" https://acme.example
primr --orchestrate --max-cost 5.0    # With cost budget

# Roadmap
primr roadmap                         # Show roadmap overview
primr --roadmap-version v1.7.0        # Show version details
```

### Skills Directory

Pre-built workflow definitions in `skills/`:

| Skill | Description |
|-------|-------------|
| `company-research` | Full pipeline with memory integration |
| `scrape-strategy` | Tier selection and error handling |
| `hypothesis-tracking` | Confidence level management |
| `qa-iteration` | Section refinement workflow |

Each skill includes a `SKILL.md` with workflow steps, decision points, and example usage.
