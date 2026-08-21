"""
Shared HTTP helpers used by both HTTP tiers and discovery.

Provides consistent request handling, headers, and timeouts.
"""

import logging
from collections.abc import Mapping
from urllib.parse import urljoin

import requests

from primr.utils.url_helpers import normalized_hostname

from .config import DEFAULT_TIMEOUT_REQUESTS
from .profiles import HttpHeaderProfile, get_random_http_profile

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 10


def get_default_headers(profile: HttpHeaderProfile | None = None) -> dict:
    """
    Get default HTTP headers for requests.

    Args:
        profile: Optional HTTP header profile. If None, uses random profile.

    Returns:
        Dict of headers matching the profile.
    """
    if profile is None:
        profile = get_random_http_profile()

    headers = {
        "User-Agent": profile.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": profile.accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # Add Chrome-specific headers if present
    if profile.sec_ch_ua:
        headers["Sec-CH-UA"] = profile.sec_ch_ua
        headers["Sec-CH-UA-Mobile"] = "?0"
        # sec_ch_ua_platform is Optional; only emit the header when present so a
        # None value can't leak into the (str-valued) header dict and get sent
        # as the literal "None" or raise in the HTTP client.
        if profile.sec_ch_ua_platform:
            headers["Sec-CH-UA-Platform"] = profile.sec_ch_ua_platform
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"

    return headers


def make_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT_REQUESTS,
    allow_redirects: bool = True,
    profile: HttpHeaderProfile | None = None,
    cookies: dict | None = None,
) -> requests.Response:
    """
    Make an HTTP request with consistent headers and timeouts.

    Args:
        url: URL to request
        method: HTTP method (GET, HEAD, etc.)
        headers: Optional custom headers (merged with defaults)
        timeout: Request timeout in seconds
        allow_redirects: Whether to follow redirects
        profile: Optional HTTP header profile
        cookies: Optional cookies to send

    Returns:
        requests.Response object

    Raises:
        requests.RequestException: On network errors
        ValueError: If URL fails SSRF validation on the initial URL or any
            redirect hop.
    """
    from primr.data.pinned_requests import create_pinned_session
    from primr.utils.validators import validate_url_for_request

    default_headers = get_default_headers(profile)

    if headers:
        default_headers.update(headers)

    current_url = url
    with create_pinned_session() as session:
        for redirect_count in range(_MAX_REDIRECTS + 1):
            is_valid, normalized_url, error = validate_url_for_request(current_url)
            if not is_valid:
                raise ValueError(f"Invalid URL: {error}")

            response = session.request(
                method=method,
                url=normalized_url,
                headers=default_headers,
                timeout=timeout,
                allow_redirects=False,
                cookies=cookies,
            )

            if not allow_redirects:
                return response

            headers_obj = getattr(response, "headers", {}) or {}
            location = None
            if isinstance(headers_obj, Mapping):
                location = headers_obj.get("Location") or headers_obj.get("location")

            status_code = getattr(response, "status_code", None)
            if (
                status_code not in _REDIRECT_STATUSES
                or not isinstance(location, str)
                or not location
            ):
                return response

            response_url = getattr(response, "url", normalized_url)
            current_url = urljoin(str(response_url), location)

            if redirect_count == _MAX_REDIRECTS:
                raise requests.TooManyRedirects(f"Exceeded {_MAX_REDIRECTS} redirects for {url}")

    raise requests.TooManyRedirects(f"Exceeded {_MAX_REDIRECTS} redirects for {url}")


def head_exists(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_REQUESTS,
    profile: HttpHeaderProfile | None = None,
) -> bool:
    """
    Check if a URL exists using HEAD request.

    Used by discovery to verify URLs before adding to scrape list.
    Falls back to GET if HEAD returns 405 Method Not Allowed.

    Args:
        url: URL to check
        timeout: Request timeout in seconds
        profile: Optional HTTP header profile

    Returns:
        True if URL exists (2xx or 3xx status), False otherwise
    """
    from primr.utils.validators import validate_url_for_request

    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        logger.debug(f"URL validation failed for {url}: {error}")
        return False

    url = normalized_url

    try:
        response = make_request(
            url=url,
            method="HEAD",
            timeout=timeout,
            allow_redirects=True,
            profile=profile,
        )

        # HEAD returned 405, try GET
        if response.status_code == 405:
            response = make_request(
                url=url,
                method="GET",
                timeout=timeout,
                allow_redirects=True,
                profile=profile,
            )

        return response.status_code < 400

    except (requests.RequestException, ValueError) as e:
        logger.debug(f"URL check failed for {url}: {e}")
        return False


def extract_host(url: str) -> str:
    """
    Extract host from URL.

    Args:
        url: Full URL

    Returns:
        Canonical hostname without credentials, port, or DNS root dot
    """
    return normalized_hostname(url)


def is_same_domain(url1: str, url2: str) -> bool:
    """
    Check if two URLs share the same normalized host.

    Treats www/non-www variants as the same site, but does not collapse
    other subdomains. Broader subdomain scoping belongs in is_in_scope.
    """
    host1 = extract_host(url1)
    host2 = extract_host(url2)

    if not host1 or not host2:
        return False

    host1 = host1[4:] if host1.startswith("www.") else host1
    host2 = host2[4:] if host2.startswith("www.") else host2
    return host1 == host2


def is_in_scope(url: str, target_url: str) -> bool:
    """
    Check if a URL is in scope for scraping based on the target URL.

    In-scope means:
    - Same domain as target (e.g., company.com)
    - Subdomain of target (e.g., docs.company.com, blog.company.com)

    Out-of-scope (external):
    - Different domain entirely (e.g., linkedin.com, techcrunch.com)

    Args:
        url: URL to check
        target_url: Target company website URL

    Returns:
        True if in-scope, False if external
    """
    url_host = extract_host(url)
    target_host = extract_host(target_url)

    if not url_host or not target_host:
        return False

    # Remove a leading www. prefix for comparison — only the prefix, not any
    # embedded "www." (e.g. "my-www.example.com" must stay intact, otherwise
    # the scope/subdomain check below is computed against a corrupted host).
    url_host = url_host[4:] if url_host.startswith("www.") else url_host
    target_host = target_host[4:] if target_host.startswith("www.") else target_host

    # Exact match
    if url_host == target_host:
        return True

    # Subdomain match: url_host ends with .target_host
    # e.g., docs.company.com ends with .company.com
    return bool(url_host.endswith("." + target_host))


def normalize_url_for_request(url: str) -> str:
    """
    Normalize URL for making requests.

    Ensures URL has scheme, handles common issues.

    Args:
        url: URL to normalize

    Returns:
        Normalized URL
    """
    url = url.strip()

    # Add scheme if missing
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url
