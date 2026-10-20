"""Fallback HTTP adapter over the existing per-hop SSRF-safe transport."""

from __future__ import annotations


def http_get(
    url: str,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
    params: dict[str, str | int] | None = None,
) -> tuple[int | None, bytes | None, str | None]:
    """Validate and pin every redirect hop through the shared safe HTTP seam."""
    from primr.data.safe_http import safe_http_get

    return safe_http_get(
        url, timeout=timeout, headers=headers, params=params, log_prefix="fallback"
    )
