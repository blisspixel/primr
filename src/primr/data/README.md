# Data Module

This module handles all data collection in Primr, including web scraping, search, and content extraction.

## Components

### Web Scraping (`scrape.py`)

4-tier scraping engine with fallback:

```python
from primr.data.scrape import (
    scrape_with_requests,      # Tier 1: Simple HTTP
    scrape_with_httpx,         # Tier 2: HTTP/2
    scrape_with_playwright,    # Tier 3: Browser
    scrape_with_playwright_aggressive  # Tier 4: Stealth browser
)

content, error = scrape_with_requests(url)
if content is None:
    content, error = scrape_with_httpx(url)
# ... continue through tiers
```

### Parallel Scraping (`parallel_scraper.py`)

Concurrent scraping with rate limiting and circuit breaker:

```python
from primr.data import get_parallel_scraper

scraper = get_parallel_scraper()
results = await scraper.scrape_urls(urls)
```

### Caching (`cache.py`)

Two-layer caching (memory LRU + disk):

```python
from primr.data import cache_get, cache_set, cache_clear

cached = cache_get(url)
if not cached:
    content = scrape(url)
    cache_set(url, content)
```

### Content Extraction (`content_extractor.py`)

Structured extraction of tables, quotes, and financial figures:

```python
from primr.data import get_content_extractor

extractor = get_content_extractor()
tables = extractor.extract_tables(html)
figures = extractor.extract_financial_figures(text)
```

### Search (`search_utils.py`)

Google Custom Search integration:

```python
from primr.data.search_utils import search_google

results = search_google(query, company_name, website)
```

### Link Scoring (`link_scorer.py`)

Prioritizes high-value links for crawling:

```python
from primr.data import get_link_scorer

scorer = get_link_scorer()
scored_links = scorer.score_links(links, company_name)
best = scorer.get_best_links(scored_links, limit=10)
```

## Additional Components

- `adaptive_scraper.py`: Domain-learning scraper that remembers what works
- `http_client.py`: HTTP client wrapper with consistent configuration
- `validator.py`: Fact validation and conflict detection
- `sentiment.py`: Sentiment and tone analysis
- `pagination.py`: Pagination detection and handling
- `monitoring.py`: Change monitoring for tracked companies
- `knowledge_graph.py`: Entity and relationship extraction

## Key Patterns

### Soft Block Detection

Content is analyzed for block indicators:

```python
from primr.data.scrape import detect_soft_block

is_blocked, reason = detect_soft_block(content, url)
if is_blocked:
    # Escalate to next tier
```

### Browser Fingerprinting

Random browser profiles for stealth:

```python
from primr.data.scrape import get_random_profile, create_stealth_context

profile = get_random_profile()
context = create_stealth_context(browser, profile)
```

### Resource Cleanup

Playwright browser is shared and cleaned up on exit:

```python
import atexit
from primr.data.scrape import _cleanup_playwright_browser

atexit.register(_cleanup_playwright_browser)
```

## Configuration

Scraping behavior is configured via `ScrapingConfig`:

- `max_retries`: Retry count per tier
- `timeout`: Request timeout in seconds
- `max_depth`: Maximum crawl depth
- `cache_ttl_hours`: Cache lifetime
- `excluded_sites`: URL patterns to skip
- `soft_block_indicators`: Block detection keywords
