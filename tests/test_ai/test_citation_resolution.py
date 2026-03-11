"""
Tests for citation URL resolution functionality.

These tests verify that Google grounding redirect URLs are properly
resolved to their final destinations for readable citations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from primr.ai.deep_research import (
    resolve_citation_urls,
    resolve_citation_urls_sync,
    resolve_redirect_url,
)

# =============================================================================
# MOCK DATA - Based on real Deep Research API output
# =============================================================================

# Real redirect URL format from Gemini Deep Research API
SAMPLE_REDIRECT_URL = (
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
    "AUZIYQHiUPADByx59S7B3Rjb0UaBTII1Nu1EsZZP8zkDn_u3pbz1L7OZ9_mj4Zl3"
)

# Sample citations as returned by Deep Research API
SAMPLE_CITATIONS_WITH_REDIRECTS = [
    {
        "number": "1",
        "title": "partstown.com",
        "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC123",
    },
    {
        "number": "2",
        "title": "businesswire.com",
        "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEF456",
    },
    {
        "number": "3",
        "title": "forbes.com",
        "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/GHI789",
    },
]

# Expected resolved URLs
RESOLVED_URLS = {
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC123": "https://www.partstown.com/about-us",
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEF456": "https://www.businesswire.com/news/home/20240115",
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/GHI789": "https://www.forbes.com/companies/parts-town",
}


# =============================================================================
# UNIT TESTS - resolve_redirect_url
# =============================================================================


class TestResolveRedirectUrl:
    """Tests for the resolve_redirect_url async function."""

    @pytest.mark.asyncio
    async def test_non_redirect_url_returned_unchanged(self):
        """Non-redirect URLs should be returned as-is without HTTP calls."""
        normal_url = "https://www.partstown.com/about"
        result = await resolve_redirect_url(normal_url)
        assert result == normal_url

    @pytest.mark.asyncio
    async def test_empty_url_returned_unchanged(self):
        """Empty URLs should be returned as-is."""
        result = await resolve_redirect_url("")
        assert result == ""

    @pytest.mark.asyncio
    async def test_redirect_url_is_resolved(self):
        """Redirect URLs should be resolved via HTTP HEAD request."""
        redirect_url = SAMPLE_REDIRECT_URL
        final_url = "https://www.partstown.com/about-us"

        # Mock the httpx response
        mock_response = MagicMock()
        mock_response.url = final_url

        with patch.object(httpx, "AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.head = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await resolve_redirect_url(redirect_url)
            assert result == final_url

    @pytest.mark.asyncio
    async def test_timeout_returns_original_url(self):
        """On timeout, original URL should be returned."""
        redirect_url = SAMPLE_REDIRECT_URL

        with patch.object(httpx, "AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.head = AsyncMock(side_effect=TimeoutError())
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await resolve_redirect_url(redirect_url)
            assert result == redirect_url

    @pytest.mark.asyncio
    async def test_http_error_returns_original_url(self):
        """On HTTP error, original URL should be returned."""
        redirect_url = SAMPLE_REDIRECT_URL

        with patch.object(httpx, "AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.head = AsyncMock(side_effect=Exception("Connection failed"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await resolve_redirect_url(redirect_url)
            assert result == redirect_url


# =============================================================================
# UNIT TESTS - resolve_citation_urls
# =============================================================================


class TestResolveCitationUrls:
    """Tests for the resolve_citation_urls async function."""

    @pytest.mark.asyncio
    async def test_empty_citations_returns_empty(self):
        """Empty citation list should return empty list."""
        result = await resolve_citation_urls([])
        assert result == []

    @pytest.mark.asyncio
    async def test_citations_with_non_redirect_urls_unchanged(self):
        """Citations with normal URLs should pass through unchanged."""
        citations = [{"number": "1", "title": "Test", "url": "https://www.example.com/page"}]

        result = await resolve_citation_urls(citations)

        # Non-redirect URLs should be unchanged
        assert result[0]["url"] == "https://www.example.com/page"

    @pytest.mark.asyncio
    async def test_multiple_citations_processed(self):
        """Multiple citations should all be processed."""
        citations = [
            {"number": "1", "title": "Test1", "url": "https://example1.com"},
            {"number": "2", "title": "Test2", "url": "https://example2.com"},
            {"number": "3", "title": "Test3", "url": "https://example3.com"},
        ]

        result = await resolve_citation_urls(citations)

        assert len(result) == 3
        assert result[0]["url"] == "https://example1.com"
        assert result[1]["url"] == "https://example2.com"
        assert result[2]["url"] == "https://example3.com"


# =============================================================================
# UNIT TESTS - resolve_citation_urls_sync
# =============================================================================


class TestResolveCitationUrlsSync:
    """Tests for the synchronous wrapper function."""

    def test_empty_citations_returns_empty(self):
        """Empty citation list should return empty list."""
        result = resolve_citation_urls_sync([])
        assert result == []

    def test_non_redirect_urls_pass_through(self):
        """Non-redirect URLs should pass through unchanged."""
        citations = [{"number": "1", "title": "Test", "url": "https://example.com/page"}]

        result = resolve_citation_urls_sync(citations)

        assert result[0]["url"] == "https://example.com/page"


# =============================================================================
# INTEGRATION TESTS - Citation formatting with URL resolution
# =============================================================================


class TestCitationFormattingIntegration:
    """Integration tests for citation formatting with URL resolution."""

    def test_format_numbered_citations_with_resolved_urls(self):
        """Test that ReportFormatter uses resolved URLs in output."""
        from primr.ai.deep_research import ReportFormatter

        formatter = ReportFormatter()

        # Content with inline citations and Sources section
        content = """
## Executive Summary

Parts Town is a leading distributor. [cite: 1, 2]

**Sources:**
1. [partstown.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC)
2. [businesswire.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/DEF)
"""

        # Citations with resolved URLs
        citations = [
            {"number": "1", "title": "partstown.com", "url": "https://www.partstown.com/about"},
            {
                "number": "2",
                "title": "businesswire.com",
                "url": "https://www.businesswire.com/news",
            },
        ]

        result = formatter._format_numbered_citations(content, citations)

        # Check inline citations are converted
        assert "[1] [2]" in result
        assert "[cite:" not in result

        # Check Sources section uses resolved URLs
        assert "https://www.partstown.com/about" in result
        assert "https://www.businesswire.com/news" in result
        assert "vertexaisearch.cloud.google.com" not in result

    def test_format_preserves_citation_titles(self):
        """Test that citation titles are preserved in output."""
        from primr.ai.deep_research import ReportFormatter

        formatter = ReportFormatter()

        content = """
**Sources:**
1. [Parts Town Official](https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC)
"""

        citations = [
            {"number": "1", "title": "Parts Town Official", "url": "https://www.partstown.com"},
        ]

        result = formatter._format_numbered_citations(content, citations)

        # Title should be preserved
        assert "Parts Town Official" in result

    def test_format_uses_domain_for_ugly_titles(self):
        """Test that domain is used when title contains redirect URL."""
        from primr.ai.deep_research import ReportFormatter

        formatter = ReportFormatter()

        content = """
**Sources:**
1. [vertexaisearch.cloud.google.com](https://example.com/page)
"""

        citations = [
            {
                "number": "1",
                "title": "vertexaisearch.cloud.google.com",
                "url": "https://www.partstown.com/page",
            },
        ]

        result = formatter._format_numbered_citations(content, citations)

        # Should use domain from resolved URL, not the ugly title
        assert "partstown.com" in result


# =============================================================================
# AI STRATEGY CITATION TESTS
# =============================================================================


class TestAIStrategyCitationProcessing:
    """Tests for AI strategy citation processing."""

    def test_process_citations_converts_inline_format(self):
        """Test that inline [cite: X, Y] format is converted."""
        from primr.core.ai_strategy import _process_citations

        content = "This is important. [cite: 1, 2, 3] More text."

        result = _process_citations(content)

        assert "[1] [2] [3]" in result
        assert "[cite:" not in result

    def test_process_citations_handles_no_sources_section(self):
        """Test graceful handling when no Sources section exists."""
        from primr.core.ai_strategy import _process_citations

        content = "Content without sources section."

        result = _process_citations(content)

        assert result == content

    def test_process_citations_with_sources_section(self):
        """Test that Sources section is processed."""
        from primr.core.ai_strategy import _process_citations

        content = """
Some content.

**Sources:**
1. [example.com](https://www.example.com/page)
"""

        result = _process_citations(content)

        # Should still contain the sources section
        assert "**Sources:**" in result
        assert "example.com" in result
