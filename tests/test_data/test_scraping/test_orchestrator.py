"""Tests for the scrape orchestrator."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile

from primr.data.scraping.orchestrator import ScrapeOrchestrator
from primr.data.scraping.models import (
    Attempt,
    ErrorType,
    HostState,
    ScrapeResult,
    ScrapeTier,
)
from primr.data.scraping.cache import ScrapeCache
from primr.data.scraping.rate_limiter import NoOpRateLimiter
from primr.data.scraping.trace import TraceLogger


# Default mock content that passes success signal check AND quality check
# Must have: 200+ chars, 30+ words, 2+ sentences, no garbage patterns
DEFAULT_MOCK_CONTENT = b"""<!DOCTYPE html>
<html>
<head><title>Test Company - About Us</title></head>
<body>
<main>
<h1>About Test Company</h1>
<article>
<p>Test Company is a leading provider of innovative technology solutions that help businesses transform their operations. Founded in 2010, we have grown to serve over 5,000 customers across North America with our comprehensive suite of cloud and digital workplace services.</p>
<p>Our team of 500 certified experts brings deep expertise in cloud migration, cybersecurity, and digital transformation. We partner with industry leaders including Microsoft, AWS, and Google Cloud to deliver best-in-class solutions.</p>
<p>Our mission is to empower organizations to achieve their full potential through technology. We believe in building long-term partnerships with our customers, providing ongoing support and guidance as their needs evolve.</p>
</article>
</main>
</body>
</html>"""


def make_mock_tier(name: str, success: bool = True, content: bytes = DEFAULT_MOCK_CONTENT) -> ScrapeTier:
    """Create a mock tier for testing."""
    def scrape_fn(url: str, timeout: int) -> ScrapeResult:
        if success:
            return ScrapeResult(
                url=url,
                success=True,
                raw_content=content,
                content_type="text/html",
                http_status=200,
                final_url=url,
                tier=name,
                elapsed_ms=100,
                attempts=[Attempt(tier=name, success=True, elapsed_ms=100, http_status=200)],
            )
        else:
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error="Mock failure",
                tier=name,
                elapsed_ms=100,
                attempts=[Attempt(tier=name, success=False, error="Mock failure", elapsed_ms=100)],
            )
    
    return ScrapeTier(
        name=name,
        scrape_fn=scrape_fn,
        timeout=10,
        requires=None,
    )


class TestScrapeOrchestrator:
    """Tests for ScrapeOrchestrator class."""
    
    def test_uses_first_successful_tier(self):
        """Should use first tier that succeeds."""
        tier1 = make_mock_tier("tier1", success=True)
        tier2 = make_mock_tier("tier2", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1, tier2],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
            
            result = orchestrator.scrape_url("https://example.com")
        
        assert result.success is True
        assert result.tier == "tier1"
    
    def test_escalates_on_failure(self):
        """Should try next tier when first fails."""
        tier1 = make_mock_tier("tier1", success=False)
        tier2 = make_mock_tier("tier2", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1, tier2],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                delay_between_tiers=(0, 0),  # No delay for tests
            )
            
            result = orchestrator.scrape_url("https://example.com")
        
        assert result.success is True
        assert result.tier == "tier2"
    
    def test_returns_cached_result(self):
        """Should return cached result without making requests."""
        tier1 = make_mock_tier("tier1", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(cache_dir=tmpdir)
            cache.set_raw("https://example.com", b"<html>Cached</html>")
            
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1],
                cache=cache,
                rate_limiter=NoOpRateLimiter(),
                use_cache=True,  # Enable cache for this test
            )
            
            result = orchestrator.scrape_url("https://example.com")
        
        assert result.success is True
        assert result.cached is True
        assert result.tier == "cache"
    
    def test_records_all_attempts(self):
        """Should record attempts from all tried tiers."""
        tier1 = make_mock_tier("tier1", success=False)
        tier2 = make_mock_tier("tier2", success=False)
        tier3 = make_mock_tier("tier3", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1, tier2, tier3],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                delay_between_tiers=(0, 0),
            )
            
            result = orchestrator.scrape_url("https://example.com")
        
        assert result.success is True
        assert len(result.attempts) >= 3
        tier_names = [a.tier for a in result.attempts]
        assert "tier1" in tier_names
        assert "tier2" in tier_names
        assert "tier3" in tier_names


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""
    
    def test_skips_tier_after_threshold_failures(self):
        """Should skip tier after threshold failures."""
        call_count = {"tier1": 0, "tier2": 0}
        
        def tier1_fn(url, timeout):
            call_count["tier1"] += 1
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.SOFT_BLOCK,
                error="Blocked",
                tier="tier1",
                attempts=[Attempt(tier="tier1", success=False)],
            )
        
        def tier2_fn(url, timeout):
            call_count["tier2"] += 1
            return ScrapeResult(
                url=url,
                success=True,
                raw_content=DEFAULT_MOCK_CONTENT,  # Use content that passes success signal
                tier="tier2",
                http_status=200,
                attempts=[Attempt(tier="tier2", success=True, http_status=200)],
            )
        
        tier1 = ScrapeTier(name="tier1", scrape_fn=tier1_fn, timeout=10)
        tier2 = ScrapeTier(name="tier2", scrape_fn=tier2_fn, timeout=10)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1, tier2],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                circuit_breaker_threshold=2,
                delay_between_tiers=(0, 0),
            )
            
            # First request - tier1 fails, tier2 succeeds
            # After this, best_tier="tier2" so subsequent requests start with tier2
            result1 = orchestrator.scrape_url("https://example.com/page1")
            assert result1.success is True
            
            # Reset best_tier to force tier1 to be tried again
            host_state = orchestrator._get_host_state("example.com")
            host_state.best_tier = None
            
            # Second request - tier1 fails again (count=2), tier2 succeeds
            result2 = orchestrator.scrape_url("https://example.com/page2")
            assert result2.success is True
            
            # Reset best_tier again
            host_state.best_tier = None
            
            # Third request - tier1 should be skipped (2 failures >= threshold)
            result3 = orchestrator.scrape_url("https://example.com/page3")
            assert result3.success is True
        
        # tier1 should have been called only twice (then skipped due to circuit breaker)
        assert call_count["tier1"] == 2
        # tier2 should have been called 3 times
        assert call_count["tier2"] == 3
    
    def test_circuit_breaker_is_per_host(self):
        """Circuit breaker should be per-host."""
        call_count = {"host1": 0, "host2": 0}
        
        def tier_fn(url, timeout):
            host = "host1" if "host1" in url else "host2"
            call_count[host] += 1
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.SOFT_BLOCK,
                error="Blocked",
                tier="tier1",
                attempts=[Attempt(tier="tier1", success=False)],
            )
        
        tier = ScrapeTier(name="tier1", scrape_fn=tier_fn, timeout=10)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                circuit_breaker_threshold=2,
                delay_between_tiers=(0, 0),
            )
            
            # Bypass SSRF check for fake test hostnames
            with patch("primr.utils.security.is_safe_url", return_value=(True, None)):
                # Fail on host1 twice
                orchestrator.scrape_url("https://host1.com/page1")
                orchestrator.scrape_url("https://host1.com/page2")

                # host1 should now be skipped, but host2 should still work
                orchestrator.scrape_url("https://host1.com/page3")  # Skipped
                orchestrator.scrape_url("https://host2.com/page1")  # Not skipped
        
        assert call_count["host1"] == 2  # Skipped on 3rd
        assert call_count["host2"] == 1  # Not affected


class TestHardBlockHandling:
    """Tests for hard block handling."""
    
    def test_stops_on_hard_block(self):
        """Should stop escalation on hard block."""
        def tier1_fn(url, timeout):
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.HARD_BLOCK,
                error="403 Forbidden",
                tier="tier1",
                attempts=[Attempt(tier="tier1", success=False)],
            )
        
        tier1 = ScrapeTier(name="tier1", scrape_fn=tier1_fn, timeout=10)
        tier2 = make_mock_tier("tier2", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1, tier2],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
            
            result = orchestrator.scrape_url("https://example.com")
        
        # Should fail with hard block, not try tier2
        assert result.success is False
        assert result.error_type == ErrorType.HARD_BLOCK
    
    def test_marks_host_as_blocked(self):
        """Should mark host as blocked after hard block."""
        def tier_fn(url, timeout):
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.HARD_BLOCK,
                error="Blocked",
                tier="tier1",
                attempts=[],
            )
        
        tier = ScrapeTier(name="tier1", scrape_fn=tier_fn, timeout=10)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
            
            orchestrator.scrape_url("https://example.com/page1")
            
            # Second request should fail immediately
            result = orchestrator.scrape_url("https://example.com/page2")
        
        assert result.success is False
        assert result.error_type == ErrorType.HARD_BLOCK
        # Host should be marked as blocked
        host_state = orchestrator.get_host_state("example.com")
        assert host_state is not None
        assert host_state.hard_blocked is True


class TestRateLimiting:
    """Tests for rate limiting integration."""
    
    def test_acquires_and_releases_rate_limit(self):
        """Should acquire and release rate limit."""
        mock_limiter = Mock()
        mock_limiter.acquire = Mock()
        mock_limiter.release = Mock()
        
        tier = make_mock_tier("tier1", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=mock_limiter,
            )
            
            orchestrator.scrape_url("https://example.com")
        
        mock_limiter.acquire.assert_called_once_with("example.com")
        mock_limiter.release.assert_called_once_with("example.com")
    
    def test_releases_on_exception(self):
        """Should release rate limit even on exception."""
        mock_limiter = Mock()
        mock_limiter.acquire = Mock()
        mock_limiter.release = Mock()
        
        def failing_fn(url, timeout):
            raise RuntimeError("Unexpected error")
        
        tier = ScrapeTier(name="tier1", scrape_fn=failing_fn, timeout=10)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=mock_limiter,
                delay_between_tiers=(0, 0),
            )
            
            # Should not raise, should handle gracefully
            result = orchestrator.scrape_url("https://example.com")
        
        # Release should still be called
        mock_limiter.release.assert_called()


class TestCaching:
    """Tests for caching behavior."""
    
    def test_caches_raw_content(self):
        """Should cache raw content on success."""
        test_content = b"""<!DOCTYPE html>
<html>
<head><title>Test Content Page</title></head>
<body>
<main>
<h1>Test Content</h1>
<p>This is test content that should be cached.</p>
</main>
</body>
</html>"""
        tier = make_mock_tier("tier1", success=True, content=test_content)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(cache_dir=tmpdir)
            
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=cache,
                rate_limiter=NoOpRateLimiter(),
            )
            
            orchestrator.scrape_url("https://example.com")
        
        # Check cache
        cached = cache.get_raw("https://example.com")
        assert cached is not None
        assert b"Test Content" in cached
    
    def test_caches_extracted_text(self):
        """Should cache extracted text on success."""
        content = b"""
        <html>
        <head><title>Test Company Page</title></head>
        <body><main>
        <h1>Main Content Section</h1>
        <p>This is a test page with substantial content that should pass the quality check. It contains multiple sentences and enough words to be considered meaningful content for extraction and caching purposes.</p>
        <p>The company provides various services including cloud solutions, digital transformation, and managed IT services. Our team of experts helps businesses achieve their technology goals through innovative approaches and proven methodologies.</p>
        </main></body>
        </html>
        """
        tier = make_mock_tier("tier1", success=True, content=content)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(cache_dir=tmpdir)
            
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=cache,
                rate_limiter=NoOpRateLimiter(),
            )
            
            orchestrator.scrape_url("https://example.com")
        
        # Check extracted cache
        extracted = cache.get_extracted("https://example.com")
        assert extracted is not None
        assert "Main Content" in extracted


class TestTraceLogging:
    """Tests for trace logging integration."""
    
    def test_logs_successful_scrape(self):
        """Should log successful scrape to trace."""
        tier = make_mock_tier("tier1", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_logger = TraceLogger(
                company_name="test",
                output_dir=tmpdir,
            )
            
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                trace_logger=trace_logger,
            )
            
            orchestrator.scrape_url("https://example.com")
            
            # Verify trace file has content
            trace_path = trace_logger.get_path()
            assert trace_path.exists(), f"Trace file not found at {trace_path}"
            
            content = trace_path.read_text()
            assert "example.com" in content


class TestVisionTier:
    """Tests for vision tier handling."""
    
    def test_vision_included_by_default(self):
        """Vision tier should be included by default (enable_vision=True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
        
        tier_names = [t.name for t in orchestrator.tiers]
        assert "vision" in tier_names
    
    def test_vision_excluded_when_disabled(self):
        """Vision tier should be excluded when enable_vision=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                enable_vision=False,
            )
        
        tier_names = [t.name for t in orchestrator.tiers]
        assert "vision" not in tier_names


class TestScrapeUrls:
    """Tests for scrape_urls method."""
    
    def test_scrapes_multiple_urls(self):
        """Should scrape multiple URLs."""
        tier = make_mock_tier("tier1", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
            
            urls = [
                "https://example.com/page1",
                "https://example.com/page2",
                "https://example.com/page3",
            ]
            
            results = orchestrator.scrape_urls(urls)
        
        assert len(results) == 3
        assert all(r.success for r in results)
    
    def test_respects_max_pages(self):
        """Should respect max_pages limit."""
        tier = make_mock_tier("tier1", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
            
            urls = [f"https://example.com/page{i}" for i in range(10)]
            
            results = orchestrator.scrape_urls(urls, max_pages=3)
        
        assert len(results) == 3


class TestOrchestratorStats:
    """Tests for orchestrator statistics."""
    
    def test_get_stats(self):
        """Should return stats dict."""
        tier = make_mock_tier("tier1", success=True)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            orchestrator = ScrapeOrchestrator(
                tiers=[tier],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
            )
            
            stats = orchestrator.get_stats()
        
        assert "tiers" in stats
        assert "hosts_tracked" in stats
        assert "hosts_blocked" in stats
        assert "cache_stats" in stats



class TestGoldenRunTrace:
    """Golden-run trace test for orchestrator."""
    
    def test_golden_run_trace_format(self):
        """Test trace output format with fake tiers."""
        # Create two fake tiers - first fails, second succeeds
        def tier1_fn(url, timeout):
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.SOFT_BLOCK,
                error="Soft block detected",
                tier="tier1",
                elapsed_ms=50,
                attempts=[Attempt(
                    tier="tier1",
                    success=False,
                    error="Soft block detected",
                    error_type=ErrorType.SOFT_BLOCK,
                    elapsed_ms=50,
                )],
            )
        
        def tier2_fn(url, timeout):
            return ScrapeResult(
                url=url,
                success=True,
                raw_content=DEFAULT_MOCK_CONTENT,
                tier="tier2",
                http_status=200,
                content_type="text/html",
                elapsed_ms=100,
                attempts=[Attempt(
                    tier="tier2",
                    success=True,
                    elapsed_ms=100,
                    http_status=200,
                )],
            )
        
        tier1 = ScrapeTier(name="tier1", scrape_fn=tier1_fn, timeout=10)
        tier2 = ScrapeTier(name="tier2", scrape_fn=tier2_fn, timeout=10)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_logger = TraceLogger(
                company_name="golden_test",
                output_dir=tmpdir,
            )
            
            orchestrator = ScrapeOrchestrator(
                tiers=[tier1, tier2],
                cache=ScrapeCache(cache_dir=tmpdir),
                rate_limiter=NoOpRateLimiter(),
                trace_logger=trace_logger,
                delay_between_tiers=(0, 0),
            )
            
            result = orchestrator.scrape_url("https://example.com/test")
            
            # Verify result
            assert result.success is True
            assert result.tier == "tier2"
            
            # Read and verify trace file
            import json
            trace_path = trace_logger.get_path()
            assert trace_path.exists()
            
            lines = trace_path.read_text().strip().split("\n")
            assert len(lines) == 2  # Header + 1 entry
            
            # Verify header
            header = json.loads(lines[0])
            assert header["schema_version"] == "1.0"
            assert header["company"] == "golden_test"
            assert "run_id" in header
            
            # Verify entry
            entry = json.loads(lines[1])
            assert entry["url"] == "https://example.com/test"
            assert entry["success_tier"] == "tier2"
            assert len(entry["tier_attempts"]) >= 2
            
            # Verify attempt sequence
            attempts = entry["tier_attempts"]
            tier1_attempt = next((a for a in attempts if a["tier"] == "tier1"), None)
            tier2_attempt = next((a for a in attempts if a["tier"] == "tier2"), None)
            
            assert tier1_attempt is not None
            assert tier1_attempt["success"] is False
            assert tier1_attempt["error_type"] == "soft_block"
            
            assert tier2_attempt is not None
            assert tier2_attempt["success"] is True
            assert tier2_attempt["http_status"] == 200
