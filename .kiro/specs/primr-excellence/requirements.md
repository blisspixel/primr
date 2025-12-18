# Requirements Document

## Introduction

This specification defines the requirements for elevating Primr from a functional CLI research tool to a **reference-grade implementation** — the kind of codebase that serves as a teaching example for professional Python development, and a CLI experience that sets the standard for terminal UX design.

The goal is twofold:
1. **PhD-level code quality**: Formal correctness guarantees through property-based testing, comprehensive type safety, and defensive programming patterns
2. **Mona Lisa CLI UX**: A terminal experience so polished it makes developers *feel something* — clear visual hierarchy, intelligent progress feedback, and delightful micro-interactions

This is not about adding features. It's about making the existing features bulletproof and beautiful.

## Glossary

- **Primr**: The AI-powered company research CLI tool being enhanced
- **Property-Based Testing (PBT)**: Testing methodology using randomly generated inputs to verify universal properties
- **Hypothesis**: Python library for property-based testing
- **Console**: The terminal output abstraction layer (`primr.utils.console`)
- **Research Agent**: The main CLI entry point and orchestration logic
- **Deep Research**: Gemini's autonomous multi-step research agent
- **Type Guard**: Runtime validation function that narrows types
- **Result Monad**: A type that represents either success or failure
- **Visual Hierarchy**: Design principle organizing information by importance through visual cues
- **Heartbeat**: Periodic status message during long-running operations
- **Spinner**: Animated indicator showing active processing

---

## Requirements

### Requirement 1: Type Safety and Runtime Validation

**User Story:** As a developer maintaining Primr, I want comprehensive type safety so that type errors are caught at development time and runtime boundaries are validated, preventing silent failures in production.

#### Acceptance Criteria

1. WHEN the codebase is analyzed with mypy in strict mode THEN the type checker SHALL report zero errors across all modules
2. WHEN external API responses are received THEN the system SHALL validate response structure using type guards before processing
3. WHEN configuration is loaded from environment or files THEN the system SHALL validate all values against expected types and ranges
4. WHEN a function receives parameters at a module boundary THEN the system SHALL validate parameter types at runtime using type guards
5. WHEN type validation fails THEN the system SHALL raise a descriptive TypeValidationError with field name, expected type, and actual type

---

### Requirement 2: Error Handling and Recovery

**User Story:** As a user running long research jobs, I want robust error handling so that transient failures don't lose my progress and I get clear feedback about what went wrong.

#### Acceptance Criteria

1. WHEN a network request fails THEN the system SHALL retry with exponential backoff and jitter up to a configurable maximum
2. WHEN a Deep Research job is interrupted THEN the system SHALL persist the interaction ID for recovery
3. WHEN an error occurs THEN the system SHALL log structured error context including correlation ID, operation name, and relevant parameters
4. WHEN a recoverable error occurs THEN the system SHALL display a user-friendly message without exposing internal stack traces
5. WHEN all retry attempts are exhausted THEN the system SHALL provide actionable guidance for the user

---

### Requirement 3: Property-Based Test Coverage

**User Story:** As a QA engineer, I want property-based tests for all core transformations so that correctness is verified across the entire input space, not just example cases.

#### Acceptance Criteria

1. WHEN markdown content is parsed and then rendered back THEN the system SHALL produce semantically equivalent output (round-trip property)
2. WHEN a report section is generated THEN the output SHALL contain all required structural elements regardless of input content
3. WHEN citation processing transforms references THEN the citation count SHALL equal the number of unique sources in the input
4. WHEN URL normalization is applied THEN the normalized form SHALL be idempotent (normalizing twice equals normalizing once)
5. WHEN cost estimation is calculated THEN the estimate SHALL be monotonically increasing with input complexity
6. WHEN any parser receives malformed input THEN the parser SHALL return a valid result without raising exceptions (graceful degradation)

---

### Requirement 4: Console Visual Hierarchy

**User Story:** As a user watching a long research job, I want clear visual hierarchy so that I can instantly understand what's happening, what phase I'm in, and how much longer to wait.

#### Acceptance Criteria

1. WHEN a major phase begins THEN the console SHALL display a prominent phase banner with step number, title, and expected duration
2. WHEN progress updates occur THEN the console SHALL show elapsed time alongside the progress indicator
3. WHEN a long operation exceeds 30 seconds THEN the console SHALL display periodic heartbeat messages confirming activity
4. WHEN a phase completes THEN the console SHALL display a completion summary with key statistics and duration
5. WHEN an error occurs THEN the console SHALL use distinct visual styling that stands out from normal output

---

### Requirement 5: Progress Feedback Intelligence

**User Story:** As a user, I want intelligent progress feedback so that I know the system is working and can estimate completion time accurately.

#### Acceptance Criteria

1. WHEN Deep Research is running THEN the console SHALL stream thinking summaries in real-time when available
2. WHEN multiple sections are being processed THEN the console SHALL show both individual and overall progress
3. WHEN estimated time differs significantly from actual elapsed time THEN the console SHALL adjust displayed estimates
4. WHEN a sub-operation completes THEN the console SHALL show its duration inline without disrupting the overall flow
5. WHEN the terminal is resized THEN the console SHALL adapt output width gracefully without breaking formatting

---

### Requirement 6: CLI Argument Validation

**User Story:** As a user, I want clear validation of CLI arguments so that I get immediate feedback about invalid inputs before expensive operations begin.

#### Acceptance Criteria

1. WHEN a URL argument is provided THEN the system SHALL validate URL format and normalize it before processing
2. WHEN required arguments are missing THEN the system SHALL display specific guidance about what's needed
3. WHEN mutually exclusive options are provided THEN the system SHALL reject the combination with a clear explanation
4. WHEN an unknown option is provided THEN the system SHALL suggest similar valid options (fuzzy matching)
5. WHEN all validation passes THEN the system SHALL display a confirmation summary before starting expensive operations

---

### Requirement 7: Output Document Quality

**User Story:** As a user receiving research reports, I want consistently formatted, professional documents so that the output is immediately usable without manual cleanup.

#### Acceptance Criteria

1. WHEN markdown tables are present in Deep Research output THEN the DOCX converter SHALL render them as properly formatted Word tables
2. WHEN citations are processed THEN the system SHALL generate a consistent citation format throughout the document
3. WHEN headings are nested THEN the document SHALL maintain correct heading hierarchy (H1 > H2 > H3)
4. WHEN bullet lists contain sub-items THEN the document SHALL render proper indentation levels
5. WHEN bold or italic markdown is present THEN the document SHALL apply corresponding Word formatting

---

### Requirement 8: Observability and Debugging

**User Story:** As a developer debugging issues, I want comprehensive observability so that I can trace exactly what happened during a research run.

#### Acceptance Criteria

1. WHEN a research job starts THEN the system SHALL generate a unique correlation ID for all related log entries
2. WHEN an API call is made THEN the system SHALL log request parameters, response status, and duration
3. WHEN verbose mode is enabled THEN the system SHALL output detailed timing for each operation
4. WHEN a job completes THEN the system SHALL log a summary including total duration, API calls made, and tokens consumed
5. WHEN structured logging is enabled THEN log entries SHALL be valid JSON with consistent field names

---

### Requirement 9: Resource Management

**User Story:** As a user running multiple research jobs, I want proper resource management so that the system doesn't leak memory, file handles, or leave orphaned processes.

#### Acceptance Criteria

1. WHEN a research job completes or fails THEN the system SHALL close all open file handles and network connections
2. WHEN Playwright browsers are used THEN the system SHALL ensure browser processes are terminated on exit
3. WHEN temporary files are created THEN the system SHALL clean them up after use or on process exit
4. WHEN the process receives SIGINT THEN the system SHALL perform graceful shutdown with cleanup
5. WHEN cache size exceeds configured limits THEN the system SHALL evict oldest entries automatically

---

### Requirement 10: Configuration Validation

**User Story:** As a user setting up Primr, I want configuration validation so that misconfigurations are caught early with helpful error messages.

#### Acceptance Criteria

1. WHEN API keys are missing THEN the system SHALL identify which specific keys are needed and how to obtain them
2. WHEN API keys are invalid format THEN the system SHALL detect this before making API calls
3. WHEN optional settings have invalid values THEN the system SHALL fall back to defaults with a warning
4. WHEN `primr doctor` is run THEN the system SHALL validate all configuration and dependencies comprehensively
5. WHEN configuration sources conflict THEN the system SHALL document the precedence order clearly

---

### Requirement 11: Serialization Round-Trip Integrity

**User Story:** As a developer, I want serialization operations to be lossless so that data can be saved and restored without corruption.

#### Acceptance Criteria

1. WHEN research state is serialized to JSON THEN deserializing SHALL produce an equivalent object
2. WHEN usage history is persisted THEN loading SHALL restore all recorded metrics accurately
3. WHEN cache entries are stored THEN retrieval SHALL return byte-identical content
4. WHEN configuration is exported THEN importing SHALL recreate identical settings

---

### Requirement 12: Concurrent Operation Safety

**User Story:** As a user running batch operations, I want thread-safe operations so that concurrent processing doesn't cause data corruption or race conditions.

#### Acceptance Criteria

1. WHEN multiple scraping operations run concurrently THEN the cache SHALL handle concurrent reads and writes safely
2. WHEN console output occurs from multiple threads THEN the output SHALL not interleave or corrupt
3. WHEN usage tracking is updated from concurrent operations THEN the totals SHALL be accurate
4. WHEN rate limiting is applied THEN the semaphore SHALL correctly limit concurrent API calls

