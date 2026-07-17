"""Small, side-effect-free helpers for public web URL components."""

from __future__ import annotations

import ipaddress
import re
from typing import NamedTuple
from urllib.parse import SplitResult, urlsplit, urlunsplit

import idna

from primr.utils.validators import sanitize_for_filename

_SCHEME_NAME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")


class _WebURL(NamedTuple):
    parsed: SplitResult
    hostname: str
    port: int | None


def _parse_web_url(url: str) -> _WebURL | None:
    """Parse an HTTP(S) URL or scheme-less web authority, failing closed."""
    candidate = (url or "").strip()
    if not candidate:
        return None
    if "://" not in candidate and not candidate.startswith("//"):
        scheme_like, separator, remainder = candidate.partition(":")
        if separator and _SCHEME_NAME.fullmatch(scheme_like):
            port_text = re.split(r"[/#?]", remainder, maxsplit=1)[0]
            host_like = "." in scheme_like or scheme_like.lower() == "localhost"
            is_host_port = host_like and port_text.isascii() and port_text.isdecimal()
            if not is_host_port:
                return None
        candidate = f"//{candidate.lstrip('/')}"

    try:
        parsed = urlsplit(candidate)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return None
        hostname = parsed.hostname
        port = parsed.port  # Force urllib's lazy syntax and range validation.
        if not hostname:
            return None

        unrooted = hostname.rstrip(".")
        try:
            canonical_host = str(ipaddress.ip_address(unrooted))
        except ValueError:
            canonical_host = idna.encode(unrooted, uts46=True).decode("ascii").lower()
    except (UnicodeError, ValueError, idna.IDNAError):
        return None

    return _WebURL(parsed=parsed, hostname=canonical_host, port=port)


def normalized_hostname(url: str, *, strip_www: bool = False) -> str:
    """Return an IDNA hostname without credentials, port, or root dot.

    Scheme-less hostnames are accepted because several internal call sites
    operate after user-facing URL normalization but remain useful in isolation.
    Invalid URLs return an empty string.
    """
    result = _parse_web_url(url)
    if result is None:
        return ""
    return result.hostname.removeprefix("www.") if strip_www else result.hostname


def normalized_web_origin(url: str) -> str:
    """Return an HTTP(S) origin with userinfo removed and a valid port retained."""
    result = _parse_web_url(url)
    if result is None:
        return ""
    scheme = result.parsed.scheme.lower() or "https"
    host = f"[{result.hostname}]" if ":" in result.hostname else result.hostname
    authority = f"{host}:{result.port}" if result.port is not None else host
    return f"{scheme}://{authority}"


def public_web_url(url: str) -> str:
    """Return a canonical public URL with any userinfo removed.

    Invalid and non-HTTP(S) values return an empty string so callers do not
    persist a misleading or credential-bearing hyperlink.
    """
    result = _parse_web_url(url)
    if result is None:
        return ""
    origin_parts = urlsplit(normalized_web_origin(url))
    parsed = result.parsed
    return urlunsplit(
        (origin_parts.scheme, origin_parts.netloc, parsed.path, parsed.query, parsed.fragment)
    )


def hostname_is_same_or_subdomain(candidate: str, parent: str) -> bool:
    """Return whether *candidate* is *parent* or one of its DNS subdomains."""
    candidate_host = normalized_hostname(candidate)
    parent_host = normalized_hostname(parent)
    return bool(
        parent_host
        and (candidate_host == parent_host or candidate_host.endswith(f".{parent_host}"))
    )


def safe_hostname_token(url: str, *, max_length: int = 30) -> str:
    """Return a portable filename token derived only from a URL hostname."""
    hostname = normalized_hostname(url, strip_www=True) or "source"
    return sanitize_for_filename(hostname, max_length=max_length)


__all__ = [
    "hostname_is_same_or_subdomain",
    "normalized_hostname",
    "normalized_web_origin",
    "public_web_url",
    "safe_hostname_token",
]
