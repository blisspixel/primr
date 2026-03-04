# Primr Roadmap

Current State: v1.12.1 (February 2026, plus unreleased hardening and mode changes)

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

**Pro Models**: Gemini 3.1 Pro for section writing and analysis in premium mode.

**Standard Mode** (default when `XAI_API_KEY` set): Grok 4.1 pipeline with research deepening, parallel section writing, cross-validation, coherence pass, and strategy enrichment. ~30 min, ~$0.55. Formerly called "fast mode."

**Premium Mode** (`--premium`): Gemini + Deep Research pipeline for maximum depth. ~50-75 min, ~$5. Formerly the default "full" mode.

**Full Mode**: Auto-detects — uses standard (Grok) when `XAI_API_KEY` is set, otherwise falls back to Gemini pipeline

### Resource Management (v1.3.1)

- Automatic cleanup of Gemini File Search Stores after each run
- `primr doctor` checks for orphaned resources that could incur costs
- Manual cleanup script: `"<python-executable>" scripts/check_gemini_resources.py --delete-stores --force-empty`
  - Example on Windows: `"C:\Users\you\AppData\Local\Programs\Python\Python313\python.exe" scripts/check_gemini_resources.py --delete-stores --force-empty`

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
- Strategy enrichment: cross-validation, evidence search, section regeneration, and polish pass (same quality treatment as reports)

### Operational Maturity

- Cost estimation with confirmation (--dry-run)
- Usage tracking and job recovery
- System diagnostics (primr doctor)
- Test coverage
- Cross-platform runtime support (Windows, macOS, Linux) for CLI, scraping, and report generation

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
- Deterministic verification before AI judgment — check structure, citations, and epistemic labels with code before asking a model to score prose quality (validated by SkillsBench research, arXiv:2602.12670)
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
- Design principles: focused > monolithic (94-116 lines, 2-5 tools each), human-curated only, don't skill what the model already knows (validated by SkillsBench, arXiv:2602.12670)

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
- Fixed MCP company name extraction truncating multi-word names (`"ExampleCo_Company_..."` -> `"ExampleCo"` instead of `"ExampleCo Company"`)

### Post-v1.12.1 - Reliability, Maintainability, and Model Updates (Unreleased)

Goal: Reduce noisy integration-runtime warnings, improve maintainability in AI runtime modules, and register new Gemini models.

**Deep Research Refactor:**
- Extracted shared deep research parsing helpers to `src/primr/ai/deep_research_parsing.py`
- Extracted adaptive polling policy helpers to `src/primr/ai/deep_research_polling.py`
- Extracted shared polling execution engine to `src/primr/ai/deep_research_execution.py`
- Refactored polling loops in deep research clients/orchestrators to use shared execution logic
- Enforced `store=True` for background Deep Research interactions to support durable async recovery after local process interruption
- Improved `primr --check-jobs` diagnostics to separate provider terminal failures from local status-check connectivity errors
- Added `primr --resume-latest` / `--resume-jobs` one-shot recovery flow to finalize canonical MD/TXT/DOCX outputs from completed cloud jobs
- Added `--resume-local` to reuse latest incomplete local working folders for the same company
- Added richer pending-job metadata capture (company/vendor/report kind) so recovered files use business-safe names instead of generic `recovered_*`
- Added per-run `_run_state.json` phase/status timeline in each working folder for reboot-safe local state inspection

**AI Error Policy Refactor:**
- Extracted shared error classification policy to `src/primr/ai/error_policy.py`
- Unified sync/async AI client retry classification through the shared policy module

**Flaky/Integration Warning Reduction:**
- Added a dedicated pass to reduce noisy integration-runtime warnings in constrained environments
- Hardened handling around Playwright subprocess permission constraints in tests
- Hardened handling around network-restricted AI integration tests to avoid misleading warning noise

**Scraping Reliability Hardening:**
- Added adaptive lazy-load scrolling for Playwright tiers (up to 20 steps, early stop when page height stabilizes)
- Added strict scrape-quality validation gate in scrape/full pipelines (fail fast on thin extraction)
- Added explicit override flag: `--skip-scrape-validation`
- Added `_raw_scrapes/_scrape_trace.log` with per-page `OK/FAIL/DUP` outcomes for debugging
- Updated progress line to show attempted pages and successful pages separately (e.g., `Scraping 23/50 (ok 17) ...`)
- Added external search caps via config: `MAX_EXTERNAL_SEARCH_QUERIES`, `MAX_EXTERNAL_SOURCES`

**Gemini 3.1 Pro Preview (February 2026):**
- Registered `gemini-3.1-pro-preview` and `gemini-3.1-pro-preview-customtools` in ModelRegistry
- Now the default Pro model (cost delta ~$0.28/run vs 3.0 Pro — negligible since DR dominates cost)
- Override via `AI_REASONING_MODEL=gemini-3-pro-preview` to revert
- Improvements: better thinking, token efficiency, factual consistency, agentic workflow optimization
- Tiered pricing: $2/$12 per 1M (prompts <=200k) | $4/$18 per 1M (prompts >200k)
- `customtools` variant optimized for tool-heavy workflows (prioritizes custom tools over bash)

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

**Versioned Eval Workflow (Initial):**
- Added `primr --eval` command for offline, versioned profile comparison (`full`, `lite`, `fast`)
- Generates scorecards at `output/evals/<eval-id>/scorecard.md` and `scorecard.csv`
- Tracks per-profile trust, decision utility, reuse quality, utility-per-dollar, and cost ratios against baseline
- Adds a deterministic trust gate (citation coverage + section completeness + confidence labels) before profile pass/fail
- Auto-stages existing local reports into eval profile folders (no API spend), with optional company targeting (`--eval-company`)
- Writes `staging_manifest.json` to preserve exactly which artifacts were compared
- Optional `--eval-run-missing` can execute missing runs, gated by explicit caps:
  - `--eval-max-new-runs`
  - `--eval-max-estimated-cost`

### Fast Mode Default + Quality Improvements (Unreleased)

Goal: Make the Grok 4.1 pipeline the default and improve report quality.

**Motivation:** Fast mode now matches full mode on QA score (89 vs 89), has more external sources (38 vs 8), similar page count (~40 vs ~39), and costs 88% less ($0.57 vs $5.00). The quality gap has closed enough to make fast mode the default.

**Mode Renaming:**
- Default `primr` command now auto-detects: uses Grok 4.1 when `XAI_API_KEY` is set, falls back to Gemini otherwise
- Added `--premium` flag to explicitly request Gemini + Deep Research pipeline
- `--fast` retained for backward compatibility (no-op when `XAI_API_KEY` already set)
- MCP server tools accept `"premium"` mode alongside `"scrape"`, `"deep"`, `"full"`
- Pipeline runner auto-dispatches to fast pipeline for `"full"` mode when `XAI_API_KEY` available
- Cost estimator labels updated: "standard (Grok 4.1)" for default, "premium" for Gemini+DR

**Quality Improvements:**
- **Coherence pass fix**: Rewrote prompt to be surgical (cross-references only, not content deletion). Added explicit 95% word budget, acceptable/unacceptable edit examples. Increased `max_tokens` from 25K to 32K. Tightened guard threshold from 0.85 to 0.92.
- **Executive summary written last**: Exec summary now written after all other sections, with full report context for true synthesis. Previously written first with zero prior context.
- **Parallel external source search**: Phase 1 and Phase 2 search loops parallelized with `ThreadPoolExecutor(max_workers=3)`. Expected speedup: Phase 1 from ~14 min to ~5-6 min, Phase 2 from ~8 min to ~3-4 min.
- **Robust cross-validation JSON parsing**: On parse failure, retries with tighter prompt including failed response. Falls back to regex extraction of title/reason fields as last resort.
- **Framework section word targets**: Raised from 600 to 800 words (sections were consistently producing 700-900 anyway).

**Strategy Enrichment Pass:**
- Strategy documents now go through the same quality treatment as reports: cross-validation to identify weak sections, targeted DDG search for evidence, section regeneration with new evidence, and a polish pass for coherence and evidence discipline
- Cross-validation tuned for strategy-specific weaknesses: unsupported vendor claims, generic recommendations, missing company-specific details
- Up to 2 weak sections identified and re-written per strategy document
- Polish pass deduplicates, standardizes vendor references, adds confidence labels, and checks specificity
- Guarded at every step: CV failure skips enrichment, regen failure keeps original section, polish failure keeps unpolished content
- Strategy `max_tokens` raised from 16K to 32K (Grok supports 131K; strategies were being truncated)
- Strategy context enriched with `insights.txt`, `gap_analysis.md`, and `analysis_workbook.md` from earlier pipeline phases
- Per-vendor strategy cost: ~$0.03 to ~$0.07. Per-vendor time: 2-3 min to 3-6 min
- Phase 6 banner updated from "2-5 min" to "3-8 min"

**All Strategy Types in Fast Mode:**
- `--strategy-type` now works during research runs (not just `--ai-strategy-only`)
- Non-AI strategy types (customer_experience, modern_security_compliance, data_fabric_strategy) run via Grok in Phase 6, using YAML-based prompts
- Strategy YAML configs auto-discovered at runtime from `src/primr/prompts/strategies/`
- `--list-strategies` dynamically reads YAML metadata (name, description, expected pages)
- `_save_strategy_output` uses strategy-specific filenames from YAML `output_filename` field

**Files Modified:**
- `src/primr/core/research_agent.py` — coherence prompt, exec summary last, parallel search, cross-val retry, word targets, premium_mode dispatch, generalized Phase 6 for all strategy types, strategy enrichment pass (cross-validate, evidence search, regen, polish)
- `src/primr/core/cli.py` — `--premium` flag, `CLIConfig.premium_mode`, `MODE_MAP`, auto-detect logic, dynamic `--strategy-type` choices/help from YAML, dynamic `--list-strategies`
- `src/primr/utils/cost_estimator.py` — `premium_mode` param, display labels
- `src/primr/mcp_server/types.py` — `PREMIUM` enum member
- `src/primr/mcp_server/tools.py` — tool schema enums + descriptions
- `src/primr/mcp_server/pipeline_runner.py` — fast mode dispatch for "full"
- `CLAUDE.md` — updated examples, costs, MCP docs

### Agentic Pipeline + Report Quality + New Sections (Unreleased)

Goal: Make the pipeline more agentic, fix quality bugs, improve UX, and add new report sections.

**Bug Fixes:**
- **Duplicate section elimination**: Section writing now deduplicates by title — if Grok hallucinates a section that already exists, it is dropped with a warning instead of appearing twice in the report
- **Coherence pass rewrite**: Prompt completely rewritten to be minimally invasive (terminology, cross-references, transitions only). Guard threshold raised from 0.92 to 0.96. Eliminates the catastrophic word-loss bug (19,000 → 1,300 words)
- **Contradiction resolution**: Contradictions detected during cross-validation are now resolved by standardizing conflicting values across sections, preferring best-sourced data. Previously only logged

**UX Improvements:**
- **Domain in progress**: "Scanning website" now shows the actual domain (e.g., "Scanning northgatemarket.com"). Phase subtitle also shows the domain
- **Cleaner mode message**: "Using fast mode (Grok 4.1) — XAI_API_KEY detected..." replaced with "Using Grok 4.1 · for deeper research add --premium"
- **Search sub-progress**: External source search and gap-filling search now show live progress (queries completed, results found, sources validated) instead of a static spinner during 15+ minute phases

**Agentic Behavior:**
- **Adaptive search depth**: After scraping, assesses data richness. Rich websites (>200K chars, 30+ pages) get reduced external search (10 queries, 20 sources). Thin websites (<20K chars, <5 pages) get increased search (15 queries, 40 sources)
- **Source quality filtering**: LLM reviews all collected external sources and drops low-relevance ones. Prefers 5 high-quality sources over 25 mediocre ones, especially for less prominent companies
- **Dynamic section selection**: Before writing, checks if analysis workbook contains evidence keywords for each section. Sections with zero evidence signals (e.g., Financial Profile when no financial data found) are skipped with a notice

**New Report Sections (23 total, up from 21):**
- **Industry Outlook** (part 2): Near-term (6-12mo), medium-term (1-3yr), long-term (3-5yr) industry trends with positioning assessment. Includes timeline table
- **Strategic Leadership Perspective** (part 4): Simulated board meeting — builds executive personas from public data, debates findings from CEO/CFO/CTO/board perspectives, identifies alignment and tension points

**Stronger QA Gate:**
- Fast QA now checks for duplicate section headings and thin sections (<100 words) in addition to confidence labels, citations, and validation prompts
- QA gate fails if duplicates or thin sections detected
- Display includes `dupes=` and `thin=` counts when issues found

**Search Query Improvements:**
- External search queries now explicitly target industry trends/outlook and executive/board information
- Ensures at least 2 industry trend queries and 1 leadership query per run

**Files Modified:**
- `src/primr/core/research_agent.py` — duplicate dedup, coherence rewrite, domain progress, sub-progress, adaptive depth, source quality filter, contradiction resolution, dynamic sections, QA gate
- `src/primr/core/cli.py` — cleaner mode message
- `src/primr/data/search_utils.py` — industry/leadership search queries
- `src/primr/prompts/company_overview.yaml` — Industry Outlook, Strategic Leadership Perspective sections
- `README.md` — updated sample output
- Tests updated for 23-section count

## Near-Term Roadmap

### v1.13.0 - QA-Driven Report Iteration (Planned)

Goal: Use QA feedback to iteratively improve weak sections until reports hit 90+.

**Deterministic Verification (Complete):**

Added code-level quality checks that run before (or instead of) AI-based scoring, validated by SkillsBench research (arXiv:2602.12670) showing deterministic checks outperform model-only evaluation for structural quality:

- **Hypothesis coverage**: Counts `(Hypothesis)` labels and validation phrases (`we hypothesize`, `to validate`, `worth validating`) with report-type thresholds
- **Confidence labels**: Counts all four epistemic labels `(Confirmed)`, `(Reported)`, `(Estimated)`, `(Hypothesis)` plus hedging phrases from `epistemic_rules.yaml`
- **Section length analysis**: Flags truncated sections (< 50 words) that indicate incomplete generation
- **Citation density**: Citations per 1000 words with type-specific thresholds (3.0 strategic, 2.0 AI strategy)
- **Report-type-aware structure**: Different required-section checklists for strategic_overview vs ai_strategy
- `QAGateHook` upgraded from 3 inline checks to `ReportAnalyzer`-backed scoring (6 checks, penalty system)
- `QASubagent` expanded from 5 to 7 quality dimensions with new `hypothesis_framing` and `confidence_labels` scores

**Iteration Workflow (Planned):**
1. Generate report
2. Run QA, get feedback on specific weak sections
3. Re-run just those sections with targeted improvements
4. Repeat until grade >= 90

Implementation:
- `primr refine "Company"` command to re-run weak sections
- QA identifies specific sections needing work
- Section-level regeneration without full pipeline re-run

### v1.13.1 - Versioned Model Evaluation Harness (Planned)

Goal: Make model/profile upgrades measurable and repeatable before changing defaults.

Problem this solves:
- New model releases (for example Pro/Flash/Grok variants) are hard to compare consistently
- Teams need a defensible quality/cost decision, not anecdotal "looks better"

Planned capabilities:
- `primr eval` workflow to run a fixed company corpus across profiles (for example `full`, `full --lite`, `--fast`)
- Versioned evaluation IDs (for example `eval-2026-02-r1`) with immutable run manifests
- Aggregated scorecard per profile:
  - Cost (estimated and actual)
  - Runtime
  - Document length (words/pages)
  - Citation density
  - Required-section completeness
  - Confidence-label coverage
- Side-by-side comparison output (Markdown + CSV) for baseline vs candidate profiles
- Configurable acceptance gates (example: quality >= 80% baseline and cost <= 20% baseline)
- CI guard for regression detection on a lightweight fixture corpus

Success criteria:
- Model default changes are backed by saved scorecards, not one-off manual judgment
- Users can answer "is this new model worth it?" in one command with reproducible evidence

### v1.13.2 - OpenAI Deep Research Integration (Planned)

Goal: Add OpenAI's Deep Research API as an alternative research backend, giving users a third provider option alongside Grok and Gemini.

**Motivation:** OpenAI's Deep Research API offers a different cost/depth/speed tradeoff. Adding it unlocks better defaults — the eval harness (v1.13.1) can determine which provider wins at each tier (quick, standard, premium) based on real data instead of assumptions.

**Research Tiers:**
- **Quick**: Lightweight OpenAI Deep Research call for fast external research (potential replacement for DDG search + scrape in standard mode)
- **Full**: Full-depth OpenAI Deep Research for comprehensive analysis (potential `--premium` alternative to Gemini DR)

**Implementation:**
- `OPENAI_API_KEY` env var support
- OpenAI Deep Research client in `src/primr/ai/`
- `--provider openai` flag (or auto-detect from available keys)
- Cost estimator updated with OpenAI DR pricing
- Shared deep research parsing/polling modules extended for OpenAI response format

**Decision:** Which tier(s) OpenAI DR best serves (quick, standard, premium) will be determined by eval results from v1.13.1, not by assumption.

### v1.13.3 - Cross-Provider Eval and Tier Optimization (Planned)

Goal: Extend the eval harness to compare all available providers and determine the best default for each research tier.

**Motivation:** With three providers (Grok, Gemini, OpenAI), the eval system should answer: what's the best option for quick runs, standard runs, and premium runs? These answers should be data-driven, not hardcoded.

**Planned capabilities:**
- Eval profiles expanded: `grok-standard`, `gemini-premium`, `openai-quick`, `openai-full`, etc.
- Cross-provider scorecard: quality, cost, runtime, citation density compared side-by-side
- Tier recommendation output: "For quick: use X, for standard: use Y, for premium: use Z"
- Auto-detect available API keys and only eval providers the user has access to
- Historical eval tracking: compare across eval IDs to see if a provider improved over time

**Success criteria:**
- `primr eval` can answer "which provider should be my default?" with evidence
- Tier defaults (quick/standard/premium) are backed by saved scorecards across providers

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

### v1.16.0 - A2A Protocol Integration (Planned)

Goal: Enable Primr to participate in the Agent-to-Agent (A2A) mesh — both as a callable research agent and as a client that delegates to external agents.

**A2A Server (Primr as an A2A agent):**
- AgentCard served at `/.well-known/agent.json` describing Primr's research skills
- A2A JSON-RPC endpoint for `message/send` and `message/stream`
- Skills: `estimate_research`, `research_company`, `check_jobs`, `run_qa`, `system_health`
- SSE streaming for long-running research jobs
- Shares `SingleJobStore` with MCP server (single-job model enforced across both protocols)
- Standalone `primr-a2a` CLI or `primr-mcp --a2a` co-hosted mode

**A2A Client (Primr calls external agents):**
- `delegate_to_agent` MCP tool for calling external A2A agents
- Agent discovery via `/.well-known/agent.json`
- `A2AExternalAgentHook` for SSRF validation and cost budget on delegations
- `A2AContentSanitizationHook` for prompt injection protection on external responses

**Optional dependency:** `pip install primr[a2a]` (a2a-sdk). Existing installs unaffected.

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
# Basic usage (auto-uses Grok 4.1 when XAI_API_KEY set)
primr "ExampleCo" https://example.co

# Research modes
primr "ExampleCo" https://example.co --mode scrape
primr "ExampleCo" https://example.co --mode deep
primr "ExampleCo" https://example.co --premium  # Gemini + Deep Research

# AI Strategy
primr "ExampleCo" https://example.co --cloud-vendor azure
primr "ExampleCo" https://example.co --cloud-vendor aws azure  # Multi-vendor
primr "ExampleCo" https://example.co --no-ai-strategy

# Retry AI Strategy
primr --ai-strategy-only "output/ExampleCo_Strategic_Overview.md"

# Job management
primr --check-jobs
primr --clear-jobs

# Operations
primr doctor
primr "ExampleCo" https://example.co --dry-run

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
| unreleased | Feb 2026 | Deep-research refactor, scrape reliability hardening, shared error policy, warning reduction |
| unreleased | Mar 2026 | Fast mode as default, `--premium` flag, quality improvements (coherence, exec summary, parallel search, cross-val), strategy enrichment pass |

## Final Note

Primr is a tool for understanding companies. The focus is on useful output, not user growth.

## Disclaimer

**Legal Compliance**: Users are responsible for ensuring their use of Primr complies with applicable laws, website terms of service, and robots.txt directives. Web scraping may be restricted or prohibited by certain websites. The authors do not endorse or encourage scraping sites that prohibit it.

**Accuracy**: Primr uses AI models that may produce inaccurate, incomplete, or hallucinated information. All outputs should be treated as hypotheses requiring human verification, not facts. Do not make business decisions based solely on Primr outputs without independent validation.

**Costs**: Primr makes API calls to third-party AI services (Gemini, Grok) that incur real monetary charges. Web search uses DuckDuckGo by default (free). Cost estimates are approximate. Users are responsible for monitoring their own API usage and costs.

**No Warranty**: This software is provided "as is" without warranty of any kind. The authors are not liable for any damages, costs, or legal issues arising from use of this software.

**Intended Use**: Primr is designed for legitimate research purposes — understanding companies, evaluating opportunities, and making informed decisions. It is not intended for competitive intelligence gathering that violates laws or ethical standards, mass surveillance, or any malicious purpose.
