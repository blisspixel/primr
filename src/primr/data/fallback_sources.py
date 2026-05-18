"""
First-party and public-data fallback sources for blocked hosts.

When a primary host is bot-protected and the orchestrator can't reach real
content (Kasada, Akamai, etc.), these fallbacks harvest the same company's
information from places that aren't under the same WAF:

- **Subdomain probe**: many companies expose investor.*, ir.*, newsroom.*,
  press.* on a different stack (Q4 Inc., Business Wire, etc.) that isn't
  bot-protected even when the main shop/marketing site is.
- **SEC EDGAR**: public US companies must file 10-K / 10-Q / 8-K. These are
  freely downloadable and contain comprehensive About/History/Risk/Products
  sections written by the company itself.
- **Wikipedia**: most known companies have a synthesized history + products
  + leadership article, served via REST API with no bot protection.

All fallback sources are fail-open: missing data from one source does not
prevent the others from contributing. The caller fans them out in parallel
and merges whatever comes back.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# =============================================================================
# Shared HTTP helper
# =============================================================================


def _http_get(
    url: str,
    timeout: float = 15.0,
    headers: dict | None = None,
    params: dict | None = None,
) -> tuple[int | None, bytes | None, str | None]:
    """Plain httpx GET with follow_redirects. Returns (status, body, final_url).

    SSRF protection: validates the initial URL and the final URL after
    redirects against the central SSRF blocklist. The fallback fan-out
    builds URLs from arbitrary subdomains of a user-supplied host, and the
    raw response is later merged into scrape artifacts — without this
    check, attacker-controlled DNS or HTTP redirects could read internal
    services. Mirror any changes here in
    ``hiring_signals.py::_http_get`` and
    ``scraping/stealth_browser.py``.
    """
    from primr.utils.security import is_safe_url, validate_final_url_after_redirect

    safe, reason = is_safe_url(url)
    if not safe:
        logger.info("fallback: blocked outbound request to %s (%s)", url, reason)
        return None, None, None

    try:
        import httpx

        base_headers = {
            "User-Agent": "primr/1.0 (+https://github.com/blisspixel/primr; research fetcher)",
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if headers:
            base_headers.update(headers)

        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=base_headers,
        ) as client:
            resp = client.get(url, params=params)
            final_url = str(resp.url)
            safe_final, reason = validate_final_url_after_redirect(final_url)
            if not safe_final:
                logger.info(
                    "fallback: dropped response from %s — final URL %s blocked (%s)",
                    url,
                    final_url,
                    reason,
                )
                return None, None, None
            return resp.status_code, resp.content, final_url
    except Exception as e:
        logger.debug("fallback HTTP get failed for %s: %s", url, e)
        return None, None, None


# =============================================================================
# Result types
# =============================================================================


@dataclass
class FallbackPage:
    """A page of content recovered from a fallback source."""

    url: str
    source: str  # "subdomain" | "edgar" | "wikipedia" | "wayback"
    content: str  # extracted plain text
    raw_html: bytes | None = None
    title: str | None = None
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Subdomain probing
# =============================================================================

# Subdomains that typically host company intelligence, in priority order.
# Investor-relations subdomains are most valuable because they contain
# quarterly filings, leadership bios, and strategic messaging.
CANDIDATE_SUBDOMAINS = [
    "investor",
    "investors",
    "ir",
    "corporate",
    "corp",
    "about",
    "newsroom",
    "news",
    "press",
    "media",
    "careers",
    "jobs",
    "sustainability",
    "esg",
    "impact",
]

# Pages commonly hosted on investor / corporate subdomains.
SUBDOMAIN_PROBE_PATHS = [
    "/",
    "/overview/default.aspx",  # Q4 Inc. IR sites (common CMS)
    "/overview",
    "/company-overview",
    "/about",
    "/about-us",
    "/leadership",
    "/board-of-directors",
    "/news",
    "/news/default.aspx",
    "/press-releases",
    "/financials",
    "/annual-reports",
]


def _resolve_subdomain(host: str) -> bool:
    """Check whether a subdomain resolves via DNS (cheap pre-filter)."""
    try:
        socket.gethostbyname(host)
        return True
    except (OSError, socket.gaierror):
        return False


def discover_live_subdomains(base_host: str, max_workers: int = 6) -> list[str]:
    """
    Probe CANDIDATE_SUBDOMAINS against base_host, return hosts that resolve.

    Example: base_host="example.com" -> ["investor.example.com", ...] if that
    subdomain resolves.
    """
    # Strip any leading "www." from base host
    apex = base_host.lower().removeprefix("www.").strip()
    candidates = [f"{sub}.{apex}" for sub in CANDIDATE_SUBDOMAINS]

    live: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_resolve_subdomain, h): h for h in candidates}
        for f in as_completed(futures):
            host = futures[f]
            try:
                if f.result():
                    live.append(host)
            except Exception:
                continue

    # Preserve priority order of CANDIDATE_SUBDOMAINS
    prio = {sub: i for i, sub in enumerate(CANDIDATE_SUBDOMAINS)}
    live.sort(key=lambda h: prio.get(h.split(".", 1)[0], 999))
    return live


def fetch_subdomain_content(
    base_host: str,
    max_pages: int = 6,
    per_page_timeout: float = 12.0,
) -> list[FallbackPage]:
    """
    Discover live subdomains and fetch priority pages from each.

    Many corporate sites host their main marketing/shop site behind a WAF
    (Kasada, Akamai) but leave investor relations, newsroom, and careers
    subdomains on a separate, lightly-protected stack. Plain HTTP usually
    works there.
    """
    from primr.data.scraping.content import extract_main_content, get_page_title

    subdomains = discover_live_subdomains(base_host)
    if not subdomains:
        logger.info("No live subdomains discovered for %s", base_host)
        return []

    logger.info("Discovered live subdomains for %s: %s", base_host, subdomains)

    pages: list[FallbackPage] = []
    seen_content_hashes: set[int] = set()

    for sub_host in subdomains:
        if len(pages) >= max_pages:
            break

        for path in SUBDOMAIN_PROBE_PATHS:
            if len(pages) >= max_pages:
                break

            url = f"https://{sub_host}{path}"
            status, body, final_url = _http_get(url, timeout=per_page_timeout)
            if status != 200 or not body or len(body) < 2000:
                continue

            # Cheap challenge-shell check
            head = body[:4000].decode("utf-8", errors="ignore").lower()
            if any(m in head for m in ("kpsdk", "ips.js", "_abck", "cf_chl_opt")):
                continue

            extracted = extract_main_content(body) or ""
            if len(extracted) < 400:
                continue

            content_hash = hash(extracted[:500])
            if content_hash in seen_content_hashes:
                continue
            seen_content_hashes.add(content_hash)

            pages.append(
                FallbackPage(
                    url=final_url or url,
                    source="subdomain",
                    content=extracted,
                    raw_html=body,
                    title=get_page_title(body),
                    metadata={"subdomain": sub_host, "path": path},
                )
            )
            logger.info("Subdomain fallback: fetched %s (%d chars)", url, len(extracted))

    return pages


# =============================================================================
# SEC EDGAR
# =============================================================================

EDGAR_TICKER_INDEX = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# Cache the ticker index in-memory for the process lifetime.
_ticker_index_cache: dict | None = None


def _sec_headers(for_url: str | None = None) -> dict:
    """Build SEC-compliant request headers.

    SEC requires a User-Agent identifying the requester with contact info
    (see https://www.sec.gov/os/accessing-edgar-data). Without it EDGAR
    returns 403. Contact email can be overridden via PRIMR_SEC_CONTACT env.
    """
    import os

    contact = os.getenv("PRIMR_SEC_CONTACT", "admin@primr.local").strip()
    ua = f"primr research tool ({contact})"
    headers = {
        "User-Agent": ua,
        "Accept-Encoding": "gzip, deflate",
    }
    if for_url:
        host = urlparse(for_url).netloc
        if host:
            headers["Host"] = host
    return headers


def _load_edgar_ticker_index(timeout: float = 20.0) -> dict:
    """Load SEC's company_tickers.json (CIK / ticker / name map).

    Returns a dict keyed by lowercased company name -> {cik_str, ticker, title}.
    SEC requires a descriptive User-Agent; we send a contact URL.
    """
    global _ticker_index_cache
    if _ticker_index_cache is not None:
        return _ticker_index_cache

    status, body, _ = _http_get(
        EDGAR_TICKER_INDEX,
        timeout=timeout,
        headers=_sec_headers(EDGAR_TICKER_INDEX),
    )
    if status != 200 or not body:
        _ticker_index_cache = {}
        return _ticker_index_cache

    try:
        raw = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        _ticker_index_cache = {}
        return _ticker_index_cache

    # Format is { "0": {"cik_str": N, "ticker": "X", "title": "NAME"}, ... }
    index: dict = {}
    for entry in raw.values():
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        index[title.lower()] = entry

    _ticker_index_cache = index
    logger.info("Loaded EDGAR ticker index: %d companies", len(index))
    return index


def _normalize_company_name(name: str) -> str:
    """Strip common suffixes for fuzzy matching (Inc, Corp, Ltd, etc)."""
    lowered = name.lower().strip()
    # Remove punctuation
    lowered = re.sub(r"[.,]", "", lowered)
    # Remove trailing corporate suffixes
    for suffix in (
        " incorporated",
        " corporation",
        " company",
        " holdings",
        " inc",
        " corp",
        " co",
        " ltd",
        " llc",
        " plc",
        " sa",
        " nv",
        " ag",
    ):
        if lowered.endswith(suffix):
            lowered = lowered[: -len(suffix)].strip()
    return lowered


def find_edgar_cik(company_name: str) -> tuple[str, str, str] | None:
    """
    Resolve a company name to (CIK-padded-10, ticker, canonical_name).

    Does a normalized substring match against SEC's ticker index.
    """
    index = _load_edgar_ticker_index()
    if not index:
        return None

    target = _normalize_company_name(company_name)
    if not target:
        return None

    # Try exact normalized match first
    for name, entry in index.items():
        if _normalize_company_name(name) == target:
            cik = str(entry["cik_str"]).zfill(10)
            return cik, entry.get("ticker", ""), entry.get("title", "")

    # Fall back to substring
    for name, entry in index.items():
        norm = _normalize_company_name(name)
        if target in norm or norm in target:
            if abs(len(target) - len(norm)) <= 10:  # avoid wildly different matches
                cik = str(entry["cik_str"]).zfill(10)
                return cik, entry.get("ticker", ""), entry.get("title", "")

    return None


def fetch_latest_edgar_filing(
    cik: str,
    form_types: tuple[str, ...] = ("10-K", "20-F", "10-Q"),
    timeout: float = 30.0,
) -> tuple[str, bytes] | None:
    """
    Fetch the most recent filing of one of the given form types.

    Returns (filing_url, body_bytes) on success. Returns None if no matching
    filing exists or the fetch failed.
    """
    submissions_url = f"{EDGAR_SUBMISSIONS_BASE}/CIK{cik}.json"
    status, body, _ = _http_get(
        submissions_url,
        timeout=timeout,
        headers=_sec_headers(submissions_url),
    )
    if status != 200 or not body:
        return None

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None

    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form", [])
    accession = recent.get("accessionNumber", [])
    primary_doc = recent.get("primaryDocument", [])

    for form, acc, doc in zip(forms, accession, primary_doc, strict=False):
        if form not in form_types:
            continue
        # Build filing URL: /Archives/edgar/data/<CIK>/<ACCESSION_no_dashes>/<primary_doc>
        acc_clean = acc.replace("-", "")
        filing_url = f"{EDGAR_ARCHIVES_BASE}/{int(cik)}/{acc_clean}/{doc}"
        fetch_status, fetch_body, _ = _http_get(
            filing_url,
            timeout=timeout,
            headers=_sec_headers(filing_url),
        )
        if fetch_status == 200 and fetch_body:
            return filing_url, fetch_body

    return None


def fetch_edgar_content(company_name: str) -> list[FallbackPage]:
    """
    Look up a company on EDGAR and fetch its most recent annual report.

    Returns a list containing a single FallbackPage with the filing text, or
    an empty list if the company isn't a US public filer or has no matching
    filings.
    """
    from primr.data.scraping.content import extract_main_content

    resolved = find_edgar_cik(company_name)
    if not resolved:
        logger.info("EDGAR: no CIK match for %r", company_name)
        return []

    cik, ticker, canonical = resolved
    logger.info("EDGAR: matched %r -> CIK %s (%s, %s)", company_name, cik, ticker, canonical)

    filing = fetch_latest_edgar_filing(cik)
    if not filing:
        logger.info("EDGAR: no annual filing found for CIK %s", cik)
        return []

    filing_url, body = filing
    text = extract_main_content(body) or ""
    if len(text) < 2000:
        logger.info("EDGAR: filing too thin (%d chars) — skipping", len(text))
        return []

    # 10-Ks are very long — cap extracted text at 50k chars for downstream budget.
    if len(text) > 50_000:
        text = text[:50_000] + "\n\n[... 10-K truncated for length ...]"

    return [
        FallbackPage(
            url=filing_url,
            source="edgar",
            content=text,
            raw_html=body,
            title=f"{canonical} ({ticker}) — SEC filing",
            metadata={"cik": cik, "ticker": ticker, "canonical_name": canonical},
        )
    ]


# =============================================================================
# Wikipedia
# =============================================================================

WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_EXTRACT = "https://en.wikipedia.org/w/api.php"


def find_wikipedia_title(company_name: str, timeout: float = 15.0) -> str | None:
    """Find the best-matching Wikipedia article title for a company."""
    status, body, _ = _http_get(
        WIKIPEDIA_SEARCH,
        timeout=timeout,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{company_name} company",
            "srlimit": 5,
            "format": "json",
        },
    )
    if status != 200 or not body:
        return None

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None

    results = (data.get("query") or {}).get("search") or []
    if not results:
        return None

    normalized_target = _normalize_company_name(company_name)
    target_tokens = {t for t in normalized_target.split() if len(t) >= 3}

    if target_tokens:
        for hit in results:
            title = hit.get("title") or ""
            if not title:
                continue
            title_norm = _normalize_company_name(title)
            title_tokens = set(title_norm.split())
            # Prefer titles that share at least one meaningful token with the
            # target name (cheap way to reject unrelated top hits).
            if target_tokens & title_tokens:
                return title

    # Otherwise the top hit
    return results[0].get("title")


def fetch_wikipedia_content(company_name: str, timeout: float = 20.0) -> list[FallbackPage]:
    """
    Fetch the Wikipedia article for a company as plain text.

    Returns a list with one FallbackPage, or empty if no article found.
    """
    title = find_wikipedia_title(company_name, timeout=timeout)
    if not title:
        logger.info("Wikipedia: no article for %r", company_name)
        return []

    # Use the action API to get a plain-text extract of the full article.
    status, body, _ = _http_get(
        WIKIPEDIA_EXTRACT,
        timeout=timeout,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "exlimit": 1,
            "titles": title,
            "format": "json",
            "redirects": 1,
        },
    )
    if status != 200 or not body:
        return []

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return []

    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        extract = page.get("extract") or ""
        if len(extract) < 500:
            continue
        article_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        logger.info("Wikipedia: fetched %r (%d chars)", title, len(extract))
        return [
            FallbackPage(
                url=article_url,
                source="wikipedia",
                content=extract,
                raw_html=None,
                title=title,
                metadata={"pageid": page.get("pageid")},
            )
        ]

    return []


# =============================================================================
# Wayback bridge (reuses the scrape tier function, returns FallbackPage)
# =============================================================================


def fetch_grok_surrogates(
    urls: list[str],
    company_name: str,
    max_pages: int = 3,
    total_deadline: float = 120.0,
) -> list[FallbackPage]:
    """Ask Grok to browse/summarize a list of URLs and return the summaries.

    Used when the origin is bot-protected and the URL ISN'T in Wayback either.
    Grok fetches via its own infrastructure and synthesizes from public
    sources when direct fetch fails, citing each fact. Returned FallbackPage
    entries are tagged ``source="grok"`` so downstream pipelines know they are
    LLM synthesis with citations, not first-party scraped text.
    """
    try:
        from primr.ai.grok_client import grok_browse_and_summarize
    except ImportError:
        logger.info("Grok client not available; skipping grok surrogate")
        return []

    if not urls:
        return []

    pages: list[FallbackPage] = []
    start = time.time()
    context_hint = f"The target company is {company_name}." if company_name else None

    # Serial (not parallel) — Grok Agent Tools calls are expensive enough
    # that we care more about early-stop than wall time.
    for url in urls:
        if len(pages) >= max_pages:
            break
        if time.time() - start >= total_deadline:
            logger.info("Grok surrogate: total deadline reached, collected %d page(s)", len(pages))
            break

        remaining_budget = max(20.0, total_deadline - (time.time() - start))
        try:
            result = grok_browse_and_summarize(
                url, context=context_hint, timeout=min(90.0, remaining_budget)
            )
        except Exception as e:
            logger.warning("grok surrogate failed for %s: %s", url, e)
            continue

        if not result or not result.get("text"):
            continue

        text = result["text"].strip()
        if len(text) < 250:
            continue

        pages.append(
            FallbackPage(
                url=url,
                source="grok",
                content=text,
                raw_html=None,
                title=f"Grok synthesis: {url}",
                metadata={
                    "citations": result.get("citations") or [],
                    "tool_calls": result.get("tool_calls", 0),
                    "synthesis": True,
                },
            )
        )

    logger.info(
        "Grok surrogate: %d summary page(s) from %d URL(s) in %.1fs",
        len(pages),
        len(urls),
        time.time() - start,
    )
    return pages


def fetch_wayback_pages(
    urls: list[str],
    per_url_timeout: float = 30.0,
    max_pages: int = 4,
    total_deadline: float = 75.0,
) -> list[FallbackPage]:
    """Run the Wayback tier over a list of URLs in parallel.

    Caps the total time (total_deadline) so slow CDX queries can't starve
    the parent fan-out, and stops after max_pages successful retrievals
    to avoid burning time once we have enough content.
    """
    from primr.data.scraping.content import extract_main_content, get_page_title
    from primr.data.scraping.wayback import scrape_with_wayback

    if not urls:
        return []

    pages: list[FallbackPage] = []
    start = time.time()

    # Parallelize across up to 4 URLs at a time; Wayback tolerates concurrent
    # CDX queries from a single client.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(scrape_with_wayback, url, per_url_timeout): url for url in urls}

        try:
            remaining = max(1.0, total_deadline - (time.time() - start))
            for f in as_completed(futures, timeout=remaining):
                url = futures[f]
                try:
                    r = f.result(timeout=0)
                except Exception as e:
                    logger.debug("Wayback worker failed for %s: %s", url, e)
                    continue
                if not r.success or not r.raw_content:
                    continue
                text = extract_main_content(r.raw_content) or ""
                if len(text) < 400:
                    continue
                pages.append(
                    FallbackPage(
                        url=r.final_url or url,
                        source="wayback",
                        content=text,
                        raw_html=r.raw_content,
                        title=get_page_title(r.raw_content),
                        metadata={"requested_url": url},
                    )
                )
                if len(pages) >= max_pages:
                    break
        except TimeoutError:
            logger.info(
                "Wayback: total deadline (%ss) reached, collected %d page(s)",
                int(total_deadline),
                len(pages),
            )
        finally:
            for f in futures:
                if not f.done():
                    f.cancel()

    logger.info(
        "Wayback fetched %d page(s) from %d URL(s) in %.1fs",
        len(pages),
        len(urls),
        time.time() - start,
    )
    return pages


# =============================================================================
# Parallel fan-out
# =============================================================================


def gather_fallback_content(
    company_name: str,
    website: str,
    wayback_urls: list[str] | None = None,
    grok_surrogate_urls: list[str] | None = None,
    timeout_per_source: float = 60.0,
) -> list[FallbackPage]:
    """
    Fire all fallback sources in parallel and merge whatever comes back.

    Sources:
    - subdomain probe (fast, ~5-15s per live subdomain)
    - SEC EDGAR (public companies only, ~10-30s including filing fetch)
    - Wikipedia (almost always available for known companies, ~5s)
    - Wayback replays for a provided list of blocked URLs (slow, ~30-60s)
    - Grok synthesis for URLs that have no Wayback capture either
      (opt-in; expensive but catches pages that nothing else can)

    Fails are silent — each source logs its own outcome. The caller should
    always check `len(pages) > 0` before using the result.
    """
    base_host = urlparse(website).netloc or website
    base_host = base_host.lower().removeprefix("www.")

    logger.info(
        "Gathering fallback content for %r (host=%s) — subdomain/EDGAR/Wikipedia/Wayback in parallel",
        company_name,
        base_host,
    )
    start = time.time()

    results: list[FallbackPage] = []

    pool = ThreadPoolExecutor(max_workers=5)
    try:
        futures = {
            pool.submit(fetch_subdomain_content, base_host): "subdomain",
            pool.submit(fetch_edgar_content, company_name): "edgar",
            pool.submit(fetch_wikipedia_content, company_name): "wikipedia",
        }
        if wayback_urls:
            futures[pool.submit(fetch_wayback_pages, wayback_urls)] = "wayback"
        if grok_surrogate_urls:
            futures[pool.submit(fetch_grok_surrogates, grok_surrogate_urls, company_name)] = "grok"

        # Cap the total gather — some sources (Wayback over slow CDX) can hang.
        # Any futures that aren't done when we hit the deadline are abandoned.
        deadline = time.time() + timeout_per_source * 2
        try:
            for f in as_completed(futures, timeout=max(1.0, deadline - time.time())):
                source = futures[f]
                try:
                    pages = f.result()
                    logger.info("Fallback source %s returned %d page(s)", source, len(pages))
                    results.extend(pages)
                except Exception as e:
                    logger.warning("Fallback source %s raised: %s", source, e)
        except TimeoutError:
            # Collect whatever already finished; abandon the rest.
            for f, source in futures.items():
                if f.done():
                    try:
                        pages = f.result(timeout=0)
                        if pages:
                            logger.info(
                                "Fallback source %s returned %d page(s) (collected after timeout)",
                                source,
                                len(pages),
                            )
                            results.extend(pages)
                    except Exception as e:
                        logger.warning("Fallback source %s raised: %s", source, e)
                else:
                    logger.warning(
                        "Fallback source %s still running past deadline — abandoning",
                        source,
                    )
                    f.cancel()
    finally:
        from primr.utils.async_utils import detach_running_workers

        pool.shutdown(wait=False, cancel_futures=True)
        detach_running_workers(pool)

    elapsed = time.time() - start
    logger.info("Fallback gather done: %d total pages in %.1fs", len(results), elapsed)
    return results
