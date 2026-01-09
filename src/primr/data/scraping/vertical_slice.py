"""
Vertical Slice Checkpoint - Minimal orchestrator to prove end-to-end flow.

This module wires together:
- models → requests tier → detection → content → cache → trace

Goal: Derisk the refactor and ensure module boundaries are correct.
"""

import logging
import time
from typing import Optional

from .cache import ScrapeCache
from .content import extract_clean_text, get_page_title
from .detection import detect_soft_block, check_success_signal
from .http_clients import scrape_with_requests
from .models import Attempt, ErrorType, ScrapeResult, ValidationResult
from .net import extract_host
from .trace import TraceLogger
from .validation import validate_content


logger = logging.getLogger(__name__)


def scrape_single_url(
    url: str,
    cache: Optional[ScrapeCache] = None,
    trace_logger: Optional[TraceLogger] = None,
    timeout: float = 15,
) -> ScrapeResult:
    """
    Scrape a single URL using the requests tier only.
    
    This is a minimal orchestrator for the vertical slice checkpoint.
    It demonstrates the full flow:
    1. Check cache for existing result
    2. Make request using requests tier
    3. Check for soft blocks
    4. Check success signal
    5. Extract content
    6. Validate content
    7. Cache result
    8. Log to trace
    
    Args:
        url: URL to scrape
        cache: Optional cache instance
        trace_logger: Optional trace logger
        timeout: Request timeout in seconds
    
    Returns:
        ScrapeResult with all fields populated
    """
    host = extract_host(url)
    start_time = time.time()
    
    # 1. Check cache
    if cache:
        cached_raw = cache.get_raw(url)
        if cached_raw is not None:
            logger.debug(f"Cache hit for {url}")
            
            # Extract text from cached content
            extracted = extract_clean_text(cached_raw)
            title = get_page_title(cached_raw)
            
            result = ScrapeResult(
                url=url,
                success=True,
                raw_content=cached_raw,
                extracted_text=extracted,
                tier="cache",
                cached=True,
                content_type="text/html",
            )
            
            if trace_logger:
                trace_logger.log(result)
            
            return result
    
    # 2. Make request
    result = scrape_with_requests(url, timeout=timeout)
    
    if not result.success:
        # Request failed
        if trace_logger:
            trace_logger.log(result)
        return result
    
    # 3. Check for soft blocks
    is_blocked, block_reason = detect_soft_block(
        result.raw_content,
        http_status=result.http_status,
        content_type=result.content_type,
        final_url=result.final_url,
        host=host,
    )
    
    if is_blocked:
        result.success = False
        result.error_type = ErrorType.SOFT_BLOCK
        result.error = f"Soft block detected: {block_reason}"
        result.blocked_reason = block_reason
        
        if trace_logger:
            trace_logger.log(result)
        return result
    
    # 4. Check success signal
    if not check_success_signal(result.raw_content, result.http_status):
        result.success = False
        result.error_type = ErrorType.SUCCESS_SIGNAL_FAILED
        result.error = "Content failed success signal check"
        
        if trace_logger:
            trace_logger.log(result)
        return result
    
    # 5. Extract content
    extracted_text = extract_clean_text(result.raw_content)
    result.extracted_text = extracted_text
    
    # 6. Validate content
    validation = validate_content(extracted_text, url)
    result.validation = validation
    
    # Note: Validation failures do NOT change success status
    # They are informational only (per spec)
    
    # 7. Cache result
    if cache and result.success:
        cache.set_raw(url, result.raw_content)
        if extracted_text:
            cache.set_extracted(url, extracted_text)
    
    # 8. Log to trace
    if trace_logger:
        trace_logger.log(result)
    
    return result


def run_vertical_slice_test(
    url: str = "https://httpbin.org/html",
    output_dir: str = "output",
) -> bool:
    """
    Run the vertical slice test to verify end-to-end flow.
    
    Args:
        url: URL to test with (default: httpbin.org/html)
        output_dir: Directory for trace output
    
    Returns:
        True if test passed, False otherwise
    """
    import os
    
    print(f"Running vertical slice test with {url}")
    
    # Create cache and trace logger
    cache = ScrapeCache(max_memory_items=100)
    trace_logger = TraceLogger(
        company_name="vertical_slice_test",
        output_dir=output_dir,
    )
    
    try:
        # First request - should hit network
        print("  Making first request (should hit network)...")
        result1 = scrape_single_url(url, cache=cache, trace_logger=trace_logger)
        
        if not result1.success:
            print(f"  FAILED: First request failed: {result1.error}")
            return False
        
        print(f"  SUCCESS: Got {len(result1.raw_content)} bytes")
        print(f"  Tier: {result1.tier}")
        print(f"  Cached: {result1.cached}")
        
        if result1.extracted_text:
            print(f"  Extracted: {len(result1.extracted_text)} chars")
        
        if result1.validation:
            print(f"  Validation: valid={result1.validation.valid}, density={result1.validation.content_density:.2f}")
        
        # Second request - should hit cache
        print("  Making second request (should hit cache)...")
        result2 = scrape_single_url(url, cache=cache, trace_logger=trace_logger)
        
        if not result2.cached:
            print("  WARNING: Second request did not hit cache")
        else:
            print("  SUCCESS: Cache hit on second request")
        
        # Verify trace file
        trace_path = trace_logger.get_path()
        if os.path.exists(trace_path):
            print(f"  Trace file written: {trace_path}")
            with open(trace_path, "r") as f:
                lines = f.readlines()
            print(f"  Trace entries: {len(lines)}")
        else:
            print("  WARNING: Trace file not found")
        
        print("Vertical slice test PASSED")
        return True
        
    except Exception as e:
        print(f"  FAILED with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the test when executed directly
    success = run_vertical_slice_test()
    exit(0 if success else 1)
