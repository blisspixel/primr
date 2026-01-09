"""
Tests for resilient link discovery in scraping module.

The link discovery system uses multiple strategies to find pages:
1. Sitemap.xml parsing
2. Common URL pattern guessing + verification
3. HTML link extraction

These tests verify the discovery functions work correctly.
"""

import pytest
from unittest.mock import patch, MagicMock

from primr.data.scrape import (
    fetch_sitemap_links,
    guess_common_urls,
    verify_urls_exist,
    extract_links_from_html,
    detect_waf_block,
    detect_soft_block,
    normalize_url,
    COMMON_PAGE_PATTERNS,
)


class TestSitemapFetching:
    """Tests for sitemap.xml link extraction."""
    
    def test_fetch_sitemap_returns_all_links(self):
        """Sitemap should return ALL links, not an arbitrary subset."""
        sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
            <url><loc>https://example.com/page3</loc></url>
            <url><loc>https://example.com/about</loc></url>
            <url><loc>https://example.com/investors</loc></url>
        </urlset>"""
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = sitemap_xml
        
        with patch('primr.data.scraping.discovery.make_request', return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")
            
            # Should get ALL 5 links
            assert len(links) == 5
            assert "https://example.com/about" in links
            assert "https://example.com/investors" in links
    
    def test_fetch_sitemap_handles_missing(self):
        """Should return empty set if no sitemap exists."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch('primr.data.scraping.discovery.make_request', return_value=mock_response):
            links = fetch_sitemap_links("https://example.com")
            assert len(links) == 0


class TestCommonURLGuessing:
    """Tests for common URL pattern guessing."""
    
    def test_guess_common_urls_generates_patterns(self):
        """Should generate URLs for all common patterns."""
        urls = guess_common_urls("https://example.com")
        
        # Should have many URLs
        assert len(urls) >= 50
        
        # Check some expected patterns
        assert "https://example.com/about" in urls
        assert "https://example.com/investors" in urls
        assert "https://example.com/news" in urls
    
    def test_common_patterns_cover_key_areas(self):
        """Common patterns should cover key business research areas."""
        patterns_str = " ".join(COMMON_PAGE_PATTERNS)
        
        assert "about" in patterns_str
        assert "investor" in patterns_str
        assert "leadership" in patterns_str or "team" in patterns_str
        assert "product" in patterns_str or "service" in patterns_str
        assert "news" in patterns_str


class TestURLVerification:
    """Tests for URL existence verification."""
    
    def test_verify_urls_checks_provided(self):
        """Should check provided URLs."""
        test_urls = {"https://example.com/page1", "https://example.com/page2"}
        
        with patch('primr.data.scraping.discovery.head_exists', return_value=True):
            verified = verify_urls_exist(test_urls)
            assert len(verified) == 2
    
    def test_verify_urls_filters_missing(self):
        """Should filter out URLs that don't exist."""
        test_urls = {"https://example.com/exists", "https://example.com/missing"}
        
        def mock_head_exists(url, **kwargs):
            return "exists" in url
        
        with patch('primr.data.scraping.discovery.head_exists', side_effect=mock_head_exists):
            verified = verify_urls_exist(test_urls)
            assert len(verified) == 1
            assert "https://example.com/exists" in verified


class TestWAFDetection:
    """Tests for WAF/bot protection detection."""
    
    def test_detect_waf_block_wirewall(self):
        """Should detect WireWall protection pages."""
        html = "<html><title>Access Restricted - WireWall</title></html>"
        is_blocked, reason = detect_waf_block(html)
        assert is_blocked
    
    def test_detect_waf_block_cloudflare(self):
        """Should detect Cloudflare challenge pages."""
        html = "<html>Just a moment... Checking your browser. Ray ID: abc123</html>"
        is_blocked, reason = detect_waf_block(html)
        assert is_blocked
    
    def test_detect_waf_block_captcha(self):
        """Should detect CAPTCHA pages."""
        html = "<html>Please verify you are human by completing the CAPTCHA</html>"
        is_blocked, reason = detect_waf_block(html)
        assert is_blocked
    
    def test_detect_waf_block_real_content(self):
        """Should NOT flag real content as blocked."""
        html = "<html><body>" + "Real content " * 500 + "</body></html>"
        is_blocked, reason = detect_waf_block(html)
        assert not is_blocked
    
    def test_detect_waf_block_empty(self):
        """Should flag empty responses as blocked."""
        is_blocked, reason = detect_waf_block("")
        assert is_blocked


class TestSoftBlockDetection:
    """Tests for soft block detection (200 OK but fake content)."""
    
    def test_detect_soft_block_access_denied(self):
        """Should detect access denied messages."""
        html = "Access Denied - You don't have permission to view this page"
        is_blocked, reason = detect_soft_block(html, "https://example.com")
        assert is_blocked
    
    def test_detect_soft_block_real_content(self):
        """Should NOT flag real content."""
        html = "This is a real page with lots of content. " * 100
        is_blocked, reason = detect_soft_block(html, "https://example.com")
        assert not is_blocked


class TestHTMLLinkExtraction:
    """Tests for extracting links from HTML content."""
    
    def test_extract_links_from_anchors(self):
        """Should extract links from anchor tags."""
        html = """
        <html>
        <body>
            <a href="/about">About</a>
            <a href="/products">Products</a>
        </body>
        </html>
        """
        
        links = extract_links_from_html(html, "https://example.com")
        
        assert "https://example.com/about" in links
        assert "https://example.com/products" in links
    
    def test_extract_links_skips_external(self):
        """Should skip external links by default."""
        html = """
        <html>
        <body>
            <a href="/about">About</a>
            <a href="https://other.com/external">External</a>
        </body>
        </html>
        """
        
        links = extract_links_from_html(html, "https://example.com")
        
        assert "https://example.com/about" in links
        assert "https://other.com/external" not in links


class TestURLNormalization:
    """Tests for URL normalization."""
    
    def test_normalize_removes_trailing_slash(self):
        """Should remove trailing slashes for consistency."""
        assert normalize_url("https://example.com/about/") == "https://example.com/about"
    
    def test_normalize_removes_fragments(self):
        """Should remove URL fragments."""
        assert normalize_url("https://example.com/about#team") == "https://example.com/about"
    
    def test_normalize_preserves_query_strings(self):
        """Should preserve query strings."""
        normalized = normalize_url("https://example.com/search?q=test")
        assert "q=test" in normalized
