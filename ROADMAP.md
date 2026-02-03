# Primr Roadmap

Current State: v1.5.1 (February 2026)

Primr is a CLI-first, local research tool for company intelligence and strategic analysis. It aims to accelerate research workflows while being transparent about uncertainty.

The design is intentionally opinionated and local-first. This roadmap reflects completed work and planned improvements. Some features work better than others, and the tool continues to evolve based on actual usage.

## What's Working Today

### Research Engines

**Scrape Mode**: 8-tier web scraping with intelligent escalation:
- HTTP tiers: requests, httpx, curl_cffi (TLS fingerprint impersonation)
- Browser tiers: Playwright, Playwright aggressive, DrissionPage (driverless CDP), DrissionPage stealth
- Vision tier: Screenshot + LLM extraction for image-heavy pages (opt-in)
- Reader-mode content extraction (BeautifulSoup-based, removes boilerplate)
- Content quality validation (catches garbage pages, triggers escalation)
- Homepage-first link discovery (fresher than sitemaps)
- Sticky tier optimization (reuses working tier for same host)
- Circuit breaker pattern (skips failing tiers after 3 failures)
- Soft block detection (catches "200 OK" traps, browser blocks)

**Deep Mode**: Gemini Deep Research Agent with autonomous multi-step search and synthesis

**Full Mode**: Sequential scrape + deep research pipeline

### Resource Management (v1.3.1)

- Automatic cleanup of Gemini File Search Stores after each run
- `primr doctor` checks for orphaned resources that could incur costs
- Manual cleanup script: `scripts/check_gemini_resources.py`

### Report Generation

- TXT, DOCX, and PDF outputs
- Citation styles: numbered, inline, sidecar
- Automatic citation URL resolution
- Structured report sectioning

### AI Strategy

- AI strategy and roadmap generation
- Cloud vendor support: Azure, AWS, GCP, agnostic
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric

### Operational Maturity

- Cost estimation with confirmation (--dry-run)
- Usage tracking and job recovery
- System diagnostics (primr doctor)
- Test coverage

## Design Philosophy

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

## Completed Work

### v1.0.0 - Primr Release (Complete)

- Rebrand from company_researcher to primr
- CLI usage: primr "Company" https://company.com
- Simplified research modes: scrape, deep, full
- primr doctor system diagnostics
- pip-installable via pyproject.toml

### v1.1.0 - Link Discovery and Scraping Improvements (Complete)

- Browser-first homepage discovery
- Section expansion for news/blog/press content
- LLM link selection for valuable pages
- Citation URL resolution

### v1.1.1 - Content Extraction and Quality Validation (Complete)

- Reader-mode extraction
- Content quality validation
- Browser block detection
- Vision tier implementation

### v1.2.0 - Stability and Maintainability (Complete)

- Test coverage hardening (146 new tests)
- External source validation with LLM company identification
- Structured content extraction with quality scoring
- AI Strategy retry/resume capability
- Security review (XXE, SSRF fixes)
- CLI output improvements

### v1.4.0 - MCP Server for AI Agent Integration (Complete)

- Full Model Context Protocol (MCP) server implementation
- Two transport modes: stdio (for Claude Desktop) and streamable HTTP
- 8 tools for research operations
- Security middleware with path traversal, SSRF, and rate limit protection
- JWT authentication for HTTP mode

### v1.4.1 - Open Claw Integration (Complete)

- Full Open Claw integration with skills, workflows, and adapters
- Approval gates for cost-incurring operations
- Run manifest generation for audit trail

### v1.5.0 - Code Quality Improvements (Complete)

- Typed error hierarchy with automatic retry classification
- Circuit breaker with per-host failure tracking
- OpenTelemetry integration for distributed tracing
- Configuration validation with early startup checks
- State machine specifications for tier escalation and job lifecycle
- Unified async/sync boundary handling
- 282 property-based tests
- Documentation: CONCURRENCY.md, docs/STATE_MACHINES.md, docs/MIGRATION.md

### v1.5.1 - Code Quality Fixes (Complete)

- Fixed dead code and unreachable statements
- Fixed Python 3.10 compatibility in MCP server
- Fixed exception chaining across modules
- Fixed ambiguous variable names and duplicate definitions
- Full ruff compliance (all checks pass)
- 1526 tests passing

## Near-Term Roadmap

### v1.6.0 - QA-Driven Report Iteration (Planned)

Goal: Use QA feedback to iteratively improve weak sections until reports hit 90+.

Workflow:
1. Generate report
2. Run QA, get feedback on specific weak sections
3. Re-run just those sections with targeted improvements
4. Repeat until grade >= 90

Implementation:
- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work
- Section-level regeneration without full pipeline re-run

## Medium-Term Roadmap

### v1.7.0 - Research State and Iteration (Planned)

Goal: Move from "generate once" to "think over time."

- Lightweight local research state file (YAML or JSON)
- Track hypotheses, assumptions, confidence levels, open questions
- Persist state across runs for the same company
- Explicit hypothesis tracking (untested, validated, invalidated, confirmed)

### v1.8.0 - Refinement and Learning Loop (Planned)

Goal: Support post-discovery learning without re-running everything from scratch.

- `primr refine` command accepting discovery notes, meeting summaries, client feedback
- Re-synthesize insights with updated confidence and revised hypotheses
- Outputs evolve from pre-meeting prep to post-discovery POV

### v1.9.0 - POV and Narrative Evolution (Planned)

Goal: Make Primr the system of record for how thinking evolves.

- Versioned research artifacts
- Explicit "what changed and why" sections
- Optional narrative framing outputs for internal deck creation

## Scale Readiness (Intentional, Not Yet Implemented)

Primr is currently optimized for individual and small-team use, running locally with user-provided API keys. This is intentional so the focus remains on output quality and usefulness in real consulting workflows.

If organizational adoption increases, the expected evolution would be:

- **Execution model**: Transition from local to centralized, container-based job execution
- **Interface model**: Preserve CLI as primary interface
- **Reliability and cost control**: Shared caching, retries, scheduling
- **Governance**: Centralized prompt versions and configuration defaults

This evolution would be driven by demonstrated usage and clear internal demand, not speculative scaling.

## Explicitly Deferred (By Design)

These are conscious non-goals for now:

**Centralized Execution Infrastructure**
- Docker, Cloud Run, Container Apps
- Async job queues
- Multi-tenant execution

**Web Interface**
- Browser-based submission
- Job dashboards

**Collaboration and Sharing**
- Accounts, permissions, comments
- Sharing reports externally

## Usage Reference

```bash
# Basic usage
primr "Tesla" https://tesla.com

# Research modes
primr "Tesla" https://tesla.com --mode scrape
primr "Tesla" https://tesla.com --mode deep
primr "Tesla" https://tesla.com --mode full

# AI Strategy
primr "Tesla" https://tesla.com --cloud-vendor azure
primr "Tesla" https://tesla.com --no-ai-strategy

# Retry AI Strategy
primr --ai-strategy-only "output/Tesla_Strategic_Overview.md"

# Job management
primr --check-jobs
primr --clear-jobs

# Operations
primr doctor
primr "Tesla" https://tesla.com --dry-run

# MCP Server
primr-mcp --stdio
primr-mcp --http --port 8000
```

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 0.1.0 | Nov 2025 | Core research pipeline |
| 0.2.0 | Nov 2025 | Deep Research integration |
| 0.3.0 | Dec 2025 | Full mode (two-step) |
| 0.4.0 | Dec 2025 | AI Strategy generation |
| 0.5.0 | Dec 2025 | Cost tracking, job recovery |
| 1.0.0 | Dec 2025 | Rebrand to Primr, pip installable |
| 1.1.0 | Jan 2026 | Browser-first discovery, LLM link selection |
| 1.1.1 | Jan 2026 | Reader-mode extraction, vision tier |
| 1.2.0 | Jan 2026 | Test coverage, security review |
| 1.3.0 | Jan 2026 | Python 3.11+ requirement |
| 1.3.1 | Jan 2026 | File Search Store billing fix |
| 1.4.0 | Feb 2026 | MCP Server for AI agent integration |
| 1.4.1 | Feb 2026 | Open Claw integration |
| 1.5.0 | Feb 2026 | Code quality improvements |
| 1.5.1 | Feb 2026 | Code quality fixes, ruff compliance |
| 1.6.0 | TBD | QA-driven report iteration |

## Final Note

Primr is a tool for understanding companies. The focus is on useful output, not user growth.
