"""
HTTP authentication for MCP server.

This module provides token verification and authentication middleware
for the streamable HTTP transport.

Requirements: 13.1-13.10
"""

import logging
import os
import time
from dataclasses import dataclass, field

from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)


@dataclass
class AuthConfig:
    """Authentication configuration."""

    # Admin tokens from environment (comma-separated)
    admin_tokens: set[str] = field(default_factory=set)

    # Whether to require authentication (disabled for stdio)
    require_auth: bool = True

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Load auth config from environment variables."""
        admin_tokens_str = os.environ.get("MCP_ADMIN_TOKENS", "")
        admin_tokens = {t.strip() for t in admin_tokens_str.split(",") if t.strip()}

        return cls(admin_tokens=admin_tokens)


class PrimrTokenVerifier:
    """
    Token verifier for Primr MCP server.

    Implements the MCP SDK TokenVerifier protocol.

    Supports:
    - JWT tokens with role=admin claim for admin access
    - Static admin tokens from MCP_ADMIN_TOKENS env var
    - Client ID extraction from token sub claim

    Requirements: 13.1, 13.4, 13.8, 13.9
    """

    def __init__(self, config: AuthConfig | None = None):
        """
        Initialize the token verifier.

        Args:
            config: Auth configuration. If None, loads from environment.
        """
        self.config = config or AuthConfig.from_env()
        self._token_cache: dict[str, tuple[AccessToken, float]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify a bearer token and return access info if valid.

        Args:
            token: The bearer token to verify

        Returns:
            AccessToken if valid, None if invalid
        """
        # Check cache first
        cached = self._get_cached(token)
        if cached:
            return cached

        # Check if it's a static admin token
        if token in self.config.admin_tokens:
            access = AccessToken(
                token=token,
                client_id=f"admin-{hash(token) % 10000}",
                scopes=["admin", "read", "write"],
                expires_at=None,  # Static tokens don't expire
            )
            self._cache_token(token, access)
            logger.info(f"Admin token authenticated: client_id={access.client_id}")
            return access

        # Try to decode as JWT
        jwt_result = self._verify_jwt(token)
        if jwt_result:
            self._cache_token(token, jwt_result)
            return jwt_result

        # Invalid token
        logger.warning("Token verification failed")
        return None

    def _verify_jwt(self, token: str) -> AccessToken | None:
        """
        Verify a JWT token.

        For production, this should verify the signature against a public key.
        For now, we do basic JWT structure validation and claim extraction.

        Args:
            token: JWT token string

        Returns:
            AccessToken if valid JWT, None otherwise
        """
        import base64
        import json

        try:
            # Split JWT parts
            parts = token.split(".")
            if len(parts) != 3:
                return None

            # Decode payload (middle part)
            # Add padding if needed
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes)

            # Extract claims
            client_id = payload.get("sub", "unknown")
            role = payload.get("role", "user")
            exp = payload.get("exp")

            # Check expiration
            if exp and time.time() > exp:
                logger.warning(f"Token expired for client_id={client_id}")
                return None

            # Determine scopes based on role
            scopes = ["read", "write"]
            if role == "admin":
                scopes.append("admin")

            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=scopes,
                expires_at=exp,
            )

        except Exception as e:
            logger.debug(f"JWT decode failed: {e}")
            return None

    def _get_cached(self, token: str) -> AccessToken | None:
        """Get cached token if still valid."""
        if token in self._token_cache:
            access, cached_at = self._token_cache[token]

            # Check cache TTL
            if time.time() - cached_at > self._cache_ttl:
                del self._token_cache[token]
                return None

            # Check token expiration
            if access.expires_at and time.time() > access.expires_at:
                del self._token_cache[token]
                return None

            return access
        return None

    def _cache_token(self, token: str, access: AccessToken) -> None:
        """Cache a verified token."""
        self._token_cache[token] = (access, time.time())

    def is_admin(self, access: AccessToken) -> bool:
        """Check if the access token has admin privileges."""
        return "admin" in access.scopes

    def clear_cache(self) -> None:
        """Clear the token cache."""
        self._token_cache.clear()


@dataclass
class AuthResult:
    """Result of authentication check."""

    authenticated: bool
    client_id: str | None = None
    is_admin: bool = False
    error_message: str | None = None


class AuthContext:
    """
    Authentication context for request handling.

    Provides access to the authenticated user's information
    during request processing.
    """

    def __init__(self, access_token: AccessToken | None = None):
        """
        Initialize auth context.

        Args:
            access_token: The verified access token, or None for unauthenticated
        """
        self._access_token = access_token

    @property
    def client_id(self) -> str:
        """Get the client ID, or 'anonymous' if not authenticated."""
        if self._access_token:
            return self._access_token.client_id
        return "anonymous"

    @property
    def is_authenticated(self) -> bool:
        """Check if the request is authenticated."""
        return self._access_token is not None

    @property
    def is_admin(self) -> bool:
        """Check if the authenticated user is an admin."""
        if self._access_token:
            return "admin" in self._access_token.scopes
        return False

    @property
    def scopes(self) -> list[str]:
        """Get the scopes for the authenticated user."""
        if self._access_token:
            return self._access_token.scopes
        return []

    def can_cancel_job(self, job_owner_id: str | None) -> bool:
        """
        Check if the user can cancel a job.

        Requirements: 18.9
        - Admin can cancel any job
        - Owner can cancel their own job
        - In stdio mode (anonymous), always allowed
        """
        if self.is_admin:
            return True
        if self.client_id == "anonymous":
            # Stdio mode - always allowed
            return True
        if job_owner_id is None:
            # Job has no owner - anyone can cancel
            return True
        return self.client_id == job_owner_id


def create_auth_middleware(verifier: PrimrTokenVerifier):
    """
    Create ASGI middleware for bearer token authentication.

    This wraps the MCP SDK's RequireAuthMiddleware with our token verifier.

    Requirements: 13.2, 13.3, 13.6, 13.7
    """
    from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware

    backend = BearerAuthBackend(verifier)
    return RequireAuthMiddleware(backend)


def log_auth_failure(client_ip: str, reason: str) -> None:
    """
    Log authentication failure for audit.

    Requirements: 13.6
    """
    logger.warning(
        f"Authentication failure: ip={client_ip}, reason={reason}, "
        f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
    )
