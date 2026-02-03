# Primr

Primr is a research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

The tool combines first-party website content (site corpus) with validated external sources (deep research) to produce structured company briefs. It is designed for internal use by consultants and researchers who need company intelligence quickly.

This is a working tool, not a polished product. It handles many common cases well but has limitations. See Known Limitations below.

## What It Does

Primr runs company research through a single unified pipeline. Modes control how much of the pipeline runs - they are not separate implementations.

### The Pipeline

```
[Build Site Corpus] -> [Extract Insights] -> [Deep Research] -> [Write Report]
         |                    |                   |                |
    corpus files         insights.txt        dossier.txt      report.docx
```

**Stage outputs:**
- **Build Site Corpus**: `_raw_scrapes/` (individual page text), `scraped_content.txt` (combined corpus), `_external_links.txt` (discovered external URLs; recorded as metadata, not scraped in scrape mode)
- **Extract Insights**: `insights.txt` (LLM-compressed facts from corpus)
- **Deep Research**: `dossier.txt` (LLM analysis using external sources to validate/augment)
- **Write Report**: `report.docx` (final formatted deliverable)

### Modes (same code, different stopping points)

| Mode | What Runs | Time | Cost |
|------|-----------|------|------|
| `--mode scrape` | Build Site Corpus + Extract Insights (multi-page) | 5-10 min | ~$0.01-0.05 |
| `--mode deep` | Deep Research only (external sources; uses provided URL as research anchor; no site corpus build) | 8-15 min | ~$0.80-1.00 |
| `--mode full` | Full pipeline (default) | 25-40 min | ~$0.80-1.50 |

### Key Point

There is ONE site-to-corpus function: `fetch_web_content()` (aka `build_site_corpus`) in `src/primr/data/scrape.py`. It discovers in-scope URLs, selects pages, scrapes them with tier escalation, and saves results incrementally. All modes that build a corpus use this same function. No other function should implement a site discovery + scrape loop.

Scrape mode stops after insights; full mode continues through deep research and report generation. In all modes, the provided URL is the canonical target identifier (used for domain scoping, deduping, and source attribution).

<p align="center">
  <img src="docs/images/primr-demo.png" alt="Primr CLI demo" width="700">
</p>

**Example Output**: See sample reports in [docs/examples/](docs/examples/)

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd primr
python setup_env.py

# Run research
primr "Acme Corp" https://acme.example
```

## MCP Server (AI Agent Integration)

Primr includes a Model Context Protocol (MCP) server that enables AI agents like Claude Desktop to drive company research programmatically.

### Quick Start

```bash
# Run with stdio transport (for Claude Desktop)
primr-mcp --stdio

# Run with HTTP transport
primr-mcp --http --port 8000
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

### Available Tools

| Tool | Description |
|------|-------------|
| `estimate_run` | Get cost/time estimates before running research |
| `research_company` | Start async research job (returns job_id immediately) |
| `generate_strategy` | Generate strategy documents from existing reports |
| `check_jobs` | Check status of research jobs |
| `run_qa` | Run quality assessment on reports |
| `doctor` | Check system health |
| `cancel_job` | Cancel an active research job |
| `clear_jobs` | Clear stale jobs |

### Resources

| Resource | Description |
|----------|-------------|
| `primr://research/status` | Current job status with progress |
| `primr://output/latest` | Most recent research output |
| `primr://output/artifacts` | Pipeline stage artifacts |
| `primr://config` | Current configuration (no secrets) |
| `primr://strategies/available` | Available strategy types with metadata |
| `primr://output/by_job/{job_id}` | Job-scoped artifact retrieval |
| `primr://output/manifest/latest` | Run manifest for audit trail |

### Features

- Async job model with background execution
- JWT authentication for HTTP mode
- Per-tool rate limiting
- Graceful shutdown with job recovery
- Journal persistence for crash recovery

See [docs/API.md](docs/API.md) for full MCP server documentation.

## Open Claw Integration

Primr integrates with [Open Claw](https://openclaw.dev), a local-first agentic AI runtime, enabling autonomous research workflows with approval gates for cost-incurring operations.

### Features

- **Skills**: Pre-built skills for research, strategy generation, and QA
- **Workflows**: Lobster workflow for orchestrated research with approval gates
- **Adapters**: TypeScript adapters for status monitoring
- **Sandbox**: Docker container for secure execution

### Quick Start

```bash
# Copy configuration to Open Claw
cp -r openclaw/* ~/.openclaw/

# Verify installation
primr doctor
```

### Example Workflow

```
User: "Research Acme Corp at https://acme.com"

Agent: Getting estimate...
       Mode: full
       Estimated cost: $0.75
       Estimated time: 30 minutes
       
       Reply "approve ABC123" to proceed.

User: "approve ABC123"

Agent: Research started. Monitoring progress...
       [30 minutes later]
       Research complete. Report saved to output/acme_corp/report.md
```

See [docs/OPENCLAW.md](docs/OPENCLAW.md) for full integration guide.

## Usage

```
primr "<company_label>" <company_website_url> [options]
```

The first argument is a display label used in output paths and headings; scraping scope is determined by the website URL host. The website URL is always required. It defines the research target (canonical domain) and is used for scoping, link discovery, and as a seed for external research.

```bash
# Basic usage
primr "Acme Corp" https://acme.example

# Research modes
primr "Acme Corp" https://acme.example --mode scrape    # Build Site Corpus + Extract Insights (multi-page)
primr "Acme Corp" https://acme.example --mode deep      # Deep research only (no site corpus build)
primr "Acme Corp" https://acme.example --mode full      # Full pipeline (default)

# AI strategy with cloud vendor
primr "Acme Corp" https://acme.example --cloud-vendor azure

# Retry AI strategy (when main report succeeded but AI strategy failed)
primr --ai-strategy-only "output/Acme Corp_Strategic_Overview_01-09-2026.md"
primr --ai-strategy-only "output/report.md" --cloud-vendor aws

# Generate other strategy documents
primr --ai-strategy-only "output/report.md" --strategy-type customer_experience
primr --ai-strategy-only "output/report.md" --strategy-type modern_security_compliance
primr --ai-strategy-only "output/report.md" --strategy-type data_fabric_strategy

# List available strategies
primr --list-strategies

# Options
primr "Acme Corp" https://acme.example --dry-run    # Cost estimate only
primr "Acme Corp" https://acme.example --verbose    # Detailed output
primr "Acme Corp" https://acme.example --no-qa      # Skip quality assessment

# Job management
primr --check-jobs                                  # Check status of pending Deep Research jobs
primr --clear-jobs                                  # Clear stale/old pending jobs

# Batch mode
primr --csv companies.csv

# System check
primr doctor
```

## Configuration

Required API keys in `.env`:
```
GEMINI_API_KEY=       # Google AI API key
SEARCH_API_KEY=       # Google Custom Search API key
SEARCH_ENGINE_ID=     # Google Custom Search Engine ID
```

See [docs/CONFIG.md](docs/CONFIG.md) for full configuration reference.

## Intended Use

Primr outputs are designed for internal research and go-to-market preparation, not as client-ready deliverables. The goal is to help consultants and researchers understand how a company creates value and identify where support could help them move faster.

Reports surface hypotheses to validate in conversation. Strong claims should be treated as working hypotheses unless explicitly supported by cited sources. The tool aims to accelerate research, not replace human judgment.

### Strategy Documents: Research to Enable Conversations

Beyond the standard company brief, Primr can generate optional strategy frameworks to help consultants prepare for discovery conversations:

- **AI Strategy** - Agentic AI transformation, organizational design, investment frameworks
- **Customer Experience Strategy** - CX transformation, journey mapping, experience design
- **Security & Compliance Strategy** - Security transformation, guardrails-first governance, risk frameworks
- **Data Fabric Strategy** - Modern data platform for agentic AI, semantic layers, intelligent estates

These strategy documents are research tools, not finished deliverables. They help consultants show up prepared with frameworks and hypotheses to validate in discovery conversations. Each includes facilitation toolkits (workshop agendas, stakeholder maps, ghostwritten templates) that support co-creation where clients invest effort and own the outcome.

#### Usage

```bash
# List available strategies
primr --list-strategies

# Generate specific strategy from existing report
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type customer_experience
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type modern_security_compliance
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --strategy-type data_fabric_strategy

# AI Strategy (default, or with specific vendor)
primr --ai-strategy-only "output/Company_Strategic_Overview.md" --cloud-vendor azure
```

All strategies use the Strategic Overview as primary context and generate company-specific recommendations grounded in the research findings.

## Security

Primr underwent security review in January 2026. Key protections include:

- XXE protection via secure XML parsing
- SSRF protection via URL validation
- Input validation across user inputs
- Dependency scanning via Bandit and Safety

See [docs/SECURITY_REVIEW_2026-01-21.md](docs/SECURITY_REVIEW_2026-01-21.md) for the security audit report.

## Code Quality

Primr includes infrastructure for reliability and maintainability:

- Typed error hierarchy with automatic retry classification
- Circuit breaker pattern for per-host failure tracking
- OpenTelemetry integration for distributed tracing
- Configuration validation with schema versioning
- State machines for tier escalation and job lifecycle
- Property-based testing (282 tests)
- Unified async/sync boundary handling

See [CONCURRENCY.md](CONCURRENCY.md) for threading model documentation and [docs/STATE_MACHINES.md](docs/STATE_MACHINES.md) for state machine specifications.

## Known Limitations

- Deep Research API produces ~8-12 pages max per call (worked around with Accordion Method)
- Some sites with aggressive WAF block all automated access - use Deep Mode for coverage
- Deep Research connections may drop during long runs - Primr automatically polls for completion
- Vision tier uses LLM API calls for extraction (~$0.01-0.02 per page)

## Understanding Scrape Results

When you see output like `+ 34/46 pages scraped`, this is normal behavior:

- **46** = total pages selected for scraping (homepage + discovered links)
- **34** = pages successfully scraped
- **12 failed** = pages blocked by WAF, timeouts, or anti-bot protection

The tiered scraper tries multiple approaches (HTTP, stealth HTTP, browser, vision) before giving up on a page. Protected sites like enterprise companies often block 20-40% of requests. This is expected - the scraper extracts what it can and moves on.

Quality matters more than quantity. 34 pages from a protected site typically yields more useful content than 100 pages from a poorly-structured site.

## Quality Assessment

Primr automatically runs QA on both generated reports:
- Strategic Overview report
- AI Strategy report (when enabled)

Grades are displayed at the end of each run:
```
Quality: Overview 87 · AI Strategy 89
```

Scores are color-coded: green (85+), yellow (70-84), red (<70).

To run QA manually on existing reports:
```bash
primr --qa "Company Name"                    # QA most recent report for company
primr --qa "output/report.docx"              # QA specific file
primr --qa-recent 5                          # QA summary for last 5 reports
```

Use `--no-qa` to skip automatic quality assessment during generation.

## Job Recovery

Deep Research jobs run asynchronously on Google's servers. If a connection drops mid-research:

1. The job continues running in the background
2. Primr automatically polls for completion (every 2 min for up to 30 min)
3. If polling times out, use `primr --check-jobs` to check status later
4. Completed jobs are automatically saved to `output/recovered_*.txt`

For AI Strategy specifically, use `--ai-strategy-only` to retry with an existing report as context.

## Resource Management

Primr uses Gemini File Search Stores to provide context during Deep Research. These resources are automatically cleaned up after each run, but if a process is interrupted (crash, power loss, etc.), orphaned resources may remain.

To check for and clean up orphaned resources:

```bash
# Check system health including orphaned resources
primr doctor

# Manually inspect Gemini resources
python scripts/check_gemini_resources.py

# Clean up orphaned stores (if any found)
python scripts/check_gemini_resources.py --delete-stores --force-empty
```

The `primr doctor` command will warn you if orphaned resources are detected. Run the cleanup script periodically if you experience interrupted runs.

## Documentation

Full documentation index: [docs/INDEX.md](docs/INDEX.md)

Key documents:
- [CHANGELOG.md](CHANGELOG.md) - Version history and changes
- [ROADMAP.md](ROADMAP.md) - Development roadmap
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture, scraping tiers, resilience features
- [docs/API.md](docs/API.md) - Programmatic usage, MCP server reference
- [docs/CONFIG.md](docs/CONFIG.md) - Configuration reference
- [docs/MIGRATION.md](docs/MIGRATION.md) - Error hierarchy migration guide
- [CONCURRENCY.md](CONCURRENCY.md) - Threading model and async patterns

## License

MIT
