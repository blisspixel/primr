# Implementation Plan

- [x] 1. Update config module for lazy validation




  - [ ] 1.1 Refactor config.py to remove import-time API key validation
    - Add private variables for API keys loaded from environment
    - Create `get_gemini_api_key()`, `get_search_api_key()`, `get_search_engine_id()` lazy accessors
    - Create `ConfigValidationResult` dataclass for structured validation results
    - Create `validate_config()` function that returns validation result
    - Create `require_valid_config()` guard function
    - Remove the `if not GEMINI_API_KEY: raise ValueError` blocks


    - Keep backward compatible constants for non-sensitive config

    - _Requirements: 3.1, 3.2, 3.3, 3.5_
  - [ ] 1.2 Write property test for lazy API key validation
    - **Property 2: Lazy API key validation**
    - **Validates: Requirements 3.2**




  - [ ] 1.3 Write unit tests for config validation functions
    - Test `validate_config()` returns correct errors when keys missing
    - Test `require_valid_config()` raises ConfigurationError when invalid
    - Test backward compatible constants are still accessible
    - _Requirements: 3.1, 3.2, 3.4, 3.5_


- [ ] 2. Create config/prompts.py module
  - [ ] 2.1 Implement PromptTemplate dataclass and PromptRegistry
    - Create `PromptTemplate` frozen dataclass with name, template, required_vars


    - Create `PromptError` exception class
    - Create `PromptRegistry` singleton with lazy loading
    - Implement `get()`, `render()`, `list_prompts()`, `reload()` methods




    - Implement `_load_prompts_from_file()` and `_extract_template_vars()` helpers
    - _Requirements: 4.3_
  - [ ] 2.2 Implement public interface functions
    - Create `get_registry()` function

    - Create `generate_prompt()` function (main interface)
    - Create `list_prompts()` and `get_prompt_template()` functions
    - _Requirements: 4.3_
  - [ ] 2.3 Write unit tests for prompts module
    - Test prompt loading from prompts.json
    - Test variable extraction from templates
    - Test error handling for missing prompts and variables
    - _Requirements: 4.3_



- [ ] 3. Create workspace.py module
  - [x] 3.1 Implement workspace dataclasses and constants


    - Create `WorkspaceConfig` frozen dataclass with computed properties




    - Create `ConsolidationResult` dataclass
    - Create `FileValidationResult` dataclass
    - Define `SUPPORTED_EXTENSIONS` frozenset
    - _Requirements: 4.1_

  - [ ] 3.2 Implement workspace functions
    - Move `create_working_folder()` from research_agent.py
    - Create `create_working_folder_simple()` for backward compatibility
    - Create `working_folder()` context manager

    - Move `consolidate_working_folder()` from research_agent.py
    - Move `save_section_output()` from research_agent.py
    - Move `validate_context_files()` from research_agent.py
    - Add `list_section_files()` and `get_section_content()` helpers
    - _Requirements: 4.1, 4.2_

  - [ ] 3.3 Write unit tests for workspace module
    - Test folder creation with various inputs
    - Test consolidation produces correct output
    - Test file validation categorizes files correctly

    - _Requirements: 4.1_

- [x] 4. Checkpoint - Ensure all tests pass


  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create structured_research.py module



  - [ ] 5.1 Implement structured research dataclasses
    - Create `ScrapedData` dataclass with computed properties
    - Create `AnalysisResult` dataclass
    - Create `ResearchContext` dataclass

    - Create `ProgressReporter` protocol
    - _Requirements: 1.2_
  - [ ] 5.2 Extract and refactor run_research function
    - Move `run_research()` from research_agent.py
    - Refactor to use new dataclasses
    - Add optional `reporter` parameter for progress

    - _Requirements: 1.2, 2.1_
  - [ ] 5.3 Extract phase functions
    - Create `_collect_data()` for Phase 1 (data collection)
    - Create `_analyze_content()` for Phase 2 (analysis)

    - Create `_generate_sections()` for Phase 3 (section generation)
    - Ensure each function is under 50 lines
    - _Requirements: 2.1, 2.5_
  - [x] 5.4 Extract section research functions


    - Move `research_section()` from research_agent.py
    - Move `generate_initial_overview()` from research_agent.py
    - Refactor to use ResearchContext



    - _Requirements: 1.2_
  - [ ] 5.5 Create research_pipeline context manager
    - Implement `research_pipeline()` context manager
    - Handle setup, cleanup, and error recovery
    - _Requirements: 1.2_
  - [ ] 5.6 Write unit tests for structured research
    - Test phase functions in isolation
    - Test data flow through pipeline
    - Test error handling
    - _Requirements: 1.2, 2.1_

- [ ] 6. Create vendor_research.py module
  - [ ] 6.1 Implement vendor research dataclasses
    - Create `VendorResearchFile` frozen dataclass with computed properties
    - Create `VendorResearchResult` dataclass
    - Create `VendorPromptBuilder` protocol
    - _Requirements: 1.5_
  - [ ] 6.2 Extract vendor research functions
    - Move `_get_vendor_research_path()` from research_agent.py
    - Move `_is_vendor_research_current()` from research_agent.py
    - Move `_generate_vendor_research()` from research_agent.py
    - Move `_get_or_generate_vendor_research()` from research_agent.py
    - Rename to public functions without underscore prefix
    - _Requirements: 1.5_
  - [ ] 6.3 Refactor to async and add sync wrapper
    - Convert `generate_vendor_research()` to async
    - Convert `get_or_generate_vendor_research()` to async
    - Add `get_or_generate_vendor_research_sync()` wrapper
    - _Requirements: 1.5_
  - [ ] 6.4 Extract vendor prompt building
    - Create `_build_vendor_prompt()` function
    - Create `_get_vendor_metadata()` helper
    - Ensure prompt building is under 50 lines
    - _Requirements: 1.5, 2.4, 2.5_
  - [ ] 6.5 Write unit tests for vendor research
    - Test path generation for different vendors
    - Test current month detection
    - Test manual file preference for Azure
    - _Requirements: 1.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Create ai_strategy.py module
  - [x] 8.1 Implement AI strategy dataclasses and enums
    - Create `CloudVendor` enum with display_name property
    - Create `AIStrategyConfig` frozen dataclass
    - Create `AIStrategyResult` dataclass
    - Create `StrategyPromptContext` dataclass
    - Create `StrategyPromptBuilder` protocol
    - _Requirements: 1.4_
  - [x] 8.2 Extract AI strategy generation functions
    - Move `_generate_ai_strategy_section()` from research_agent.py
    - Move `_build_ai_strategy_prompt()` from research_agent.py
    - Rename to public functions
    - _Requirements: 1.4, 2.3_
  - [x] 8.3 Refactor to async and decompose
    - Convert `generate_ai_strategy()` to async
    - Add `generate_ai_strategy_sync()` wrapper
    - Create `_gather_context()` for context collection
    - Create `_execute_strategy_research()` for Deep Research call
    - Create `_save_strategy_outputs()` for output generation
    - Ensure each function is under 50 lines
    - _Requirements: 1.4, 2.3, 2.5_
  - [x] 8.4 Write unit tests for AI strategy
    - Test CloudVendor enum values and display names
    - Test config validation
    - Test prompt building
    - _Requirements: 1.4, 2.3_

- [x] 9. Create deep_research_runner.py module
  - [x] 9.1 Implement deep research dataclasses and enums
    - Create `PreflightStatus` enum
    - Create `PreflightCheck` dataclass
    - Create `PreflightResult` dataclass with computed properties
    - Create `DeepResearchConfig` dataclass
    - Create `DeepResearchResult` dataclass
    - Create `DeepResearchProgress` protocol
    - _Requirements: 1.3_
  - [x] 9.2 Extract preflight validation
    - Move preflight validation logic from `perform_deep_research()`
    - Create `validate_preflight()` function returning PreflightResult
    - Ensure clear error messages with guidance
    - _Requirements: 1.3, 2.2_
  - [x] 9.3 Extract deep research execution
    - Move `perform_deep_research()` from research_agent.py
    - Refactor to use new dataclasses
    - Convert to async function
    - Add `perform_deep_research_sync()` wrapper
    - _Requirements: 1.3, 2.2_
  - [x] 9.4 Decompose into phase functions
    - Create `_execute_research()` for Deep Research API call
    - Create `_process_results()` for result parsing
    - Create `_generate_outputs()` for DOCX generation
    - Move `_convert_deep_research_to_docx()` to this module
    - Ensure each function is under 50 lines
    - _Requirements: 1.3, 2.2, 2.5_
  - [x] 9.5 Create deep_research_session context manager
    - Implement async context manager for session lifecycle
    - Handle pre-flight, resource allocation, cleanup
    - _Requirements: 1.3_
  - [x] 9.6 Write unit tests for deep research runner
    - Test preflight validation with various inputs
    - Test config dataclass validation
    - Test result dataclass computed properties
    - _Requirements: 1.3, 2.2_

- [x] 10. Checkpoint - Ensure all tests pass (2108 tests passing)
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Create cli.py module
  - [x] 11.1 Implement CLI dataclasses and enums
    - Create `Command` enum for CLI commands
    - Create `CLIConfig` frozen dataclass
    - Create `CLIRunner` protocol
    - _Requirements: 1.6_
  - [x] 11.2 Extract argument parsing
    - Move argument parser setup from `main()` in research_agent.py
    - Create `parse_args()` function returning CLIConfig
    - Ensure clean separation of parsing and execution
    - _Requirements: 1.6_
  - [x] 11.3 Extract main entry point
    - Move `main()` from research_agent.py
    - Refactor to use CLIConfig and delegate to runners
    - Add optional runner parameter for testing
    - Return exit codes for scripting
    - _Requirements: 1.6_
  - [x] 11.4 Extract doctor command
    - Move `run_doctor()` from research_agent.py
    - Integrate with `validate_config()` from config module
    - Return boolean for scripting
    - _Requirements: 1.6, 3.4_
  - [x] 11.5 Extract utility commands
    - Move `process_csv()` from research_agent.py
    - Move `_list_recent_outputs()` from research_agent.py
    - Move `_check_api_quota()` from research_agent.py
    - Move `_clean_temp_files()` from research_agent.py
    - Move `_open_file()` from research_agent.py
    - _Requirements: 1.6_
  - [x] 11.6 Write unit tests for CLI
    - Test argument parsing with various inputs
    - Test command dispatch
    - Test exit codes
    - _Requirements: 1.6_

- [x] 12. Refactor research_agent.py to orchestration hub
  - [x] 12.1 Implement orchestration dataclasses
    - Create `ResearchConfig` frozen dataclass
    - Create `ResearchResult` dataclass
    - Create `ResearchRunner` protocol
    - _Requirements: 1.1_
  - [x] 12.2 Refactor perform_research to delegate
    - Simplify `perform_research()` to validate and delegate
    - Create `get_runner()` to select appropriate runner
    - Remove all implementation details (moved to other modules)
    - _Requirements: 1.1, 2.1_
  - [x] 12.3 Add backward compatible re-exports
    - Import and re-export `run_research`, `research_section` from structured_research
    - Import and re-export `create_working_folder`, `consolidate_working_folder` from workspace
    - Import and re-export `main`, `run_doctor` from cli
    - Define explicit `__all__` list
    - _Requirements: 5.2, 5.3_
  - [x] 12.4 Write property test for module import compatibility
    - **Property 1: Module import compatibility**
    - **Validates: Requirements 1.1, 3.1, 3.3, 5.2, 5.3**

- [x] 13. Checkpoint - Ensure all tests pass (2144 tests passing)
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Write property tests for module independence
  - [x] 14.1 Write property test for function size constraint
    - **Property 3: Function size constraint**
    - **Validates: Requirements 2.5**
  - [x] 14.2 Write property test for module independence
    - **Property 4: Module independence**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 15. Final verification and cleanup
  - [x] 15.1 Run full test suite
    - Execute `pytest tests/ -v`
    - Verify all 1900+ tests pass
    - Fix any regressions
    - _Requirements: 5.1_
  - [x] 15.2 Verify backward compatibility
    - Test imports from research_agent.py work
    - Test CLI entry point works
    - Test programmatic API works
    - _Requirements: 5.2, 5.3_
  - [x] 15.3 Remove dead code from research_agent.py


    - Remove any functions that were moved and are no longer needed
    - Verify file is under 300 lines
    - _Requirements: 1.1_
  - [x] 15.4 Update module docstrings
    - Add comprehensive docstrings to each new module
    - Document public API and usage examples
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 16. Final Checkpoint - Ensure all tests pass (2173 tests passing)
  - Ensure all tests pass, ask the user if questions arise.
