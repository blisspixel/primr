# Implementation Plan

- [x] 1. Create Theme and Terminal Capability Foundation



  - [x] 1.1 Create theme.py with Theme dataclass and terminal-aware factory

    - Define Theme dataclass with all indicators, progress chars, box drawing, and color codes
    - Implement `Theme.for_terminal()` factory that adapts to color/unicode support
    - _Requirements: 1.4, 15.1, 15.5_

  - [x] 1.2 Write property test for symbol vocabulary consistency

    - **Property 2: Symbol Vocabulary Consistency**
    - **Validates: Requirements 1.4**

  - [x] 1.3 Create terminal.py with TerminalCapabilities detection

    - Detect color support (isatty, NO_COLOR, TERM)
    - Detect unicode support from encoding
    - Detect cursor movement support
    - Get terminal width with fallback
    - Detect if interactive vs piped
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 1.4 Write property test for color adaptation

    - **Property 30: Color Adaptation**
    - **Validates: Requirements 15.1, 15.3, 15.5**


- [ ] 2. Implement Visual Hierarchy System
  - [x] 2.1 Refactor console.py to use Theme and implement four visual levels


    - Level 1: Phase (bold, colored, separators)
    - Level 2: Step (indicator + text)
    - Level 3: Detail (indented, muted)
    - Level 4: Result (highlighted)
    - Consistent 2-space indentation per level
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 2.2 Write property test for visual hierarchy consistency
    - **Property 1: Visual Hierarchy Consistency**
    - **Validates: Requirements 1.1, 1.3**
  - [ ] 2.3 Implement intelligent text wrapping and truncation
    - Respect terminal width for all output
    - Smart truncation with ellipsis
    - Word-aware wrapping for long messages
    - _Requirements: 1.5, 15.2_
  - [ ] 2.4 Write property test for terminal width respect
    - **Property 3: Terminal Width Respect**
    - **Validates: Requirements 1.5, 15.2**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Build Progress Display System
  - [ ] 4.1 Create progress.py with ProgressDisplay class
    - Implement bounded() for progress bars with percentage, count, label
    - Implement unbounded() for spinners with elapsed time
    - In-place updates using carriage return
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ] 4.2 Write property test for progress bar rendering
    - **Property 4: Progress Bar Rendering**
    - **Validates: Requirements 2.1**
  - [ ] 4.3 Implement contextual time display
    - No time for < 1s operations
    - Completion-only time for 1-10s
    - Live elapsed time for > 10s
    - ETA calculation when progress > 10%
    - _Requirements: 2.5, 2.6, 4.1, 4.2, 4.3_
  - [ ] 4.4 Write property test for time display thresholds
    - **Property 5: Time Display Thresholds**
    - **Validates: Requirements 2.5, 4.1, 4.2, 4.3**
  - [ ] 4.5 Implement adaptive time formatting
    - Seconds for < 60s
    - "Xm Ys" for 60s-3600s
    - "Xh Ym" for >= 3600s
    - _Requirements: 4.4_
  - [ ] 4.6 Write property test for adaptive time formatting
    - **Property 6: Adaptive Time Formatting**
    - **Validates: Requirements 4.4**
  - [ ] 4.7 Implement "safe to leave" indicator for long operations
    - Show indicator when expected duration > 5 minutes
    - _Requirements: 4.5_

- [ ] 5. Implement Phase Orchestration Display
  - [ ] 5.1 Create PhaseDisplay class with roadmap visualization
    - show_roadmap() for initial phase overview
    - enter_phase() for phase entry banners
    - complete_phase() for phase summaries
    - mini_roadmap() for compact progress indicator
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ] 5.2 Write property test for phase header completeness
    - **Property 7: Phase Header Completeness**
    - **Validates: Requirements 3.2**
  - [ ] 5.3 Write property test for phase summary completeness
    - **Property 8: Phase Summary Completeness**
    - **Validates: Requirements 3.3**
  - [ ] 5.4 Write property test for roadmap indicator generation
    - **Property 9: Roadmap Indicator Generation**
    - **Validates: Requirements 3.4**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Build Error and Warning Presentation
  - [ ] 7.1 Create ErrorDisplay class with recovery guidance
    - Define ERROR_GUIDANCE mapping for known error types
    - Implement show_error() with boxed display
    - Include error type, description, and fix command
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [ ] 7.2 Write property test for error presentation completeness
    - **Property 10: Error Presentation Completeness**
    - **Validates: Requirements 5.2**
  - [ ] 7.3 Implement error grouping by category
    - Group errors by category prefix
    - Show count per category
    - _Requirements: 5.6_
  - [ ] 7.4 Write property test for error grouping
    - **Property 11: Error Grouping**
    - **Validates: Requirements 5.6**
  - [ ] 7.5 Implement warning and degradation display
    - Yellow/amber styling for warnings
    - Fallback explanations
    - Affected section indicators
    - Warning summary at phase end
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [ ] 7.6 Write property test for status styling consistency
    - **Property 12: Status Styling Consistency**
    - **Validates: Requirements 5.1, 6.1, 15.1, 15.3, 15.5**

- [ ] 8. Implement Final Output Presentation
  - [ ] 8.1 Create CompletionDisplay class
    - Success banner with company name
    - File listing with types and sizes
    - Summary table with metrics
    - Cost variance explanation when needed
    - AI strategy highlighting
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - [ ] 8.2 Write property test for file output formatting
    - **Property 13: File Output Formatting**
    - **Validates: Requirements 7.2, 7.3**
  - [ ] 8.3 Write property test for completion summary completeness
    - **Property 14: Completion Summary Completeness**
    - **Validates: Requirements 7.4**
  - [ ] 8.4 Write property test for cost variance explanation
    - **Property 15: Cost Variance Explanation**
    - **Validates: Requirements 7.5, 10.4**

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Build Doctor Command Display
  - [ ] 10.1 Create DoctorDisplay class
    - Header with version and system info
    - Check results with aligned columns
    - Fix commands for failed checks
    - Impact explanations for warnings
    - Summary with ready/warning/failed states
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  - [ ] 10.2 Write property test for check result formatting
    - **Property 16: Check Result Formatting**
    - **Validates: Requirements 8.2, 8.6**
  - [ ] 10.3 Write property test for failed check fix display
    - **Property 17: Failed Check Fix Display**
    - **Validates: Requirements 8.3**

- [ ] 11. Implement Batch Mode Display
  - [ ] 11.1 Create BatchDisplay class
    - Initial display with total and estimate
    - Compact status lines per company
    - In-place updates when supported
    - Summary table on completion
    - Failure listing with reasons
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [ ] 11.2 Write property test for batch status line completeness
    - **Property 18: Batch Status Line Completeness**
    - **Validates: Requirements 9.2**
  - [ ] 11.3 Write property test for batch summary completeness
    - **Property 19: Batch Summary Completeness**
    - **Validates: Requirements 9.4**

- [ ] 12. Implement Cost Display
  - [ ] 12.1 Enhance cost estimation display
    - Component breakdown
    - Min-max range from historical data
    - Actual vs estimated comparison
    - Variance explanation
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [ ] 12.2 Write property test for cost estimate completeness
    - **Property 20: Cost Estimate Completeness**
    - **Validates: Requirements 10.1, 10.2**

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Build Confirmation Flow
  - [ ] 14.1 Implement confirmation prompt display
    - Show company, mode, duration, cost
    - List expected outputs
    - Accept y/n/q input
    - Handle --yes flag
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_
  - [ ] 14.2 Write property test for confirmation prompt completeness
    - **Property 21: Confirmation Prompt Completeness**
    - **Validates: Requirements 11.1**

- [ ] 15. Enhance Help System
  - [ ] 15.1 Implement grouped help display
    - Organize commands into Research, Utilities, Options groups
    - Show examples for each command
    - Display defaults in brackets
    - Consistent column alignment
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  - [ ] 15.2 Write property test for help command grouping
    - **Property 22: Help Command Grouping**
    - **Validates: Requirements 12.1**
  - [ ] 15.3 Write property test for help example presence
    - **Property 23: Help Example Presence**
    - **Validates: Requirements 12.2**
  - [ ] 15.4 Write property test for help default value display
    - **Property 24: Help Default Value Display**
    - **Validates: Requirements 12.3**
  - [ ] 15.5 Implement command suggestion for typos
    - Calculate edit distance to valid commands
    - Suggest closest match when distance <= 2
    - _Requirements: 12.5, 12.6_
  - [ ] 15.6 Write property test for command suggestion
    - **Property 25: Command Suggestion**
    - **Validates: Requirements 12.5**

- [ ] 16. Implement Output Modes
  - [ ] 16.1 Create output_modes.py with OutputRouter
    - Normal mode (default)
    - Quiet mode (errors and paths only)
    - JSON mode (structured output)
    - Verbose mode (debug details)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_
  - [ ] 16.2 Write property test for quiet mode filtering
    - **Property 26: Quiet Mode Filtering**
    - **Validates: Requirements 13.1**
  - [ ] 16.3 Write property test for JSON output structure
    - **Property 27: JSON Output Structure**
    - **Validates: Requirements 13.2**
  - [ ] 16.4 Write property test for JSON formatting purity
    - **Property 28: JSON Formatting Purity**
    - **Validates: Requirements 13.3**

- [ ] 17. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. Implement Interrupt Handling
  - [ ] 18.1 Add graceful Ctrl+C handling
    - Immediate acknowledgment
    - Complete in-progress file writes
    - Display completed vs incomplete items
    - Show partial outputs saved
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  - [ ] 18.2 Write property test for cancellation output completeness
    - **Property 29: Cancellation Output Completeness**
    - **Validates: Requirements 14.3, 14.4**

- [ ] 19. Integrate with Research Agent
  - [ ] 19.1 Update research_agent.py to use new display components
    - Replace direct console calls with PhaseDisplay
    - Use ProgressDisplay for section processing
    - Use CompletionDisplay for final output
    - Wire up ErrorDisplay for error handling
    - _Requirements: All_
  - [ ] 19.2 Update doctor command to use DoctorDisplay
    - _Requirements: 8.1-8.6_
  - [ ] 19.3 Update batch mode to use BatchDisplay
    - _Requirements: 9.1-9.6_
  - [ ] 19.4 Wire up output mode routing
    - Parse --quiet, --json, --verbose flags
    - Route all output through OutputRouter
    - _Requirements: 13.1-13.5_

- [ ] 20. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
