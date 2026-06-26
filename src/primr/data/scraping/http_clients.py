"""
HTTP-based scrapers returning ScrapeResult.

Each function returns a ScrapeResult with raw bytes.
Success signal check is applied by orchestrator (not here).
"""

import logging
import time
from collections.abc import Mapping
from urllib.parse import urljoin

from .config import (
    DEFAULT_TIMEOUT_CURL_CFFI,
    DEFAULT_TIMEOUT_HTTPX,
    DEFAULT_TIMEOUT_REQUESTS,
)
from .models import Attempt, ErrorType, ScrapeResult
from .net import get_default_headers
from .profiles import HttpHeaderProfile, get_random_http_profile

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 10


def _redirect_location(response: object) -> str | None:
    headers_obj = getattr(response, "headers", {}) or {}
    location = _header_value(headers_obj, "Location") or _header_value(headers_obj, "location")
    return location if isinstance(location, str) and location else None


def _header_value(headers_obj: object, name: str) -> object:
    if isinstance(headers_obj, Mapping):
        return headers_obj.get(name)

    get = getattr(headers_obj, "get", None)
    if callable(get):
        return get(name)
    return None


def _blocked_redirect_result(
    *,
    url: str,
    tier_name: str,
    start_time: float,
    redirect_url: str,
    error: str | None,
) -> ScrapeResult:
    elapsed_ms = (time.time() - start_time) * 1000
    redirect_error = error or "URL blocked"
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
        error=f"SSRF protection: redirect to {redirect_url} blocked - {redirect_error}",
        tier=tier_name,
        elapsed_ms=elapsed_ms,
        attempts=[attempt],
    )


def _too_many_redirects_result(*, url: str, tier_name: str, start_time: float) -> ScrapeResult:
    elapsed_ms = (time.time() - start_time) * 1000
    error = f"Exceeded {_MAX_REDIRECTS} redirects"
    attempt = Attempt(
        tier=tier_name,
        success=False,
        error_type=ErrorType.NETWORK_ERROR,
        error=error,
        elapsed_ms=elapsed_ms,
    )
    return ScrapeResult(
        url=url,
        success=False,
        error_type=ErrorType.NETWORK_ERROR,
        error=error,
        tier=tier_name,
        elapsed_ms=elapsed_ms,
        attempts=[attempt],
    )


def _successful_scrape_result(
    *,
    url: str,
    tier_name: str,
    start_time: float,
    response: object,
    final_url: str | None = None,
) -> ScrapeResult:
    elapsed_ms = (time.time() - start_time) * 1000
    status_code = getattr(response, "status_code", None)
    headers_obj = getattr(response, "headers", {}) or {}
    content_type_value = _header_value(headers_obj, "Content-Type")
    content_type = content_type_value if isinstance(content_type_value, str) else ""
    attempt = Attempt(
        tier=tier_name,
        success=True,
        elapsed_ms=elapsed_ms,
        http_status=status_code,
    )

    return ScrapeResult(
        url=url,
        success=True,
        raw_content=getattr(response, "content", b""),
        content_type=content_type,
        http_status=status_code,
        final_url=final_url or str(getattr(response, "url", url)),
        tier=tier_name,
        elapsed_ms=elapsed_ms,
        attempts=[attempt],
    )


def _headers_for_pinned_request(headers: dict, host_header: str) -> dict:
    request_headers = dict(headers)
    request_headers["Host"] = host_header
    return request_headers


def _extensions_for_pinned_request(sni_hostname: str | None) -> dict | None:
    if sni_hostname is None:
        return None
    return {"sni_hostname": sni_hostname}


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
        current_url = url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            response = requests.get(
                current_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
                cookies=cookies,
            )

            location = _redirect_location(response)
            if response.status_code not in _REDIRECT_STATUSES or location is None:
                return _successful_scrape_result(
                    url=url,
                    tier_name=tier_name,
                    start_time=start_time,
                    response=response,
                )

            redirect_url = urljoin(str(getattr(response, "url", current_url)), location)
            is_valid, normalized_redirect_url, redirect_error = validate_url_for_request(
                redirect_url
            )
            if not is_valid:
                return _blocked_redirect_result(
                    url=url,
                    tier_name=tier_name,
                    start_time=start_time,
                    redirect_url=redirect_url,
                    error=redirect_error,
                )
            if redirect_count == _MAX_REDIRECTS:
                return _too_many_redirects_result(
                    url=url,
                    tier_name=tier_name,
                    start_time=start_time,
                )
            current_url = normalized_redirect_url

        return _too_many_redirects_result(
            url=url,
            tier_name=tier_name,
            start_time=start_time,
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
    from primr.utils.security import resolve_safe_url_for_connect
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
        current_url = url
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            http2=True,
        ) as client:
            for redirect_count in range(_MAX_REDIRECTS + 1):
                resolution, guard_error = resolve_safe_url_for_connect(current_url)
                if resolution is None:
                    return _blocked_redirect_result(
                        url=url,
                        tier_name=tier_name,
                        start_time=start_time,
                        redirect_url=current_url,
                        error=guard_error,
                    )

                response = client.get(
                    resolution.request_url,
                    headers=_headers_for_pinned_request(headers, resolution.host_header),
                    cookies=cookies,
                    extensions=_extensions_for_pinned_request(resolution.sni_hostname),
                )

                location = _redirect_location(response)
                if response.status_code not in _REDIRECT_STATUSES or location is None:
                    return _successful_scrape_result(
                        url=url,
                        tier_name=tier_name,
                        start_time=start_time,
                        response=response,
                        final_url=current_url,
                    )

                redirect_url = urljoin(current_url, location)
                is_valid, normalized_redirect_url, redirect_error = validate_url_for_request(
                    redirect_url
                )
                if not is_valid:
                    return _blocked_redirect_result(
                        url=url,
                        tier_name=tier_name,
                        start_time=start_time,
                        redirect_url=redirect_url,
                        error=redirect_error,
                    )
                if redirect_count == _MAX_REDIRECTS:
                    return _too_many_redirects_result(
                        url=url,
                        tier_name=tier_name,
                        start_time=start_time,
                    )
                current_url = normalized_redirect_url

        return _too_many_redirects_result(
            url=url,
            tier_name=tier_name,
            start_time=start_time,
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
        current_url = url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            response = curl_requests.get(
                current_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=False,
                cookies=cookies,
                impersonate=impersonate,
            )

            location = _redirect_location(response)
            if response.status_code not in _REDIRECT_STATUSES or location is None:
                return _successful_scrape_result(
                    url=url,
                    tier_name=tier_name,
                    start_time=start_time,
                    response=response,
                )

            redirect_url = urljoin(str(getattr(response, "url", current_url)), location)
            is_valid, normalized_redirect_url, redirect_error = validate_url_for_request(
                redirect_url
            )
            if not is_valid:
                return _blocked_redirect_result(
                    url=url,
                    tier_name=tier_name,
                    start_time=start_time,
                    redirect_url=redirect_url,
                    error=redirect_error,
                )
            if redirect_count == _MAX_REDIRECTS:
                return _too_many_redirects_result(
                    url=url,
                    tier_name=tier_name,
                    start_time=start_time,
                )
            current_url = normalized_redirect_url

        return _too_many_redirects_result(
            url=url,
            tier_name=tier_name,
            start_time=start_time,
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
