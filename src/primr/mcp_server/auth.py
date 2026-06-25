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
from typing import Any

from mcp.server.auth.provider import AccessToken

from primr.mcp_server.tool_authz import ADMIN_SCOPE, DELEGATE_SCOPE, READ_SCOPE, RESEARCH_SCOPE

logger = logging.getLogger(__name__)

# Minimum secret key length for security
MIN_SECRET_KEY_LENGTH = 32

# Maximum number of entries in the token cache
MAX_CACHE_SIZE = 10000

# Substrings that betray a non-secret placeholder accidentally shipped from an
# IaC template, example, or hand-edit. A JWT signing secret containing any of
# these is treated as not-a-real-secret. The Azure Bicep now generates a random
# secret per deployment (deploy/azure/bicep/modules/keyvault.bicep), but a
# redeploy or manual `az keyvault secret set` could reintroduce a literal like
# "placeholder-replace-before-exposing-public-fqdn" — which passes the 32-char
# length floor yet is public in the repo. Since forging HS256 tokens against a
# known secret is a full authentication bypass, this is the runtime backstop.
PLACEHOLDER_SECRET_MARKERS: tuple[str, ...] = (
    "placeholder",
    "replace-before",
    "replace-after",
    "replace-me",
    "replace_me",
    "changeme",
    "change-me",
    "your-secret",
    "your_secret",
    "example-secret",
    "dummy-secret",
)


def _is_placeholder_secret(secret: str) -> bool:
    """Return True if *secret* looks like a non-random placeholder value."""
    lowered = secret.lower()
    return any(marker in lowered for marker in PLACEHOLDER_SECRET_MARKERS)


@dataclass
class AuthConfig:
    """Authentication configuration."""

    # Admin tokens from environment (comma-separated).
    # NOTE: Static admin tokens do not expire. For production deployments,
    # rotate tokens regularly (e.g., monthly) by updating MCP_ADMIN_TOKENS
    # and restarting the service. Set MCP_ADMIN_TOKEN_MAX_AGE_HOURS to
    # enforce automatic expiry after first use.
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

    # L4: Maximum age in hours for admin tokens from first use (None = no expiry)
    admin_token_max_age_hours: float | None = None

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """Load auth config from environment variables."""
        admin_tokens_str = os.environ.get("MCP_ADMIN_TOKENS", "")
        admin_tokens = {t.strip() for t in admin_tokens_str.split(",") if t.strip()}

        jwt_secret = os.environ.get("MCP_JWT_SECRET")
        jwt_issuer = os.environ.get("MCP_JWT_ISSUER")
        jwt_audience = os.environ.get("MCP_JWT_AUDIENCE")

        is_cloud = bool(os.environ.get("AZURE_CLIENT_ID"))

        # L3: In cloud mode, refuse to start if JWT secret is too short
        if jwt_secret and len(jwt_secret) < MIN_SECRET_KEY_LENGTH:
            if is_cloud:
                raise ValueError(
                    f"MCP_JWT_SECRET must be at least {MIN_SECRET_KEY_LENGTH} characters "
                    "in cloud mode (AZURE_CLIENT_ID is set). "
                    "Use a cryptographically random secret of 32+ characters."
                )
            else:
                logger.warning(
                    f"MCP_JWT_SECRET is shorter than {MIN_SECRET_KEY_LENGTH} characters. "
                    "Consider using a longer secret for better security."
                )

        # L3b: Refuse known placeholder secrets. A long-but-public placeholder
        # (e.g. the IaC's old "placeholder-replace-before-exposing-public-fqdn",
        # 47 chars) passes the length floor above but lets anyone forge admin
        # bearer tokens. Fail closed in cloud mode; warn loudly otherwise.
        if jwt_secret and _is_placeholder_secret(jwt_secret):
            if is_cloud:
                raise ValueError(
                    "MCP_JWT_SECRET appears to be a placeholder value and is not safe "
                    "for a public deployment (AZURE_CLIENT_ID is set). Set it to a "
                    "cryptographically random secret of 32+ characters, e.g. "
                    '`az keyvault secret set --name MCP-JWT-SECRET --value "$(openssl rand -base64 48)"`.'
                )
            else:
                logger.warning(
                    "MCP_JWT_SECRET looks like a placeholder value. Replace it with a "
                    "cryptographically random secret before exposing the server publicly."
                )

        # L4: Optional admin token max age
        max_age_str = os.environ.get("MCP_ADMIN_TOKEN_MAX_AGE_HOURS")
        admin_token_max_age_hours: float | None = None
        if max_age_str:
            try:
                admin_token_max_age_hours = float(max_age_str)
            except ValueError:
                logger.warning(
                    f"Invalid MCP_ADMIN_TOKEN_MAX_AGE_HOURS value: {max_age_str!r}. Ignoring."
                )

        return cls(
            admin_tokens=admin_tokens,
            jwt_secret=jwt_secret,
            jwt_issuer=jwt_issuer,
            jwt_audience=jwt_audience,
            admin_token_max_age_hours=admin_token_max_age_hours,
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
        # L4: Track first-use time for admin tokens (token_hash -> first_use_timestamp)
        self._admin_token_first_use: dict[str, float] = {}

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
        is_admin = False
        for stored_hash in self._admin_token_hashes:
            if hmac.compare_digest(token_hash, stored_hash):
                is_admin = True
        if is_admin:
            # L4: Check admin token max age if configured
            if self.config.admin_token_max_age_hours is not None:
                now = time.time()
                if token_hash not in self._admin_token_first_use:
                    self._admin_token_first_use[token_hash] = now
                first_use = self._admin_token_first_use[token_hash]
                max_age_seconds = self.config.admin_token_max_age_hours * 3600
                if now - first_use > max_age_seconds:
                    logger.warning(
                        f"Admin token expired: first used {now - first_use:.0f}s ago, "
                        f"max age is {max_age_seconds:.0f}s. Rotate the token."
                    )
                    return None

            access = AccessToken(
                token=token,
                client_id=f"admin-{hashlib.sha256(token.encode()).hexdigest()[:12]}",
                scopes=[ADMIN_SCOPE, READ_SCOPE, "write", RESEARCH_SCOPE, DELEGATE_SCOPE],
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

            # Determine scopes. Explicit OAuth-style scope/scp claims allow
            # least-privilege callers; no-scope tokens retain the legacy
            # read/write default for backwards compatibility.
            scopes = self._extract_scopes(payload)
            if role == "admin":
                for scope in (ADMIN_SCOPE, READ_SCOPE, "write", RESEARCH_SCOPE, DELEGATE_SCOPE):
                    if scope not in scopes:
                        scopes.append(scope)

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

    def _extract_scopes(self, payload: dict) -> list[str]:
        """Extract scopes from JWT claims or return legacy defaults."""
        explicit_scopes = self._coerce_scope_claim(payload.get("scope"))
        if not explicit_scopes:
            explicit_scopes = self._coerce_scope_claim(payload.get("scp"))
        if explicit_scopes:
            return explicit_scopes
        return [READ_SCOPE, "write"]

    def _coerce_scope_claim(self, raw_scopes: object) -> list[str]:
        """Normalize OAuth scope claims from strings or arrays."""
        if isinstance(raw_scopes, str):
            candidates = raw_scopes.replace(",", " ").split()
        elif isinstance(raw_scopes, list):
            candidates = [item for item in raw_scopes if isinstance(item, str)]
        else:
            return []

        seen: set[str] = set()
        scopes: list[str] = []
        for scope in candidates:
            normalized = scope.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                scopes.append(normalized)
        return scopes

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
        """Cache a verified token. Evicts oldest 20% when cache is full."""
        if len(self._token_cache) >= MAX_CACHE_SIZE:
            # Evict oldest 20% of entries by cached_at timestamp
            evict_count = MAX_CACHE_SIZE // 5
            sorted_keys = sorted(self._token_cache, key=lambda k: self._token_cache[k][1])
            for key in sorted_keys[:evict_count]:
                del self._token_cache[key]
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
        - Legacy jobs with no recorded owner are NOT cancellable by HTTP
          callers — same fail-closed rule as ``tools._handle_cancel_job``
          (otherwise an HTTP client could cancel any pre-owner-tracking
          job by id).
        """
        if self.is_admin:
            return True
        if self.client_id == "anonymous":
            # Stdio mode - always allowed
            return True
        if job_owner_id is None:
            # Job has no recorded owner — fail closed for HTTP callers.
            return False
        return self.client_id == job_owner_id


def create_auth_middleware(verifier: PrimrTokenVerifier, required_scopes: list[str] | None = None):
    """
    Return a callable that wraps an ASGI app with bearer-token authentication.

    Two SDK/Starlette middlewares are layered so the result actually enforces
    auth (the previous implementation called ``RequireAuthMiddleware(backend)``
    with the wrong argument and no ``required_scopes``, which raised at startup
    and meant auth was never installed):

    * ``AuthenticationMiddleware`` (outer) runs ``BearerAuthBackend`` to read the
      ``Authorization: Bearer`` header, verify the token, and populate
      ``scope["user"]`` / ``scope["auth"]``.
    * ``RequireAuthMiddleware`` (inner) rejects any request whose ``scope["user"]``
      is not an authenticated user (HTTP 401), and enforces ``required_scopes``
      (HTTP 403) when provided.

    Usage: ``app = create_auth_middleware(verifier)(app)``.

    Requirements: 13.2, 13.3, 13.6, 13.7
    """
    from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
    from starlette.middleware.authentication import AuthenticationMiddleware

    backend = BearerAuthBackend(verifier)
    scopes = list(required_scopes) if required_scopes is not None else []

    def _wrap(app: Any) -> Any:
        # Inner: require an authenticated user (+ any required scopes).
        app = RequireAuthMiddleware(app, required_scopes=scopes)
        # Outer: authenticate the request so scope["user"] is set before the
        # inner middleware checks it.
        app = AuthenticationMiddleware(app, backend=backend)
        return app

    return _wrap


def validate_entra_id_audience(token_payload: dict, expected_audience: str) -> bool:
    """
    Validate the JWT audience claim against the expected Entra ID audience.

    Handles both string and list audience claims per the JWT spec (RFC 7519).

    Args:
        token_payload: Decoded JWT payload dictionary.
        expected_audience: The expected audience value (e.g., Container App application ID).

    Returns:
        True if the audience claim matches, False otherwise.

    Requirements: 3.1, 3.4
    """
    if not expected_audience:
        return False

    aud = token_payload.get("aud")
    if aud is None:
        return False

    if isinstance(aud, str):
        return aud == expected_audience

    if isinstance(aud, list):
        return expected_audience in aud

    # Malformed aud claim (not str or list)
    return False


def get_entra_id_config() -> dict:
    """
    Return Entra ID configuration from environment variables.

    Returns:
        Dictionary with keys:
        - audience: from MCP_JWT_AUDIENCE env var (or None)
        - tenant_id: from MCP_JWT_TENANT_ID env var (or None)
        - enabled: True if MCP_JWT_AUDIENCE is set

    Requirements: 3.1, 3.4, 4.7
    """
    audience = os.environ.get("MCP_JWT_AUDIENCE")
    tenant_id = os.environ.get("MCP_JWT_TENANT_ID")
    return {
        "audience": audience,
        "tenant_id": tenant_id,
        "enabled": audience is not None and audience != "",
    }


def log_auth_failure(client_ip: str, reason: str) -> None:
    """
    Log authentication failure for audit.

    Requirements: 13.6
    """
    logger.warning(
        f"Authentication failure: ip={client_ip}, reason={reason}, "
        f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
    )
