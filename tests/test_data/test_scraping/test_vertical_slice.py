"""Tests for vertical slice checkpoint - proves end-to-end flow."""

import pytest
from unittest.mock import Mock, patch
import tempfile
import os

from primr.data.scraping.vertical_slice import scrape_single_url
from primr.data.scraping.cache import ScrapeCache
from primr.data.scraping.trace import TraceLogger
from primr.data.scraping.models import ErrorType


class TestVerticalSlice:
    """Tests for the vertical slice minimal orchestrator."""
    
    def test_successful_scrape_flow(self):
        """Should complete full flow: request → detection → content → validation."""
        mock_response = Mock()
        mock_response.content = b"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <main>
                <h1>Test Content</h1>
                <p>This is a test page with enough content to pass validation.</p>
                <p>It has multiple paragraphs and good structure.</p>
                <p>The content is meaningful and not just boilerplate.</p>
            </main>
        </body>
        </html>
        """
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"
        
        with patch("requests.get", return_value=mock_response):
            result = scrape_single_url("https://example.com")
        
        assert result.success is True
        assert result.raw_content is not None
        assert result.extracted_text is not None
        assert result.tier == "requests"
        assert result.cached is False
    
    def test_cache_hit_on_second_request(self):
        """Should return cached result on second request."""
        mock_response = Mock()
        mock_response.content = b"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <main>
                <h1>Test Content</h1>
                <p>This is a test page with enough content.</p>
            </main>
        </body>
        </html>
        """
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ScrapeCache(memory_size=100, cache_dir=tmpdir)
            
            with patch("requests.get", return_value=mock_response) as mock_get:
                # First request
                result1 = scrape_single_url("https://example.com", cache=cache)
                assert result1.cached is False
                assert mock_get.call_count == 1
                
                # Second request - should hit cache
                result2 = scrape_single_url("https://example.com", cache=cache)
                assert result2.cached is True
                assert mock_get.call_count == 1  # No additional request
    
    def test_detects_soft_block(self):
        """Should detect soft blocks and fail."""
        mock_response = Mock()
        mock_response.content = b"""
        <html>
        <head><title>Just a moment...</title></head>
        <body>
            <h1>Checking your browser</h1>
            <p>Please wait while we verify you are human.</p>
            <p>Cloudflare protection</p>
        </body>
        </html>
        """
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"
        
        with patch("requests.get", return_value=mock_response):
            result = scrape_single_url("https://example.com")
        
        assert result.success is False
        assert result.error_type == ErrorType.SOFT_BLOCK
        assert result.blocked_reason is not None
    
    def test_writes_trace_log(self):
        """Should write trace log entries."""
        mock_response = Mock()
        mock_response.content = b"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <main>
                <h1>Test Content</h1>
                <p>This is a test page with enough content.</p>
            </main>
        </body>
        </html>
        """
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_logger = TraceLogger(
                company_name="test_company",
                output_dir=tmpdir,
            )
            
            with patch("requests.get", return_value=mock_response):
                result = scrape_single_url(
                    "https://example.com",
                    trace_logger=trace_logger,
                )
            
            # Verify trace file exists
            trace_path = trace_logger.get_path()
            assert os.path.exists(trace_path)
            
            # Verify content
            with open(trace_path, "r") as f:
                content = f.read()
            
            assert "example.com" in content
            assert "test_company" in content
    
    def test_handles_network_error(self):
        """Should handle network errors gracefully."""
        import requests
        
        with patch("requests.get", side_effect=requests.ConnectionError("Failed")):
            result = scrape_single_url("https://example.com")
        
        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR
    
    def test_handles_timeout(self):
        """Should handle timeout errors."""
        import requests
        
        with patch("requests.get", side_effect=requests.Timeout("Timeout")):
            result = scrape_single_url("https://example.com", timeout=5)
        
        assert result.success is False
        assert result.error_type == ErrorType.TIMEOUT
    
    def test_extracts_text_content(self):
        """Should extract clean text from HTML."""
        mock_response = Mock()
        mock_response.content = b"""
        <html>
        <head>
            <title>Test Page</title>
            <script>var x = 1;</script>
            <style>.foo { color: red; }</style>
        </head>
        <body>
            <nav>Home | About | Contact</nav>
            <main>
                <h1>Main Heading</h1>
                <p>This is the main content of the page.</p>
            </main>
            <footer>Copyright 2025</footer>
        </body>
        </html>
        """
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"
        
        with patch("requests.get", return_value=mock_response):
            result = scrape_single_url("https://example.com")
        
        assert result.success is True
        assert result.extracted_text is not None
        assert "Main Heading" in result.extracted_text
        assert "main content" in result.extracted_text
        # Script content should be removed
        assert "var x" not in result.extracted_text
    
    def test_validates_content(self):
        """Should include validation result."""
        mock_response = Mock()
        mock_response.content = b"""
        <html>
        <head><title>Test Page</title></head>
        <body>
            <main>
                <h1>Test Content</h1>
                <p>This is a test page with enough content to pass validation.</p>
                <p>It has multiple paragraphs and good structure.</p>
                <p>The content is meaningful and not just boilerplate.</p>
                <p>Adding more content to ensure density is good.</p>
            </main>
        </body>
        </html>
        """
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.status_code = 200
        mock_response.url = "https://example.com/"
        
        with patch("requests.get", return_value=mock_response):
            result = scrape_single_url("https://example.com")
        
        assert result.success is True
        assert result.validation is not None
        assert result.validation.content_density is not None


class TestModuleBoundaries:
    """Tests verifying module boundaries are correct."""
    
    def test_no_circular_imports(self):
        """Should be able to import all modules without circular import errors."""
        # These imports should all work without errors
        from primr.data.scraping import models
        from primr.data.scraping import config
        from primr.data.scraping import profiles
        from primr.data.scraping import cache
        from primr.data.scraping import trace
        from primr.data.scraping import rate_limiter
        from primr.data.scraping import detection
        from primr.data.scraping import validation
        from primr.data.scraping import content
        from primr.data.scraping import net
        from primr.data.scraping import http_clients
        from primr.data.scraping import vertical_slice
        
        # If we get here, no circular imports
        assert True
    
    def test_models_has_no_dependencies_on_other_modules(self):
        """Models module should not import from other scraping modules."""
        import primr.data.scraping.models as models
        
        # Check that models doesn't import from other scraping modules
        # (it should only use stdlib)
        module_source = models.__file__
        with open(module_source, "r") as f:
            source = f.read()
        
        # Should not have imports from sibling modules
        assert "from .cache" not in source
        assert "from .detection" not in source
        assert "from .http_clients" not in source
