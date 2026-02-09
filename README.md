# Primr

**Turn a company URL into a cited, analyst-grade intelligence brief.**

Primr extracts primary-source data from company websites using a multi-tier approach that adapts to different site architectures, then synthesizes external research into structured briefs that can be consumed by humans *or* autonomous agents.

Runs as a CLI, an MCP server, an OpenClaw integration, and a Claude Skill.

```
primr "Acme Corp" https://acme.example
```

30 minutes later: competitive positioning, technology stack, strategic initiatives, and external validation—all cited.

## Why This Exists

Company research is tedious. You visit the website, click around, Google the company, read articles, synthesize it all, write it up. Repeat for every prospect, every deal, every meeting.

Primr does that entire workflow autonomously.

## What Makes It Different

- **Adaptive scraping**: 8 retrieval methods from simple HTTP to browser rendering to screenshot+vision extraction, with per-host optimization. Tries the simplest approach first and falls back to more capable methods as needed.
- **Autonomous external research**: Gemini Deep Research plans queries, follows leads, cross-validates sources, and synthesizes findings into a structured brief.
- **Cost controls built in**: `--dry-run` estimates, usage tracking, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills—all first-class.

Manual research takes hours. Primr typically runs in ~30 minutes and costs ~$1–2 in API usage (varies by depth and site behavior).

## Modes

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| `scrape` | Crawls site, extracts insights | ~5 min | ~$0.10 |
| `deep` | Gemini Deep Research on external sources | ~10 min | ~$1.00 |
| `full` | Both combined into comprehensive brief | ~30 min | ~$1.50 |

Costs are primarily Gemini API usage. Web search is free (DuckDuckGo). Use `--dry-run` for accurate estimates based on your usage history.

## Quick Start

```bash
git clone https://github.com/blisspixel/primr.git
cd primr
python setup_env.py              # Installs deps, creates .env
# Add your API keys to .env (see docs/API_KEYS.md)
primr doctor                     # Verify everything works
primr "Acme Corp" https://acme.example  # Run your first research
```

Requires Python 3.11+ and a Gemini API key. That's it — web search uses DuckDuckGo (no key needed).

```bash
# More usage
primr "Company" https://company.com --mode scrape   # Site corpus only
primr "Company" https://company.com --mode deep     # External research only
primr "Company" https://company.com --dry-run       # Cost estimate first
```

### What a run looks like

```
▸ PHASE 1 · Data Collection
  Website scraping + web search + AI analysis

  Scraping 23/47 /about/leadership (15s)

✓ Data Collection
  Pages scraped: 47
  External sources: 8

▸ PHASE 2 · Analysis
  Processing and synthesizing content

✓ Analysis

▸ PHASE 3 · Deep Research
  Gemini Deep Research running autonomously

✓ Deep Research

▸ PHASE 4 · Report Generation
  Building report sections

  Generating 8/10 Competitive Landscape (12s)

✓ Report Generation
  Sections: 10

✓ Complete in 34m 12s

✓ Report ready
  output/Cirrus_Fleet_Strategic_Overview_01-28-2026.docx

Quality: Overview 91
Cost: $1.45
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

Reports include 10 structured chapters, SWOT analysis, competitive landscape, discovery questions, and inline confidence levels on every non-obvious claim. Full sample: [docs/examples/sample-brief.md](docs/examples/sample-brief.md)

## Batch Research

Have a spreadsheet of companies? Primr can enrich it with website URLs and run research across the list.

**Two-step workflow (recommended):**

```bash
# Step 1: Enrich — auto-detect columns, look up websites, filter by industry, save CSV
primr --batch companies.xlsx --industry Utilities --enrich

# Step 2: Review the enriched CSV, then run research
primr --batch companies_utilities_enriched.csv --mode scrape
```

**Options:**

```bash
--enrich          # Enrich only — look up websites, save CSV, don't research
--industry NAME   # Filter rows by industry column value
--limit N         # Process only the first N companies (useful for testing)
--skip-confirm    # Skip the confirmation prompt (for unattended runs)
--mode MODE       # scrape (~$0.10/co), deep (~$1.00/co), full (~$1.50/co)
```

**Defensive behavior:**

- Shows cost estimate and asks for confirmation before starting (use `--skip-confirm` to bypass)
- **Resume:** re-run the same command to skip companies that already have reports from today
- Cooldown between companies (10s for scrape, 60s for deep/full) to avoid API quota issues
- Progressive retry with backoff on rate-limit errors (immediate → 2 min → 5 min)
- Pauses and asks after 3 consecutive failures — option to wait 10 minutes or stop
- Deduplicates companies by name (case-insensitive)

Accepts Excel (`.xlsx`) or CSV files. Smart column detection uses an LLM to find company name, website, and industry columns automatically.

## Under the Hood

**8-Tier Retrieval Engine** (browser-first for modern JS-heavy sites)
- Browser tiers: Playwright → expanded rendering → DrissionPage (driverless CDP)
- HTTP tiers: curl_cffi → httpx → requests
- Vision tier: Screenshot + LLM extraction for image-heavy or non-standard layouts
- Automatic fallback, per-host optimization, circuit breakers

**Gemini Deep Research**
- Autonomous multi-step search and synthesis
- Plans its own research strategy, follows leads, validates across sources
- Not a wrapper around chat completions—actual agentic research

**Agentic Architecture**
- Hypothesis tracking with confidence levels across sessions
- Subagents for scraping, analysis, writing, and QA
- Hook system for governance (cost limits, quality gates)
- Research memory that persists and evolves

## Configuration

```bash
# Required in .env
GEMINI_API_KEY=       # https://aistudio.google.com/apikey

# Optional — only needed if you want to use Google Custom Search instead of DuckDuckGo
# SEARCH_PROVIDER=google
# SEARCH_API_KEY=     # Google Custom Search API
# SEARCH_ENGINE_ID=   # Programmable Search Engine ID
```

Web search uses DuckDuckGo by default — no search API key needed. Google Custom Search is available as an optional fallback for users with existing whole-web CSEs.

→ [Full setup guide](docs/API_KEYS.md)

## Agent Integration

Primr is built for the agentic era. Three ways to plug it in:

**MCP Server** — Claude Desktop, Cursor, and any MCP-compatible client:
```bash
primr-mcp --stdio              # stdio transport
primr-mcp --http --port 8000   # HTTP with JWT auth
```

<details>
<summary><strong>OpenClaw</strong> — Drop-in integration with skills and workflows</summary>

```bash
# openclaw/openclaw.json already configured
# Skills: primr-research, primr-strategy, primr-qa
# Sandboxed Docker execution included
```
</details>

<details>
<summary><strong>Claude Skills</strong> — Anthropic's Agent Skills format</summary>

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
<summary><strong>Cloud Deployment</strong> — Serverless on AWS, Azure, or GCP</summary>

Scale-to-zero ephemeral containers, event-driven queues, production observability. See [deployment guide](docs/CLOUD_DEPLOYMENT.md).
</details>

→ [MCP docs](docs/API.md) · [OpenClaw config](openclaw/openclaw.json)

## Development

```bash
python -m pytest tests/ -x --tb=short   # Run tests
ruff check src/                          # Lint
mypy src/primr --ignore-missing-imports  # Type check
```

1,500+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, OpenTelemetry tracing, and typed error hierarchy with automatic retry classification.

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

Primr is a nights-and-weekends project by a solo developer. I think AI-assisted research workflows are going to be transformative over the next few years, and this is my way of building deeply in the space — learning by shipping something real.

It's not backed by a company or a team. It's an independent project built for personal use.

## Disclaimer

Primr is a research tool. You are responsible for:

- **Web content**: Primr retrieves publicly available web content, similar to a browser or search engine crawler. It does not bypass authentication, access paywalled content, or exploit vulnerabilities. However, some websites restrict automated access in their terms of service — it is your responsibility to check before running Primr against any site.
- **Accuracy**: AI-generated content may contain errors, hallucinations, or outdated information. Verify findings before acting on them.
- **Costs**: API calls to Gemini and other services incur real charges. Use `--dry-run` to estimate costs before running.
- **Use case**: This tool is intended for legitimate research purposes such as due diligence and meeting preparation. Do not use it to violate any website's terms of service or any applicable law.

This software is provided as-is by a solo developer. The author is not liable for how you use this software, the accuracy of its outputs, or any consequences of its use.

## License

MIT
