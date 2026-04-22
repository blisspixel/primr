# Changelog

All notable changes to Primr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Scraping Resilience — Routing Around Bot Protection

- **Recon moved to external `recon-tool` package**: the embedded `src/primr/recon/` module was deleted; primr now depends on the standalone `recon-tool` (PyPI) so recon work can evolve in its own repo. `primr recon <domain>` CLI shorthand still works via mount of `recon_tool.cli:app`. `dnspython` removed as a primr dependency (owned by recon-tool now).
- **Patchright stealth-browser tier** (`src/primr/data/scraping/stealth_browser.py`): real-Chrome + persistent per-host user-data-dir, bypasses Kasada / Akamai / PerimeterX challenges that blank plain Playwright. Two-phase: headless first, headed only if headless returns a challenge shell.
- **First-time browser install is automatic**: on first scrape that needs Patchright, primr runs `python -m patchright install chromium` in a subprocess with a one-line CLI notice. No manual setup required — baked into install.
- **Global headed-popup budget** (default 3 per run, override with `PRIMR_MAX_HEADED_POPUPS`): after the budget is exhausted, blocked pages fall through to public-data fallbacks without the visible-browser retry. Prevents popup spam on runs that hit dozens of protected pages.
- **Tiny, minimized, off-screen popup**: when Patchright does go headed, the Chrome window is resized to 320x200 via CDP, minimized to the taskbar, and positioned off-screen before navigation starts. Chrome profile `Preferences` is also sanitized to prevent saved maximized state from overriding.
- **Low-value URL filter**: Glassdoor, Indeed, G2, Capterra, LinkedIn, Twitter/X, Reddit, privacy/terms/cookie paths etc. skip Patchright entirely. No popup possible on those.
- **External-source orchestrator** (`get_external_orchestrator`): web-search validation and discovery scrapes use a popup-free orchestrator (Patchright stripped from tier list). Blocked external sources are silently skipped.
- **Per-host rate-limit memory** (`src/primr/data/scraping/rate_limit_state.py`): 429 responses record a 20-minute cooldown (expandable on repeat) at `logs/rate_limit_state.json`. Subsequent scrapes on cooldown hosts skip live fetch and go straight to public-data fallbacks with a clear user-facing message.
- **Public-data fallback fan-out** (`src/primr/data/fallback_sources.py`): when the origin is blocked or returns zero pages, primr fetches content in parallel from Wayback Machine (CDX API), live sister subdomains (investor./ir./newsroom./press.), SEC EDGAR 10-K filings, Wikipedia REST API, and xAI Grok surrogate synthesis. Fails open — any one source returning content produces a report.
- **Grok surrogate** (`grok_browse_and_summarize` in `primr.ai.grok_client`): uses xAI's Responses API with `web_search` agent tool to fetch URLs or synthesize equivalent content from public sources when direct fetch fails. Returns citations. Opt-out via `PRIMR_DISABLE_GROK_SURROGATE=1`.
- **"Thin website data" threshold widened**: 3 rich fallback pages totalling 60K+ chars no longer trigger the "thin" branch — char volume is the real signal, not page count.
- **Wayback parallelized and bounded**: CDX lookups run concurrently across candidate URLs with a hard 75s total deadline; can't starve the fan-out budget.
- **New tests**: `tests/test_data/test_fallback_sources.py` (12), `tests/test_data/test_scraping/test_rate_limit_state.py` (9). Existing `tests/test_data/test_external_sources.py` patch paths updated for new orchestrator routing.

## [1.18.0] - 2026-04-10

### Recon Integration — DNS Intelligence Pre-Flight
- **Recon as first-class module**: DNS intelligence tool relocated from standalone `recon/` into `src/primr/recon/`, fully integrated into primr's package, linting, type checking, and CI
- **`primr recon` subcommand**: Standalone DNS intelligence lookups — `primr recon acme.com` returns company name, email provider, tenant ID, 156 SaaS service fingerprints, email security score, and 20 signal intelligence rules. Supports `--json`, `--md`, `--services`, `--full`, batch mode, and `primr recon doctor`
- **Auto-platform detection**: Recon runs automatically before scraping, detects cloud platform(s) from DNS fingerprints (AWS Route 53, Azure DNS, GCP DNS, etc.), and auto-selects `--platform` value. Override with explicit `--platform` flag
- **Recon context injection**: Detected services, signal intelligence, email security, auth type, and infrastructure insights injected as context into all strategy types (AI, Security, CX, Data Fabric)
- **`--cloud-vendor` renamed to `--platform`**: Cleaner flag name. `--cloud-vendor` kept as deprecated alias with warning
- **`--platform ms` shorthand**: Expands to `azure private` for the common Microsoft + NVIDIA combo
- **`--skip-recon` flag**: Opt out of DNS pre-flight step
- **`CloudVendor` → `Platform` enum rename**: `CloudVendor` kept as deprecated alias for backward compatibility
- **Pipeline integration**: Recon results logged, recorded in `_run_state.json`, included in `--dry-run` cost estimates ($0.00, ~2-3 seconds)
- **Property-based tests**: 4 correctness properties validated with Hypothesis (platform mapper purity/ordering, formatter section presence/determinism)
- **156 fingerprints**: 13 new detections including Box, Egnyte, Glean (Enterprise AI Search), Datadog, New Relic, PagerDuty, Render, Ping Identity, CyberArk, Lakera (LLM Guardrails), Cato Networks (SASE), Rippling, Deel
- **20 signal rules**: 7 new signals including Zero Trust Posture, AI Security Posture, Shadow IT Risk, Startup Tool Mix, Dual Email Provider, Observability & SRE, File Collaboration Sprawl
- **Certificate transparency**: Passive subdomain discovery via crt.sh integration
- **SRV record detection**: Skype for Business, XMPP, CalDAV, CardDAV
- **Expanded DKIM**: ESP selectors for Mailchimp, SendGrid, Mailgun, Postmark, Mimecast
- **Custom signals**: User-defined signals via `~/.recon/signals.yaml` (additive, mirrors fingerprint extensibility)

## [1.16.0] - 2026-03-23

This release consolidates all work from v1.7.0 through v1.16.0. See [ROADMAP.md](ROADMAP.md) for the detailed changelog.

### Added
- **A2A Protocol Integration** — Agent-to-agent communication with AgentCard, executor, client, hooks, and 165 dedicated tests
  - Standalone `primr-a2a` server or co-hosted `primr-mcp --http --a2a`
  - `delegate_to_agent` MCP tool for calling external A2A agents
  - Governance hooks: SSRF, cost budget, content sanitization
- **Grok 4.20 Hybrid Tier** — 4.20 reasoning + 4.1 writing as new default, `--grok-tier` flag (fast/hybrid/max), per-model cost tracking, calibrated estimates
- **Private Cloud Vendor** — NVIDIA-first, on-prem AI strategy via `--cloud-vendor private`
- **Agentic Architecture** (v1.7.0) — Hypothesis tracking, subagents (scraper, analyst, writer, QA), hook system (cost guard, SSRF guard, QA gate), orchestrator, research memory, Claude Skills
- **Output Improve Mode** — `primr improve <path>` for deterministic cleanup + optional `--improve-agentic` review pass
- **Versioned Eval Workflow** — `primr --eval` with scorecards, auto-staging, LLM-judge overlays (cloud and local), multi-model sweeps
- **Fast Mode as Default** — Auto-detects Grok 4.1 when `XAI_API_KEY` set; `--premium` for Gemini + Deep Research
- **Startup Banner** — Animated ANSI gradient with 5-layer terminal fallback, cross-platform
- **Adaptive Output Shipping Gate** — Deterministic salvage pass, DOCX pre/post validation, strategy-only reruns
- **Agentic Pipeline** — Adaptive search depth, source quality filtering, dynamic section selection, 2 new report sections (23 total)
- **Deep Research Refactor** — Shared parsing/polling/execution modules, durable async recovery, `--resume-latest`, `--resume-local`
- **Shared AI Error Policy** — Unified sync/async retry classification
- **Scraping Reliability** — Adaptive lazy-load scrolling, strict quality gate, scrape trace logging, external search caps
- **Content Sanitization** (v1.8.1) — Prompt injection protection
- **Interactive Research Mode** (v1.11.0) — Expanded external search, MCP progress subscriptions
- **Multi-Cloud-Vendor AI Strategy** (v1.12.0) — `--cloud-vendor aws azure` for multi-vendor strategy documents
- **Strategy Enrichment** — Cross-validation, evidence search, section regeneration, polish pass, pre-ship repair
- **Gemini 3.1 Pro Preview** — Registered with tiered pricing in ModelRegistry
- **All Strategy Types in Fast Mode** — `--strategy-type` works with Grok pipeline, YAML configs auto-discovered

### Fixed
- **Silent Failure Audit** — 45+ bare `except: pass` and DEBUG-level error handlers upgraded across 23 modules
- **Report Quality** — Duplicate section elimination, coherence pass rewrite (guard threshold 0.92→0.96), contradiction resolution
- **Scraping Robustness** (v1.12.1) — PDF routing, bug fixes
- **SharedBrowser** (v1.11.2) — ETA progress, UI polish
- **Deep Research Progress** (v1.11.1) — Visibility and failure recovery

### Changed
- Default pipeline uses Grok 4.20 hybrid (was Grok 4.1)
- Strategy `max_tokens` raised from 16K to 32K
- Executive summary written last (with full report context)
- Parallel external source search (`ThreadPoolExecutor(max_workers=3)`)
- Framework section word targets raised from 600 to 800

## [1.6.0] - 2026-02-03

### Added
- **Serverless Cloud Deployment** - Full job-based ephemeral execution for AWS, Azure, and GCP
  - Job runner contract with manifest-as-commit pattern
  - Artifact storage abstraction (S3, Blob Storage, GCS)
  - Control plane API (submit, status, cancel, results)
  - Event-driven queue boundary (SQS FIFO, Service Bus, Pub/Sub)
  - State reconciliation for stuck/orphaned jobs
  - Comprehensive SSRF protection (RFC1918, metadata IPs, DNS rebinding)
  - Per-API-key rate limiting and quota enforcement
  - OpenTelemetry tracing with job_id correlation
  - Structured JSON logging with sensitive data redaction

- **AWS (Primary - Production Ready)**
  - Lambda control plane + Fargate job runner
  - ECR lifecycle policy (keep last 10 images)
  - S3 lifecycle rules (IA transition after 30 days, version cleanup)
  - SQS dead-letter queue for failed messages
  - Step Functions with least-privilege IAM roles
  - X-Ray tracing on reconciler Lambda
  - CloudWatch alarms (Lambda errors, DynamoDB throttling, DLQ, queue age)

- **Azure (Reference Implementation)**
  - Container Apps control plane + Container Apps Jobs runner
  - Cosmos DB autoscale (400-4000 RU/s)
  - Managed identity with RBAC roles
  - Application Insights for monitoring and tracing

- **GCP (Reference Implementation)**
  - Cloud Run control plane + Cloud Run Jobs runner
  - Dedicated service account (not default App Engine SA)
  - Least-privilege IAM roles
  - Firestore composite indexes for efficient reconciler queries
  - Cloud Scheduler with dedicated service account for OIDC auth

### Documentation
- docs/CLOUD_DEPLOYMENT.md - Serverless deployment guide
- Updated README.md with cloud deployment section
- Updated ROADMAP.md with v1.6.0 completion

## [1.5.1] - 2026-02-02

### Added
- JWT signature verification (HMAC-SHA256/384/512)
- Security headers middleware
- Request ID tracking
- Rate limit headers
- API key rotation with grace periods
- API key expiration support
- Security utilities module
- Security operations guide

### Fixed
- Removed dead code in deep_research.py
- Fixed Python 3.10 compatibility in MCP server modules
- Added missing COMMON_PAGE_PATTERNS re-export in scrape.py
- Fixed exception chaining in multiple modules
- Fixed ambiguous variable names
- Fixed multiple statements on one line in browsers.py
- Removed duplicate method definitions in qa/integration.py
- Fixed import shadowed by loop variable in type_guards.py

### Changed
- CORS now restricts origins, methods, and headers
- JWT tokens require valid signatures
- Admin tokens hashed before comparison

### Documentation
- docs/SECURITY_REVIEW_2026-02-02.md
- docs/SECURITY_OPS.md

## [1.5.0] - 2026-02-02

### Added
- Typed error hierarchy with automatic retry classification
- Circuit breaker with per-host failure tracking and monitoring
- OpenTelemetry integration for distributed tracing
- Configuration validation with early startup checks
- State machine specifications for tier escalation and job lifecycle
- Unified async/sync boundary handling via `async_utils` module
- 282 property-based tests using Hypothesis

### Changed
- Migrated all error classes to typed error hierarchy
- Legacy error names (AIError, ScrapingError, etc.) now alias to typed classes
- All errors now have `user_message()`, `debug_message()`, and `guidance` attributes
- Error formatting utilities updated to use typed hierarchy

### Documentation
- CONCURRENCY.md - Threading model documentation
- docs/STATE_MACHINES.md - State machine specifications
- docs/MIGRATION.md - Error hierarchy documentation
- docs/INDEX.md - Unified documentation index

## [1.4.1] - 2026-02-02

### Added
- Open Claw integration with skills, workflows, and adapters
- 3 skills: primr-research, primr-strategy, primr-qa
- Lobster workflow for orchestrated research with approval gates
- New MCP resources for Open Claw integration
- Run manifest generation for audit trail
- 163 new tests for Open Claw integration

### Documentation
- docs/OPENCLAW.md - Open Claw integration guide

## [1.3.2] - 2026-01-30

### Added
- **Preflight validation** - Research pipeline now validates all dependencies and API keys BEFORE starting expensive operations
  - Checks Gemini API key validity
  - Checks Google Search API key and engine ID with actual API call
  - Checks Playwright browser installation
  - Fails fast with clear error messages instead of failing mid-pipeline
- **Input validation** - Added comprehensive validation across all modules:
  - AI client: temperature bounds (0.0-2.0), prompt non-empty, thinking level validation
  - HTTP client: URL format validation, timeout bounds checking
  - Config: AIConfig and ScrapingConfig now have `validate()` methods
- **Thread-safe job tracking** - Job tracking file operations now use file locking to prevent corruption from concurrent writes
- **Atomic file writes** - Job tracking uses temp file + rename pattern for crash safety
- **14 new hardening tests** - Tests for input validation, error context, thread safety

### Changed
- **`primr doctor` now tests APIs** - Actually calls Google Search API to verify configuration works, not just that keys exist
- **Better error context** - ScrapingError and SearchError now include HTTP status codes and additional context
- **Improved quota detection** - AI client now catches more quota error patterns (daily limit, rate limit exceeded, etc.)
- **Cleanup retry logic** - Temp file cleanup now retries up to 3 times with delays (helps on Windows with file locks)
- **External source logging** - LLM validation results now logged at INFO level so users can see why sources were accepted/rejected

### Fixed
- **Bare except handler** - Fixed `except:` in qa/command.py to `except Exception:` (was catching KeyboardInterrupt)
- **Silent validation failures** - External source validation failures now logged at WARNING level
- **Empty API response handling** - AI client now properly handles None responses and extracts text from candidates

## [1.3.1] - 2026-01-30

### Fixed
- **Critical: File Search Store billing leak** - Stores were not being deleted because they contained documents. Fixed by implementing two-step cleanup: delete documents first, then delete store. Cleaned up 72 orphaned stores from December 2025.
- **File descriptor leaks** - Fixed 3 instances where `tempfile.mkstemp()` file descriptors were not being closed, which could cause "too many open files" errors over time.
- **Database connection leaks** - Fixed connection leaks in `CompanyMonitor`, `KnowledgeGraph`, and `TenantManager` where new SQLite connections were created on each operation but never closed. Now uses persistent connections with proper `close()` methods.
- **Silent error swallowing** - Improved error logging in browser cleanup code (browsers.py) - bare `except: pass` patterns now log errors at debug level for troubleshooting.
- **Gemini resource cleanup** - `primr doctor` now checks for orphaned File Search Stores and Context Caches that could be incurring costs.

### Added
- `scripts/check_gemini_resources.py` - Utility script to inspect and clean up Gemini resources
  - `--delete-stores --force-empty` to properly delete File Search Stores with documents
  - `--delete-caches` to remove explicit context caches
- File Search Store lifecycle tests (14 tests) to prevent future billing leaks

### Changed
- All File Search Store operations now use try/finally blocks to ensure cleanup
- `FileSearchStoreManager.delete_store()` now properly deletes documents before store
- Improved error logging when store cleanup fails

## [1.3.0] - 2026-01-26

### Added
- Multiple strategy document types (AI, Customer Experience, Security & Compliance, Data Fabric)
- `--list-strategies` command to show available strategy frameworks
- `--strategy-type` option for generating specific strategy documents
- Enhanced build configuration with proper version constraints
- Comprehensive security review and hardening (January 2026)
- XXE protection with secure XML parsing
- SSRF protection with URL validation
- Input validation across all user inputs
- Auto-detection of Python 3.11+ in setup wizard

### Changed
- Python requirement updated from 3.10 to 3.11+
- Updated project description to better reflect company intelligence focus
- Improved dependency management with version constraints
- Enhanced README with clearer pipeline explanation and mode descriptions
- Consolidated scraping logic into single `fetch_web_content()` function
- Better documentation of scraping tier escalation
- Setup wizard now auto-restarts with correct Python version if needed

### Fixed
- Deep Research connection drop recovery with automatic polling
- AI Strategy retry capability with `--ai-strategy-only` flag
- Windows PATH configuration in setup wizard
- Build artifact cleanup for network/sync drives

### Security
- All critical vulnerabilities addressed (see docs/SECURITY_REVIEW_2026-01-21.md)
- Secure XML parser prevents XXE attacks
- URL validation blocks SSRF attempts
- Comprehensive input validation

## [1.2.4] - 2025-12-23

### Added
- Quality assessment system for generated reports
- Automatic QA scoring with color-coded grades
- `--qa` and `--qa-recent` commands for manual QA
- Job recovery system for Deep Research

### Changed
- Improved CLI output with better progress indicators
- Enhanced error messages and user guidance

## [1.2.0] - 2025-12-19

### Added
- AI Strategy document generation with cloud vendor customization
- `--ai-strategy-only` flag for retry capability
- `--cloud-vendor` option (azure, aws, gcp)
- Batch processing with `--csv` flag

### Changed
- Unified pipeline architecture (modes are stopping points, not separate implementations)
- Improved scraping resilience with tier escalation
- Better handling of WAF-protected sites

## [1.1.0] - 2025-11-15

### Added
- Deep Research mode for external source validation
- Vision tier for JavaScript-heavy sites
- Automatic link discovery and selection

### Changed
- Refactored scraping into tiered approach (HTTP → Stealth → Browser → Vision)
- Improved cost estimation with `--dry-run`

## [1.0.0] - 2025-10-01

### Added
- Initial release
- Basic scraping and report generation
- Gemini API integration
- DOCX report output
