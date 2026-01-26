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

import logging
import random
import time
from typing import List, Optional, Dict

from .cache import ScrapeCache
from .config import RateLimitConfig
from .content import extract_clean_text, extract_main_content, is_quality_content
from .detection import detect_soft_block, check_success_signal
from .models import (
    Attempt,
    ErrorType,
    HostState,
    ScrapeResult,
    ScrapeTier,
    ValidationResult,
)
from .net import extract_host
from .rate_limiter import RateLimiter, NoOpRateLimiter
from .tier_registry import DEFAULT_TIERS, get_available_tiers
from .trace import TraceLogger
from .validation import validate_content


logger = logging.getLogger(__name__)


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
        tiers: Optional[List[ScrapeTier]] = None,
        cache: Optional[ScrapeCache] = None,
        rate_limiter: Optional[RateLimiter] = None,
        trace_logger: Optional[TraceLogger] = None,
        rate_config: Optional[RateLimitConfig] = None,
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
        self._host_states: Dict[str, HostState] = {}
    
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
    
    def scrape_url(self, url: str) -> ScrapeResult:
        """
        Scrape a single URL using tiered approach.
        
        Flow:
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
        host = extract_host(url)
        start_time = time.time()
        all_attempts: List[Attempt] = []
        
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
        last_result: Optional[ScrapeResult] = None
        host_state = self._get_host_state(host)
        
        # Reorder tiers to start with best_tier if we know one works for this host
        tiers_to_try = self.tiers
        use_fast_timeout = False
        
        if host_state.best_tier:
            # Find the best tier and put it first
            best_tier_obj = next((t for t in self.tiers if t.name == host_state.best_tier), None)
            if best_tier_obj:
                # Start with best tier, then fall back to others if needed
                other_tiers = [t for t in self.tiers if t.name != host_state.best_tier]
                tiers_to_try = [best_tier_obj] + other_tiers
                logger.debug(f"Starting with best_tier {host_state.best_tier} for {host}")
                
                # Use shorter timeouts when we have a proven working tier
                # If requests normally works in <1s, waiting 15s is wasteful
                use_fast_timeout = True
        
        tier_attempts = 0
        consecutive_failures = 0
        last_error_type = None
        
        for tier in tiers_to_try:
            # Check max page time - allow sufficient time for quality content
            elapsed_total = time.time() - start_time
            if elapsed_total > self.max_page_time:
                logger.debug(
                    f"Page timeout after {elapsed_total:.1f}s (limit: {self.max_page_time}s): {url}\n"
                    f"  Tried {tier_attempts} tiers: {[t.name for t in tiers_to_try[:tier_attempts]]}\n"
                    f"  Last result: {last_result.error if last_result else 'none'}"
                )
                break
            
            # SMART STOPPING: If we've had too many consecutive failures of the same type, stop
            # This prevents wasting time when a site is down/blocking all methods
            if consecutive_failures >= self.max_consecutive_failures:
                logger.debug(
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
            remaining_time = self.max_page_time - elapsed_total
            
            # Browser tiers that need full timeout for JS/challenges
            browser_tiers = {"playwright", "playwright_aggressive", "drissionpage", "drissionpage_stealth", "vision"}
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
                    tier_result = tier.scrape_fn(url, effective_timeout)
                    
                    # Record attempt
                    if tier_result.attempts:
                        all_attempts.extend(tier_result.attempts)
                    else:
                        all_attempts.append(Attempt(
                            tier=tier.name,
                            success=tier_result.success,
                            error=tier_result.error,
                            error_type=tier_result.error_type,
                            elapsed_ms=tier_result.elapsed_ms,
                            http_status=tier_result.http_status,
                        ))
                    
                    last_result = tier_result
                    
                finally:
                    # 3d. Always release rate limit
                    self.rate_limiter.release(host)
                
            except Exception as e:
                # Handle unexpected errors
                logger.warning(f"Tier {tier.name} raised exception: {e}")
                all_attempts.append(Attempt(
                    tier=tier.name,
                    success=False,
                    error=str(e),
                    error_type=ErrorType.NETWORK_ERROR,
                ))
                host_state.record_tier_attempt(tier.name, success=False)
                
                # Track consecutive failures
                if ErrorType.NETWORK_ERROR == last_error_type:
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
            
            # 3e. Check for soft blocks
            is_blocked, block_reason = detect_soft_block(
                tier_result.raw_content,
                http_status=tier_result.http_status,
                content_type=tier_result.content_type,
                final_url=tier_result.final_url,
                host=host,
            )
            
            if is_blocked:
                logger.debug(f"Soft block detected on {tier.name} for {url}: {block_reason}")
                # Check if it's a hard block
                if "hard" in (block_reason or "").lower() or tier_result.error_type == ErrorType.HARD_BLOCK:
                    # 3i. Hard block - stop escalation
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
                    )
                    
                    if self.trace_logger:
                        self.trace_logger.log(result)
                    
                    return result
                
                # 3h. Soft block - record failure, try next tier
                logger.debug(f"Soft block on {tier.name}: {block_reason}")
                host_state.record_tier_attempt(tier.name, success=False)
                self._random_delay()
                continue
            
            # 3f. Check success signal
            if not check_success_signal(tier_result.raw_content, tier_result.http_status):
                logger.debug(f"Success signal failed on {tier.name} for {url}")
                host_state.record_tier_attempt(tier.name, success=False)
                self._random_delay()
                continue
            
            # 3g. Success! Cache and return
            # Record this tier as best for this host (sticky tier optimization)
            host_state.best_tier = tier.name
            host_state.record_tier_attempt(tier.name, success=True)
            
            # Reset consecutive failures on success
            consecutive_failures = 0
            
            # Store cookies if browser tier provided them (for cookie handoff)
            if tier_result.cookies:
                host_state.cookies = tier_result.cookies
                from datetime import datetime
                host_state.last_clearance_ts = datetime.now()
            
            # Cache raw content (if available - vision tier may only have screenshot)
            if tier_result.raw_content:
                self.cache.set_raw(url, tier_result.raw_content)
            
            # Extract text - vision tier provides extracted_text directly
            if tier.name == "vision" and tier_result.extracted_text:
                # Vision tier already extracted text via LLM
                extracted = tier_result.extracted_text
            else:
                # Use reader mode for cleaner output from HTML
                extracted = extract_main_content(tier_result.raw_content)
            
            # Check content quality - if garbage, try next tier
            is_quality, quality_reason = is_quality_content(extracted)
            if not is_quality:
                logger.debug(f"Content quality failed on {tier.name} for {url}: {quality_reason}")
                
                # FAST FAIL: If we got HTML but content is too short (50-199 chars),
                # the page is likely a stub/redirect, not a scraping issue.
                # Don't waste time trying other tiers.
                if extracted and 50 < len(extracted) < 200:
                    logger.debug(f"Fast fail: Page has content but too short ({len(extracted)} chars)")
                    break  # Exit tier loop, return failure
                
                host_state.record_tier_attempt(tier.name, success=False)
                self._random_delay()
                continue
            
            # Cache extracted text
            if extracted:
                self.cache.set_extracted(url, extracted)
            
            # Validate content (informational only)
            validation = validate_content(extracted, url) if extracted else None
            
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
        urls: List[str],
        max_pages: Optional[int] = None,
    ) -> List[ScrapeResult]:
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
            logger.debug(f"Scraping {i+1}/{min(len(urls), max_pages)}: {url}")
            
            result = self.scrape_url(url)
            results.append(result)
            
            # Log progress
            if result.success:
                logger.debug(f"  Success: {result.tier}, {len(result.raw_content or b'')} bytes")
            else:
                logger.debug(f"  Failed: {result.error}")
        
        return results
    
    def get_host_state(self, host: str) -> Optional[HostState]:
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
