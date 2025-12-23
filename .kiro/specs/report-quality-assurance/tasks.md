# Implementation Plan

- [x] 1. Set up QA system foundation and integration with report pipeline



  - Create QA module structure in `src/primr/qa/`
  - Define core data models (QAOptions, QAResult, QAAnalysis, ClassifiedIssue)
  - Implement QA integration handler for automatic post-generation QA
  - Set up clean CLI output formatting ("Grade: XX/100")
  - Configure QA to be enabled by default with --no-qa opt-out
  - _Requirements: 1.1, 1.5, 3.1, 4.1, 4.2_

- [x] 1.1 Write property test for automatic QA integration


  - **Property 1: Automatic QA execution**
  - **Validates: Requirements 1.1**

- [x] 2. Implement report loading and parsing



  - Create ReportLoader class to find and load existing reports
  - Support loading TXT, DOCX, and PDF formats
  - Extract report metadata and structure sections
  - Handle missing reports with clear error messages
  - _Requirements: 1.3, 5.4_


- [x] 2.1 Write property test for report loading

  - **Property 8: Report existence validation**
  - **Validates: Requirements 1.3**

- [x] 3. Build core QA analyzer with AI model integration
  - Implement QAAnalyzer class with model configuration
  - Create structured prompts for quality assessment
  - Implement citation accuracy checking
  - Add logical consistency analysis
  - Build completeness assessment against report templates
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3.1 Write property test for QA analysis completeness


  - **Property 1: QA execution completeness**
  - **Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 2.5**

- [x] 3.2 Write property test for citation checking


  - **Property 2: Citation accuracy validation**
  - **Validates: Requirements 2.1**

- [x] 4. Create issue classification and scoring system


  - Implement IssueClassifier to categorize problems by type
  - Add severity calculation (critical, high, medium, low)
  - Build overall quality scoring algorithm
  - Ensure score consistency with section-level assessments
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 4.1 Write property test for score consistency


  - **Property 2: Score consistency**

  - **Validates: Requirements 3.1**



- [x] 4.2 Write property test for issue location specificity
  - **Property 3: Issue location specificity**
  - **Validates: Requirements 3.3**

- [x] 5. Build QA report generation with clean CLI output and detailed storage
  - Create QAReportGenerator for formatted output
  - Implement clean CLI display: "Grade: (XX/100)" (default)
  - Add verbose mode for additional summary information


  - Implement detailed analysis storage in TXT and JSON formats
  - Include specific line references and issue descriptions in detailed files
  - Add warning indicator for scores below 70
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 5.1 Write property test for file persistence
  - **Property 4: File persistence**
  - **Validates: Requirements 3.4, 5.4**




- [x] 6. Implement CLI command for detailed QA review
  - Add `primr qa` command to CLI parser for detailed analysis review
  - Support company name argument to show detailed QA analysis
  - Display comprehensive QA findings when requested
  - Integrate with existing CLI error handling patterns
  - _Requirements: 5.4_

- [x] 6.1 Write property test for detailed QA review command
  - **Property 6: Detailed QA review access**
  - **Validates: Requirements 5.4**

- [x] 7. Integrate QA system as default step in report generation pipeline
  - Modify research pipeline to include automatic QA after report completion
  - Implement --no-qa flag to opt out of quality assurance
  - Ensure QA runs seamlessly without disrupting main workflow
  - Handle QA failures gracefully without breaking report generation
  - Display clean "Grade: XX/100" summary at end of generation
  - _Requirements: 1.1, 1.5, 3.1_

- [x] 7.1 Write property test for default QA integration
  - **Property 1: Default QA execution**
  - **Validates: Requirements 1.1, 3.1**

- [x] 8. Integrate QA system with existing Primr commands
  - Update `primr doctor` to verify QA model configuration
  - Modify `primr list` to show report grades and QA status
  - Ensure consistent file naming and workspace integration
  - Add QA history preservation with timestamps
  - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [x] 8.1 Write property test for workspace integration
  - **Property 7: Workspace integration**
  - **Validates: Requirements 5.2, 5.4**

- [x] 8.2 Write property test for QA history preservation
  - **Property 8: QA history tracking**
  - **Validates: Requirements 5.5**

- [x] 9. Add comprehensive error handling and retry logic
  - Implement exponential backoff for API failures
  - Add clear error messages for all failure modes
  - Handle rate limiting and authentication errors
  - Test recovery from partial failures
  - _Requirements: 1.4_

- [x] 9.1 Write property test for error recovery
  - **Property 7: Error recovery**
  - **Validates: Requirements 1.4**

- [x] 10. Create configuration and model management
  - Add QA model configuration to settings
  - Implement model validation and availability checking
  - Support different models for different use cases
  - Add cost estimation for different model choices
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 10.1 Write unit tests for configuration management
  - Test default model selection
  - Test custom model configuration
  - Test invalid configuration handling
  - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [x] 11. Checkpoint - Ensure all tests pass


  - Ensure all tests pass, ask the user if questions arise.


- [x] 12. Add documentation and help text

  - Update CLI help text for new `primr qa` command
  - Add configuration documentation for QA models
  - Create usage examples and best practices guide
  - Update README with QA feature description
  - _Requirements: All_

- [x] 12.1 Write integration tests for end-to-end QA workflow
  - Test complete flow: generate report → run QA → verify output
  - Test with different report modes and QA models
  - Test auto-QA integration
  - _Requirements: All_

- [x] 13. Final checkpoint - Ensure all tests pass



  - Ensure all tests pass, ask the user if questions arise.