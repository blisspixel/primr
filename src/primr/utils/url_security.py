"""URL validation and connection-target helpers for SSRF protection."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import ParseResult, urlunparse

logger = logging.getLogger(__name__)

# Private/reserved IP ranges that should be blocked
_PRIVATE_IP_RANGES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "0.0.0.0/8",
    "100.64.0.0/10",
    "192.0.0.0/24",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]

# Cloud metadata endpoints
_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "169.254.170.2",
        "metadata.google.internal",
        "metadata.goog",
    }
)
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})
_LOCAL_HOST_SUFFIXES = (".home.arpa", ".internal", ".lan", ".local", ".localdomain")
_IDNA_DOT_TRANSLATION = str.maketrans({"\u3002": ".", "\uff0e": ".", "\uff61": "."})


@dataclass(frozen=True, slots=True)
class SafeUrlResolution:
    """Validated URL connection target for SSRF-safe clients.

    ``request_url`` is the IP-literal URL the HTTP client should connect to.
    ``host_header`` and ``sni_hostname`` preserve the original authority so
    virtual hosting and HTTPS certificate validation still use the public host.
    """

    original_url: str
    request_url: str
    host_header: str
    sni_hostname: str | None
    resolved_ip: str


def _parse_ipv4_part(part: str) -> int | None:
    """Parse one dotted-quad part with C/inet_aton radix rules; None if invalid.

    ``0x..`` is hex, a leading ``0`` (with more digits) is octal, otherwise
    decimal. Python's ``int(part, 0)`` is NOT used because it rejects C-style
    leading-zero octal (``0177``), which inet_aton accepts and attackers use.
    """
    if part == "":
        return None
    if part[:2] in ("0x", "0X"):
        digits = part[2:]
        if not digits or any(c not in "0123456789abcdefABCDEF" for c in digits):
            return None
        return int(digits, 16)
    if len(part) > 1 and part[0] == "0":
        if any(c not in "01234567" for c in part):
            return None
        return int(part, 8)
    if not part.isdigit():
        return None
    return int(part, 10)


def canonicalize_numeric_host(host: str) -> str | None:
    """Return the canonical dotted IPv4 for a numeric-literal host, else ``None``.

    SSRF filters that trust the OS resolver to decode obfuscated IPv4 forms are
    platform-dependent: e.g. macOS ``getaddrinfo`` does not decode octal
    dotted-quad (``0177.0.0.1`` resolves to the public ``177.0.0.1``, not
    loopback), while Linux/Windows do. This canonicalizer decodes the forms
    ``inet_aton`` accepts -- dotted octal/hex/decimal with 1 to 4 parts, plus a
    bare 32-bit integer -- ourselves, so a loopback/private literal is detected
    identically on every platform.

    Returns ``None`` for anything that is not a pure numeric IPv4 literal (real
    domain names, IPv6, malformed input), so callers apply extra scrutiny only
    to numeric literals and leave normal hostnames to ordinary DNS resolution.
    """
    import ipaddress

    h = host.strip()
    if h.endswith("."):
        h = h[:-1]
    if not h or any(c not in "0123456789abcdefABCDEFxX." for c in h):
        return None

    parts = h.split(".")
    if not 1 <= len(parts) <= 4:
        return None

    values: list[int] = []
    for part in parts:
        value = _parse_ipv4_part(part)
        if value is None:
            return None
        values.append(value)

    leading, last = values[:-1], values[-1]
    if any(v > 0xFF for v in leading):
        return None
    remaining_bytes = 4 - len(leading)
    if last > (1 << (8 * remaining_bytes)) - 1:
        return None

    address = 0
    for v in leading:
        address = (address << 8) | v
    address = (address << (8 * remaining_bytes)) | last

    try:
        return str(ipaddress.IPv4Address(address))
    except (ipaddress.AddressValueError, ValueError):
        return None


def numeric_host_block_reason(host: str) -> str | None:
    """Return a block reason if an obfuscated numeric IPv4 is not public."""
    import ipaddress

    canonical = canonicalize_numeric_host(host)
    if canonical is None:
        return None
    if canonical in _METADATA_HOSTS:
        return "Cloud metadata endpoints are blocked"
    try:
        ip = ipaddress.ip_address(canonical)
    except ValueError:
        return None
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_unspecified
        or ip.is_reserved
        or ip.is_multicast
    ):
        return "Obfuscated numeric IP resolves to a private/reserved address"
    for network_str in _PRIVATE_IP_RANGES:
        network = ipaddress.ip_network(network_str)
        if ip.version == network.version and ip in network:
            return "Obfuscated numeric IP resolves to a private/reserved address"
    return None


def _parse_url_for_ssrf(url: str) -> tuple[ParseResult | None, str | None, int | None, str | None]:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (ValueError, Exception) as e:
        logger.warning("URL parse failed: %s", type(e).__name__)
        return None, None, None, "Failed to parse URL"

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None, None, None, f"Invalid scheme: {parsed.scheme}. Only HTTP/HTTPS allowed."

    if not parsed.hostname:
        return None, None, None, "URL has no hostname"

    hostname = parsed.hostname.lower()
    if host_block := non_public_host_block_reason(hostname):
        return None, None, None, host_block

    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return None, None, None, "Invalid port"

    return parsed, hostname, port, None


def _resolved_ip_block_reason(ip_str: str) -> str | None:
    import ipaddress

    if ip_str in _METADATA_HOSTS:
        return "Cloud metadata endpoints are blocked"

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None

    ips_to_check: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ip]
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ips_to_check.append(mapped)
    six_to_four = getattr(ip, "sixtofour", None)
    if six_to_four is not None:
        ips_to_check.append(six_to_four)
    if ip.version == 6:
        try:
            nat64 = ipaddress.ip_network("64:ff9b::/96")
        except ValueError:
            nat64 = None
        if nat64 is not None and ip in nat64:
            ips_to_check.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))

    for candidate in ips_to_check:
        if str(candidate) in _METADATA_HOSTS:
            return "Cloud metadata endpoints are blocked"
        if (
            candidate.is_loopback
            or candidate.is_link_local
            or candidate.is_private
            or candidate.is_unspecified
            or candidate.is_reserved
            or candidate.is_multicast
        ):
            return "Private/reserved IP addresses are blocked"

        for network_str in _PRIVATE_IP_RANGES:
            network = ipaddress.ip_network(network_str)
            if candidate.version == network.version and candidate in network:
                return "Private/reserved IP addresses are blocked"

    return None


def non_public_host_block_reason(host: str) -> str | None:
    """Return a reason for a host that is lexically known to be non-public.

    Unlike :func:`is_safe_url`, this check performs no DNS lookup. It is suited
    to validating authored instructions where network access would be an
    inappropriate side effect, while connect-time callers must still use the
    full redirect-aware SSRF guard.
    """
    import ipaddress

    hostname = host.strip().translate(_IDNA_DOT_TRANSLATION).rstrip(".").casefold()
    try:
        hostname = hostname.encode("idna").decode("ascii").rstrip(".").casefold()
    except UnicodeError:
        return "Invalid internationalized hostname"
    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(".localhost"):
        return "Localhost targets are blocked"
    if hostname in _METADATA_HOSTS:
        return "Cloud metadata endpoints are blocked"
    if numeric_reason := numeric_host_block_reason(hostname):
        return numeric_reason
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        return _resolved_ip_block_reason(hostname)
    labels = hostname.split(".")
    if len(hostname) > 253 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or any(
            not (character.isascii() and character.isalnum()) and character != "-"
            for character in label
        )
        for label in labels
    ):
        return "Invalid hostname syntax"
    if "." not in hostname:
        return "Single-label hostnames are blocked"
    if hostname.endswith(_LOCAL_HOST_SUFFIXES):
        return "Local and special-use hostnames are blocked"
    return _resolved_ip_block_reason(hostname)


def _resolve_public_ips(hostname: str, port: int) -> tuple[list[str], str | None]:
    import socket

    try:
        ip_addresses = socket.getaddrinfo(hostname, port)
    except socket.gaierror:
        return [], "DNS resolution failed"

    resolved_ips: list[str] = []
    seen: set[str] = set()
    for _family, _type, _proto, _canonname, sockaddr in ip_addresses:
        ip_str = str(sockaddr[0])
        if ip_str in seen:
            continue
        seen.add(ip_str)
        resolved_ips.append(ip_str)

    if not resolved_ips:
        return [], "DNS resolution failed"

    for ip_str in resolved_ips:
        block_reason = _resolved_ip_block_reason(ip_str)
        if block_reason:
            return [], block_reason

    return resolved_ips, None


def _format_ip_literal(ip_str: str) -> str:
    return f"[{ip_str}]" if ":" in ip_str else ip_str


def _format_authority_host(hostname: str) -> str:
    return f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _host_header(parsed: ParseResult, hostname: str, port: int) -> str:
    host = _format_authority_host(hostname)
    if port != _default_port(parsed.scheme.lower()):
        return f"{host}:{port}"
    return host


def _request_url_for_ip(parsed: ParseResult, ip_str: str, port: int) -> str:
    host = _format_ip_literal(ip_str)
    netloc = host if port == _default_port(parsed.scheme.lower()) else f"{host}:{port}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def resolve_safe_url_for_connect(url: str) -> tuple[SafeUrlResolution | None, str | None]:
    """Resolve and validate ``url`` for an SSRF-safe outbound connection.

    This is the connect-time form of :func:`is_safe_url`: it resolves the host
    once, validates every returned address, and returns an IP-literal request
    URL for clients that can preserve the original Host header and TLS SNI.
    Callers that use ``request_url`` avoid the DNS-rebind check/connect split.
    """
    parsed, hostname, port, error = _parse_url_for_ssrf(url)
    if error or parsed is None or hostname is None or port is None:
        return None, error

    resolved_ips, error = _resolve_public_ips(hostname, port)
    if error:
        return None, error

    resolved_ip = resolved_ips[0]
    request_url = _request_url_for_ip(parsed, resolved_ip, port)
    sni_hostname = hostname if parsed.scheme.lower() == "https" else None

    return (
        SafeUrlResolution(
            original_url=url,
            request_url=request_url,
            host_header=_host_header(parsed, hostname, port),
            sni_hostname=sni_hostname,
            resolved_ip=resolved_ip,
        ),
        None,
    )


def is_safe_url(url: str) -> tuple[bool, str | None]:
    """
    Check if a URL is safe to fetch (SSRF protection).

    Validates:
    - Scheme is HTTP or HTTPS
    - Host is not a private/reserved IP
    - Host is not a cloud metadata endpoint
    - DNS resolution doesn't point to private IPs
    """
    parsed, hostname, port, error = _parse_url_for_ssrf(url)
    if error or parsed is None or hostname is None or port is None:
        return False, error

    _resolved_ips, error = _resolve_public_ips(hostname, port)
    if error:
        return False, error

    return True, None


def redact_url_for_log(url: str) -> str:
    """Return a URL suitable for logs without credentials or query secrets."""
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return "<unparseable-url>"
        host = parsed.hostname
        if not host:
            return "<unparseable-url>"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host
        try:
            if parsed.port is not None:
                netloc = f"{netloc}:{parsed.port}"
        except ValueError:
            pass
        return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
    except Exception:
        return "<unparseable-url>"


def validate_redirect_url(url: str, allowed_hosts: set[str] | None = None) -> bool:
    """
    Validate a redirect URL to prevent open redirect vulnerabilities.

    Relative URLs are safe unless they are protocol-relative. Absolute URLs are
    allowed only when ``allowed_hosts`` is supplied and the hostname is in it.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (ValueError, Exception) as e:
        logger.warning("URL parse failed: %s", type(e).__name__)
        return False

    if not parsed.scheme and not parsed.netloc:
        return not url.startswith("//")

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    if allowed_hosts is not None:
        hostname = parsed.hostname
        if hostname is None:
            return False
        return hostname.lower() in {h.lower() for h in allowed_hosts}

    return False


def validate_final_url_after_redirect(final_url: str) -> tuple[bool, str | None]:
    """Validate a final redirect destination with the central SSRF guard."""
    return is_safe_url(final_url)
