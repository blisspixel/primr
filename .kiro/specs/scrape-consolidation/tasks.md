# Implementation Plan: Scrape Consolidation

## Overview

Consolidate all scraping to use ONE site-to-corpus workflow (`build_site_corpus`, implemented as `fetch_web_content()`). Refactor `perform_scrape_only()` to delegate instead of duplicate. Add scope policy, external link recording, and boilerplate filtering.

## Tasks

- [x] 0. Update documentation policies
  - [x] 0.1 Replace "no company names" rule in design.md with Examples Policy
    - Change to: docs MAY use fictional placeholder, MUST NOT repeat real companies, tests use fixtures
    - _Requirements: 4.6_

  - [x] 0.2 Replace "no company names" rule in requirements.md with Examples Policy
    - Same policy as design.md
    - _Requirements: 4.6_

  - [x] 0.3 Make README examples use only fictional placeholder
    - Remove all real company examples (Tesla, etc.)
    - Use one fictional placeholder (Acme Corp, acme.example) consistently
    - _Requirements: 4.6_

- [x] 1. Update naming in docs to reflect scrape_page vs build_site_corpus
  - [x] 1.1 Update ARCHITECTURE.md terminology
    - Add conceptual names: `scrape_page` (primitive), `build_site_corpus` (workflow), `extract_insights` (compression)
    - Map to implementation names: `ScrapeOrchestrator.scrape_url()`, `fetch_web_content()`, `summarize_scraped_content()`
    - Clarify: "one site-scrape workflow, many page-scrape tiers"
    - Add naming rules section
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Update README.md pipeline description
    - Describe `--mode scrape` as "Corpus+Insights mode" or "Build Site Corpus + Extract Insights (multi-page)"
    - Never call it "Website only" without adding "(multi-page corpus)"
    - Add exact artifact list: `_raw_scrapes/`, `scraped_content.txt`, `insights.txt`, `_external_links.txt`
    - Update pipeline diagram to show outputs
    - _Requirements: 4.1, 4.5_

  - [x] 1.3 Add extract_insights naming mapping
    - Document that `summarize_scraped_content` is the implementation of `extract_insights`
    - Add to glossary in design and requirements
    - _Requirements: 4.1_

- [x] 2. Refactor perform_scrape_only to delegate to build_site_corpus
  - [x] 2.1 Remove discovery loop from perform_scrape_only
    - Delete homepage scanning code (scrape_with_playwright, extract_links_from_html)
    - Delete section expansion code
    - Delete sitemap/guessing fallback code
    - Delete link scoring and LLM selection code
    - _Requirements: 1.5_

  - [x] 2.2 Remove scraping loop from perform_scrape_only
    - Delete the `for page_url in pages_to_scrape` loop
    - Delete orchestrator.scrape_url calls
    - Delete tier_stats tracking
    - _Requirements: 1.6_

  - [x] 2.3 Remove raw scrape saving from perform_scrape_only
    - Delete raw_folder creation
    - Delete file writing loop for raw scrapes
    - _Requirements: 1.7_

  - [x] 2.4 Add build_site_corpus call with working_folder
    - Call fetch_web_content with working_folder parameter
    - Pass company_name, website, max_pages=50
    - _Requirements: 1.3_

  - [x] 2.5 Keep extract_insights call (summarize_scraped_content)
    - Ensure it uses the corpus from build_site_corpus
    - _Requirements: 4.1_

  - [x] 2.6 Update progress display
    - Use console.phase_banner for phases
    - Show page count from build_site_corpus result
    - _Requirements: 8.1, 8.3_

- [x] 3. Add scope policy to build_site_corpus (fetch_web_content)
  - [x] 3.1 Add is_in_scope helper function
    - Check if URL is same domain or subdomain of target
    - Return True for in-scope, False for external
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Enforce scope during discovery (before selection)
    - Separate in-scope links (eligible for selection) from external links (metadata only)
    - External URLs NEVER allowed into selected_urls
    - _Requirements: 2.4, 2.5_

  - [x] 3.3 Save external links to _external_links.txt
    - Create file in working_folder with discovered external links
    - Group by type (press, social, other)
    - Include note that these are NOT scraped in scrape mode
    - _Requirements: 2.3, 3.1_

- [x] 4. Implement/validate boilerplate filtering
  - [x] 4.1 Implement within-page deduplication
    - Remove repeated lines within a single page
    - _Requirements: 6.1_

  - [x] 4.2 Implement cross-page line fingerprinting
    - Normalize lines (lowercase, strip punctuation, collapse whitespace)
    - Count frequency across pages
    - Remove lines appearing in >30% of pages
    - _Requirements: 6.2_

  - [x] 4.3 Log boilerplate_ratio for each page
    - Add to raw scrape file metrics
    - _Requirements: 6.6_

  - [x] 4.4 Add unit test for boilerplate removal
    - Test that "Request a demo", cookie consent, footer fragments are removed
    - Test that brand taglines are preserved
    - _Requirements: 6.4, 6.5_

- [x] 5. Verify raw scrape format includes all required fields
  - [x] 5.1 Verify URL, Tier, Title are written
    - Check existing code in fetch_web_content
    - _Requirements: 3.2_

  - [x] 5.2 Verify Quality score and Metrics are written
    - Ensure quality.score, char_count, heading_count, paragraph_count, link_density, boilerplate_ratio included
    - _Requirements: 3.2_

- [x] 6. Create test fixtures
  - [x] 6.1 Create tests/fixtures/sites.json
    - Define 3 representative site types: docs_heavy, js_heavy_spa, blog_driven
    - Include assertions for each: min_pages, min_chars, max_boilerplate_ratio
    - URLs configured at runtime (not hardcoded in spec)
    - _Requirements: 7.1, 7.2_

  - [x] 6.2 Create tests/fixtures/regression_urls.json
    - Add regression case for structured_content_pruning fix
    - Include assertions: min_chars, min_quality
    - URLs configured at runtime (not hardcoded in spec)
    - _Requirements: 5.1, 5.2_

- [x] 7. Multi-site corpus testing (run BEFORE regression)
  - [x] 7.1 Run multi-site sanity suite from fixtures
    - Load site configs from tests/fixtures/sites.json
    - For each site type, assert thresholds from fixture config
    - _Requirements: 7.2, 7.3_

- [x] 8. Checkpoint - Test scrape mode on fixture corpus
  - Run scrape mode on all site types from fixtures
  - Verify _raw_scrapes/ folder is populated with quality content
  - Verify _external_links.txt is created
  - Verify insights.txt is generated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Regression test from fixtures
  - [x] 9.1 Run regression cases from tests/fixtures/regression_urls.json
    - For each case, verify assertions pass
    - Verify content is actual text (not garbage/JS artifacts)
    - _Requirements: 5.1, 5.2_

- [x] 10. Remove perform_scrape_test function
  - [x] 10.1 Delete perform_scrape_test function
    - This is another duplicate that should not exist
    - _Requirements: 1.1_

- [x] 11. Add mode equivalence diff automation
  - [x] 11.1 Create diff helper script/function
    - `diff_scrape_outputs(folder_scrape, folder_full)`
    - Diffs _raw_scrapes/, _external_links.txt, scraped_content.txt
    - _Requirements: 4.4_

  - [x] 11.2 Add mode equivalence test
    - Run scrape mode and full mode on same fixture site
    - Use diff helper to verify identical corpus outputs
    - _Requirements: 4.4_

- [x] 12. Add static analysis to prevent future duplicates
  - [x] 12.1 Add static check for duplicate site-scrape patterns
    - Scan repo for "discover links + scrape loop" patterns
    - Assert only build_site_corpus (fetch_web_content) contains these patterns
    - _Requirements: 1.8, 1.9_

- [x] 13. Final checkpoint
  - Run full mode and scrape mode on same fixture site
  - Use diff helper to verify identical outputs
  - Run static analysis to verify no duplicate patterns
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- The key insight: we're DELETING code, not adding it
- perform_scrape_only should shrink from ~300 lines to ~50 lines
- Naming matters: `scrape_page` (primitive) vs `build_site_corpus` (workflow)
- Scope policy ensures consistent behavior across any company
- External links are captured for later pipeline stages (full mode)
- Tests use fixture files, not hardcoded company names
- Do not paste specific real target URLs into tasks; use fixture mechanisms
- Mode equivalence diff tool makes the most important property easy to validate
