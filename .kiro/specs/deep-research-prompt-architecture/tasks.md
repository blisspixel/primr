# Implementation Plan

- [x] 1. Create shared components infrastructure



  - [x] 1.1 Create `src/primr/prompts/shared/` directory structure

    - Create directory for shared YAML components
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 1.2 Create `shared/epistemic_rules.yaml` with all epistemic rules


    - Extract rules from existing hardcoded prompts in `deep_research.py`
    - Include: fact_inference_hypothesis, risk_framing, hedging_language, transformation_rule, confidence_labeling
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 1.3 Create `shared/formatting.yaml` with all formatting standards

    - Extract rules from existing hardcoded prompts
    - Include: paragraphs, bullets, bullet_depth, no_dashes, citations, tables, numbers, headings
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 1.4 Create `shared/personas.yaml` with consulting personas


    - Include: senior_consultant, ai_strategist, technical_architect
    - _Requirements: 2.3_
  - [x] 1.5 Write property test for shared component loading


    - **Property 2: Shared Component Inclusion**
    - **Validates: Requirements 2.1, 7.1, 7.2, 7.3, 7.4**


- [x] 2. Implement SharedComponentLoader


  - [x] 2.1 Create `src/primr/prompts/schema.py` with dataclasses


    - Define: SharedComponents, SectionSpec, PromptConfig, DataSource, StrategyModule
    - _Requirements: 6.1_
  - [x] 2.2 Create `src/primr/prompts/shared_loader.py`


    - Implement SharedComponentLoader class with caching
    - Load epistemic_rules.yaml, formatting.yaml, personas.yaml
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 2.3 Write property test for formatting rules inclusion

    - **Property 3: Formatting Rules Inclusion**
    - **Validates: Requirements 2.2, 8.1, 8.2, 8.3, 8.4, 8.5**

- [x] 3. Create strategic_layer.yaml prompt config


  - [x] 3.1 Extract `_build_strategic_layer_prompt()` content to YAML


    - Create `src/primr/prompts/strategic_layer.yaml`
    - Include all sections: Narrative Gap Analysis, Competitive Deep-Dive, Industry Dynamics, Strategic Assessment, Risk Analysis, Strategic Options, Second-Order Insights, Discovery Questions
    - Reference: `docs/research putting it together.txt` for architecture patterns
    - _Requirements: 1.2, 10.3_
  - [x] 3.2 Update `_build_strategic_layer_prompt()` to use YAML loader

    - Replace hardcoded string with call to PromptComposer
    - _Requirements: 1.2, 1.4_

- [x] 4. Implement PromptComposer


  - [x] 4.1 Create `src/primr/prompts/composer.py` with PromptComposer class


    - Implement compose() method that loads YAML and merges shared components
    - Implement variable substitution for {company_name}, {website_url}, {current_date}, {cloud_vendor}
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [x] 4.2 Implement shared component merging with override support

    - Prompt-specific values override shared values
    - _Requirements: 2.4, 2.5_

  - [x] 4.3 Implement context-aware prompt building

    - Include hierarchy of truth instructions when has_stage1_context=True
    - Generate standalone prompts when no context available
    - _Requirements: 10.1, 10.2, 10.4, 10.5_
  - [x] 4.4 Write property test for variable substitution

    - **Property 4: Variable Substitution Completeness**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

  - [x] 4.5 Write property test for missing variable handling
    - **Property 5: Missing Variable Graceful Handling**

    - **Validates: Requirements 9.5**
  - [x] 4.6 Write property test for context-aware building
    - **Property 13: Context-Aware Prompt Building**
    - **Validates: Requirements 10.1, 10.2, 10.4**

- [x] 5. Checkpoint - Ensure all tests pass


  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Enhance company_overview.yaml for comprehensive output

  - [x] 6.1 Review and expand company_overview.yaml sections
    - Ensure all 20+ sections across 5 parts are defined
    - Add depth guidance for 20-70 page output
    - _Requirements: 3.1, 3.5_
  - [x] 6.2 Add table requirements to appropriate sections
    - Financial Profile, Competitive Landscape, Company History should require tables
    - _Requirements: 3.4_
  - [x] 6.3 Write property test for section completeness
    - **Property 6: Section Completeness**
    - **Validates: Requirements 3.1, 3.5**
  - [x] 6.4 Write property test for section spec rendering
    - **Property 7: Section Spec Rendering**
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [ ] 7. Refactor ConsultingPromptBuilder to use PromptComposer
  - [ ] 7.1 Update ConsultingPromptBuilder.build_comprehensive_prompt()
    - Delegate to PromptComposer.compose("company_overview", context)
    - Remove hardcoded prompt string
    - _Requirements: 1.3_
  - [ ] 7.2 Update build_company_overview_prompt() in loader.py
    - Use PromptComposer internally
    - Maintain backward compatibility with existing API
    - _Requirements: 1.1, 1.4_
  - [ ] 7.3 Write property test for YAML loading round-trip
    - **Property 1: YAML Loading Round-Trip**
    - **Validates: Requirements 1.1**

- [x] 8. Implement StrategyModuleRegistry


  - [x] 8.1 Create `src/primr/prompts/registry.py`

    - Implement StrategyModuleRegistry class
    - Auto-discover modules from strategies/ directory
    - _Requirements: 4.5, 11.1_

  - [x] 8.2 Implement DataSource handling
    - Parse data_sources from strategy YAML
    - Resolve file paths relative to docs/ directory
    - Filter by vendor when applicable

    - _Requirements: 13.1, 13.2, 13.3_
  - [x] 8.3 Implement get_context_files() method
    - Return list of paths for files to upload to File Search Store
    - _Requirements: 4.6, 13.3_
  - [x] 8.4 Write property test for strategy discovery
    - **Property 9: Strategy Module Discovery**
    - **Validates: Requirements 4.5, 11.1, 11.4**
  - [x] 8.5 Write property test for data source vendor filtering
    - **Property 19: Data Source Vendor Filtering**
    - **Validates: Requirements 4.6, 13.2**

- [x] 9. Migrate ai_strategy.yaml to strategies/ directory



  - [x] 9.1 Move ai_strategy.yaml to strategies/ai_strategy.yaml




    - Update file location
    - Add data_sources section pointing to vendor research files
    - _Requirements: 4.1, 13.1_
  - [x] 9.2 Add vendor-specific data source definitions

    - Point to docs/vendor-research-azure-2025-12.txt, etc.
    - _Requirements: 5.2, 13.2_
  - [x] 9.3 Update build_ai_strategy_prompt() to use PromptComposer


    - Use compose_strategy("ai", context) internally
    - _Requirements: 1.1_

  - [x] 9.4 Write property test for vendor-specific content

    - **Property 15: Vendor-Specific Content**
    - **Validates: Requirements 5.2**

- [x] 10. Checkpoint - Ensure all tests pass


  - Ensure all tests pass, ask the user if questions arise.



- [x] 11. Create placeholder strategy modules


  - [x] 11.1 Create strategies/cloud_migration.yaml (placeholder)

    - Define basic structure with sections for cloud assessment
    - Mark as placeholder for future implementation

    - _Requirements: 4.2, 11.1_
  - [x] 11.2 Create strategies/data_strategy.yaml (placeholder)

    - Define basic structure with sections for data platform assessment
    - Mark as placeholder for future implementation
    - _Requirements: 11.1_

  - [x] 11.3 Write property test for custom strategy shared components

    - **Property 11: Custom Strategy Shared Components**
    - **Validates: Requirements 11.3**

- [x] 12. Integrate data sources into research pipeline



  - [x] 12.1 Update AI strategy generation to use data sources from YAML

    - Load vendor research files based on --cloud-vendor flag
    - Upload to File Search Store before Deep Research call
    - _Requirements: 4.6, 13.3_

  - [x] 12.2 Add --list-strategies command (foundation for v1.2.6)

    - Display all available strategy modules with descriptions
    - This prepares for future --strategy flag
    - _Requirements: 4.5_

- [x] 13. Update DeepResearchOrchestrator integration


  - [x] 13.1 Update generate_report() to use PromptComposer

    - Replace ConsultingPromptBuilder with PromptComposer
    - _Requirements: 1.1, 1.3_
  - [x] 13.2 Add strategy module support to research pipeline
    - Generate separate Deep Research calls for each strategy
    - Use company overview as context for strategy generation
    - Implemented via --strategy flag in task 14
    - _Requirements: 5.4_
  - [x] 13.3 Implement data source file upload
    - Upload vendor research files from strategy data_sources
    - Implemented in _generate_ai_strategy_section()
    - _Requirements: 13.3, 13.5_

- [x] 14. Implement --strategy CLI flag (v1.2.6 feature)
  - [x] 14.1 Add --strategy argument to CLI parser
    - Accept comma-separated strategy names (e.g., --strategy ai,cloud)
    - Validate against available strategies from registry
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 14.2 Create generate_strategy() function in research_agent.py
    - Generic function to generate any strategy using PromptComposer
    - Accept strategy name, company name, context path, vendor
    - _Requirements: 4.1, 11.3_
  - [x] 14.3 Update research pipeline to support multiple strategies
    - After company overview, loop through requested strategies
    - Use company overview as context for each strategy
    - Generate separate output files per strategy
    - _Requirements: 4.3, 5.4_
  - [x] 14.4 Add --strategy-only flag for running strategies on existing research

    - Skip company overview generation
    - Require --context-folder with existing research
    - _Requirements: 5.4_

- [x] 15. Implement error handling
  - [x] 15.1 Add PromptConfigNotFoundError
    - Raise when YAML file doesn't exist
    - Include file path and available alternatives
    - _Requirements: 1.5_
  - [x] 15.2 Add PromptConfigValidationError
    - Raise when schema validation fails
    - Include field name and expected type
    - _Requirements: 11.2, 11.5_
  - [x] 15.3 Write property test for malformed YAML handling
    - **Property 17: Malformed YAML Error Handling**
    - **Validates: Requirements 1.5**

- [x] 16. Update public API exports
  - [x] 16.1 Update src/primr/prompts/__init__.py
    - Export PromptComposer, PromptContext, ComposedPrompt
    - Export StrategyModuleRegistry, StrategyModule
    - Maintain backward compatibility with existing exports
    - _Requirements: 1.1_

- [x] 17. Checkpoint - Ensure all tests pass
  - All 2278 tests pass (89 prompt tests, 2189 other tests)

- [x] 18. Documentation and cleanup
  - [x] 18.1 Add header comments to all YAML files
    - All YAML files have proper header comments
    - Document dependencies on shared components
    - _Requirements: 12.1, 12.3_
  - [x] 18.2 Update docs/INTERNALS.md with prompt architecture
    - Document YAML schema
    - Include example for creating new strategy modules
    - Reference: `docs/documentation gemini deep research.txt`
    - _Requirements: 12.4_
  - [-] 18.3 Remove hardcoded prompts from deep_research.py
    - Skipped: Legacy prompts kept for backward compatibility
    - New code uses YAML-based prompts via PromptComposer
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 19. Final Checkpoint - Ensure all tests pass
  - All 2278 tests pass (2 skipped)
