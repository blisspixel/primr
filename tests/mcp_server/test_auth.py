"""
Tests for HTTP authentication.

Task 12: HTTP authentication
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

from primr.mcp_server.auth import (
    AuthConfig,
    AuthContext,
    PrimrTokenVerifier,
    log_auth_failure,
)

# Test secret for JWT signing
TEST_JWT_SECRET = "test-secret-key-for-jwt-signing-minimum-32-chars"


def create_signed_jwt(payload: dict, secret: str = TEST_JWT_SECRET, alg: str = "HS256") -> str:
    """Create a properly signed JWT for testing."""
    header = {"alg": alg, "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")

    signing_input = f"{header_b64}.{payload_b64}".encode()

    if alg == "HS256":
        signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    elif alg == "HS384":
        signature = hmac.new(secret.encode(), signing_input, hashlib.sha384).digest()
    elif alg == "HS512":
        signature = hmac.new(secret.encode(), signing_input, hashlib.sha512).digest()
    else:
        signature = b"fake-signature"

    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def create_unsigned_jwt(payload: dict) -> str:
    """Create an unsigned JWT (alg: none) for testing rejection."""
    header = {"alg": "none", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}."


class TestAuthConfig:
    """Tests for AuthConfig."""

    def test_default_config(self):
        """Default config has empty admin tokens."""
        config = AuthConfig()
        assert config.admin_tokens == set()
        assert config.require_auth is True
        assert config.jwt_secret is None

    def test_from_env_with_admin_tokens(self, monkeypatch):
        """Config loads admin tokens from environment."""
        monkeypatch.setenv("MCP_ADMIN_TOKENS", "token1,token2,token3")

        config = AuthConfig.from_env()

        assert config.admin_tokens == {"token1", "token2", "token3"}

    def test_from_env_strips_whitespace(self, monkeypatch):
        """Config strips whitespace from tokens."""
        monkeypatch.setenv("MCP_ADMIN_TOKENS", " token1 , token2 , token3 ")

        config = AuthConfig.from_env()

        assert config.admin_tokens == {"token1", "token2", "token3"}

    def test_from_env_ignores_empty(self, monkeypatch):
        """Config ignores empty tokens."""
        monkeypatch.setenv("MCP_ADMIN_TOKENS", "token1,,token2,")

        config = AuthConfig.from_env()

        assert config.admin_tokens == {"token1", "token2"}

    def test_from_env_with_jwt_secret(self, monkeypatch):
        """Config loads JWT secret from environment."""
        monkeypatch.setenv("MCP_JWT_SECRET", TEST_JWT_SECRET)

        config = AuthConfig.from_env()

        assert config.jwt_secret == TEST_JWT_SECRET

    def test_from_env_with_jwt_issuer_audience(self, monkeypatch):
        """Config loads JWT issuer and audience from environment."""
        monkeypatch.setenv("MCP_JWT_SECRET", TEST_JWT_SECRET)
        monkeypatch.setenv("MCP_JWT_ISSUER", "test-issuer")
        monkeypatch.setenv("MCP_JWT_AUDIENCE", "test-audience")

        config = AuthConfig.from_env()

        assert config.jwt_issuer == "test-issuer"
        assert config.jwt_audience == "test-audience"


class TestPrimrTokenVerifier:
    """Tests for PrimrTokenVerifier."""

    @pytest.fixture
    def verifier(self):
        """Create a verifier with test admin tokens and JWT secret."""
        config = AuthConfig(
            admin_tokens={"test-admin-token", "another-admin"},
            jwt_secret=TEST_JWT_SECRET,
        )
        return PrimrTokenVerifier(config)

    @pytest.fixture
    def verifier_no_jwt(self):
        """Create a verifier without JWT secret (admin tokens only)."""
        config = AuthConfig(admin_tokens={"test-admin-token"})
        return PrimrTokenVerifier(config)

    @pytest.mark.asyncio
    async def test_verify_admin_token(self, verifier):
        """Admin tokens are verified successfully."""
        result = await verifier.verify_token("test-admin-token")

        assert result is not None
        assert "admin" in result.scopes
        assert result.expires_at is None  # Static tokens don't expire

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, verifier):
        """Invalid tokens return None."""
        result = await verifier.verify_token("invalid-token")

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_signed_jwt_token(self, verifier):
        """Valid signed JWT tokens are verified."""
        token = create_signed_jwt({
            "sub": "user-123",
            "role": "user",
            "exp": int(time.time()) + 3600,
        })

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "user-123"
        assert "admin" not in result.scopes

    @pytest.mark.asyncio
    async def test_verify_jwt_admin_role(self, verifier):
        """JWT with admin role gets admin scope."""
        token = create_signed_jwt({
            "sub": "admin-user",
            "role": "admin",
            "exp": int(time.time()) + 3600,
        })

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "admin-user"
        assert "admin" in result.scopes

    @pytest.mark.asyncio
    async def test_verify_expired_jwt(self, verifier):
        """Expired JWT tokens are rejected."""
        token = create_signed_jwt({
            "sub": "user-123",
            "exp": int(time.time()) - 3600,  # 1 hour ago
        })

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_unsigned_jwt(self, verifier):
        """Unsigned JWT tokens (alg: none) are rejected."""
        token = create_unsigned_jwt({
            "sub": "attacker",
            "role": "admin",
            "exp": int(time.time()) + 3600,
        })

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_jwt_with_wrong_signature(self, verifier):
        """JWT with wrong signature is rejected."""
        # Create JWT signed with wrong secret
        token = create_signed_jwt(
            {"sub": "user", "exp": int(time.time()) + 3600},
            secret="wrong-secret-key-that-is-long-enough"
        )

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_jwt_without_secret_configured(self, verifier_no_jwt):
        """JWT tokens are rejected when no secret is configured."""
        token = create_signed_jwt({
            "sub": "user-123",
            "exp": int(time.time()) + 3600,
        })

        result = await verifier_no_jwt.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_unsupported_algorithm(self, verifier):
        """JWT with unsupported algorithm is rejected."""
        # Create JWT with RS256 (not in allowed algorithms)
        header = {"alg": "RS256", "typ": "JWT"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps({
            "sub": "user",
            "exp": int(time.time()) + 3600,
        }).encode()).decode().rstrip("=")
        token = f"{header_b64}.{payload_b64}.fake-signature"

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_jwt_issuer(self):
        """JWT issuer claim is validated when configured."""
        config = AuthConfig(
            jwt_secret=TEST_JWT_SECRET,
            jwt_issuer="expected-issuer",
        )
        verifier = PrimrTokenVerifier(config)

        # Token with wrong issuer
        wrong_issuer_token = create_signed_jwt({
            "sub": "user",
            "iss": "wrong-issuer",
            "exp": int(time.time()) + 3600,
        })
        result = await verifier.verify_token(wrong_issuer_token)
        assert result is None

        # Token with correct issuer
        correct_issuer_token = create_signed_jwt({
            "sub": "user",
            "iss": "expected-issuer",
            "exp": int(time.time()) + 3600,
        })
        result = await verifier.verify_token(correct_issuer_token)
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_jwt_audience(self):
        """JWT audience claim is validated when configured."""
        config = AuthConfig(
            jwt_secret=TEST_JWT_SECRET,
            jwt_audience="expected-audience",
        )
        verifier = PrimrTokenVerifier(config)

        # Token with wrong audience
        wrong_aud_token = create_signed_jwt({
            "sub": "user",
            "aud": "wrong-audience",
            "exp": int(time.time()) + 3600,
        })
        result = await verifier.verify_token(wrong_aud_token)
        assert result is None

        # Token with correct audience
        correct_aud_token = create_signed_jwt({
            "sub": "user",
            "aud": "expected-audience",
            "exp": int(time.time()) + 3600,
        })
        result = await verifier.verify_token(correct_aud_token)
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_jwt_nbf_claim(self, verifier):
        """JWT not-before claim is validated."""
        # Token not valid yet
        future_token = create_signed_jwt({
            "sub": "user",
            "nbf": int(time.time()) + 3600,  # Valid 1 hour from now
            "exp": int(time.time()) + 7200,
        })
        result = await verifier.verify_token(future_token)
        assert result is None

        # Token already valid
        valid_token = create_signed_jwt({
            "sub": "user",
            "nbf": int(time.time()) - 60,  # Valid since 1 minute ago
            "exp": int(time.time()) + 3600,
        })
        result = await verifier.verify_token(valid_token)
        assert result is not None

    @pytest.mark.asyncio
    async def test_token_caching(self, verifier):
        """Verified tokens are cached."""
        result1 = await verifier.verify_token("test-admin-token")
        result2 = await verifier.verify_token("test-admin-token")

        # Both should return the same cached result
        assert result1 is not None
        assert result2 is not None
        assert result1.client_id == result2.client_id

    @pytest.mark.asyncio
    async def test_clear_cache(self, verifier):
        """Cache can be cleared."""
        await verifier.verify_token("test-admin-token")
        assert len(verifier._token_cache) > 0

        verifier.clear_cache()

        assert len(verifier._token_cache) == 0

    def test_is_admin(self, verifier):
        """is_admin checks scopes correctly."""
        from mcp.server.auth.provider import AccessToken

        admin_token = AccessToken(
            token="test",
            client_id="admin",
            scopes=["admin", "read", "write"],
        )
        user_token = AccessToken(
            token="test",
            client_id="user",
            scopes=["read", "write"],
        )

        assert verifier.is_admin(admin_token) is True
        assert verifier.is_admin(user_token) is False

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self, verifier):
        """Empty tokens are rejected."""
        assert await verifier.verify_token("") is None
        assert await verifier.verify_token(None) is None

    @pytest.mark.asyncio
    async def test_malformed_jwt_rejected(self, verifier):
        """Malformed JWTs are rejected."""
        assert await verifier.verify_token("not.a.valid.jwt.token") is None
        assert await verifier.verify_token("only-one-part") is None
        assert await verifier.verify_token("two.parts") is None


class TestAuthContext:
    """Tests for AuthContext."""

    def test_unauthenticated_context(self):
        """Unauthenticated context has anonymous client_id."""
        ctx = AuthContext()

        assert ctx.client_id == "anonymous"
        assert ctx.is_authenticated is False
        assert ctx.is_admin is False
        assert ctx.scopes == []

    def test_authenticated_context(self):
        """Authenticated context has correct properties."""
        from mcp.server.auth.provider import AccessToken

        token = AccessToken(
            token="test",
            client_id="user-123",
            scopes=["read", "write"],
        )
        ctx = AuthContext(token)

        assert ctx.client_id == "user-123"
        assert ctx.is_authenticated is True
        assert ctx.is_admin is False
        assert ctx.scopes == ["read", "write"]

    def test_admin_context(self):
        """Admin context has is_admin=True."""
        from mcp.server.auth.provider import AccessToken

        token = AccessToken(
            token="test",
            client_id="admin-user",
            scopes=["admin", "read", "write"],
        )
        ctx = AuthContext(token)

        assert ctx.is_admin is True

    def test_can_cancel_job_admin(self):
        """Admin can cancel any job."""
        from mcp.server.auth.provider import AccessToken

        token = AccessToken(
            token="test",
            client_id="admin-user",
            scopes=["admin", "read", "write"],
        )
        ctx = AuthContext(token)

        assert ctx.can_cancel_job("other-user") is True
        assert ctx.can_cancel_job(None) is True

    def test_can_cancel_job_owner(self):
        """Owner can cancel their own job."""
        from mcp.server.auth.provider import AccessToken

        token = AccessToken(
            token="test",
            client_id="user-123",
            scopes=["read", "write"],
        )
        ctx = AuthContext(token)

        assert ctx.can_cancel_job("user-123") is True
        assert ctx.can_cancel_job("other-user") is False

    def test_can_cancel_job_anonymous(self):
        """Anonymous (stdio mode) can cancel any job."""
        ctx = AuthContext()

        assert ctx.can_cancel_job("any-user") is True
        assert ctx.can_cancel_job(None) is True

    def test_can_cancel_job_no_owner(self):
        """Anyone can cancel a job with no owner."""
        from mcp.server.auth.provider import AccessToken

        token = AccessToken(
            token="test",
            client_id="user-123",
            scopes=["read", "write"],
        )
        ctx = AuthContext(token)

        assert ctx.can_cancel_job(None) is True


class TestAuthLogging:
    """Tests for auth logging."""

    def test_log_auth_failure(self, caplog):
        """Auth failures are logged."""
        import logging

        with caplog.at_level(logging.WARNING):
            log_auth_failure("192.168.1.1", "invalid token")

        assert "Authentication failure" in caplog.text
        assert "192.168.1.1" in caplog.text
        assert "invalid token" in caplog.text


class TestAuthenticationEnforcement:
    """
    Property 12: Authentication Enforcement (HTTP Mode)
    
    Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.6
    """

    @pytest.fixture
    def verifier(self):
        """Create a verifier with test admin tokens and JWT secret."""
        config = AuthConfig(
            admin_tokens={"valid-admin-token"},
            jwt_secret=TEST_JWT_SECRET,
        )
        return PrimrTokenVerifier(config)

    @pytest.mark.asyncio
    async def test_valid_token_authenticated(self, verifier):
        """Valid tokens are authenticated."""
        result = await verifier.verify_token("valid-admin-token")
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, verifier):
        """Invalid tokens are rejected."""
        result = await verifier.verify_token("invalid-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, verifier):
        """Expired tokens are rejected."""
        token = create_signed_jwt({
            "sub": "user",
            "exp": int(time.time()) - 1,  # Expired
        })

        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_client_id_extracted(self, verifier):
        """Client ID is extracted from token."""
        token = create_signed_jwt({
            "sub": "client-abc-123",
            "exp": int(time.time()) + 3600,
        })

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "client-abc-123"

    @pytest.mark.asyncio
    async def test_unsigned_token_rejected(self, verifier):
        """Unsigned tokens are rejected even with valid claims."""
        token = create_unsigned_jwt({
            "sub": "attacker",
            "role": "admin",
            "exp": int(time.time()) + 3600,
        })

        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_forged_signature_rejected(self, verifier):
        """Tokens with forged signatures are rejected."""
        # Create a token signed with wrong key
        token = create_signed_jwt(
            {"sub": "attacker", "role": "admin", "exp": int(time.time()) + 3600},
            secret="attacker-controlled-secret-key-long"
        )

        result = await verifier.verify_token(token)
        assert result is None
