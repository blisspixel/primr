# Primr Roadmap

Current State: v1.7.0 (February 2026)

Primr is a CLI-first, local research tool for company intelligence and strategic analysis. It aims to accelerate research workflows while being transparent about uncertainty.

The design is intentionally opinionated and local-first. This roadmap reflects completed work and planned improvements. Some features work better than others, and the tool continues to evolve based on actual usage.

## What's Working Today

### Research Engines

**Scrape Mode**: 8-tier web scraping with intelligent escalation (browser-first):
- Browser tiers: Playwright, Playwright aggressive, DrissionPage stealth, DrissionPage (driverless CDP)
- HTTP tiers: curl_cffi (TLS fingerprint impersonation), httpx, requests
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

### Cloud Deployment (v1.6.0)

- Serverless job execution on AWS, Azure, GCP
- Job-based ephemeral containers (scale to zero)
- Event-driven queue boundary
- Production-grade observability and monitoring

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

### v1.6.0 - Serverless Cloud Deployment (Complete)

Goal: Enable scalable cloud deployment with job-based ephemeral execution.

**Core Infrastructure:**
- Job runner contract with manifest-as-commit pattern
- Artifact storage abstraction (S3, Blob, GCS)
- Control plane API (submit, status, cancel, results)
- Event-driven queue boundary (SQS FIFO, Service Bus, Pub/Sub)
- State reconciliation for stuck/orphaned jobs

**AWS (Primary - Production Ready):**
- Lambda control plane + Fargate job runner
- ECR lifecycle policy (keep last 10 images)
- S3 lifecycle rules (IA transition, version cleanup)
- SQS dead-letter queue for failed messages
- Step Functions with least-privilege IAM roles
- X-Ray tracing on reconciler Lambda
- CloudWatch alarms: Lambda errors, DynamoDB throttling, DLQ messages, queue age

**Azure (Reference Implementation):**
- Container Apps control plane + Container Apps Jobs runner
- Cosmos DB autoscale (400-4000 RU/s)
- Managed identity with RBAC roles (Cosmos DB, Storage, Key Vault)
- Application Insights for monitoring and tracing

**GCP (Reference Implementation):**
- Cloud Run control plane + Cloud Run Jobs runner
- Dedicated service account (not default App Engine SA)
- Least-privilege IAM roles (Firestore user, GCS viewer, Run invoker)
- Firestore composite indexes for efficient reconciler queries
- Cloud Scheduler with dedicated service account for OIDC auth

**Security:**
- Comprehensive SSRF protection (RFC1918, metadata IPs, DNS rebinding)
- Per-API-key rate limiting and quota enforcement
- Secrets management via cloud secret managers (runner only)
- Control plane requires NO LLM keys

**Observability:**
- OpenTelemetry tracing with job_id correlation
- Structured JSON logging with sensitive data redaction
- Metrics: job duration, queue depth, success/failure rates

### v1.7.0 - Agentic Architecture (Complete)

Goal: Enable AI agents to drive research workflows with persistent memory and governance.

**Research Memory:**
- Hypothesis tracking with confidence levels (low, medium, high, validated)
- YAML persistence with file-per-company storage
- Expiration filtering and topic-based queries
- Cross-session learning and hypothesis evolution

**Roadmap API:**
- Programmatic access to ROADMAP.md for agent planning
- Version queries, dependency graphs, status filtering
- Cache invalidation based on file modification time
- JSON serialization for MCP integration

**Hook System:**
- Pre/post execution hooks for governance
- CostGuardHook: Budget enforcement with tracking
- SSRFGuardHook: URL validation using security module
- QAGateHook: Quality threshold enforcement
- Configurable error handling (log, raise, skip)

**Subagent Architecture:**
- Context-isolated subagents for pipeline stages
- ScraperSubagent: Delegates to fetch_web_content
- AnalystSubagent: Insight synthesis and hypothesis generation
- WriterSubagent: Report generation with citations
- QASubagent: Quality assessment and feedback

**Research Orchestrator:**
- Coordinates subagent lifecycle (scrape → analyze → write → qa)
- Context derivation between stages
- Hook integration for governance
- Partial result recovery on failure

**MCP Server Extensions:**
- `query_roadmap` tool for version/feature queries
- `get_hypotheses` and `save_hypothesis` tools
- `primr://roadmap`, `primr://memory/{company}`, `primr://context` resources

**Skills Directory:**
- `company-research`: Full pipeline workflow
- `scrape-strategy`: Tier selection heuristics
- `hypothesis-tracking`: Confidence management
- `qa-iteration`: Section refinement workflow

**CLAUDE.md Context Map:**
- Quick-start section for common agent tasks
- Architecture pointers and verification commands
- Negative constraints (what agents should NOT do)
- Token budget under 2000 tokens

**Property Tests:**
- 112 property-based tests validating correctness
- Hypothesis round-trip, expiration filtering, query filtering
- Hook execution order, blocking behavior, error handling
- Orchestrator lifecycle, context isolation, failure handling

## Near-Term Roadmap

### v1.8.0 - QA-Driven Report Iteration (Planned)

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

### v1.8.1 - Content Sanitization Layer (Complete)

Goal: Protect against prompt injection from scraped web content.

**Security Critical**: Required before v2.0.0 public release.

Problem: Scraped content flows directly into LLM prompts without sanitization. A malicious website could embed injection patterns like "IGNORE PREVIOUS INSTRUCTIONS" in their HTML.

Implementation:
- `ContentSanitizer` class in `src/primr/utils/content_sanitizer.py`
- Detection of control characters, Unicode normalization issues, and prompt injection patterns
- Three modes: BLOCK (reject content), STRIP (remove patterns), WARN (log only)
- Integration at summarization layer before LLM calls
- `ContentSanitizationHook` for agentic pipeline governance
- 75 comprehensive tests including property-based tests

Detection patterns (20+):
- Instruction override attempts ("ignore previous instructions")
- System prompt markers (SYSTEM:, [SYSTEM], <system>)
- Role manipulation ("you are now", "act as", "pretend to be")
- Output format manipulation ("output only", "respond exclusively")
- Jailbreak patterns (DAN mode, bypass mode)
- Hidden HTML comment instructions
- Prompt leaking attempts ("show me your system prompt")
- Conversation injection (User:, Human:)
- Context manipulation ("from now on")
- Debug mode attempts ("developer mode enabled")

## Medium-Term Roadmap

### v1.9.0 - Refinement and Learning Loop (Planned)

Goal: Support post-discovery learning without re-running everything from scratch.

- `primr refine` command accepting discovery notes, meeting summaries, client feedback
- Re-synthesize insights with updated confidence and revised hypotheses
- Outputs evolve from pre-meeting prep to post-discovery POV

**MCP Progress Subscriptions (Complete):**
- `wait_for_status_change(job_id, timeout)` tool for real-time progress updates
- Replaces polling-based `check_jobs` pattern for better UX
- Asyncio.Event-based state change notification in job store
- 5 async tests validating notification behavior

### v1.10.0 - POV and Narrative Evolution (Planned)

Goal: Make Primr the system of record for how thinking evolves.

- Versioned research artifacts
- Explicit "what changed and why" sections
- Optional narrative framing outputs for internal deck creation

### v1.11.0 - Interactive Research Mode (Complete)

Goal: Enable human-in-the-loop decisions during research.

**Orchestrator Enhancements:**
- `OrchestratorState.PAUSED` state for pipeline pause/resume
- `user_input_callback` in OrchestratorConfig for user interaction
- `enable_interactive`, `pause_on_error`, `pause_between_stages` config options
- `pause()` and `resume()` methods on orchestrator
- `_request_user_input()`, `_handle_stage_transition()`, `_handle_error_recovery()` methods
- `user_decisions` tracking in OrchestratorResult

**Hook System Enhancements:**
- `HookType.ERROR_RECOVERY` for error handling hooks
- `run_error_recovery_hooks()` method in HookSystem
- `InteractiveErrorRecoveryHook` for user-driven error recovery
- `mutable_data` and `user_input_callback` fields in HookContext

Use cases:
- Approve high-cost operations before execution
- Choose between research directions at decision points
- Provide domain expertise when AI is uncertain
- Review and edit hypotheses mid-pipeline
- Handle recoverable errors with user guidance

### v2.0.0 - Public Release (Planned)

Goal: Make Primr available to the broader community via PyPI.

**Prerequisites:**
- v1.8.1 Content Sanitization Layer (security critical)

**Scope:**
- PyPI publication (`pip install primr`)
- Public GitHub repository
- GitHub Actions CI/CD for automated testing
- Contribution workflow for external contributors
- Documentation site

## Scale Readiness (Implemented in v1.6.0)

Primr now supports serverless cloud deployment for organizational adoption:

- **Execution model**: Job-based ephemeral containers (Fargate/Container Apps/Cloud Run Jobs)
- **Interface model**: REST API control plane + CLI preserved for local use
- **Reliability**: Event-driven queues, dead-letter handling, state reconciliation
- **Cost control**: Scale-to-zero, per-API-key quotas, cost estimation on submit
- **Governance**: Centralized secrets management, audit logging, manifest trail

See [docs/CLOUD_DEPLOYMENT.md](docs/CLOUD_DEPLOYMENT.md) for deployment guide.

## Explicitly Deferred (By Design)

These are conscious non-goals for now:

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

# Cloud Deployment
cd deploy/aws && ./deploy.sh -d prod deploy
cd deploy/aws && ./deploy.sh -d prod destroy
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
| 1.5.1 | Feb 2026 | Security hardening, API key rotation |
| 1.6.0 | Feb 2026 | Serverless cloud deployment (AWS/Azure/GCP) |
| 1.7.0 | Feb 2026 | Agentic architecture (memory, hooks, orchestrator) |

## Final Note

Primr is a tool for understanding companies. The focus is on useful output, not user growth.

## Disclaimer

**Legal Compliance**: Users are responsible for ensuring their use of Primr complies with applicable laws, website terms of service, and robots.txt directives. Web scraping may be restricted or prohibited by certain websites. The authors do not endorse or encourage scraping sites that prohibit it.

**Accuracy**: Primr uses AI models that may produce inaccurate, incomplete, or hallucinated information. All outputs should be treated as hypotheses requiring human verification, not facts. Do not make business decisions based solely on Primr outputs without independent validation.

**Costs**: Primr makes API calls to third-party services (Gemini, Google Search) that incur real monetary charges. Cost estimates are approximate. Users are responsible for monitoring their own API usage and costs.

**No Warranty**: This software is provided "as is" without warranty of any kind. The authors are not liable for any damages, costs, or legal issues arising from use of this software.

**Intended Use**: Primr is designed for legitimate internal research and due diligence purposes. It is not intended for competitive intelligence gathering that violates laws or ethical standards, mass surveillance, or any malicious purpose.
