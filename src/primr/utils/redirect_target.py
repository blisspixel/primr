"""Request a redirect target without rewriting the path the server sent."""

from __future__ import annotations

from urllib.parse import urlparse


def request_url_for_validated_target(url: str) -> tuple[bool, str, str | None]:
    """Validate a redirect target and return the exact URL to request.

    ``validate_url_for_request`` still rejects non-HTTP(S) schemes, credentials,
    and private or link-local targets. Its normalized form is only an identity
    check (scheme, host, and port). The URL that is requested is ``url`` as
    resolved by ``urljoin``, so a trailing slash the server sent is preserved.
    """
    from primr.utils.validators import validate_url_for_request

    exact = url.strip() if isinstance(url, str) else ""
    is_valid, normalized, error = validate_url_for_request(exact)
    if not is_valid:
        return (False, exact, error)

    try:
        raw = urlparse(exact)
        checked = urlparse(normalized)
        raw_port = raw.port
        checked_port = checked.port
    except ValueError as exc:
        return (False, exact, f"Invalid URL format: {exc}")

    if raw.username is not None or raw.password is not None:
        return (False, exact, "URL cannot contain user credentials")
    if (raw.scheme or "").lower() not in {"http", "https"}:
        return (False, exact, "Only HTTP/HTTPS schemes allowed for requests")
    if (raw.hostname or "").casefold() != (checked.hostname or "").casefold():
        return (False, exact, "Redirect target does not match the validated host")
    if raw_port != checked_port:
        return (False, exact, "Redirect target does not match the validated port")
    return (True, exact, None)


def request_url_for_hop(url: str, *, redirect_hop: bool) -> tuple[bool, str, str | None]:
    """Return the URL for a first hop or a later redirect hop.

    The first hop keeps historical normalization. A redirect hop is requested
    exactly as ``urljoin`` resolved it after the same SSRF and identity checks.
    """
    if redirect_hop:
        return request_url_for_validated_target(url)
    from primr.utils.validators import validate_url_for_request

    return validate_url_for_request(url)
