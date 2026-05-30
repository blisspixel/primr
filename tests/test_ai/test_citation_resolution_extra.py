"""Supplemental tests for primr.ai.citation_resolution.

These cover branches not exercised by the existing
test_citation_resolution.py file: scheme/host/path safety gates, SSRF
blocking, base64 fallback decoding, and the thread-pool sync wrapper
path when an event loop is already running.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from primr.ai.citation_resolution import (
    _extract_domain_from_redirect,
    resolve_citation_urls,
    resolve_citation_urls_sync,
    resolve_redirect_url,
)

# ---------------------------------------------------------------------------
# Safety-gate branches in resolve_redirect_url
# ---------------------------------------------------------------------------


class TestSafetyGates:
    @pytest.mark.asyncio
    async def test_non_google_host_returned_unchanged(self):
        url = "https://other.example/grounding-api-redirect/x"
        assert await resolve_redirect_url(url) == url

    @pytest.mark.asyncio
    async def test_wrong_path_returned_unchanged(self):
        url = "https://vertexaisearch.cloud.google.com/somewhere-else"
        assert await resolve_redirect_url(url) == url

    @pytest.mark.asyncio
    async def test_non_https_scheme_returned_unchanged(self):
        url = "http://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        assert await resolve_redirect_url(url) == url

    @pytest.mark.asyncio
    async def test_ssrf_blocks_initial_url(self):
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        with patch(
            "primr.utils.security.is_safe_url",
            return_value=(False, "private CIDR"),
        ):
            assert await resolve_redirect_url(url) == url

    @pytest.mark.asyncio
    async def test_final_url_blocked_returns_original(self):
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        response = MagicMock(url="http://internal.local/xyz")
        async_client = MagicMock()
        async_client.head = AsyncMock(return_value=response)
        async_client.__aenter__ = AsyncMock(return_value=async_client)
        async_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch(
                "primr.utils.security.validate_final_url_after_redirect",
                return_value=(False, "private network"),
            ),
            patch("httpx.AsyncClient", return_value=async_client),
        ):
            result = await resolve_redirect_url(url)
        assert result == url


# ---------------------------------------------------------------------------
# _extract_domain_from_redirect
# ---------------------------------------------------------------------------


class TestExtractDomainFromRedirect:
    def test_decodes_base64_payload(self):
        target = "https://example.com/article"
        encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
        redirect = f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/{encoded}"
        assert _extract_domain_from_redirect(redirect) == target

    def test_returns_original_when_no_match(self):
        url = "https://other.example/nothing"
        assert _extract_domain_from_redirect(url) == url

    def test_returns_original_when_payload_garbage(self):
        # Characters that are valid base64 but decode to garbage with no URL.
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AAAAAAAA"
        result = _extract_domain_from_redirect(url)
        # Should return the original since the decoded bytes contain no http(s) URL.
        assert result == url


# ---------------------------------------------------------------------------
# resolve_citation_urls behavior
# ---------------------------------------------------------------------------


class TestResolveCitationUrls:
    @pytest.mark.asyncio
    async def test_empty_resolved_url_preserves_original(self):
        citations = [{"url": "https://a.example"}]
        with patch(
            "primr.ai.citation_resolution.resolve_redirect_url",
            new=AsyncMock(return_value=""),
        ):
            result = await resolve_citation_urls(citations)
        assert result[0]["url"] == "https://a.example"

    @pytest.mark.asyncio
    async def test_resolves_each_url_via_helper(self):
        citations = [{"url": "https://a"}, {"url": "https://b"}]
        with patch(
            "primr.ai.citation_resolution.resolve_redirect_url",
            new=AsyncMock(side_effect=lambda u, **kw: u + "-x"),
        ):
            result = await resolve_citation_urls(citations)
        assert result[0]["url"].endswith("-x")
        assert result[1]["url"].endswith("-x")


# ---------------------------------------------------------------------------
# resolve_citation_urls_sync — inside-loop path
# ---------------------------------------------------------------------------


class TestResolveCitationUrlsSyncInsideLoop:
    def test_uses_thread_pool_when_loop_running(self):
        """Force the inside-loop branch via patching get_running_loop."""
        citations = [{"url": "https://x"}]
        with (
            patch(
                "primr.ai.citation_resolution.asyncio.get_running_loop",
                return_value=MagicMock(),
            ),
            patch(
                "primr.ai.citation_resolution.resolve_citation_urls",
                new=AsyncMock(return_value=[{"url": "https://x-done"}]),
            ),
        ):
            result = resolve_citation_urls_sync(citations)
        assert result[0]["url"] == "https://x-done"


# ---------------------------------------------------------------------------
# Timeout/retry branches
# ---------------------------------------------------------------------------


class TestTimeoutFallback:
    @pytest.mark.asyncio
    async def test_httpx_timeout_falls_back_to_extractor(self):
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
        async_client = MagicMock()
        async_client.head = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        async_client.__aenter__ = AsyncMock(return_value=async_client)
        async_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch("httpx.AsyncClient", return_value=async_client),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await resolve_redirect_url(url, timeout=0.01, retries=1)
        # Should fall back to the domain extractor; with no base64 payload to decode,
        # returns the original URL.
        assert result == url

    @pytest.mark.asyncio
    async def test_runtime_exception_retries_then_falls_back(self):
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"

        async_client = MagicMock()
        async_client.head = AsyncMock(side_effect=RuntimeError("boom"))
        async_client.__aenter__ = AsyncMock(return_value=async_client)
        async_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("primr.utils.security.is_safe_url", return_value=(True, "")),
            patch("httpx.AsyncClient", return_value=async_client),
            patch("asyncio.sleep", new=AsyncMock(return_value=None)),
        ):
            result = await resolve_redirect_url(url, retries=1)
        # Falls back to domain extractor (no decodable payload -> original URL)
        assert result == url


def test_module_loaded():
    # Sanity: confirm the symbols are available.
    assert callable(resolve_redirect_url)
    assert callable(resolve_citation_urls)
    assert callable(resolve_citation_urls_sync)
    assert callable(_extract_domain_from_redirect)


@pytest.mark.asyncio
async def test_unparseable_url_short_circuits():
    with patch(
        "primr.ai.citation_resolution.urlparse",
        side_effect=ValueError("bad url"),
    ):
        assert await resolve_redirect_url("anything") == "anything"


def test_sync_wrapper_without_loop_uses_asyncio_run():
    # When no event loop is running, the wrapper uses asyncio.run.
    with patch(
        "primr.ai.citation_resolution.resolve_citation_urls",
        new=AsyncMock(return_value=[{"url": "https://done"}]),
    ):
        # Ensure no loop is running (we're in a sync context already)
        result = resolve_citation_urls_sync([{"url": "https://input"}])
    assert result[0]["url"] == "https://done"


@pytest.mark.asyncio
async def test_happy_path_returns_resolved_url():
    url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    final = "https://example.com/article"

    response = MagicMock(url=final)
    async_client = MagicMock()
    async_client.head = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("primr.utils.security.is_safe_url", return_value=(True, "")),
        patch(
            "primr.utils.security.validate_final_url_after_redirect",
            return_value=(True, ""),
        ),
        patch("httpx.AsyncClient", return_value=async_client),
    ):
        result = await resolve_redirect_url(url)
    assert result == final


# Smoke check: an arbitrary string that doesn't look like a URL still returns cleanly.
def test_extract_domain_with_unmatched_string_returns_input():
    assert _extract_domain_from_redirect("not a url") == "not a url"


# Loop-related fixture cleanup so subsequent tests don't see a leaked loop.
@pytest.fixture(autouse=True)
def _cleanup_event_loops():
    yield
    # Defensive: close any loop the test created.
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except Exception:
        pass
