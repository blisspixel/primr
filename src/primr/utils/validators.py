"""
Defensive validation utilities.

This module provides validators for:
- URL validation, normalization, and sanitization
- File path validation with traversal prevention
- Company name validation
- Safe JSON parsing
- Fuzzy option suggestion for CLI
- CLI argument validation

Example:
    from primr.utils.validators import (
        validate_url, normalize_url, validate_file_path,
        suggest_similar, CLIValidationResult
    )

    url = validate_url("https://example.com/path")
    normalized = normalize_url("example.com")  # -> "https://example.com"
    suggestions = suggest_similar("scrpe", ["scrape", "deep", "hybrid"])
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class InputValidationError(ValueError):
    """
    Raised when input validation fails.

    Attributes:
        field: Name of the field that failed validation
        reason: Why validation failed
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"Invalid {field}: {reason}")


# =============================================================================
# URL VALIDATION
# =============================================================================


def validate_url(
    url: str, allowed_schemes: tuple[str, ...] = ("http", "https"), require_host: bool = True
) -> str:
    """
    Validate and normalize a URL.

    Checks that the URL:
    - Has an allowed scheme (http/https by default)
    - Has a valid format
    - Has a host (if required)
    - Doesn't contain obvious injection attempts

    Args:
        url: URL string to validate
        allowed_schemes: Tuple of allowed URL schemes
        require_host: Whether a host is required

    Returns:
        Normalized URL string

    Raises:
        InputValidationError: If URL is invalid

    Example:
        >>> validate_url("https://example.com/path")
        'https://example.com/path'
        >>> validate_url("javascript:alert(1)")  # raises InputValidationError
    """
    if not url or not isinstance(url, str):
        raise InputValidationError("url", "URL cannot be empty")

    url = url.strip()

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InputValidationError("url", f"Invalid URL format: {e}") from e

    # Check scheme
    if not parsed.scheme:
        raise InputValidationError("url", "URL must have a scheme (http/https)")

    if parsed.scheme.lower() not in allowed_schemes:
        raise InputValidationError(
            "url",
            f"URL scheme '{parsed.scheme}' not allowed. Allowed: {', '.join(allowed_schemes)}",
        )

    # Check host
    if require_host and not parsed.netloc:
        raise InputValidationError("url", "URL must have a host")

    # Check for suspicious patterns
    suspicious_patterns = [
        r"javascript:",
        r"data:",
        r"vbscript:",
        r"file:",
        r"<script",
        r"onclick",
        r"onerror",
    ]

    url_lower = url.lower()
    for pattern in suspicious_patterns:
        if re.search(pattern, url_lower):
            raise InputValidationError("url", "URL contains suspicious pattern")

    return url


def normalize_url(url: str) -> str:
    """
    Normalize a URL by adding scheme and handling common variations.

    Normalization rules:
    - Add https:// if no scheme present
    - Lowercase the scheme and host
    - Remove trailing slashes from path (except root)
    - Handle www. prefix consistently

    This function is idempotent: normalize(normalize(url)) == normalize(url)

    Args:
        url: URL string to normalize

    Returns:
        Normalized URL string

    Example:
        >>> normalize_url("example.com")
        'https://example.com'
        >>> normalize_url("HTTP://EXAMPLE.COM/PATH/")
        'http://example.com/PATH'
        >>> normalize_url("https://example.com")
        'https://example.com'
    """
    if not url or not isinstance(url, str):
        return ""

    url = url.strip()

    # Check for scheme (case-insensitive)
    url_lower = url.lower()
    has_scheme = url_lower.startswith(("http://", "https://", "ftp://"))

    # Add scheme if missing
    if not has_scheme:
        url = "https://" + url

    # Parse and normalize
    try:
        parsed = urlparse(url)
    except ValueError:
        return url  # Return as-is if parsing fails

    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower() if parsed.netloc else ""

    # Remove trailing slash from path (except for root)
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path

    # Reconstruct URL
    result = f"{scheme}://{host}"
    if path:
        result += path
    if parsed.query:
        result += f"?{parsed.query}"
    if parsed.fragment:
        result += f"#{parsed.fragment}"

    return result


def validate_and_normalize_url(
    url: str,
    allowed_schemes: tuple[str, ...] = ("http", "https"),
) -> tuple[bool, str, str | None]:
    """
    Validate and normalize a URL, returning structured result.

    Args:
        url: URL string to validate
        allowed_schemes: Tuple of allowed URL schemes

    Returns:
        Tuple of (is_valid, normalized_url, error_message)
        - If valid: (True, normalized_url, None)
        - If invalid: (False, original_url, error_message)

    Example:
        >>> validate_and_normalize_url("example.com")
        (True, 'https://example.com', None)
        >>> validate_and_normalize_url("javascript:alert(1)")
        (False, 'javascript:alert(1)', 'URL scheme ...')
    """
    if not url or not isinstance(url, str):
        return (False, url or "", "URL cannot be empty")

    # First normalize
    normalized = normalize_url(url)

    # Then validate
    try:
        validate_url(normalized, allowed_schemes=allowed_schemes)
        return (True, normalized, None)
    except InputValidationError as e:
        return (False, url, e.reason)


def validate_url_for_request(
    url: str, allow_private_ips: bool = False
) -> tuple[bool, str, str | None]:
    """
    Validate URL for making external HTTP requests (SSRF protection).

    Blocks:
    - Internal/private IP addresses (localhost, 10.x, 192.168.x, 169.254.x, 172.16-31.x)
    - Loopback addresses (127.x.x.x, ::1)
    - Link-local addresses (169.254.x.x, fe80::/10)
    - Non-HTTP schemes (file://, ftp://, etc.)
    - Invalid URLs

    Args:
        url: URL string to validate
        allow_private_ips: If True, allow private IP addresses (default: False)

    Returns:
        Tuple of (is_valid, normalized_url, error_message)
        - If valid: (True, normalized_url, None)
        - If invalid: (False, original_url, error_message)

    Example:
        >>> validate_url_for_request("https://example.com")
        (True, 'https://example.com', None)
        >>> validate_url_for_request("http://localhost:8080")
        (False, 'http://localhost:8080', 'Localhost not allowed')
        >>> validate_url_for_request("http://192.168.1.1")
        (False, 'http://192.168.1.1', 'Private IP addresses not allowed')
    """
    import ipaddress
    import socket

    # First validate and normalize
    is_valid, normalized, error = validate_and_normalize_url(url)
    if not is_valid:
        return (False, url, error)

    # Parse normalized URL
    try:
        parsed = urlparse(normalized)
    except Exception as e:
        return (False, url, f"Invalid URL format: {e}")

    # Block non-HTTP schemes
    if parsed.scheme not in ("http", "https"):
        return (False, url, "Only HTTP/HTTPS schemes allowed for requests")

    # Use urllib's authority parser instead of hand-splitting parsed.netloc.
    # The hand-split version returned the userinfo (e.g. "x" from
    # "http://x@169.254.169.254/...") as the host, so URLs whose actual
    # hostname was internal/metadata bypassed the SSRF check while
    # requests/httpx still resolved the real authority. parsed.hostname
    # also lowercases and unwraps IPv6 brackets correctly.
    host = (parsed.hostname or "").strip()

    if not host:
        return (False, url, "URL must have a host")

    # Block localhost variations (case-insensitive)
    localhost_patterns = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "::",
    ]

    if host.lower() in localhost_patterns:
        return (False, url, "Localhost not allowed")

    def _candidates(addr: ipaddress.IPv4Address | ipaddress.IPv6Address):
        # IPv4-mapped IPv6 (::ffff:127.0.0.1) and 6to4 hide the underlying
        # IPv4 from raw CIDR checks. Evaluate both representations.
        out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [addr]
        mapped = getattr(addr, "ipv4_mapped", None)
        if mapped is not None:
            out.append(mapped)
        six_to_four = getattr(addr, "sixtofour", None)
        if six_to_four is not None:
            out.append(six_to_four)
        return out

    def _ip_is_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
        for c in _candidates(addr):
            if c.is_loopback:
                return "Loopback addresses not allowed"
            if c.is_link_local:
                return "Link-local addresses not allowed"
            if c.is_unspecified or c.is_reserved or c.is_multicast:
                return "Reserved IP addresses not allowed"
            if not allow_private_ips and c.is_private:
                return "Private IP addresses not allowed"
        return None

    # Check if host is an IP address
    try:
        ip = ipaddress.ip_address(host)
        blocked = _ip_is_blocked(ip)
        if blocked:
            return (False, url, blocked)
    except ValueError:
        # Not an IP address, it's a hostname. Resolve DNS and fail closed
        # if resolution doesn't succeed — the previous fail-open behavior
        # meant a malformed/unresolvable host string slipped through and
        # the underlying HTTP client was free to resolve the real authority.
        if not allow_private_ips:
            try:
                resolved_ips = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            except (OSError, socket.gaierror):
                return (False, url, "Hostname could not be resolved (SSRF guard)")

            for _family, _socktype, _proto, _canonname, sockaddr in resolved_ips:
                resolved_ip = sockaddr[0]
                try:
                    ip = ipaddress.ip_address(resolved_ip)
                except ValueError:
                    continue
                blocked = _ip_is_blocked(ip)
                if blocked:
                    return (
                        False,
                        url,
                        f"Hostname resolves to blocked address ({resolved_ip}): {blocked}",
                    )

    return (True, normalized, None)


# =============================================================================
# FUZZY SUGGESTION
# =============================================================================


def _edit_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein edit distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Minimum number of edits (insert, delete, substitute) to transform s1 to s2
    """
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def suggest_similar(
    unknown: str,
    valid_options: list[str],
    max_distance: int = 2,
    max_suggestions: int = 3,
) -> list[str]:
    """
    Find valid options similar to an unknown input using edit distance.

    Args:
        unknown: The unknown/invalid input string
        valid_options: List of valid option strings
        max_distance: Maximum edit distance to consider (default 2)
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of similar valid options, sorted by edit distance

    Example:
        >>> suggest_similar("scrpe", ["scrape", "deep", "hybrid"])
        ['scrape']
        >>> suggest_similar("depe", ["scrape", "deep", "hybrid"])
        ['deep']
        >>> suggest_similar("xyz", ["scrape", "deep", "hybrid"])
        []
    """
    if not unknown or not valid_options:
        return []

    unknown_lower = unknown.lower()
    suggestions: list[tuple[int, str]] = []

    for option in valid_options:
        distance = _edit_distance(unknown_lower, option.lower())
        if distance <= max_distance:
            suggestions.append((distance, option))

    # Sort by distance, then alphabetically
    suggestions.sort(key=lambda x: (x[0], x[1]))

    return [option for _, option in suggestions[:max_suggestions]]


# =============================================================================
# CLI VALIDATION
# =============================================================================


@dataclass
class CLIValidationResult:
    """
    Result of CLI argument validation.

    Attributes:
        valid: Whether all arguments are valid
        normalized_args: Dict of normalized argument values
        errors: List of error messages
        suggestions: List of suggestion messages for fixing errors
    """

    valid: bool = True
    normalized_args: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def add_error(self, message: str, suggestion: str | None = None) -> None:
        """Add an error and optionally a suggestion."""
        self.valid = False
        self.errors.append(message)
        if suggestion:
            self.suggestions.append(suggestion)

    def merge(self, other: "CLIValidationResult") -> "CLIValidationResult":
        """Merge another validation result into this one."""
        if not other.valid:
            self.valid = False
        self.normalized_args.update(other.normalized_args)
        self.errors.extend(other.errors)
        self.suggestions.extend(other.suggestions)
        return self


def validate_cli_url(url: str) -> CLIValidationResult:
    """
    Validate and normalize a URL from CLI input.

    Args:
        url: URL string from CLI

    Returns:
        CLIValidationResult with normalized URL or errors
    """
    result = CLIValidationResult()

    is_valid, normalized, error = validate_and_normalize_url(url)

    if is_valid:
        result.normalized_args["url"] = normalized
    else:
        result.add_error(f"Invalid URL: {error}", "URLs should start with http:// or https://")
        result.normalized_args["url"] = url

    return result


def validate_cli_mode(mode: str, valid_modes: list[str] | None = None) -> CLIValidationResult:
    """
    Validate research mode from CLI input.

    Args:
        mode: Mode string from CLI
        valid_modes: List of valid mode names (default: scrape, deep, hybrid)

    Returns:
        CLIValidationResult with validated mode or suggestions
    """
    if valid_modes is None:
        valid_modes = ["scrape", "deep", "hybrid"]

    result = CLIValidationResult()
    mode_lower = mode.lower()

    if mode_lower in [m.lower() for m in valid_modes]:
        result.normalized_args["mode"] = mode_lower
    else:
        suggestions = suggest_similar(mode, valid_modes)
        suggestion_text = ""
        if suggestions:
            suggestion_text = f"Did you mean: {', '.join(suggestions)}?"

        result.add_error(
            f"Unknown mode '{mode}'. Valid modes: {', '.join(valid_modes)}",
            suggestion_text if suggestion_text else None,
        )
        result.normalized_args["mode"] = mode

    return result


# =============================================================================
# FILE PATH VALIDATION
# =============================================================================


def validate_file_path(
    path: str, base_dir: Path | None = None, must_exist: bool = False, allow_absolute: bool = False
) -> Path:
    r"""
    Validate file path against traversal attacks.

    Checks that the path:
    - Doesn't contain traversal sequences (../, ..\)
    - Is within base_dir if specified
    - Exists if must_exist is True
    - Is relative unless allow_absolute is True

    Args:
        path: Path string to validate
        base_dir: If provided, path must resolve within this directory
        must_exist: If True, path must exist
        allow_absolute: If True, allow absolute paths

    Returns:
        Validated Path object

    Raises:
        InputValidationError: If path is invalid or attempts traversal

    Example:
        >>> validate_file_path("data/file.txt")
        PosixPath('data/file.txt')
        >>> validate_file_path("../etc/passwd")  # raises InputValidationError
    """
    if not path or not isinstance(path, str):
        raise InputValidationError("path", "Path cannot be empty")

    path = path.strip()

    # Check for traversal sequences
    traversal_patterns = [
        "..",
        "..\\",
        "../",
        "..%2f",
        "..%5c",
        "%2e%2e",
    ]

    path_lower = path.lower()
    for pattern in traversal_patterns:
        if pattern in path_lower:
            raise InputValidationError("path", "Path traversal not allowed")

    # Convert to Path
    try:
        path_obj = Path(path)
    except Exception as e:
        raise InputValidationError("path", f"Invalid path format: {e}") from e

    # Check absolute path
    if path_obj.is_absolute() and not allow_absolute:
        raise InputValidationError("path", "Absolute paths not allowed")

    # Check base_dir constraint
    if base_dir is not None:
        base_dir = base_dir.resolve()
        try:
            resolved = (base_dir / path_obj).resolve()
            # Ensure resolved path is within base_dir
            resolved.relative_to(base_dir)
        except ValueError as e:
            raise InputValidationError("path", f"Path must be within {base_dir}") from e

    # Check existence
    if must_exist:
        check_path = path_obj if base_dir is None else base_dir / path_obj
        if not check_path.exists():
            raise InputValidationError("path", f"Path does not exist: {path}")

    return path_obj


# =============================================================================
# COMPANY NAME VALIDATION
# =============================================================================


def validate_company_name(name: str, min_length: int = 1, max_length: int = 200) -> str:
    """
    Validate and sanitize company name.

    Args:
        name: Company name to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length

    Returns:
        Sanitized company name

    Raises:
        InputValidationError: If name is invalid

    Example:
        >>> validate_company_name("Acme Corp, Inc.")
        'Acme Corp, Inc.'
        >>> validate_company_name("")  # raises InputValidationError
    """
    if not name or not isinstance(name, str):
        raise InputValidationError("company_name", "Company name cannot be empty")

    # Strip whitespace
    name = name.strip()

    if len(name) < min_length:
        raise InputValidationError(
            "company_name", f"Company name must be at least {min_length} characters"
        )

    if len(name) > max_length:
        raise InputValidationError(
            "company_name", f"Company name must be at most {max_length} characters"
        )

    # Check for suspicious patterns (potential injection)
    suspicious_patterns = [
        r"<script",
        r"javascript:",
        r"onclick",
        r"onerror",
        r"\x00",  # Null byte
    ]

    name_lower = name.lower()
    for pattern in suspicious_patterns:
        if re.search(pattern, name_lower):
            raise InputValidationError("company_name", "Company name contains invalid characters")

    # Reject filesystem path components. company_name is used as a filename
    # prefix and as a working-directory component in many writers, and
    # pathlib does not neutralize '..', '/', '\\', or absolute paths when
    # joined. Without this gate, MCP/CLI callers could write artifacts
    # outside OUTPUT_DIR/WORKING_DIR by sending names like "../../tmp/x"
    # or "/etc/x".
    if any(sep in name for sep in ("/", "\\")) or ".." in name:
        raise InputValidationError(
            "company_name",
            "Company name cannot contain path separators or traversal sequences",
        )
    # Reject Windows-style drive prefixes (C:, D:, ...) and other paths
    # absolutized by ntpath/posixpath.
    if len(name) >= 2 and name[1] == ":" and name[0].isalpha():
        raise InputValidationError("company_name", "Company name cannot start with a drive prefix")
    # Reject control characters that confuse downstream filesystem APIs.
    if any(ord(c) < 0x20 for c in name):
        raise InputValidationError("company_name", "Company name contains control characters")

    return name


def sanitize_for_filename(name: str, max_length: int = 100, replacement: str = "_") -> str:
    """
    Sanitize string for use as a filename.

    Removes or replaces characters that are invalid in filenames
    on common operating systems.

    Args:
        name: String to sanitize
        max_length: Maximum filename length
        replacement: Character to replace invalid chars with

    Returns:
        Safe filename string

    Example:
        >>> sanitize_for_filename("Acme Corp: The Company")
        'Acme Corp_ The Company'
        >>> sanitize_for_filename("file/with\\slashes")
        'file_with_slashes'
    """
    if not name:
        return "unnamed"

    # Characters invalid in filenames on Windows/Unix
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'

    # Replace invalid characters
    sanitized = re.sub(invalid_chars, replacement, name)

    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip(". ")

    # Collapse multiple replacements
    if replacement:
        sanitized = re.sub(f"{re.escape(replacement)}+", replacement, sanitized)

    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip(". ")

    # Ensure not empty
    if not sanitized:
        return "unnamed"

    return sanitized


# =============================================================================
# JSON PARSING
# =============================================================================


def safe_json_parse(content: str, default: Any = None) -> Any:
    """
    Safely parse JSON with graceful error handling.

    Never raises an exception - returns default on any error.

    Args:
        content: JSON string to parse
        default: Value to return if parsing fails

    Returns:
        Parsed JSON or default value

    Example:
        >>> safe_json_parse('{"key": "value"}')
        {'key': 'value'}
        >>> safe_json_parse('invalid json', default={})
        {}
    """
    if not content or not isinstance(content, str):
        return default

    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def safe_json_get(data: Any, *keys: str, default: Any = None) -> Any:
    """
    Safely get nested value from JSON-like structure.

    Args:
        data: Dict or list to traverse
        *keys: Keys/indices to follow
        default: Value to return if path doesn't exist

    Returns:
        Value at path or default

    Example:
        >>> data = {"a": {"b": {"c": 1}}}
        >>> safe_json_get(data, "a", "b", "c")
        1
        >>> safe_json_get(data, "a", "x", "y", default="missing")
        'missing'
    """
    current = data

    for key in keys:
        try:
            if isinstance(current, dict):
                current = current.get(key, default)
                if current is default:
                    return default
            elif isinstance(current, list | tuple) and isinstance(key, int):
                current = current[key]
            else:
                return default
        except (KeyError, IndexError, TypeError):
            return default

    return current
