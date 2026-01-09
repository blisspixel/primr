Primr – Roadmap
Current State: v1.1.2 (January 2026)

Primr is a CLI-first, local research tool designed to support company intelligence research, strategic sensemaking, and AI roadmap development. It supports a structured research process while trying to stay honest about uncertainty and maintain a subject-positive posture.

Primr is intentionally opinionated, local-first, and analysis-driven.

What’s Working Today
Research Engines

Scrape Mode: 8-tier web scraping with intelligent escalation:
- HTTP tiers: requests, httpx, curl_cffi (TLS fingerprint impersonation)
- Browser tiers: Playwright, Playwright aggressive, DrissionPage (driverless CDP), DrissionPage stealth
- Vision tier: Screenshot + LLM extraction for image-heavy pages (opt-in)
- Reader-mode content extraction (BeautifulSoup-based, removes boilerplate)
- Content quality validation (catches garbage pages, triggers escalation)
- Homepage-first link discovery (fresher than sitemaps)
- Sticky tier optimization (reuses working tier for same host)
- Circuit breaker pattern (skips failing tiers after 3 failures)
- Soft block detection (catches "200 OK" traps, browser blocks)

Deep Mode: Gemini Deep Research Agent with autonomous multi-step search and synthesis

Full Mode: Sequential scrape + deep research pipeline

Report Generation

Professional TXT, DOCX, and PDF outputs

Citation styles: numbered, inline, sidecar

Automatic citation URL resolution (Google redirect URLs resolved to final destinations)

Structured report sectioning

Internal analysis-first orientation with downstream translation guidance

AI Strategy

AI strategy and roadmap generation

Explicit distinction between AI-enabled vs AI-native

Confidence labeling, deprioritization, governance, and ROI framing

Cloud vendor support: Azure, AWS, GCP, agnostic

Operational Maturity

Cost estimation with confirmation (--dry-run)

Usage tracking and job recovery

System diagnostics (primr doctor)

Test coverage

Design Philosophy (Locked)

Primr is optimized for:

Internal prep, not client-ready delivery

Hypothesis generation, not premature conclusions

Helping strong teams move faster and smarter

Delivering most of the value through thinking, framing, and structure

Primr is not:

A generic research scraper

A SaaS collaboration platform

A presentation builder

A “share with the client” tool

These constraints are intentional.

Completed Work
v1.0.0 – Primr Release (Complete)

Rebrand from company_researcher to primr

CLI usage: primr "Company" https://company.com

Simplified research modes: scrape, deep, full

primr doctor system diagnostics

pip-installable via pyproject.toml

Input validation for company name and URL

Stable output directory and artifact structure

v1.1.0 – Link Discovery and Scraping Improvements (Complete)

Browser-first homepage discovery: Uses Playwright directly for homepage link extraction since most modern sites are JS-heavy

Section expansion: Automatically spiders into news/blog/press/resources sections to capture article content for LLM analysis

LLM link selection: Uses LLM to intelligently select the most valuable pages for consultant research (falls back to heuristic scoring)

Smart discovery skipping: Skips common URL guessing and sitemap when homepage already provides 20+ links

Soft block detection fix: Pages with >10KB content no longer falsely flagged as WAF blocks

Improved link extraction: Two-pass regex approach handles nested tags in anchor elements

Citation URL resolution (redirect URLs resolved to readable final destinations)

v1.1.1 – Content Extraction and Quality Validation (Complete)

Reader-mode extraction: BeautifulSoup-based content extraction that removes boilerplate (nav, footer, ads, sidebars) and focuses on main content area. Produces cleaner text for LLM summarization.

Content quality validation: Automatic detection of garbage content (too short, repetitive, error pages, "Browser not supported" messages). Failed quality checks trigger tier escalation.

Browser block detection: Catches sites that serve "Browser not supported" or "Internet Explorer required" pages to HTTP clients, triggering escalation to browser tier.

Vision tier implementation: Full implementation of screenshot + LLM extraction for image-heavy pages. Takes full-page screenshot, sends to Gemini for text extraction. Opt-in via `enable_vision=True`.

Defensive tier escalation: Quality check runs after content extraction - if content is garbage, automatically tries next tier instead of returning bad data.

Near-Term Roadmap
v1.2.0 – Stability and Maintainability (In Progress)

Goal: Make Primr boringly reliable.

**Completed:**
- Test coverage hardening with 146 new tests across 9 test files
- pytest custom marks (slow, integration, smoke, resilience) for selective test execution
- CLI smoke tests for basic functionality validation
- API resilience tests (retry, backoff, fallback, consecutive failure handling)
- sections_written field accuracy and propagation tests
- Citation URL resolution and deduplication tests
- YAML configuration validation tests
- Output format consistency tests (DOCX tables, heading hierarchy)
- Thread safety tests for console and file operations
- Cost estimation accuracy tests
- File Search Store lifecycle and cleanup tests
- QA system aligned to core purpose (consultant prep, not report mechanics)

**Remaining:**
- Static analysis compliance (mypy, ruff)
- Performance profiling and bottleneck identification
- Documentation cleanup and developer guidance
- Refined error messages for failed research stages

This phase intentionally adds no new user-facing features.

v1.2.1 – QA-Driven Report Iteration (Near-Term)

Goal: Use QA feedback to iteratively improve weak sections until reports hit 90+.

**Workflow:**
1. Generate report
2. Run QA, get feedback on specific weak sections
3. Re-run just those sections with targeted improvements
4. Repeat until grade >= 90

**Implementation:**
- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work (not just overall grade)
- Section-level regeneration without full pipeline re-run
- Track iteration count and improvement delta

**Why this matters:**
The goal is consultant prep. An 85 is "usable" but a 90+ means the consultant walks in genuinely prepared. The marginal effort to go from 85 to 90 is worth it if it's automated.

Medium-Term Roadmap: Make Primr Iterative

v1.2.5 – Externalized Prompt Architecture (Complete)

Goal: Move prompts from hardcoded Python strings to structured, versionable configuration files.

Implemented Structure:
```
src/primr/prompts/
├── __init__.py                # Public API
├── loader.py                  # YAML loading and prompt building
├── company_overview.yaml      # Company research prompt (20 sections)
└── ai_strategy.yaml           # AI strategy prompt (vendor-specific)
```

Each prompt YAML file contains:
- Meta information (name, version, description)
- Document purpose and epistemic rules
- Formatting guidelines
- Sections organized by part (Foundational, Market Context, Strategic Analysis, etc.)
- Each section has: id, name, part, purpose, covers (bullet points), depth guidance
- Vendor-specific guidance (Azure, AWS, GCP, Agnostic) for AI strategy

Usage:
```python
from primr.prompts import (
    load_prompt_config,
    build_company_overview_prompt,
    build_ai_strategy_prompt,
    get_available_prompts,
)

# List available prompts
prompts = get_available_prompts()  # ['ai_strategy', 'company_overview']

# Build prompts from YAML
prompt = build_company_overview_prompt("Acme Corp", website_url="https://acme.com")
prompt = build_ai_strategy_prompt("Acme Corp", cloud_vendor="azure")
```

Benefits achieved:
- Prompts are now reviewable YAML artifacts (not buried in Python)
- Version control shows prompt evolution clearly
- Easier to iterate on section structure and guidance
- Clear separation of prompt engineering from code logic
- **Foundation for v1.2.6**: Adding a new strategy module = adding a YAML file

v1.2.6 – Extensible Strategy Modules (In Progress)

Goal: Make the "strategy layer" configurable and extensible beyond AI.

Currently, Primr generates an AI Strategy report after the company research. This is valuable but limiting. The same rich company context could inform other strategic analyses.

**How It Works (Building on v1.2.5)**

The externalized prompt architecture (v1.2.5) makes this straightforward:
1. Company Overview is always generated first (the research foundation)
2. Strategy modules are YAML configs in `src/primr/prompts/strategies/`
3. Each module defines its own sections, epistemic rules, and output structure
4. CLI flag selects which strategy reports to generate

**Implemented:**
- Strategy module YAML configs exist in `src/primr/prompts/strategies/`
- StrategyModuleRegistry auto-discovers modules from strategies/ directory
- PromptComposer class handles YAML loading and variable substitution

**Not Yet Implemented:**
- CLI flags (`--strategy`, `--list-strategies`, `--strategy-only`)
- Integration with research pipeline to generate multiple strategy reports

**Strategy Modules (YAML configs ready):**
```
src/primr/prompts/strategies/
├── ai_strategy.yaml           # AI roadmap, quick wins, bigger bets
├── cloud_migration.yaml       # Infrastructure and platform decisions
├── data_strategy.yaml         # Data platform, governance, analytics maturity
```

**Planned CLI Usage (not yet working):**
```bash
# Select specific strategy modules
primr "Tesla" https://tesla.com --strategy ai
primr "Tesla" https://tesla.com --strategy cloud
primr "Tesla" https://tesla.com --strategy data

# Multiple strategies in one run
primr "Tesla" https://tesla.com --strategy ai,cloud,data

# Skip all strategy reports (company overview only)
primr "Tesla" https://tesla.com --no-strategy

# List available strategy modules
primr --list-strategies
```

**Each Strategy Module YAML Contains:**
- Meta information (name, version, description)
- Document purpose and audience
- Epistemic rules specific to that domain
- Sections with purpose, covers, and depth guidance
- Domain-specific context (e.g., vendor guidance for cloud, compliance frameworks for security)

**Benefits (when complete):**
- Adding a new strategy type = adding a YAML file (no code changes)
- Users can customize existing strategies or create their own
- Same company research feeds multiple strategic analyses
- Clear separation between research (company overview) and analysis (strategy modules)


v1.3.0 – Research State and Iteration (Planned)

Goal: Move from “generate once” to “think over time.”

Research State Artifacts

Introduce a lightweight local research state file (YAML or JSON)

Track:

initial hypotheses

assumptions

confidence levels

open questions

Persist state across runs for the same company

Explicit Hypothesis Tracking

Clearly separate:

facts

inferences

hypotheses

Mark hypotheses as:

untested

partially validated

invalidated

confirmed

This mirrors how consultants actually work after discovery conversations.

v1.4.0 – Refinement and Learning Loop (Planned)

Goal: Support post-discovery learning without re-running everything from scratch.

Potential capabilities:

primr refine command that accepts:

discovery notes

meeting summaries

client feedback

Re-synthesize insights with:

updated confidence

revised hypotheses

adjusted recommendations

Outputs evolve from:

pre-meeting prep

to post-discovery POV

to proposal-grade thinking

Still local. Still internal.

v1.5.0 – POV and Narrative Evolution (Planned)

Goal: Make Primr the system of record for how thinking evolves.

Versioned research artifacts (v1 prep, v2 post-discovery, v3 POV)

Explicit “what changed and why” sections

Stronger alignment between company overview and AI strategy

Optional narrative framing outputs for internal deck creation

At this point, Primr becomes less a one-shot tool and more a structured research workflow.

Scale Readiness (Intentional, Not Yet Implemented)

Primr is currently optimized for individual and small-team use, running locally with user-provided API keys. This is intentional so the focus remains on output quality, honest uncertainty handling, and usefulness in real consulting workflows.

That said, Primr is being designed with a clear and realistic path to scale if organizational adoption increases.

If Primr were to support hundreds or thousands of internal users, the expected evolution would be:

Execution model
Transition from local execution to centralized, container-based job execution to support long-running scraping and research jobs reliably.

Interface model
Preserve the CLI as the primary interface, with local vs remote execution as an implementation detail rather than a product shift.

Reliability and cost control
Centralized execution would enable shared caching, retries, scheduling, and predictable cost governance that are impractical across individual laptops.

Governance
Centralized prompt versions, configuration defaults, and guardrails to ensure consistent outputs and maintain trust at scale.

This evolution would position Primr as an internal research and strategy platform, not a public SaaS product. Any move in this direction would be driven by demonstrated usage and clear internal demand, not speculative scaling.

Explicitly Deferred (By Design)

These are not “missing features.” They are conscious non-goals for now.

Centralized Execution Infrastructure

Docker, Cloud Run, Container Apps

Async job queues

Multi-tenant execution

Deferred until:

Iterative workflow is proven indispensable

Reliability or throughput becomes a real constraint

Web Interface

Browser-based submission

Job dashboards

Report downloads

Deferred because:

It adds UX, auth, and infra complexity

It risks turning Primr into “just another research app”

Collaboration and Sharing

Accounts, permissions, comments

Sharing reports externally

Deferred because:

Primr’s value is thinking quality, not collaboration mechanics

Sharing comes after POV clarity, not before

Long-Term Possibilities (Non-Commitments)

Only to be explored if usage patterns justify them:

Read-only web viewer for generated artifacts

Webhooks or notifications on job completion

CRM or document system integration

Programmatic API for embedding Primr into larger workflows

These are downstream enablers, not core value drivers.

Usage Reference
# Basic usage
primr "Tesla" https://tesla.com

# Research modes
primr "Tesla" https://tesla.com --mode scrape
primr "Tesla" https://tesla.com --mode deep
primr "Tesla" https://tesla.com --mode full

# AI Strategy
primr "Tesla" https://tesla.com --cloud-vendor azure
primr "Tesla" https://tesla.com --no-ai-strategy

# Operations
primr doctor
primr "Tesla" https://tesla.com --dry-run
primr --check-jobs

Version History
Version	Date	Highlights
0.1.0	Nov 2025	Core research pipeline
0.2.0	Nov 2025	Deep Research integration
0.3.0	Dec 2025	Full mode (two-step)
0.4.0	Dec 2025	AI Strategy generation
0.5.0	Dec 2025	Cost tracking, job recovery
1.0.0	Dec 2025	Rebrand to Primr, pip installable
1.1.0	Jan 2026	Browser-first discovery, LLM link selection, section expansion
1.1.1	Jan 2026	Reader-mode extraction, content quality validation, vision tier
1.1.2	Jan 2026	Cache disabled by default (fresh data always)
1.2.0	Dec 2025	Test coverage hardening (146 new tests, pytest marks)
1.2.1	Planned	QA-driven report iteration (target 90+ grades)
1.2.5	Dec 2025	Externalized prompt architecture (YAML configs)
1.2.6	In Progress	Extensible strategy modules (YAML ready, CLI pending)
1.3.0	TBD	Research state and hypothesis tracking
1.4.0	TBD	Iterative refinement loop
1.5.0	TBD	POV evolution and narrative continuity
Final Framing

Primr is a tool for understanding companies. The focus is on useful output, not user growth.