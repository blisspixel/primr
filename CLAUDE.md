# CLAUDE.md - Primr Agent Context Map

> Context engineering for AI agents working with primr. Read this first.

## Quick Start (< 500 tokens)

### What is Primr?
Company research tool using Gemini and Grok models. Generates strategic intelligence briefs from adaptive scraping + AI-powered research and synthesis.

### Critical Constraints
- **Single-job model**: ONE research job at a time. Check `primr --check-jobs` before starting new research.
- **Async execution**: `research_company` returns immediately with `job_id`. Poll `check_jobs` for completion.
- **Cost awareness**: ALWAYS run `estimate_run` before `research_company`. Default mode uses Grok 4.20 hybrid when XAI_API_KEY is set (~$0.75, ~35-50 min, 40-55 sources). Use `--premium` for Gemini + Deep Research (~$5, 50-75 min). Scrape ~$0.10, deep ~$2.50. Each extra `--platform` adds ~$0.07 (standard) or ~$2.50 (premium). DDG searches are free. Use `--lite` with `--premium` to drop strategy cost.

### Common Tasks

```bash
# Estimate before running (REQUIRED)
primr "Company" https://example.com --dry-run

# Quick website intel (5-10 min, ~$0.10)
primr "Company" https://example.com --mode scrape

# Deep external research (10-15 min, ~$2.50)
primr "Company" https://example.com --mode deep

# Standard run (~$0.75, ~35-50 min — auto-uses Grok 4.20 hybrid when XAI_API_KEY set)
primr "Company" https://example.com

# Most common: Microsoft + NVIDIA AI strategy
primr "Company" https://example.com --platform ms

# DNS intelligence only (no API keys, 2-3 seconds)
primr recon acme.com

# Multi-platform AI strategy (~$0.60, adds ~$0.07 per platform)
primr "Company" https://example.com --platform aws azure

# Platform aliases: microsoft=azure, amazon=aws, google=gcp, nvidia=private
primr "Company" https://example.com --platform microsoft nvidia

# Other strategy types (CX, security, data fabric — see --list-strategies)
primr "Company" https://example.com --strategy-type customer_experience

# Premium mode: Gemini + Deep Research (~$5, 50-75 min)
primr "Company" https://example.com --premium

# Premium + Microsoft/NVIDIA (~$9)
primr "Company" https://example.com --premium --platform ms

# Lite premium strategy (~$4, uses Pro instead of DR)
primr "Company" https://example.com --premium --platform ms --lite

# Claim verification (~$0.01, 3-5 min, non-blocking)
primr "Company" https://example.com --verify

# Continuous reasoning is ON by default after the n=3 pilot: workbook + cross-validation share
# one Grok session so the validator inherits corpus + workbook reasoning. Avg ~+12% cost
# (range −3.7% to +32%) for sharper analysis and ~81% fewer leaked-instruction lines in the
# final report. See ROADMAP "Continuous Reasoning Session".
# To revert to fresh-call topology for one run:
primr "Company" https://example.com --no-continuous-reasoning
# To disable across all runs on this machine, set PRIMR_CONTINUOUS_REASONING=0 in env.

# Check job status
primr --check-jobs

# System health
primr doctor

# DNS intelligence lookup
primr recon acme.com

# A2A server (requires: pip install primr[a2a])
primr-a2a --no-auth                        # Standalone A2A on port 9000
primr-mcp --http --a2a                     # Co-hosted MCP + A2A
```

### MCP Tools (for programmatic access)
| Tool | Purpose |
|------|---------|
| `estimate_run` | Get cost/time estimate (call FIRST). Includes strategy cost when platforms specified. Modes: scrape, deep, full (default, Grok), premium (Gemini+DR) |
| `research_company` | Start async research job (includes strategy when platform set). Returns job_id. Optional `destination` param for output directory. |
| `check_jobs` | Poll job status. Returns full artifact content (report + strategy MD) inline when completed — no filesystem access needed. |
| `generate_strategy` | Add strategy to an existing report after the fact (not needed for new research — use platform on research_company instead) |
| `run_qa` | Quality assessment on reports |
| `doctor` | System health check |
| `delegate_to_agent` | Call an external A2A agent (requires primr[a2a]) |

---

## Architecture Pointers

| Document | What You'll Find |
|----------|------------------|
| `docs/ARCHITECTURE.md` | Pipeline stages, scraping tiers, data flow diagrams |
| `docs/API.md` | MCP server tools, resources, authentication |
| `docs/STATE_MACHINES.md` | Tier escalation logic, job lifecycle states |
| `docs/CONFIG.md` | Environment variables, configuration options |
| `ROADMAP.md` | Planned features, version dependencies |

### Key Source Locations
```
src/primr/
├── core/           # Research orchestration, CLI
├── ai/             # LLM clients, deep research, summarization
├── data/           # Scraping engine, caching, link discovery
├── a2a/            # A2A protocol integration (optional: pip install primr[a2a])
├── agentic/        # Agent architecture (memory, hooks, subagents)
├── mcp_server/     # MCP protocol implementation
└── prompts/        # YAML-based prompt templates
```

### The Pipeline (one function: `fetch_web_content`)
```
[Build Site Corpus] -> [Extract Insights] -> [Deep Research] -> [Write Report]
     corpus files        insights.txt         dossier.txt       report.docx
```

---

## Verification Commands

```bash
# System health (API keys, dependencies)
primr doctor

# Run all tests (stop on first failure)
python -m pytest tests/ -x --tb=short

# Run agentic module tests only
python -m pytest tests/agentic/ -v --tb=short

# Run A2A tests only (requires: pip install .[a2a])
python -m pytest tests/a2a/ -v --tb=short

# Lint check
ruff check src/

# Type check
mypy src/primr --ignore-missing-imports
```

---

## Negative Constraints (What NOT to Do)

### NEVER
- Start research without running `estimate_run` or `--dry-run` first
- Run multiple research jobs concurrently (single-job model)
- Bypass SSRF protection - all URLs validated via `primr.utils.security`
- Store API keys or secrets in research memory entries
- Call `fetch_web_content` from multiple places - it's the ONE site-to-corpus function
- Assume scrape success - check `pages_failed` count in results

### AVOID
- Long-running commands in agent context (use `--check-jobs` polling instead)
- Modifying `_raw_scrapes/` directory directly - managed by scraper
- Hardcoding tier selection - let the 9-tier orchestrator handle escalation
- Ignoring QA scores below 70 - indicates report quality issues

---

## Progressive Disclosure

<details>
<summary><strong>Scraping Tiers (9-tier fallback system)</strong></summary>

| Tier | Method | When Used |
|------|--------|-----------|
| 1 | Playwright | JS-rendered content (default) |
| 2 | Playwright Aggressive | Accordions, lazy load |
| 3 | Patchright | Kasada/Akamai bypass (real Chrome + persistent profile) |
| 4 | curl_cffi | TLS fingerprint impersonation |
| 5 | DrissionPage Stealth | Challenge waiting |
| 6 | DrissionPage | Driverless CDP |
| 7 | Vision | AI extraction (enabled by default) |
| 8 | httpx | HTTP/2 sites |
| 9 | requests | Simple sites (fallback) |

Key features: Sticky tier (remembers what works), Circuit breaker (skips failing tiers), Cookie handoff (browser→HTTP), Content-type routing (PDF/HTML/binary detection), Per-host rate-limit memory (429-flagged hosts skip live scrape for 20 min), Headed popup budget (default 0 — opt in per run via `PRIMR_MAX_HEADED_POPUPS=N` to allow up to N visible-browser challenges; shared across stealth + adaptive retry; auto-disabled on Linux without `DISPLAY`/`WAYLAND_DISPLAY`).

**Public-data fallback fan-out** (`src/primr/data/fallback_sources.py`): when live scrape returns zero pages, primr routes around the block by fetching in parallel from (1) Wayback Machine via CDX API, (2) live sister subdomains (investor.*, ir.*, newsroom.*), (3) SEC EDGAR 10-K filings (for US public filers), (4) Wikipedia REST API, and (5) Grok web_search synthesis with citations. All fail open — any one returning content is enough to produce a report.

**Hiring-signal gathering** (`src/primr/data/hiring_signals.py`): after the main-site scrape (fast mode only for now), primr tries Greenhouse / Lever / Ashby / SmartRecruiters public board APIs in parallel against slug candidates, falls back to an HTML careers-page crawl if they all miss, LLM-triages up to 15 postings, and runs a batched LLM extraction to produce tech-stack frequency, strategic initiatives, culture signals, and a one-paragraph summary. Output persists to `<working>/_hiring/` and is threaded into `insights.txt` + raw external-sources bundle so every downstream phase sees it. Skip with `PRIMR_SKIP_HIRING_SIGNALS=1`.

</details>

<details>
<summary><strong>Recon (external recon-tool package)</strong></summary>

DNS intelligence is provided by the standalone `recon-tool` package (pinned in `pyproject.toml` as a dependency). The CLI is mounted at `primr recon <domain>` and delegates to `recon_tool.cli:app`. Update recon features by updating `recon-tool` in its own repo and bumping the version pin here.

```python
from recon_tool.resolver import resolve_tenant      # async
from recon_tool.models import TenantInfo
from recon_tool.validator import validate_domain
from recon_tool.formatter import format_tenant_dict, format_tenant_json, format_tenant_markdown
```

primr wraps recon output into strategy-context text via `primr.core.recon_context.format_recon_context(TenantInfo)`.

</details>

<details>
<summary><strong>Research Memory System</strong></summary>

Persistent hypothesis tracking across research sessions:

```python
from primr.agentic.memory import ResearchMemory, Hypothesis, ConfidenceLevel

memory = ResearchMemory(Path("logs/research_memory"))
hypotheses = memory.get_hypotheses("Acme Corp", min_confidence=ConfidenceLevel.VALIDATED)

# Update hypothesis with new evidence
memory.update_hypothesis("Acme Corp", "h_001", ConfidenceLevel.CONFIRMED, "Q4 earnings confirmed growth")
```

Confidence levels: `UNTESTED` → `VALIDATED` → `CONFIRMED` (or `INVALIDATED`)

</details>

<details>
<summary><strong>Hook System (Policy Enforcement)</strong></summary>

```python
from primr.agentic.hooks import HookSystem, CostGuardHook, SSRFGuardHook

hooks = HookSystem()
hooks.register(CostGuardHook(max_cost_usd=5.0))  # Block if over budget
hooks.register(SSRFGuardHook())  # Validate URLs

# Hooks run in priority order (lower = first)
# PRE_TOOL_USE hooks can BLOCK operations
# POST_TOOL_USE hooks can WARN or trigger follow-up
```

</details>

<details>
<summary><strong>Subagent Architecture</strong></summary>

Specialized agents with isolated context:

| Subagent | Responsibility | Delegates To |
|----------|----------------|--------------|
| ScraperSubagent | Tier escalation, content extraction | `fetch_web_content` |
| AnalystSubagent | Insight synthesis, hypothesis generation | `summarize_scraped_content` |
| WriterSubagent | Report generation | Report pipeline |
| QASubagent | Quality assessment, feedback | QA analyzer |

Orchestrator coordinates: `IDLE → SCRAPING → ANALYZING → WRITING → QA → COMPLETED`

</details>

<details>
<summary><strong>Error Hierarchy</strong></summary>

All errors inherit from `PrimrError` in `src/primr/utils/errors.py`:

```
PrimrError
├── ConfigurationError      # Missing API keys, invalid config
├── NetworkError           # Connection failures, timeouts
│   ├── RateLimitError     # 429 responses (auto-retry)
│   └── SSRFError          # Blocked URL patterns
├── ScrapingError          # Content extraction failures
├── AIError                # LLM API failures
└── ValidationError        # Input validation failures
```

Use `error.is_retryable` to check if retry makes sense.

</details>

---

## Agentic Module Reference

```python
# Memory - persistent research state
from primr.agentic.memory import ResearchMemory, Hypothesis, ConfidenceLevel

# Roadmap - programmatic access to ROADMAP.md
from primr.agentic.roadmap_api import RoadmapAPI, VersionStatus

# Hooks - policy enforcement
from primr.agentic.hooks import HookSystem, CostGuardHook, SSRFGuardHook, QAGateHook

# Subagents - specialized research agents
from primr.agentic.subagents import ScraperSubagent, AnalystSubagent, WriterSubagent, QASubagent

# Orchestrator - coordinates subagent execution
from primr.agentic.orchestrator import ResearchOrchestrator, OrchestratorConfig
```

---

## Testing Patterns

```bash
# Property-based tests (Hypothesis library)
python -m pytest tests/agentic/property_tests/ -v --tb=short

# Specific test file
python -m pytest tests/agentic/property_tests/test_memory_properties.py -v

# Run with coverage
python -m pytest tests/ --cov=src/primr --cov-report=term-missing
```

Property tests validate universal correctness (e.g., "round-trip serialization preserves data").
Unit tests validate specific examples and edge cases.

---

*Last updated: 2026-04-21 | Primr v1.19.0 | Agentic Architecture v1.0 | A2A Protocol v1.0*
