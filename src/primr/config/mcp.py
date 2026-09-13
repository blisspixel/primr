"""Explicit trusted HTTP authorities for the MCP transport."""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit


def _entries(name: str) -> list[str]:
    return [value.strip() for value in os.environ.get(name, "").split(",") if value.strip()]


def _authority(value: str, name: str) -> str:
    """Validate an exact authority, never a URL or wildcard pattern."""
    try:
        parsed = urlsplit(f"//{value}")
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or any(ord(character) <= 32 or ord(character) == 127 for character in value)
            or any(character in value for character in "*\\?#")
            or not value.isascii()
            or value.endswith(":")
        ):
            raise ValueError
        # Accessing port validates malformed and out-of-range values.
        if parsed.port is not None and parsed.port < 1:
            raise ValueError
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and address.is_unspecified:
            raise ValueError
        if address is None:
            labels = parsed.hostname.removesuffix(".").split(".")
            if len(parsed.hostname) > 253 or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or not all(character.isalnum() or character == "-" for character in label)
                for label in labels
            ):
                raise ValueError
        return value.lower()
    except ValueError:
        raise ValueError(
            f"{name} must contain exact hostnames with optional ports, without wildcards"
        ) from None


def mcp_http_allowlists(host: str, port: int) -> tuple[list[str], list[str]]:
    """Read trusted hosts/origins without trusting request or proxy headers.

    Local aliases need no configuration. Wildcard listeners need an explicit
    ingress authority because a bind address does not identify their public URL.
    Native MCP clients may omit Origin; browser origins must be listed exactly.
    """
    normalized = host.lower().removeprefix("[").removesuffix("]")
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        address = None
    loopback = normalized == "localhost" or (address is not None and address.is_loopback)
    authorities = _entries("MCP_ALLOWED_HOSTS")
    local_authorities: list[str] = []
    if loopback:
        aliases = {"localhost", "127.0.0.1", "[::1]"}
        aliases.add(f"[{normalized}]" if ":" in normalized else normalized)
        local_authorities.extend(f"{alias}:{port}" for alias in sorted(aliases))
        if port == 80:
            local_authorities.extend(sorted(aliases))
        authorities.extend(local_authorities)
    elif address is not None and address.is_unspecified:
        if not authorities:
            raise ValueError(
                "MCP_ALLOWED_HOSTS is required for a wildcard HTTP listener; "
                "set it to the exact ingress hostname (for example mcp.example.com)."
            )
    else:
        authority = f"[{normalized}]" if ":" in normalized else normalized
        authorities.append(f"{authority}:{port}")
        if port == 80:
            authorities.append(authority)
    hosts = sorted({_authority(value, "MCP_ALLOWED_HOSTS") for value in authorities})

    origins = _entries("MCP_ALLOWED_ORIGINS")
    origins.extend(f"http://{authority}" for authority in local_authorities)
    validated_origins = set()
    for origin in origins:
        try:
            parsed = urlsplit(origin)
        except ValueError:
            raise ValueError("MCP_ALLOWED_ORIGINS must contain valid http(s) origins") from None
        if parsed.scheme not in {"http", "https"} or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("MCP_ALLOWED_ORIGINS must contain exact http(s) origins without paths")
        authority = _authority(parsed.netloc, "MCP_ALLOWED_ORIGINS")
        validated_origins.add(f"{parsed.scheme}://{authority}")
    return hosts, sorted(validated_origins)
