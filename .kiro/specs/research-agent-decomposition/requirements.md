# Requirements Document

## Introduction

This specification defines the decomposition of `research_agent.py` (currently ~2800 lines with 22 functions) into smaller, focused modules with clear responsibilities. The refactoring also addresses the config module's import-time validation that makes testing difficult. The goal is to improve maintainability, testability, and code organization while preserving all existing functionality and the existing test suite.

## Glossary

- **Research Agent**: The main CLI entry point and orchestration module for Primr research operations
- **Structured Pipeline**: The scrape-based research mode that extracts and analyzes website content section-by-section
- **Deep Research**: The Gemini Deep Research Agent mode for autonomous multi-step research
- **AI Strategy**: Optional board-level AI roadmap generation based on company research
- **Vendor Research**: Cloud vendor-specific AI capabilities research (Azure, AWS, GCP)
- **Working Folder**: Temporary directory for storing intermediate research artifacts
- **Lazy Validation**: Deferring validation until the value is actually needed, rather than at import time

## Requirements

### Requirement 1

**User Story:** As a developer, I want the research agent code organized into focused modules, so that I can understand, test, and modify specific functionality without navigating a 2800-line file.

#### Acceptance Criteria

1. WHEN the research_agent.py module is imported THEN the System SHALL load only orchestration logic with clear delegation to specialized modules
2. WHEN a developer needs to modify structured pipeline logic THEN the System SHALL provide a dedicated structured_research.py module containing all scrape-based research functions
3. WHEN a developer needs to modify deep research logic THEN the System SHALL provide a dedicated deep_research_runner.py module containing all Deep Research execution functions
4. WHEN a developer needs to modify AI strategy generation THEN the System SHALL provide a dedicated ai_strategy.py module in the core package containing all strategy-related functions
5. WHEN a developer needs to modify vendor research logic THEN the System SHALL provide a dedicated vendor_research.py module containing all vendor-specific research functions
6. WHEN a developer needs to modify CLI argument parsing THEN the System SHALL provide a dedicated cli.py module containing argument parsing and main entry point

### Requirement 2

**User Story:** As a developer, I want long functions decomposed into smaller units, so that I can test individual behaviors and understand the code flow.

#### Acceptance Criteria

1. WHEN perform_research executes THEN the System SHALL delegate to phase-specific functions for data collection, analysis, report generation, and finalization
2. WHEN perform_deep_research executes THEN the System SHALL delegate to phase-specific functions for pre-flight validation, research execution, result processing, and output generation
3. WHEN _generate_ai_strategy_section executes THEN the System SHALL delegate to separate functions for prompt building, research execution, and output conversion
4. WHEN _generate_vendor_research executes THEN the System SHALL delegate to separate functions for prompt building, research execution, and result saving
5. IF any extracted function exceeds 50 lines THEN the System SHALL further decompose that function into smaller units

### Requirement 3

**User Story:** As a developer, I want the config module to use lazy validation, so that I can import and test modules without requiring API keys to be configured.

#### Acceptance Criteria

1. WHEN the config.py module is imported THEN the System SHALL NOT raise exceptions for missing API keys
2. WHEN code accesses an API key property THEN the System SHALL validate and return the key or raise ConfigurationError
3. WHEN running tests that do not require API access THEN the System SHALL allow imports without API key configuration
4. WHEN the primr doctor command runs THEN the System SHALL explicitly validate all required configuration
5. WHEN the settings module is imported THEN the System SHALL provide a validate_on_demand method for explicit validation

### Requirement 4

**User Story:** As a developer, I want shared utilities extracted to appropriate modules, so that code duplication is eliminated and utilities are discoverable.

#### Acceptance Criteria

1. WHEN working folder operations are needed THEN the System SHALL provide functions in a dedicated workspace.py module
2. WHEN file validation is needed THEN the System SHALL provide functions in the existing validators.py module
3. WHEN prompt generation is needed THEN the System SHALL provide functions in a dedicated prompts.py module in the config package
4. WHEN output conversion is needed THEN the System SHALL provide functions in the existing output package

### Requirement 5

**User Story:** As a developer, I want all existing tests to pass after refactoring, so that I have confidence the refactoring preserves behavior.

#### Acceptance Criteria

1. WHEN the refactoring is complete THEN the System SHALL pass all 1900+ existing tests without modification
2. WHEN public function signatures change THEN the System SHALL provide backward-compatible aliases in the original module
3. WHEN imports are reorganized THEN the System SHALL re-export public symbols from research_agent.py for backward compatibility
4. IF a test fails after refactoring THEN the System SHALL fix the implementation to match expected behavior rather than modifying the test

### Requirement 6

**User Story:** As a developer, I want clear module boundaries with minimal coupling, so that changes in one module do not cascade to others.

#### Acceptance Criteria

1. WHEN modules communicate THEN the System SHALL use well-defined interfaces via function parameters and return values
2. WHEN modules share types THEN the System SHALL import from the centralized types.py module
3. WHEN modules share configuration THEN the System SHALL import from the settings module using get_settings()
4. WHEN circular imports would occur THEN the System SHALL restructure to eliminate the cycle using dependency injection or interface extraction
