"
# Implementation Plan

- [x] 1. Enhance existing QA analyzer to leverage Primr infrastructure


  - Integrate with existing `consolidate_working_folder` for structured context
  - Use existing workspace section files for granular analysis
  - Build on existing `grade_report` function rather than replacing entirely
  - Leverage existing industry/overview context for better assessment
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 1.1 Write property test for Primr standards coverage


  - **Property 1: Assessment covers Primr quality standards**
  - **Validates: Requirements 1.1**

- [x] 2. Implement robust JSON response parsing



  - Create `SimpleJSONParser` to extract structured feedback reliably
  - Handle markdown-wrapped JSON, inline JSON, and malformed responses
  - Implement regex fallback for key information extraction
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2.1 Write property test for actionable feedback generation


  - **Property 2: Feedback is actionable and specific**
  - **Validates: Requirements 2.1**

- [x] 3. Add basic error handling and retry logic


  - Implement single model fallback (gemini-3-flash if primary fails)
  - Add exponential backoff for network/service issues
  - Create diagnostic fallback that explains failures instead of generic responses
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3.1 Write property test for comprehensive report reliability


  - **Property 3: Comprehensive reports complete successfully**
  - **Validates: Requirements 3.1**

- [x] 4. Update QA integration to use enhanced system


  - Enhance existing QA integration to use workspace context
  - Update CLI output to show practical recommendations instead of generic scores
  - Modify detailed report generation to leverage section-level analysis
  - _Requirements: 2.1, 2.4_

- [x] 5. Test with real reports and validate improvements

  - Test specifically with Evertrue LLC report to ensure proper assessment
  - Validate that comprehensive reports receive meaningful feedback using workspace context
  - Verify error cases provide diagnostic information instead of generic fallbacks
  - Test integration with existing section-level analysis
  - _Requirements: 3.1, 2.1_

- [x] 5.1 Write unit tests for enhanced components


  - Test enhanced `SimpleQAAnalyzer` with workspace context integration
  - Test `SimpleJSONParser` with various response formats
  - Test error handling and fallback scenarios
  - Test integration with existing `grade_report` function
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 6. Deploy and monitor enhanced QA system


  - Deploy enhanced system with gradual rollout to monitor success rates
  - Add logging for assessment completion rates and error types
  - Monitor that 95%+ of comprehensive reports get proper assessment
  - Track improvement in feedback quality using workspace context
  - _Requirements: 3.1, 3.5_