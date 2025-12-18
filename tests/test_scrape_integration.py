"""
Integration tests for scrape.py
All tests use mocked HTTP responses to avoid hitting real sites.
Run with: pytest tests/test_scrape_integration.py -v
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import requests
import httpx

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the module for patching, and functions for direct use
from primr.data import scrape as scrape_module
from primr.data.scrape import (
    scrape_with_requests,
    scrape_with_httpx,
    scrape_page,
    extract_links_from_homepage,
    get_cached_content,
    cache_content,
    clear_cache,
    _SCRAPE_CACHE,
    detect_soft_block,
    extract_clean_text,
)
from bs4 import BeautifulSoup


# ============================================================================
# MOCK HTML RESPONSES
# ============================================================================
MOCK_HTML_SIMPLE = """
<!DOCTYPE html>
<html>
<head><title>Test Company</title></head>
<body>
    <h1>Welcome to Test Company</h1>
    <p>We are a leading provider of innovative solutions.</p>
    <nav>
        <a href="/about">About Us</a>
        <a href="/products">Products</a>
        <a href="/services">Services</a>
        <a href="/contact">Contact</a>
    </nav>
    <main>
        <p>Our company has been serving customers for over 20 years.</p>
        <p>We specialize in enterprise software solutions.</p>
    </main>
</body>
</html>
"""

MOCK_HTML_BLOCKED = """
<!DOCTYPE html>
<html>
<head><title>Access Denied</title></head>
<body>
    <h1>403 Forbidden</h1>
    <p>Access denied. Please verify you are human.</p>
</body>
</html>
"""

MOCK_HTML_CAPTCHA = """
<!DOCTYPE html>
<html>
<head><title>Security Check</title></head>
<body>
    <h1>Checking your browser</h1>
    <p>Please complete the captcha to continue.</p>
</body>
</html>
"""

MOCK_HTML_WITH_LINKS = """
<!DOCTYPE html>
<html>
<head><title>Company Site</title></head>
<body>
    <nav>
        <a href="/">Home</a>
        <a href="/about">About</a>
        <a href="/products">Products</a>
        <a href="/services">Services</a>
        <a href="/blog">Blog</a>
        <a href="/login">Login</a>
        <a href="/careers">Careers</a>
        <a href="/privacy">Privacy Policy</a>
        <a href="https://external.com">External Link</a>
    </nav>
    <main>
        <p>Welcome to our company website with lots of useful content.</p>
    </main>
</body>
</html>
"""


# ============================================================================
# TIER 1: REQUESTS TESTS (MOCKED)
# ============================================================================
class TestScrapeWithRequests:
    """Tests for requests-based scraping with mocked responses."""
    
    def test_scrape_success(self):
        """Should successfully extract text from valid HTML."""
        mock_response = MagicMock()
        mock_response.text = MOCK_HTML_SIMPLE
        mock_response.raise_for_status = MagicMock()
        
        with patch('primr.data.scrape.requests.get', return_value=mock_response):
            text, error = scrape_with_requests("https://test-company.com", timeout=15)
        
        assert error is None
        assert text is not None
        assert "Test Company" in text
        assert "innovative solutions" in text
    
    def test_scrape_http_403(self):
        """Should handle 403 errors gracefully."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=403)
        )
        
        with patch('primr.data.scrape.requests.get', return_value=mock_response):
            text, error = scrape_with_requests("https://blocked-site.com", timeout=15)
        
        assert text is None
        assert error is not None
        assert "403" in error or "HTTP" in error
    
    def test_scrape_connection_error(self):
        """Should handle connection errors gracefully."""
        with patch('primr.data.scrape.requests.get', side_effect=requests.exceptions.ConnectionError("Failed")):
            text, error = scrape_with_requests("https://unreachable.com", timeout=5)
        
        assert text is None
        assert error is not None
    
    def test_scrape_timeout(self):
        """Should handle timeouts gracefully."""
        with patch('primr.data.scrape.requests.get', side_effect=requests.exceptions.Timeout("Timed out")):
            text, error = scrape_with_requests("https://slow-site.com", timeout=1)
        
        assert text is None
        assert error is not None
    
    def test_scrape_detects_soft_block(self):
        """Should detect soft blocks in response content."""
        mock_response = MagicMock()
        mock_response.text = MOCK_HTML_BLOCKED
        mock_response.raise_for_status = MagicMock()
        
        with patch('primr.data.scrape.requests.get', return_value=mock_response):
            text, error = scrape_with_requests("https://soft-blocked.com", timeout=15)
        
        assert text is None
        assert error is not None


# ============================================================================
# TIER 2: HTTPX TESTS (MOCKED)
# ============================================================================
class TestScrapeWithHttpx:
    """Tests for httpx-based scraping with mocked responses."""
    
    def test_scrape_success(self):
        """Should successfully scrape with httpx."""
        mock_response = MagicMock()
        mock_response.text = MOCK_HTML_SIMPLE
        mock_response.raise_for_status = MagicMock()
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        
        with patch('primr.data.scrape.httpx.Client', return_value=mock_client):
            text, error = scrape_with_httpx("https://test-company.com", timeout=15)
        
        assert error is None
        assert text is not None
        assert "Test Company" in text
    
    def test_scrape_http_error(self):
        """Should handle HTTP errors gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.get.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        
        with patch('primr.data.scrape.httpx.Client', return_value=mock_client):
            text, error = scrape_with_httpx("https://blocked-site.com", timeout=15)
        
        assert text is None
        assert error is not None


# ============================================================================
# MAIN SCRAPE_PAGE TESTS (MOCKED)
# ============================================================================
class TestScrapePage:
    """Tests for the main scrape_page orchestrator."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()
    
    def test_returns_cached_content(self):
        """Should return cached content without making requests."""
        url = "https://cached-site.com"
        cached_content = "This is cached content for testing"
        
        cache_content(url, cached_content)
        
        content, method = scrape_page(url)
        assert content == cached_content
        assert method == "cache"
    
    def test_caches_successful_scrape(self):
        """Should cache successful scrapes."""
        url = "https://fresh-site.com"
        
        mock_response = MagicMock()
        mock_response.text = MOCK_HTML_SIMPLE
        mock_response.raise_for_status = MagicMock()
        
        with patch('primr.data.scrape.requests.get', return_value=mock_response):
            content, method = scrape_page(url)
        
        assert content is not None
        assert method == "requests"
        
        # Verify it's cached
        cached = get_cached_content(url)
        assert cached == content
    
    def test_handles_pdf_urls(self):
        """Should detect PDF URLs and handle them differently."""
        url = "https://example.com/document.pdf"
        
        with patch.object(scrape_module, 'extract_text_from_pdf') as mock_pdf:
            mock_pdf.return_value = "PDF content extracted successfully"
            content, method = scrape_module.scrape_page(url)
            mock_pdf.assert_called_once_with(url)
            assert content == "PDF content extracted successfully"
            assert method == "pdf"
    
    def test_graceful_degradation(self):
        """Should try all tiers before giving up."""
        with patch.object(scrape_module, 'scrape_with_requests') as mock_req, \
             patch.object(scrape_module, 'scrape_with_httpx') as mock_httpx, \
             patch.object(scrape_module, 'scrape_with_playwright') as mock_pw, \
             patch.object(scrape_module, 'scrape_with_playwright_aggressive') as mock_pw_agg:
            
            mock_req.return_value = (None, "HTTP 403")
            mock_httpx.return_value = (None, "HTTP 403")
            mock_pw.return_value = (None, "Blocked")
            mock_pw_agg.return_value = (None, "Blocked")
            
            content, method = scrape_module.scrape_page("https://hardened-site.com")
            
            mock_req.assert_called_once()
            mock_httpx.assert_called_once()
            mock_pw.assert_called_once()
            mock_pw_agg.assert_called_once()
            
            assert content is None
            assert method is None
    
    def test_stops_on_first_success(self):
        """Should stop trying tiers after first success."""
        with patch.object(scrape_module, 'scrape_with_requests') as mock_req, \
             patch.object(scrape_module, 'scrape_with_httpx') as mock_httpx:
            
            mock_req.return_value = ("Success content from requests", None)
            
            content, method = scrape_module.scrape_page("https://easy-site.com")
            
            mock_req.assert_called_once()
            mock_httpx.assert_not_called()
            
            assert content == "Success content from requests"
            assert method == "requests"
    
    def test_falls_back_to_httpx(self):
        """Should fall back to httpx when requests fails."""
        with patch.object(scrape_module, 'scrape_with_requests') as mock_req, \
             patch.object(scrape_module, 'scrape_with_httpx') as mock_httpx, \
             patch.object(scrape_module, 'scrape_with_playwright') as mock_pw:
            
            mock_req.return_value = (None, "HTTP 403")
            mock_httpx.return_value = ("Success from httpx", None)
            
            content, method = scrape_module.scrape_page("https://medium-site.com")
            
            mock_req.assert_called_once()
            mock_httpx.assert_called_once()
            mock_pw.assert_not_called()
            
            assert content == "Success from httpx"
            assert method == "httpx"
    
    def test_falls_back_to_playwright(self):
        """Should fall back to playwright when httpx fails."""
        with patch.object(scrape_module, 'scrape_with_requests') as mock_req, \
             patch.object(scrape_module, 'scrape_with_httpx') as mock_httpx, \
             patch.object(scrape_module, 'scrape_with_playwright') as mock_pw:
            
            mock_req.return_value = (None, "HTTP 403")
            mock_httpx.return_value = (None, "HTTP 403")
            mock_pw.return_value = ("Success from browser", None)
            
            content, method = scrape_module.scrape_page("https://protected-site.com")
            
            assert content == "Success from browser"
            assert method == "browser"


# ============================================================================
# LINK EXTRACTION TESTS (MOCKED)
# ============================================================================
class TestExtractLinksFromHomepage:
    """Tests for link extraction with mocked responses."""
    
    def test_returns_base_url_on_failure(self):
        """Should return at least the base URL if extraction fails."""
        with patch('primr.data.scrape.get_html_requests') as mock_req, \
             patch('primr.data.scrape.get_html_httpx') as mock_httpx, \
             patch('primr.data.scrape.get_html_playwright') as mock_pw:
            
            mock_req.side_effect = Exception("Failed")
            mock_httpx.side_effect = Exception("Failed")
            mock_pw.side_effect = Exception("Failed")
            
            result = extract_links_from_homepage("https://example.com", "Example Corp")
            
            assert "https://example.com" in result
    
    def test_extracts_internal_links(self):
        """Should extract internal links from HTML."""
        with patch('primr.data.scrape.get_html_requests') as mock_req, \
             patch('primr.data.scrape.llm') as mock_llm:
            
            mock_req.return_value = MOCK_HTML_WITH_LINKS
            mock_llm.return_value = "https://example.com/about\nhttps://example.com/products"
            
            result = extract_links_from_homepage("https://example.com", "Example Corp")
            
            assert "https://example.com" in result
    
    def test_filters_excluded_keywords(self):
        """Should filter out URLs with excluded keywords."""
        with patch('primr.data.scrape.get_html_requests') as mock_req, \
             patch('primr.data.scrape.llm') as mock_llm:
            
            mock_req.return_value = MOCK_HTML_WITH_LINKS
            mock_llm.return_value = "https://example.com/about\nhttps://example.com/products"
            
            result = extract_links_from_homepage("https://example.com", "Example Corp")
            
            result_str = " ".join(result)
            assert "login" not in result_str.lower()
            assert "careers" not in result_str.lower()
            assert "privacy" not in result_str.lower()
    
    def test_excludes_external_links(self):
        """Should not include external links."""
        with patch('primr.data.scrape.get_html_requests') as mock_req, \
             patch('primr.data.scrape.llm') as mock_llm:
            
            mock_req.return_value = MOCK_HTML_WITH_LINKS
            mock_llm.return_value = "https://example.com/about"
            
            result = extract_links_from_homepage("https://example.com", "Example Corp")
            
            assert "external.com" not in " ".join(result)


# ============================================================================
# SOFT BLOCK DETECTION TESTS
# ============================================================================
class TestSoftBlockDetection:
    """Tests for soft block detection."""
    
    def test_detects_captcha(self):
        """Should detect captcha pages."""
        soup = BeautifulSoup(MOCK_HTML_CAPTCHA, "html.parser")
        text = extract_clean_text(soup)
        
        is_blocked, reason = detect_soft_block(text)
        assert is_blocked is True
        assert reason is not None
    
    def test_detects_access_denied(self):
        """Should detect access denied pages."""
        soup = BeautifulSoup(MOCK_HTML_BLOCKED, "html.parser")
        text = extract_clean_text(soup)
        
        is_blocked, reason = detect_soft_block(text)
        assert is_blocked is True
    
    def test_allows_valid_content(self):
        """Should allow valid content through."""
        soup = BeautifulSoup(MOCK_HTML_SIMPLE, "html.parser")
        text = extract_clean_text(soup)
        
        is_blocked, reason = detect_soft_block(text)
        assert is_blocked is False
        assert reason is None
    
    def test_detects_empty_response(self):
        """Should detect empty responses as blocked."""
        is_blocked, reason = detect_soft_block("")
        assert is_blocked is True
        
        is_blocked, reason = detect_soft_block(None)
        assert is_blocked is True
    
    def test_detects_short_content(self):
        """Should detect suspiciously short content."""
        is_blocked, reason = detect_soft_block("OK")
        assert is_blocked is True
        assert "short" in reason.lower()


# ============================================================================
# CONTENT EXTRACTION TESTS
# ============================================================================
class TestContentExtraction:
    """Tests for HTML content extraction."""
    
    def test_removes_scripts(self):
        """Should remove script tags."""
        html = "<html><body><script>alert('bad')</script><p>Good content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)
        
        assert "alert" not in text
        assert "Good content" in text
    
    def test_removes_styles(self):
        """Should remove style tags."""
        html = "<html><body><style>.bad{color:red}</style><p>Good content</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)
        
        assert ".bad" not in text
        assert "Good content" in text
    
    def test_removes_nav_footer(self):
        """Should remove navigation and footer."""
        html = """
        <html><body>
            <nav>Navigation links</nav>
            <main><p>Main content here</p></main>
            <footer>Footer stuff</footer>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)
        
        assert "Navigation links" not in text
        assert "Footer stuff" not in text
        assert "Main content" in text
    
    def test_deduplicates_lines(self):
        """Should remove duplicate consecutive lines."""
        html = "<html><body><p>Same line</p><p>Same line</p><p>Different</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        text = extract_clean_text(soup)
        
        assert text.count("Same line") == 1
        assert "Different" in text


# ============================================================================
# CACHE TESTS
# ============================================================================
class TestCaching:
    """Tests for caching functionality."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()
    
    def test_memory_cache(self):
        """Should cache in memory."""
        url = "https://memory-test.com"
        content = "Test content for memory cache"
        
        cache_content(url, content)
        cached = get_cached_content(url)
        
        assert cached == content
    
    def test_cache_miss(self):
        """Should return None for uncached URLs."""
        cached = get_cached_content("https://never-cached.com")
        assert cached is None
    
    def test_clear_cache(self):
        """Should clear all cached content."""
        cache_content("https://test1.com", "Content 1")
        cache_content("https://test2.com", "Content 2")
        
        clear_cache()
        
        assert get_cached_content("https://test1.com") is None
        assert get_cached_content("https://test2.com") is None
