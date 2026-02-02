# Changelog

All notable changes to Primr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-02-02

### Added
- **PhD-Level Code Quality** - Comprehensive improvements to achieve publication-ready quality
  - Typed error hierarchy with `PrimrError` base class, `TransientError`/`PermanentError` categories
  - Specific error types: RateLimitError, QuotaError, NetworkError, ValidationError, AuthenticationError, ConfigurationError
  - Automatic correlation ID capture and JSON serialization for all errors
- **Retry Policy Manager** - Automatic retry policies based on error type hierarchy
  - Exponential backoff with configurable jitter
  - Retry history tracking attached to final errors
  - Metrics emission for retry attempts
- **Circuit Breaker with Monitoring** - Per-host/operation circuit breaker
  - State tracking (CLOSED/OPEN/HALF_OPEN) with configurable thresholds
  - State change event emission with listener support
  - Monitoring interface for observability
- **OpenTelemetry Integration** - Distributed tracing for pipeline phases
  - TracerProvider initialization with configurable exporters (console, OTLP, Jaeger)
  - Span creation with correlation_id, operation name, and phase attributes
  - Async context propagation across boundaries
- **Cost Attribution** - Token usage tracking with cost calculation
  - Per-model pricing tables
  - Aggregation by operation, phase, and model
  - Span attribute attachment for observability
- **Pydantic Configuration Validation** - Strict validation for YAML configurations
  - Detailed error messages with field paths and expected types
  - Schema versioning with migration guidance
  - JSON Schema export for external tooling
- **Configuration Migration Tooling** - Safe schema upgrades
  - Version detection and sequential migration application
  - Backup/restore functionality
  - Dry-run mode for previewing changes
- **State Machine Specifications** - Formal state machines for tier escalation and job lifecycle
  - Transition validation with guards and invariants
  - State change event emission
  - State persistence for crash recovery
  - Mermaid diagrams in docs/STATE_MACHINES.md
- **Performance Benchmarking Suite** - Benchmark infrastructure
  - Result storage with historical comparison
  - Regression detection with configurable thresholds
- **Memory Profiling** - Memory tracking for long-running operations
  - Allocation tracking and unbounded growth detection
  - Component-level reporting
  - Threshold-based warnings
  - pytest integration for memory regression tests
- **MCP API Versioning** - Semantic versioning for tool schemas
  - Deprecation warnings with minimum 2 minor versions notice
  - Migration guides for breaking changes
- **282 Property-Based Tests** - Comprehensive property tests using Hypothesis
  - Tests for error hierarchy, retry policies, circuit breaker, telemetry, cost tracking
  - Tests for configuration validation, migration, state machines
  - Tests for benchmarking, memory profiling, MCP versioning, backward compatibility

### Documentation
- CONCURRENCY.md - Threading model documentation with operation classification, thread pool sizing, shared state, async/sync boundaries, and deadlock prevention
- docs/STATE_MACHINES.md - Formal state machine specifications with Mermaid diagrams

### New Modules
- `src/primr/utils/errors.py` - Typed error hierarchy
- `src/primr/utils/retry.py` - RetryPolicyManager
- `src/primr/utils/circuit_breaker.py` - Circuit breaker with monitoring
- `src/primr/utils/telemetry.py` - OpenTelemetry integration
- `src/primr/utils/cost_tracker.py` - Cost attribution
- `src/primr/utils/validation.py` - Pydantic configuration validation
- `src/primr/utils/migration.py` - Configuration migration tooling
- `src/primr/utils/state_machine.py` - Generic state machine
- `src/primr/utils/benchmarks.py` - Performance benchmarking suite
- `src/primr/utils/memory_profiler.py` - Memory profiling
- `src/primr/mcp_server/versioning.py` - MCP API versioning

## [1.4.1] - 2026-02-02

### Added
- **Open Claw Integration** - Full integration with Open Claw agentic runtime
  - 3 skills: primr-research, primr-strategy, primr-qa
  - Lobster workflow for orchestrated research with approval gates
  - TypeScript adapter for status monitoring
  - Docker sandbox configuration (Dockerfile.primr)
  - exec-approvals.json for cost-incurring operation gates
- **New MCP Resources for Open Claw**:
  - `primr://strategies/available` - List available strategy types with metadata (id, name, description, estimated cost/time)
  - `primr://output/by_job/{job_id}` - Job-scoped artifact retrieval for provenance tracking
  - `primr://output/manifest/latest` - Run manifest for audit trail
- **Run Manifest Generation** - Each completed job generates a run_manifest.json with:
  - Job metadata (id, company, mode)
  - Estimate vs actual cost/time comparison
  - Approval token and timestamp
  - List of generated artifacts
- **job_id in primr://output/latest** - Response now includes job_id for artifact provenance verification
- **163 new tests** for Open Claw integration covering:
  - Configuration validation (openclaw.json, exec-approvals.json)
  - SKILL.md compliance with AgentSkills spec
  - Workflow structure validation
  - TypeScript adapter compilation
  - Dockerfile security configuration
  - New MCP resources (strategies, job-scoped output, manifest)
  - Integration harness for workflow simulation

### Documentation
- Added docs/OPENCLAW.md - Complete Open Claw integration guide
- Updated README.md with Open Claw section
- Updated docs/API.md with new MCP resources

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
