# Requirements Document

## Examples and Fixtures Policy

- Examples may use a fictional placeholder company (e.g., `Acme Corp`, `acme.example`).
- Tests must use fixture files (`tests/fixtures/sites.json`, `tests/fixtures/regression_urls.json`).
- Specs must not hardcode real-company test targets.

## Introduction

Primr currently has duplicate scraping implementations that cause inconsistent behavior. This spec consolidates all scraping to use ONE site-to-corpus workflow so that all modes use identical code paths.

The core principle: **Modes are stopping points in a single pipeline, NOT separate implementations.**

This spec distinguishes between two levels of scraping:
- **Page scrape** (primitive): A deterministic unit (URL → extracted content + diagnostics)
- **Site scrape / build_site_corpus** (workflow): A site-to-corpus workflow (base domain → corpus of URL → cleaned text)

## Glossary

### Conceptual Names (used in docs)

- **scrape_page**: Page scrape primitive. Input: URL. Output: extracted content + tier used + quality score + errors. Implemented by `ScrapeOrchestrator.scrape_url()`.
- **build_site_corpus**: Site-to-corpus workflow. Input: base domain, company name, max_pages. Output: corpus of cleaned text + raw scrapes + external links metadata. Implemented by `fetch_web_content()`.
- **extract_insights**: Corpus-to-facts compression. Input: corpus. Output: structured facts for downstream steps. Implemented by `summarize_scraped_content()`.

### Implementation Names (current code)

- **fetch_web_content**: Current implementation of `build_site_corpus` in `src/primr/data/scrape.py`
- **ScrapeOrchestrator.scrape_url**: Current implementation of `scrape_page` in `src/primr/data/scraping/orchestrator.py`
- **summarize_scraped_content**: Current implementation of `extract_insights` in `src/primr/ai/summarize.py`

### Other Terms

- **company_name**: Display label used for report headings and output folder naming; does not determine scrape scope (scope is determined by website URL host)
- **Pipeline**: The sequential flow: Build Corpus → Extract Insights → Deep Research → Write Report
- **In_Scope_Pages**: Pages on same domain or subdomains of the target website
- **External_Links**: Links to domains outside the target company (captured as metadata, not scraped in scrape mode)
- **Working_Folder**: Timestamped folder like `working/Company_Name/2026-01-09_0915/`
- **Raw_Scrapes_Folder**: Subfolder `_raw_scrapes/` containing individual page scrapes for quality validation
- **Boilerplate**: Repeated content across pages (nav, footer, CTAs) that should be filtered
- **Corpus**: The collection of cleaned, deduplicated text extracted from a website

## Requirements

### Requirement 1: Single Site-to-Corpus Workflow

**User Story:** As a developer, I want ONE site-to-corpus workflow used everywhere, so that fixes apply consistently and behavior is predictable.

#### Acceptance Criteria

1. THE build_site_corpus workflow (implemented as fetch_web_content) SHALL be the only function that performs site-level scraping
2. THE system MAY have multiple page-scrape implementations (tiers), but MUST have only one site-scrape implementation
3. WHEN perform_scrape_only is called, THE System SHALL delegate to build_site_corpus
4. WHEN run_research is called, THE System SHALL delegate to build_site_corpus
5. THE perform_scrape_only function SHALL NOT contain its own discovery loop
6. THE perform_scrape_only function SHALL NOT contain its own scraping loop
7. THE perform_scrape_only function SHALL NOT duplicate raw scrape saving logic
8. Discovery, selection, scraping loop, raw scrape saving, boilerplate filtering, and external link recording SHALL be implemented as a single workflow invoked by all modes
9. No other top-level function SHALL re-implement any of these steps

### Requirement 2: Scope Policy

**User Story:** As a user, I want clear rules for what pages get scraped, so that I get consistent coverage across any company.

#### Acceptance Criteria

1. THE System SHALL scrape pages on the same domain as the target website
2. THE System SHALL scrape pages on subdomains of the target website (e.g., docs.company.com, blog.company.com)
3. WHEN external links are discovered, THE System SHALL record them in `_external_links.txt` but NOT scrape them in scrape mode
4. Scope SHALL be enforced during discovery, before selection
5. External URLs SHALL never be allowed into selected_urls in scrape mode
6. WHEN mode is "full", THE System MAY scrape external sources during deep research validation phase
7. THE System SHALL attempt to discover these page types if they exist: homepage, about/company, products/solutions, pricing, docs/help, security/trust/compliance

### Requirement 3: Scrape Mode Outputs

**User Story:** As a user, I want to know exactly what scrape mode produces, so that I can validate and use the outputs.

#### Acceptance Criteria

1. WHEN scrape mode completes, THE System SHALL produce these outputs in the working folder:
   - `_raw_scrapes/` folder with individual page scrapes
   - `_external_links.txt` with discovered external links
   - `scraped_content.txt` with combined corpus
   - `insights.txt` with LLM-extracted insights
2. WHEN a raw scrape is saved, THE System SHALL include URL, Tier, Title, Quality score, Metrics, and content
3. THE raw scrape file format SHALL be identical regardless of which mode triggered the scrape

### Requirement 4: Mode Controls Pipeline Stopping Point

**User Story:** As a user, I want modes to control how far the pipeline runs, not which code path executes.

#### Acceptance Criteria

1. WHEN mode is "scrape" (CLI: `--mode scrape`, prose: "Corpus+Insights mode"), THE System SHALL run: build_site_corpus → extract_insights → save outputs → stop
2. WHEN mode is "deep", THE System SHALL run: Deep Research only (no scraping)
3. WHEN mode is "full", THE System SHALL run: build_site_corpus → extract_insights → deep_research → write_report
4. THE corpus-building phase in "scrape" mode SHALL produce identical output to the corpus-building phase in "full" mode
5. Documentation SHALL always describe `--mode scrape` as "Corpus+Insights mode" or "Build Site Corpus + Extract Insights (multi-page)"
6. Documentation examples SHALL use a single fictional placeholder company consistently and SHALL NOT repeat real company names/domains

### Requirement 5: Content Quality and Escalation

**User Story:** As a user, I want the same content extraction quality regardless of mode, so that scrape mode output matches what full mode would have scraped.

#### Acceptance Criteria

1. WHEN extracting content, THE System SHALL use structured content extraction with DOM pruning
2. WHEN extracting content, THE System SHALL apply boilerplate filtering across pages
3. WHEN content quality score is below 0.3 (configurable), THE System SHALL escalate to higher tiers
4. WHEN extracted character count is below 200 (configurable), THE System SHALL escalate to higher tiers
5. WHEN link density exceeds 0.5 (configurable), THE System SHALL escalate to higher tiers or flag as low quality
6. WHEN boilerplate ratio exceeds 0.6 (configurable), THE System SHALL apply cross-page filtering
7. WHEN repeated lines exceed 30% of content (configurable), THE System SHALL deduplicate
8. Quality thresholds SHALL be configurable; default values are specified in design document

### Requirement 6: Boilerplate Filtering

**User Story:** As a user, I want boilerplate content (nav, footer, CTAs) removed, so that extracted content is meaningful.

#### Acceptance Criteria

1. THE System SHALL remove within-page repeated lines
2. THE System SHALL fingerprint lines across pages and remove those appearing in >30% of pages
3. THE System SHALL prune high link-density regions before extraction
4. THE System SHALL NOT include "Request a demo", cookie consent, or footer fragments in final output
5. THE System SHALL preserve meaningful repeated content (brand taglines, product names)
6. THE System SHALL log boilerplate_ratio for each page

### Requirement 7: Corpus Coverage

**User Story:** As a user, I want comprehensive coverage of a company's website, so that I get a complete picture.

#### Acceptance Criteria

1. WHEN discovery completes, THE System SHALL have attempted to find: homepage, about, products, pricing, docs, security pages
2. THE System SHALL discover at least 10 pages for typical company websites (blocked/single-page/tiny sites may not meet this)
3. THE System SHALL extract at least 5000 characters total for typical company websites (blocked/single-page/tiny sites may not meet this)
4. WHEN fewer than 10 pages are discovered, THE System SHALL try sitemap and common URL guessing as fallbacks
5. THE System SHALL use deterministic heuristic selection as baseline; LLM selection is an optional refinement that MAY be disabled
6. Deterministic URL selection MUST work without LLM availability
7. Coverage thresholds are defaults for typical sites; exceptions for blocked/minimal sites are expected

### Requirement 8: Progress Display

**User Story:** As a user, I want to see scraping progress, so that I know the system is working during long runs.

#### Acceptance Criteria

1. WHEN scraping pages, THE System SHALL display progress (e.g., "[3/50] /about-us")
2. WHEN a page is scraped, THE System SHALL show the tier used
3. WHEN scraping completes, THE System SHALL show total pages and characters scraped
