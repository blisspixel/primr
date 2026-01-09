# Requirements Document

## Introduction

This specification defines the requirements for refactoring Primr's web scraping subsystem into a modular, resilient architecture. The current `scrape.py` (2100+ lines) is a monolithic file that has grown organically. This refactor will decompose it into focused modules with the goal of **maximizing coverage**, **minimizing silent failure**, and providing **full traceability** for debugging.

The scraping subsystem is critical to Primr's Scrape Mode and Full Mode, which gather company intelligence from corporate websites. Sites increasingly use sophisticated WAF protection (Cloudflare, Akamai, WireWall, DataDome) that requires multi-layered bypass strategies.

### Alignment with Primr's Purpose

Primr is for understanding companies. The scraping layer should:
- Maximize data extraction from accessible sites
- Fail gracefully on hard-blocked sites (don't escalate infinitely)
- Preserve discovered links for Deep Mode fallback when scraping fails
- Provide full traceability for debugging and QA

## Glossary

- **WAF**: Web Application Firewall - security systems that detect and block automated access
- **Soft_Block**: A 200 OK response that contains a block page instead of real content
- **TLS_Fingerprint**: The unique signature of a client's TLS handshake, used by WAFs to identify bots
- **Driverless_Browser**: Browser automation via CDP (Chrome DevTools Protocol) without WebDriver
- **Circuit_Breaker**: A pattern where the system detects failures and switches strategies
- **Scrape_Tier**: A scraping method with specific capabilities (e.g., requests, curl_cffi, DrissionPage)
- **Link_Discovery**: The process of finding all valuable URLs on a target site
- **Content_Extraction**: The process of extracting clean text from HTML/PDF content
- **Browser_Profile**: A consistent set of fingerprint attributes (User-Agent, screen size, WebGL, etc.)

## Requirements

### Requirement 1: Modular Architecture

**User Story:** As a developer, I want the scraping code organized into focused modules, so that I can understand, test, and maintain each component independently.

#### Acceptance Criteria

1. THE Scraping_Subsystem SHALL be decomposed into separate modules for: HTTP clients, browser automation, content extraction, link discovery, caching, detection, profiles, trace logging, and orchestration
2. WHEN a module is imported, THE Module SHALL have no side effects (no global state initialization)
3. THE Orchestrator_Module SHALL coordinate between other modules without containing implementation details
4. WHEN adding a new scraping tier, THE Developer SHALL only need to modify the tiers module and register it with the orchestrator
5. THE Module_Structure SHALL follow this organization:
   - `scraping/http_clients.py` - requests, httpx, curl_cffi implementations
   - `scraping/browsers.py` - Playwright, DrissionPage, BrowserSession abstraction
   - `scraping/content.py` - text extraction from raw bytes, PDF handling
   - `scraping/discovery.py` - link discovery, sitemap, URL guessing
   - `scraping/detection.py` - WAF detection, soft block detection, challenge detection
   - `scraping/profiles.py` - HTTP header profiles, browser context profiles, stealth patches (separated)
   - `scraping/cache.py` - LRU cache, disk cache with URL normalization
   - `scraping/trace.py` - scrape trace artifact logging
   - `scraping/config.py` - tier configuration, rate limits, constants
   - `scraping/orchestrator.py` - tiered scraping coordination
6. ALL tier functions SHALL return a standardized ScrapeResult object (not tuples)

### Requirement 2: Tiered Scraping with Circuit Breaker

**User Story:** As a researcher, I want the scraper to automatically escalate through increasingly sophisticated methods when simpler ones fail, so that I get content even from protected sites.

#### Acceptance Criteria

1. THE Scrape_Orchestrator SHALL attempt tiers in order of increasing resource cost: HTTP clients → Driverless browsers → Full browsers → Vision AI (opt-in)
2. WHEN a tier fails with a soft block, THE Orchestrator SHALL wait a random delay (1-3 seconds) before trying the next tier
3. WHEN all tiers fail for a URL, THE Orchestrator SHALL log the failure with the last error and return a ScrapeResult with success=False
4. THE Tier_Configuration SHALL be externalized so new tiers can be added without modifying orchestrator logic
5. WHEN a tier succeeds, THE Orchestrator SHALL cache the raw content and return immediately (no unnecessary tier attempts)
6. IF a tier returns a soft block, THEN THE Orchestrator SHALL treat it as a failure and continue to the next tier
7. THE Orchestrator SHALL maintain per-host circuit breaker state: if a host repeatedly fails at tier X, skip lower tiers for future pages on that host
8. THE Vision_Tier SHALL only be attempted when explicitly enabled via flag OR for pages marked as "important" (leadership, products, investors)

### Requirement 3: Driverless Browser Integration

**User Story:** As a researcher, I want the scraper to use driverless browser automation (DrissionPage) to bypass WAFs that detect WebDriver, so that I can access sites with aggressive bot protection.

#### Acceptance Criteria

1. THE DrissionPage_Tier SHALL use CDP (Chrome DevTools Protocol) directly without WebDriver
2. WHEN navigating to a page, THE DrissionPage_Tier SHALL wait for Cloudflare/WAF challenges to complete (up to 20 seconds)
3. THE DrissionPage_Tier SHALL dismiss cookie consent banners automatically
4. THE DrissionPage_Tier SHALL scroll the page to trigger lazy-loaded content
5. WHEN the page title contains "Just a moment" or "Checking your browser", THE DrissionPage_Tier SHALL wait and retry
6. THE DrissionPage_Stealth_Tier SHALL use maximum anti-detection arguments and human-like scrolling patterns

### Requirement 4: TLS Fingerprint Impersonation

**User Story:** As a researcher, I want HTTP requests to have browser-like TLS fingerprints, so that WAFs cannot detect Python's OpenSSL signature.

#### Acceptance Criteria

1. THE Curl_Cffi_Tier SHALL impersonate real browser TLS signatures (Chrome, Safari, Edge)
2. WHEN making a request, THE Curl_Cffi_Tier SHALL randomly select from available browser impersonation targets
3. THE HTTP_Headers SHALL be consistent with the impersonated browser (Sec-Ch-Ua, etc.)
4. IF curl_cffi is not installed, THEN THE Tier SHALL return a clear error and be skipped

### Requirement 5: Comprehensive Soft Block Detection

**User Story:** As a researcher, I want the scraper to detect when a site returns fake content (soft blocks), so that I don't get useless data.

#### Acceptance Criteria

1. THE Soft_Block_Detector SHALL identify known WAF signatures: Cloudflare, Akamai, WireWall, DataDome, PerimeterX, Kasada, Imperva
2. THE Soft_Block_Detector SHALL flag HTML content shorter than 5KB as potentially blocked (configurable threshold)
3. THE Soft_Block_Detector SHALL detect JavaScript-only pages that haven't rendered
4. THE Soft_Block_Detector SHALL detect suspiciously repetitive content (less than 30% unique lines)
5. WHEN content contains "access denied", "forbidden", "captcha", or similar indicators, THE Detector SHALL flag it as blocked
6. THE Soft_Block_Detector SHALL avoid false positives on legitimate content (e.g., "blocked" in a news article)
7. THE Soft_Block_Detector SHALL distinguish between challenge pages (solvable) and hard blocks (not solvable)
8. THE Soft_Block_Detector SHALL detect consent walls blocking content
9. THE Soft_Block_Detector SHALL check response metadata: HTTP status, content-type header, final URL after redirects
10. THE Detection_Result SHALL be attached to ScrapeResult for consistent logging

### Requirement 6: Resilient Link Discovery

**User Story:** As a researcher, I want the scraper to discover all valuable pages on a site using multiple strategies, so that even if one method is blocked, others succeed.

#### Acceptance Criteria

1. THE Link_Discovery_System SHALL try multiple strategies in order: browser scraping → sitemap.xml → common URL guessing
2. WHEN sitemap.xml exists, THE System SHALL fetch ALL links with safety guardrails:
   - Stream parse XML to avoid memory issues
   - Enforce max sitemap depth (default 3) for sitemap indexes
   - Stop after configurable max URLs (default 100,000) with explicit log
   - Handle gzipped sitemaps
   - Treat sitemaps > 50MB as special mode
3. THE Common_URL_Guesser SHALL generate URLs for 60+ standard business page patterns
4. THE URL_Verifier SHALL check guessed URLs with HEAD requests to confirm they exist
5. WHEN a site blocks browser scraping, THE System SHALL fall back to sitemap or URL guessing
6. THE LLM_Selector SHALL review ALL discovered links and select the most valuable for consultant prep
7. THE Link_Discovery_System SHALL combine links from all successful strategies before LLM selection
8. THE Link_Discovery_System SHALL apply heuristic scoring (URL pattern + anchor text + sitemap priority) before LLM selection to improve quality and reduce cost
9. NOTE: Discovery may return >500 links; orchestrator will only scrape top N based on LLM selection + per_run_max_pages cap (default 500). This is intentional - discovery is comprehensive, scraping is bounded.

### Requirement 7: Browser Fingerprint Consistency

**User Story:** As a researcher, I want browser fingerprints to be internally consistent, so that WAFs cannot detect mismatches between User-Agent and other properties.

#### Acceptance Criteria

1. THE Profile_System SHALL separate concerns into three types:
   - HTTP header profiles (User-Agent, Sec-Ch-Ua, Accept-Language)
   - Browser context profiles (viewport, locale, timezone)
   - Stealth patches (minimal JS injections, used sparingly)
2. WHEN a profile claims to be Chrome on Windows, THE HTTP_Headers SHALL have Windows-consistent Sec-Ch-Ua-Platform
3. THE Profile_Selector SHALL randomly choose from multiple realistic profiles to avoid fingerprint clustering
4. THE Stealth_Patches SHALL be minimal to avoid detection of tampering (many properties are read-only)
5. THE HTTP_Header_Profile SHALL match the curl_cffi impersonation target when used together

### Requirement 8: Content Extraction

**User Story:** As a researcher, I want clean text extracted from web pages and PDFs, so that I get useful content without HTML noise.

#### Acceptance Criteria

1. THE Text_Extractor SHALL operate on raw bytes from tiers (not pre-parsed content)
2. THE Text_Extractor SHALL support two modes: conservative (keep more) and aggressive (strip more)
3. THE Text_Extractor SHALL remove script, style, noscript, meta, and optionally header, footer, form, aside, nav, iframe, svg, and canvas elements
4. THE Text_Extractor SHALL deduplicate consecutive identical lines
5. THE PDF_Extractor SHALL extract text from PDF bytes using PyMuPDF
6. WHEN extracting text, THE Extractor SHALL preserve paragraph structure with newlines
7. THE Raw_Content and Extracted_Text SHALL be cached separately to allow re-parsing without re-scraping

### Requirement 9: Caching System

**User Story:** As a researcher, I want scraped content cached to avoid redundant requests, so that repeated runs are fast and don't trigger rate limits.

#### Acceptance Criteria

1. THE Memory_Cache SHALL use LRU eviction with configurable max size (default 100 entries)
2. THE Disk_Cache SHALL persist content with TTL (default 24 hours)
3. WHEN content is requested, THE Cache SHALL check memory first, then disk
4. THE Cache_Key SHALL be derived from the normalized URL:
   - Strip trailing slash
   - Normalize scheme (prefer https)
   - Remove fragments (#section)
   - Sort query params alphabetically
   - Optionally ignore utm_* params
5. WHEN content is scraped successfully, THE Orchestrator SHALL cache raw content immediately
6. THE Cache SHALL store raw content and extracted text separately to allow re-parsing without re-scraping

### Requirement 10: Graceful Degradation

**User Story:** As a researcher, I want the scraper to continue working even when some components fail, so that I get partial results rather than nothing.

#### Acceptance Criteria

1. IF DrissionPage is not installed, THEN THE Orchestrator SHALL skip DrissionPage tiers and continue with others
2. IF curl_cffi is not installed, THEN THE Orchestrator SHALL skip curl_cffi tier and continue with others
3. IF Playwright browsers are not installed, THEN THE Orchestrator SHALL skip Playwright tiers and continue with others
4. WHEN a tier throws an unexpected exception, THE Orchestrator SHALL log it and continue to the next tier
5. THE Orchestrator SHALL return partial results (some URLs scraped) rather than failing entirely

### Requirement 11: Test Infrastructure

**User Story:** As a developer, I want comprehensive tests that don't repeatedly hit the same live sites, so that tests are reliable and don't get the test environment blocked.

#### Acceptance Criteria

1. THE Unit_Tests SHALL use mocked HTTP responses, not live requests
2. THE Integration_Tests SHALL use a diverse set of test URLs (not just one site)
3. THE Test_Suite SHALL include tests for each scraping tier in isolation
4. THE Test_Suite SHALL include tests for soft block detection with known WAF signatures
5. THE Test_Suite SHALL include tests for link discovery strategies
6. THE Test_Suite SHALL include tests for the circuit breaker pattern
7. WHEN testing browser automation, THE Tests SHALL use mock page content or local HTML files

### Requirement 12: Observability and Logging

**User Story:** As a developer, I want detailed logs of scraping attempts, so that I can diagnose failures and understand which tiers succeed.

#### Acceptance Criteria

1. THE Scraping_Subsystem SHALL log each tier attempt with URL, tier name, and result (success/failure/error)
2. WHEN a soft block is detected, THE Log SHALL include the detection reason
3. THE Failure_Log SHALL be written to disk for post-mortem analysis
4. THE Console_Output SHALL show progress without overwhelming detail (unless VERBOSE mode)
5. THE Scraping_Subsystem SHALL persist a scrape trace artifact per run as JSON Lines:
   - URL, timestamp, tier attempts sequence
   - Success tier, blocked flag, blocked reason
   - HTTP status, content type, final URL
   - Extracted text length, total elapsed time
6. THE Trace_Artifact SHALL be saved to `logs/scrape_traces/{company}_{timestamp}.jsonl`

### Requirement 13: Rate Limiting and Politeness

**User Story:** As a researcher, I want the scraper to respect rate limits and behave politely, so that I don't trigger WAFs or get blocked.

#### Acceptance Criteria

1. THE Orchestrator SHALL enforce per-host concurrency limits (default 2 concurrent requests per host)
2. THE Orchestrator SHALL enforce per-host request rate limits (default 20 requests per minute per host)
3. THE Orchestrator SHALL enforce per-run max pages (default 500 pages per scrape run)
4. WHEN receiving a 429 response, THE Orchestrator SHALL apply exponential backoff (base 2x multiplier)
5. THE Orchestrator SHALL add random jitter to delays (base 1.5s + random 0-3.5s) to avoid detection patterns

### Requirement 14: Content Validity

**User Story:** As a researcher, I want the scraper to detect thin or duplicate content, so that reports aren't populated with useless pages.

#### Acceptance Criteria

1. THE Content_Validator SHALL detect pages with insufficient main content density (nav-only pages)
2. THE Content_Validator SHALL detect duplicate templates across many URLs (common in CMS)
3. THE Content_Validator SHALL require some text beyond boilerplate for a page to be considered valid
4. WHEN content fails validation, THE Orchestrator SHALL log the reason and optionally skip the page
5. THE Content_Validity_Check SHALL NOT trigger tier escalation (unlike soft blocks)
6. THE Content_Validity_Check SHALL run after extraction, not during tier attempts

### Requirement 15: Raw Artifact Persistence

**User Story:** As a developer, I want raw HTML/PDF bytes saved for successful pages, so that I can debug parsing issues without re-scraping.

#### Acceptance Criteria

1. WHEN enabled (default true), THE Scraper SHALL save raw HTML/PDF bytes for successful pages
2. THE Raw_Artifacts SHALL be saved to working folder, keyed by normalized URL hash
3. THE Raw_Artifact_Persistence SHALL be configurable (can be disabled for disk space)
4. THE Raw_Artifacts SHALL be separate from the cache (cache has TTL, artifacts are permanent per run)

### Requirement 16: Robots.txt Support

**User Story:** As a researcher, I want the option to respect robots.txt, so that I can maintain compliance posture when needed.

#### Acceptance Criteria

1. THE Scraper SHALL support `--respect-robots` mode (default false)
2. WHEN respect-robots is enabled, THE Scraper SHALL fetch and parse robots.txt before scraping
3. WHEN a URL is disallowed by robots.txt, THE Scraper SHALL skip it and log the reason
4. THE Scraper SHALL log whether robots.txt was respected in the trace artifact

### Requirement 17: Hard Block Handling

**User Story:** As a researcher, I want hard-blocked sites to fail gracefully without infinite escalation, so that scraping doesn't become an arms race.

#### Acceptance Criteria

1. WHEN a site returns a hard block (403, geo-block) on all tiers, THE Orchestrator SHALL mark the host as blocked
2. THE Orchestrator SHALL NOT retry hard-blocked hosts during the same run
3. WHEN a host is hard-blocked, THE Orchestrator SHALL preserve discovered links for Deep Mode fallback
4. THE Trace_Artifact SHALL record hard-blocked hosts with the failure reason

### Requirement 18: Content-Based Success Criteria

**User Story:** As a researcher, I want tiers to only report success when content is actually valid, so that I don't get silent failures.

#### Acceptance Criteria

1. A Tier SHALL NOT report success unless a "success signal" passes:
   - Content length over threshold (5KB for HTML), OR
   - Key selectors exist (title, h1, main content area), OR
   - Extracted text density > threshold (30%)
2. THE Success_Signal_Check SHALL run before caching to prevent caching bad content
3. WHEN a success signal fails, THE Tier SHALL return success=False with appropriate error_type

### Requirement 19: Trace Completeness

**User Story:** As a developer, I want every URL to have exactly one trace entry with all outcomes logged, so that debugging is reliable.

#### Acceptance Criteria

1. EVERY URL scraped SHALL yield exactly one trace entry
2. ALL tier attempts and outcomes SHALL be logged in the trace entry
3. THE Trace_Entry SHALL include detection outputs (BlockType enum, reason)
4. THE Trace_Entry SHALL include validation results (density, duplicate flag)
5. THE Trace_Schema SHALL be versioned and stable for analytics

### Requirement 20: Ethical Scope Constraints

**User Story:** As a researcher, I want the scraper to have clear ethical boundaries, so that I don't accidentally violate site policies.

#### Acceptance Criteria

1. THE Scraper SHALL NOT attempt to bypass paywalls
2. THE Scraper SHALL NOT attempt infinite CAPTCHA solving loops
3. THE Scraper SHALL obey configured rate limits and per-host concurrency
4. THE Scraper SHALL log when it stops due to ethical constraints

### Requirement 21: Vision Tier Output Contract

**User Story:** As a developer, I want the vision tier to have a clear output contract, so that downstream code doesn't treat vision output as HTML.

#### Acceptance Criteria

1. THE Vision_Tier SHALL return content_type="vision_text"
2. THE Vision_Tier SHALL return raw_content=None (no HTML bytes)
3. THE Vision_Tier SHALL return extracted_text with the vision output
4. DOWNSTREAM code SHALL check content_type before treating content as HTML

### Requirement 22: Host Trust State

**User Story:** As a researcher, I want the scraper to remember successful authentication per host, so that subsequent pages are faster.

#### Acceptance Criteria

1. THE Orchestrator SHALL track per-host trust state (cookies, clearance timestamp, best tier)
2. WHEN a browser tier obtains clearance cookies, THE Orchestrator SHALL store them for the host
3. WHEN clearance is fresh (< 10 min), THE Orchestrator SHALL prefer curl_cffi over browser tiers
4. THE Host_Trust_State SHALL be used to optimize tier ordering for subsequent URLs on the same host

### Requirement 23: Template-Based Soft Block Detection

**User Story:** As a researcher, I want the scraper to detect blocked pages even when they have normal length, so that I don't get useless data.

#### Acceptance Criteria

1. THE Soft_Block_Detector SHALL compute structural hashes of pages
2. WHEN a page is confirmed as blocked, THE Detector SHALL register its template hash for the host
3. FUTURE pages matching a known block template SHALL be detected immediately
4. THE Template_Detection SHALL use title + h1 + main text patterns
