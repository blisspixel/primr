"""Google grounding redirect URL resolution for Deep Research citations.

Extracted from `primr.ai.deep_research` for isolated unit testing.

The Deep Research API returns citations as Google grounding redirect
URLs that need to be resolved to their actual destination domains.
These helpers do that resolution in parallel with SSRF protection,
falling back to base64-decoded domain extraction when the network
hop fails.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


async def resolve_redirect_url(url: str, timeout: float = 10.0, retries: int = 2) -> str:
    """Resolve a Google grounding redirect URL to its final destination.

    Returns the final destination URL, or the original URL if resolution fails.
    """
    import httpx

    from primr.data.safe_http import async_safe_http_head

    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if (parsed.hostname or "").lower() != "vertexaisearch.cloud.google.com":
        return url
    if not parsed.path.startswith("/grounding-api-redirect"):
        return url
    if parsed.scheme != "https":
        return url

    for attempt in range(retries + 1):
        try:
            _status, final_url, blocked = await async_safe_http_head(
                url,
                timeout=timeout,
                log_prefix="citation-resolver",
            )
            if blocked:
                return url
            if final_url:
                logger.debug(f"Resolved URL: {url[:50]}... -> {final_url[:80]}...")
                return final_url
            return _extract_domain_from_redirect(url)
        except (TimeoutError, httpx.TimeoutException):
            if attempt < retries:
                logger.debug(f"URL resolution timeout (attempt {attempt + 1}), retrying...")
                await asyncio.sleep(0.5)
                continue
            logger.warning(f"URL resolution timed out after {retries + 1} attempts: {url[:50]}...")
            return _extract_domain_from_redirect(url)
        except Exception as e:
            if attempt < retries:
                logger.debug(f"URL resolution failed (attempt {attempt + 1}): {e}, retrying...")
                await asyncio.sleep(0.5)
                continue
            logger.warning(f"URL resolution failed after {retries + 1} attempts: {e}")
            return _extract_domain_from_redirect(url)

    return url


def _extract_domain_from_redirect(redirect_url: str) -> str:
    """Extract a readable domain hint from a Google redirect URL.

    The redirect URL often contains a base64-encoded path segment that
    decodes to a URL we can use as a fallback when HEAD resolution fails.
    """
    try:
        match = re.search(r"/grounding-api-redirect/([A-Za-z0-9_-]+)", redirect_url)
        if match:
            encoded = match.group(1)
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            try:
                decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="ignore")
                url_match = re.search(r'https?://[^\s<>"\']+', decoded)
                if url_match:
                    decoded_url = url_match.group(0)
                    from primr.utils.security import is_safe_url

                    is_safe, unsafe_reason = is_safe_url(decoded_url)
                    if is_safe:
                        return decoded_url
                    logger.warning(
                        "Blocked unsafe decoded citation redirect fallback: %s",
                        unsafe_reason,
                    )
            except (ValueError, UnicodeDecodeError) as e:
                logger.debug("Failed to decode redirect URL base64: %s", e)
    except (re.error, ValueError, UnicodeDecodeError) as e:
        logger.debug("Failed to extract domain from redirect URL: %s", e)

    return redirect_url


async def resolve_citation_urls(
    citations: list[dict[str, str]],
    max_concurrency: int = 16,
) -> list[dict[str, str]]:
    """Resolve all citation URLs in parallel.

    ``citations`` comes from parsing the Sources section of LLM output, so
    its length is attacker-influenceable through prompt injection in
    scraped content. A bare ``asyncio.gather(*tasks)`` over that list lets
    a single research run spawn thousands of concurrent HEAD requests.
    Cap concurrency with a semaphore so the resolver scales linearly in
    runtime, not in peak FDs / sockets.
    """
    if not citations:
        return citations

    if max_concurrency < 1:
        max_concurrency = 1

    sem = asyncio.Semaphore(max_concurrency)

    async def _resolve_one(url: str) -> str:
        async with sem:
            return await resolve_redirect_url(url)

    tasks = [_resolve_one(c.get("url", "")) for c in citations]
    resolved_urls = await asyncio.gather(*tasks)

    for citation, resolved_url in zip(citations, resolved_urls, strict=False):
        if resolved_url:
            citation["url"] = resolved_url

    return citations


def resolve_citation_urls_sync(
    citations: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Synchronous wrapper for resolve_citation_urls.

    Uses asyncio.run() or a thread pool if an event loop is already running.
    """
    if not citations:
        return citations

    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, resolve_citation_urls(citations))
            return future.result(timeout=30)
    except RuntimeError:
        return asyncio.run(resolve_citation_urls(citations))
