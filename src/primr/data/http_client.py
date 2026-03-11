"""
HTTP client with connection pooling and retry logic.

This module provides:
- Persistent HTTP session with connection pooling
- Automatic retry with exponential backoff
- DNS caching
- Request/response logging

Usage:
    client = HTTPClient()
    response = client.get("https://example.com")

    # Or use the singleton
    from primr.data.http_client import http_get
    content = http_get("https://example.com")
"""

import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from primr.utils.errors import ScrapingError
from primr.utils.logging_config import get_logger

logger = get_logger("http_client")


# =============================================================================
# BROWSER PROFILES
# =============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def get_random_user_agent() -> str:
    """Get a random user agent string."""
    return random.choice(USER_AGENTS)


def get_default_headers() -> dict[str, str]:
    """Get default headers for HTTP requests."""
    return {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }


# =============================================================================
# HTTP CLIENT
# =============================================================================


@dataclass
class HTTPClientConfig:
    """Configuration for HTTP client."""

    pool_connections: int = 10
    pool_maxsize: int = 20
    max_retries: int = 3
    backoff_factor: float = 0.5
    timeout: float = 30.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    verify_ssl: bool = True


class HTTPClient:
    """
    HTTP client with connection pooling and retry logic.

    Features:
    - Connection pooling for better performance
    - Automatic retry with exponential backoff
    - Configurable timeouts
    - Request statistics tracking

    Example:
        client = HTTPClient()

        # Simple GET
        response = client.get("https://example.com")

        # With custom headers
        response = client.get(
            "https://api.example.com",
            headers={"Authorization": "Bearer token"}
        )
    """

    def __init__(self, config: HTTPClientConfig | None = None):
        """
        Initialize HTTP client.

        Args:
            config: Optional configuration override
        """
        self._config = config or HTTPClientConfig()
        self._session = self._create_session()
        self._lock = threading.Lock()

        # Statistics
        self._request_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._total_time = 0.0

        logger.debug(
            f"HTTPClient initialized: pool_connections={self._config.pool_connections}, "
            f"pool_maxsize={self._config.pool_maxsize}"
        )

    def _create_session(self) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self._config.max_retries,
            backoff_factor=self._config.backoff_factor,
            status_forcelist=self._config.retry_statuses,
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            raise_on_status=False,
        )

        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=self._config.pool_connections,
            pool_maxsize=self._config.pool_maxsize,
            max_retries=retry_strategy,
        )

        # Mount for both HTTP and HTTPS
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(get_default_headers())

        return session

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """
        Make a GET request.

        Args:
            url: URL to request
            headers: Optional additional headers
            timeout: Request timeout (uses default if not specified)
            allow_redirects: Whether to follow redirects
            **kwargs: Additional arguments passed to requests

        Returns:
            Response object

        Raises:
            ScrapingError: If request fails after retries
            ValueError: If URL is invalid or fails SSRF validation
        """
        from primr.utils.validators import validate_url_for_request

        # Validate URL format
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://, got: {url[:50]}")

        # SSRF protection
        is_valid, normalized_url, error = validate_url_for_request(url)
        if not is_valid:
            raise ValueError(f"SSRF protection: {error}")
        url = normalized_url

        # Validate timeout if provided
        if timeout is not None and (not isinstance(timeout, int | float) or timeout <= 0):
            raise ValueError(f"timeout must be a positive number, got: {timeout}")

        start_time = time.time()

        try:
            # Merge headers
            request_headers = get_default_headers()
            if headers:
                request_headers.update(headers)

            response = self._session.get(
                url,
                headers=request_headers,
                timeout=timeout or self._config.timeout,
                allow_redirects=allow_redirects,
                verify=self._config.verify_ssl,
                **kwargs,
            )

            # SSRF protection: validate final URL after redirects
            if allow_redirects:
                from primr.utils.security import validate_final_url_after_redirect

                final_url = str(response.url)
                is_safe, redirect_error = validate_final_url_after_redirect(final_url)
                if not is_safe:
                    raise ValueError(
                        f"SSRF protection: redirect to {final_url} blocked - {redirect_error}"
                    )

            duration = time.time() - start_time
            self._record_request(True, duration)

            logger.debug(f"GET {url} -> {response.status_code} ({duration:.2f}s)")

            return response

        except requests.RequestException as e:
            duration = time.time() - start_time
            self._record_request(False, duration)

            logger.warning(f"GET {url} failed: {e}")
            raise ScrapingError(f"HTTP request failed: {e}", url=url, cause=e) from e

    def get_text(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        raise_for_status: bool = True,
        **kwargs: Any,
    ) -> str | None:
        """
        Make a GET request and return text content.

        Args:
            url: URL to request
            headers: Optional additional headers
            timeout: Request timeout
            raise_for_status: Whether to raise on HTTP errors
            **kwargs: Additional arguments

        Returns:
            Response text or None if failed
        """
        try:
            response = self.get(url, headers=headers, timeout=timeout, **kwargs)

            if raise_for_status:
                response.raise_for_status()

            return response.text

        except (ScrapingError, requests.HTTPError) as e:
            logger.warning(f"Failed to get text from {url}: {e}")
            return None

    def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """
        Make a GET request and return JSON content.

        Args:
            url: URL to request
            headers: Optional additional headers
            timeout: Request timeout
            **kwargs: Additional arguments

        Returns:
            Parsed JSON or None if failed
        """
        try:
            response = self.get(url, headers=headers, timeout=timeout, **kwargs)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

        except (ScrapingError, requests.HTTPError, ValueError) as e:
            logger.warning(f"Failed to get JSON from {url}: {e}")
            return None

    def head(
        self, url: str, timeout: float | None = None, **kwargs: Any
    ) -> requests.Response | None:
        """
        Make a HEAD request.

        Args:
            url: URL to request
            timeout: Request timeout
            **kwargs: Additional arguments

        Returns:
            Response object or None if failed
        """
        try:
            response = self._session.head(
                url,
                timeout=timeout or self._config.timeout,
                verify=self._config.verify_ssl,
                **kwargs,
            )
            return response
        except requests.RequestException as e:
            logger.warning("HEAD %s failed: %s", url, e)
            return None

    def _record_request(self, success: bool, duration: float) -> None:
        """Record request statistics."""
        with self._lock:
            self._request_count += 1
            self._total_time += duration
            if success:
                self._success_count += 1
            else:
                self._failure_count += 1

    def get_stats(self) -> dict[str, Any]:
        """Get client statistics."""
        with self._lock:
            avg_time = self._total_time / self._request_count if self._request_count > 0 else 0.0
            return {
                "total_requests": self._request_count,
                "successful": self._success_count,
                "failed": self._failure_count,
                "success_rate": (
                    self._success_count / self._request_count if self._request_count > 0 else 0.0
                ),
                "total_time": self._total_time,
                "avg_time": avg_time,
            }

    def reset_stats(self) -> None:
        """Reset statistics."""
        with self._lock:
            self._request_count = 0
            self._success_count = 0
            self._failure_count = 0
            self._total_time = 0.0

    def close(self) -> None:
        """Close the session and release resources."""
        self._session.close()
        logger.debug("HTTPClient session closed")

    def __enter__(self) -> "HTTPClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        """Context manager exit."""
        self.close()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_client: HTTPClient | None = None
_client_lock = threading.Lock()


def get_http_client() -> HTTPClient:
    """
    Get the global HTTP client instance.

    Returns:
        HTTPClient instance
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = HTTPClient()
    return _client


def reset_http_client() -> None:
    """Reset the global HTTP client (useful for testing)."""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def http_get(
    url: str, headers: dict[str, str] | None = None, timeout: float | None = None, **kwargs: Any
) -> requests.Response:
    """
    Make a GET request using the global client.

    Args:
        url: URL to request
        headers: Optional additional headers
        timeout: Request timeout
        **kwargs: Additional arguments

    Returns:
        Response object
    """
    return get_http_client().get(url, headers=headers, timeout=timeout, **kwargs)


def http_get_text(
    url: str, headers: dict[str, str] | None = None, timeout: float | None = None, **kwargs: Any
) -> str | None:
    """
    Make a GET request and return text using the global client.

    Args:
        url: URL to request
        headers: Optional additional headers
        timeout: Request timeout
        **kwargs: Additional arguments

    Returns:
        Response text or None
    """
    return get_http_client().get_text(url, headers=headers, timeout=timeout, **kwargs)


def http_get_json(
    url: str, headers: dict[str, str] | None = None, timeout: float | None = None, **kwargs: Any
) -> dict[str, Any] | None:
    """
    Make a GET request and return JSON using the global client.

    Args:
        url: URL to request
        headers: Optional additional headers
        timeout: Request timeout
        **kwargs: Additional arguments

    Returns:
        Parsed JSON or None
    """
    return get_http_client().get_json(url, headers=headers, timeout=timeout, **kwargs)
