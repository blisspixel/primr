# Implementation Plan

- [x] 1. Remove memo-style formatting from all report prompts
  - [x] 1.1 Update ai_strategy.py to use clean professional headers
    - Remove "RESEARCH REQUEST:", "TO:", "FROM:", "SUBJECT:" patterns
    - Replace with clean markdown headers: `# AI Strategy: {Company Name}`
    - Keep all strategic content and instructions, just fix the output format
    - _Requirements: 5.4_
  - [x] 1.2 Update deep_research.py to use clean headers
    - Remove "RESEARCH REQUEST: Strategic Company Overview" pattern
    - Replace with `# Strategic Company Overview: {Company Name}`
    - _Requirements: 5.4_
  - [x] 1.3 Update vendor_research.py to use clean headers
    - Remove memo-style formatting from vendor research prompts
    - _Requirements: 5.4_
  - [x] 1.4 Update research_agent.py to use clean headers
    - Remove any remaining memo-style patterns
    - _Requirements: 5.4_
  - [ ]* 1.5 Write property test for no memo-style headers
    - **Property 11: No Memo-Style Headers**
    - **Validates: Requirements 5.4**

- [x] 2. Create FileSearchStoreManager for context lifecycle
  - [x] 2.1 Implement FileSearchStoreManager class
    - Create `create_store(display_name)` method
    - Create `upload_context(store_name, content, filename)` method
    - Create `delete_store(store_name)` method
    - Add proper error handling and logging
    - _Requirements: 2.1, 2.4_
  - [ ]* 2.2 Write property test for store cleanup
    - **Property 4: File Search Store Cleanup**
    - **Validates: Requirements 2.4**

- [x] 3. Create ConsultingPromptBuilder for comprehensive prompts
  - [x] 3.1 Implement ConsultingPromptBuilder class
    - Create `build_comprehensive_prompt(company_name, website_url, store_name)` method
    - Include all 10 chapter specifications in single prompt
    - Inject consulting persona ("Senior Strategy Consultant")
    - Include hierarchy of truth instructions
    - Include formatting and epistemic standards
    - _Requirements: 3.2, 6.1, 6.2, 6.3, 6.4_
  - [ ]* 3.2 Write property test for prompt completeness
    - **Property 6: Prompt Contains All Chapters**
    - **Validates: Requirements 3.2**
  - [ ]* 3.3 Write property test for consulting persona
    - **Property 7: Consulting Persona Injection**
    - **Validates: Requirements 6.1**

- [x] 4. Create DeepResearchOrchestrator for single-call execution
  - [x] 4.1 Implement DeepResearchOrchestrator class
    - Create `generate_report(company_name, website_url, stage1_context, on_progress)` method
    - Implement single Deep Research API call (not parallel chapters)
    - Implement exponential backoff retry (60s base, 5 attempts max)
    - Implement adaptive polling (5s → 10s → 20s → 30s)
    - Set 60-minute timeout
    - _Requirements: 1.2, 3.1, 3.3, 3.4, 4.1_
  - [ ]* 4.2 Write property test for single API call
    - **Property 1: Single API Call Per Report**
    - **Validates: Requirements 3.1**
  - [ ]* 4.3 Write property test for exponential backoff
    - **Property 3: Retry with Exponential Backoff**
    - **Validates: Requirements 1.2**
  - [ ]* 4.4 Write property test for progress callbacks
    - **Property 9: Progress Callbacks During Polling**
    - **Validates: Requirements 4.1**

- [x] 5. Create ReportFormatter for clean output
  - [x] 5.1 Implement ReportFormatter class
    - Create `format_report(raw_content, company_name, citation_style)` method
    - Generate clean Table of Contents (no ✓/✗ markers)
    - Apply consistent citation formatting
    - Remove any debug artifacts
    - _Requirements: 1.1, 5.1, 5.2, 5.3, 5.4_
  - [ ]* 5.2 Write property test for no failure markers
    - **Property 2: No Failure Markers in Output**
    - **Validates: Requirements 1.1, 5.1**
  - [ ]* 5.3 Write property test for chapter coverage
    - **Property 5: Complete Chapter Coverage**
    - **Validates: Requirements 5.2**
  - [ ]* 5.4 Write property test for clean output
    - **Property 10: Clean Output Without Debug Artifacts**
    - **Validates: Requirements 5.4**

- [x] 6. Integrate new architecture into research pipeline
  - [x] 6.1 Update deep_research_runner.py to use new orchestrator
    - Replace ResearchNodeExecutor with DeepResearchOrchestrator
    - Wire up FileSearchStoreManager for context
    - Ensure store cleanup in finally block
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1_
  - [x] 6.2 Update report_aggregator.py to use ReportFormatter
    - Remove ✓/✗ marker generation from TOC
    - Use new clean formatting
    - _Requirements: 5.1_
  - [x] 6.3 Ensure scrape-only mode bypasses Deep Research
    - Verify --mode scrape does not call Deep Research API
    - Add suggestion to use scrape mode when quota exhausted
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ]* 6.4 Write property test for scrape mode bypass
    - **Property 8: Scrape Mode Bypasses Deep Research**
    - **Validates: Requirements 7.1**

- [x] 7. Checkpoint - Make sure all tests pass

  - Ensure all tests pass, ask the user if questions arise.

- [-] 8. End-to-end validation

  - [x] 8.1 Run full deep research report generation


    - Execute `primr "Test Company" https://example.com --mode deep`
    - Verify single API call made
    - Verify no ✓/✗ markers in output
    - Verify no memo-style headers
    - Verify all 10 chapters present
    - _Requirements: 1.1, 3.1, 5.1, 5.2_
  - [ ] 8.2 Run scrape-only mode
    - Execute `primr "Test Company" https://example.com --mode scrape`
    - Verify Deep Research API not called
    - Verify complete report generated
    - _Requirements: 7.1, 7.3_
  - [ ] 8.3 Verify AI Strategy output format
    - Check AI Strategy report has clean headers
    - No "RESEARCH REQUEST", "TO:", "FROM:" patterns
    - _Requirements: 5.4_

- [ ] 9. Final Checkpoint - Make sure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
