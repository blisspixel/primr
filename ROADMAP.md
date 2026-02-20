# Primr Roadmap

Current State: v1.12.1 (February 2026, plus unreleased hardening)

Primr is a CLI-first, local research tool for company intelligence and strategic analysis. It aims to accelerate research workflows while being transparent about uncertainty.

The design is intentionally opinionated and local-first. This roadmap reflects completed work and planned improvements. Some features work better than others, and the tool continues to evolve based on actual usage.

## What's Working Today

### Research Engines

**Scrape Mode**: 8-tier web scraping with intelligent escalation (browser-first):
- Browser tiers: Playwright, Playwright aggressive, DrissionPage stealth, DrissionPage (driverless CDP)
- Vision tier: Screenshot + LLM extraction for image-heavy pages (enabled by default, can be disabled)
- HTTP tiers: curl_cffi (TLS fingerprint impersonation), httpx, requests
- Content-type routing: automatic PDF detection and LLM-powered extraction with PyMuPDF fallback
- Reader-mode content extraction (BeautifulSoup-based, removes boilerplate)
- Content quality validation (catches garbage pages, triggers escalation)
- Homepage-first link discovery (fresher than sitemaps)
- Sticky tier optimization (reuses working tier for same host)
- Circuit breaker pattern (skips failing tiers after 3 failures)
- Soft block detection (catches "200 OK" traps, browser blocks)

**Deep Mode**: Gemini Deep Research Agent with autonomous multi-step search and synthesis

**Pro Models**: Gemini 3 Pro (default) for section writing and analysis. Gemini 3.1 Pro Preview available for opt-in testing with improved reasoning and factual consistency.

**Fast Mode**: Grok 4.1 accordion-style batch writing — analysis workbook + 5-batch report in 10-17 min

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
- Multi-vendor support: `--cloud-vendor aws azure` generates separate strategy documents per vendor in a single run
- Cloud vendor options: Azure, AWS, GCP, agnostic
- Multiple strategy types: AI, Customer Experience, Security, Data Fabric
- Vendor-tagged output filenames (e.g., `Company_AI_Strategy_AWS_02-11-2026.docx`)

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

Primr is designed around a few core principles:

- Structured output over raw data — briefs you can act on, not link dumps
- Hypothesis generation over premature conclusions — confidence levels on every claim
- Transparency about uncertainty — what's confirmed, what's inferred, what's speculation
- Local-first, CLI-first — your data stays on your machine

Primr is intentionally not designed as:

- A generic web scraper
- A SaaS collaboration platform
- A presentation builder

These design constraints help maintain focus on the core purpose: turning a URL into useful intelligence.

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
- Hypothesis tracking with confidence levels (untested, validated, invalidated, confirmed)
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
- Coordinates subagent lifecycle (scrape -> analyze -> write -> qa)
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

### v1.8.1 - Content Sanitization Layer (Complete)

Goal: Protect against prompt injection from scraped web content.

**Security Critical**: Required before v2.0.0 public release.

**Content Sanitizer:**
- `ContentSanitizer` class in `src/primr/utils/content_sanitizer.py`
- Three modes: BLOCK (reject), STRIP (remove patterns), WARN (log only)
- Detection of control characters, Unicode normalization issues
- 20+ prompt injection detection patterns

**Detection Patterns:**
- Instruction override attempts ("ignore previous instructions")
- System prompt markers (SYSTEM:, [SYSTEM], <system>)
- Role manipulation ("you are now", "act as", "pretend to be")
- Output format manipulation ("output only", "respond exclusively")
- Jailbreak patterns (DAN mode, bypass mode)
- Hidden HTML comment instructions
- Prompt leaking attempts ("show me your system prompt")
- Conversation injection (User:, Human:)
- Context manipulation ("from now on")

**Integration:**
- Integrated at summarization layer before LLM calls
- `ContentSanitizationHook` for agentic pipeline governance
- 75 comprehensive tests including property-based tests

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

**Expanded External Search Coverage:**
- LLM-generated search queries (7 targeted queries per company) replace 2 hardcoded queries
- Target raised from 3 to 8 validated external sources
- Covers news, funding, technology stack, leadership, competitive landscape, industry analysis, and financial performance
- Hardcoded queries retained as fallbacks (news, funding, financials)
- CLI preflight respects SEARCH_PROVIDER setting (no longer requires Google API keys when using DuckDuckGo)

**MCP Progress Subscriptions:**
- `wait_for_status_change(job_id, timeout)` tool for real-time progress updates
- Replaces polling-based `check_jobs` pattern for better UX
- Asyncio.Event-based state change notification in job store

**Use Cases:**
- Approve high-cost operations before execution
- Choose between research directions at decision points
- Provide domain expertise when AI is uncertain
- Review and edit hypotheses mid-pipeline
- Handle recoverable errors with user guidance

### v1.11.1 - Deep Research Progress and Failure Recovery (Complete)

Goal: Fix silent progress and silent failures during Deep Research phase.

**Progress Visibility:**
- Progress callback now shows periodic updates every 2 minutes even when phase name is unchanged (was going silent after "Finalizing" phase)
- Sub-status messages (e.g., "Uploading Stage 1 context") now forwarded to console instead of being silently filtered
- Heartbeat interval reduced from 90s to 30s for more frequent activity indication
- Heartbeat display uses terminal width instead of hardcoded 60 characters (fixes partial overwrite artifacts)
- Diagnostic logging every 5 polls in deep research polling loop

**Failure Recovery:**
- Full exception tracebacks now logged in orchestrator (were being discarded)
- Partial results from structured phase preserved when deep research fails (were being thrown away)
- Prominent failure message with actionable tips shown to user on failure
- Working folder retains scraped data and partial sections instead of appearing empty

### v1.11.2 - Scraping Performance and UI Polish (Complete)

Goal: Improve scraping throughput with shared browser sessions, add ETA progress, and clean up console output.

**Scraping Performance:**
- SharedBrowser: Single browser instance shared across all pages in a scraping session (reduces memory and startup overhead)
- ETA progress: Real-time estimated time remaining during scraping (`Scraping 23/50 /about [15s elapsed, ~2m left]`)
- DOM protections: Graceful handling of dynamic DOM mutations during content extraction

**Console UI Polish:**
- Removed heartbeat that was firing during Phase 1 scraping (overlapped with existing progress updates)
- Suppressed experimental API warnings from Genai SDK during Deep Research interactions
- Downgraded expected SSRF blocks and content sanitization from WARNING to INFO log level (no longer clutters stderr)
- Fixed phase numbering jump (2 -> 5 now correctly goes 2 -> 3 in complete mode)
- Removed internal jargon message "Running structured research pipeline..." from console output
- Fixed "Sections" label -> "Chapters" for consistency with report structure
- Fixed citation count always showing 0 (broken import path; now counts `[cite: N]` patterns from generated content)

### v1.12.0 - Multi-Cloud-Vendor AI Strategy (Complete)

Goal: Generate separate AI strategy documents for multiple cloud vendors in a single run.

**Multi-Vendor CLI:**
- `--cloud-vendor` now accepts multiple values: `--cloud-vendor aws azure`
- Deduplicates vendors while preserving order
- Backward compatible: single vendor still works the same way

**Efficient Pipeline:**
- Scraping and deep research run once (vendor-agnostic)
- Only the AI strategy step loops per vendor
- Cost estimator accounts for multiple vendor runs

**Vendor-Tagged Output:**
- Filenames include vendor tag: `Company_AI_Strategy_AWS_02-11-2026.docx`
- Each vendor gets its own vendor research context
- Phase banners show vendor name for multi-vendor runs

**Backward Compatibility:**
- `CLIConfig.cloud_vendor` property still returns first vendor for existing code
- Single-vendor usage unchanged
- MCP server unchanged (future work)

### v1.12.1 - Scraping Robustness and Bug Fixes (Complete)

Goal: Improve content handling, scraping throughput, and fix resource management bugs.

**Content-Type Routing:**
- Orchestrator detects content type from HTTP headers and magic bytes (HTML, PDF, JSON, XML, binary)
- PDF content routed to Gemini LLM extraction with PyMuPDF fallback
- Binary content (images, fonts) rejected early instead of crashing BeautifulSoup
- BeautifulSoup wrapped in try/except for malformed HTML resilience

**Scraping Performance:**
- Background file I/O: Raw scrape files written via ThreadPoolExecutor (non-blocking)
- Structured content caching: Avoids duplicate HTML extraction between scraping and boilerplate learning phases
- Removed inter-page random delay (rate limiter already handles pacing)
- Smart page timeout: Reduced from 45s to 25s when best_tier is known for a host

**Bug Fixes:**
- Fixed ThreadPoolExecutor resource leak in scraping loop (try/finally ensures shutdown)
- Fixed MCP company name extraction truncating multi-word names (`"Acme_Corp_..."` -> `"Acme"` instead of `"Acme Corp"`)

### Post-v1.12.1 - Reliability, Maintainability, and Model Updates (Unreleased)

Goal: Reduce noisy integration-runtime warnings, improve maintainability in AI runtime modules, and register new Gemini models.

**Deep Research Refactor:**
- Extracted shared deep research parsing helpers to `src/primr/ai/deep_research_parsing.py`
- Extracted adaptive polling policy helpers to `src/primr/ai/deep_research_polling.py`
- Extracted shared polling execution engine to `src/primr/ai/deep_research_execution.py`
- Refactored polling loops in deep research clients/orchestrators to use shared execution logic

**AI Error Policy Refactor:**
- Extracted shared error classification policy to `src/primr/ai/error_policy.py`
- Unified sync/async AI client retry classification through the shared policy module

**Flaky/Integration Warning Reduction:**
- Added a dedicated pass to reduce noisy integration-runtime warnings in constrained environments
- Hardened handling around Playwright subprocess permission constraints in tests
- Hardened handling around network-restricted AI integration tests to avoid misleading warning noise

**Gemini 3.1 Pro Preview (February 2026):**
- Registered `gemini-3.1-pro-preview` and `gemini-3.1-pro-preview-customtools` in ModelRegistry
- Available for opt-in testing via `AI_REASONING_MODEL=gemini-3.1-pro-preview` in `.env`
- NOT yet default — pending cost validation on real research runs
- Improvements: better thinking, token efficiency, factual consistency, agentic workflow optimization
- Tiered pricing: $2/$12 per 1M (prompts <=200k) | $4/$18 per 1M (prompts >200k)
- `customtools` variant optimized for tool-heavy workflows (prioritizes custom tools over bash)
- Default remains `gemini-3-pro-preview` (flat $2/$12 pricing)

**Tiered Pricing Support:**
- `ModelConfig` now supports tiered pricing via optional fields: `cost_per_1m_input_tokens_high`, `cost_per_1m_output_tokens_high`, `tier_threshold_tokens`
- `has_tiered_pricing` property on `ModelConfig` for easy detection
- `PrimrModels.calculate_cost()` accepts optional `prompt_tokens` — uses high tier when prompt exceeds threshold
- `PrimrModels.calculate_cost_conservative()` — always uses highest tier for tiered models (for pre-run estimates)
- `PrimrModels.get_active_pro_model()` — reads the active Pro model from settings (honours `AI_REASONING_MODEL`)
- Cost estimator uses conservative (high-tier) pricing when a tiered model is active; adds note to estimates
- Usage tracker uses active Pro model pricing instead of hardcoded default
- AI client fallback pricing uses active Pro model instead of hardcoded default

**Validation:**
- Added targeted tests for new helper modules:
  - `tests/test_ai/test_deep_research_parsing.py`
  - `tests/test_ai/test_deep_research_polling.py`
  - `tests/test_ai/test_error_policy.py`
- Targeted deep-research and AI suites pass after refactor

## Near-Term Roadmap

### v1.13.0 - QA-Driven Report Iteration (Planned)

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

### v1.14.0 - Refinement and Learning Loop (Planned)

Goal: Support post-discovery learning without re-running everything from scratch.

- `primr refine` command accepting new information, notes, and follow-up findings
- Re-synthesize insights with updated confidence and revised hypotheses
- Outputs evolve as understanding deepens

### v1.15.0 - POV and Narrative Evolution (Planned)

Goal: Make Primr the system of record for how thinking evolves.

- Versioned research artifacts
- Explicit "what changed and why" sections
- Optional narrative framing outputs

### v2.0.0 - Public Release (Planned)

Goal: Make Primr available to the broader community via PyPI.

**Prerequisites:**
- v1.8.1 Content Sanitization Layer (complete - security requirement satisfied)

**Scope:**
- PyPI publication (`pip install primr`)
- Public GitHub repository
- ~~GitHub Actions CI/CD for automated testing~~ (done - lint, type check, tests run on every push)
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

## TODO: README Assets

These require running the tool and capturing output manually:

- [ ] Record a terminal GIF of a real research run (asciinema or vhs) for the top of the README
- [ ] Screenshot a DOCX report to show the formatted output
- [ ] Update `docs/images/primr-demo.png` with a current screenshot (existing one is from an older version)

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
primr "Acme Corp" https://acme.example

# Research modes
primr "Acme Corp" https://acme.example --mode scrape
primr "Acme Corp" https://acme.example --mode deep
primr "Acme Corp" https://acme.example --mode full

# AI Strategy
primr "Acme Corp" https://acme.example --cloud-vendor azure
primr "Acme Corp" https://acme.example --cloud-vendor aws azure  # Multi-vendor
primr "Acme Corp" https://acme.example --no-ai-strategy

# Retry AI Strategy
primr --ai-strategy-only "output/Acme_Corp_Strategic_Overview.md"

# Job management
primr --check-jobs
primr --clear-jobs

# Operations
primr doctor
primr "Acme Corp" https://acme.example --dry-run

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
| 1.3.1 | Jan 2026 | Resource cleanup, File Search Store billing fix |
| 1.4.0 | Feb 2026 | MCP Server for AI agent integration |
| 1.4.1 | Feb 2026 | Open Claw integration |
| 1.5.0 | Feb 2026 | Code quality improvements |
| 1.5.1 | Feb 2026 | Code quality fixes, full ruff compliance |
| 1.6.0 | Feb 2026 | Serverless cloud deployment (AWS/Azure/GCP) |
| 1.7.0 | Feb 2026 | Agentic architecture (memory, hooks, orchestrator) |
| 1.8.1 | Feb 2026 | Content sanitization for prompt injection protection |
| 1.11.0 | Feb 2026 | Interactive research mode (pause/resume, user callbacks) |
| 1.11.1 | Feb 2026 | Deep Research progress visibility and failure recovery |
| 1.11.2 | Feb 2026 | SharedBrowser, ETA progress, UI polish |
| 1.12.0 | Feb 2026 | Multi-cloud-vendor AI strategy |
| 1.12.1 | Feb 2026 | Scraping robustness, PDF routing, bug fixes |
| unreleased | Feb 2026 | Deep-research refactor, shared error policy, flaky warning reduction |

## Final Note

Primr is a tool for understanding companies. The focus is on useful output, not user growth.

## Disclaimer

**Legal Compliance**: Users are responsible for ensuring their use of Primr complies with applicable laws, website terms of service, and robots.txt directives. Web scraping may be restricted or prohibited by certain websites. The authors do not endorse or encourage scraping sites that prohibit it.

**Accuracy**: Primr uses AI models that may produce inaccurate, incomplete, or hallucinated information. All outputs should be treated as hypotheses requiring human verification, not facts. Do not make business decisions based solely on Primr outputs without independent validation.

**Costs**: Primr makes API calls to third-party AI services (Gemini, Grok) that incur real monetary charges. Web search uses DuckDuckGo by default (free). Cost estimates are approximate. Users are responsible for monitoring their own API usage and costs.

**No Warranty**: This software is provided "as is" without warranty of any kind. The authors are not liable for any damages, costs, or legal issues arising from use of this software.

**Intended Use**: Primr is designed for legitimate research purposes — understanding companies, evaluating opportunities, and making informed decisions. It is not intended for competitive intelligence gathering that violates laws or ethical standards, mass surveillance, or any malicious purpose.
