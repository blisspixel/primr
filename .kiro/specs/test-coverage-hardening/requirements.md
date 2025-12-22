# Requirements Document

## Introduction

This specification defines requirements for hardening Primr's test coverage to ensure production-grade reliability. Primr is a research tool that generates company intelligence briefs using Google's Gemini models, including the Deep Research Agent (`deep-research-pro-preview-12-2025`) via the Interactions API. The tool produces 20-70 page strategic reports through the Accordion Method (Phase 1: Research Dossier gathering, Phase 2: Section-by-section writing with Gemini Flash).

The current test suite has 2,364 tests with strong property-based testing coverage but gaps in end-to-end integration, API resilience, and output quality validation. This spec addresses those gaps to achieve "boringly reliable" production quality as stated in the ROADMAP.md v1.2.0 goals.

## Glossary

- **Primr**: The research tool being tested
- **Accordion Method**: Two-phase report generation (Deep Research gathers facts, Gemini Flash writes sections)
- **Deep Research Agent**: Google's `deep-research-pro-preview-12-2025` agent for autonomous multi-step research
- **Interactions API**: Google's stateful API for long-running agentic tasks with background execution
- **File Search Store**: Google's managed RAG system for uploading proprietary context documents
- **Property-Based Testing (PBT)**: Testing approach using Hypothesis to verify properties across random inputs
- **Thought Signatures**: Encrypted tokens representing the model's internal reasoning, required for multi-turn consistency
- **sections_written**: Field tracking actual number of sections written by the Accordion Method

## Requirements

### Requirement 1

**User Story:** As a developer, I want pytest custom marks registered, so that I can run slow/integration tests selectively without warnings.

#### Acceptance Criteria

1. WHEN pytest runs THEN the system SHALL recognize `@pytest.mark.slow` without warnings
2. WHEN pytest runs THEN the system SHALL recognize `@pytest.mark.integration` without warnings
3. WHEN a user runs `pytest -m "not slow"` THEN the system SHALL exclude tests marked as slow
4. WHEN a user runs `pytest -m integration` THEN the system SHALL run only integration tests

### Requirement 2

**User Story:** As a developer, I want CLI smoke tests, so that I can verify the basic CLI functionality works without running expensive API calls.

#### Acceptance Criteria

1. WHEN `primr doctor` is executed THEN the system SHALL complete without error and return exit code 0
2. WHEN `primr --help` is executed THEN the system SHALL display usage information and return exit code 0
3. WHEN `primr --list-strategies` is executed THEN the system SHALL list available strategy modules
4. WHEN `primr "Test" https://test.com --dry-run` is executed THEN the system SHALL display cost estimate without making API calls
5. WHEN invalid arguments are provided THEN the system SHALL return a non-zero exit code and display error message

### Requirement 3

**User Story:** As a developer, I want API resilience tests, so that I can verify the system handles failures gracefully.

#### Acceptance Criteria

1. WHEN a 429 rate limit error occurs THEN the system SHALL retry with exponential backoff
2. WHEN a 500 internal server error occurs THEN the system SHALL retry up to MAX_RETRIES times
3. WHEN a network timeout occurs THEN the system SHALL log the error and attempt reconnection
4. WHEN Deep Research fails after retries THEN the system SHALL fall back to Stage 1 context and continue
5. WHEN consecutive section writes fail THEN the system SHALL stop after 3 consecutive failures and return partial results

### Requirement 4

**User Story:** As a developer, I want the sections_written field tested, so that I can verify accurate section counts are reported.

#### Acceptance Criteria

1. WHEN the Accordion Method completes successfully THEN the sections_written field SHALL equal the number of sections actually written
2. WHEN sections_written is propagated to OrchestratorResult THEN the value SHALL match DeepResearchOrchestratorResult.sections_written
3. WHEN the CLI displays "Sections: N" THEN N SHALL reflect sections_written, not len(section_results)
4. WHEN some sections fail THEN sections_written SHALL reflect only successful sections

### Requirement 5

**User Story:** As a developer, I want citation URL resolution tests, so that I can verify Google redirect URLs are properly resolved.

#### Acceptance Criteria

1. WHEN a citation contains a Google redirect URL THEN the system SHALL resolve it to the final destination URL
2. WHEN a citation URL is already a direct link THEN the system SHALL preserve it unchanged
3. WHEN URL resolution fails THEN the system SHALL preserve the original URL and log a warning
4. WHEN multiple citations reference the same URL THEN the system SHALL deduplicate them in the sources list

### Requirement 6

**User Story:** As a developer, I want YAML configuration validation tests, so that I can catch configuration errors before runtime.

#### Acceptance Criteria

1. WHEN company_overview.yaml is loaded THEN the system SHALL validate all 21 sections have required fields
2. WHEN ai_strategy.yaml is loaded THEN the system SHALL validate vendor guidance exists for azure, aws, gcp
3. WHEN a strategy module YAML is malformed THEN the system SHALL raise a descriptive error
4. WHEN accordion_method prompts are loaded THEN the system SHALL validate placeholders exist ({company_name}, {section_title}, etc.)

### Requirement 7

**User Story:** As a developer, I want output format consistency tests, so that I can verify reports maintain structure across modes.

#### Acceptance Criteria

1. WHEN a report is generated in deep mode THEN the output SHALL contain all 21 section headings
2. WHEN a report is generated THEN the executive summary SHALL appear first
3. WHEN a report is generated THEN the strategic positioning hypothesis SHALL appear last
4. WHEN markdown is converted to DOCX THEN table formatting SHALL be preserved
5. WHEN markdown is converted to DOCX THEN heading hierarchy SHALL be preserved

### Requirement 8

**User Story:** As a developer, I want concurrent access safety tests, so that I can verify thread safety in shared resources.

#### Acceptance Criteria

1. WHEN multiple threads write to console THEN output SHALL not be interleaved mid-line
2. WHEN heartbeat thread runs during section writing THEN console output SHALL remain coherent
3. WHEN multiple sections are saved to working folder THEN file writes SHALL not corrupt each other

### Requirement 9

**User Story:** As a developer, I want cost estimation accuracy tests, so that I can verify estimates match actual usage patterns.

#### Acceptance Criteria

1. WHEN cost is estimated for deep mode THEN the estimate SHALL be within 50% of typical actual costs
2. WHEN cost is estimated for full mode THEN the estimate SHALL account for both scraping and Deep Research
3. WHEN AI strategy is included THEN the estimate SHALL add the strategy generation cost

### Requirement 10

**User Story:** As a developer, I want File Search Store lifecycle tests, so that I can verify proper cleanup of uploaded context.

#### Acceptance Criteria

1. WHEN a research task completes THEN the File Search Store SHALL be deleted
2. WHEN a research task fails THEN the File Search Store SHALL still be deleted in the finally block
3. WHEN Stage 1 context is uploaded THEN the file SHALL be properly indexed before Deep Research starts

