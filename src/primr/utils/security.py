"""
Security utilities for Primr.

This module provides:
- Secure secret comparison (constant-time)
- Input sanitization helpers
- Security audit logging
- Sensitive data masking for logs
- URL validation for SSRF protection

Security best practices:
- Use constant-time comparison for secrets to prevent timing attacks
- Mask sensitive data before logging
- Validate and sanitize all user inputs
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# CONSTANT-TIME COMPARISON
# =============================================================================


def secure_compare(a: str | bytes, b: str | bytes) -> bool:
    """
    Compare two strings/bytes in constant time to prevent timing attacks.

    This should be used when comparing secrets, tokens, or hashes
    where timing differences could leak information.

    Args:
        a: First value to compare
        b: Second value to compare

    Returns:
        True if values are equal, False otherwise

    Example:
        if secure_compare(provided_token, expected_token):
            grant_access()
    """
    if isinstance(a, str):
        a = a.encode("utf-8")
    if isinstance(b, str):
        b = b.encode("utf-8")

    return hmac.compare_digest(a, b)


def hash_secret(secret: str, salt: str | None = None) -> str:
    """
    Hash a secret using SHA-256 with optional salt.

    Use this for storing secrets that need to be verified later
    but should not be stored in plaintext.

    Args:
        secret: The secret to hash
        salt: Optional salt (generated if not provided)

    Returns:
        Hex-encoded hash string (salt$hash format if salted)

    Example:
        hashed = hash_secret("my_api_key")
        # Later: verify by hashing input and comparing
    """
    if salt is None:
        salt = secrets.token_hex(16)

    salted = f"{salt}{secret}".encode()
    hash_value = hashlib.sha256(salted).hexdigest()

    return f"{salt}${hash_value}"


def verify_hashed_secret(secret: str, hashed: str) -> bool:
    """
    Verify a secret against its hash (constant-time).

    Args:
        secret: The plaintext secret to verify
        hashed: The stored hash (salt$hash format)

    Returns:
        True if secret matches hash

    Example:
        if verify_hashed_secret(user_input, stored_hash):
            authenticate()
    """
    try:
        salt, expected_hash = hashed.split("$", 1)
    except ValueError:
        return False

    salted = f"{salt}{secret}".encode()
    actual_hash = hashlib.sha256(salted).hexdigest()

    return secure_compare(actual_hash, expected_hash)


# =============================================================================
# SENSITIVE DATA MASKING
# =============================================================================

# Patterns for sensitive data that should be masked in logs
SENSITIVE_PATTERNS = [
    (re.compile(r'(api[_-]?key\s*[=:]\s*)["\']?([a-zA-Z0-9_-]{20,})["\']?', re.I), r"\1[REDACTED]"),
    (re.compile(r'(token\s*[=:]\s*)["\']?([a-zA-Z0-9_.-]{20,})["\']?', re.I), r"\1[REDACTED]"),
    (re.compile(r'(password\s*[=:]\s*)["\']?([^\s"\']+)["\']?', re.I), r"\1[REDACTED]"),
    (re.compile(r'(secret\s*[=:]\s*)["\']?([^\s"\']+)["\']?', re.I), r"\1[REDACTED]"),
    (re.compile(r"(bearer\s+)([a-zA-Z0-9_.-]+)", re.I), r"\1[REDACTED]"),
    (re.compile(r'(authorization\s*[=:]\s*)["\']?([^\s"\']+)["\']?', re.I), r"\1[REDACTED]"),
    # API key patterns
    (re.compile(r"\b(AIza[a-zA-Z0-9_-]{35})\b"), "[GOOGLE_API_KEY]"),
    # Covers both the classic 48-char form (sk-<48 alnum>) and the modern
    # prefixed/variable-length forms (sk-proj-, sk-svcacct-, sk-admin-, ...),
    # which contain hyphens/underscores and would slip past a fixed [a-zA-Z0-9]{48}.
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{20,})"), "[OPENAI_API_KEY]"),
    (re.compile(r"\b(ghp_[a-zA-Z0-9]{36})\b"), "[GITHUB_TOKEN]"),
    # Additional patterns for common API keys
    (re.compile(r"\b(gho_[a-zA-Z0-9]{36})\b"), "[GITHUB_OAUTH_TOKEN]"),
    (re.compile(r"\b(github_pat_[a-zA-Z0-9_]{22,})\b"), "[GITHUB_PAT]"),
    (re.compile(r"\b(xox[baprs]-[a-zA-Z0-9-]+)\b"), "[SLACK_TOKEN]"),
    (re.compile(r"\b(sk-ant-[a-zA-Z0-9-]+)\b"), "[ANTHROPIC_API_KEY]"),
    # xAI / Grok keys (primr's primary provider) — format: xai-<alphanumeric>
    (re.compile(r"\b(xai-[a-zA-Z0-9]{16,})\b"), "[XAI_API_KEY]"),
    (re.compile(r"\b(AKIA[A-Z0-9]{16})\b"), "[AWS_ACCESS_KEY]"),
    # JWT tokens (header.payload.signature format)
    (re.compile(r"\beyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]+\b"), "[JWT_TOKEN]"),
]


def mask_sensitive_data(text: str) -> str:
    """
    Mask sensitive data in text for safe logging.

    Replaces API keys, tokens, passwords, and other secrets
    with [REDACTED] placeholders.

    Args:
        text: Text that may contain sensitive data

    Returns:
        Text with sensitive data masked

    Example:
        safe_log = mask_sensitive_data(f"Using key: {api_key}")
        logger.info(safe_log)  # "Using key: [REDACTED]"
    """
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def mask_dict_values(data: dict, sensitive_keys: set[str] | None = None) -> dict:
    """
    Mask sensitive values in a dictionary for safe logging.

    Args:
        data: Dictionary that may contain sensitive values
        sensitive_keys: Set of key names to mask (case-insensitive)

    Returns:
        New dictionary with sensitive values masked

    Example:
        config = {"api_key": "secret123", "mode": "full"}
        safe_config = mask_dict_values(config)
        # {"api_key": "[REDACTED]", "mode": "full"}
    """
    if sensitive_keys is None:
        sensitive_keys = {
            "api_key",
            "apikey",
            "api-key",
            "token",
            "access_token",
            "refresh_token",
            "password",
            "passwd",
            "pwd",
            "secret",
            "secret_key",
            "authorization",
            "auth",
            "credential",
            "credentials",
            "private_key",
            "privatekey",
        }

    result = {}
    for key, value in data.items():
        key_lower = key.lower().replace("-", "_")
        if key_lower in sensitive_keys:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = mask_dict_values(value, sensitive_keys)
        elif isinstance(value, str):
            result[key] = mask_sensitive_data(value)
        else:
            result[key] = value

    return result


# =============================================================================
# SECURITY AUDIT LOGGING
# =============================================================================


class SecurityAuditLogger:
    """
    Specialized logger for security-relevant events.

    Logs security events with structured data for audit trails.
    Events are logged at WARNING level or higher for visibility.

    Example:
        audit = SecurityAuditLogger("auth")
        audit.log_auth_success(user_id="user123", method="jwt")
        audit.log_auth_failure(reason="invalid_token", ip="192.168.1.1")
    """

    def __init__(self, component: str):
        """
        Initialize the security audit logger.

        Args:
            component: Component name (e.g., "auth", "api", "mcp")
        """
        self.component = component
        self._logger = logging.getLogger(f"security.{component}")

    def log_auth_success(
        self, user_id: str, method: str, ip: str | None = None, **extra: Any
    ) -> None:
        """Log successful authentication."""
        self._logger.info(
            f"AUTH_SUCCESS: user={user_id}, method={method}, ip={ip or 'unknown'}",
            extra={"event": "auth_success", "user_id": user_id, "method": method, **extra},
        )

    def log_auth_failure(
        self, reason: str, ip: str | None = None, user_id: str | None = None, **extra: Any
    ) -> None:
        """Log failed authentication attempt."""
        self._logger.warning(
            f"AUTH_FAILURE: reason={reason}, ip={ip or 'unknown'}, user={user_id or 'unknown'}",
            extra={"event": "auth_failure", "reason": reason, "ip": ip, **extra},
        )

    def log_access_denied(
        self, resource: str, user_id: str | None = None, reason: str | None = None, **extra: Any
    ) -> None:
        """Log access denied event."""
        self._logger.warning(
            f"ACCESS_DENIED: resource={resource}, user={user_id or 'unknown'}, reason={reason or 'unauthorized'}",
            extra={"event": "access_denied", "resource": resource, **extra},
        )

    def log_rate_limit(self, user_id: str, endpoint: str, limit: int, **extra: Any) -> None:
        """Log rate limit exceeded event."""
        self._logger.warning(
            f"RATE_LIMIT: user={user_id}, endpoint={endpoint}, limit={limit}",
            extra={"event": "rate_limit", "user_id": user_id, "endpoint": endpoint, **extra},
        )

    def log_security_violation(
        self, violation_type: str, details: str, ip: str | None = None, **extra: Any
    ) -> None:
        """Log security violation (SSRF, path traversal, etc.)."""
        self._logger.error(
            f"SECURITY_VIOLATION: type={violation_type}, details={details}, ip={ip or 'unknown'}",
            extra={"event": "security_violation", "type": violation_type, **extra},
        )

    def log_sensitive_access(self, resource: str, user_id: str, action: str, **extra: Any) -> None:
        """Log access to sensitive resources."""
        self._logger.info(
            f"SENSITIVE_ACCESS: resource={resource}, user={user_id}, action={action}",
            extra={"event": "sensitive_access", "resource": resource, **extra},
        )


# =============================================================================
# INPUT SANITIZATION
# =============================================================================


def sanitize_log_input(value: str, max_length: int = 200) -> str:
    """
    Sanitize user input for safe logging.

    Removes control characters, truncates long strings, and masks
    potential sensitive data.

    Args:
        value: User input to sanitize
        max_length: Maximum length before truncation

    Returns:
        Sanitized string safe for logging
    """
    if not isinstance(value, str):
        value = str(value)

    # Remove control characters except newlines and tabs
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)

    # Truncate if too long
    if len(value) > max_length:
        value = value[:max_length] + "...[truncated]"

    # Mask any sensitive data
    value = mask_sensitive_data(value)

    return value


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token.

    Uses secrets module for secure random generation.

    Args:
        length: Length of the token in bytes (output is hex, so 2x chars)

    Returns:
        Hex-encoded secure random token

    Example:
        token = generate_secure_token(32)  # 64 character hex string
    """
    return secrets.token_hex(length)


def generate_secure_id(prefix: str = "") -> str:
    """
    Generate a secure unique identifier.

    Args:
        prefix: Optional prefix for the ID

    Returns:
        Secure unique ID string

    Example:
        job_id = generate_secure_id("job")  # "job_a1b2c3d4..."
    """
    token = secrets.token_urlsafe(16)
    if prefix:
        return f"{prefix}_{token}"
    return token


# =============================================================================
# ENVIRONMENT VARIABLE SECURITY
# =============================================================================


def get_secret_from_env(name: str, required: bool = True, min_length: int = 0) -> str | None:
    """
    Securely retrieve a secret from environment variables.

    Validates the secret meets minimum requirements and logs
    warnings for potential issues (without logging the secret).

    Args:
        name: Environment variable name
        required: Whether the secret is required
        min_length: Minimum acceptable length

    Returns:
        The secret value, or None if not found and not required

    Raises:
        ValueError: If required secret is missing or too short
    """
    value = os.environ.get(name)

    if value is None or value.strip() == "":
        if required:
            raise ValueError(f"Required secret {name} not found in environment")
        return None

    value = value.strip()

    if min_length > 0 and len(value) < min_length:
        if required:
            raise ValueError(f"Secret {name} is too short (minimum {min_length} characters)")
        logger.warning(f"Secret {name} is shorter than recommended ({min_length} chars)")

    return value


# =============================================================================
# DECORATOR FOR SECURITY LOGGING
# =============================================================================


def audit_security_event(event_type: str, component: str = "general"):
    """
    Decorator to audit security-relevant function calls.

    Args:
        event_type: Type of security event
        component: Component name for logging

    Example:
        @audit_security_event("auth_attempt", "api")
        def authenticate(username, password):
            ...
    """
    audit = SecurityAuditLogger(component)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Log the attempt (without sensitive args)
            safe_kwargs = mask_dict_values(kwargs)
            logger.debug(f"Security event {event_type}: {func.__name__}({safe_kwargs})")

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                audit.log_security_violation(
                    violation_type=event_type, details=f"{func.__name__} failed: {type(e).__name__}"
                )
                raise

        return wrapper

    return decorator


# =============================================================================
# URL VALIDATION FOR SSRF PROTECTION
# =============================================================================

from primr.utils import url_security as _url_security

SafeUrlResolution = _url_security.SafeUrlResolution
canonicalize_numeric_host = _url_security.canonicalize_numeric_host
is_safe_url = _url_security.is_safe_url
numeric_host_block_reason = _url_security.numeric_host_block_reason
resolve_safe_url_for_connect = _url_security.resolve_safe_url_for_connect
validate_final_url_after_redirect = _url_security.validate_final_url_after_redirect
validate_redirect_url = _url_security.validate_redirect_url

# =============================================================================
# API INPUT SANITIZATION
# =============================================================================

# Characters that could be used for injection attacks
_DANGEROUS_CHARS = frozenset(
    {
        "\x00",  # Null byte
        "\r",  # Carriage return (log injection)
        "\n",  # Newline (log injection)
        "\x1b",  # Escape (ANSI injection)
    }
)

# Patterns that could indicate injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"<script", re.I),  # XSS
    re.compile(r"javascript:", re.I),  # XSS
    re.compile(r"on\w+\s*=", re.I),  # Event handlers
    re.compile(r"\{\{.*\}\}"),  # Template injection
    re.compile(r"\$\{.*\}"),  # Template injection
    re.compile(r"<%.*%>"),  # Server-side template injection
]


def sanitize_company_name(name: str, max_length: int = 200) -> tuple[str, str | None]:
    """
    Sanitize a company name for safe processing.

    Validates and sanitizes company names to prevent:
    - Log injection attacks
    - XSS attacks
    - Template injection
    - Excessively long inputs

    Args:
        name: Company name to sanitize
        max_length: Maximum allowed length

    Returns:
        Tuple of (sanitized_name, error_message)
        If error_message is not None, the input was rejected.

    Example:
        safe_name, error = sanitize_company_name(user_input)
        if error:
            raise ValueError(f"Invalid company name: {error}")
    """
    if not name or not isinstance(name, str):
        return "", "Company name is required"

    # Strip whitespace
    name = name.strip()

    if not name:
        return "", "Company name cannot be empty"

    # Check length
    if len(name) > max_length:
        return "", f"Company name exceeds maximum length of {max_length} characters"

    # Check for dangerous characters (log injection)
    for char in _DANGEROUS_CHARS:
        if char in name:
            return "", "Company name contains invalid characters"

    # Check for injection patterns
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(name):
            return "", "Company name contains potentially dangerous content"

    # Remove any remaining control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", name)

    return sanitized, None


def sanitize_url_input(url: str, max_length: int = 2048) -> tuple[str, str | None]:
    """
    Sanitize a URL input for safe processing.

    Validates and sanitizes URLs to prevent:
    - SSRF attacks
    - Log injection
    - Excessively long inputs

    Args:
        url: URL to sanitize
        max_length: Maximum allowed length

    Returns:
        Tuple of (sanitized_url, error_message)
        If error_message is not None, the input was rejected.

    Example:
        safe_url, error = sanitize_url_input(user_input)
        if error:
            raise ValueError(f"Invalid URL: {error}")
    """
    if not url or not isinstance(url, str):
        return "", "URL is required"

    # Strip whitespace
    url = url.strip()

    if not url:
        return "", "URL cannot be empty"

    # Check length
    if len(url) > max_length:
        return "", f"URL exceeds maximum length of {max_length} characters"

    # Check for dangerous characters (log injection)
    for char in _DANGEROUS_CHARS:
        if char in url:
            return "", "URL contains invalid characters"

    # Validate URL structure and SSRF protection
    is_safe, error = is_safe_url(url)
    if not is_safe:
        return "", error

    return url, None


def sanitize_webhook_url(
    url: str, allowed_schemes: set[str] | None = None
) -> tuple[str, str | None]:
    """
    Sanitize a webhook URL for safe callback.

    Validates webhook URLs with stricter requirements:
    - Must be HTTPS (by default)
    - Must not point to internal addresses
    - Must not be a cloud metadata endpoint

    Args:
        url: Webhook URL to sanitize
        allowed_schemes: Allowed URL schemes (default: {"https"})

    Returns:
        Tuple of (sanitized_url, error_message)
        If error_message is not None, the input was rejected.

    Example:
        safe_url, error = sanitize_webhook_url(user_input)
        if error:
            raise ValueError(f"Invalid webhook URL: {error}")
    """
    if allowed_schemes is None:
        allowed_schemes = {"https"}

    if not url or not isinstance(url, str):
        return "", "Webhook URL is required"

    url = url.strip()

    if not url:
        return "", "Webhook URL cannot be empty"

    # Check for dangerous characters
    for char in _DANGEROUS_CHARS:
        if char in url:
            return "", "Webhook URL contains invalid characters"

    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (ValueError, Exception) as e:
        # Log only the exception class — the raw URL may carry secrets in
        # userinfo / query / fragment (webhook tokens, signed callbacks),
        # and warnings land in stderr + persistent log files where
        # operators or log aggregators can see them.
        logger.warning("URL parse failed: %s", type(e).__name__)
        return "", "Invalid webhook URL format"

    # Check scheme
    if parsed.scheme.lower() not in allowed_schemes:
        return "", f"Webhook URL must use {' or '.join(allowed_schemes)}"

    # SSRF protection
    is_safe, error = is_safe_url(url)
    if not is_safe:
        return "", f"Webhook URL blocked: {error}"

    return url, None
