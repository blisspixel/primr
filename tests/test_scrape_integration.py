"""
Integration tests for the scraping architecture.

These tests verify the orchestrator, wrapper, and module integration.
All tests use mocks - no live network calls.

Run with: pytest tests/test_scrape_integration.py -v
"""

from unittest.mock import patch

from bs4 import BeautifulSoup

from primr.data.scrape import (
    cache_content,
    clear_cache,
    detect_soft_block,
    extract_clean_text,
    extract_links_from_html,
    get_cached_content,
    scrape_page,
)
from primr.data.scraping import (
    RateLimitConfig,
    RateLimiter,
    ScrapeCache,
    ScrapeOrchestrator,
    ScrapeResult,
    ScrapeTier,
)

# ============================================================================
# TEST HTML FIXTURES
# ============================================================================

VALID_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Company</title></head>
<body>
    <main>
        <h1>Welcome to Test Company</h1>
        <p>We are a leading provider of innovative solutions for enterprise customers around the world. Our company has been serving customers for over 20 years with dedication and excellence.</p>
        <p>We specialize in enterprise software solutions that help businesses grow and succeed. Our products are used by thousands of companies worldwide to improve their operations and increase efficiency.</p>
        <p>Our team of experts is committed to delivering the best possible service to our clients. We work closely with each customer to understand their unique needs and provide tailored solutions that meet their specific requirements.</p>
        <p>Contact us today to learn more about how we can help your business achieve its goals. We look forward to hearing from you and discussing how our solutions can benefit your organization.</p>
    </main>
</body>
</html>
"""

BLOCKED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Access Denied</title></head>
<body>
    <h1>403 Forbidden</h1>
    <p>Access denied. Please verify you are human.</p>
</body>
</html>
"""

CAPTCHA_HTML = """
<!DOCTYPE html>
<html>
<head><title>Security Check</title></head>
<body>
    <h1>Checking your browser</h1>
    <p>Please complete the captcha to continue.</p>
</body>
</html>
"""

HTML_WITH_LINKS = """
<!DOCTYPE html>
<html>
<body>
    <a href="/about">About</a>
    <a href="/products">Products</a>
    <a href="https://external.com">External</a>
</body>
</html>
"""


# ============================================================================
# ORCHESTRATOR TESTS
# ============================================================================


class TestOrchestratorTierEscalation:
    """Tests for orchestrator tier escalation behavior."""

    def test_stops_on_first_success(self, tmp_path):
        """Should stop trying tiers after first success."""
        # Use temp directory for cache to avoid cross-test pollution
        cache = ScrapeCache(cache_dir=str(tmp_path / "cache1"))
        orchestrator = ScrapeOrchestrator(
            cache=cache,
            rate_limiter=RateLimiter(RateLimitConfig()),
        )

        call_order = []

        def tier1_success(url, timeout=30):
            call_order.append("tier1")
            return ScrapeResult(
                url=url,
                success=True,
                tier="tier1",
                raw_content=VALID_HTML.encode("utf-8"),
            )

        def tier2_should_not_run(url, timeout=30):
            call_order.append("tier2")
            return ScrapeResult(url=url, success=True, tier="tier2")

        orchestrator.tiers = [
            ScrapeTier(name="tier1", scrape_fn=tier1_success, timeout=30),
            ScrapeTier(name="tier2", scrape_fn=tier2_should_not_run, timeout=30),
        ]

        result = orchestrator.scrape_url("https://example.com/page1")

        assert result.success
        assert call_order == ["tier1"]

    def test_escalates_on_failure(self, tmp_path):
        """Should try next tier when previous fails."""
        cache = ScrapeCache(cache_dir=str(tmp_path / "cache2"))
        orchestrator = ScrapeOrchestrator(
            cache=cache,
            rate_limiter=RateLimiter(RateLimitConfig()),
        )

        call_order = []

        def tier1_fail(url, timeout=30):
            call_order.append("tier1")
            return ScrapeResult(url=url, success=False, tier="tier1", error="Failed")

        def tier2_success(url, timeout=30):
            call_order.append("tier2")
            return ScrapeResult(
                url=url,
                success=True,
                tier="tier2",
                raw_content=VALID_HTML.encode("utf-8"),
            )

        orchestrator.tiers = [
            ScrapeTier(name="tier1", scrape_fn=tier1_fail, timeout=30),
            ScrapeTier(name="tier2", scrape_fn=tier2_success, timeout=30),
        ]

        result = orchestrator.scrape_url("https://example.com/page2")

        assert result.success
        assert result.tier == "tier2"
        assert call_order == ["tier1", "tier2"]

    def test_returns_failure_when_all_tiers_fail(self, tmp_path):
        """Should return failure when all tiers exhausted."""
        cache = ScrapeCache(cache_dir=str(tmp_path / "cache3"))
        orchestrator = ScrapeOrchestrator(
            cache=cache,
            rate_limiter=RateLimiter(RateLimitConfig()),
        )

        def always_fail(url, timeout=30):
            return ScrapeResult(url=url, success=False, tier="fail", error="Nope")

        orchestrator.tiers = [
            ScrapeTier(name="tier1", scrape_fn=always_fail, timeout=30),
            ScrapeTier(name="tier2", scrape_fn=always_fail, timeout=30),
        ]

        result = orchestrator.scrape_url("https://example.com/page3")

        assert not result.success
        assert result.error is not None


class TestOrchestratorCaching:
    """Tests for orchestrator cache behavior."""

    def test_returns_cached_content(self, tmp_path):
        """Should return cached content without calling tiers."""
        cache = ScrapeCache(cache_dir=str(tmp_path / "cache4"))
        orchestrator = ScrapeOrchestrator(
            cache=cache,
            rate_limiter=RateLimiter(RateLimitConfig()),
            use_cache=True,  # Enable cache usage
        )

        # Pre-populate cache with raw content (orchestrator checks raw cache)
        url = "https://example.com/cached"
        cache.set_raw(url, VALID_HTML.encode("utf-8"))

        tier_called = False

        def should_not_run(url, timeout=30):
            nonlocal tier_called
            tier_called = True
            return ScrapeResult(url=url, success=True)

        orchestrator.tiers = [ScrapeTier(name="tier1", scrape_fn=should_not_run, timeout=30)]

        result = orchestrator.scrape_url(url)

        assert result.success
        assert result.cached
        assert not tier_called


# ============================================================================
# WRAPPER FUNCTION TESTS
# ============================================================================


class TestScrapePage:
    """Tests for the scrape_page wrapper function."""

    def setup_method(self):
        clear_cache()

    def test_returns_content_and_tier_on_success(self):
        """Should return (content, tier) tuple on success."""
        mock_result = ScrapeResult(
            url="https://test.com",
            success=True,
            tier="requests",
            extracted_text="Test content",
        )

        with patch.object(ScrapeOrchestrator, "scrape_url", return_value=mock_result):
            content, tier = scrape_page("https://test.com")

        assert content == "Test content"
        assert tier == "requests"

    def test_returns_none_and_error_on_failure(self):
        """Should return (None, error) tuple on failure."""
        mock_result = ScrapeResult(
            url="https://blocked.com",
            success=False,
            error="All tiers exhausted",
        )

        with patch.object(ScrapeOrchestrator, "scrape_url", return_value=mock_result):
            content, error = scrape_page("https://blocked.com")

        assert content is None
        assert error == "All tiers exhausted"


# ============================================================================
# SOFT BLOCK DETECTION TESTS
# ============================================================================


class TestSoftBlockDetection:
    """Tests for soft block detection integration."""

    def test_detects_access_denied(self):
        """Should detect access denied pages."""
        is_blocked, reason = detect_soft_block(BLOCKED_HTML)
        assert is_blocked

    def test_detects_captcha(self):
        """Should detect captcha pages."""
        is_blocked, reason = detect_soft_block(CAPTCHA_HTML)
        assert is_blocked

    def test_allows_valid_content(self):
        """Should allow valid content through."""
        is_blocked, reason = detect_soft_block(VALID_HTML)
        assert not is_blocked

    def test_detects_empty_response(self):
        """Should detect empty responses."""
        is_blocked, reason = detect_soft_block("")
        assert is_blocked


# ============================================================================
# CONTENT EXTRACTION TESTS
# ============================================================================


class TestContentExtraction:
    """Tests for content extraction integration."""

    def test_extracts_text_from_soup(self):
        """Should extract clean text from BeautifulSoup."""
        soup = BeautifulSoup(VALID_HTML, "html.parser")
        text = extract_clean_text(soup)

        assert "Test Company" in text
        assert "innovative solutions" in text

    def test_removes_nav_and_footer(self):
        """Should remove navigation and footer elements."""
        html = """
        <html><body>
            <nav>Nav content</nav>
            <main>Main content</main>
            <footer>Footer content</footer>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)

        assert "Nav content" not in text
        assert "Footer content" not in text
        assert "Main content" in text


# ============================================================================
# LINK EXTRACTION TESTS
# ============================================================================


class TestLinkExtraction:
    """Tests for link extraction integration."""

    def test_extracts_internal_links(self):
        """Should extract internal links."""
        links = extract_links_from_html(HTML_WITH_LINKS, "https://example.com")

        assert "https://example.com/about" in links
        assert "https://example.com/products" in links

    def test_excludes_external_links(self):
        """Should exclude external links."""
        links = extract_links_from_html(HTML_WITH_LINKS, "https://example.com")

        for link in links:
            assert "external.com" not in link


# ============================================================================
# CACHE TESTS
# ============================================================================


class TestCaching:
    """Tests for caching integration."""

    def setup_method(self):
        clear_cache()

    def test_cache_roundtrip(self):
        """Should store and retrieve cached content."""
        url = "https://test.com/page"
        content = "Test content"

        cache_content(url, content)
        cached = get_cached_content(url)

        assert cached == content

    def test_cache_miss_returns_none(self):
        """Should return None for uncached URLs."""
        cached = get_cached_content("https://never-cached.com")
        assert cached is None
