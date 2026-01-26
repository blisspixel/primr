# Primr

Primr is a research tool that generates company intelligence briefs using Google's Gemini models. It automates the collection and analysis of company information for internal research and go-to-market preparation.

The tool combines first-party website content (site corpus) with validated external sources (deep research) to produce structured company briefs. Primr is designed for internal use by consultants and researchers who need comprehensive company intelligence quickly.

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

Primr has undergone comprehensive security review (January 2026) with all critical vulnerabilities addressed:

- **XXE Protection**: Secure XML parser prevents XML External Entity attacks
- **SSRF Protection**: URL validation blocks internal/private IP access and DNS rebinding
- **Input Validation**: Comprehensive validation across all user inputs
- **Secure Dependencies**: Core dependencies verified clean via automated scanning

See [docs/SECURITY_REVIEW_2026-01-21.md](docs/SECURITY_REVIEW_2026-01-21.md) for complete security audit report.

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

## Documentation

- [CHANGELOG.md](CHANGELOG.md) - Version history and changes
- [ROADMAP.md](ROADMAP.md) - Development roadmap
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture, scraping tiers, resilience features
- [docs/API.md](docs/API.md) - Programmatic usage
- [docs/CONFIG.md](docs/CONFIG.md) - Configuration reference
- [docs/INTERNALS.md](docs/INTERNALS.md) - Prompt engineering and algorithms

## License

MIT
