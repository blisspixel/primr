"""
Tiered scraping coordinator with per-host state.

The orchestrator manages:
- Tier escalation on soft blocks
- Per-host, per-tier circuit breaker state
- Rate limiting with try/finally release
- Caching (raw and extracted separately)
- Trace logging
- Success signal checking (uniform across all tiers)
"""

import contextlib
import logging
import os
import random
import re
import time
from urllib.parse import urlparse

from .cache import ScrapeCache
from .config import RateLimitConfig
from .content import (
    detect_content_type,
    extract_clean_text,
    extract_main_content,
    extract_text_from_pdf_via_llm,
    is_quality_content,
)
from .models import (
    Attempt,
    ErrorType,
    HostState,
    PageAccessState,
    ScrapeResult,
    ScrapeTier,
)
from .net import extract_host
from .page_access import classify_page_access
from .rate_limiter import RateLimiter
from .tier_registry import get_available_tiers
from .trace import TraceLogger
from .validation import validate_content

logger = logging.getLogger(__name__)

ADAPTIVE_BROWSER_TIERS = {"playwright", "playwright_aggressive"}

_BOILERPLATE_TEXT_PATTERNS = (
    "skip to content",
    "consent details",
    "this website uses cookies",
    "cookie policy",
    "accept all",
    "show details",
)


def _score_extracted_text(text: str) -> float:
    """Heuristic quality score used to choose the best extraction variant."""
    if not text:
        return 0.0
    length = min(len(text), 20000)
    sentences = len([s for s in text.split(".") if len(s.strip()) > 20])
    lower = text.lower()
    boilerplate_hits = sum(lower.count(p) for p in _BOILERPLATE_TEXT_PATTERNS)
    return (length * 0.02) + (sentences * 8.0) - (boilerplate_hits * 40.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Matches <link rel="canonical" href="..."> in either attribute order
_CANONICAL_RE = re.compile(
    r'<link\s[^>]*?rel=["\']canonical["\'][^>]*?href=["\']([^"\']+)["\']'
    r"|"
    r'<link\s[^>]*?href=["\']([^"\']+)["\'][^>]*?rel=["\']canonical["\']',
    re.IGNORECASE,
)


def _normalise_path(url: str) -> str:
    """Return lower-cased path without trailing slash for comparison."""
    parsed = urlparse(url)
    return parsed.path.rstrip("/").lower()


def _equivalent_paths(path: str) -> set[str]:
    """Return acceptable path variants for canonical/final URL comparison."""
    variants = {path}
    if path.startswith("/fdc/"):
        variants.add(path[4:])
    elif path.startswith("/fdc"):
        variants.add(path[4:] or "/")
    elif path and path != "/":
        variants.add("/fdc" + path)
    return {variant.rstrip("/") or "/" for variant in variants}


def _paths_match(requested_path: str, candidate_path: str) -> bool:
    return bool(_equivalent_paths(requested_path) & _equivalent_paths(candidate_path))


def _detect_wrong_page(
    requested_url: str,
    raw_content: bytes,
    final_url: str | None,
) -> tuple[bool, str | None]:
    """Detect if the server returned a different page than requested.

    Checks the ``<link rel="canonical">`` tag and the final (post-redirect)
    URL against the originally requested URL.  Category pages that redirect
    to a child (e.g. ``/services`` -> ``/services/environmental/home``) or
    that serve blog content in place of the requested page are caught here.

    Returns:
        (is_wrong_page, canonical_or_final_url)
    """
    requested_path = _normalise_path(requested_url)
    if not requested_path:
        return False, None  # homepage — always accept

    # Check canonical tag
    try:
        head = raw_content[:8192].decode("utf-8", errors="ignore")
    except Exception:
        head = ""

    match = _CANONICAL_RE.search(head)
    if match:
        canonical = match.group(1) or match.group(2)
        canonical_path = _normalise_path(canonical)
        if canonical_path and not _paths_match(requested_path, canonical_path):
            return True, canonical

    # Check final URL after redirect
    if final_url:
        final_path = _normalise_path(final_url)
        if final_path and not _paths_match(requested_path, final_path):
            return True, final_url

    return False, None


class ScrapeOrchestrator:
    """
    Coordinates tiered scraping with circuit breaker and rate limiting.

    Features:
    - Tries tiers in order from lightest to heaviest
    - Per-host, per-tier circuit breaker (skips failing tiers)
    - Rate limiting with guaranteed release (try/finally)
    - Caches raw content and extracted text separately
    - Logs all attempts to trace file
    - Applies success signal check uniformly to all tiers
    - Max time per page to avoid hanging on protected sites
    """

    def __init__(
        self,
        tiers: list[ScrapeTier] | None = None,
        cache: ScrapeCache | None = None,
        rate_limiter: RateLimiter | None = None,
        trace_logger: TraceLogger | None = None,
        rate_config: RateLimitConfig | None = None,
        enable_vision: bool = True,
        circuit_breaker_threshold: int = 3,
        delay_between_tiers: tuple = (1.0, 3.0),
        max_page_time: float = 90.0,  # 90s allows multiple tier attempts while being reasonable
        max_consecutive_failures: int = 3,  # Stop after 3 consecutive failures of same type
        use_cache: bool = False,
    ):
        """
        Initialize orchestrator.

        Args:
            tiers: List of tiers to use (default: available tiers)
            cache: Cache instance (default: new ScrapeCache)
            rate_limiter: Rate limiter (default: new RateLimiter)
            trace_logger: Trace logger (optional)
            rate_config: Rate limiting config
            enable_vision: Whether to enable vision tier (default: True - we need the content)
            circuit_breaker_threshold: Failures before skipping tier
            delay_between_tiers: Random delay range between failed tiers
            max_page_time: Max seconds to spend on a single page across all tiers (90s allows multiple attempts)
            max_consecutive_failures: Stop after N consecutive failures of same error type (prevents wasting time)
            use_cache: Whether to use cached content (default: False for fresh data)
        """
        # Use available tiers if not specified
        self.tiers = tiers if tiers is not None else get_available_tiers()

        # Filter out vision tier unless enabled
        if not enable_vision:
            self.tiers = [t for t in self.tiers if t.name != "vision"]

        # Initialize components
        self.cache = cache or ScrapeCache()
        self.rate_limiter = rate_limiter or RateLimiter(rate_config or RateLimitConfig())
        self.trace_logger = trace_logger
        self.use_cache = use_cache

        # Circuit breaker settings
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.delay_between_tiers = delay_between_tiers or (0.5, 1.5)  # Shorter delays
        self.max_page_time = max_page_time
        self.max_consecutive_failures = max_consecutive_failures

        # Per-host state tracking
        self._host_states: dict[str, HostState] = {}

    def _get_host_state(self, host: str) -> HostState:
        """Get or create host state."""
        if host not in self._host_states:
            self._host_states[host] = HostState(host=host)
        return self._host_states[host]

    def _should_skip_tier(self, host: str, tier_name: str) -> bool:
        """Check if tier should be skipped for this host."""
        state = self._get_host_state(host)
        return state.should_skip_tier(tier_name, self.circuit_breaker_threshold)

    def _record_tier_failure(self, host: str, tier_name: str) -> None:
        """Record a tier failure for circuit breaker."""
        state = self._get_host_state(host)
        state.record_tier_failure(tier_name)

    def _mark_host_blocked(self, host: str) -> None:
        """Mark host as hard-blocked."""
        state = self._get_host_state(host)
        state.hard_blocked = True

    def _is_host_blocked(self, host: str) -> bool:
        """Check if host is hard-blocked."""
        state = self._get_host_state(host)
        return state.hard_blocked

    def _random_delay(self) -> None:
        """Add random delay between tier attempts."""
        delay = random.uniform(*self.delay_between_tiers)
        time.sleep(delay)

    @contextlib.contextmanager
    def _browser_execution_env(self, host_state: HostState, tier_name: str, headed: bool = False):
        """Temporarily apply adaptive browser settings for Playwright tiers."""
        if tier_name not in ADAPTIVE_BROWSER_TIERS:
            yield
            return

        force_headed = headed or host_state.browser_headed_preferred
        previous_headed = os.environ.get("PRIMR_BROWSER_HEADED")
        previous_session = os.environ.get("PRIMR_BROWSER_SESSION_MODE")
        try:
            os.environ["PRIMR_BROWSER_SESSION_MODE"] = "persistent"
            if force_headed:
                os.environ["PRIMR_BROWSER_HEADED"] = "1"
            elif previous_headed is None:
                os.environ.pop("PRIMR_BROWSER_HEADED", None)
            yield
        finally:
            if previous_session is None:
                os.environ.pop("PRIMR_BROWSER_SESSION_MODE", None)
            else:
                os.environ["PRIMR_BROWSER_SESSION_MODE"] = previous_session

            if previous_headed is None:
                os.environ.pop("PRIMR_BROWSER_HEADED", None)
            else:
                os.environ["PRIMR_BROWSER_HEADED"] = previous_headed

    def _maybe_retry_browser_tier(
        self,
        host_state: HostState,
        tier: ScrapeTier,
        url: str,
        timeout: float,
        all_attempts: list[Attempt],
        start_time: float,
    ) -> ScrapeResult | None:
        """Retry browser tiers with stronger session settings before escalating away."""
        if tier.name not in ADAPTIVE_BROWSER_TIERS:
            return None
        if host_state.browser_headed_preferred:
            return None
        if host_state.browser_escalations.get(tier.name, 0) >= 1:
            return None

        logger.info("Adaptive browser retry for %s on %s", tier.name, url)
        host_state.browser_escalations[tier.name] = (
            host_state.browser_escalations.get(tier.name, 0) + 1
        )

        try:
            self.rate_limiter.acquire(host_state.host)
            try:
                with self._browser_execution_env(host_state, tier.name, headed=True):
                    retry_result = tier.scrape_fn(url, timeout)
            finally:
                self.rate_limiter.release(host_state.host)
        except Exception as e:
            logger.warning("Adaptive browser retry failed on %s for %s: %s", tier.name, url, e)
            all_attempts.append(
                Attempt(
                    tier=f"{tier.name}:adaptive",
                    success=False,
                    error=str(e),
                    error_type=ErrorType.NETWORK_ERROR,
                    elapsed_ms=(time.time() - start_time) * 1000,
                )
            )
            return None

        if retry_result.attempts:
            adapted_attempts = [
                Attempt(
                    tier=f"{attempt.tier}:adaptive",
                    success=attempt.success,
                    error=attempt.error,
                    error_type=attempt.error_type,
                    elapsed_ms=attempt.elapsed_ms,
                    http_status=attempt.http_status,
                )
                for attempt in retry_result.attempts
            ]
            all_attempts.extend(adapted_attempts)
        else:
            all_attempts.append(
                Attempt(
                    tier=f"{tier.name}:adaptive",
                    success=retry_result.success,
                    error=retry_result.error,
                    error_type=retry_result.error_type,
                    elapsed_ms=retry_result.elapsed_ms,
                    http_status=retry_result.http_status,
                )
            )

        if retry_result.success:
            host_state.browser_headed_preferred = True
        return retry_result

    def scrape_url(self, url: str) -> ScrapeResult:
        """
        Scrape a single URL using tiered approach.

        Flow:
        0. SSRF validation (block private IPs, metadata endpoints)
        1. Check cache
        2. Check if host is hard-blocked
        3. Try each tier in order
        4. For each tier:
           a. Check circuit breaker
           b. Acquire rate limit
           c. Make request
           d. Release rate limit (always, via try/finally)
           e. Check for soft blocks
           f. Check success signal
           g. On success: cache and return
           h. On soft block: record failure, try next tier
           i. On hard block: mark host blocked, stop
        5. Log to trace

        Args:
            url: URL to scrape

        Returns:
            ScrapeResult with all fields populated
        """
        # 0. SSRF validation - block private IPs, cloud metadata endpoints
        from primr.utils.security import is_safe_url

        is_safe, ssrf_error = is_safe_url(url)
        if not is_safe:
            logger.info(f"SSRF blocked: {url} - {ssrf_error}")
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.HARD_BLOCK,
                error=f"URL blocked by SSRF protection: {ssrf_error}",
                tier=None,
                attempts=[],
            )

        host = extract_host(url)
        start_time = time.time()
        all_attempts: list[Attempt] = []

        # 1. Check cache (only if use_cache is enabled)
        if self.use_cache:
            cached_raw = self.cache.get_raw(url)
            if cached_raw is not None:
                logger.debug(f"Cache hit for {url}")

                # Extract text from cached content (use reader mode for cleaner output)
                extracted = extract_main_content(cached_raw)
                validation = validate_content(extracted, url) if extracted else None

                result = ScrapeResult(
                    url=url,
                    success=True,
                    raw_content=cached_raw,
                    extracted_text=extracted,
                    tier="cache",
                    cached=True,
                    content_type="text/html",
                    validation=validation,
                )

                if self.trace_logger:
                    self.trace_logger.log(result)

                return result

        # 2. Check if host is hard-blocked
        if self._is_host_blocked(host):
            result = ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.HARD_BLOCK,
                error="Host is hard-blocked from previous attempts",
                tier=None,
                attempts=all_attempts,
            )

            if self.trace_logger:
                self.trace_logger.log(result)

            return result

        # 3. Try each tier (start with best_tier if known for this host)
        last_result: ScrapeResult | None = None
        host_state = self._get_host_state(host)

        # Reorder tiers to start with best_tier if we know one works for this host
        tiers_to_try = self.tiers
        use_fast_timeout = False
        effective_max_page_time = self.max_page_time

        if host_state.best_tier:
            # Find the best tier and put it first
            best_tier_obj = next((t for t in self.tiers if t.name == host_state.best_tier), None)
            if best_tier_obj:
                # Start with best tier, then fall back to others if needed
                other_tiers = [t for t in self.tiers if t.name != host_state.best_tier]
                tiers_to_try = [best_tier_obj, *other_tiers]
                logger.debug(f"Starting with best_tier {host_state.best_tier} for {host}")

                # Use shorter timeouts when we have a proven working tier
                # If requests normally works in <1s, waiting 15s is wasteful
                use_fast_timeout = True

                # Keep full per-page budget even with sticky tier so hard pages
                # can still escalate to later fallbacks (including vision).
                effective_max_page_time = self.max_page_time

        tier_attempts = 0
        consecutive_failures = 0
        last_error_type = None

        for tier in tiers_to_try:
            # Check max page time - allow sufficient time for quality content
            elapsed_total = time.time() - start_time
            if elapsed_total > effective_max_page_time:
                logger.info(
                    f"Page timeout after {elapsed_total:.1f}s (limit: {effective_max_page_time}s): {url} "
                    f"[tried {tier_attempts} tiers]"
                )
                break

            # SMART STOPPING: If we've had too many consecutive failures of the same type, stop
            # This prevents wasting time when a site is down/blocking all methods
            if consecutive_failures >= self.max_consecutive_failures:
                logger.info(
                    f"Stopping after {consecutive_failures} consecutive {last_error_type} failures for {url}"
                )
                break

            # 3a. Check circuit breaker
            if self._should_skip_tier(host, tier.name):
                logger.debug(f"Skipping tier {tier.name} for {host} (circuit breaker)")
                continue

            tier_attempts += 1

            # Use shorter timeout when we have a proven working tier
            # If requests normally works in <1s, waiting 15s is wasteful
            # BUT: Browser tiers need full timeout for JS rendering and challenge solving
            # Only apply fast timeout to HTTP tiers (requests, httpx, curl_cffi)
            remaining_time = effective_max_page_time - elapsed_total

            # Browser tiers that need full timeout for JS/challenges
            browser_tiers = {
                "playwright",
                "playwright_aggressive",
                "drissionpage",
                "drissionpage_stealth",
                "vision",
            }
            is_browser_tier = tier.name in browser_tiers

            # Apply fast timeout only to HTTP tiers when we have a proven working tier
            if use_fast_timeout and not is_browser_tier:
                effective_timeout = min(tier.timeout, 5.0)
            else:
                effective_timeout = tier.timeout

            effective_timeout = min(effective_timeout, remaining_time)

            if effective_timeout <= 0:
                break  # No time left

            # 3b-d. Acquire rate limit, make request, release (try/finally)
            try:
                self.rate_limiter.acquire(host)

                try:
                    # Make request
                    with self._browser_execution_env(host_state, tier.name):
                        tier_result = tier.scrape_fn(url, effective_timeout)

                    # Record attempt
                    if tier_result.attempts:
                        all_attempts.extend(tier_result.attempts)
                    else:
                        all_attempts.append(
                            Attempt(
                                tier=tier.name,
                                success=tier_result.success,
                                error=tier_result.error,
                                error_type=tier_result.error_type,
                                elapsed_ms=tier_result.elapsed_ms,
                                http_status=tier_result.http_status,
                            )
                        )

                    last_result = tier_result

                finally:
                    # 3d. Always release rate limit
                    self.rate_limiter.release(host)

            except Exception as e:
                # Handle unexpected errors
                logger.warning(f"Tier {tier.name} raised exception: {e}")
                all_attempts.append(
                    Attempt(
                        tier=tier.name,
                        success=False,
                        error=str(e),
                        error_type=ErrorType.NETWORK_ERROR,
                    )
                )
                host_state.record_tier_attempt(tier.name, success=False)

                # Track consecutive failures
                if last_error_type == ErrorType.NETWORK_ERROR:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_error_type = ErrorType.NETWORK_ERROR

                self._random_delay()
                continue

            # Check if request succeeded at network level
            if not tier_result.success:
                # Track consecutive failures
                if tier_result.error_type == last_error_type:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_error_type = tier_result.error_type

                # Check if it's a hard block (stop escalation)
                if tier_result.error_type == ErrorType.HARD_BLOCK:
                    self._mark_host_blocked(host)

                    result = ScrapeResult(
                        url=url,
                        success=False,
                        error_type=ErrorType.HARD_BLOCK,
                        error=tier_result.error or "Hard block detected",
                        blocked_reason=tier_result.blocked_reason,
                        tier=tier.name,
                        attempts=all_attempts,
                        elapsed_ms=(time.time() - start_time) * 1000,
                    )

                    if self.trace_logger:
                        self.trace_logger.log(result)

                    return result

                host_state.record_tier_attempt(tier.name, success=False)
                self._random_delay()
                continue

            # 3e-f. Classify whether transport success produced real content.
            access_assessment = classify_page_access(
                tier_result.raw_content or b"",
                url=url,
                http_status=tier_result.http_status,
                content_type=tier_result.content_type,
                final_url=tier_result.final_url,
            )

            if access_assessment.state == PageAccessState.SOFT_BLOCK:
                block_reason = access_assessment.reason or "Challenge/interstitial detected"
                logger.debug(f"Soft block detected on {tier.name} for {url}: {block_reason}")
                if "hard" in block_reason.lower() or tier_result.error_type == ErrorType.HARD_BLOCK:
                    self._mark_host_blocked(host)
                    result = ScrapeResult(
                        url=url,
                        success=False,
                        error_type=ErrorType.HARD_BLOCK,
                        error=f"Hard block detected: {block_reason}",
                        blocked_reason=block_reason,
                        tier=tier.name,
                        attempts=all_attempts,
                        elapsed_ms=(time.time() - start_time) * 1000,
                        access_assessment=access_assessment,
                    )

                    if self.trace_logger:
                        self.trace_logger.log(result)

                    return result

                retry_result = self._maybe_retry_browser_tier(
                    host_state,
                    tier,
                    url,
                    effective_timeout,
                    all_attempts,
                    start_time,
                )
                if retry_result and retry_result.success:
                    retry_assessment = classify_page_access(
                        retry_result.raw_content or b"",
                        url=url,
                        http_status=retry_result.http_status,
                        content_type=retry_result.content_type,
                        final_url=retry_result.final_url,
                    )
                    if retry_assessment.state == PageAccessState.SUCCESS:
                        tier_result = retry_result
                        access_assessment = retry_assessment
                    else:
                        logger.debug(
                            "Adaptive browser retry still rejected on %s for %s: %s",
                            tier.name,
                            url,
                            retry_assessment.reason,
                        )
                        host_state.browser_headed_preferred = False
                        retry_result = None
                if (
                    retry_result
                    and retry_result.success
                    and access_assessment.state == PageAccessState.SUCCESS
                ):
                    # Continue using the adapted result through the normal success path below.
                    pass
                else:
                    host_state.record_tier_attempt(tier.name, success=False)
                    last_result = ScrapeResult(
                        url=url,
                        success=False,
                        error=f"Soft block detected: {block_reason}",
                        error_type=ErrorType.SOFT_BLOCK,
                        blocked_reason=block_reason,
                        tier=tier.name,
                        elapsed_ms=(time.time() - start_time) * 1000,
                        access_assessment=access_assessment,
                    )
                    error_key = "soft_block"
                    if last_error_type == error_key:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 1
                        last_error_type = error_key
                    self._random_delay()
                    continue

            if access_assessment.state in (PageAccessState.THIN_CONTENT, PageAccessState.UNKNOWN):
                logger.debug(
                    "Access classifier rejected %s on %s for %s: %s",
                    access_assessment.state.value,
                    tier.name,
                    url,
                    access_assessment.reason,
                )
                retry_result = self._maybe_retry_browser_tier(
                    host_state,
                    tier,
                    url,
                    effective_timeout,
                    all_attempts,
                    start_time,
                )
                if retry_result and retry_result.success:
                    retry_assessment = classify_page_access(
                        retry_result.raw_content or b"",
                        url=url,
                        http_status=retry_result.http_status,
                        content_type=retry_result.content_type,
                        final_url=retry_result.final_url,
                    )
                    if retry_assessment.state == PageAccessState.SUCCESS:
                        tier_result = retry_result
                        access_assessment = retry_assessment
                    else:
                        logger.debug(
                            "Adaptive browser retry remained %s on %s for %s",
                            retry_assessment.state.value,
                            tier.name,
                            url,
                        )
                        host_state.browser_headed_preferred = False
                        retry_result = None
                if (
                    retry_result
                    and retry_result.success
                    and access_assessment.state == PageAccessState.SUCCESS
                ):
                    pass
                else:
                    host_state.record_tier_attempt(tier.name, success=False)
                    last_result = ScrapeResult(
                        url=url,
                        success=False,
                        error=access_assessment.reason
                        or "Page loaded without convincing real-content markers",
                        error_type=ErrorType.SUCCESS_SIGNAL_FAILED,
                        tier=tier.name,
                        elapsed_ms=(time.time() - start_time) * 1000,
                        access_assessment=access_assessment,
                    )
                    error_key = access_assessment.state.value
                    if last_error_type == error_key:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 1
                        last_error_type = error_key
                    self._random_delay()
                    continue

            # 3f2. Check for wrong-page (canonical URL mismatch)
            # Some sites redirect category pages to a child or serve a blog
            # post instead of the requested page.  Detect this by comparing
            # the <link rel="canonical"> or final URL with the requested URL.
            if tier_result.raw_content:
                wrong, canonical = _detect_wrong_page(
                    url, tier_result.raw_content, tier_result.final_url
                )
                if wrong:
                    logger.info(
                        f"Wrong page for {url}: canonical={canonical}, final={tier_result.final_url}"
                    )
                    host_state.record_tier_attempt(tier.name, success=False)
                    # Overwrite last_result so the "all tiers failed" block
                    # reports a meaningful error instead of success=True.
                    last_result = ScrapeResult(
                        url=url,
                        success=False,
                        error=f"Wrong page served (canonical={canonical})",
                        error_type=ErrorType.NETWORK_ERROR,
                        tier=tier.name,
                        elapsed_ms=(time.time() - start_time) * 1000,
                    )
                    # Don't retry — other tiers will get the same redirect.
                    break

            # 3g. Tentative success — defer best_tier promotion until after
            # binary content and quality checks (below) confirm usable output.
            consecutive_failures = 0

            # Store cookies if browser tier provided them (for cookie handoff)
            if tier_result.cookies:
                host_state.cookies = tier_result.cookies
                from datetime import datetime

                host_state.last_clearance_ts = datetime.now()

            # Cache raw content (if available - vision tier may only have screenshot)
            if tier_result.raw_content:
                self.cache.set_raw(url, tier_result.raw_content)

            # Extract text - route by content type
            if tier.name == "vision" and tier_result.extracted_text:
                # Vision tier already extracted text via LLM
                extracted = tier_result.extracted_text
            else:
                # Detect content type from header + magic bytes
                detected_type = detect_content_type(
                    tier_result.raw_content or b"",
                    tier_result.content_type,
                )

                if detected_type == "pdf":
                    # Extract text from PDF via LLM (handles charts/tables)
                    # Falls back to PyMuPDF if Gemini unavailable
                    extracted = extract_text_from_pdf_via_llm(tier_result.raw_content) or ""
                    logger.debug(f"PDF extraction for {url}: {len(extracted)} chars")
                elif detected_type in ("html", "text", "json", "xml", "unknown"):
                    # Try multiple extraction strategies and pick highest-quality output.
                    # Some sites fail reader mode but work in clean-text modes (and vice versa).
                    candidates = []
                    reader_text = extract_main_content(tier_result.raw_content)
                    candidates.append(reader_text or "")
                    candidates.append(
                        extract_clean_text(tier_result.raw_content, mode="aggressive") or ""
                    )
                    candidates.append(
                        extract_clean_text(tier_result.raw_content, mode="conservative") or ""
                    )
                    extracted = max(candidates, key=_score_extracted_text)
                else:
                    # Skip truly binary content (images, fonts, etc.)
                    logger.debug(f"Skipping non-text content type '{detected_type}' for {url}")
                    host_state.record_tier_attempt(tier.name, success=False)
                    # Track consecutive failures before continuing
                    error_key = "binary_content"
                    if last_error_type == error_key:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 1
                        last_error_type = error_key
                    continue

            validation = validate_content(extracted, url) if extracted else None

            # Check content quality - if garbage, try next tier unless richer
            # validation says this is a useful structured short page.
            is_quality, quality_reason = is_quality_content(extracted)
            allow_structured_short = bool(
                validation and validation.valid and validation.content_class == "structured_short"
            )
            if not is_quality and not allow_structured_short:
                logger.debug(f"Content quality failed on {tier.name} for {url}: {quality_reason}")
                last_result = ScrapeResult(
                    url=url,
                    success=False,
                    error=f"Content quality failed: {quality_reason}",
                    error_type=ErrorType.PARSE_ERROR,
                    tier=tier.name,
                    elapsed_ms=(time.time() - start_time) * 1000,
                )

                # Keep escalating instead of fast-failing; some sites only yield
                # substantial content at later tiers (especially vision).
                if extracted and 50 < len(extracted) < 200:
                    logger.debug(
                        f"Short content ({len(extracted)} chars) on {tier.name}; continuing escalation"
                    )

                host_state.record_tier_attempt(tier.name, success=False)
                # Track consecutive failures for quality issues
                error_key = "quality_failure"
                if last_error_type == error_key:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 1
                    last_error_type = error_key
                self._random_delay()
                continue
            if allow_structured_short and not is_quality:
                logger.debug(
                    "Accepting structured short page on %s for %s: %s",
                    tier.name,
                    url,
                    validation.reason,
                )

            # Cache extracted text
            if extracted:
                self.cache.set_extracted(url, extracted)

            # Content is confirmed usable — now promote this tier as best
            host_state.best_tier = tier.name
            host_state.record_tier_attempt(tier.name, success=True)

            result = ScrapeResult(
                url=url,
                success=True,
                raw_content=tier_result.raw_content,
                extracted_text=extracted,
                tier=tier.name,
                cached=False,
                http_status=tier_result.http_status,
                content_type=tier_result.content_type,
                final_url=tier_result.final_url,
                elapsed_ms=(time.time() - start_time) * 1000,
                cookies=tier_result.cookies,
                validation=validation,
                access_assessment=access_assessment,
                attempts=all_attempts,
            )

            if self.trace_logger:
                self.trace_logger.log(result)

            return result

        # All tiers failed
        elapsed_ms = (time.time() - start_time) * 1000

        result = ScrapeResult(
            url=url,
            success=False,
            error_type=last_result.error_type if last_result else ErrorType.NETWORK_ERROR,
            error=last_result.error if last_result else "All tiers failed",
            tier=None,
            elapsed_ms=elapsed_ms,
            attempts=all_attempts,
        )

        if self.trace_logger:
            self.trace_logger.log(result)

        return result

    def scrape_urls(
        self,
        urls: list[str],
        max_pages: int | None = None,
    ) -> list[ScrapeResult]:
        """
        Scrape multiple URLs.

        Args:
            urls: List of URLs to scrape
            max_pages: Maximum pages to scrape (default: from rate config)

        Returns:
            List of ScrapeResult for each URL
        """
        if max_pages is None:
            max_pages = 500  # Default from RateLimitConfig

        results = []

        for i, url in enumerate(urls[:max_pages]):
            page_num = i + 1
            total = min(len(urls), max_pages)
            logger.info(f"Scraping {page_num}/{total}: {url}")

            page_start = time.time()
            result = self.scrape_url(url)
            page_secs = time.time() - page_start
            results.append(result)

            # Log progress at INFO so it's always visible
            if result.success:
                logger.info(
                    f"  [{page_secs:.1f}s] OK via {result.tier} "
                    f"({len(result.raw_content or b'')} bytes)"
                )
            else:
                logger.info(f"  [{page_secs:.1f}s] FAIL: {result.error}")

        return results

    def get_host_state(self, host: str) -> HostState | None:
        """Get host state for inspection."""
        return self._host_states.get(host)

    def reset_host_state(self, host: str) -> None:
        """Reset host state (clear circuit breaker)."""
        if host in self._host_states:
            del self._host_states[host]

    def reset_all_host_states(self) -> None:
        """Reset all host states."""
        self._host_states.clear()

    def get_stats(self) -> dict:
        """Get orchestrator statistics."""
        return {
            "tiers": [t.name for t in self.tiers],
            "hosts_tracked": len(self._host_states),
            "hosts_blocked": sum(1 for s in self._host_states.values() if s.hard_blocked),
            "cache_stats": {
                "raw_items": len(self.cache.raw_memory),
                "extracted_items": len(self.cache.extracted_memory),
            },
        }
