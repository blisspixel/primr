# Implementation Plan

> **STATUS: COMPLETE** - All phases implemented. This spec is archived for reference.
> See ROADMAP.md for current development priorities.

- [x] 1. Create core data models and types
  - [x] 1.1 Create `core/report_models.py` with SourceType, ConfidenceLevel, SourceCitation, GatheredData dataclasses
  - [x] 1.2 Write property test for data model serialization
  - [x] 1.3 Create `core/report_models.py` additions for Insight, SectionContent, Report dataclasses

- [x] 2. Implement formatting utilities
  - [x] 2.1 Create `utils/formatting.py` with clean_content() function
  - [x] 2.2 Write property test for em-dash and emoji removal
  - [x] 2.3 Write property test for heading format
  - [x] 2.4 Write property test for number formatting
  - [x] 2.5 Write property test for no nested numbering

- [x] 3. Checkpoint - All tests pass

- [x] 4. Implement Insight Engine
  - [x] 4.1 Create `ai/insight_engine.py` with InsightEngine class
  - [x] 4.2 Write property test for insight count
  - [x] 4.3 Write property test for recommendation structure

- [x] 5. Implement Quality Grader enhancements
  - [x] 5.1 Create `ai/quality_grader.py` with enhanced QualityGrader class
  - [x] 5.2 Write property test for refinement trigger
  - [x] 5.3 Write property test for no filler content

- [x] 6. Checkpoint - All tests pass

- [x] 7. Implement Section Writer enhancements
  - [x] 7.1 Create `output/section_writer.py` with SectionWriter class
  - [x] 7.2 Write property test for executive summary completeness
  - [x] 7.3 Write property test for executive summary length

- [x] 8. Implement Report Assembler enhancements
  - [x] 8.1 Create `output/report_assembler.py` with ReportAssembler class
  - [x] 8.2 Write property test for sources appendix
  - [x] 8.3 Write property test for confidence marking

- [x] 9. Checkpoint - All tests pass

- [x] 10. Integrate into research pipeline
  - [x] 10.1 Update `core/research_agent.py` to use new components
  - [x] 10.2 Write property test for execution time
  - [x] 10.3 Write property test for timeout handling

- [x] 11. Update prompts for consulting quality
  - [x] 11.1 Update `prompts.json` with enhanced prompts

- [x] 12. Implement financial analysis enhancements
  - [x] 12.1 Add financial analysis to InsightEngine
  - [x] 12.2 Write property test for financial data inclusion

- [x] 13. Implement competitive analysis enhancements
  - [x] 13.1 Add competitive analysis to InsightEngine
  - [x] 13.2 Write property test for competitor count

- [x] 14. Final Checkpoint - All tests pass (1173 tests)

- [x] 15. Implement Citation Processor for clean numbered references
  - [x] 15.1 Create `output/citation_processor.py` with CitationProcessor class


    - Implement CitationStyle enum (NUMBERED, INLINE, SIDECAR)
    - Implement process_content() to transform `[text](url)` to `text [n]`
    - Implement get_reference_number() with URL deduplication
    - Implement generate_sources_appendix() for formatted output
    - _Requirements: 12.1, 12.2, 12.3_
  - [x] 15.2 Write property test for citation reference numbering


    - **Property 18: Citation Reference Numbering**
    - **Validates: Requirements 12.1**
  - [x] 15.3 Write property test for citation deduplication

    - **Property 19: Citation Deduplication**
    - **Validates: Requirements 12.2**

  - [x] 15.4 Write property test for citation round-trip consistency
    - **Property 20: Citation Round-Trip Consistency**
    - **Validates: Requirements 12.3**
  - [x] 15.5 Implement generate_sidecar_file() for separate sources file

    - Generate `{company}_sources.md` with all citations
    - _Requirements: 12.6_
  - [x] 15.6 Add `--citation-style` CLI flag to company_research.py


    - Support: numbered (default), inline, sidecar
    - Validate input and display error for invalid styles
    - _Requirements: 12.5_

- [x] 16. Integrate CitationProcessor into DocumentBuilder
  - [x] 16.1 Update DocumentBuilder to use CitationProcessor

    - Process all section content through CitationProcessor before rendering
    - Pass citations to _add_sources_appendix()
    - _Requirements: 12.1, 12.3_

  - [x] 16.2 Update _add_sources_appendix() to use numbered format
    - Display as `[1] Title - URL` format
    - Preserve existing functionality for explicit citations
    - _Requirements: 12.3_
  - [x] 16.3 Handle inline citation style (preserve URLs)
    - Skip CitationProcessor when style is INLINE
    - _Requirements: 12.5_

- [x] 17. Checkpoint - Ensure citation tests pass

  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. Implement AI Strategy Analyzer
  - [x] 18.1 Create `ai/ai_strategy.py` with AIStrategyAnalyzer class
    - Define CloudVendor enum (AZURE, AWS, GCP, AGNOSTIC)
    - Define AICategory enum (CONVERSATIONAL, AGENTIC, GEN_BI, AUTOMATION, PRODUCTIVITY, ML_WORKLOADS)
    - Define VENDOR_TECHNOLOGIES mapping
    - _Requirements: 13.3, 13.4, 13.5_
  - [x] 18.2 Implement analyze() method
    - Accept company research results and cloud vendor
    - Generate 5 AI opportunities tailored to company industry
    - _Requirements: 13.1, 13.2_
  - [x] 18.3 Write property test for AI opportunity count
    - **Property 21: AI Opportunity Count**
    - **Validates: Requirements 13.2**
  - [x] 18.4 Write property test for AI opportunity structure
    - **Property 22: AI Opportunity Structure**
    - **Validates: Requirements 13.7**
  - [x] 18.5 Write property test for vendor technology alignment
    - **Property 23: Vendor Technology Alignment**
    - **Validates: Requirements 13.3, 13.4, 13.5**
  - [x] 18.6 Implement _identify_industry_opportunities() method
    - Map industries to most relevant AI categories
    - _Requirements: 13.2_
  - [x] 18.7 Implement _generate_opportunity() method
    - Generate detailed opportunity with vendor-specific technologies
    - Include business impact and implementation complexity
    - _Requirements: 13.7_

- [x] 19. Add AI Strategy CLI integration
  - [x] 19.1 Add `--ai-strategy` flag to company_research.py
    - Trigger AI strategy analysis after company research
    - _Requirements: 13.1_
  - [x] 19.2 Add `--cloud-vendor` flag to company_research.py
    - Support: azure, aws, gcp (default: agnostic)
    - _Requirements: 13.3, 13.4, 13.5, 13.6_
  - [x] 19.3 Integrate AI strategy output into report
    - Add "AI Opportunities" chapter to report (saved as separate markdown file)
    - Format opportunities with all required fields
    - _Requirements: 13.7_

- [x] 20. Final Checkpoint - All Phase 9 tests pass
  - All 1415 tests pass

---

## Phase 10: Enhanced Hybrid Mode (Two-Step Sequential Pipeline)

Based on expert consultation (PhD consultants, UX guru), this phase implements a sequential two-step research pipeline that combines the ground-truth accuracy of structured scraping with the strategic depth of Deep Research.

**Architecture:**
- Step 1: Full Structured Pipeline → produces 18-section report with quality grading
- Step 2: Deep Research Agent → receives Step 1 output + optional user docs as context

- [x] 21. Implement Sequential Hybrid Mode


  - [x] 21.1 Update `ResearchMode` enum in `core/research_orchestrator.py`


    - Add `COMPLETE = "complete"` as new mode (outcome-oriented naming per UX feedback)
    - Keep existing `HYBRID` for backward compatibility (parallel mode)
    - _Requirements: Sequential execution, not parallel_
  - [x] 21.2 Implement `_run_complete_research()` method in ResearchOrchestrator


    - Step 1: Call `_run_structured_research()` and wait for completion
    - Save Step 1 output to temp file for File Search upload
    - Step 2: Call `_run_deep_research()` with Step 1 output as context
    - Merge results with Step 2 strategic layer on top of Step 1 ground truth
    - _Requirements: Sequential, not parallel execution_
  - [x] 21.3 Add progress callbacks for two-step transparency

    - "Step 1/2: Running structured pipeline (website scraping + Google search)..."
    - "Step 1/2: Generating 18-section report with quality grading..."
    - "Step 2/2: Running Deep Research for strategic analysis..."
    - "Step 2/2: Analyzing market position and competitive landscape..."
    - _Requirements: UX feedback - narrative progress updates_
  - [x] 21.4 Update CLI to support `--mode complete`


    - Add to argparse choices in `company_research.py`
    - Update help text to explain two-step process
    - _Requirements: User-facing mode selection_

- [x] 22. Implement File Search Context Passing

  - [x] 22.1 Create `_prepare_step1_context()` method

    - Convert Step 1 section_results dict to markdown document
    - Save to temp file with company name and timestamp
    - Return file path for upload
    - _Requirements: Step 1 output as Deep Research context_

  - [x] 22.2 Update `_run_deep_research()` to accept context_files parameter
    - Pass Step 1 output file to `context_files` parameter
    - Also accept optional user-provided documents (PDFs, POVs)
    - _Requirements: File Search integration_

  - [x] 22.3 Update Deep Research prompt for Step 2 context
    - Add instruction: "You have been provided initial research findings. Build upon this foundation..."
    - Emphasize: "Focus on strategic implications, market dynamics, and second-order insights"
    - Avoid: "Do not repeat basic facts already covered in the initial research"
    - _Requirements: Prompt engineering for context-aware research_

- [x] 23. Implement Narrative Gap Analysis
  - [x] 23.1 Create `ai/gap_analyzer.py` with NarrativeGapAnalyzer class
    - Gap analysis is now embedded in the strategic_layer prompt
    - _Requirements: Expert feedback - flag contradictions_
  - [x] 23.2 Add gap analysis to Step 2 Deep Research prompt
    - "Identify any gaps between company's stated positioning and market reality"
    - "Flag contradictions between website claims and external sources"
    - "Note discrepancies in financial claims vs. industry benchmarks"
    - _Requirements: Consulting-grade critical analysis_
  - [x] 23.3 Add "Narrative Gap Analysis" section to report output
    - New section in report structure
    - Format: Claim → Reality → Implication
    - _Requirements: Actionable insights for decision-makers_

- [x] 24. Implement Strategic Implications Layer
  - [x] 24.1 Add "Strategic Implications" synthesis to Deep Research prompt
    - "For each major finding, provide strategic implications"
    - "What does this mean for potential partners/investors/competitors?"
    - "What are the 3-5 most important takeaways for decision-makers?"
    - _Requirements: Expert feedback - synthesis layer_
  - [x] 24.2 Create `_merge_research_results()` method
    - Combine Step 1 (ground truth) with Step 2 (strategic layer)
    - Step 1 sections: company_overview, products_services, website data
    - Step 2 sections: competitive_landscape, strategic_assessment, gap_analysis
    - Resolve conflicts by preferring Step 1 for facts, Step 2 for analysis
    - _Requirements: Intelligent result merging_

- [x] 25. Update CLI Help and Documentation
  - [x] 25.1 Update `--mode` help text in company_research.py
    - `structured`: Website scraping + Google search, 18 sections (~20-25 min)
    - `deep-research`: Autonomous web research, 8 sections (~10-15 min)
    - `complete`: Two-step pipeline: structured → deep research (~30-40 min)
    - `hybrid`: Parallel execution of both (legacy, ~25 min)
    - _Requirements: Clear mode descriptions_
  - [x] 25.2 Update README.md with new mode documentation
    - Add `--mode complete` to usage examples
    - Explain two-step process and when to use it
    - _Requirements: User documentation_

- [x] 26. Checkpoint - Enhanced Hybrid Mode Tests
  - [x] 26.1 Add unit tests for sequential execution
    - Verify Step 1 completes before Step 2 starts
    - Verify Step 1 output is passed to Step 2
    - Added 12 new tests for COMPLETE mode (1382 total tests)
    - _Requirements: Test coverage_
  - [x] 26.2 Add integration test with Parts Town
    - Run `--mode complete` on Parts Town
    - Verify report contains both ground-truth and strategic sections
    - Manual test completed: 35 min, 23 sections, DOCX/PDF generated
    - _Requirements: Real-world validation_


---

## Phase 11: Cost Tracking and Usage Monitoring

Track actual API usage and costs during research runs to provide accurate cost reporting and improve estimates over time.

- [x] 27. Implement Usage Tracking Integration
  - [x] 27.1 Add token usage extraction to AIClient
    - Add `_extract_usage()` method to extract token counts from Gemini API responses
    - Track `total_input_tokens`, `total_output_tokens`, `call_count` on client
    - Add `get_usage_summary()` method for cost calculation
    - Add `reset_usage()` method for clearing counters
    - _Requirements: Accurate cost tracking_
  - [x] 27.2 Integrate usage tracking into research flow
    - Display actual cost in summary at end of `perform_research()`
    - Display actual cost in summary at end of `perform_deep_research()`
    - Save usage to history via `UsageTracker.record_usage()`
    - _Requirements: User visibility into actual costs_
  - [x] 27.3 Add tests for usage tracking
    - Test `_extract_usage()` with valid metadata
    - Test `_extract_usage()` returns None without metadata
    - Test `get_usage_summary()` cost calculation
    - Test `reset_usage()` clears counters
    - Test usage accumulates across calls
    - Added 7 new tests (1415 total tests)
    - _Requirements: Test coverage_

- [x] 28. Future: Usage-Based Estimate Refinement
  - [x] 28.1 Add `--show-usage` flag to display historical usage stats
  - [x] 28.2 Update cost estimates based on historical averages (when sample_size >= 3)
  - [x] 28.3 Add usage comparison (estimated vs actual) in summary output

---

## Phase 12: Defensive Programming and Robustness

Based on PhD-level code review, this phase implements defensive programming patterns to improve reliability, prevent resource leaks, and handle edge cases gracefully.

**Priority Order:**
1. CRITICAL: Silent failures that degrade output quality
2. CRITICAL: Thread safety and race conditions
3. HIGH: Resource leaks and memory management
4. HIGH: Data integrity (URL normalization, content handling)
5. MEDIUM: Cost optimization and API resilience

- [x] 29. Fix Critical Silent Failures


  - [x] 29.1 Add explicit error handling for Deep Research file upload failures


    - Update `_upload_context_files()` in `ai/deep_research.py` to raise AIError on failure
    - Update `_run_complete_research()` to catch and handle gracefully with user notification
    - Log warning when Step 2 runs without context due to upload failure
    - _Requirements: Prevent degraded reports without user awareness_
  - [x] 29.2 Add defensive content parsing in DocumentBuilder


    - Wrap `parser.parse_content()` in try/except in `_render_section_content()`
    - Fallback to plain paragraph rendering on parse failure
    - Wrap individual `_render_block()` calls to prevent single block failures from crashing
    - _Requirements: Graceful handling of malformed Deep Research output_

- [x] 30. Fix Thread Safety in Singletons


  - [x] 30.1 Add thread-safe singleton pattern to AIClient


    - Add `threading.Lock` to `ai/client.py`
    - Implement double-check locking in `get_client()`
    - _Requirements: Prevent race conditions in concurrent usage_
  - [x] 30.2 Add thread-safe singleton pattern to DeepResearchClient


    - Add `threading.Lock` to `ai/deep_research.py`
    - Implement double-check locking in `get_deep_research_client()`
    - _Requirements: Prevent race conditions_
  - [x] 30.3 Add thread-safe singleton pattern to ResearchOrchestrator


    - Add `threading.Lock` to `core/research_orchestrator.py`
    - Implement double-check locking in `get_orchestrator()`
    - _Requirements: Prevent race conditions_

- [x] 31. Fix Resource Leaks


  - [x] 31.1 Implement LRU cache for scrape cache


    - Create `LRUCache` class in `data/scrape.py` with configurable max_size (default 100)
    - Replace unbounded `_SCRAPE_CACHE` dict with LRU implementation
    - Add `get()` and `set()` methods with automatic eviction
    - _Requirements: Prevent memory exhaustion on long runs_
  - [x] 31.2 Add Playwright browser cleanup with atexit


    - Register `_cleanup_browser()` function with atexit in `data/scrape.py`
    - Ensure browser and playwright instances are properly closed
    - Add idle timeout tracking for browser reuse
    - _Requirements: Prevent browser process leaks_
  - [x] 31.3 Add context manager for temp files in orchestrator


    - Create `@contextmanager temp_context_file()` in `core/research_orchestrator.py`
    - Guarantee cleanup even on exceptions
    - Replace manual temp file handling in `_run_complete_research()`
    - _Requirements: Prevent temp file accumulation_

- [x] 32. Improve URL Normalization in CitationProcessor


  - [x] 32.1 Implement comprehensive URL normalization


    - Add `TRACKING_PARAMS` set for UTM and tracking parameter removal
    - Preserve meaningful query parameters while stripping tracking
    - Normalize scheme and netloc to lowercase
    - Remove fragments
    - _Requirements: Accurate citation deduplication_
  - [x] 32.2 Add tests for URL normalization edge cases


    - Test tracking parameter removal (utm_source, fbclid, gclid)
    - Test preservation of meaningful params (page, id, query)
    - Test case normalization
    - _Requirements: Verify deduplication accuracy_

- [x] 33. Add Circuit Breaker for External APIs


  - [x] 33.1 Create CircuitBreaker class in `utils/circuit_breaker.py`


    - Implement states: closed, open, half-open
    - Configure failure_threshold (default 3) and reset_timeout (default 60s)
    - Add `can_execute()`, `record_success()`, `record_failure()` methods
    - _Requirements: Prevent cascading failures_
  - [x] 33.2 Integrate circuit breaker with Google Search API


    - Add `_search_circuit` instance in `data/search_utils.py`
    - Check circuit before API calls, skip gracefully when open
    - Record success/failure after each call
    - _Requirements: Fail fast when API is down_
  - [x] 33.3 Add tests for circuit breaker behavior


    - Test state transitions (closed -> open -> half-open -> closed)
    - Test timeout-based reset
    - Test graceful degradation
    - _Requirements: Verify circuit breaker correctness_

- [x] 34. Enhance AI Strategy with Context Awareness


  - [x] 34.1 Implement `_extract_context_signals()` in AIStrategyAnalyzer


    - Extract business signals from company research context
    - Detect customer volume indicators (support, call center mentions)
    - Detect data-heavy indicators (analytics, warehouse, reporting)
    - Detect automation opportunities (manual processes, repetitive tasks)
    - _Requirements: Tailored AI recommendations_
  - [x] 34.2 Use context signals to prioritize AI categories


    - Adjust category ordering based on detected signals
    - Prioritize CONVERSATIONAL for high customer volume
    - Prioritize GEN_BI for data-heavy companies
    - Prioritize AUTOMATION for process-heavy companies
    - _Requirements: More relevant AI opportunities_

- [x] 35. Add Adaptive Polling for Deep Research


  - [x] 35.1 Implement `_get_poll_interval()` method in DeepResearchClient


    - Return 5s for first 60s (catch quick completions)
    - Return 10s for 60-300s (normal progress)
    - Return 20s for 300s+ (reduce API calls for long runs)
    - _Requirements: Optimize API usage_
  - [x] 35.2 Update polling loop to use adaptive intervals


    - Replace fixed `poll_interval` with dynamic calculation
    - Log interval changes at debug level
    - _Requirements: Reduce unnecessary API calls_

- [x] 36. Centralize Pricing Configuration


  - [x] 36.1 Add PricingConfig to settings


    - Create `PricingConfig` dataclass in `config/settings.py`
    - Add `gemini_input_per_million`, `gemini_output_per_million` fields
    - Add `last_updated` field for tracking staleness
    - _Requirements: Maintainable pricing_
  - [x] 36.2 Update cost calculations to use centralized pricing


    - Update `research_agent.py` to use `get_settings().pricing`
    - Update `cost_estimator.py` to use centralized pricing
    - Remove hardcoded pricing constants
    - _Requirements: Single source of truth for pricing_

- [x] 37. Add Content Deduplication Before LLM Calls


  - [x] 37.1 Create `deduplicate_content()` utility function


    - Add to `utils/formatting.py`
    - Remove duplicate lines/paragraphs (normalized comparison)
    - Preserve short lines (headers, separators)
    - _Requirements: Reduce token usage_
  - [x] 37.2 Integrate deduplication in summarize flow


    - Apply deduplication before sending scraped content to LLM
    - Log reduction percentage at debug level
    - _Requirements: Cost optimization_

- [x] 38. Checkpoint - Defensive Programming Tests



  - Ensure all tests pass, ask the user if questions arise.
  - Verify thread safety with concurrent test execution
  - Verify resource cleanup with memory profiling
