"""
HTTP authentication for MCP server.

This module provides token verification and authentication middleware
for the streamable HTTP transport.

Requirements: 13.1-13.10

Security:
- JWT tokens are verified using HMAC-SHA256 signature validation
- Unsigned tokens (alg: none) are rejected
- Token expiration is enforced
- Static admin tokens are hashed before comparison
"""

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass, field

from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)

# Minimum secret key length for security
MIN_SECRET_KEY_LENGTH = 32


@dataclass
class AuthConfig:
    """Authentication configuration."""

    # Admin tokens from environment (comma-separated)
    admin_tokens: set[str] = field(default_factory=set)

    # Whether to require authentication (disabled for stdio)
    require_auth: bool = True

    # JWT secret key for signature verification (required for JWT auth)
    jwt_secret: str | None = None

    # Allowed JWT algorithms (HS256 only by default for security)
    jwt_algorithms: set[str] = field(default_factory=lambda: {"HS256"})

    # Required JWT issuer (optional, for additional validation)
    jwt_issuer: str | None = None

    # Required JWT audience (optional, for additional validation)
    jwt_audience: str | None = None

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Load auth config from environment variables."""
        admin_tokens_str = os.environ.get("MCP_ADMIN_TOKENS", "")
        admin_tokens = {t.strip() for t in admin_tokens_str.split(",") if t.strip()}

        jwt_secret = os.environ.get("MCP_JWT_SECRET")
        jwt_issuer = os.environ.get("MCP_JWT_ISSUER")
        jwt_audience = os.environ.get("MCP_JWT_AUDIENCE")

        # Warn if JWT secret is too short
        if jwt_secret and len(jwt_secret) < MIN_SECRET_KEY_LENGTH:
            logger.warning(
                f"MCP_JWT_SECRET is shorter than {MIN_SECRET_KEY_LENGTH} characters. "
                "Consider using a longer secret for better security."
            )

        return cls(
            admin_tokens=admin_tokens,
            jwt_secret=jwt_secret,
            jwt_issuer=jwt_issuer,
            jwt_audience=jwt_audience,
        )


class PrimrTokenVerifier:
    """
    Token verifier for Primr MCP server.

    Implements the MCP SDK TokenVerifier protocol.

    Supports:
    - JWT tokens with HMAC-SHA256 signature verification
    - Static admin tokens from MCP_ADMIN_TOKENS env var
    - Client ID extraction from token sub claim

    Security:
    - Rejects unsigned tokens (alg: none)
    - Validates signature using constant-time comparison
    - Enforces token expiration
    - Validates issuer and audience claims if configured

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

        # Hash admin tokens for secure comparison
        self._admin_token_hashes: set[str] = {self._hash_token(t) for t in self.config.admin_tokens}

    def _hash_token(self, token: str) -> str:
        """Hash a token for secure storage/comparison."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify a bearer token and return access info if valid.

        Args:
            token: The bearer token to verify

        Returns:
            AccessToken if valid, None if invalid
        """
        if not token or not isinstance(token, str):
            logger.warning("Empty or invalid token provided")
            return None

        # Check cache first
        cached = self._get_cached(token)
        if cached:
            return cached

        # Check if it's a static admin token (using constant-time comparison)
        token_hash = self._hash_token(token)
        if token_hash in self._admin_token_hashes:
            access = AccessToken(
                token=token,
                client_id=f"admin-{hashlib.sha256(token.encode()).hexdigest()[:12]}",
                scopes=["admin", "read", "write"],
                expires_at=None,  # Static tokens don't expire
            )
            self._cache_token(token, access)
            logger.info(f"Admin token authenticated: client_id={access.client_id}")
            return access

        # Try to verify as JWT (requires secret to be configured)
        if self.config.jwt_secret:
            jwt_result = self._verify_jwt(token)
            if jwt_result:
                self._cache_token(token, jwt_result)
                return jwt_result
        else:
            # Check if it looks like a JWT but we have no secret configured
            if token.count(".") == 2:
                logger.warning(
                    "JWT token received but MCP_JWT_SECRET not configured. "
                    "Set MCP_JWT_SECRET environment variable to enable JWT authentication."
                )

        # Invalid token
        logger.warning("Token verification failed")
        return None

    def _verify_jwt(self, token: str) -> AccessToken | None:
        """
        Verify a JWT token with cryptographic signature validation.

        Security measures:
        - Rejects unsigned tokens (alg: none)
        - Only accepts configured algorithms (HS256 by default)
        - Uses constant-time comparison for signature verification
        - Validates expiration, issuer, and audience claims

        Args:
            token: JWT token string

        Returns:
            AccessToken if valid JWT, None otherwise
        """

        try:
            # Split JWT parts
            parts = token.split(".")
            if len(parts) != 3:
                logger.debug("Invalid JWT structure: expected 3 parts")
                return None

            header_b64, payload_b64, signature_b64 = parts

            # Decode header
            header = self._decode_jwt_part(header_b64)
            if header is None:
                logger.debug("Failed to decode JWT header")
                return None

            # Security: Reject unsigned tokens and unsupported algorithms
            alg = header.get("alg", "").upper()
            if alg == "NONE" or not alg:
                logger.warning("Rejected unsigned JWT token (alg: none)")
                return None

            if alg not in self.config.jwt_algorithms:
                logger.warning(f"Rejected JWT with unsupported algorithm: {alg}")
                return None

            # Verify signature
            if not self._verify_jwt_signature(header_b64, payload_b64, signature_b64, alg):
                logger.warning("JWT signature verification failed")
                return None

            # Decode payload
            payload = self._decode_jwt_part(payload_b64)
            if payload is None:
                logger.debug("Failed to decode JWT payload")
                return None

            # Validate claims
            validation_error = self._validate_jwt_claims(payload)
            if validation_error:
                logger.warning(f"JWT claim validation failed: {validation_error}")
                return None

            # Extract claims
            client_id = payload.get("sub", "unknown")
            role = payload.get("role", "user")
            exp = payload.get("exp")

            # Determine scopes based on role
            scopes = ["read", "write"]
            if role == "admin":
                scopes.append("admin")

            logger.info(f"JWT authenticated: client_id={client_id}, role={role}")

            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=scopes,
                expires_at=exp,
            )

        except Exception as e:
            logger.warning("JWT verification failed: %s", e)
            return None

    def _decode_jwt_part(self, part_b64: str) -> dict | None:
        """Decode a base64url-encoded JWT part."""
        import base64
        import json

        try:
            # Add padding if needed
            padding = 4 - len(part_b64) % 4
            if padding != 4:
                part_b64 += "=" * padding

            part_bytes = base64.urlsafe_b64decode(part_b64)
            return json.loads(part_bytes)
        except (ValueError, Exception) as e:
            logger.warning("Failed to decode JWT part: %s", e)
            return None

    def _verify_jwt_signature(
        self, header_b64: str, payload_b64: str, signature_b64: str, alg: str
    ) -> bool:
        """
        Verify JWT signature using constant-time comparison.

        Args:
            header_b64: Base64url-encoded header
            payload_b64: Base64url-encoded payload
            signature_b64: Base64url-encoded signature
            alg: Algorithm from header

        Returns:
            True if signature is valid
        """
        import base64

        if not self.config.jwt_secret:
            return False

        try:
            # Compute expected signature
            signing_input = f"{header_b64}.{payload_b64}".encode()

            if alg == "HS256":
                expected_sig = hmac.new(
                    self.config.jwt_secret.encode(), signing_input, hashlib.sha256
                ).digest()
            elif alg == "HS384":
                expected_sig = hmac.new(
                    self.config.jwt_secret.encode(), signing_input, hashlib.sha384
                ).digest()
            elif alg == "HS512":
                expected_sig = hmac.new(
                    self.config.jwt_secret.encode(), signing_input, hashlib.sha512
                ).digest()
            else:
                logger.warning(f"Unsupported JWT algorithm: {alg}")
                return False

            # Decode provided signature
            padding = 4 - len(signature_b64) % 4
            if padding != 4:
                signature_b64 += "=" * padding
            provided_sig = base64.urlsafe_b64decode(signature_b64)

            # Constant-time comparison to prevent timing attacks
            return hmac.compare_digest(expected_sig, provided_sig)

        except Exception as e:
            logger.debug(f"Signature verification error: {e}")
            return False

    def _validate_jwt_claims(self, payload: dict) -> str | None:
        """
        Validate JWT claims (exp, iss, aud).

        Returns:
            Error message if validation fails, None if valid
        """
        # Check expiration
        exp = payload.get("exp")
        if exp:
            if not isinstance(exp, int | float):
                return "Invalid exp claim type"
            if time.time() > exp:
                return f"Token expired at {exp}"

        # Check not-before
        nbf = payload.get("nbf")
        if nbf:
            if not isinstance(nbf, int | float):
                return "Invalid nbf claim type"
            if time.time() < nbf:
                return f"Token not valid until {nbf}"

        # Check issuer if configured
        if self.config.jwt_issuer:
            iss = payload.get("iss")
            if iss != self.config.jwt_issuer:
                return f"Invalid issuer: expected {self.config.jwt_issuer}, got {iss}"

        # Check audience if configured
        if self.config.jwt_audience:
            aud = payload.get("aud")
            # Audience can be a string or list
            if isinstance(aud, list):
                if self.config.jwt_audience not in aud:
                    return f"Invalid audience: {self.config.jwt_audience} not in {aud}"
            elif aud != self.config.jwt_audience:
                return f"Invalid audience: expected {self.config.jwt_audience}, got {aud}"

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
