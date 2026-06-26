"""Redirect helpers for hiring-signal provider probes."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def describe_redirect_drop(base_url: str, response: Any) -> tuple[str, str] | None:
    """Return a loggable redirect target/reason when a probe should fail closed."""

    status_code = getattr(response, "status_code", None)
    is_redirect = (
        getattr(response, "is_redirect", False) is True or status_code in _REDIRECT_STATUSES
    )
    if not is_redirect:
        return None

    headers = getattr(response, "headers", {}) or {}
    location = None
    if isinstance(headers, Mapping):
        location = headers.get("location") or headers.get("Location")
    redirect_url = urljoin(base_url, location) if isinstance(location, str) else ""
    if not redirect_url:
        return "<missing location>", "missing"

    from primr.utils.security import is_safe_url

    safe_redirect, reason = is_safe_url(redirect_url)
    return redirect_url, "safe but unsupported" if safe_redirect else reason or "blocked"


def post_json_no_redirect(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
    label: str,
) -> Any | None:
    """POST JSON to a provider endpoint without following redirects."""

    import httpx

    from primr.utils.security import is_safe_url

    logger = logging.getLogger(__name__)
    safe, reason = is_safe_url(url)
    if not safe:
        logger.info("hiring-signals: blocked %s request to %s (%s)", label, url, reason)
        return None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
            response = client.post(url, json=payload)
    except Exception as exc:
        logger.debug("%s POST failed for %s: %s", label, url, exc)
        return None

    redirect_drop = describe_redirect_drop(url, response)
    if redirect_drop is not None:
        redirect_url, redirect_reason = redirect_drop
        logger.info(
            "hiring-signals: dropped %s redirect to %s (%s)",
            label,
            redirect_url,
            redirect_reason,
        )
        return None
    return response
