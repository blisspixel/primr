"""
HTTP-based scrapers returning ScrapeResult.

Each function returns a ScrapeResult with raw bytes.
Success signal check is applied by orchestrator (not here).
"""

import logging
import time

from .config import (
    DEFAULT_TIMEOUT_CURL_CFFI,
    DEFAULT_TIMEOUT_HTTPX,
    DEFAULT_TIMEOUT_REQUESTS,
)
from .models import Attempt, ErrorType, ScrapeResult
from .net import get_default_headers
from .profiles import HttpHeaderProfile, get_random_http_profile

logger = logging.getLogger(__name__)


def scrape_with_requests(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_REQUESTS,
    profile: HttpHeaderProfile | None = None,
    cookies: dict | None = None,
) -> ScrapeResult:
    """
    Scrape URL using requests library.

    Tier 1: Basic HTTP client, fast but easily detected.

    Args:
        url: URL to scrape
        timeout: Request timeout in seconds
        profile: Optional HTTP header profile
        cookies: Optional cookies to send

    Returns:
        ScrapeResult with raw bytes on success
    """
    import requests

    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="requests",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url
    start_time = time.time()
    tier_name = "requests"

    if profile is None:
        profile = get_random_http_profile()

    headers = get_default_headers(profile)

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            cookies=cookies,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        # SSRF protection: validate final URL after redirects
        final_url = str(response.url)
        from primr.utils.security import validate_final_url_after_redirect
        is_safe, redirect_error = validate_final_url_after_redirect(final_url)
        if not is_safe:
            attempt = Attempt(
                tier=tier_name,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"Redirect to unsafe URL blocked: {redirect_error}",
                elapsed_ms=elapsed_ms,
            )
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"SSRF protection: redirect to {final_url} blocked - {redirect_error}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[attempt],
            )

        attempt = Attempt(
            tier=tier_name,
            success=True,
            elapsed_ms=elapsed_ms,
            http_status=response.status_code,
        )

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            http_status=response.status_code,
            final_url=final_url,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except requests.Timeout as e:
        elapsed_ms = (time.time() - start_time) * 1000

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=ErrorType.TIMEOUT,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.TIMEOUT,
            error=f"Request timeout after {timeout}s",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except requests.ConnectionError as e:
        elapsed_ms = (time.time() - start_time) * 1000

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Connection error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except requests.RequestException as e:
        elapsed_ms = (time.time() - start_time) * 1000

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Request error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )


def scrape_with_httpx(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_HTTPX,
    profile: HttpHeaderProfile | None = None,
    cookies: dict | None = None,
) -> ScrapeResult:
    """
    Scrape URL using httpx library.

    Tier 2: Modern async-capable HTTP client with HTTP/2 support.

    Args:
        url: URL to scrape
        timeout: Request timeout in seconds
        profile: Optional HTTP header profile
        cookies: Optional cookies to send

    Returns:
        ScrapeResult with raw bytes on success
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="httpx",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url

    try:
        import httpx
    except ImportError:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="httpx not installed",
            tier="httpx",
            attempts=[],
        )

    start_time = time.time()
    tier_name = "httpx"

    if profile is None:
        profile = get_random_http_profile()

    headers = get_default_headers(profile)

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            http2=True,
        ) as client:
            response = client.get(
                url,
                headers=headers,
                cookies=cookies,
            )

        elapsed_ms = (time.time() - start_time) * 1000

        # SSRF protection: validate final URL after redirects
        final_url = str(response.url)
        from primr.utils.security import validate_final_url_after_redirect
        is_safe, redirect_error = validate_final_url_after_redirect(final_url)
        if not is_safe:
            attempt = Attempt(
                tier=tier_name,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"Redirect to unsafe URL blocked: {redirect_error}",
                elapsed_ms=elapsed_ms,
            )
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"SSRF protection: redirect to {final_url} blocked - {redirect_error}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[attempt],
            )

        attempt = Attempt(
            tier=tier_name,
            success=True,
            elapsed_ms=elapsed_ms,
            http_status=response.status_code,
        )

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            http_status=response.status_code,
            final_url=final_url,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except httpx.TimeoutException as e:
        elapsed_ms = (time.time() - start_time) * 1000

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=ErrorType.TIMEOUT,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.TIMEOUT,
            error=f"HTTPX timeout after {timeout}s",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except httpx.ConnectError as e:
        elapsed_ms = (time.time() - start_time) * 1000

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Connection error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except httpx.HTTPError as e:
        elapsed_ms = (time.time() - start_time) * 1000

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"HTTP error: {e}",
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )


def scrape_with_curl_cffi(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_CURL_CFFI,
    profile: HttpHeaderProfile | None = None,
    cookies: dict | None = None,
    impersonate: str = "chrome120",
) -> ScrapeResult:
    """
    Scrape URL using curl_cffi with TLS fingerprint impersonation.

    Tier 3: Advanced HTTP client that mimics browser TLS fingerprints.

    Args:
        url: URL to scrape
        timeout: Request timeout in seconds
        profile: Optional HTTP header profile (headers match impersonation)
        cookies: Optional cookies to send
        impersonate: Browser to impersonate (chrome120, chrome119, etc.)

    Returns:
        ScrapeResult with raw bytes on success
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error=f"Invalid URL: {error}",
            tier="curl_cffi",
            elapsed_ms=0,
            attempts=[],
        )

    url = normalized_url

    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return ScrapeResult(
            url=url,
            success=False,
            error_type=ErrorType.NETWORK_ERROR,
            error="curl_cffi not installed",
            tier="curl_cffi",
            attempts=[],
        )

    start_time = time.time()
    tier_name = "curl_cffi"

    if profile is None:
        profile = get_random_http_profile()

    # curl_cffi handles most headers via impersonation, but we can add extras
    headers = {
        "Accept-Language": profile.accept_language,
    }

    try:
        response = curl_requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
            cookies=cookies,
            impersonate=impersonate,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        # SSRF protection: validate final URL after redirects
        final_url = str(response.url)
        from primr.utils.security import validate_final_url_after_redirect
        is_safe, redirect_error = validate_final_url_after_redirect(final_url)
        if not is_safe:
            attempt = Attempt(
                tier=tier_name,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"Redirect to unsafe URL blocked: {redirect_error}",
                elapsed_ms=elapsed_ms,
            )
            return ScrapeResult(
                url=url,
                success=False,
                error_type=ErrorType.NETWORK_ERROR,
                error=f"SSRF protection: redirect to {final_url} blocked - {redirect_error}",
                tier=tier_name,
                elapsed_ms=elapsed_ms,
                attempts=[attempt],
            )

        attempt = Attempt(
            tier=tier_name,
            success=True,
            elapsed_ms=elapsed_ms,
            http_status=response.status_code,
        )

        return ScrapeResult(
            url=url,
            success=True,
            raw_content=response.content,
            content_type=response.headers.get("Content-Type", ""),
            http_status=response.status_code,
            final_url=final_url,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000

        error_str = str(e).lower()
        if "timeout" in error_str:
            error_type = ErrorType.TIMEOUT
            error_msg = f"curl_cffi timeout after {timeout}s"
        else:
            error_type = ErrorType.NETWORK_ERROR
            error_msg = f"curl_cffi error: {e}"

        attempt = Attempt(
            tier=tier_name,
            success=False,
            error_type=error_type,
            error=str(e),
            elapsed_ms=elapsed_ms,
        )

        return ScrapeResult(
            url=url,
            success=False,
            error_type=error_type,
            error=error_msg,
            tier=tier_name,
            elapsed_ms=elapsed_ms,
            attempts=[attempt],
        )


# Mapping of tier names to functions for registry
HTTP_TIERS = {
    "requests": scrape_with_requests,
    "httpx": scrape_with_httpx,
    "curl_cffi": scrape_with_curl_cffi,
}
