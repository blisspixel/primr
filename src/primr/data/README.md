# Data Package

`primr.data` owns public-evidence collection and normalization. Its primary
contract is one site-to-corpus workflow built on one page-level scraping
primitive. AI synthesis belongs in `primr.ai`; run coordination belongs in
`primr.core`.

## Concern map

| Area | Modules | Responsibility |
|------|---------|----------------|
| Site workflow | `scrape.py` | URL discovery, ranking, page collection, corpus assembly, raw scrape storage, and fallback routing |
| Page primitive | `scraping/orchestrator.py`, `scraping/tier_registry.py` | Tier selection, escalation, sticky host state, cookie handoff, and standardized `ScrapeResult` values |
| Browser tiers | `scraping/browsers.py`, `scraping/stealth_browser.py`, `scraping/vision_browser.py` | Playwright, Patchright, DrissionPage, and screenshot-based retrieval |
| HTTP tiers | `scraping/http_clients.py`, `pinned_requests.py`, `safe_http.py` | curl_cffi, httpx, requests, and pinned safe-request handling |
| Discovery and validation | `scraping/discovery.py`, `scraping/net.py`, `scraping/validation.py`, `link_scorer.py` | Scope checks, link selection, block detection, and content validation |
| Extraction | `scraping/content.py`, `scraping/structured_content.py`, `content_extractor.py` | Main-text, PDF, metadata, table, and structured-content extraction |
| Recovery sources | `fallback_sources.py`, `first_party_*.py`, `scraping/wayback.py` | Same-site recovery, first-party documents, Wayback, feeds, filings, and public fallbacks |
| Hiring signals | `hiring_signals.py`, `hiring_*.py` | ATS discovery, career-page recovery, posting selection, extraction, routing, and artifacts |
| Search | `search_utils.py` | External search provider selection and normalized result collection |
| Performance | `parallel_scraper.py`, `adaptive_scraper.py`, `cache.py` | Bounded concurrency, learned host behavior, and content caching |
| Trace and host state | `scraping/trace.py`, `scraping/trace_stats.py`, `scraping/host_markers.py`, `scraping/rate_limit_state.py` | Attempt records, compact health summaries, positive markers, and rate-limit state |
| Supporting analysis | `validator.py`, `sentiment.py`, `knowledge_graph.py`, `monitoring.py`, `pagination.py` | Optional fact, tone, entity, change, and pagination utilities |

## Collection shape

```text
base company URL
        |
        v
discover and rank in-scope links
        |
        v
scrape_page for each selected URL
        |
        +-> Playwright
        +-> Playwright aggressive
        +-> Patchright
        +-> curl_cffi
        +-> DrissionPage stealth
        +-> DrissionPage
        +-> Vision when enabled
        +-> httpx
        +-> requests
        |
        v
validate and extract content -> corpus, raw pages, links, and trace records
        |
        v
same-site and public fallback sources when live access is insufficient
```

`scrape_page` always means one URL. `build_site_corpus`, implemented by
`fetch_web_content()`, always means the multi-page workflow. New collection
features extend these seams instead of adding another discovery and scrape
loop. The registry defines nine ordered tiers; runtime availability and
configuration can filter optional tiers for a specific call.

## Safety and resource boundaries

- Every outbound URL passes SSRF validation before connection and after
  redirects.
- The HTTP client set is deliberately closed because tier diversity is part of
  the retrieval design.
- Browser and thread-pool lifetimes are owned by their context managers and
  orchestrators, not by callers reaching into private cleanup functions.
- Untrusted page and posting text is fenced before model use.
- Network failures, blocks, and thin content return typed results and traces so
  the caller can degrade without treating failure as evidence.
