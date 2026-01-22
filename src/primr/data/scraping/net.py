"""
Shared HTTP helpers used by both HTTP tiers and discovery.

Provides consistent request handling, headers, and timeouts.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

import requests

from .config import DEFAULT_TIMEOUT_REQUESTS
from .profiles import HttpHeaderProfile, get_random_http_profile


logger = logging.getLogger(__name__)


def get_default_headers(profile: Optional[HttpHeaderProfile] = None) -> dict:
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
        headers["Sec-CH-UA-Platform"] = profile.sec_ch_ua_platform
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"
    
    return headers


def make_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT_REQUESTS,
    allow_redirects: bool = True,
    profile: Optional[HttpHeaderProfile] = None,
    cookies: Optional[dict] = None,
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
        ValueError: If URL fails SSRF validation
    """
    from primr.utils.validators import validate_url_for_request
    
    # SSRF protection
    is_valid, normalized_url, error = validate_url_for_request(url)
    if not is_valid:
        raise ValueError(f"Invalid URL: {error}")
    
    url = normalized_url
    default_headers = get_default_headers(profile)
    
    if headers:
        default_headers.update(headers)
    
    response = requests.request(
        method=method,
        url=url,
        headers=default_headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        cookies=cookies,
    )
    
    return response


def head_exists(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_REQUESTS,
    profile: Optional[HttpHeaderProfile] = None,
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
        
    except requests.RequestException as e:
        logger.debug(f"URL check failed for {url}: {e}")
        return False


def extract_host(url: str) -> str:
    """
    Extract host from URL.
    
    Args:
        url: Full URL
    
    Returns:
        Host portion of URL (e.g., "example.com")
    """
    parsed = urlparse(url)
    return parsed.netloc.lower()


def is_same_domain(url1: str, url2: str) -> bool:
    """
    Check if two URLs are on the same domain.
    
    Compares the registered domain (ignores subdomains).
    
    Args:
        url1: First URL
        url2: Second URL
    
    Returns:
        True if same domain, False otherwise
    """
    host1 = extract_host(url1)
    host2 = extract_host(url2)
    
    # Simple comparison - could be enhanced with tldextract
    # For now, compare full host
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
    
    # Remove www. prefix for comparison
    url_host = url_host.replace("www.", "")
    target_host = target_host.replace("www.", "")
    
    # Exact match
    if url_host == target_host:
        return True
    
    # Subdomain match: url_host ends with .target_host
    # e.g., docs.company.com ends with .company.com
    if url_host.endswith("." + target_host):
        return True
    
    return False


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
