"""
Security middleware for MCP server.

This module provides path validation, URL validation (SSRF protection),
and rate limiting for the MCP server.

Requirements: 11.1-11.10, 12.1-12.6, 17.1-17.10
"""

import ipaddress
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


import contextlib
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Path traversal patterns (tripwire - core defense is resolve + containment)
TRAVERSAL_PATTERNS = [
    re.compile(r"\.\."),  # Basic ..
    re.compile(r"%2e%2e", re.IGNORECASE),  # URL encoded ..
    re.compile(r"%2e\.", re.IGNORECASE),  # Mixed encoding
    re.compile(r"\.%2e", re.IGNORECASE),  # Mixed encoding
    re.compile(r"%252e", re.IGNORECASE),  # Double encoded
    re.compile(r"%2f", re.IGNORECASE),  # Encoded /
    re.compile(r"%5c", re.IGNORECASE),  # Encoded \
]

# Unicode homoglyph patterns
HOMOGLYPH_PATTERNS = [
    re.compile(r"[\uff0e\u2024\u2025]"),  # Fullwidth period, one/two dot leader
    re.compile(r"[\uff0f\u2215\u29f8]"),  # Fullwidth slash, division slash
    re.compile(r"[\uff3c\u29f5\u29f9]"),  # Fullwidth backslash
]

# System directories to block (only block specific sensitive paths)
SYSTEM_DIRECTORIES = [
    "/etc/",
    "/var/log/",
    "/var/run/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/root/",
    "/tmp/",
    "C:\\Windows\\",
    "C:\\Windows\\System32\\",
    "C:\\Program Files\\",
    "C:\\Program Files (x86)\\",
]

# Private/reserved IP ranges for SSRF protection
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

# Cloud metadata endpoints
METADATA_HOSTS = {
    "169.254.169.254",  # AWS/GCP/Azure
    "169.254.170.2",  # ECS task metadata
    "metadata.google.internal",
    "metadata.goog",
}


@dataclass
class PathValidationResult:
    """Result of path validation."""

    valid: bool
    resolved_path: Path | None = None
    error_type: str | None = None
    error_message: str | None = None


class PathValidator:
    """
    Validates file paths against allowed directories.

    Defense strategy (in order):
    1. Parse input as path; reject if absolute unless in allowed roots
    2. Join with allowed root directory
    3. Resolve to absolute path WITHOUT following symlinks
    4. Verify resolved path is_relative_to() an allowed root

    Requirements: 11.1-11.10
    """

    def __init__(self, allowed_roots: list[str] | None = None):
        """
        Initialize path validator.

        Args:
            allowed_roots: List of allowed root directories (default: output/, logs/)
        """
        if allowed_roots is None:
            allowed_roots = ["output", "logs"]

        self.allowed_roots = [Path(root).resolve() for root in allowed_roots]

    def validate(self, path: str, client_id: str | None = None) -> PathValidationResult:
        """
        Validate a path is within allowed directories.

        Args:
            path: Path to validate
            client_id: Client identifier for logging

        Returns:
            PathValidationResult with validity and resolved path or error

        Requirements: 11.1-11.9
        """
        # Check for null bytes (OS truncates at \x00, classic injection vector)
        if "\x00" in path:
            self._log_rejection(client_id, path, "null_byte")
            return PathValidationResult(
                valid=False,
                error_type="path_traversal_blocked",
                error_message="Path contains null bytes",
            )

        # Check for traversal patterns (tripwire)
        for pattern in TRAVERSAL_PATTERNS:
            if pattern.search(path):
                self._log_rejection(client_id, path, "traversal_pattern")
                return PathValidationResult(
                    valid=False,
                    error_type="path_traversal_blocked",
                    error_message="Path contains traversal sequences",
                )

        # Check for unicode homoglyphs
        for pattern in HOMOGLYPH_PATTERNS:
            if pattern.search(path):
                self._log_rejection(client_id, path, "homoglyph")
                return PathValidationResult(
                    valid=False,
                    error_type="path_traversal_blocked",
                    error_message="Path contains suspicious unicode characters",
                )

        # Check for Windows separators on non-Windows
        if os.name != "nt" and "\\" in path:
            self._log_rejection(client_id, path, "windows_separator")
            return PathValidationResult(
                valid=False,
                error_type="path_traversal_blocked",
                error_message="Path contains Windows separators",
            )

        # Parse and resolve path
        try:
            input_path = Path(path)

            # Try each allowed root
            for root in self.allowed_roots:
                # Join with root if relative
                if input_path.is_absolute():
                    candidate = input_path
                else:
                    candidate = root / input_path

                # Resolve without following symlinks
                try:
                    resolved = candidate.resolve(strict=False)
                except (OSError, ValueError):
                    continue

                # Check if resolved path is within allowed root
                try:
                    resolved.relative_to(root)

                    # Check for symlinks in the path
                    if self._contains_symlink(resolved, root):
                        self._log_rejection(client_id, path, "symlink")
                        return PathValidationResult(
                            valid=False,
                            error_type="path_traversal_blocked",
                            error_message="Path contains symlinks",
                        )

                    # Check for system directories - but skip this check if the allowed root
                    # itself is under a system directory (administrator explicitly configured it)
                    root_str = str(root)
                    root_is_in_system_dir = any(
                        root_str.startswith(sys_dir) for sys_dir in SYSTEM_DIRECTORIES
                    )

                    if not root_is_in_system_dir:
                        resolved_str = str(resolved)
                        for sys_dir in SYSTEM_DIRECTORIES:
                            if resolved_str.startswith(sys_dir):
                                self._log_rejection(client_id, path, "system_directory")
                                return PathValidationResult(
                                    valid=False,
                                    error_type="path_traversal_blocked",
                                    error_message="Path resolves to system directory",
                                )

                    return PathValidationResult(valid=True, resolved_path=resolved)
                except ValueError:
                    # Not relative to this root, try next
                    continue

            # Not in any allowed root
            self._log_rejection(client_id, path, "outside_allowed_roots")
            return PathValidationResult(
                valid=False,
                error_type="path_traversal_blocked",
                error_message="Path is outside allowed directories",
            )

        except Exception as e:
            self._log_rejection(client_id, path, f"exception: {e}")
            return PathValidationResult(
                valid=False,
                error_type="path_traversal_blocked",
                error_message="Invalid path",
            )

    def _contains_symlink(self, path: Path, root: Path) -> bool:
        """Check if any component of the path is a symlink."""
        current = path
        while current != root and current != current.parent:
            if current.is_symlink():
                return True
            current = current.parent
        return False

    def _log_rejection(self, client_id: str, path: str, reason: str) -> None:
        """Log path traversal rejection attempt."""
        logger.warning(
            "Path traversal blocked",
            extra={
                "client_id": client_id or "unknown",
                "attempted_path": path,
                "reason": reason,
            },
        )

    def resolve_safe(self, path: str, client_id: str | None = None) -> Path | None:
        """
        Resolve path to absolute, returning None if invalid.

        Only returns path AFTER all security checks pass.

        Args:
            path: Path to resolve
            client_id: Client identifier for logging

        Returns:
            Resolved Path if valid, None otherwise

        Requirements: 11.9
        """
        result = self.validate(path, client_id)
        return result.resolved_path if result.valid else None


@dataclass
class URLValidationResult:
    """Result of URL validation."""

    valid: bool
    error_type: str | None = None
    error_message: str | None = None
    resolved_ip: str | None = None


class URLValidator:
    """
    Validates URLs against SSRF attacks.

    Inherits Primr's existing SSRF protections.

    Requirements: 17.1-17.10
    """

    def __init__(
        self,
        max_response_size: int = 10 * 1024 * 1024,  # 10MB
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
    ):
        self.max_response_size = max_response_size
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    def validate(self, url: str, client_id: str | None = None) -> URLValidationResult:
        """
        Validate URL is safe to fetch.

        Args:
            url: URL to validate
            client_id: Client identifier for logging

        Returns:
            URLValidationResult with validity or error

        Requirements: 17.1-17.10
        """
        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception:
            return URLValidationResult(
                valid=False,
                error_type="invalid_url",
                error_message="Failed to parse URL",
            )

        # Check scheme (HTTP/HTTPS only)
        if parsed.scheme.lower() not in ("http", "https"):
            self._log_rejection(client_id, url, None, "invalid_scheme")
            return URLValidationResult(
                valid=False,
                error_type="invalid_url",
                error_message=f"Invalid scheme: {parsed.scheme}. Only HTTP/HTTPS allowed.",
            )

        # Check for empty host
        if not parsed.hostname:
            return URLValidationResult(
                valid=False,
                error_type="invalid_url",
                error_message="URL has no hostname",
            )

        hostname = parsed.hostname.lower()

        # Check metadata endpoints by hostname
        if hostname in METADATA_HOSTS:
            self._log_rejection(client_id, url, None, "metadata_hostname")
            return URLValidationResult(
                valid=False,
                error_type="ssrf_blocked",
                error_message="Cloud metadata endpoints are blocked",
            )

        # Resolve hostname to IP
        try:
            import socket

            ip_addresses = socket.getaddrinfo(
                hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
            resolved_ips: set[str] = set()
            for _family, _type, _proto, _canonname, sockaddr in ip_addresses:
                ip = str(sockaddr[0])  # Ensure string type
                resolved_ips.add(ip)
        except socket.gaierror:
            return URLValidationResult(
                valid=False,
                error_type="url_unreachable",
                error_message="DNS resolution failed. Try mode=deep which doesn't require site access.",
            )

        # Check each resolved IP
        for ip_str in resolved_ips:
            try:
                ip = ipaddress.ip_address(ip_str)

                # Check metadata IP
                if ip_str in METADATA_HOSTS:
                    self._log_rejection(client_id, url, ip_str, "metadata_ip")
                    return URLValidationResult(
                        valid=False,
                        error_type="ssrf_blocked",
                        error_message="Cloud metadata endpoints are blocked",
                        resolved_ip=ip_str,
                    )

                # Check private/reserved ranges
                for network in PRIVATE_IP_RANGES:
                    if ip in network:
                        self._log_rejection(client_id, url, ip_str, "private_ip")
                        return URLValidationResult(
                            valid=False,
                            error_type="ssrf_blocked",
                            error_message="Private/reserved IP addresses are blocked",
                            resolved_ip=ip_str,
                        )
            except ValueError:
                # Invalid IP format, skip
                continue

        # URL is valid
        return URLValidationResult(
            valid=True,
            resolved_ip=next(iter(resolved_ips)) if resolved_ips else None,
        )

    def _log_rejection(self, client_id: str, url: str, resolved_ip: str, reason: str) -> None:
        """Log SSRF rejection attempt."""
        logger.warning(
            "SSRF blocked",
            extra={
                "client_id": client_id or "unknown",
                "attempted_url": url,
                "resolved_ip": resolved_ip,
                "reason": reason,
            },
        )


@dataclass
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    retry_after_seconds: int | None = None


@dataclass
class ClientRateState:
    """Tracks request timestamps per client for rate limiting."""

    requests: list[datetime] = field(default_factory=list)

    def prune_old(self, window: timedelta) -> None:
        """Remove requests outside the time window."""
        cutoff = _utcnow() - window
        self.requests = [r for r in self.requests if r > cutoff]

    def count_in_window(self, window: timedelta) -> int:
        """Count requests within time window."""
        self.prune_old(window)
        return len(self.requests)

    def add_request(self) -> None:
        """Record a new request."""
        self.requests.append(_utcnow())


class RateLimiter:
    """
    Rate limits tool invocations per client.

    Supports per-tool rate limits with configurable defaults.

    Requirements: 12.1-12.6
    """

    # Default per-tool rate limits (requests per minute)
    DEFAULT_LIMITS = {
        "estimate_run": 30,  # Lightweight, encourage use
        "estimate_strategy": 30,  # Lightweight, encourage use
        "doctor": 10,
        "research_company": 2,  # Expensive operation
        "generate_strategy": 5,
        "check_jobs": 10,
        "run_qa": 10,
        "clear_jobs": 10,
        "cancel_job": 10,
    }

    def __init__(self, window_minutes: int = 1):
        self._clients: dict[str, dict[str, ClientRateState]] = defaultdict(
            lambda: defaultdict(ClientRateState)
        )
        self._window = timedelta(minutes=window_minutes)
        self._lock = Lock()
        self._limits = self._load_limits()

    def _load_limits(self) -> dict[str, int]:
        """Load rate limits from environment or use defaults."""
        limits = dict(self.DEFAULT_LIMITS)

        # Override from environment
        for tool_name in limits:
            env_var = f"MCP_RATE_LIMIT_{tool_name.upper()}"
            if env_var in os.environ:
                with contextlib.suppress(ValueError):
                    limits[tool_name] = int(os.environ[env_var])

        return limits

    def get_limit(self, tool_name: str) -> int:
        """Get rate limit for a tool."""
        return self._limits.get(tool_name, 10)  # Default 10/min

    def check(self, client_id: str, tool_name: str) -> RateLimitResult:
        """
        Check if client can make a request.

        Args:
            client_id: Client identifier
            tool_name: Name of the tool being called

        Returns:
            RateLimitResult with allowed status and retry_after if blocked

        Requirements: 12.1, 12.2, 12.3
        """
        limit = self.get_limit(tool_name)

        with self._lock:
            state = self._clients[client_id][tool_name]
            count = state.count_in_window(self._window)

            if count >= limit:
                # Calculate retry time
                if state.requests:
                    oldest = min(state.requests)
                    retry_after = int((oldest + self._window - _utcnow()).total_seconds())
                    return RateLimitResult(
                        allowed=False,
                        retry_after_seconds=max(1, retry_after),
                    )
                return RateLimitResult(allowed=False, retry_after_seconds=60)

            return RateLimitResult(allowed=True)

    def record(self, client_id: str, tool_name: str) -> None:
        """
        Record a request from client.

        Args:
            client_id: Client identifier
            tool_name: Name of the tool being called
        """
        with self._lock:
            self._clients[client_id][tool_name].add_request()

    def check_and_record(self, client_id: str, tool_name: str) -> RateLimitResult:
        """
        Check if client can make request and record it if allowed.

        Args:
            client_id: Client identifier
            tool_name: Name of the tool being called

        Returns:
            RateLimitResult with allowed status and retry_after if blocked
        """
        result = self.check(client_id, tool_name)
        if result.allowed:
            self.record(client_id, tool_name)
        return result

    def reset(self, client_id: str | None = None) -> None:
        """Reset rate limit state (for testing)."""
        with self._lock:
            if client_id:
                self._clients.pop(client_id, None)
            else:
                self._clients.clear()
