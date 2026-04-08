# Primr

[![CI](https://github.com/blisspixel/primr/actions/workflows/ci.yml/badge.svg)](https://github.com/blisspixel/primr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

**Turn any company or organization URL into deep strategic analysis that gets a consultant maximally up to speed.**

Primr extracts primary-source data from company and organization websites using adaptive, org-aware scraping that handles modern site architectures, then synthesizes external research into long-form strategic analysis using AI-powered research and synthesis (Grok 4.1 by default, or Gemini Deep Research via `--premium`).

Runs as a CLI, an MCP server, an OpenClaw integration, and a Claude Skill.

```
primr "ExampleCo" https://example.co
```

About 35-50 minutes later: a deep strategic analysis covering competitive positioning, technology stack, strategic initiatives, likely constraints, and consultant-grade hypotheses, with dense references consolidated at the end. ~$0.55 in API costs.

## Why This Exists

Company research is tedious. You visit the website, click around, search the company, read articles, synthesize it all, write it up. That process easily takes 1-2 hours per company and the output is usually unstructured notes.

Primr does that entire workflow autonomously in about 35-50 minutes for about $0.55 in API costs. The output is deep, structured strategic analysis, competitive positioning, technology stack, strategic initiatives, financial profile, external validation, and a consultant-ready view of what matters most to validate in conversation. Whether you're researching a potential employer, evaluating an investment, preparing for a partnership, doing competitive analysis, or running due diligence, a single run replaces hours of manual work.

## What Makes It Different

- **Adaptive scraping**: 8 retrieval methods from browser rendering to TLS fingerprinting to screenshot+vision extraction, with per-host optimization. Starts with full browser rendering (what works on 95%+ of modern sites) and falls back through increasingly specialized methods.
- **Org-aware site selection**: Link discovery and prioritization now adapt for commercial companies, government sites, nonprofits, education, and healthcare organizations instead of assuming every site looks like a SaaS company.
- **Fail-fast scrape quality gate**: Full/scrape modes now abort when site extraction is too thin, while still preserving short structured pages like contact, leadership, and org-chart references when they carry useful signal (override with `--skip-scrape-validation`).
- **Autonomous external research**: Gemini Deep Research for comprehensive analysis, Grok 4.1 for fast turnaround — both plan queries, follow leads, cross-validate sources, and synthesize findings.
- **Cost controls built in**: `--dry-run` estimates (including recovery table and stage classifications), usage tracking, and governance hooks for budget limits.
- **Agent-native interfaces**: CLI, MCP server, OpenClaw integration, and Claude Skills, all first-class.

Manual research takes hours. Primr typically runs in about 35-50 minutes and costs about $0.55 in API usage (varies by depth and site complexity). The output is long-form, strategically interpretive, cited where it matters, and readable enough to use before a real client conversation.

## Modes

| Mode | What it does | Time | Cost |
|------|--------------|------|------|
| Default | Grok 4.20 hybrid: 4.20 reasoning + 4.1 writing + AI Strategy | ~35-50 min | ~$0.67 |
| Default + multi-vendor | Add `--cloud-vendor aws azure` | ~45-60 min | ~$0.80 |
| Default + strategy type | Add `--strategy-type customer_experience` | ~35-50 min | ~$0.75 |
| `--grok-tier fast` | Grok 4.1 everywhere (cheaper, slightly lower quality) | ~30-45 min | ~$0.47 |
| `--grok-tier max` | Grok 4.20 everywhere (diminishing returns on writing) | ~35-50 min | ~$4.29 |
| `--premium` | Gemini + Deep Research + AI Strategy | 50-75 min | ~$5 |
| `--premium` + multi-vendor | Add `--cloud-vendor aws azure` | 75-120 min | $6-9 |
| `--premium --lite` | Pro model instead of DR for AI Strategy | 50-80 min | ~$4 |
| `--mode scrape` | Crawl site + extract insights only | 5-10 min | $0.10 |
| `--mode deep` | Gemini Deep Research on external sources only | 10-15 min | $2.50 |

The default `primr` command auto-detects: when `XAI_API_KEY` is set, it uses the Grok 4.20 hybrid pipeline (4.20 for reasoning-heavy stages like gap analysis, workbook, and cross-validation; 4.1 for bulk writing). This delivers near-premium analytical quality at ~$0.67/run. Use `--grok-tier fast` for cheaper runs at slightly lower quality, or `--premium` for the Gemini + Deep Research pipeline for maximum depth.

Naming note: historical references to "fast mode" in logs/code refer to this standard Grok pipeline. A separate true quick mode target (under 5 minutes) is planned as a future profile.

**Strategy types** (use `primr --list-strategies` for details): `ai` (default), `customer_experience`, `modern_security_compliance`, `data_fabric_strategy`. Strategy types are defined by YAML configs in `src/primr/prompts/strategies/` and auto-discovered at runtime.

The standard Grok pipeline includes research deepening (gap analysis + targeted search), cross-validation (weak section detection + re-generation), trust-polish, citation normalization, and constrained-evidence reasoning for sparse-company sections. Strategy documents get the same treatment plus pre-ship artifact repair when budgets, citations, or source inventories conflict. Dense references are kept primarily in the final Sources appendix so the narrative stays readable. Produces reports with 40-55 sources. DDG searches are free. Use `--dry-run` for accurate estimates based on your usage history.

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

Optional LLM-judge overlays on staged reports:

```bash
# Cloud judge (requires spend cap)
primr --eval --eval-id eval-2026-02-r1 --eval-llm-judge --eval-judge-provider grok --eval-judge-model grok-4-1-fast-reasoning --eval-judge-max-cost 0.25

# Local judge against an Ollama/OpenAI-compatible endpoint
primr --eval --eval-id eval-2026-03-local --eval-llm-judge --eval-judge-provider local --eval-judge-model qwen3:30b --eval-judge-base-url http://localhost:11434/v1

# Local multi-model sweep on the same staged company/profile pairs
primr --eval --eval-id eval-2026-03-local-sweep --eval-llm-judge --eval-judge-provider local --eval-judge-models qwen3:30b qwen2.5-coder:32b-instruct-q5_K_M qwen2.5:14b --eval-judge-base-url http://localhost:11434/v1

# Local sweep from a maintained named shortlist
primr --eval --eval-id eval-2026-03-local-sweep --eval-llm-judge --eval-judge-provider local --eval-judge-model-list 4090-top10 --eval-judge-base-url http://localhost:11434/v1
```

Local judge runs now evaluate every staged non-baseline profile against the chosen baseline, not just the first available profile. They write one JSON artifact per model plus `local_judge_summary.json` / `local_judge_summary.md` with candidate-profile coverage, winner consensus, and per-profile breakdowns for side-by-side comparison.

This is useful for evaluating local models against existing cloud-generated reports before routing any production pipeline stages to local inference. It is still a judge-based acceptance layer, not proof that a local model is ready to replace report-writing or deep-research stages directly.

### 2) Track the same metrics for every profile

- Trust gate (must-pass): citation coverage + section completeness + confidence-label quality
- Decision utility: actionable recommendations, risks/tradeoffs, key validation questions, and depth of strategic interpretation
- Reuse quality (human + AI): structured headings, tables, machine-friendly signal density, and readable appendix-style sourcing
- Efficiency: utility-per-dollar and total estimated cost
- Runtime: end-to-end duration per company

These dimensions are aligned to the README goal: producing deep strategic analysis that gets humans and AI up to speed quickly and safely, not just producing long reports.

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

Requires Python 3.11+. Set `XAI_API_KEY` for the standard Grok pipeline (recommended), or `GEMINI_API_KEY` for Gemini/premium mode. Web search uses DuckDuckGo (no key needed).

### Platform Support

Primr is designed to run on all three major desktop/server platforms:

- Windows
- macOS
- Linux

Notes:
- Core research/scraping/report generation flows are cross-platform.
- On Windows, prefer keeping the repo outside OneDrive/Dropbox/iCloud-synced folders. Primr writes checkpoint state into `working/`, and sync/AV tools can transiently lock atomic renames.
- "Open report after run" behavior uses native OS launchers (`startfile` / `open` / `xdg-open` family) with a browser fallback on minimal Linux environments.

```bash
# More usage
primr "Company" https://company.com --mode scrape        # Site corpus only
primr "Company" https://company.com --mode deep          # External research only
primr "Company" https://company.com --dry-run            # Cost estimate first
primr "Company" https://company.com --cloud-vendor aws azure  # Multi-vendor AI strategy
primr "Company" https://company.com --cloud-vendor azure private  # Azure + private cloud/NVIDIA
primr "Company" https://company.com --strategy-type customer_experience  # CX strategy document
primr "Company" https://company.com --strategy-type data_fabric_strategy # Data fabric strategy
primr --list-strategies                                                  # See all strategy types
primr "Company" https://company.com --premium            # Gemini + Deep Research (~$5)
primr "Company" https://company.com --premium --cloud-vendor aws azure  # Premium + multi-vendor
primr "Company" https://company.com --premium --lite     # Cheaper premium strategy
primr "Company" https://company.com --skip-scrape-validation      # Continue even if scrape quality is low
primr "Company" https://company.com --resume-local                # Reuse latest incomplete local run folder
primr --resume-latest                                              # Recover completed cloud jobs and finalize MD/DOCX
primr --ai-strategy-only "output/Company_Strategic_Overview_03-06-2026.md" --cloud-vendor aws  # Reuse an existing report to generate only a missing strategy
primr --improve "output/Company_Strategic_Overview_03-06-2026.md"          # Improve an existing output file
primr improve "output/Company_AI_Strategy_AZURE_03-06-2026.md" --improve-agentic  # Agentic+deterministic post-pass
primr --banner                                                           # Show startup banner only
```

### What a run looks like

```
Using Grok 4.1 · for deeper research add --premium

▸ PHASE 1/6 · Data Collection (fast)
  Scraping example.co + external sources

✓ 251 links → 50 selected
Scraping 23/50 (ok 17) /about  [15s elapsed, ~2m left]
✓ 48/50 pages scraped (6m 10s)
Searching external sources (15/15 queries, 42 results)
Validating external sources (38 validated, checking 42/42)
✓ Searching external sources (8m 22s)
Quality filter: 38 → 31 sources (dropped 7 low-relevance)
✓ Data Collection (fast)
  Pages: 48  External: 31

▸ PHASE 2/6 · Research Deepening
  Identifying gaps and searching for additional evidence

✓ Gap analysis: 8 questions identified
✓ Found 12 additional sources

▸ PHASE 3/6 · Analysis (Grok)
  Building structured workbook from enriched data

✓ Analysis (Grok)

▸ PHASE 4/6 · Report Writing (Grok)
  Writing sections (parallel within parts)

Part 1/5 (Foundation): 7 section(s) in parallel
  ✓ Executive Summary (1,142 words)
  ...
Part 2/5 (Industry): 3 section(s) in parallel
  ✓ Industry Dynamics (970 words)
  ✓ Industry Outlook (1,050 words)
  ✓ Competitive Landscape (1,118 words)
Part 4/5 (Deep Insights): 7 section(s) in parallel
  ✓ Strategic Leadership Perspective (1,200 words)
  ...
✓ Report Writing (Grok)
  Sections: 23  Words: 21,500

Narrative style: deep strategic analysis, compact in-body citations, dense references in final Sources appendix

▸ PHASE 5/6 · Cross-Validation
  Reviewing report for gaps and weak sections

✓ Resolved 3 contradiction(s)
✓ Cross-Validation

Fast QA: labels=310, cites=12/12, validate=23/23, gate=PASS
Trust Summary: report=PASS cites=12/12 appendix=clean reasoning=deep

✓ Complete in 35m

✓ Report ready
  output/ExampleCo_Strategic_Overview_03-03-2026.docx

Artifact Gate: PASS
Mode: Standard (Grok 4.1)
Chapters: 23
Citations: 48
Duration: 35m
Est. Cost: $0.60
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
- `--resume-local` reuses the latest incomplete working folder for the same company and skips pages already saved in `_raw_scrapes` (same run folder is reused for standard/Grok mode).
- Local scrape progress is logged in `_raw_scrapes/_scrape_trace.log` and summarized in `_run_state.json`.


### Improve Existing Outputs

Use `primr improve` (or `--improve`) to run a post-generation quality pass on existing `.md` / `.txt` outputs.

```bash
# Deterministic cleanup + QA metrics
primr improve "output/Company_Strategic_Overview_03-06-2026.md"

# Add an agentic review pass first (find weak sections, then tighten)
primr improve "output/Company_AI_Strategy_AZURE_03-06-2026.md" --improve-agentic

# Overwrite the original file instead of writing *_improved
primr improve "output/Company_Strategic_Overview_03-06-2026.md" --in-place
```

What this does:
- Removes internal placeholder/source artifacts that should not ship (`Analysis Context`, `vendor-research`, `citation inventory`, etc.)
- Normalizes and validates citations for reports
- Applies strategy consistency checks (including budget-total mismatch detection)
- Runs a deterministic salvage pass before blocking output, so recoverable markdown issues are auto-cleaned
- Applies an artifact shipping gate before DOCX render and validates the rendered DOCX text afterward
- Holds back dirty DOCX files but still saves `.md` / `.txt` plus a validation sidecar when issues remain
- Prints deterministic QA summary (`gate=PASS|WARN`) before writing output

### Startup Banner

Primr now shows a short startup banner by default in interactive terminals. It is skipped automatically in non-interactive/CI contexts and when `NO_COLOR` disables styling.

```bash
# Show banner only, then exit
primr --banner

# Choose mode explicitly
primr --banner static
primr --banner animated

# Disable once
primr --no-banner

# Disable globally (env)
set PRIMR_NO_BANNER=1
```

Env controls:
- `PRIMR_BANNER=auto|off|static|animated`
- `PRIMR_NO_BANNER=1`
- `PRIMR_BANNER_DURATION_MS=250..3000` (animated mode)

### What the output looks like

From the executive summary of a sample report:

> Northwind Haulage Corp is a mid-market logistics optimization vendor ($180-220M ARR, estimated) that sells route planning and fleet analytics software to regional shipping companies. The company occupies a defensible but narrowing niche: optimizing last-mile delivery for carriers still running legacy dispatch systems.
>
> **Key insights:**
>
> - Northwind's customer concentration is high. Cross-referencing case studies, press releases, and conference presentations, roughly 40% of referenced deployments involve just 3 carrier networks. Loss of any one would be material. *[Confidence: Inferred]*
> - The company has no disclosed AI strategy, but 4 of their last 7 engineering hires have ML/optimization backgrounds. Combined with a patent filing for "autonomous route replanning under disruption," this suggests an unannounced product line. *[Confidence: Inferred]*
> - Pricing has shifted from perpetual licenses to consumption-based billing (per-shipment), visible in public procurement portal RFP responses. *[Confidence: Reported]*

Reports include 23 structured sections, SWOT analysis, competitive landscape, discovery questions, and inline confidence levels on every non-obvious claim.

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
--mode MODE       # scrape ($0.10/co), deep ($2.50/co), full (~$0.55/co or ~$5/co with --premium)
--grok-tier TIER  # fast (~$0.55), hybrid (~$1.10, 4.20 reasoning), max (~$4, 4.20 everywhere)
```

**Defensive behavior:**

- Shows cost estimate and asks for confirmation before starting (use `--skip-confirm` to bypass)
- **Resume:** re-run the same command to skip companies that already have reports from today
- Cooldown between companies (10s for scrape, 60s for deep/full) to avoid API quota issues
- Exponential retry with jitter on transient API failures (429, 5xx, service unavailable, timeouts)
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
| Grok 4.1 | Default mode: analysis, writing, strategy | $0.20 in / $0.50 out |
| Grok 4.20 | `--grok-tier hybrid/max`: reasoning and/or writing | $2.00 in / $6.00 out |
| Gemini 3 Flash | Scraping, link selection, QA | $0.50 in / $3 out |
| Gemini 3.1 Pro | `--premium` mode: section writing, analysis | $2/$12 (≤200k) · $4/$18 (>200k) |
| Deep Research Agent | `--premium` mode: autonomous research | ~$2.50/task (flat) |

**Why Grok 4.1 is the default:** Primr originally ran everything through Google's Deep Research API + Gemini 3.1 Pro — excellent research quality, but the Deep Research API runs ~$2.50 per task, pushing full runs to ~$5 and 50-75 minutes. When xAI released Grok 4.1, testing showed it handles company research comparably: strong at search-grounded analysis, solid structured output, and reliable citation handling. Switching the default pipeline to Grok 4.1 dropped costs to ~$0.55 (~90% cheaper) and runtime to ~35-50 minutes with similar report quality. Gemini Flash is still used for scraping in both modes. The full Gemini + Deep Research pipeline remains available via `--premium` when maximum research depth justifies the cost. [Full config reference](docs/CONFIG.md).

**Agentic Architecture**
- Hypothesis tracking with confidence levels across sessions
- Subagents for scraping, analysis, writing, and QA
- Hook system for governance (cost limits, quality gates)
- Research memory that persists and evolves

## Configuration

```bash
# Recommended - for default Grok 4.1 pipeline
XAI_API_KEY=          # https://console.x.ai/

# Required for --premium mode or if XAI_API_KEY not set
GEMINI_API_KEY=       # https://aistudio.google.com/apikey

# Optional - only needed if you want to use Google Custom Search instead of DuckDuckGo
# SEARCH_PROVIDER=google
# SEARCH_API_KEY=     # Google Custom Search API
# SEARCH_ENGINE_ID=   # Programmable Search Engine ID

# Optional - local/OpenAI-compatible eval judge backend (for Ollama, LAN-hosted servers, etc.)
# LOCAL_LLM_BASE_URL=http://localhost:11434/v1
# LOCAL_LLM_API_KEY=
# OLLAMA_BASE_URL=http://localhost:11434
# Local judge model lists live in src/primr/config/local_eval_models.py
# Built-in lists today: 4090-top10, installed-starter

# Optional - scrape quality gate (fail fast when website extraction is too thin)
# MIN_SCRAPED_PAGES=3
# MIN_SCRAPED_CHARS=6000
# SCRAPE_PILOT_COUNT=10
# SCRAPE_PILOT_MIN_SUCCESS_RATE=0.70
# SCRAPE_PILOT_MIN_CHARS=700

# Optional - external search volume caps
# MAX_EXTERNAL_SEARCH_QUERIES=5
# MAX_EXTERNAL_SOURCES=8

# Optional - lazy-load scrolling behavior for scroll-driven sites
# PLAYWRIGHT_LAZY_SCROLL_MAX_STEPS=20
# PLAYWRIGHT_LAZY_SCROLL_PAUSE_MS=250
# PLAYWRIGHT_LAZY_SCROLL_SETTLE_ROUNDS=3
```

Web search uses DuckDuckGo by default - no search API key needed. Google Custom Search is available as an optional fallback for users with existing whole-web CSEs.
When `XAI_API_KEY` is set, Primr automatically uses the standard Grok hybrid pipeline by default: Grok 4.20 for reasoning-heavy stages and Grok 4.1 for bulk writing. Use `--grok-tier fast` for 4.1 everywhere, or `--premium` to force Gemini + Deep Research.
If scrape validation blocks a run you intentionally want to continue, pass `--skip-scrape-validation` or lower `SCRAPE_PILOT_MIN_CHARS` (default `700`) for terse websites. Primr now constrains LLM link selection to the discovered URL set, filters obvious non-content URLs like favicons/manifests/search endpoints, and preserves short structured pages when they carry useful signal. Strategy outputs also add a deterministic `## Sources` appendix when the model does not emit explicit source URLs on its own.
Deep Research background jobs are created with persistent storage enabled, so `primr --check-jobs` can recover completed cloud work after local interruptions. Job checks now distinguish local connectivity issues (`CHECK ERROR`) from provider terminal failures.
For one-shot recovery after crashes/reboots, use `primr --resume-latest` (or `--resume-jobs`) to fetch completed jobs and finalize canonical output filenames automatically.

[Full setup guide](docs/API_KEYS.md)

## Agent Integration

Primr is built for the agentic era. Four ways to plug it in:

**MCP Server** - Claude Desktop, Cursor, and any MCP-compatible client:
```bash
primr-mcp --stdio              # stdio transport
primr-mcp --http --port 8000   # HTTP with JWT auth
```

**A2A Protocol** - Agent-to-Agent communication with any A2A-compatible agent:
```bash
pip install primr[a2a]                     # install optional A2A support
primr-a2a --no-auth                        # standalone A2A server on port 9000
primr-mcp --http --a2a                     # co-hosted with MCP server
curl localhost:9000/.well-known/agent.json  # discover agent capabilities
```

<details>
<summary><strong>OpenClaw</strong> - Packaged skills, governed workflows, and sandbox config</summary>

```bash
# openclaw/openclaw.json wires Primr MCP into OpenClaw
# Skills: primr-research, primr-strategy, primr-qa
# Workflows: research-pipeline, strategy-pipeline
```

The packaged workflows estimate cost, require approval, and propagate approved cost caps into spend calls.
See `docs/OPENCLAW.md` for setup and troubleshooting.
</details>

<details>
<summary><strong>Claude Skills</strong> - MCP-first skill packages</summary>

```text
skills/
├── company-research/SKILL.md
├── hypothesis-tracking/SKILL.md
├── qa-iteration/SKILL.md
└── scrape-strategy/SKILL.md
```

These skills are thin intent routers over Primr MCP rather than separate product definitions. Generic MCP clients can also use `primr://agent/governance`, `primr://research/next-actions`, and the `governed_execution` prompt to follow the same estimate/approval/monitor pattern.
</details>

<details>
<summary><strong>Cloud Deployment</strong> - Serverless on AWS, Azure, or GCP</summary>

Scale-to-zero ephemeral containers, event-driven queues, production observability. See [deployment guide](docs/CLOUD_DEPLOYMENT.md).
</details>

[MCP docs](docs/API.md) | [A2A protocol](https://github.com/a2aproject/a2a-python) | [OpenClaw config](openclaw/openclaw.json) | [OpenClaw guide](docs/OPENCLAW.md)

## Development

```bash
python -m pytest tests/ -x --tb=short                    # Run tests
python -m pytest tests/a2a/ -v --tb=short                # A2A tests only (requires pip install .[a2a])
pytest -q tests/test_core/test_resume_recovery.py tests/test_core/test_research_agent_resume.py tests/test_data/test_scrape_resume.py --cov=primr.core.cli --cov=primr.core.research_agent --cov=primr.data.scrape --cov-fail-under=13 --cov-report=term  # Recovery regression gate
ruff check .                                              # Lint (full repo)
mypy src/primr --ignore-missing-imports                  # Type check
```

4,500+ tests including property-based testing (Hypothesis), full ruff and mypy compliance, OpenTelemetry tracing, and typed error hierarchy with automatic retry classification. CI runs lint, type check, and tests on every push via GitHub Actions.

Recent hardening includes shared deep-research parsing/polling/execution modules, a shared AI error policy module across sync/async clients, reduced noisy integration-runtime warnings for constrained Playwright/network test environments, and A2A protocol integration with 165+ dedicated tests.

**Validation snapshot (March 23, 2026):**
- `ruff check .` passes
- `mypy src/primr --ignore-missing-imports` passes (202 source files)
- `python -m pytest -q` passes: `4490 passed, 25 skipped`

## Documentation

| Doc | What's in it |
|-----|--------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, scraping tiers |
| [API.md](docs/API.md) | MCP server, A2A server, programmatic usage |
| [CONFIG.md](docs/CONFIG.md) | Full configuration reference |
| [API_KEYS.md](docs/API_KEYS.md) | API key setup |
| [CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) | Serverless deployment |
| [OPENCLAW.md](docs/OPENCLAW.md) | OpenClaw setup and troubleshooting |
| [SECURITY_OPS.md](docs/SECURITY_OPS.md) | Security operations guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [SECURITY.md](SECURITY.md) | Vulnerability reporting |
| [ROADMAP.md](ROADMAP.md) | What's planned |

## About This Project

Primr is a nights-and-weekends project by a solo developer. I kept finding myself spending hours researching companies — clicking around websites, reading articles, trying to piece together what a company actually does and where it's headed. The time-to-insight ratio was terrible, and most of the work was mechanical. That's exactly what AI should be doing.

So I built the tool I wanted: drop in a URL, get back a structured brief. It costs about $0.50 in API fees and saves hours per company. Whether you're evaluating a potential employer, researching an investment, preparing for a partnership conversation, or just curious about a company, it gets you up to speed fast.

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


