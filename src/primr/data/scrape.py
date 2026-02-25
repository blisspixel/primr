"""
Web Scraper - Refactored to use new modular scraping architecture.

This module provides the high-level scraping API used by the rest of Primr.
It wraps the new modular scraping system in primr.data.scraping.
"""

import hashlib
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from primr.config.config import PROJECT_ROOT
from primr.config.config import (
    SCRAPE_PILOT_COUNT,
    SCRAPE_PILOT_MIN_CHARS,
    SCRAPE_PILOT_MIN_SUCCESS_RATE,
)

# Import from new modular scraping system
from primr.data.scraping import (
    COMMON_PAGE_PATTERNS,
    DiscoveredLink,
    RateLimitConfig,
    RateLimiter,
    ScrapeCache,
    ScrapeOrchestrator,
    ScrapeResult,
)
from primr.data.scraping.tier_registry import get_available_tiers
from primr.data.scraping import (
    extract_links_from_html as _extract_links_from_html_new,
)
from primr.data.scraping import (
    normalize_url as normalize_url_new,
)
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("scrape")

# =============================================================================
# Console Output Helpers
# =============================================================================

def out_step(msg):
    console.step(msg)

def out_ok(msg, show_time=True):
    console.ok(msg, show_time=show_time)

def out_warn(msg):
    console.warn(msg)

def out_err(msg):
    console.error(msg)

def out_info(msg):
    console.info(msg)

def out_progress(current, total, msg=""):
    console.progress(current, total, msg)

def out_progress_done():
    console.progress_done()


# =============================================================================
# Caching Setup
# =============================================================================

CACHE_DIR = Path(PROJECT_ROOT) / "logs" / "scrape_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Global orchestrator instance (lazy initialized)
_orchestrator: ScrapeOrchestrator | None = None


def get_orchestrator(
    enable_vision: bool = True,
    use_cache: bool = False,
) -> ScrapeOrchestrator:
    """Get or create the global scrape orchestrator.

    Args:
        enable_vision: Enable vision tier for image-heavy pages (default: True)
        use_cache: Use cached content (default: False for fresh data)
    """
    global _orchestrator

    if _orchestrator is None:
        tiers = get_available_tiers()

        # Drission tiers are powerful but can hang on some Windows environments.
        # Default to Playwright/HTTP/Vision unless explicitly enabled.
        enable_drission = os.getenv("PRIMR_ENABLE_DRISSION", "0").lower() in {"1", "true", "yes"}
        if not enable_drission:
            tiers = [t for t in tiers if t.name not in {"drissionpage", "drissionpage_stealth"}]

        _orchestrator = ScrapeOrchestrator(
            tiers=tiers,
            cache=ScrapeCache(cache_dir=str(CACHE_DIR)),
            rate_limiter=RateLimiter(RateLimitConfig(
                per_host_requests_per_minute=30,  # Tokens refill every 2s; actual scrapes take 2-15s
                base_delay_seconds=0.5,  # Reduced jitter when rate-limited (0-0.5s vs 0-1.5s)
            )),
            enable_vision=enable_vision,
            max_page_time=45.0,  # Allow time for quality content - we want the data
            delay_between_tiers=(0.3, 1.0),  # Avg 0.65s between failed tiers (was 1-3s)
            use_cache=use_cache,
            circuit_breaker_threshold=5,  # More lenient - sites have mixed content
        )

    return _orchestrator


# =============================================================================
# URL Utilities
# =============================================================================

def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    if not url:
        return url
    return normalize_url_new(url)


def is_valid_url_string(s: str) -> bool:
    """Check if a string is a valid HTTP(S) URL."""
    try:
        parsed = urlparse(s)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except (ValueError, AttributeError):
        return False


def validate_url(url: str, base_url: str | None = None) -> str | None:
    """Validate and normalize a URL."""
    if not isinstance(url, str) or len(url) < 5:
        return None
    parsed = urlparse(url)
    if not parsed.scheme:
        url = f"https://{url.lstrip('/')}"
    return url if "http" in url else None


# =============================================================================
# Main Scraping Functions
# =============================================================================

def scrape_page(
    url: str,
    silent: bool = False,
    pbar=None,
    use_vision: bool = False,
) -> tuple[str | None, str | None]:
    """
    Scrape a single page using tiered approach.

    Args:
        url: URL to scrape
        silent: Suppress console output
        pbar: Progress bar (unused, kept for compatibility)
        use_vision: Enable vision tier for hard-to-scrape pages

    Returns:
        Tuple of (extracted_text, tier_name) or (None, error_reason)
    """
    orchestrator = get_orchestrator(enable_vision=use_vision)

    result = orchestrator.scrape_url(url)

    if result.success:
        return result.extracted_text, result.tier
    else:
        return None, result.error


def fetch_web_content(
    website: str,
    company_name: str,
    max_pages: int | None = None,
    use_vision: bool = False,
    working_folder: str | None = None,
) -> dict[str, str]:
    """
    build_site_corpus: Discover and scrape pages from a company website.

    This is THE ONLY function that performs site-level scraping.
    All modes that need a corpus call this function.

    Uses structured content extraction with:
    - Aggressive DOM pruning (removes nav/footer/CTA before extraction)
    - Boilerplate fingerprinting (learns and removes repeated lines across pages)
    - Structured blocks (preserves headings, lists, quotes)

    Scope Policy (enforced during discovery):
    - IN-SCOPE: same domain + subdomains (scraped)
    - OUT-OF-SCOPE: external domains (recorded to _external_links.txt, not scraped)

    Args:
        website: Base URL of the website
        company_name: Company name (for logging)
        max_pages: Maximum pages to scrape (default: no limit)
        use_vision: Enable vision tier for hard-to-scrape pages
        working_folder: If provided, save raw scrapes incrementally to this folder

    Returns:
        Dict mapping URL -> extracted text (cleaned, boilerplate removed)
    """
    import os
    from concurrent.futures import ThreadPoolExecutor

    from .scraping import (
        BoilerplateFilter,
        extract_main_content,
        extract_structured_content,
        scrape_with_playwright,
    )

    def _write_raw_file(file_path, url, tier, structured):
        """Write raw scrape file to disk (may run in background thread)."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n")
                f.write(f"Tier: {tier}\n")
                f.write(f"Title: {structured.title or 'N/A'}\n")
                f.write(f"Quality: {structured.quality.score:.2f} {structured.quality.flags}\n")
                f.write(f"Metrics: {structured.metrics.char_count} chars, ")
                f.write(f"{structured.metrics.heading_count} headings, ")
                f.write(f"{structured.metrics.paragraph_count} paragraphs, ")
                f.write(f"link_density={structured.metrics.link_density:.2f}, ")
                f.write(f"boilerplate_ratio={structured.metrics.boilerplate_ratio:.2f}\n")
                f.write("-" * 60 + "\n\n")
                f.write(structured.raw_text)
        except Exception as e:
            logger.debug(f"Failed to save raw scrape: {e}")

    # Create raw scrapes folder if working_folder provided
    raw_folder = None
    trace_file = None
    if working_folder:
        raw_folder = os.path.join(working_folder, "_raw_scrapes")
        os.makedirs(raw_folder, exist_ok=True)
        trace_file = os.path.join(raw_folder, "_scrape_trace.log")

    def _append_trace(status: str, url: str, detail: str = "") -> None:
        """Write a compact per-page scrape outcome trace for debugging."""
        if not trace_file:
            return
        try:
            with open(trace_file, "a", encoding="utf-8") as f:
                line = f"{status} | {url}"
                if detail:
                    line += f" | {detail}"
                f.write(line + "\n")
        except Exception as e:
            logger.debug(f"Failed to write scrape trace: {e}")

    def _failure_detail(result: ScrapeResult) -> str:
        """Extract a useful failure reason even when result.error is empty."""
        if result.error:
            return result.error
        if result.attempts:
            last = result.attempts[-1]
            if last.error:
                return last.error
            if last.error_type:
                return str(last.error_type)
            if last.http_status:
                return f"http_status={last.http_status}"
        if result.error_type:
            return str(result.error_type)
        return "unknown"

    domain = urlparse(website).netloc
    orchestrator = get_orchestrator(enable_vision=use_vision)

    # Step 1: Get homepage with browser (modern sites need JS rendering)
    console.status(f"Scanning {domain}...")

    # Use playwright directly for homepage - it handles JS
    # Homepage gets a generous timeout: failed homepage = entire run fails
    result = scrape_with_playwright(website, timeout=25)
    homepage_tier = "playwright"

    if not result.success or not result.raw_content:
        # Fallback to orchestrator (tries all tiers)
        result = orchestrator.scrape_url(website)
        homepage_tier = result.tier if result.success else None

    if not result.success or not result.raw_content:
        _append_trace("FAIL", website, f"homepage: {result.error}")
        console.clear_line()
        console.fail(f"Could not access {domain}")
        return {}
    _append_trace("OK", website, f"homepage via {homepage_tier or result.tier}")

    # Tell orchestrator what tier worked for this host (sticky tier)
    # This prevents wasteful tier escalation on subsequent pages
    if homepage_tier:
        from .scraping.net import extract_host
        host = extract_host(website)
        host_state = orchestrator._get_host_state(host)
        host_state.best_tier = homepage_tier
        logger.debug(f"Set best_tier={homepage_tier} for {host} based on homepage success")

    homepage_html = result.raw_content

    # Step 2: Discover ALL links using full discovery pipeline
    # This includes: homepage links, common URL guessing, sitemap fallback
    from .scraping.discovery import discover_links, is_same_domain

    all_links = discover_links(
        base_url=website,
        homepage_html=homepage_html,
        verify_guessed=True,  # Verify guessed URLs exist
        min_links_before_sitemap=20,  # Check sitemap if < 20 links
    )

    # Filter to in-scope links (same domain + subdomains)
    in_scope_links = [link for link in all_links if is_same_domain(website, link.url)]

    # Use LLM to intelligently select the most valuable pages for company research
    # The LLM decides how many pages are worth scraping - no artificial limits
    # Falls back to heuristic scoring if LLM fails
    from primr.core.research_agent import select_links_with_llm

    with console.spinner(f"Selecting from {len(in_scope_links)} pages"):
        selected_urls = select_links_with_llm(
            in_scope_links,
            company_name=company_name,
            website=website,
            max_links=max_pages or 100,  # Let LLM decide, but cap at 100 for sanity
        )
    total_found = len(selected_urls)

    # Apply max_pages limit (reserve 1 slot for homepage)
    if max_pages and max_pages < total_found + 1:
        pages_to_scrape = selected_urls[:max_pages - 1]
        console.found(f"{len(in_scope_links)} links {console._arrow} {max_pages} selected")
    elif total_found == 0:
        pages_to_scrape = []
        console.found("1 page (homepage only)")
    else:
        pages_to_scrape = selected_urls
        console.found(f"{len(in_scope_links)} links {console._arrow} {total_found} selected")

    # Persist selected URL set for reproducibility and debugging.
    if raw_folder:
        selected_links_file = os.path.join(raw_folder, "_selected_links.txt")
        try:
            with open(selected_links_file, "w", encoding="utf-8") as f:
                f.write(f"# Selected links for {company_name}\n")
                f.write(f"# Website: {website}\n")
                f.write(f"# Selected count: {len(pages_to_scrape)} (excluding homepage)\n\n")
                for idx, link in enumerate(pages_to_scrape, start=1):
                    f.write(f"{idx:03d}. {link}\n")
        except Exception as e:
            logger.debug(f"Failed to save selected links manifest: {e}")

    # Flush stdout to ensure progress shows immediately
    import sys
    sys.stdout.flush()

    # Step 3: Scrape pages (homepage first, then discovered links)
    scrape_start = time.time()
    raw_pages = []  # List of (url, raw_html_bytes)
    structured_cache = {}  # normalized_url -> StructuredContent (reused in Phase 2)
    scraped_results = {}  # url -> ScrapeResult
    success_count = 0
    write_executor = ThreadPoolExecutor(max_workers=1) if raw_folder else None

    # Add homepage as first result (we already scraped it for link discovery)
    homepage_normalized = normalize_url(website)
    homepage_result = ScrapeResult(
        url=website,
        success=True,
        raw_content=homepage_html,
        tier=result.tier,
    )
    scraped_results[homepage_normalized] = homepage_result
    raw_pages.append((homepage_normalized, homepage_html))
    success_count = 1

    # Save homepage raw scrape (and cache extraction for Phase 2)
    if raw_folder:
        try:
            structured = extract_structured_content(homepage_html, website)
            structured_cache[homepage_normalized] = structured
            raw_file = os.path.join(raw_folder, "homepage.txt")
            write_executor.submit(_write_raw_file, raw_file, website, result.tier, structured)
        except Exception as e:
            logger.debug(f"Failed to save homepage raw scrape: {e}")

    total = len(pages_to_scrape) + 1  # +1 for homepage already scraped
    page_times = []  # Track per-page durations for ETA
    dup_count = 0  # Pages rejected as duplicate content
    attempted_urls: set[str] = {homepage_normalized}

    pilot_count = min(max(0, SCRAPE_PILOT_COUNT), len(pages_to_scrape))
    pilot_attempts = 0
    pilot_success = 0
    pilot_chars_total = 0

    # Track content hashes to detect duplicate/wrong-page content
    # (e.g. every page returning the same sidebar widget text)
    _seen_content_hashes: set[str] = set()
    # Seed with homepage content so later pages that return the same
    # text (e.g. a global sidebar widget) are caught as duplicates.
    # Uses extract_main_content (same pipeline as the orchestrator's
    # result.extracted_text) to ensure hashes are comparable.
    if homepage_html:
        try:
            _hp_text = extract_main_content(homepage_html)
            if _hp_text and _hp_text.strip():
                _seen_content_hashes.add(hashlib.md5(_hp_text.encode()).hexdigest())
        except Exception:
            pass

    # Show initial progress immediately
    if pages_to_scrape:
        console.scrape_progress(1, total, "homepage", scrape_start, ok_count=success_count)
        logger.info(f"Starting to scrape {total} pages (homepage + {len(pages_to_scrape)} discovered)")

    try:
        for i, page_url in enumerate(pages_to_scrape):
            normalized = normalize_url(page_url)
            if normalized in scraped_results or normalized in attempted_urls:
                continue
            attempted_urls.add(normalized)

            path = urlparse(page_url).path or "/"
            path_display = path[:30] + "..." if len(path) > 30 else path

            logger.debug(f"Scraping page {i + 2}/{total}: {page_url}")
            _append_trace("TRY", page_url, f"attempt {i + 2}/{total}")
            # Show immediate page transition so long-running pages don't appear stuck.
            console.scrape_progress(i + 2, total, path_display, scrape_start, ok_count=success_count)

            page_start = time.time()
            result = orchestrator.scrape_url(page_url)
            page_elapsed = time.time() - page_start

            # Track timing and compute ETA from rolling average
            page_times.append(page_elapsed)
            avg_time = sum(page_times) / len(page_times)
            remaining = total - (i + 2)
            eta_seconds = avg_time * remaining if remaining > 0 else 0

            # Only log actual failures (not slow-but-successful pages)
            if not result.success:
                logger.debug(f"Failed {page_url}: {result.error}")
                _append_trace("FAIL", page_url, _failure_detail(result))

            if result.success and result.raw_content:
                # Dedup: reject pages whose extracted text is identical to a
                # previously scraped page (catches wrong-page / sidebar-only content)
                _text_for_hash = result.extracted_text or ""
                _content_hash = hashlib.md5(_text_for_hash.encode()).hexdigest() if _text_for_hash else ""
                if _content_hash and _content_hash in _seen_content_hashes:
                    dup_count += 1
                    logger.info(
                        f"Duplicate content for {page_url} (matches previously scraped page) — skipping"
                    )
                    _append_trace("DUP", page_url, f"tier={result.tier}")
                    continue
                if _content_hash:
                    _seen_content_hashes.add(_content_hash)

                scraped_results[normalized] = result
                raw_pages.append((normalized, result.raw_content))
                success_count += 1
                logger.debug(f"Scraped {page_url} via {result.tier}")
                _append_trace("OK", page_url, f"tier={result.tier}")
                if pilot_attempts < pilot_count:
                    pilot_success += 1
                    pilot_chars_total += len(result.extracted_text or "")

                # Extract + cache structured content, write raw file in background
                if raw_folder:
                    try:
                        structured = extract_structured_content(result.raw_content, page_url)
                        structured_cache[normalized] = structured
                        safe_name = path.replace("/", "_").strip("_") or "page"
                        safe_name = safe_name[:50]
                        raw_file = os.path.join(raw_folder, f"{safe_name}.txt")
                        write_executor.submit(_write_raw_file, raw_file, page_url, result.tier, structured)
                    except Exception as e:
                        logger.debug(f"Failed to save raw scrape: {e}")
            else:
                logger.debug(f"Failed to scrape {page_url}: {result.error}")
                _append_trace("FAIL", page_url, _failure_detail(result))

            if pilot_attempts < pilot_count:
                pilot_attempts += 1
                if pilot_attempts == pilot_count:
                    success_rate = pilot_success / max(pilot_attempts, 1)
                    avg_chars = int(pilot_chars_total / max(pilot_success, 1)) if pilot_success else 0
                    _append_trace(
                        "PILOT",
                        website,
                        (
                            f"attempts={pilot_attempts}, success={pilot_success}, "
                            f"success_rate={success_rate:.2f}, avg_chars={avg_chars}"
                        ),
                    )
                    if success_rate < SCRAPE_PILOT_MIN_SUCCESS_RATE or avg_chars < SCRAPE_PILOT_MIN_CHARS:
                        console.clear_line()
                        console.fail(
                            "Pilot scrape validation failed "
                            f"({pilot_success}/{pilot_attempts} ok, avg {avg_chars} chars)"
                        )
                        console.muted(
                            "  Defensive stop: initial sample quality too low to trust full crawl"
                        )
                        console.muted(
                            "  Override thresholds via SCRAPE_PILOT_* env vars if needed"
                        )
                        return {}

            # Show progress AFTER processing so "ok" count is accurate
            console.scrape_progress(
                i + 2,
                total,
                path_display,
                scrape_start,
                eta_seconds=eta_seconds,
                ok_count=success_count,
            )
    finally:
        # Ensure executor shutdown even if scraping loop throws
        if write_executor:
            write_executor.shutdown(wait=True)

    console.clear_line()

    # Show scrape completion
    scrape_elapsed = time.time() - scrape_start
    if scrape_elapsed < 60:
        time_str = f"{int(scrape_elapsed)}s"
    else:
        time_str = f"{int(scrape_elapsed // 60)}m {int(scrape_elapsed % 60)}s"
    dup_note = f", {dup_count} duplicates skipped" if dup_count else ""
    console.done(f"{success_count}/{total} pages scraped ({time_str}{dup_note})")

    # Phase 2: Apply boilerplate learning across all pages
    if len(raw_pages) >= 3:
        # Learn boilerplate from scraped pages
        bp_filter = BoilerplateFilter()

        for url, raw_html in raw_pages:
            # Use cached extraction if available (avoids duplicate work)
            structured = structured_cache.get(url) or extract_structured_content(raw_html, url)
            bp_filter.add_page(structured.raw_text)

        # Compute boilerplate (lines appearing in >30% of pages)
        bp_filter.compute_boilerplate(threshold=0.3)

        boilerplate_count = len(bp_filter.boilerplate_lines)
        if boilerplate_count > 0:
            logger.debug(f"Detected {boilerplate_count} boilerplate patterns")

        # Re-extract with boilerplate removal
        scraped_content = {}
        for url, raw_html in raw_pages:
            structured = extract_structured_content(raw_html, url, bp_filter)
            # Use clean_text (boilerplate removed) and exclude CTAs
            clean_text = structured.to_plain_text(include_cta=False)
            if clean_text.strip():
                scraped_content[url] = clean_text
    else:
        # Not enough pages for boilerplate learning, use direct extraction
        scraped_content = {}
        for url, raw_html in raw_pages:
            structured = structured_cache.get(url) or extract_structured_content(raw_html, url)
            clean_text = structured.to_plain_text(include_cta=False)
            if clean_text.strip():
                scraped_content[url] = clean_text

    return scraped_content


def scrape_external_sources(
    search_results: list[dict],
    max_sources: int = 2,
    allowed_domains: list[str] | None = None,
) -> dict[str, str]:
    """
    Scrape external sources from search results.

    Args:
        search_results: List of search result dicts with 'url' key
        max_sources: Maximum sources to scrape
        allowed_domains: Optional list of allowed domain substrings

    Returns:
        Dict mapping URL -> extracted text
    """
    orchestrator = get_orchestrator()
    scraped_sources = {}
    count = 0

    for result in search_results:
        url = result.get("url")
        if not url:
            continue

        # Filter by allowed domains if specified
        if allowed_domains:
            domain = urlparse(url).netloc.lower()
            if not any(allowed in domain for allowed in allowed_domains):
                continue

        scrape_result = orchestrator.scrape_url(url)

        if scrape_result.success and scrape_result.extracted_text:
            text = scrape_result.extracted_text.strip()
            if len(text) > 100:
                scraped_sources[url] = text
                count += 1

        if count >= max_sources:
            break

    return scraped_sources


def scrape_external_sources_validated(
    search_results: list[dict],
    company_name: str,
    website: str,
    max_sources: int = 2,
    working_folder: str | None = None,
) -> dict[str, str]:
    """
    Scrape external sources with LLM validation to ensure they're about the right company.

    This prevents including content from similarly-named but unrelated companies
    (e.g., "EverTrue" fundraising software vs "EverTrue" senior living).

    The LLM is instructed to be DEFENSIVE - assume it's wrong unless clearly right.
    But it's also smart about mergers, subsidiaries, investors, and name changes.

    Args:
        search_results: List of search result dicts with 'url' key
        company_name: Name of the target company
        website: Target company's website (for context)
        max_sources: Maximum validated sources to return
        working_folder: If provided, save raw scrapes to _raw_scrapes subfolder

    Returns:
        Dict mapping URL -> extracted text (only for validated sources)
    """
    import os

    from primr.ai.llm import llm

    orchestrator = get_orchestrator()
    validated_sources = {}
    count = 0

    # Create raw scrapes folder if working_folder provided
    raw_folder = None
    if working_folder:
        raw_folder = os.path.join(working_folder, "_raw_scrapes")
        os.makedirs(raw_folder, exist_ok=True)

    # Extract domain from website for context
    target_domain = urlparse(website).netloc.lower().replace("www.", "") if website else ""

    external_idx = 0
    for result in search_results:
        url = result.get("url")
        title = result.get("title", "")
        if not url:
            continue

        # Skip if it's the company's MAIN website (exact match only)
        # We want to KEEP subdomains like investors.company.com, blog.company.com
        # Only filter: company.com, www.company.com
        source_domain = urlparse(url).netloc.lower()
        source_domain_no_www = source_domain.replace("www.", "")
        if target_domain and source_domain_no_www == target_domain:
            # Exact match - this is the main site, skip it
            continue

        # Scrape the content
        scrape_result = orchestrator.scrape_url(url)

        if not scrape_result.success or not scrape_result.extracted_text:
            continue

        text = scrape_result.extracted_text.strip()
        if len(text) < 100:
            continue

        external_idx += 1

        # Save raw scrape incrementally if working folder provided
        if raw_folder:
            source_domain = urlparse(url).netloc.replace("www.", "")
            safe_name = source_domain[:30]
            raw_file = os.path.join(raw_folder, f"ext_{external_idx:03d}_{safe_name}.txt")
            try:
                with open(raw_file, "w", encoding="utf-8") as f:
                    f.write(f"URL: {url}\n")
                    f.write(f"Title: {title}\n")
                    f.write("Source: External (web search)\n")
                    f.write(f"Length: {len(text)} chars\n")
                    f.write("-" * 60 + "\n\n")
                    f.write(text)
            except Exception as e:
                logger.debug(f"Failed to save external raw scrape: {e}")

        # Use LLM to validate this is about the RIGHT company
        # Use a small snippet to save tokens
        snippet = text[:2000]

        validation_prompt = f"""You are a fact-checker. Determine if this article is about a SPECIFIC company.

TARGET COMPANY:
- Full Name: {company_name}
- Website: {website}
- Domain: {target_domain}

ARTICLE TO CHECK:
- Title: {title}
- URL: {url}
- Content snippet:
{snippet}

VALIDATION RULES:

VALID (answer YES) - article must have at least one of these:
- Mentions {target_domain} or {website}
- Discusses products/services that {company_name} offers
- From investors or PE firms about {company_name}
- Press release about {company_name}'s deals, funding, or partnerships
- Names leadership known to work at {company_name}

INVALID (answer NO):
- About a DIFFERENT company that happens to have a similar name
- Mentions a different website/domain than {target_domain}
- About a company in a completely different industry
- Generic industry news without specific identifiers for {company_name}

KEY: The domain {target_domain} is the definitive identifier. If the article references a different domain, it's the wrong company.

ANSWER:
Line 1: YES or NO
Line 2: Why (cite the specific identifier you found)"""

        try:
            response = llm(validation_prompt, model_type="research", streaming=False).strip()
            lines = response.split('\n', 1)
            decision = lines[0].strip().upper()
            reason = lines[1].strip() if len(lines) > 1 else "No reason provided"

            if decision.startswith("YES"):
                validated_sources[url] = text
                count += 1
                logger.info(f"External source VALIDATED: {url[:60]}... - {reason[:80]}")
            else:
                # Log rejections at INFO level so users can see why sources were skipped
                logger.info(f"External source REJECTED (wrong company): {url[:60]}... - {reason[:80]}")

        except Exception as e:
            # Log validation failures at WARNING level - these are unexpected
            logger.warning(f"Failed to validate external source {url}: {e}")
            # Skip on validation failure - better to miss a source than include wrong company
            continue

        if count >= max_sources:
            break

    return validated_sources


# =============================================================================
# Legacy Compatibility Exports
# =============================================================================

# Import the new tier functions (they return ScrapeResult with raw_content)
from primr.data.scraping import (
    extract_clean_text as _extract_text,
)
from primr.data.scraping import (
    scrape_with_curl_cffi as _scrape_with_curl_cffi_new,
)
from primr.data.scraping import (
    scrape_with_drissionpage as _scrape_with_drissionpage_new,
)
from primr.data.scraping import (
    scrape_with_drissionpage_stealth as _scrape_with_drissionpage_stealth_new,
)
from primr.data.scraping import (
    scrape_with_httpx as _scrape_with_httpx_new,
)
from primr.data.scraping import (
    scrape_with_playwright as _scrape_with_playwright_new,
)
from primr.data.scraping import (
    scrape_with_playwright_aggressive as _scrape_with_playwright_aggressive_new,
)
from primr.data.scraping import (
    scrape_with_requests as _scrape_with_requests_new,
)
from primr.data.scraping import (
    scrape_with_vision as _scrape_with_vision_new,
)


def _wrap_tier_function(tier_fn):
    """Wrap a new-style tier function to return old-style tuple with extracted text."""
    def wrapper(url: str, timeout: int = 30) -> tuple[str | None, str | None]:
        result = tier_fn(url, timeout)
        if result.success and result.raw_content:
            # Extract text from raw content
            text = _extract_text(result.raw_content)
            if text:
                return text, None
            else:
                return None, "Failed to extract text"
        elif result.success and result.extracted_text:
            # Vision tier returns extracted_text directly
            return result.extracted_text, None
        else:
            return None, result.error
    return wrapper


# Wrapped tier functions that return tuple[str | None, str | None]
scrape_with_requests = _wrap_tier_function(_scrape_with_requests_new)
scrape_with_httpx = _wrap_tier_function(_scrape_with_httpx_new)
scrape_with_curl_cffi = _wrap_tier_function(_scrape_with_curl_cffi_new)
scrape_with_playwright = _wrap_tier_function(_scrape_with_playwright_new)
scrape_with_playwright_aggressive = _wrap_tier_function(_scrape_with_playwright_aggressive_new)
scrape_with_drissionpage = _wrap_tier_function(_scrape_with_drissionpage_new)
scrape_with_drissionpage_stealth = _wrap_tier_function(_scrape_with_drissionpage_stealth_new)
scrape_with_vision = _wrap_tier_function(_scrape_with_vision_new)

# Re-export detection functions (with signature adaptation)
from primr.data.scraping import (
    detect_soft_block as _detect_soft_block_new,
)


def detect_soft_block(text: str, url: str = "") -> tuple[bool, str | None]:
    """
    Detect if response is a soft block.

    Wrapper for new detection function that accepts bytes.
    """
    if not text:
        return True, "Empty response"

    # Convert string to bytes for new function
    raw_content = text.encode("utf-8", errors="ignore")
    return _detect_soft_block_new(raw_content, host=url)

# Re-export discovery functions (with signature adaptation)
from primr.data.scraping import (
    fetch_sitemap_links as _fetch_sitemap_links_new,
)
from primr.data.scraping import (
    guess_common_urls as _guess_common_urls_new,
)
from primr.data.scraping import (
    verify_urls_exist as _verify_urls_exist_new,
)


def fetch_sitemap_links(base_url: str) -> set[str]:
    """Fetch links from sitemap."""
    links = _fetch_sitemap_links_new(base_url)
    return {link.url for link in links}


def guess_common_urls(base_url: str) -> set[str]:
    """Generate common business page URLs."""
    links = _guess_common_urls_new(base_url)
    return {link.url for link in links}


def verify_urls_exist(urls: set[str], timeout_per_url: float = 3.0) -> set[str]:
    """Verify which URLs exist."""
    links = [DiscoveredLink(url=url, source="verify") for url in urls]
    verified = _verify_urls_exist_new(links)
    return {link.url for link in verified}


def extract_links_from_html(html_content: str, base_url: str) -> set[str]:
    """Extract links from HTML content."""
    # Convert string to bytes
    if isinstance(html_content, str):
        html_bytes = html_content.encode("utf-8", errors="ignore")
    else:
        html_bytes = html_content
    links = _extract_links_from_html_new(html_bytes, base_url)
    return {link.url for link in links}


# Re-export extract_links_from_homepage
from primr.data.scraping import (
    extract_links_from_homepage as _extract_links_from_homepage_new,
)


def extract_links_from_homepage(base_url: str, company_name: str = "") -> list[str]:
    """Extract links from homepage."""
    links = _extract_links_from_homepage_new(base_url)
    return [link.url for link in links]

# Re-export cache functions
from primr.data.scraping import (
    LRUCache,
)


def get_cached_content(url: str) -> str | None:
    """Get cached content for a URL."""
    orchestrator = get_orchestrator()
    cached = orchestrator.cache.get_extracted(url)
    return cached


def cache_content(url: str, content: str) -> None:
    """Cache content for a URL."""
    orchestrator = get_orchestrator()
    orchestrator.cache.set_extracted(url, content)


def clear_cache(max_age_hours: float | None = None) -> None:
    """Clear the scrape cache (both memory and disk)."""
    global _orchestrator
    if _orchestrator:
        _orchestrator.cache.clear_all()
    else:
        # Clear disk cache even if orchestrator not initialized
        cache = ScrapeCache(cache_dir=str(CACHE_DIR))
        cache.clear_all()


# =============================================================================
# Cleanup
# =============================================================================

def cleanup_browser():
    """Clean up shared browser resources."""
    try:
        from primr.data.scraping.browsers import SharedBrowser
        if SharedBrowser._instance is not None:
            SharedBrowser._instance.close()
    except Exception:
        pass  # atexit — don't crash on shutdown


# Register cleanup
import atexit

atexit.register(cleanup_browser)


# =============================================================================
# Additional Legacy Exports (for test compatibility)
# =============================================================================

from primr.config.config import EXCLUDED_SITES

# Re-export from new modules
from primr.data.scraping import WAF_SIGNATURES
from primr.data.scraping.profiles import HTTP_PROFILES

# Legacy names
SOFT_BLOCK_INDICATORS = [sig[0] for sig in WAF_SIGNATURES]
USER_AGENTS = [p.user_agent for p in HTTP_PROFILES]

# Global cache reference for tests
_SCRAPE_CACHE = LRUCache(max_size=100)


def is_excluded_site(url: str) -> bool:
    """Check if URL is in excluded sites list."""
    return any(excluded in url.lower() for excluded in EXCLUDED_SITES)


# Re-export COMMON_PAGE_PATTERNS
__all__ = [
    "COMMON_PAGE_PATTERNS",
    "SOFT_BLOCK_INDICATORS",
    "USER_AGENTS",
    "cache_content",
    "clear_cache",
    "detect_soft_block",
    "detect_waf_block",
    "extract_clean_text",
    "extract_links_from_homepage",
    "extract_links_from_html",
    "fetch_sitemap_links",
    "fetch_web_content",
    "get_cached_content",
    "guess_common_urls",
    "is_excluded_site",
    "is_valid_url_string",
    "normalize_url",
    "scrape_page",
    "validate_url",
    "verify_urls_exist",
]


def detect_waf_block(html_content: str) -> tuple[bool, str]:
    """
    Detect if we're seeing a WAF/bot protection page.

    Wrapper for new detection function.
    """
    if not html_content:
        return True, "Empty response"

    raw_content = html_content.encode("utf-8", errors="ignore")
    is_blocked, reason = _detect_soft_block_new(raw_content)
    return is_blocked, reason or ""


def extract_clean_text(soup_or_bytes):
    """Extract clean text from BeautifulSoup object or bytes."""
    if hasattr(soup_or_bytes, 'get_text'):
        # It's a BeautifulSoup object
        for tag in soup_or_bytes(["script", "style", "noscript", "meta", "header", "footer",
                         "form", "aside", "nav", "iframe", "svg", "canvas"]):
            tag.extract()
        text = soup_or_bytes.get_text(separator="\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        cleaned = []
        prev_line = None
        for line in lines:
            if line != prev_line:
                cleaned.append(line)
                prev_line = line
        return "\n".join(cleaned)
    else:
        # It's bytes, use new function
        return _extract_text(soup_or_bytes)
