# Primr

**Turn any company URL into a strategic intelligence brief.**

Primr extracts primary-source data from company websites using adaptive scraping that handles modern site architectures, then synthesizes external research into structured briefs using AI-powered research and synthesis (Gemini Deep Research, Grok 4.1, or both).

Runs as a CLI, an MCP server, an OpenClaw integration, and a Claude Skill.

```
primr "Acme Corp" https://acme.example
```

Under an hour later: competitive positioning, technology stack, strategic initiatives, and external validation, all cited.

## Why This Exists

Company research is tedious. You visit the website, click around, Google the company, read articles, synthesize it all, write it up. That process easily takes 1-2 hours per company and the output is usually unstructured notes.

Primr does that entire workflow autonomously in about an hour for about $6 in API costs. The output is a structured, cited intelligence brief — competitive positioning, technology stack, strategic initiatives, financial profile, and external validation. Whether you're researching a potential employer, evaluating an investment, preparing for a partnership, doing competitive analysis, or running due diligence, a single run replaces hours of manual work.

## What Makes It Different

- **Adaptive scraping**: 8 retrieval methods from browser rendering to TLS fingerprinting to screenshot+vision extraction, with per-host optimization. Starts with full browser rendering (what works on 95%+ of modern sites) and falls back through increasingly specialized methods.
- **Autonomous external research**: Gemini Deep Research for comprehensive analysis, Grok 4.1 for fast turnaround — both plan queries, follow leads, cross-validate sources, and synthesize findings.
- **Cost controls built in**: `--dry-run` estimates, usage tracking, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills, all first-class.

Manual research takes hours. Primr typically runs in about an hour and costs about $6 in API usage (varies by depth and site complexity). The output is structured, cited, and ready to use.

## Modes

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| `full` | Scrape + Deep Research + AI Strategy (default) | 60-90 min | $6 |
| `full` + multi-vendor | Add `--cloud-vendor aws azure` for multiple vendors | 75-120 min | $6-9 |
| `full` + `--lite` | Pro model instead of DR for AI Strategy | 50-80 min | $4 |
| `full --no-ai-strategy` | Skip AI Strategy, just the research brief | 45-75 min | $3.50 |
| `--mode scrape` | Crawl site + extract insights only | 5-10 min | $0.10 |
| `--mode deep` | Gemini Deep Research on external sources only | 10-15 min | $2.50 |
| `--fast` | Grok 4.1 accordion report (requires `XAI_API_KEY`) | 10-17 min | $0.25 |

The default `primr` command runs full mode with AI Strategy (Azure vendor). Full mode costs are Gemini API usage: Deep Research is $2.50 per task (one for the brief, one per AI Strategy vendor), plus token costs for Flash/Pro calls. `--lite` swaps the strategy DR task for a Pro model call ($0.15/vendor instead of $2.50). `--fast` uses xAI's Grok 4.1 instead — a completely different engine at a fraction of the cost. Web search uses DuckDuckGo (free). Use `--dry-run` for accurate estimates based on your usage history.

## Quick Start

```bash
git clone https://github.com/blisspixel/primr.git
cd primr
python setup_env.py              # Installs deps, creates .env
# Add your API keys to .env (see docs/API_KEYS.md)
primr doctor                     # Verify everything works
primr "Acme Corp" https://acme.example  # Run your first research
```

Requires Python 3.11+ and a Gemini API key (add `XAI_API_KEY` for `--fast` mode). Web search uses DuckDuckGo (no key needed).

```bash
# More usage
primr "Company" https://company.com --mode scrape        # Site corpus only
primr "Company" https://company.com --mode deep          # External research only
primr "Company" https://company.com --dry-run            # Cost estimate first
primr "Company" https://company.com --cloud-vendor aws azure  # Multi-vendor AI strategy
primr "Company" https://company.com --cloud-vendor aws azure --lite  # Cheaper/faster strategy
primr "Company" https://company.com --fast                        # Grok 4.1 fast mode (~$0.25)
```

### What a run looks like

```
> PHASE 1 - Data Collection
  Website scraping + web search + AI analysis

[OK] 251 links -> 50 selected
Scraping 23/50 /about  [15s elapsed, ~2m left]
[OK] 48/50 pages scraped (6m 10s)
+ 3 external sources validated
[OK] Data Collection
  Sections generated: 18

> PHASE 2 - Deep Research
  Comprehensive report with sequential elaboration (50+ pages)

  Searching sources (1m 33s)
  Analyzing findings (3m 48s)
  Generating report (6m 43s)
  Writing: Executive Summary (1/21)...
  Writing: Products and Services (2/21)...
  ...
  Writing: Strategic Positioning Hypothesis (21/21)...

[OK] Deep Research
  Chapters: 21

> PHASE 3 - AI Strategy Roadmap (AWS) Analysis
  Generating AI strategy roadmap recommendations (aws)

[OK] AI Strategy Roadmap (AWS) Analysis

> PHASE 4 - AI Strategy Roadmap (AZURE) Analysis
  Generating AI strategy roadmap recommendations (azure)

[OK] AI Strategy Roadmap (AZURE) Analysis

[OK] Complete in 85m

[OK] Report ready
  output/Acme_Corp_Strategic_Overview_02-11-2026.docx

[OK] AI Strategy Roadmap (AWS)
  output/Acme_Corp_AI_Strategy_AWS_02-11-2026.docx

[OK] AI Strategy Roadmap (AZURE)
  output/Acme_Corp_AI_Strategy_AZURE_02-11-2026.docx

Mode: Complete (Two-Step)
Chapters: 21
Citations: 34
Duration: 85m
Est. Cost: $8.85
Actual Cost: ~$8.12
AI Strategy: Yes
```

### What the output looks like

From the executive summary of a sample report:

> Cirrus Fleet Technologies is a mid-market logistics optimization vendor ($180-220M ARR, estimated) that sells route planning and fleet analytics software to regional shipping companies. The company occupies a defensible but narrowing niche: optimizing last-mile delivery for carriers still running legacy dispatch systems.
>
> **Key insights:**
>
> - Cirrus's customer concentration is high. Cross-referencing case studies, press releases, and conference presentations, roughly 40% of referenced deployments involve just 3 carrier networks. Loss of any one would be material. *[Confidence: Inferred]*
> - The company has no disclosed AI strategy, but 4 of their last 7 engineering hires have ML/optimization backgrounds. Combined with a patent filing for "autonomous route replanning under disruption," this suggests an unannounced product line. *[Confidence: Inferred]*
> - Pricing has shifted from perpetual licenses to consumption-based billing (per-shipment), visible in public procurement portal RFP responses. *[Confidence: Reported]*

Reports include 20+ structured chapters, SWOT analysis, competitive landscape, discovery questions, and inline confidence levels on every non-obvious claim. Full sample: [docs/examples/sample-brief.md](docs/examples/sample-brief.md)

## Batch Research

Have a spreadsheet of companies? Primr can enrich it with website URLs and run research across the list.

**Two-step workflow (recommended):**

```bash
# Step 1: Enrich - auto-detect columns, look up websites, filter by industry, save CSV
primr --batch companies.xlsx --industry Utilities --enrich

# Step 2: Review the enriched CSV, then run research
primr --batch companies_utilities_enriched.csv --mode scrape
```

**Options:**

```bash
--enrich          # Enrich only - look up websites, save CSV, don't research
--industry NAME   # Filter rows by industry column value
--limit N         # Process only the first N companies (useful for testing)
--skip-confirm    # Skip the confirmation prompt (for unattended runs)
--mode MODE       # scrape ($0.10/co), deep ($2.50/co), full ($6/co)
```

**Defensive behavior:**

- Shows cost estimate and asks for confirmation before starting (use `--skip-confirm` to bypass)
- **Resume:** re-run the same command to skip companies that already have reports from today
- Cooldown between companies (10s for scrape, 60s for deep/full) to avoid API quota issues
- Progressive retry with backoff on rate-limit errors (immediate -> 2 min -> 5 min)
- Pauses and asks after 3 consecutive failures - option to wait 10 minutes or stop
- Deduplicates companies by name (case-insensitive)

Accepts Excel (`.xlsx`) or CSV files. Smart column detection uses an LLM to find company name, website, and industry columns automatically.

## Under the Hood

**8-Tier Retrieval Engine** (browser-first, falls back automatically)
1. Playwright (JS rendering)
2. Playwright Aggressive (accordions, lazy load)
3. curl_cffi (TLS fingerprint impersonation)
4. DrissionPage Stealth (challenge waiting)
5. DrissionPage (driverless CDP)
6. Vision (screenshot + LLM extraction)
7. httpx (HTTP/2)
8. requests (simple fallback)

Includes sticky tier memory, circuit breakers, cookie handoff, and automatic PDF detection.

**AI Research Engines**
- **Gemini Deep Research**: Autonomous multi-step search and synthesis — plans its own research strategy, follows leads, validates across sources. Not a wrapper around chat completions; actual agentic research.
- **Grok 4.1 Fast Mode**: Accordion-style batch writing — analysis workbook + 5-batch report generation in 10-17 minutes for $0.25.

**Agentic Architecture**
- Hypothesis tracking with confidence levels across sessions
- Subagents for scraping, analysis, writing, and QA
- Hook system for governance (cost limits, quality gates)
- Research memory that persists and evolves

## Configuration

```bash
# Required in .env
GEMINI_API_KEY=       # https://aistudio.google.com/apikey

# Optional - for --fast mode (Grok 4.1)
# XAI_API_KEY=        # https://console.x.ai/

# Optional - only needed if you want to use Google Custom Search instead of DuckDuckGo
# SEARCH_PROVIDER=google
# SEARCH_API_KEY=     # Google Custom Search API
# SEARCH_ENGINE_ID=   # Programmable Search Engine ID
```

Web search uses DuckDuckGo by default - no search API key needed. Google Custom Search is available as an optional fallback for users with existing whole-web CSEs.

[Full setup guide](docs/API_KEYS.md)

## Agent Integration

Primr is built for the agentic era. Three ways to plug it in:

**MCP Server** - Claude Desktop, Cursor, and any MCP-compatible client:
```bash
primr-mcp --stdio              # stdio transport
primr-mcp --http --port 8000   # HTTP with JWT auth
```

<details>
<summary><strong>OpenClaw</strong> - Drop-in integration with skills and workflows</summary>

```bash
# openclaw/openclaw.json already configured
# Skills: primr-research, primr-strategy, primr-qa
# Sandboxed Docker execution included
```
</details>

<details>
<summary><strong>Claude Skills</strong> - Anthropic's Agent Skills format</summary>

```
skills/
├── company-research/SKILL.md   # Full pipeline with memory
├── hypothesis-tracking/SKILL.md # Confidence management
├── qa-iteration/SKILL.md       # Section refinement
└── scrape-strategy/SKILL.md    # Tier selection heuristics
```

Skills include hypothesis persistence, cost governance hooks, and QA gates. Agents can pick up where they left off across sessions.
</details>

<details>
<summary><strong>Cloud Deployment</strong> - Serverless on AWS, Azure, or GCP</summary>

Scale-to-zero ephemeral containers, event-driven queues, production observability. See [deployment guide](docs/CLOUD_DEPLOYMENT.md).
</details>

[MCP docs](docs/API.md) | [OpenClaw config](openclaw/openclaw.json)

## Development

```bash
python -m pytest tests/ -x --tb=short   # Run tests
ruff check src/                          # Lint
mypy src/primr --ignore-missing-imports  # Type check
```

4,400+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, OpenTelemetry tracing, and typed error hierarchy with automatic retry classification. CI runs lint, type check, and tests on every push via GitHub Actions.

Recent hardening includes shared deep-research parsing/polling/execution modules, a shared AI error policy module across sync/async clients, and reduced noisy integration-runtime warnings for constrained Playwright/network test environments.

## Documentation

| Doc | What's in it |
|-----|--------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, scraping tiers |
| [API.md](docs/API.md) | MCP server, programmatic usage |
| [CONFIG.md](docs/CONFIG.md) | Full configuration reference |
| [API_KEYS.md](docs/API_KEYS.md) | API key setup |
| [CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) | Serverless deployment |
| [SECURITY_OPS.md](docs/SECURITY_OPS.md) | Security operations guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [ROADMAP.md](ROADMAP.md) | What's planned |

## About This Project

Primr is a nights-and-weekends project by a solo developer. I kept finding myself spending hours researching companies — clicking around websites, reading articles, trying to piece together what a company actually does and where it's headed. The time-to-insight ratio was terrible, and most of the work was mechanical. That's exactly what AI should be doing.

So I built the tool I wanted: drop in a URL, get back a structured brief. It costs a few dollars in API fees and saves hours per company. Whether you're evaluating a potential employer, researching an investment, preparing for a partnership conversation, or just curious about a company, it gets you up to speed fast.

It's not backed by a company or a team. It's an independent project built for personal use.

## Disclaimer

Primr is a research tool. You are responsible for:

- **Web content**: Primr retrieves publicly available web content, similar to a browser or search engine crawler. It does not bypass authentication, access paywalled content, or exploit vulnerabilities. However, some websites restrict automated access in their terms of service - it is your responsibility to check before running Primr against any site.
- **Accuracy**: AI-generated content may contain errors, hallucinations, or outdated information. Verify findings before acting on them.
- **Costs**: API calls to AI services (Gemini, Grok) incur real charges. Use `--dry-run` to estimate costs before running.
- **Use case**: This tool is intended for legitimate research purposes. Do not use it to violate any website's terms of service or any applicable law.

This software is provided as-is by a solo developer. The author is not liable for how you use this software, the accuracy of its outputs, or any consequences of its use.

## License

MIT
