# Requirements Document

## Introduction

This specification defines PhD-level code quality improvements for Primr. The goal is to transform already-working code into production-grade, enterprise-ready software with improved type safety, error handling, testability, observability, and maintainability.

This is a "hardening" pass focused on code quality, not new features. The system already works; we're making it bulletproof. This spec also includes the rebrand from `company_research.py` to `primr`.

## Glossary

- **Primr**: The CLI tool and project name
- **Scrape Mode**: Website scraping + Google search research mode
- **Deep Mode**: Gemini Deep Research Agent autonomous research mode
- **Full Mode**: Two-step sequential (scrape then deep)
- **AIClient**: The unified AI client for all LLM operations
- **DeepResearchClient**: Client for Gemini Deep Research Agent
- **ResearchOrchestrator**: Coordinates research engines and modes
- **CitationProcessor**: Transforms inline URLs to numbered references
- **CircuitBreaker**: Pattern for API resilience and fail-fast behavior
- **LRUCache**: Least Recently Used cache with bounded memory
- **Type Guard**: Runtime type validation function
- **Invariant**: Condition that must always be true during execution

## Requirements

### Requirement 1: Type Safety and Runtime Validation

**User Story:** As a developer, I want comprehensive type safety, so that type errors are caught at development time and runtime edge cases are handled gracefully.

#### Acceptance Criteria

1. WHEN a public function receives parameters THEN the function SHALL validate parameter types at runtime for critical paths
2. WHEN a function returns a complex object THEN the return type SHALL be validated against its dataclass/TypedDict definition
3. WHEN the codebase is analyzed with mypy strict mode THEN the system SHALL produce zero type errors
4. WHEN Optional types are used THEN the code SHALL explicitly handle None cases without relying on truthiness
5. WHEN external API responses are received THEN the system SHALL validate response structure before processing

### Requirement 2: Error Handling Consistency

**User Story:** As a developer, I want consistent error handling patterns, so that failures are predictable and debuggable.

#### Acceptance Criteria

1. WHEN an exception is caught THEN the handler SHALL either re-raise, wrap in a domain exception, or explicitly handle with logging
2. WHEN a bare except clause exists THEN the code SHALL be refactored to catch specific exception types
3. WHEN an error occurs in async code THEN the error SHALL propagate correctly without being silently swallowed
4. WHEN a function can fail THEN it SHALL document failure modes in its docstring
5. WHEN retrying operations THEN the system SHALL use exponential backoff with jitter to prevent thundering herd

### Requirement 3: Resource Management

**User Story:** As an operator, I want guaranteed resource cleanup, so that long-running processes don't leak memory or file handles.

#### Acceptance Criteria

1. WHEN file handles are opened THEN they SHALL be managed with context managers
2. WHEN temporary files are created THEN they SHALL be cleaned up even on exception paths
3. WHEN HTTP connections are made THEN connection pools SHALL have bounded sizes and timeouts
4. WHEN caches grow THEN they SHALL have configurable size limits with eviction policies
5. WHEN browser instances are created THEN they SHALL be properly closed on process exit

### Requirement 4: Concurrency Safety

**User Story:** As a developer, I want thread-safe code, so that concurrent operations don't cause race conditions or data corruption.

#### Acceptance Criteria

1. WHEN singleton instances are accessed THEN the access SHALL use double-check locking pattern
2. WHEN shared state is modified THEN the modification SHALL be protected by appropriate locks
3. WHEN async operations share state THEN the code SHALL use asyncio-safe primitives
4. WHEN progress callbacks are invoked THEN they SHALL be thread-safe and non-blocking
5. WHEN global state is used THEN it SHALL be documented and access SHALL be synchronized

### Requirement 5: Observability and Debugging

**User Story:** As an operator, I want comprehensive observability, so that I can diagnose issues in production.

#### Acceptance Criteria

1. WHEN a function performs significant work THEN it SHALL log entry, exit, and duration at DEBUG level
2. WHEN an error occurs THEN the log SHALL include correlation ID, context, and stack trace
3. WHEN external APIs are called THEN the system SHALL track latency, success rate, and error types
4. WHEN configuration is loaded THEN the system SHALL log effective configuration at startup
5. WHEN research completes THEN the system SHALL emit structured metrics (duration, tokens, cost)

### Requirement 6: Code Documentation

**User Story:** As a developer, I want comprehensive documentation, so that I can understand and maintain the code.

#### Acceptance Criteria

1. WHEN a public function is defined THEN it SHALL have a docstring with Args, Returns, Raises, and Example sections
2. WHEN a class is defined THEN it SHALL have a class-level docstring explaining purpose and usage
3. WHEN complex logic exists THEN inline comments SHALL explain the "why" not the "what"
4. WHEN a module is created THEN it SHALL have a module-level docstring explaining its role
5. WHEN magic numbers or strings exist THEN they SHALL be extracted to named constants with documentation

### Requirement 7: Defensive Programming

**User Story:** As a developer, I want defensive code, so that unexpected inputs don't cause crashes or security issues.

#### Acceptance Criteria

1. WHEN user input is processed THEN it SHALL be validated and sanitized before use
2. WHEN URLs are constructed THEN they SHALL be properly escaped and validated
3. WHEN file paths are used THEN they SHALL be validated against path traversal attacks
4. WHEN JSON is parsed THEN the parser SHALL handle malformed input gracefully
5. WHEN string formatting uses external data THEN it SHALL use parameterized formatting not concatenation

### Requirement 8: Test Quality

**User Story:** As a developer, I want high-quality tests, so that I can refactor with confidence.

#### Acceptance Criteria

1. WHEN a bug is fixed THEN a regression test SHALL be added
2. WHEN a public function exists THEN it SHALL have unit test coverage for happy path and error cases
3. WHEN property-based tests exist THEN they SHALL use meaningful generators not just random data
4. WHEN mocks are used THEN they SHALL verify call signatures match real implementations
5. WHEN integration tests exist THEN they SHALL be isolated and not depend on external services

### Requirement 9: Performance Optimization

**User Story:** As a user, I want efficient code, so that research completes quickly without wasting resources.

#### Acceptance Criteria

1. WHEN content is deduplicated THEN the deduplication SHALL reduce token usage by at least 10% on typical inputs
2. WHEN API calls are made THEN independent calls SHALL be batched or parallelized where possible
3. WHEN large strings are processed THEN the code SHALL avoid unnecessary copies
4. WHEN regex patterns are used THEN they SHALL be pre-compiled at module level
5. WHEN caching is used THEN cache hit rates SHALL be logged for optimization

### Requirement 10: Configuration Management

**User Story:** As an operator, I want centralized configuration, so that I can tune behavior without code changes.

#### Acceptance Criteria

1. WHEN a magic number exists THEN it SHALL be moved to configuration with a sensible default
2. WHEN configuration is loaded THEN it SHALL validate values and fail fast on invalid config
3. WHEN environment variables are used THEN they SHALL have documented defaults and validation
4. WHEN timeouts are configured THEN they SHALL have separate values for connect, read, and total
5. WHEN feature flags exist THEN they SHALL be centralized and documented

