# Primr

**Turn any company URL into a strategic intelligence brief.**

Primr extracts primary-source data from company websites using adaptive scraping that handles modern site architectures, then synthesizes external research into structured briefs using AI-powered research and synthesis (Gemini Deep Research, Grok 4.1, or both).

Runs as a CLI, an MCP server, an OpenClaw integration, and a Claude Skill.

```
primr "ExampleCo" https://example.co
```

Under an hour later: competitive positioning, technology stack, strategic initiatives, and external validation, all cited.

## Why This Exists

Company research is tedious. You visit the website, click around, search the company, read articles, synthesize it all, write it up. That process easily takes 1-2 hours per company and the output is usually unstructured notes.

Primr does that entire workflow autonomously in about an hour for about $6 in API costs. The output is a structured, cited intelligence brief — competitive positioning, technology stack, strategic initiatives, financial profile, and external validation. Whether you're researching a potential employer, evaluating an investment, preparing for a partnership, doing competitive analysis, or running due diligence, a single run replaces hours of manual work.

## What Makes It Different

- **Adaptive scraping**: 8 retrieval methods from browser rendering to TLS fingerprinting to screenshot+vision extraction, with per-host optimization. Starts with full browser rendering (what works on 95%+ of modern sites) and falls back through increasingly specialized methods.
- **Fail-fast scrape quality gate**: Full/scrape modes now abort when site extraction is too thin (override with `--skip-scrape-validation`).
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
| `--fast` | Grok 4.1 with research deepening + cross-validation (requires `XAI_API_KEY`) | ~20 min | $0.50 |
| `--fast` + multi-vendor | Add `--cloud-vendor aws azure` for multiple vendors | 20-28 min | ~$0.55 |
| `--fast --no-ai-strategy` | Grok 4.1 report only, no AI Strategy | ~20 min | $0.45 |

The default `primr` command runs full mode with AI Strategy (Azure vendor). Full mode costs are Gemini API usage: Deep Research is $2.50 per task (one for the brief, one per AI Strategy vendor), plus token costs for Flash/Pro calls. `--lite` swaps the strategy DR task for a Pro model call ($0.15/vendor instead of $2.50). **Cost-sensitive?** Use `--fast` — Grok 4.1 with research deepening and cross-validation produces a high-quality report with AI Strategy in ~20 minutes for about $0.50 (Flash is still used for scraping). Add `--cloud-vendor aws azure` for multi-vendor strategy (~$0.55), or `--no-ai-strategy` for the cheapest option (~$0.45). Web search uses DuckDuckGo (free). Use `--dry-run` for accurate estimates based on your usage history.

`--fast` includes research deepening (gap analysis + targeted search), cross-validation (weak section detection + re-generation), plus trust-polish and citation normalization for high-quality reports at a fraction of full mode cost.

## Versioned Model Evaluation (Quality vs Cost)

When a new model or profile is released (for example, a new Pro/Flash/Grok variant), evaluate it with a repeatable run ID so decisions are data-driven.

### 1) Pick an eval version and fixed corpus

- Example eval ID: `eval-2026-02-r1`
- Use 5-10 representative companies (keep this set stable across model tests)
- Save runs under a dedicated folder per profile:

```bash
primr "ExampleCo A" https://example-a.com --mode full --output-dir output/evals/eval-2026-02-r1/full
primr "ExampleCo A" https://example-a.com --mode full --lite --output-dir output/evals/eval-2026-02-r1/lite
primr "ExampleCo A" https://example-a.com --fast --output-dir output/evals/eval-2026-02-r1/fast
```

Offline comparison (no API spend):

```bash
primr --eval --eval-id eval-2026-02-r1
primr --eval --eval-id eval-2026-02-r1 --eval-company "ExampleCo"
```

By default, `--eval` auto-stages matching existing reports from `output/` into `output/evals/<eval-id>/<profile>/` and writes `staging_manifest.json` for reproducibility.

Optional controlled fill-in for missing profile/company pairs (explicit spend caps required):

```bash
primr --eval --eval-id eval-2026-02-r1 --eval-run-missing --eval-manifest eval_companies.csv --eval-max-new-runs 2 --eval-max-estimated-cost 12
```

### 2) Track the same metrics for every profile

- Trust gate (must-pass): citation coverage + section completeness + confidence-label quality
- Decision utility: actionable recommendations, risks/tradeoffs, and key validation questions
- Reuse quality (human + AI): structured headings, bullets/tables, machine-friendly signal density
- Efficiency: utility-per-dollar and total estimated cost
- Runtime: end-to-end duration per company

These dimensions are aligned to the README goal: helping humans and AI get up to speed quickly and safely, not just producing long reports.

### 3) Use a clear decision rule

Adopt a candidate profile when all are true:

- Trust gate passes for compared reports
- Mean decision-utility score >= 80% of baseline profile
- Mean cost <= 20% of baseline (or your own budget target)
- Utility-per-dollar improves enough to matter operationally

This lets you make explicit tradeoffs such as "80% of quality for 1/10th of cost" with evidence, not intuition.

## Quick Start

```bash
git clone https://github.com/blisspixel/primr.git
cd primr
python setup_env.py              # Installs deps, creates .env
# Add your API keys to .env (see docs/API_KEYS.md)
primr doctor                     # Verify everything works
primr "ExampleCo" https://example.co  # Run your first research
```

Requires Python 3.11+ and a Gemini API key (add `XAI_API_KEY` for `--fast` mode). Web search uses DuckDuckGo (no key needed).

### Platform Support

Primr is designed to run on all three major desktop/server platforms:

- Windows
- macOS
- Linux

Notes:
- Core research/scraping/report generation flows are cross-platform.
- "Open report after run" behavior uses native OS launchers (`startfile` / `open` / `xdg-open` family) with a browser fallback on minimal Linux environments.

```bash
# More usage
primr "Company" https://company.com --mode scrape        # Site corpus only
primr "Company" https://company.com --mode deep          # External research only
primr "Company" https://company.com --dry-run            # Cost estimate first
primr "Company" https://company.com --cloud-vendor aws azure  # Multi-vendor AI strategy
primr "Company" https://company.com --cloud-vendor aws azure --lite  # Cheaper/faster strategy
primr "Company" https://company.com --fast                        # Grok 4.1 fast mode (~$0.50)
primr "Company" https://company.com --fast --cloud-vendor aws azure  # Fast + multi-vendor AI strategy (~$0.55)
primr "Company" https://company.com --skip-scrape-validation      # Continue even if scrape quality is low
primr "Company" https://company.com --resume-local                # Reuse latest incomplete local run folder
primr --resume-latest                                              # Recover completed cloud jobs and finalize MD/DOCX
```

### What a run looks like

```
> PHASE 1 - Data Collection
  Website scraping + web search + AI analysis

[OK] 251 links -> 50 selected
Scraping 23/50 (ok 17) /about  [15s elapsed, ~2m left]
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
  output/ExampleCo_Strategic_Overview_02-11-2026.docx

[OK] AI Strategy Roadmap (AWS)
  output/ExampleCo_AI_Strategy_AWS_02-11-2026.docx

[OK] AI Strategy Roadmap (AZURE)
  output/ExampleCo_AI_Strategy_AZURE_02-11-2026.docx

Mode: Complete (Two-Step)
Chapters: 21
Citations: 34
Duration: 85m
Est. Cost: $8.85
Actual Cost: ~$8.12
AI Strategy: Yes
```

### Crash/Reboot Recovery

Primr now writes per-run state to the working folder as `_run_state.json` (phase, status, timeline events).

If your computer reboots mid-run:

```bash
# 1) Recover completed cloud jobs (Deep Research / AI Strategy)
primr --resume-latest

# 2) Continue local run from latest incomplete working folder for this company
primr "Company Name" https://company.com --resume-local

# 3) Inspect local run state (scrape + phase checkpoints)
type working\\Company_Name\\YYYY-MM-DD_HHMM\\_run_state.json
```

Recovery behavior:
- Deep Research / AI Strategy jobs run in the cloud and can be recovered after reboot.
- `--resume-latest` finalizes recovered outputs to canonical filenames (`.md/.txt/.docx`).
- `--resume-local` reuses the latest incomplete working folder for the same company and skips pages already saved in `_raw_scrapes`.
- Local scrape progress is logged in `_raw_scrapes/_scrape_trace.log` and summarized in `_run_state.json`.

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
Playwright tiers now perform adaptive lazy-load scrolling (up to 20 steps by default, stops early when page height stabilizes).

**Models & Pricing**

| Model | Role | Pricing (per 1M tokens) |
|-------|------|-------------------------|
| Gemini 3 Flash | Scraping, link selection, QA | $0.50 in / $3 out |
| Gemini 3.1 Pro (default) | Section writing, analysis | $2/$12 (≤200k) · $4/$18 (>200k) |
| Gemini 3 Pro | Previous default, flat pricing | $2 in / $12 out |
| Deep Research Agent | Autonomous multi-step research | ~$2.50/task (flat) |
| Grok 4.1 Fast | `--fast` mode reports | $0.20 in / $0.50 out |

Gemini 3.1 Pro is the default — improved thinking, token efficiency, and factual consistency. Tiered pricing only kicks in for prompts over 200k tokens; most Primr calls stay well under. To revert: `AI_REASONING_MODEL=gemini-3-pro-preview`. [Full config reference](docs/CONFIG.md).

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

# Optional - scrape quality gate (fail fast when website extraction is too thin)
# MIN_SCRAPED_PAGES=3
# MIN_SCRAPED_CHARS=6000

# Optional - external search volume caps
# MAX_EXTERNAL_SEARCH_QUERIES=5
# MAX_EXTERNAL_SOURCES=8

# Optional - lazy-load scrolling behavior for scroll-driven sites
# PLAYWRIGHT_LAZY_SCROLL_MAX_STEPS=20
# PLAYWRIGHT_LAZY_SCROLL_PAUSE_MS=250
# PLAYWRIGHT_LAZY_SCROLL_SETTLE_ROUNDS=3
```

Web search uses DuckDuckGo by default - no search API key needed. Google Custom Search is available as an optional fallback for users with existing whole-web CSEs.
If scrape validation blocks a run you intentionally want to continue, pass `--skip-scrape-validation`.
Deep Research background jobs are created with persistent storage enabled, so `primr --check-jobs` can recover completed cloud work after local interruptions. Job checks now distinguish local connectivity issues (`CHECK ERROR`) from provider terminal failures.
For one-shot recovery after crashes/reboots, use `primr --resume-latest` (or `--resume-jobs`) to fetch completed jobs and finalize canonical output filenames automatically.

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
pytest -q tests/test_core/test_resume_recovery.py tests/test_core/test_research_agent_resume.py tests/test_data/test_scrape_resume.py --cov=primr.core.cli --cov=primr.core.research_agent --cov=primr.data.scrape --cov-fail-under=15 --cov-report=term  # Recovery regression gate
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
