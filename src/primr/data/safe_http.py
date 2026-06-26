"""SSRF-safe HTTP helpers with per-hop redirect validation.

This is the fetch seam for primr helpers that do not need client-native
response objects. A plain ``follow_redirects=True``
client connects to every intermediate redirect target before any post-hoc
check, so an attacker-controlled page can ``302`` through an internal address
(loopback / RFC1918 / link-local / cloud metadata) that a final-only check
never sees. This helper instead follows redirects MANUALLY and revalidates each
hop's URL through the central SSRF guard (``utils.security.is_safe_url``) BEFORE
connecting to it, so an internal hop is rejected before any request is made.

Consolidating the previously-duplicated per-module ``_http_get`` helpers here
also removes the "keep these two in sync" hazard the old mirror comments named.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

from primr.utils.logging_config import get_logger
from primr.utils.security import is_safe_url

logger = get_logger("data.safe_http")

_DEFAULT_USER_AGENT = "primr/1.0 (+https://github.com/blisspixel/primr; research fetcher)"
_DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/json,*/*"
_MAX_REDIRECTS = 10
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _header_value(headers_obj: object, name: str) -> object:
    if isinstance(headers_obj, Mapping):
        return headers_obj.get(name)

    get = getattr(headers_obj, "get", None)
    if callable(get):
        return get(name)
    return None


def _redirect_location(response: object) -> str | None:
    headers_obj = getattr(response, "headers", {}) or {}
    location = _header_value(headers_obj, "location") or _header_value(headers_obj, "Location")
    return location if isinstance(location, str) and location else None


def safe_http_get(
    url: str,
    *,
    timeout: float = 15.0,
    headers: dict | None = None,
    params: dict | None = None,
    user_agent: str | None = None,
    max_redirects: int = _MAX_REDIRECTS,
    log_prefix: str = "safe-http",
    transport: Any = None,
) -> tuple[int | None, bytes | None, str | None]:
    """GET ``url`` SSRF-safely, validating the initial URL and every redirect hop.

    Returns ``(status, body, final_url)``, or ``(None, None, None)`` when the
    URL (or any redirect target) is blocked by the SSRF guard, the redirect
    budget is exceeded, or the request fails. Redirects are followed manually
    with ``follow_redirects=False`` so a hop to an internal address is rejected
    before a connection is made to it.

    ``transport`` is an injection seam for hermetic tests (an httpx transport);
    production callers leave it ``None`` to use the real transport.
    """
    base_headers = {
        "User-Agent": user_agent or _DEFAULT_USER_AGENT,
        "Accept": _DEFAULT_ACCEPT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        base_headers.update(headers)

    try:
        import httpx
    except Exception as exc:  # pragma: no cover - httpx is a hard dependency
        logger.debug("%s: httpx unavailable: %s", log_prefix, exc)
        return None, None, None

    current = url
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers=base_headers,
            transport=transport,
        ) as client:
            for _hop in range(max_redirects + 1):
                safe, reason = is_safe_url(current)
                if not safe:
                    logger.info(
                        "%s: blocked outbound request to %s (%s)", log_prefix, current, reason
                    )
                    return None, None, None
                # ``params`` belong to the caller's URL only; a redirect target
                # carries its own query string, so they are not re-applied.
                resp = client.get(current, params=params if current == url else None)
                if resp.is_redirect and "location" in resp.headers:
                    current = str(resp.url.join(resp.headers["location"]))
                    continue
                return resp.status_code, resp.content, current
        logger.info("%s: too many redirects starting from %s", log_prefix, url)
        return None, None, None
    except Exception as exc:
        logger.debug("%s HTTP GET failed for %s: %s", log_prefix, url, exc)
        return None, None, None


async def async_safe_http_head(
    url: str,
    *,
    timeout: float = 10.0,
    headers: dict | None = None,
    max_redirects: int = _MAX_REDIRECTS,
    log_prefix: str = "safe-http",
    transport: Any = None,
) -> tuple[int | None, str | None, bool]:
    """HEAD ``url`` asynchronously, validating every redirect before connecting.

    Returns ``(status, final_url, blocked_by_guard)``. Network failures are
    allowed to propagate so callers can apply their own retry/fallback policy,
    but an SSRF block is represented as ``blocked_by_guard=True`` so callers do
    not mistake it for a transient fetch failure.
    """
    base_headers = {
        "User-Agent": _DEFAULT_USER_AGENT,
        "Accept": _DEFAULT_ACCEPT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        base_headers.update(headers)

    try:
        import httpx
    except Exception as exc:  # pragma: no cover - httpx is a hard dependency
        logger.debug("%s: httpx unavailable: %s", log_prefix, exc)
        return None, None, False

    current = url
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=base_headers,
        transport=transport,
    ) as client:
        for _hop in range(max_redirects + 1):
            safe, reason = is_safe_url(current)
            if not safe:
                logger.info("%s: blocked outbound HEAD to %s (%s)", log_prefix, current, reason)
                return None, None, True

            response = await client.head(current)
            location = _redirect_location(response)
            status_code = getattr(response, "status_code", None)
            is_redirect = (
                getattr(response, "is_redirect", False) is True or status_code in _REDIRECT_STATUSES
            )
            if is_redirect and location is not None:
                response_url = str(getattr(response, "url", current))
                current = urljoin(response_url, location)
                continue

            final_url = str(getattr(response, "url", current))
            return status_code, final_url, False

    logger.info("%s: too many HEAD redirects starting from %s", log_prefix, url)
    return None, None, False
