"""
Web Scraper - Refactored to use new modular scraping architecture.

This module provides the high-level scraping API used by the rest of Primr.
It wraps the new modular scraping system in primr.data.scraping.
"""

import hashlib
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from primr.config.config import (
    MIN_SCRAPED_CHARS,
    PROJECT_ROOT,
    SCRAPE_PILOT_COUNT,
    SCRAPE_PILOT_MIN_CHARS,
    SCRAPE_PILOT_MIN_SUCCESS_RATE,
)

# Import from new modular scraping system
from primr.data.scraping import (
    COMMON_PAGE_PATTERNS,
    DiscoveredLink,
    ErrorType,
    RateLimitConfig,
    RateLimiter,
    ScrapeCache,
    ScrapeOrchestrator,
    ScrapeResult,
)
from primr.data.scraping import (
    extract_links_from_html as _extract_links_from_html_new,
)
from primr.data.scraping import (
    normalize_url as normalize_url_new,
)
from primr.data.scraping.discovery import is_probably_content_url
from primr.data.scraping.org_profile import classify_organization_type
from primr.data.scraping.tier_registry import get_available_tiers
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("scrape")

# =============================================================================
# Console Output Helpers
# =============================================================================

_USEFUL_SINGLE_SEGMENT_PATHS = {
    "about",
    "team",
    "news",
    "press",
    "blog",
    "careers",
    "jobs",
    "contact",
    "leadership",
    "programs",
    "services",
    "products",
    "solutions",
    "platform",
    "resources",
    "faq",
    "support",
    "help",
    "docs",
    "documentation",
    "ir",
}


def _looks_like_low_signal_wrapper_url(url: str, website: str) -> bool:
    """Drop bare wrapper paths like /acme or /fdc when they mirror the host label."""
    try:
        parsed_url = urlparse(url)
        parsed_site = urlparse(website)
    except ValueError:
        return False

    path_parts = [part for part in parsed_url.path.lower().split("/") if part]
    if len(path_parts) != 1:
        return False

    segment = path_parts[0]
    if segment in _USEFUL_SINGLE_SEGMENT_PATHS or "-" in segment:
        return False

    host_labels = [
        label for label in parsed_site.netloc.lower().replace("www.", "").split(".") if label
    ]
    return segment in host_labels[:2]


def _filter_selected_urls(urls: list[str], website: str) -> list[str]:
    """Drop obvious non-content URLs before they count toward the scrape set."""
    filtered: list[str] = []
    homepage_normalized = normalize_url(website)
    for url in urls:
        normalized = normalize_url(url)
        if normalized == homepage_normalized:
            logger.debug("Dropping homepage self-link from scrape set: %s", url)
            continue
        if not is_probably_content_url(url):
            logger.debug("Dropping non-content URL from scrape set: %s", url)
            continue
        if _looks_like_low_signal_wrapper_url(url, website):
            logger.debug("Dropping low-signal wrapper URL from scrape set: %s", url)
            continue
        filtered.append(url)
    return filtered


def evaluate_scrape_pilot(
    pilot_success: int,
    pilot_attempts: int,
    pilot_chars_total: int,
) -> dict[str, float | int | bool]:
    """
    Evaluate whether the pilot sample is too weak to trust a full crawl.

    Relief is intentionally granted when a sparse pilot still yields a few
    content-rich pages. That pattern is common on bot-protected or uneven sites
    where the crawl is still worth continuing with heavier external research.
    """
    success_rate = pilot_success / max(pilot_attempts, 1)
    avg_chars = int(pilot_chars_total / max(pilot_success, 1)) if pilot_success else 0
    high_success_relief_rate = max(SCRAPE_PILOT_MIN_SUCCESS_RATE, 0.90)
    low_content_with_low_success = (
        avg_chars < SCRAPE_PILOT_MIN_CHARS and success_rate < high_success_relief_rate
    )

    # Permit a sparse pilot when the pages that did land are substantively
    # rich AND the success rate is at least half the configured floor.
    # Without the success-rate floor, an attacker-controlled site could
    # serve 3 rich pages and 7+ failures and still drive primr into the
    # full concurrent crawl phase, multiplying outbound work past the
    # documented pilot abort. Half the configured floor (0.35 at default)
    # preserves the legitimate "patchy site with a few good pages" case
    # while rejecting 3/50-style adversarial samples.
    rich_content_relief_floor = max(SCRAPE_PILOT_MIN_SUCCESS_RATE / 2, 0.30)
    rich_content_relief = (
        success_rate >= rich_content_relief_floor
        and avg_chars >= max(SCRAPE_PILOT_MIN_CHARS * 3, 2000)
        and (
            pilot_success >= 3
            or (pilot_success >= 2 and pilot_chars_total >= max(SCRAPE_PILOT_MIN_CHARS * 6, 4000))
        )
    )
    useful_corpus_relief = pilot_success >= 4 and pilot_chars_total >= max(MIN_SCRAPED_CHARS, 4000)

    should_abort = False
    if not (rich_content_relief or useful_corpus_relief) and (
        success_rate < SCRAPE_PILOT_MIN_SUCCESS_RATE or low_content_with_low_success
    ):
        should_abort = True

    return {
        "success_rate": success_rate,
        "avg_chars": avg_chars,
        "low_content_with_low_success": low_content_with_low_success,
        "rich_content_relief": rich_content_relief,
        "useful_corpus_relief": useful_corpus_relief,
        "should_abort": should_abort,
    }


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


# =============================================================================
# Fallback content helper (used when origin is fully blocked)
# =============================================================================


def _collect_fallback_content(
    company_name: str,
    website: str,
    raw_folder: str | None = None,
    append_trace=None,
) -> dict[str, str]:
    """
    Gather content from public-data fallbacks when the origin host is blocked.

    Fires Wayback / subdomain / EDGAR / Wikipedia in parallel and returns a
    url -> text dict compatible with fetch_web_content's output shape.

    Also writes each recovered page to raw_folder for downstream inspection,
    so the rest of the pipeline sees the same artifacts it would see from a
    normal scrape.
    """
    from primr.data.fallback_sources import gather_fallback_content

    # Build a short list of likely deep pages on the origin to try through
    # Wayback — the homepage alone rarely captures "About/History" content.
    # Generic paths only; locale prefixes and product paths are too site-
    # specific to hard-code.
    wayback_candidates = [
        website.rstrip("/") + path
        for path in (
            "/",
            "/about",
            "/about-us",
            "/our-story",
            "/company",
            "/company/overview",
            "/history",
            "/our-history",
            "/leadership",
            "/sustainability",
            "/responsibility",
            "/investors",
            "/investor-relations",
        )
    ]

    # Grok surrogate is opt-in via env — it costs tokens. Default on because
    # it catches pages Wayback doesn't have a snapshot for. Set
    # PRIMR_DISABLE_GROK_SURROGATE=1 to skip.
    grok_urls: list[str] | None = None
    if os.getenv("PRIMR_DISABLE_GROK_SURROGATE", "0").lower() not in ("1", "true", "yes"):
        # Prioritize high-value paths: about, history, leadership — where Grok's
        # synthesis-from-public-sources is most valuable. Cap at 3 to control
        # token spend.
        grok_urls = [
            website.rstrip("/") + path for path in ("/about", "/our-story", "/leadership")
        ][:3]

    pages = gather_fallback_content(
        company_name=company_name,
        website=website,
        wayback_urls=wayback_candidates,
        grok_surrogate_urls=grok_urls,
        timeout_per_source=90.0,
    )

    if not pages:
        return {}

    result: dict[str, str] = {}
    for idx, page in enumerate(pages, start=1):
        text = page.content.strip()
        if not text:
            continue
        result[page.url] = text

        if append_trace is not None:
            append_trace(
                "FALLBACK_OK",
                page.url,
                f"source={page.source} chars={len(text)} title={(page.title or '')[:60]}",
            )

        if raw_folder:
            try:
                safe_source = page.source.replace("/", "_")
                raw_file = os.path.join(raw_folder, f"fb_{idx:02d}_{safe_source}.txt")
                with open(raw_file, "w", encoding="utf-8") as f:
                    f.write(f"URL: {page.url}\n")
                    f.write(f"Source: {page.source}\n")
                    f.write(f"Title: {page.title or ''}\n")
                    f.write(f"Length: {len(text)} chars\n")
                    f.write("-" * 60 + "\n\n")
                    f.write(text)
            except Exception as e:
                logger.warning("Failed to save fallback raw file: %s", e)

    return result


# Global orchestrator instance (lazy initialized)
_orchestrator: ScrapeOrchestrator | None = None


_external_orchestrator: ScrapeOrchestrator | None = None


def get_external_orchestrator(
    enable_vision: bool = False,
) -> ScrapeOrchestrator:
    """Orchestrator used for external / validation source scrapes.

    External sources are web-search results we're assessing, not the primary
    company target. They should never trigger a visible-browser popup — if a
    search hit is behind Kasada we just skip it and move on. This orchestrator
    omits the Patchright stealth tier entirely to guarantee no popup happens
    during discovery/validation passes.
    """
    global _external_orchestrator
    if _external_orchestrator is not None:
        return _external_orchestrator

    tiers = get_available_tiers()
    enable_drission = os.getenv("PRIMR_ENABLE_DRISSION", "0").lower() in {"1", "true", "yes"}
    excluded = {"patchright"}
    if not enable_drission:
        excluded.update({"drissionpage", "drissionpage_stealth"})
    tiers = [t for t in tiers if t.name not in excluded]

    _external_orchestrator = ScrapeOrchestrator(
        tiers=tiers,
        cache=ScrapeCache(cache_dir=str(CACHE_DIR)),
        rate_limiter=RateLimiter(RateLimitConfig(per_host_requests_per_minute=30)),
        enable_vision=enable_vision,
        max_page_time=30.0,  # external sources: don't spend long per URL
        delay_between_tiers=(0.3, 1.0),
        use_cache=False,
        circuit_breaker_threshold=3,
    )
    return _external_orchestrator


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
            rate_limiter=RateLimiter(
                RateLimitConfig(
                    per_host_requests_per_minute=30,  # Tokens refill every 2s; actual scrapes take 2-15s
                    base_delay_seconds=0.5,  # Reduced jitter when rate-limited (0-0.5s vs 0-1.5s)
                )
            ),
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
        parsed = urlparse(url)
    return url if parsed.scheme in ("http", "https") else None


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
    company_name: str | None,
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
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .scraping import (
        BoilerplateFilter,
        PageAccessState,
        classify_page_access,
        extract_main_content,
        extract_structured_content,
    )

    # Normalize so downstream helpers (validation prompts, fallback fan-out)
    # never have to handle the None case themselves.
    company_name = company_name or ""

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
            logger.warning(f"Failed to save raw scrape: {e}")

    # Create raw scrapes folder if working_folder provided
    raw_folder = None
    trace_file = None
    if working_folder:
        raw_folder = os.path.join(working_folder, "_raw_scrapes")
        os.makedirs(raw_folder, exist_ok=True)
        trace_file = os.path.join(raw_folder, "_scrape_trace.log")

    def _load_resume_selected_links() -> list[str]:
        """Load previously selected links from _selected_links.txt if present."""
        if not raw_folder:
            return []
        selected_links_file = os.path.join(raw_folder, "_selected_links.txt")
        if not os.path.exists(selected_links_file):
            return []
        links: list[str] = []
        try:
            with open(selected_links_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ". http" in line:
                        links.append(line.split(". ", 1)[1].strip())
                    elif line.startswith(("http://", "https://")):
                        links.append(line)
        except Exception as e:
            logger.debug(f"Failed loading selected links resume manifest: {e}")
            return []
        return links

    def _load_existing_raw_texts() -> dict[str, str]:
        """Load previously saved raw scrape text outputs for resume behavior."""
        if not raw_folder:
            return {}
        existing: dict[str, str] = {}
        try:
            for name in os.listdir(raw_folder):
                if not name.endswith(".txt"):
                    continue
                if name.startswith("_"):
                    continue
                file_path = os.path.join(raw_folder, name)
                try:
                    with open(file_path, encoding="utf-8") as f:
                        text = f.read()
                    url = ""
                    url_marker = "URL:"
                    sep_marker = "-" * 60
                    for line in text.splitlines()[:6]:
                        if line.startswith(url_marker):
                            url = line.replace(url_marker, "", 1).strip()
                            break
                    if not url:
                        continue
                    if sep_marker in text:
                        body = text.split(sep_marker, 1)[1].strip()
                    else:
                        body = text.strip()
                    if body:
                        existing[normalize_url(url)] = body
                except Exception as e:
                    logger.debug("Failed parsing raw scrape file %s: %s", name, e)
                    continue
        except Exception as e:
            logger.debug(f"Failed loading existing raw scrapes: {e}")
        return existing

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
            logger.warning(f"Failed to write scrape trace: {e}")

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

    def _structured_to_clean_text(structured, raw_html: bytes) -> str:
        """Recover usable page text even when block rendering yields nothing."""
        plain_text = structured.to_plain_text(include_cta=False).strip()
        if plain_text:
            return plain_text

        cleaned_text = (structured.text or "").strip()
        if cleaned_text:
            return cleaned_text

        raw_text = (structured.raw_text or "").strip()
        if raw_text:
            return raw_text

        return extract_main_content(raw_html).strip()

    def _is_recoverable_selected_url(url: str, website: str) -> bool:
        """Allow high-value first-party recovery URLs, including PDFs."""
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        normalized = normalize_url(url)
        if normalized == normalize_url(website):
            return False
        if _looks_like_low_signal_wrapper_url(url, website):
            return False

        path_lower = (parsed.path or "").lower()
        if path_lower.endswith(".pdf"):
            return True

        return is_probably_content_url(url)

    def _discover_first_party_recovery_urls(
        base_url: str,
        organization_type: str,
        limit: int,
    ) -> list[str]:
        """Probe first-party deep paths when the homepage is blocked."""
        from .scraping.discovery import discover_links
        from .scraping.net import is_in_scope

        recovery_links = discover_links(
            base_url=base_url,
            homepage_html=None,
            verify_guessed=True,
            min_links_before_sitemap=20,
            organization_type=organization_type,
        )

        # First-party recovery legitimately includes subdomains (investor.*,
        # ir.*, newsroom.*), so scope with is_in_scope rather than the
        # exact-host is_same_domain.
        filtered_links = [
            link
            for link in recovery_links
            if is_in_scope(link.url, base_url) and _is_recoverable_selected_url(link.url, base_url)
        ]
        return [link.url for link in filtered_links[:limit]]

    domain = urlparse(website).netloc
    orchestrator = get_orchestrator(enable_vision=use_vision)
    resume_selected_urls_prefetch = _load_resume_selected_links()
    resumed_text_pages_prefetch = _load_existing_raw_texts()

    # Step 1: Get homepage with browser (modern sites need JS rendering)
    console.status(f"Scanning {domain}...")
    homepage_recovery_reason: str | None = None
    homepage_access_ok = False

    # Check if this host has a remembered rate-limit cooldown. If so, skip
    # live scraping entirely and go straight to public fallbacks — no point
    # burning 60+ seconds on a host we know is 429'ing us.
    from primr.data.scraping.rate_limit_state import get_rate_limit

    rl_entry = get_rate_limit(domain)
    if rl_entry is not None:
        mins = rl_entry.remaining_seconds() // 60
        secs = rl_entry.remaining_seconds() % 60
        time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
        console.warn(
            f"{domain} rate-limited for {time_str} ({rl_entry.reason}) — "
            "skipping live scrape, using public fallbacks"
        )
        _append_trace(
            "RATE_LIMIT_SKIP",
            website,
            f"remaining={rl_entry.remaining_seconds()}s reason={rl_entry.reason}",
        )
        fallback_content = _collect_fallback_content(
            company_name=company_name,
            website=website,
            raw_folder=raw_folder,
            append_trace=_append_trace,
        )
        if fallback_content:
            console.done(f"Recovered {len(fallback_content)} page(s) from public fallbacks")
        return fallback_content

    # Route homepage through the orchestrator so it gets the same adaptive
    # browser retry/escalation behavior as every subsequent page.
    result = orchestrator.scrape_url(website)
    homepage_tier = result.tier if result.success else None

    if result.success and result.raw_content:
        expected_markers: list[str] = []
        if company_name:
            expected_markers.extend(
                token.lower()
                for token in re.split(r"[^a-zA-Z0-9]+", company_name)
                if len(token) >= 4
            )
        host_tokens = [
            token
            for token in urlparse(website).netloc.lower().replace("www.", "").split(".")
            if len(token) >= 4
        ]
        expected_markers.extend(host_tokens[:2])

        homepage_assessment = classify_page_access(
            result.raw_content,
            url=website,
            final_url=getattr(result, "final_url", website),
            http_status=getattr(result, "http_status", None),
            content_type=getattr(result, "content_type", None),
            expected_markers=expected_markers,
        )
        if homepage_assessment.state != PageAccessState.SUCCESS:
            homepage_recovery_reason = homepage_assessment.reason or "Homepage blocked"
            _append_trace(
                "BLOCK",
                website,
                "homepage via orchestrator rejected: "
                f"{homepage_assessment.state.value} ({homepage_assessment.reason or 'inconclusive'})",
            )
            result = ScrapeResult(
                url=website,
                success=False,
                error=homepage_assessment.reason or "Homepage blocked",
                error_type=(
                    ErrorType.SOFT_BLOCK
                    if homepage_assessment.state == PageAccessState.SOFT_BLOCK
                    else ErrorType.SUCCESS_SIGNAL_FAILED
                ),
                tier=result.tier,
                access_assessment=homepage_assessment,
            )
            homepage_tier = None
        else:
            homepage_access_ok = True
    else:
        access_assessment = getattr(result, "access_assessment", None)
        if access_assessment and getattr(access_assessment, "reason", None):
            homepage_recovery_reason = access_assessment.reason

    if not result.success or not result.raw_content:
        homepage_norm = normalize_url(website)
        if resume_selected_urls_prefetch and homepage_norm in resumed_text_pages_prefetch:
            homepage_html = b""
            homepage_tier = "resume-local"
            homepage_access_ok = False
            _append_trace(
                "RESUME", website, "using local homepage content after live fetch failure"
            )
        else:
            homepage_html = b""
            homepage_tier = None
            homepage_access_ok = False
            homepage_recovery_reason = (
                homepage_recovery_reason or result.error or "Homepage blocked"
            )
            _append_trace(
                "RECOVER",
                website,
                f"homepage unavailable, trying first-party fallback: {homepage_recovery_reason}",
            )
    else:
        homepage_html = result.raw_content
        _append_trace("OK", website, f"homepage via {homepage_tier or result.tier}")
        homepage_access_ok = True

    homepage_text = extract_main_content(homepage_html) if homepage_html else ""
    organization_profile = classify_organization_type(
        website,
        homepage_text=homepage_text,
        company_name=company_name,
    )
    organization_type = organization_profile.organization_type

    if working_folder:
        run_state_path = os.path.join(working_folder, "_run_state.json")
        state = {}
        if os.path.exists(run_state_path):
            try:
                import json

                with open(run_state_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    state = loaded
            except Exception as e:
                logger.debug("Failed to load run state for org type persistence: %s", e)
                state = {}
        state["organization_type"] = organization_type
        state["organization_type_confidence"] = organization_profile.confidence
        state["organization_type_signals"] = list(organization_profile.signals)
        try:
            import json

            with open(run_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist organization type: {e}")

    # Tell orchestrator what tier worked for this host (sticky tier)
    # This prevents wasteful tier escalation on subsequent pages
    if homepage_access_ok and homepage_tier and homepage_tier != "resume-local":
        from .scraping.net import extract_host

        host = extract_host(website)
        host_state = orchestrator._get_host_state(host)
        host_state.best_tier = homepage_tier
        logger.debug(f"Set best_tier={homepage_tier} for {host} based on homepage success")

    resume_selected_urls = resume_selected_urls_prefetch
    if resume_selected_urls:
        selected_urls = _filter_selected_urls(resume_selected_urls, website)
        total_found = len(selected_urls)
        in_scope_count = len(selected_urls)
        _append_trace(
            "RESUME", website, f"loaded {len(selected_urls)} selected links from manifest"
        )
    else:
        if homepage_access_ok:
            # Step 2: Discover ALL links using full discovery pipeline
            # This includes: homepage links, common URL guessing, sitemap fallback
            from .scraping.discovery import discover_links
            from .scraping.net import is_in_scope

            all_links = discover_links(
                base_url=website,
                homepage_html=homepage_html,
                verify_guessed=True,  # Verify guessed URLs exist
                min_links_before_sitemap=20,  # Check sitemap if < 20 links
                organization_type=organization_type,
            )

            # Filter to in-scope links (same domain + subdomains). Use
            # is_in_scope, not is_same_domain: the latter was narrowed to
            # exact-host equality, which silently dropped docs./investors./
            # careers. subdomains and shrank report coverage.
            in_scope_links = [link for link in all_links if is_in_scope(link.url, website)]
            in_scope_count = len(in_scope_links)

            # Use LLM to intelligently select the most valuable pages for company research
            # The LLM decides how many pages are worth scraping - no artificial limits
            # Falls back to heuristic scoring if LLM fails
            from primr.core.research_agent import select_links_with_llm

            console.status(f"Selecting from {len(in_scope_links)} pages...")
            selected_urls = select_links_with_llm(
                in_scope_links,
                company_name=company_name,
                website=website,
                max_links=max_pages or 100,  # Let LLM decide, but cap at 100 for sanity
                organization_type=organization_type,
            )
            selected_urls = _filter_selected_urls(selected_urls, website)
            console.clear_line()
            total_found = len(selected_urls)
        else:
            console.status("Homepage blocked - probing first-party fallback paths...")
            selected_urls = _discover_first_party_recovery_urls(
                website,
                organization_type=organization_type,
                limit=max_pages or 100,
            )
            console.clear_line()
            total_found = len(selected_urls)
            in_scope_count = total_found
            _append_trace(
                "RECOVER",
                website,
                f"first-party recovery candidates={total_found} reason={homepage_recovery_reason or 'homepage blocked'}",
            )

    homepage_slot = 1 if homepage_access_ok else 0
    # Apply max_pages limit (reserve slot for homepage only when we have it)
    if max_pages and max_pages < total_found + homepage_slot:
        allowed_pages = max_pages - homepage_slot
        pages_to_scrape = selected_urls[:allowed_pages]
        console.found(f"{in_scope_count} links {console._arrow} {max_pages} selected")
    elif total_found == 0:
        pages_to_scrape = []
        if homepage_access_ok:
            console.found("1 page (homepage only)")
        else:
            console.found("0 recovery pages found")
    else:
        pages_to_scrape = selected_urls
        if homepage_access_ok:
            console.found(f"{in_scope_count} links {console._arrow} {total_found} selected")
        else:
            console.found(f"{in_scope_count} recovery links selected")

    if not homepage_access_ok and not pages_to_scrape:
        console.clear_line()
        console.fail(f"Could not access {domain}")
        console.muted("  Routing around block via Wayback / subdomains / EDGAR / Wikipedia...")
        _append_trace(
            "FALLBACK",
            website,
            f"origin blocked ({homepage_recovery_reason or 'unknown'}) — firing public-data fallbacks",
        )

        fallback_content = _collect_fallback_content(
            company_name=company_name,
            website=website,
            raw_folder=raw_folder,
            append_trace=_append_trace,
        )
        if fallback_content:
            console.done(f"Recovered {len(fallback_content)} page(s) from public fallbacks")
            return fallback_content

        console.muted("  No public fallbacks returned content either")
        return {}

    # Persist selected URL set for reproducibility and debugging.
    if raw_folder:
        selected_links_file = os.path.join(raw_folder, "_selected_links.txt")
        try:
            with open(selected_links_file, "w", encoding="utf-8") as f:
                f.write(f"# Selected links for {company_name}\n")
                f.write(f"# Website: {website}\n")
                f.write(f"# Organization type: {organization_type}\n")
                homepage_note = "excluding homepage" if homepage_access_ok else "recovery mode only"
                f.write(f"# Selected count: {len(pages_to_scrape)} ({homepage_note})\n\n")
                for idx, link in enumerate(pages_to_scrape, start=1):
                    f.write(f"{idx:03d}. {link}\n")
        except Exception as e:
            logger.warning(f"Failed to save selected links manifest: {e}")

    # Flush stdout to ensure progress shows immediately
    import sys

    sys.stdout.flush()

    # Step 3: Scrape pages (homepage first, then discovered links)
    scrape_start = time.time()
    raw_pages: list[tuple[str, bytes]] = []  # List of (url, raw_html_bytes)
    structured_cache = {}  # normalized_url -> StructuredContent (reused in Phase 2)
    scraped_results = {}  # url -> ScrapeResult
    success_count = 0
    write_executor = ThreadPoolExecutor(max_workers=1) if raw_folder else None
    resumed_text_pages = resumed_text_pages_prefetch
    if resumed_text_pages:
        _append_trace("RESUME", website, f"loaded {len(resumed_text_pages)} existing local pages")

    # Add homepage as first result when we have live HTML.
    homepage_normalized = normalize_url(website)
    if homepage_access_ok and homepage_html:
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
        if raw_folder and write_executor is not None:
            try:
                structured = extract_structured_content(homepage_html, website)
                structured_cache[homepage_normalized] = structured
                raw_file = os.path.join(raw_folder, "homepage.txt")
                write_executor.submit(_write_raw_file, raw_file, website, result.tier, structured)
            except Exception as e:
                logger.warning(f"Failed to save homepage raw scrape: {e}")

    resumed_non_home = [u for u in resumed_text_pages if u != homepage_normalized]
    if homepage_access_ok and homepage_normalized in resumed_text_pages:
        success_count = max(success_count, 1)
    if resumed_non_home:
        success_count += len(resumed_non_home)
    total = len(pages_to_scrape) + (1 if homepage_access_ok else 0)
    page_times = []  # Track per-page durations for ETA
    dup_count = 0  # Pages rejected as duplicate content
    attempted_urls: set[str] = {homepage_normalized} if homepage_access_ok else set()
    attempted_urls.update(resumed_text_pages.keys())

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
    if homepage_access_ok and homepage_html:
        try:
            _hp_text = extract_main_content(homepage_html)
            if _hp_text and _hp_text.strip():
                _seen_content_hashes.add(
                    hashlib.md5(_hp_text.encode(), usedforsecurity=False).hexdigest()
                )
        except Exception as e:
            logger.warning("Homepage content hash failed: %s", e)

    # Show initial progress immediately
    initial_completed = 1 if homepage_access_ok else 0
    if pages_to_scrape:
        initial_label = "homepage" if homepage_access_ok else "recovery"
        console.scrape_progress(
            initial_completed, total, initial_label, scrape_start, ok_count=success_count
        )
        logger.info(
            "Starting to scrape %s pages (%s)",
            total,
            (
                f"homepage + {len(pages_to_scrape)} discovered"
                if homepage_access_ok
                else f"{len(pages_to_scrape)} recovery candidates"
            ),
        )

    def _scrape_one_page(page_url, orchestrator):
        """Scrape a single page in a worker thread. Returns (result, elapsed)."""
        page_start = time.time()
        result = orchestrator.scrape_url(page_url)
        page_elapsed = time.time() - page_start
        return result, page_elapsed

    def _process_result(page_url, normalized, result, page_elapsed, page_index):
        """Process a scrape result, updating shared state. Returns True if pilot abort needed."""
        nonlocal success_count, dup_count, pilot_attempts, pilot_success, pilot_chars_total

        path = urlparse(page_url).path or "/"
        path_display = path[:30] + "..." if len(path) > 30 else path

        page_times.append(page_elapsed)

        if not result.success:
            logger.debug(f"Failed {page_url}: {result.error}")
            _append_trace("FAIL", page_url, _failure_detail(result))
        elif result.success and result.raw_content:
            _text_for_hash = result.extracted_text or ""
            _content_hash = (
                hashlib.md5(_text_for_hash.encode(), usedforsecurity=False).hexdigest()
                if _text_for_hash
                else ""
            )
            if _content_hash and _content_hash in _seen_content_hashes:
                dup_count += 1
                logger.info(
                    f"Duplicate content for {page_url} (matches previously scraped page) — skipping"
                )
                _append_trace("DUP", page_url, f"tier={result.tier}")
                if pilot_attempts < pilot_count:
                    pilot_success += 1
                    pilot_attempts += 1
                return False
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

            if raw_folder and write_executor is not None:
                try:
                    structured = extract_structured_content(result.raw_content, page_url)
                    structured_cache[normalized] = structured
                    safe_name = path.replace("/", "_").strip("_") or "page"
                    safe_name = safe_name[:50]
                    raw_file = os.path.join(raw_folder, f"{safe_name}.txt")
                    write_executor.submit(
                        _write_raw_file, raw_file, page_url, result.tier, structured
                    )
                except Exception as e:
                    logger.warning(f"Failed to save raw scrape: {e}")
        else:
            logger.warning(f"Failed to scrape {page_url}: {result.error}")
            _append_trace("FAIL", page_url, _failure_detail(result))

        if pilot_attempts < pilot_count:
            pilot_attempts += 1
            if pilot_attempts == pilot_count:
                pilot_eval = evaluate_scrape_pilot(
                    pilot_success=pilot_success,
                    pilot_attempts=pilot_attempts,
                    pilot_chars_total=pilot_chars_total,
                )
                success_rate = float(pilot_eval["success_rate"])
                avg_chars = int(pilot_eval["avg_chars"])
                _append_trace(
                    "PILOT",
                    website,
                    (
                        f"attempts={pilot_attempts}, success={pilot_success}, "
                        f"success_rate={success_rate:.2f}, avg_chars={avg_chars}"
                    ),
                )
                if pilot_eval["rich_content_relief"]:
                    logger.info(
                        f"Pilot success rate low ({success_rate:.0%}) but content "
                        f"is rich ({avg_chars} avg chars from {pilot_success} pages) "
                        f"— proceeding"
                    )
                elif pilot_eval["should_abort"]:
                    console.clear_line()
                    console.fail(
                        "Pilot scrape validation failed "
                        f"({pilot_success}/{pilot_attempts} ok, avg {avg_chars} chars)"
                    )
                    console.muted(
                        "  Defensive stop: initial sample quality too low to trust full crawl"
                    )
                    console.muted("  Re-run with --skip-scrape-validation to continue anyway")
                    console.muted(
                        "  Or tune SCRAPE_PILOT_* env vars (ex: SCRAPE_PILOT_MIN_CHARS=700)"
                    )
                    return True  # signal pilot abort

        # Update progress
        completed = len(scraped_results)
        avg_time = sum(page_times) / len(page_times) if page_times else 0
        remaining_pages = total - completed
        eta_seconds = avg_time * remaining_pages if remaining_pages > 0 else 0
        console.scrape_progress(
            completed,
            total,
            path_display,
            scrape_start,
            eta_seconds=eta_seconds,
            ok_count=success_count,
        )
        return False

    try:
        # Phase A: Pilot — scrape first N pages sequentially for quality gate
        pilot_pages = pages_to_scrape[:pilot_count]
        post_pilot_pages = pages_to_scrape[pilot_count:]
        pilot_abort = False

        for i, page_url in enumerate(pilot_pages):
            normalized = normalize_url(page_url)
            if normalized in scraped_results or normalized in attempted_urls:
                continue
            attempted_urls.add(normalized)

            display_index = i + 2 if homepage_access_ok else i + 1
            logger.debug(f"Scraping page {display_index}/{total}: {page_url}")
            _append_trace("TRY", page_url, f"attempt {display_index}/{total}")
            path = urlparse(page_url).path or "/"
            path_display = path[:30] + "..." if len(path) > 30 else path
            console.scrape_progress(
                display_index, total, path_display, scrape_start, ok_count=success_count
            )

            result, page_elapsed = _scrape_one_page(page_url, orchestrator)
            if _process_result(page_url, normalized, result, page_elapsed, i):
                pilot_abort = True
                break

        if pilot_abort:
            return {}

        # Phase B: Concurrent scraping — remaining pages with 3 workers
        if post_pilot_pages:
            with ThreadPoolExecutor(max_workers=3) as scrape_pool:
                futures = {}
                for i, page_url in enumerate(post_pilot_pages, start=pilot_count):
                    normalized = normalize_url(page_url)
                    if normalized in scraped_results or normalized in attempted_urls:
                        continue
                    attempted_urls.add(normalized)

                    display_index = i + 2 if homepage_access_ok else i + 1
                    logger.debug(f"Scraping page {display_index}/{total}: {page_url}")
                    _append_trace("TRY", page_url, f"attempt {display_index}/{total}")

                    future = scrape_pool.submit(_scrape_one_page, page_url, orchestrator)
                    futures[future] = (page_url, normalized, i)

                for future in as_completed(futures):
                    page_url, normalized, i = futures[future]
                    try:
                        result, page_elapsed = future.result()
                    except Exception as e:
                        logger.warning(f"Scrape worker error for {page_url}: {e}")
                        _append_trace("FAIL", page_url, f"worker error: {e}")
                        continue
                    _process_result(page_url, normalized, result, page_elapsed, i)

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
            # Prefer structured plain text, but recover from empty block output.
            clean_text = _structured_to_clean_text(structured, raw_html)
            if clean_text.strip():
                scraped_content[url] = clean_text
    else:
        # Not enough pages for boilerplate learning, use direct extraction
        scraped_content = {}
        for url, raw_html in raw_pages:
            structured = structured_cache.get(url) or extract_structured_content(raw_html, url)
            clean_text = _structured_to_clean_text(structured, raw_html)
            if clean_text.strip():
                scraped_content[url] = clean_text

    # Merge previously saved local pages for reboot/crash resume.
    # Freshly scraped pages win if both exist.
    for url, text in resumed_text_pages.items():
        if url not in scraped_content and text.strip():
            scraped_content[url] = text

    # Defensive fallback: if the origin produced zero usable pages, fan out
    # to public fallback sources. Running on "zero pages" is the safe gate:
    # any successful scrape (even a single thin homepage or one recovery
    # page) is trusted as-is. Fallbacks only replace nothing.
    if len(scraped_content) == 0:
        logger.info("Origin produced no content — supplementing with public fallbacks")
        _append_trace(
            "FALLBACK",
            website,
            "origin produced 0 pages — firing public fallbacks",
        )
        supplementary = _collect_fallback_content(
            company_name=company_name,
            website=website,
            raw_folder=raw_folder,
            append_trace=_append_trace,
        )
        for url, text in supplementary.items():
            scraped_content[url] = text
        if supplementary:
            console.done(f"Added {len(supplementary)} page(s) from public fallbacks")

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
    # External sources use a no-popup orchestrator — these are discovery
    # candidates, not worth prompting the user to solve Kasada challenges for.
    orchestrator = get_external_orchestrator()
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
    company_name: str | None,
    website: str | None,
    max_sources: int = 2,
    working_folder: str | None = None,
) -> dict[str, str]:
    """
    Scrape external sources with LLM validation to ensure they're about the right company.

    This prevents including content from similarly-named but unrelated companies
    (e.g., a SaaS vendor and a senior-living operator that share the same trade name).

    The LLM is instructed to be DEFENSIVE - assume it's wrong unless clearly right.
    But it's also smart about mergers, subsidiaries, investors, and name changes.

    Args:
        search_results: List of search result dicts with 'url' key
        company_name: Name of the target company. ``None`` is tolerated and
            treated as an empty string for prompt-context purposes.
        website: Target company's website (for context). ``None`` is tolerated
            and treated as an empty string.
        max_sources: Maximum validated sources to return
        working_folder: If provided, save raw scrapes to _raw_scrapes subfolder

    Returns:
        Dict mapping URL -> extracted text (only for validated sources)
    """
    import os

    from primr.ai.llm import llm

    # Normalize None inputs so prompt-building f-strings don't render
    # the literal string "None" into the validation prompt.
    company_name = company_name or ""
    website = website or ""

    # Use the popup-free orchestrator for external validation sources.
    orchestrator = get_external_orchestrator()
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
                logger.warning(f"Failed to save external raw scrape: {e}")

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
            lines = response.split("\n", 1)
            decision = lines[0].strip().upper()
            reason = lines[1].strip() if len(lines) > 1 else "No reason provided"

            if decision.startswith("YES"):
                validated_sources[url] = text
                count += 1
                logger.info(f"External source VALIDATED: {url[:60]}... - {reason[:80]}")
            else:
                # Log rejections at INFO level so users can see why sources were skipped
                logger.info(
                    f"External source REJECTED (wrong company): {url[:60]}... - {reason[:80]}"
                )

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
    """Clean up shared browser resources.

    Runs the actual close() in a daemon thread with a bounded join so a
    stuck Playwright Node.js subprocess (e.g., when an abandoned validation
    worker is mid-CDP-call) can't keep the interpreter from exiting. After
    the timeout, we drop on the floor — the OS will reap the orphan
    Chromium/Node processes when the parent exits.
    """
    import threading

    def _do_close() -> None:
        try:
            from primr.data.scraping.browsers import SharedBrowser

            SharedBrowser.get().close()
        except Exception:
            pass  # atexit — don't crash on shutdown

    t = threading.Thread(target=_do_close, name="primr-cleanup-browser", daemon=True)
    t.start()
    t.join(timeout=5.0)


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
    if hasattr(soup_or_bytes, "get_text"):
        # It's a BeautifulSoup object
        for tag in soup_or_bytes(
            [
                "script",
                "style",
                "noscript",
                "meta",
                "header",
                "footer",
                "form",
                "aside",
                "nav",
                "iframe",
                "svg",
                "canvas",
            ]
        ):
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
