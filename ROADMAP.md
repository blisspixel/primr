Primr – Roadmap
Current State: v1.5.0 (February 2026)

Primr is a CLI-first, local research tool designed to support company intelligence researcharation, strategic analysis, and AI roadmap development. The tool aims to accelerate research workflows while maintaining transparency about uncertainty and supporting a subject-positive posture.

The design is intentionally opinionated, local-first, and analysis-driven. This roadmap reflects completed work and planned improvements.

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
- Smart tier escalation: Stops after 3 consecutive failures (v1.2.4+)
- Patient timeout: 90s max per page for quality content (v1.2.4+)

Deep Mode: Gemini Deep Research Agent with autonomous multi-step search and synthesis

Full Mode: Sequential scrape + deep research pipeline

Resource Management (v1.3.1)

Automatic cleanup of Gemini File Search Stores after each run

`primr doctor` checks for orphaned resources that could incur costs

Manual cleanup script: `scripts/check_gemini_resources.py`

Proper two-step store deletion (documents first, then store)

CLI/UX Enhancements (v1.2.4)

Clean inline progress updates (no blank lines, single-line updates)

Reduced noise: Tier failures and timeouts logged at debug level

Professional console output with clear phase indicators

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

Design Philosophy

Primr aims to support understanding companiesaration by focusing on:

- Internal preparation rather than client-ready deliverables

- Hypothesis generation rather than premature conclusions

- Helping teams work more efficiently

- Providing value through structured thinking and framing

Primr is intentionally not designed as:

- A generic research scraper

- A SaaS collaboration platform

- A presentation builder

- A client-facing tool

These design constraints reflect the tool's intended use case and help maintain focus on its core purpose.

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
v1.2.0 – Stability and Maintainability (Complete)

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
- External source validation with LLM company identification
  - Google Search for business news (press releases, funding, partnerships)
  - Filters low-value sites (social media, job boards, support forums)
  - LLM validates articles are about the TARGET company (uses domain as identifier)
  - Prevents name collision issues (e.g., "EverTrue" fundraising vs "EverTrue" senior living)
  - 26 new tests for external source pipeline
- Structured content extraction with quality scoring (v1.2.2)
  - Multi-pass extraction pipeline: DOM sanitization → container scoring → block extraction → boilerplate filtering
  - Formalized output contract with metrics (char_count, link_density, boilerplate_ratio, etc.)
  - Quality scoring (0-1) with flags for downstream decisions
  - Container scoring algorithm picks best main content area (not just <main> tag)
  - Link density filtering removes nav-heavy blocks generically
  - Cross-page boilerplate fingerprinting learns and removes repeated lines
  - Structured blocks preserve headings, lists, quotes with attribution
  - CTA detection marks promotional content for optional exclusion
  - Quality-based tier escalation: low scores trigger browser/vision tiers
  - Metadata extraction: title, description, published_date, byline, language
- AI Strategy retry/resume capability (v1.2.3)
  - `primr --ai-strategy-only <report_path>` to retry failed AI strategy with existing report
  - Automatic polling for completion when streaming connection drops (every 2 min for 30 min)
  - Job tracking with `primr --check-jobs` and `primr --clear-jobs`
  - Full job IDs displayed in console output for recovery
  - Completed jobs auto-saved to output/recovered_*.txt
- CLI UX improvements (v1.2.3)
  - Suppressed noisy navigation timeout warnings (now debug level)
  - Fixed duplicate "pages scraped" message
  - Fixed boilerplate matching false positives (word-boundary regex)
  - Added "Understanding Scrape Results" section to README
- **Security Deep Review (v1.2.4)**
  - Fixed XXE vulnerability in XML sitemap parsing
  - Implemented comprehensive SSRF protection (9 functions protected)
  - Fixed MD5 insecure usage (3 instances)
  - Added 22 security tests covering SSRF, XXE, path traversal, input validation
  - Automated security scanning with Bandit and Safety
  - Complete security audit documented in docs/SECURITY_REVIEW_2026-01-21.md
  - Production-ready security posture achieved
- **Vendor Research Reuse Fix (v1.2.4)**
  - Fixed vendor research regeneration bug (now reuses existing monthly files)
  - Saves ~7 minutes and ~$0.10 per run when vendor research already exists
  - Added clear console feedback when reusing existing files
  - Documented in docs/VENDOR_RESEARCH_REUSE_FIX.md
- **CLI Output Improvements (v1.2.4)**
  - Reduced retry noise: Single "API delays detected" message instead of 10 WARNINGs
  - Increased heartbeat interval from 30s to 90s (less frequent progress updates)
  - Enhanced phase banners with ASCII separators for better visual hierarchy
  - Removed duplicate "Research started" messages (appeared 3 times, now 1)
  - Cleaner output during long-running operations (68-minute runs)
  - Documented in docs/CLI_OUTPUT_IMPROVEMENTS.md

**Status:** COMPLETE

v1.4.0 – MCP Server for AI Agent Integration (Complete)

Goal: Enable AI agents like Claude Desktop to drive Primr research programmatically.

**Completed:**
- Full Model Context Protocol (MCP) server implementation
- Two transport modes: stdio (for Claude Desktop) and streamable HTTP
- 8 tools: estimate_run, research_company, generate_strategy, check_jobs, run_qa, doctor, clear_jobs, cancel_job
- 4 resources: primr://research/status, primr://output/latest, primr://output/artifacts, primr://config
- 2 prompt templates: research_workflow, strategy_selection
- SingleJobStore with journal persistence for crash recovery
- Security middleware: PathValidator (path traversal protection), URLValidator (SSRF protection), RateLimiter (per-tool limits)
- JWT authentication for HTTP mode with admin policy support
- Graceful shutdown with 5s/10s timeouts, marks in-progress jobs as failed
- Heartbeat monitoring for stuck job detection
- 193 tests covering all functionality

**Architecture:**
```
src/primr/mcp_server/
├── __init__.py           # Public API
├── server.py             # Main server, transport setup
├── tools.py              # 8 tool handlers
├── resources.py          # 4 resource handlers
├── prompts.py            # 2 prompt templates
├── job_store.py          # SingleJobStore with journal
├── security.py           # PathValidator, URLValidator, RateLimiter
├── auth.py               # JWT authentication
├── pipeline_runner.py    # Wiring to Primr core modules
├── cli.py                # primr-mcp command
├── logging_config.py     # Transport-specific logging
└── types.py              # Type definitions
```

**CLI Usage:**
```bash
# Run with stdio transport (for Claude Desktop)
primr-mcp --stdio

# Run with HTTP transport
primr-mcp --http --port 8000

# Development mode (no auth)
primr-mcp --http --port 8000 --no-auth --allow-plaintext
```

**Claude Desktop Integration:**
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

**Benefits Achieved:**
- AI agents can autonomously research companies and generate strategies
- Async job model prevents blocking during long research runs
- Security-first design with path traversal, SSRF, and rate limit protection
- Journal persistence enables crash recovery without data loss
- Clean separation between MCP protocol and Primr core functionality

v1.4.1 – Open Claw Integration (Complete)

Goal: Enable Primr to run as a skill within Open Claw's agentic runtime with approval gates for cost-incurring operations.

**Completed:**
- Full Open Claw integration with skills, workflows, and adapters
- 3 skills: primr-research, primr-strategy, primr-qa
- Lobster workflow for orchestrated research with approval gates
- TypeScript adapter for status monitoring
- Docker sandbox configuration for secure execution
- 3 new MCP resources for Open Claw integration:
  - `primr://strategies/available` - List available strategy types with metadata
  - `primr://output/by_job/{job_id}` - Job-scoped artifact retrieval
  - `primr://output/manifest/latest` - Run manifest for audit trail
- Run manifest generation for audit trail and provenance tracking
- Comprehensive test suite (163 tests passing)

**Architecture:**
```
openclaw/
├── skills/
│   ├── primr-research/
│   │   ├── SKILL.md
│   │   └── scripts/research-status.ts
│   ├── primr-strategy/
│   │   └── SKILL.md
│   └── primr-qa/
│       └── SKILL.md
├── workflows/
│   └── research-pipeline.yaml
├── openclaw.json
├── exec-approvals.json
└── Dockerfile.primr
```

**Key Features:**
- Approval gates prevent cost-incurring operations without explicit user consent
- Token-bound approvals ensure estimates match execution
- Run manifests provide complete audit trail for each research job
- Skills expose Primr capabilities to Open Claw's Pi agent
- Lobster workflow orchestrates multi-step research with polling

**Benefits Achieved:**
- Autonomous research workflows with human-in-the-loop approval
- Cost transparency before execution
- Audit trail for compliance and debugging
- Secure sandboxed execution via Docker
- Seamless integration with Open Claw's agentic runtime

v1.5.0 – PhD-Level Code Quality (Complete)

Goal: Elevate codebase from A- (88/100) to A+ (publication-ready) quality through systematic improvements to error handling, observability, configuration validation, and formal specifications.

**Completed:**
- **Typed Error Hierarchy** - Comprehensive exception hierarchy with `PrimrError` base class, `TransientError`/`PermanentError` categories, and specific types (RateLimitError, QuotaError, NetworkError, ValidationError, AuthenticationError, ConfigurationError) with automatic correlation ID capture and JSON serialization
- **Retry Policy Manager** - Automatic retry policies based on error type hierarchy with exponential backoff, jitter, retry history tracking, and metrics emission
- **Circuit Breaker with Monitoring** - Per-host/operation circuit breaker with state tracking (CLOSED/OPEN/HALF_OPEN), configurable thresholds, state change events, and monitoring interface
- **OpenTelemetry Integration** - Distributed tracing with TracerProvider, span creation for pipeline phases, async context propagation, and configurable exporters (console, OTLP, Jaeger)
- **Cost Attribution** - Token usage tracking with cost calculation per model, aggregation by operation/phase, and span attribute attachment
- **Pydantic Configuration Validation** - Strict validation for all YAML configurations with detailed error messages, schema versioning, and JSON Schema export
- **Configuration Migration Tooling** - Version detection, sequential migration application, backup/restore, and dry-run mode
- **Concurrency Model Documentation** - CONCURRENCY.md documenting operation classification, thread pool sizing, shared state, async/sync boundaries, and deadlock prevention
- **State Machine Specifications** - Formal state machines for tier escalation and job lifecycle with transition validation, invariant assertions, event emission, and Mermaid diagrams in docs/STATE_MACHINES.md
- **Performance Benchmarking Suite** - Benchmark infrastructure with result storage, regression detection, and configurable thresholds
- **Memory Profiling** - Allocation tracking, unbounded growth detection, component-level reporting, threshold warnings, and pytest integration
- **MCP API Versioning** - Semantic versioning for tool schemas with deprecation warnings and migration guides
- **282 Property-Based Tests** - Comprehensive property tests validating universal correctness properties across all new modules

**New Modules:**
```
src/primr/utils/
├── errors.py              # Typed error hierarchy with retry policies
├── retry.py               # RetryPolicyManager with exponential backoff
├── circuit_breaker.py     # Circuit breaker with monitoring
├── telemetry.py           # OpenTelemetry integration
├── cost_tracker.py        # Cost attribution per operation
├── validation.py          # Pydantic configuration validation
├── migration.py           # Configuration migration tooling
├── state_machine.py       # Generic state machine with transitions
├── benchmarks.py          # Performance benchmarking suite
├── memory_profiler.py     # Memory profiling and leak detection

src/primr/mcp_server/
├── versioning.py          # MCP API versioning with deprecation support
```

**Documentation:**
- CONCURRENCY.md - Threading model and deadlock prevention
- docs/STATE_MACHINES.md - Formal state machine specifications with Mermaid diagrams

**Status:** COMPLETE

v1.6.0 – QA-Driven Report Iteration (Near-Term)

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

v1.7.0 – Research State and Iteration (Planned)

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

v1.8.0 – Refinement and Learning Loop (Planned)

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

v1.9.0 – POV and Narrative Evolution (Planned)

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

# Retry AI Strategy (when main report succeeded but AI strategy failed)
primr --ai-strategy-only "output/Tesla_Strategic_Overview_01-09-2026.md"
primr --ai-strategy-only "output/report.md" --cloud-vendor aws

# Job management
primr --check-jobs    # Check status of pending Deep Research jobs
primr --clear-jobs    # Clear stale/old pending jobs

# Operations
primr doctor
primr "Tesla" https://tesla.com --dry-run

# MCP Server (AI agent integration)
primr-mcp --stdio                              # For Claude Desktop
primr-mcp --http --port 8000                   # HTTP transport
primr-mcp --http --port 8000 --no-auth         # Development mode

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
1.2.0	Jan 2026	Test coverage hardening (146 new tests, pytest marks)
1.2.2	Jan 2026	Structured content extraction with quality scoring
1.2.3	Jan 2026	AI Strategy retry, job polling, CLI UX fixes
1.2.4	Jan 2026	Security deep review (XXE, SSRF, MD5 fixes, 22 security tests)
1.2.5	Jan 2026	Externalized prompt architecture (YAML configs)
1.2.6	Jan 2026	Strategy document portfolio (4 strategies implemented and tested)
1.3.0	Jan 2026	Python 3.11+ requirement, build configuration updates
1.3.1	Jan 2026	File Search Store billing leak fix, resource management, fd leak fixes
1.4.0	Feb 2026	MCP Server for AI agent integration (8 tools, 4 resources, 2 prompts)
1.4.1	Feb 2026	Open Claw integration (skills, workflows, adapters, 3 new resources)
1.5.0	Feb 2026	PhD-Level Code Quality (error hierarchy, telemetry, state machines, 282 property tests)
1.6.0	TBD	QA-driven report iteration
1.7.0	TBD	Research state and hypothesis tracking
1.8.0	TBD	Iterative refinement loop
1.9.0	TBD	POV evolution and narrative continuity
Final Framing

Primr is a tool for understanding companies. The focus is on useful output, not user growth.