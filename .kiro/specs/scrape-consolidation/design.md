# Design Document: Scrape Consolidation

## Documentation Examples Policy

- Docs MAY use a single fictional placeholder company and domain (e.g., `Acme Corp`, `acme.example`) for clarity.
- Docs MUST NOT use real companies/domains in repeated examples.
- Test targets MUST live in fixture files (not repeated in the docs/tasks narrative).

## Developer Mental Model (Non-Negotiable)

```
scrape_page(url)           → primitive: one URL → content + diagnostics
build_site_corpus(site)    → workflow: calls scrape_page repeatedly, returns corpus
extract_insights(corpus)   → runs once after corpus is built
```

Deep research and report writing NEVER implement scraping. If you need scraped content, call `build_site_corpus`.

## Overview

This design consolidates all scraping to use ONE site-to-corpus workflow so that modes are stopping points in a single pipeline, not separate implementations.

**Two Levels of Scraping:**

| Level | Conceptual Name | Implementation | Input | Output |
|-------|-----------------|----------------|-------|--------|
| Primitive | `scrape_page` | `ScrapeOrchestrator.scrape_url()` | URL | content + tier + quality + errors |
| Workflow | `build_site_corpus` | `fetch_web_content()` | base domain | corpus + raw scrapes + external links |

**Insight Extraction:**

| Conceptual Name | Implementation | Input | Output |
|-----------------|----------------|-------|--------|
| `extract_insights` | `summarize_scraped_content()` | corpus | structured facts |

### Naming Rules (enforced in docs and code comments)

- `scrape_page` always refers to ONE URL (the primitive)
- `build_site_corpus` always refers to multi-page site workflow
- `extract_insights` always refers to corpus → structured facts compression
- `--mode scrape` is "Corpus+Insights mode" (multi-page corpus, not one page)
- Never use "scrape" alone without clarifying page-level or site-level
- Docs must refer to the first pipeline stage as "Build Site Corpus" (not "Scrape Website"), to avoid page-vs-site confusion

**Current State (broken):**
```
perform_scrape_only() ──→ own discovery loop ──→ own scraping loop ──→ own saving
run_research()        ──→ build_site_corpus() ──→ summarize ──→ sections
```

**Target State (correct):**
```
perform_scrape_only() ──→ build_site_corpus() ──→ extract_insights ──→ stop
run_research()        ──→ build_site_corpus() ──→ extract_insights ──→ sections
perform_research()    ──→ build_site_corpus() ──→ extract_insights ──→ deep_research ──→ write_report
```

## Architecture

### Pipeline Flow with Purpose

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              SINGLE PIPELINE                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘

     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
     │  Build Site      │     │  Extract         │     │  Deep Research   │     │  Write Report    │
     │  Corpus          │────▶│  Insights        │────▶│  Validate        │────▶│                  │
     │                  │     │                  │     │  External        │     │                  │
     └──────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
            │                        │                        │                        │
     PURPOSE:                 PURPOSE:                 PURPOSE:                 PURPOSE:
     Produce clean,           Compress corpus          Fill gaps and            Produce final
     validated, deduped       to structured            validate claims          structured
     corpus + diagnostics     facts for downstream     using external           artifact
                              steps                    sources
            │                        │                        │                        │
            ▼                        ▼                        ▼                        ▼
     _raw_scrapes/             insights.txt              dossier.txt              report.docx
     _external_links.txt
     scraped_content.txt
     
     ◄────── scrape mode (Corpus+Insights) ──────►
     ◄─────────────────────────── full mode ──────────────────────────────────────────►
                                              ◄─── deep mode (no scraping) ───────────►
```

### Scope Policy (First-Class Rule)

Scope is enforced during discovery, BEFORE selection:

**In-Scope (always scraped):**
- Same domain as target (e.g., `company.com/*`)
- Subdomains (e.g., `docs.company.com`, `blog.company.com`, `investors.company.com`)

**Out-of-Scope (metadata only in scrape mode):**
- External domains (e.g., press articles, LinkedIn, Crunchbase)
- External links are recorded to `_external_links.txt` for later pipeline stages
- External URLs are NEVER allowed into `selected_urls` in scrape mode

**Full Mode Extension:**
- External sources MAY be scraped during deep research validation phase
- Uses LLM validation to ensure external content is about the target company

### Mode Dispatch

```python
def perform_research(mode="full", ...):
    if mode == "scrape":
        # Corpus+Insights mode: produces evidence + compressed facts
        corpus = build_site_corpus(website, company_name, working_folder=folder)
        extract_insights(corpus, folder)
        return folder
    
    elif mode == "deep":
        # Deep mode: expands evidence using external sources
        perform_deep_research(...)
        write_report(...)
        return folder
    
    else:  # mode == "full"
        # Full pipeline: evidence → compression → expansion → artifact
        corpus = build_site_corpus(website, company_name, working_folder=folder)
        extract_insights(corpus, folder)
        deep_research_validate_external(...)  # External sources validated here
        write_report(...)
        return folder
```

## Components and Interfaces

### build_site_corpus() - The ONE Site-to-Corpus Workflow

**Conceptual name:** `build_site_corpus`  
**Implementation name:** `fetch_web_content()` in `src/primr/data/scrape.py`

This is the composition of these internal stages:

```python
def build_site_corpus(website, company_name, max_pages=50, working_folder=None):
    """
    Site-to-corpus workflow. THE ONLY function that performs site-level scraping.
    
    Internal Stages:
    1. discover_site_urls(website) -> (in_scope_urls, external_urls)
    2. rank_and_select_urls(in_scope_urls, max_pages) -> selected_urls
    3. scrape_pages(selected_urls) -> page_results
    4. build_corpus(page_results) -> corpus
    5. clean_corpus(corpus) -> cleaned_corpus
    6. save_raw_scrapes(page_results, working_folder)
    7. save_external_links(external_urls, working_folder)
    
    No other function should perform any subset of these steps except by calling
    this composition.
    
    Scope Policy (enforced in stage 1):
    - IN-SCOPE: same domain + subdomains
    - OUT-OF-SCOPE: external domains (recorded to _external_links.txt, not scraped)
    
    Coverage Expectations (defaults for typical sites, configurable):
    - Attempts: homepage, about, products, pricing, docs, security pages
    - Minimum: 10 pages discovered, 5000 chars extracted
    - Note: blocked/single-page/tiny sites may not meet these thresholds
    
    URL Selection:
    - Deterministic heuristics work without LLM (baseline)
    - LLM selection is optional refinement layer
    - LLM link selection happens ONLY inside build_site_corpus
    
    Quality Escalation Triggers (defaults, configurable):
    - quality_score < 0.3
    - char_count < 200
    - link_density > 0.5
    - boilerplate_ratio > 0.6
    
    Returns:
        Dict mapping URL -> extracted text (cleaned, boilerplate removed)
    """
```

### scrape_page() - The Page Scrape Primitive

**Conceptual name:** `scrape_page`  
**Implementation name:** `ScrapeOrchestrator.scrape_url()` in `src/primr/data/scraping/orchestrator.py`

```python
class ScrapeOrchestrator:
    """
    Tiered page scrape engine with automatic escalation.
    
    This handles INDIVIDUAL PAGE scraping, not site-level workflow.
    scrape_url() is the implementation of the scrape_page primitive.
    
    Tiers (in order):
    1. requests - fast HTTP
    2. httpx - HTTP/2
    3. curl_cffi - TLS fingerprint impersonation
    4. playwright - browser rendering
    5. playwright_aggressive - content expansion
    6. drissionpage - driverless browser
    7. drissionpage_stealth - challenge waiting
    8. vision - AI extraction (opt-in)
    
    Features:
    - Sticky tier: once a tier works for a host, try it first
    - Circuit breaker: skip failing tiers after 3 consecutive failures
    - Cookie handoff: browser cookies reused by HTTP tiers
    - Soft block detection: checks content, not just HTTP status
    """
    
    def scrape_url(self, url: str) -> ScrapeResult:
        """
        scrape_page primitive: scrape a single URL with tier escalation.
        
        Returns:
            ScrapeResult with:
            - success: bool
            - raw_content: bytes (HTML)
            - extracted_text: str (cleaned)
            - tier: str (which tier succeeded)
            - quality: float (0-1 score)
            - error: str (if failed)
        """
```

### BoilerplateFilter - Cross-Page Deduplication

Location: `src/primr/data/scraping/boilerplate.py`

```python
class BoilerplateFilter:
    """
    Learns and removes boilerplate content across pages.
    
    Algorithm:
    1. Normalize lines (lowercase, strip punctuation, collapse whitespace)
    2. Count frequency across pages
    3. Mark lines appearing in >30% of pages as boilerplate
    4. Preserve allowlisted content (brand taglines, product names)
    
    Quality Metrics (logged per page):
    - boilerplate_ratio: fraction of content that is boilerplate
    - repeated_lines_ratio: fraction of lines that repeat within page
    - link_density: ratio of link text to total text
    """
    
    def add_page(self, text: str) -> None:
        """Add a page's text for boilerplate learning."""
    
    def compute_boilerplate(self, threshold: float = 0.3) -> None:
        """Compute boilerplate lines based on frequency threshold."""
    
    def filter(self, text: str) -> str:
        """Remove boilerplate lines from text."""
```

## Data Models

### Raw Scrape File Format

Each file in `_raw_scrapes/` follows this format:

```
URL: https://example.com/about
Tier: requests
Title: About Us - Example Corp
Quality: 0.85 []
Metrics: 3456 chars, 12 headings, 24 paragraphs, link_density=0.15, boilerplate_ratio=0.12
------------------------------------------------------------

[Actual extracted content here]
```

### External Links File Format

`_external_links.txt` captures discovered external links for later pipeline stages:

```
# External Links Discovered
# Target: Example Corp (https://example.com)
# Scraped: 2026-01-09 09:15
# Note: These are NOT scraped in scrape mode. Available for full mode validation.

## Press/News
https://techcrunch.com/2025/12/01/example-corp-raises-50m/
https://forbes.com/companies/example-corp/

## Social
https://linkedin.com/company/example-corp
https://twitter.com/examplecorp

## Other
https://crunchbase.com/organization/example-corp
```

### Working Folder Structure (Scrape Mode Outputs)

```
working/ExampleCo/2026-01-09_0915/
├── _raw_scrapes/           # Individual page scrapes (for validation)
│   ├── 001_homepage.txt
│   ├── 002_about.txt
│   ├── 003_products.txt
│   └── ...
├── _external_links.txt     # Discovered external links (metadata only)
├── scraped_content.txt     # All scraped content combined (corpus)
├── insights.txt            # LLM-extracted insights
└── _scraped_urls.txt       # List of URLs scraped
```

### Quality Metrics

```python
@dataclass
class QualityMetrics:
    char_count: int           # Total characters extracted
    word_count: int           # Total words
    heading_count: int        # Number of headings (H1-H6)
    paragraph_count: int      # Number of paragraphs
    link_density: float       # Ratio of link text to total text (0-1)
    boilerplate_ratio: float  # Fraction of boilerplate content (0-1)
    repeated_lines: float     # Fraction of repeated lines (0-1)
    quality_score: float      # Overall quality (0-1)
    flags: list[str]          # Quality issues detected
```

### Escalation Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| quality_score | < 0.3 | Escalate to next tier |
| char_count | < 200 | Escalate to next tier |
| link_density | > 0.5 | Escalate or flag low quality |
| boilerplate_ratio | > 0.6 | Apply cross-page filtering |
| repeated_lines | > 0.3 | Deduplicate within page |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system - essentially, a formal statement about what the system should do.*

### Property 1: No Second Site-to-Corpus Implementation

*There SHALL NOT exist any other function that:*
- discovers links from a domain, AND
- selects a subset, AND
- scrapes pages in a loop

*except `build_site_corpus()` (implemented as `fetch_web_content()`).*

**Validates: Requirements 1.1, 1.8, 1.9**

### Property 2: Scope Policy Enforcement

*For any* discovered link during site scraping:
- If the link is on the same domain or a subdomain of the target, it SHALL be eligible for selection
- If the link is external, it SHALL be recorded in `_external_links.txt` but NEVER appear in `selected_urls` in scrape mode

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

### Property 3: Raw Scrape Completeness

*For any* file saved to `_raw_scrapes/`, the file SHALL contain: URL, Tier, Title, Quality score, Metrics (char_count, heading_count, paragraph_count, link_density, boilerplate_ratio), and content separated by a delimiter line.

**Validates: Requirements 3.2**

### Property 4: Mode Equivalence for Corpus Output

*For any* website, running scrape mode and running full mode SHALL produce:
- Identical `_raw_scrapes/` folder contents
- Identical `scraped_content.txt` (corpus)
- Identical `_external_links.txt` contents

**Validates: Requirements 4.4**

### Property 5: Quality Escalation

*For any* page where initial tier produces:
- quality_score < 0.3, OR
- char_count < 200, OR
- link_density > 0.5

The system SHALL attempt higher tiers until success or all tiers exhausted.

**Validates: Requirements 5.3, 5.4, 5.5**

### Property 6: Boilerplate Removal

*For any* corpus of pages from a single website:
- Lines appearing in >30% of pages SHALL NOT appear in final cleaned output
- Within-page repeated lines SHALL be deduplicated
- High link-density regions SHALL be pruned before extraction
- boilerplate_ratio SHALL be logged for each page

**Validates: Requirements 6.1, 6.2, 6.3, 6.6**

### Property 7: Corpus Coverage

*For any* typical company website (not blocked, has standard pages):
- Discovery SHALL find at least 10 pages
- Extraction SHALL produce at least 5000 total characters
- Discovery SHALL attempt to find: homepage, about, products, pricing, docs, security pages

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 8: Deterministic Selection Baseline

*For any* website, URL selection SHALL work without LLM availability using deterministic heuristics. LLM selection is an optional refinement layer.

**Validates: Requirements 7.5, 7.6**

### Property 9: Single Responsibility Boundaries

- LLM link selection SHALL happen ONLY inside `build_site_corpus`
- LLM insight extraction SHALL happen ONLY in `extract_insights` stage
- No other function SHALL perform LLM-based link selection or insight extraction

**Validates: Requirements 1.8, 1.9**

## Error Handling

| Error | Handling |
|-------|----------|
| No pages discovered | Return empty dict, log warning |
| All pages fail to scrape | Return empty dict, show error message |
| Working folder not writable | Skip raw scrape saving, continue with scraping |
| LLM summarization fails | Return raw scraped content without insights |
| External link recording fails | Log warning, continue with scraping |
| LLM selection unavailable | Fall back to deterministic heuristics |

## Testing Strategy

Fixtures drive tests; do not embed real sites in docs. See `tasks.md` for detailed test implementation.

### Test Fixtures

- `tests/fixtures/sites.json` - Representative site types (docs-heavy, JS-heavy, blog-driven)
- `tests/fixtures/regression_urls.json` - URLs that triggered past bugs

### Test Categories

1. **Unit Tests**: Delegation, raw scrape format, scope policy, boilerplate filter
2. **Property-Based Tests**: Scope policy, mode equivalence, quality escalation (using `hypothesis`)
3. **Integration Tests**: Multi-site corpus against fixture configs
4. **Regression Tests**: Fixture-based regression cases
5. **Static Analysis**: Scan for duplicate site-scrape patterns
