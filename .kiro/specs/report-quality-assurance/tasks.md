# Implementation Plan

- [ ] 1. Set up QA system foundation and core interfaces
  - Create QA module structure in `src/primr/qa/`
  - Define core data models (QAOptions, QAAnalysis, ClassifiedIssue, QAReport)
  - Implement configuration loading for QA models
  - Set up error handling and retry mechanisms
  - _Requirements: 1.4, 4.1, 4.2, 4.5_

- [ ]* 1.1 Write property test for QA configuration validation
  - **Property 5: Model configuration validation**
  - **Validates: Requirements 4.5**

- [ ] 2. Implement report loading and parsing
  - Create ReportLoader class to find and load existing reports
  - Support loading TXT, DOCX, and PDF formats
  - Extract report metadata and structure sections
  - Handle missing reports with clear error messages
  - _Requirements: 1.3, 5.4_

- [ ]* 2.1 Write property test for report loading
  - **Property 8: Report existence validation**
  - **Validates: Requirements 1.3**

- [ ] 3. Build core QA analyzer with AI model integration
  - Implement QAAnalyzer class with model configuration
  - Create structured prompts for quality assessment
  - Implement citation accuracy checking
  - Add logical consistency analysis
  - Build completeness assessment against report templates
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ]* 3.1 Write property test for QA analysis completeness
  - **Property 1: QA execution completeness**
  - **Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 2.5**

- [ ]* 3.2 Write property test for citation checking
  - **Property 2: Citation accuracy validation**
  - **Validates: Requirements 2.1**

- [ ] 4. Create issue classification and scoring system
  - Implement IssueClassifier to categorize problems by type
  - Add severity calculation (critical, high, medium, low)
  - Build overall quality scoring algorithm
  - Ensure score consistency with section-level assessments
  - _Requirements: 3.1, 3.2, 3.3_

- [ ]* 4.1 Write property test for score consistency
  - **Property 2: Score consistency**
  - **Validates: Requirements 3.1**

- [ ]* 4.2 Write property test for issue location specificity
  - **Property 3: Issue location specificity**
  - **Validates: Requirements 3.3**

- [ ] 5. Build QA report generation and output formatting
  - Create QAReportGenerator for formatted output
  - Implement console display with summary and key issues
  - Add file output in TXT and JSON formats
  - Include specific line references for all issues
  - Add quality score highlighting for scores below 70
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ]* 5.1 Write property test for file persistence
  - **Property 4: File persistence**
  - **Validates: Requirements 3.4, 5.4**

- [ ] 6. Implement CLI command interface
  - Add `primr qa` command to CLI parser
  - Support company name argument and optional flags
  - Implement --model, --verbose, --output-format options
  - Add cost estimation display
  - Integrate with existing CLI error handling patterns
  - _Requirements: 1.1, 1.2, 4.4_

- [ ]* 6.1 Write property test for CLI command execution
  - **Property 1: QA command completeness**
  - **Validates: Requirements 1.1, 1.2**

- [ ] 7. Add auto-QA integration to report generation pipeline
  - Modify research pipeline to support --auto-qa flag
  - Implement automatic QA execution after report completion
  - Ensure QA runs without additional user input
  - Handle QA failures gracefully in auto mode
  - _Requirements: 1.5_

- [ ]* 7.1 Write property test for auto-QA integration
  - **Property 6: Auto-QA integration**
  - **Validates: Requirements 1.5**

- [ ] 8. Integrate QA system with existing Primr commands
  - Update `primr doctor` to verify QA model configuration
  - Modify `primr list` to show QA status for reports
  - Ensure consistent file naming and workspace integration
  - Add QA history preservation with timestamps
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 8.1 Write property test for workspace integration
  - **Property 7: Workspace integration**
  - **Validates: Requirements 5.2, 5.4**

- [ ]* 8.2 Write property test for QA history preservation
  - **Property 8: QA history tracking**
  - **Validates: Requirements 5.5**

- [ ] 9. Add comprehensive error handling and retry logic
  - Implement exponential backoff for API failures
  - Add clear error messages for all failure modes
  - Handle rate limiting and authentication errors
  - Test recovery from partial failures
  - _Requirements: 1.4_

- [ ]* 9.1 Write property test for error recovery
  - **Property 7: Error recovery**
  - **Validates: Requirements 1.4**

- [ ] 10. Create configuration and model management
  - Add QA model configuration to settings
  - Implement model validation and availability checking
  - Support different models for different use cases
  - Add cost estimation for different model choices
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ]* 10.1 Write unit tests for configuration management
  - Test default model selection
  - Test custom model configuration
  - Test invalid configuration handling
  - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [ ] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Add documentation and help text
  - Update CLI help text for new `primr qa` command
  - Add configuration documentation for QA models
  - Create usage examples and best practices guide
  - Update README with QA feature description
  - _Requirements: All_

- [ ]* 12.1 Write integration tests for end-to-end QA workflow
  - Test complete flow: generate report → run QA → verify output
  - Test with different report modes and QA models
  - Test auto-QA integration
  - _Requirements: All_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.