# Implementation Plan

- [x] 1. Register pytest custom marks
  - Add `slow`, `integration`, `smoke`, and `resilience` markers to pytest.ini
  - Verify warnings are eliminated when running pytest
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Implement CLI smoke tests
  - [x] 2.1 Create tests/test_cli_smoke.py with subprocess-based tests
    - Test `primr doctor` returns exit code 0
    - Test `primr --help` displays usage
    - Test `primr --list-strategies` lists modules
    - Test `primr --dry-run` shows estimate without API calls
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [x] 2.2 Write property test for invalid CLI arguments
    - **Property 1: Invalid CLI arguments return non-zero exit code**
    - **Validates: Requirements 2.5**

- [x] 3. Implement API resilience tests
  - [x] 3.1 Create tests/test_ai/test_api_resilience.py
    - Create mock fixtures for 429, 500, and timeout errors
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 3.2 Write property test for retry behavior
    - **Property 2: Retryable errors trigger exponential backoff**
    - **Validates: Requirements 3.1, 3.2, 3.3**
  - [x] 3.3 Write property test for fallback behavior
    - **Property 3: Deep Research fallback on exhausted retries**
    - **Validates: Requirements 3.4**
  - [x] 3.4 Write property test for consecutive failure threshold
    - **Property 4: Consecutive failure threshold stops processing**
    - **Validates: Requirements 3.5, 4.4**

- [x] 4. Checkpoint - Ensure all tests pass
  - All tests pass

- [x] 5. Implement sections_written tests
  - [x] 5.1 Create tests/test_core/test_sections_written.py
    - Test DeepResearchOrchestratorResult.sections_written field
    - Test OrchestratorResult.sections_written propagation
    - _Requirements: 4.1, 4.2_
  - [x] 5.2 Write property test for sections_written accuracy
    - **Property 5: sections_written accuracy and propagation**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 6. Implement citation resolution tests
  - [x] 6.1 Create tests/test_ai/test_citation_properties.py
    - Test Google redirect URL resolution
    - Test direct URL preservation
    - _Requirements: 5.1, 5.2_
  - [x] 6.2 Write property test for URL resolution
    - **Property 6: Google redirect URL resolution**
    - **Validates: Requirements 5.1, 5.2**
  - [x] 6.3 Write property test for graceful degradation
    - **Property 7: URL resolution graceful degradation**
    - **Validates: Requirements 5.3**
  - [x] 6.4 Write property test for deduplication
    - **Property 8: Citation deduplication**
    - **Validates: Requirements 5.4**

- [x] 7. Implement YAML validation tests
  - [x] 7.1 Extend tests/test_prompts/test_report_configs.py
    - Test company_overview.yaml has 21 sections with required fields
    - Test ai_strategy.yaml has vendor guidance for azure, aws, gcp
    - Test accordion_method prompts have required placeholders
    - _Requirements: 6.1, 6.2, 6.4_
  - [x] 7.2 Write property test for malformed YAML handling
    - **Property 9: Malformed YAML raises descriptive error**
    - **Validates: Requirements 6.3**

- [x] 8. Checkpoint - Ensure all tests pass
  - All tests pass

- [x] 9. Implement output format tests
  - [x] 9.1 Create tests/test_output/test_format_consistency.py
    - Test report contains all 21 section headings
    - Test executive summary appears first
    - Test strategic positioning hypothesis appears last
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 9.2 Write property test for table preservation
    - **Property 10: Markdown table to DOCX preservation**
    - **Validates: Requirements 7.4**
  - [x] 9.3 Write property test for heading hierarchy
    - **Property 11: Heading hierarchy preservation**
    - **Validates: Requirements 7.5**

- [x] 10. Implement thread safety tests
  - [x] 10.1 Create tests/test_utils/test_thread_safety.py
    - Test concurrent console writes
    - Test heartbeat thread interaction
    - _Requirements: 8.1, 8.2_
  - [x] 10.2 Write property test for console thread safety
    - **Property 12: Console thread safety**
    - **Validates: Requirements 8.1, 8.2**
  - [x] 10.3 Write property test for file write safety
    - **Property 13: File write thread safety**
    - **Validates: Requirements 8.3**

- [x] 11. Implement cost estimation tests
  - [x] 11.1 Create tests/test_utils/test_cost_accuracy.py
    - Test full mode estimate includes scraping and Deep Research
    - Test AI strategy cost is added when included
    - _Requirements: 9.2, 9.3_
  - [x] 11.2 Write property test for cost accuracy
    - **Property 14: Cost estimate accuracy**
    - **Validates: Requirements 9.1**

- [x] 12. Implement File Search Store lifecycle tests
  - [x] 12.1 Create tests/test_lifecycle/test_file_search_store.py
    - Test store deletion on success
    - Test store deletion on failure
    - _Requirements: 10.1, 10.2_
  - [x] 12.2 Write property test for cleanup
    - **Property 15: File Search Store cleanup**
    - **Validates: Requirements 10.1, 10.2**
  - [x] 12.3 Write property test for upload ordering
    - **Property 16: Context upload ordering**
    - **Validates: Requirements 10.3**

- [x] 13. Final Checkpoint - Ensure all tests pass
  - All 146 tests pass (verified in 136s)

