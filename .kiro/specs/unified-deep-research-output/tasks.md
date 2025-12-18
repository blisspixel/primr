# Implementation Plan

- [x] 1. Create Master Architect component
  - [x] 1.1 Create `src/primr/ai/report_architect.py`
    - Implement `MasterArchitect` class
    - `generate_chapter_plan()` method using gemini-2.0-flash
    - Prompt that decomposes report into 10 chapters
    - Returns JSON with title + research_prompt for each chapter
    - _Requirements: 1.1_
  - [x] 1.2 Write unit test for chapter plan generation
    - **Property 1: Chapter Decomposition**
    - Verify 8-10 chapters produced with required fields
    - **Validates: Requirements 1.1**

- [x] 2. Create Research Node Executor component
  - [x] 2.1 Create `src/primr/ai/research_executor.py`
    - Implement `ResearchNodeExecutor` class
    - `execute_chapter()` method for single chapter Deep Research
    - `execute_all()` method for parallel execution
    - Use `asyncio.Semaphore(3)` for rate limiting
    - _Requirements: 1.2, 4.1_
  - [x] 2.2 Implement hierarchy of truth in chapter prompts
    - Context files = baseline for company facts
    - Web search = external market context
    - _Requirements: 3.3, 3.4_
  - [x] 2.3 Write property test for rate limiting
    - **Property 2: Parallel Execution with Rate Limiting**
    - Verify max 3 concurrent tasks
    - **Validates: Requirements 4.1**
  - [x] 2.4 Write property test for shared context
    - **Property 3: Shared Context Access**
    - Verify all nodes use same File Search Store
    - **Validates: Requirements 3.2**

- [x] 3. Checkpoint - Verify architect and executor work
  - All 1744 tests pass

- [x] 4. Create Report Aggregator component
  - [x] 4.1 Create `src/primr/ai/report_aggregator.py`
    - Implement `ReportAggregator` class
    - `aggregate()` method to combine chapters
    - Generate table of contents
    - Smooth transitions between chapters
    - _Requirements: 1.3_
  - [x] 4.2 Write property test for aggregation
    - **Property 5: Aggregation Produces Single Document**
    - Verify single document with all chapters
    - **Validates: Requirements 1.3**

- [x] 5. Integrate into ResearchOrchestrator
  - [x] 5.1 Update `_run_complete_research()` in research_orchestrator.py
    - Phase 0: Existing structured pipeline
    - Phase 1: Call MasterArchitect
    - Phase 2: Call ResearchNodeExecutor
    - Phase 3: Call ReportAggregator
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 5.2 Implement File Search Store lifecycle
    - Create store before research
    - Upload context file
    - Delete store after completion
    - _Requirements: 3.1, 3.2_

- [x] 6. Checkpoint - Verify full pipeline works
  - All 1744 tests pass

- [x] 7. Implement error handling
  - [x] 7.1 Add graceful failure handling for chapter tasks
    - Log error, continue with other chapters
    - Note gap in final report
    - _Requirements: 4.2_
  - [x] 7.2 Write property test for graceful failure
    - **Property 6: Graceful Failure Handling**
    - Verify system continues when one chapter fails
    - **Validates: Requirements 4.2**

- [x] 8. Write property test for chapter completeness
  - [x] 8.1 Verify chapter output quality
    - **Property 4: Chapter Completeness**
    - Word count tracking implemented
    - **Validates: Requirements 2.3**

- [x] 9. Update document output pipeline
  - [x] 9.1 Ensure `_save_deep_research_output()` handles large documents
    - Existing `markdown_to_docx` and `DocumentBuilder` already support large documents
    - TOC generation via Word field codes
    - Page breaks between chapters
    - Headers/footers with page numbers
    - _Requirements: 1.4_

- [x] 10. Final Checkpoint
  - All 1744 tests pass
  - New components created:
    - `src/primr/ai/report_architect.py` - MasterArchitect class
    - `src/primr/ai/research_executor.py` - ResearchNodeExecutor class
    - `src/primr/ai/report_aggregator.py` - ReportAggregator class
  - Updated `src/primr/core/research_orchestrator.py` with 4-phase architecture
  - 58 new tests added for the new components
