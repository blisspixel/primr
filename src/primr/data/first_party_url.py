"""First-party URL helpers shared by public-data recovery paths."""

from __future__ import annotations


def same_site(host: str, base_host: str) -> bool:
    """Return True when ``host`` is the base host, its www form, or a subdomain."""

    host = (host or "").lower().removeprefix("www.")
    base_host = (base_host or "").lower().removeprefix("www.")
    if not host or not base_host:
        return False
    return host == base_host or host.endswith("." + base_host)
