# Implementation Plan

## Summary

Fix `--mode full` to deliver 30+ page reports using the Accordion Method architecture:
- Stage 1: Website scraping + Google Search (baseline facts, Industry extraction)
- Stage 2: 1 Deep Research call (research dossier)
- Stage 3: N Gemini 3 Flash calls (section writing via `generate_content()`)

**Architecture:**
- Stage 1 extracts: Industry, Full Company Name, baseline facts
- Stage 2: Deep Research gathers external context as "Lead Researcher"
- Stage 3: Gemini 3 Flash writes each section with dossier + previous sections
- Fallback: If Deep Research fails, use Stage 1 context as dossier

**Models:**
- Deep Research: `deep-research-pro-preview-12-2025`
- Section Writing: `gemini-3-flash-preview`

**Report Structure:**
- Sections defined in YAML (`company_overview.yaml`) - 20 sections, extensible
- AI Strategy defined in YAML (`strategies/ai_strategy.yaml`) - 17 sections
- Clean header format: Title, Date (italics), Company Name, Website, Industry

---

- [x] 1. Create standalone test runner (for architecture validation)
  - [x] 1.1 Create AccordionTestRunner class in `src/primr/ai/accordion_test.py`
    - NOTE: This is a standalone test harness, NOT used in production
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 2. Validate architecture
  - [x] 2.1 Run standalone test with "Oceanography 2026-2030" topic
    - Result: 32.7 pages, 16,342 words, 11/11 sections, 10.9 minutes
    - Architecture: 1 Deep Research + 11 Gemini Flash = 12 API calls
    - _Requirements: 10.2, 10.3_

- [x] 3. Checkpoint - Architecture validated

- [x] 4. Externalize prompts to YAML
  - [x] 4.1 Add `accordion_method` section to `company_overview.yaml`
    - `research_dossier_prompt`: Phase 1 template
    - `section_writing_prompt`: Phase 2 template  
    - `position_guidance`: opening/middle/closing guidance
    - _Requirements: 8.1, 8.2_
  - [x] 4.2 Add `position` field to all 20 sections
  - [x] 4.3 Update `DeepResearchOrchestrator` to load prompts from YAML

- [x] 5. Integrate into main pipeline
  - [x] 5.1 Update `generate_comprehensive_report()` to use direct `generate_content()`
  - [x] 5.2 Wire up as default for `--mode full`

- [x] 6. Checkpoint - Integration complete

- [x] 7. Add resilient error handling
  - [x] 7.1 Implement retry for 500/503 errors (not just 429)
  - [x] 7.2 Add fallback: use Stage 1 context when Deep Research fails
  - [x] 7.3 Stop after consecutive failures threshold

- [x] 8. Pre-flight validation module
  - [x] 8.1 Create `src/primr/ai/preflight.py` module
  - [x] 8.2-8.9 All validation checks implemented and tested

- [x] 9. Clean report output format
  - [x] 9.1 Update `_assemble_report()` for modern header format
    - Title uses user input (e.g., "Bank of Hawaii")
    - Company Name uses full legal name from Stage 1 (e.g., "Bank of Hawaii Corporation")
    - Date in italics
    - Website and Industry from Stage 1
    - No table of contents (cleaner)
    - _Requirements: 1.2_
  - [x] 9.2 Extract Industry from Stage 1 context
    - `_extract_industry_from_context()` method
  - [x] 9.3 Extract full company name from Stage 1 context
    - `_extract_full_company_name()` method
  - [x] 9.4 Update INTERNALS.md to reference YAML configs
    - Sections are configurable, not hardcoded
    - Architecture is extensible for new strategy reports

- [x] 10. End-to-end validation
  - [x] 10.1 Run `--mode deep` standalone to validate Deep Research
    - `primr "Bank of Hawaii" https://www.boh.com --mode deep`
    - Result: 39 pages (19,687 words), 20 sections written
    - _Requirements: 7.1, 7.2_
  - [x] 10.2 Run `--mode scrape` to validate Stage 1
    - `primr "Bank of Hawaii" https://www.boh.com --mode scrape`
    - Verify Industry and Company Name extraction
    - _Requirements: 2.1_
  - [x] 10.3 Run full pipeline
    - `primr "Bank of Hawaii" https://www.boh.com`
    - Result: Comprehensive report with substantive content
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 11. Final Checkpoint
  - All tests pass (175 passed)
  - Prompts refined based on user feedback:
    - Reduced repetition across SWOT/Tensions/Patterns/Fragilities
    - Added numeric precision guidance (ranges for estimates)
    - Added "Where They're Likely to Say Yes" section
    - AI Strategy prompts generalized for any company type
    - README updated to reflect quality calibration
  - Update README if needed
