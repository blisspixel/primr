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
    create_auth_middleware,
    get_entra_id_config,
    log_auth_failure,
    validate_entra_id_audience,
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
        token = create_signed_jwt(
            {
                "sub": "user-123",
                "role": "user",
                "exp": int(time.time()) + 3600,
            }
        )

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "user-123"
        assert "admin" not in result.scopes

    @pytest.mark.asyncio
    async def test_verify_jwt_admin_role(self, verifier):
        """JWT with admin role gets admin scope."""
        token = create_signed_jwt(
            {
                "sub": "admin-user",
                "role": "admin",
                "exp": int(time.time()) + 3600,
            }
        )

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "admin-user"
        assert "admin" in result.scopes

    @pytest.mark.asyncio
    async def test_verify_expired_jwt(self, verifier):
        """Expired JWT tokens are rejected."""
        token = create_signed_jwt(
            {
                "sub": "user-123",
                "exp": int(time.time()) - 3600,  # 1 hour ago
            }
        )

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_unsigned_jwt(self, verifier):
        """Unsigned JWT tokens (alg: none) are rejected."""
        token = create_unsigned_jwt(
            {
                "sub": "attacker",
                "role": "admin",
                "exp": int(time.time()) + 3600,
            }
        )

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_jwt_with_wrong_signature(self, verifier):
        """JWT with wrong signature is rejected."""
        # Create JWT signed with wrong secret
        token = create_signed_jwt(
            {"sub": "user", "exp": int(time.time()) + 3600},
            secret="wrong-secret-key-that-is-long-enough",
        )

        result = await verifier.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_jwt_without_secret_configured(self, verifier_no_jwt):
        """JWT tokens are rejected when no secret is configured."""
        token = create_signed_jwt(
            {
                "sub": "user-123",
                "exp": int(time.time()) + 3600,
            }
        )

        result = await verifier_no_jwt.verify_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_reject_unsupported_algorithm(self, verifier):
        """JWT with unsupported algorithm is rejected."""
        # Create JWT with RS256 (not in allowed algorithms)
        header = {"alg": "RS256", "typ": "JWT"}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
        payload_b64 = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "sub": "user",
                        "exp": int(time.time()) + 3600,
                    }
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
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
        wrong_issuer_token = create_signed_jwt(
            {
                "sub": "user",
                "iss": "wrong-issuer",
                "exp": int(time.time()) + 3600,
            }
        )
        result = await verifier.verify_token(wrong_issuer_token)
        assert result is None

        # Token with correct issuer
        correct_issuer_token = create_signed_jwt(
            {
                "sub": "user",
                "iss": "expected-issuer",
                "exp": int(time.time()) + 3600,
            }
        )
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
        wrong_aud_token = create_signed_jwt(
            {
                "sub": "user",
                "aud": "wrong-audience",
                "exp": int(time.time()) + 3600,
            }
        )
        result = await verifier.verify_token(wrong_aud_token)
        assert result is None

        # Token with correct audience
        correct_aud_token = create_signed_jwt(
            {
                "sub": "user",
                "aud": "expected-audience",
                "exp": int(time.time()) + 3600,
            }
        )
        result = await verifier.verify_token(correct_aud_token)
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_jwt_nbf_claim(self, verifier):
        """JWT not-before claim is validated."""
        # Token not valid yet
        future_token = create_signed_jwt(
            {
                "sub": "user",
                "nbf": int(time.time()) + 3600,  # Valid 1 hour from now
                "exp": int(time.time()) + 7200,
            }
        )
        result = await verifier.verify_token(future_token)
        assert result is None

        # Token already valid
        valid_token = create_signed_jwt(
            {
                "sub": "user",
                "nbf": int(time.time()) - 60,  # Valid since 1 minute ago
                "exp": int(time.time()) + 3600,
            }
        )
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
        token = create_signed_jwt(
            {
                "sub": "user",
                "exp": int(time.time()) - 1,  # Expired
            }
        )

        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_client_id_extracted(self, verifier):
        """Client ID is extracted from token."""
        token = create_signed_jwt(
            {
                "sub": "client-abc-123",
                "exp": int(time.time()) + 3600,
            }
        )

        result = await verifier.verify_token(token)

        assert result is not None
        assert result.client_id == "client-abc-123"

    @pytest.mark.asyncio
    async def test_unsigned_token_rejected(self, verifier):
        """Unsigned tokens are rejected even with valid claims."""
        token = create_unsigned_jwt(
            {
                "sub": "attacker",
                "role": "admin",
                "exp": int(time.time()) + 3600,
            }
        )

        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_forged_signature_rejected(self, verifier):
        """Tokens with forged signatures are rejected."""
        # Create a token signed with wrong key
        token = create_signed_jwt(
            {"sub": "attacker", "role": "admin", "exp": int(time.time()) + 3600},
            secret="attacker-controlled-secret-key-long",
        )

        result = await verifier.verify_token(token)
        assert result is None


class TestValidateEntraIdAudience:
    """Tests for validate_entra_id_audience function.

    Requirements: 3.1, 3.4
    """

    def test_matching_string_audience(self):
        """Audience validation passes when aud matches as string."""
        payload = {"aud": "app-id-123"}
        assert validate_entra_id_audience(payload, "app-id-123") is True

    def test_mismatched_string_audience(self):
        """Audience validation fails when aud doesn't match."""
        payload = {"aud": "wrong-app-id"}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_matching_list_audience(self):
        """Audience validation passes when aud list contains expected value."""
        payload = {"aud": ["app-id-123", "other-app"]}
        assert validate_entra_id_audience(payload, "app-id-123") is True

    def test_mismatched_list_audience(self):
        """Audience validation fails when aud list doesn't contain expected value."""
        payload = {"aud": ["other-app", "another-app"]}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_missing_audience_claim(self):
        """Audience validation fails when aud claim is missing."""
        payload = {"sub": "user-123"}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_empty_string_audience(self):
        """Audience validation fails when aud is empty string."""
        payload = {"aud": ""}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_empty_list_audience(self):
        """Audience validation fails when aud is empty list."""
        payload = {"aud": []}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_none_audience_in_payload(self):
        """Audience validation fails when aud is None."""
        payload = {"aud": None}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_malformed_audience_type(self):
        """Audience validation fails for non-string/non-list aud."""
        payload = {"aud": 12345}
        assert validate_entra_id_audience(payload, "app-id-123") is False

    def test_empty_expected_audience(self):
        """Audience validation fails when expected audience is empty."""
        payload = {"aud": "app-id-123"}
        assert validate_entra_id_audience(payload, "") is False

    def test_entra_id_jwt_audience_with_verifier(self):
        """Full JWT flow: Entra ID audience validated via PrimrTokenVerifier."""
        app_id = "api://my-container-app-id"
        config = AuthConfig(
            jwt_secret=TEST_JWT_SECRET,
            jwt_audience=app_id,
        )
        verifier = PrimrTokenVerifier(config)

        # Token with correct Entra ID audience
        token = create_signed_jwt(
            {
                "sub": "user@contoso.com",
                "aud": app_id,
                "exp": int(time.time()) + 3600,
            }
        )
        import asyncio

        result = asyncio.run(verifier.verify_token(token))
        assert result is not None
        assert result.client_id == "user@contoso.com"

    def test_entra_id_jwt_wrong_audience_rejected(self):
        """Full JWT flow: wrong Entra ID audience rejected with verifier."""
        config = AuthConfig(
            jwt_secret=TEST_JWT_SECRET,
            jwt_audience="api://my-container-app-id",
        )
        verifier = PrimrTokenVerifier(config)

        token = create_signed_jwt(
            {
                "sub": "user@contoso.com",
                "aud": "api://wrong-app-id",
                "exp": int(time.time()) + 3600,
            }
        )
        import asyncio

        result = asyncio.run(verifier.verify_token(token))
        assert result is None


class TestGetEntraIdConfig:
    """Tests for get_entra_id_config function.

    Requirements: 3.1, 3.4, 4.7
    """

    def test_config_with_audience_set(self, monkeypatch):
        """Config returns enabled=True when MCP_JWT_AUDIENCE is set."""
        monkeypatch.setenv("MCP_JWT_AUDIENCE", "api://my-app")
        monkeypatch.delenv("MCP_JWT_TENANT_ID", raising=False)

        config = get_entra_id_config()

        assert config["audience"] == "api://my-app"
        assert config["tenant_id"] is None
        assert config["enabled"] is True

    def test_config_with_audience_and_tenant(self, monkeypatch):
        """Config returns both audience and tenant_id when set."""
        monkeypatch.setenv("MCP_JWT_AUDIENCE", "api://my-app")
        monkeypatch.setenv("MCP_JWT_TENANT_ID", "tenant-abc-123")

        config = get_entra_id_config()

        assert config["audience"] == "api://my-app"
        assert config["tenant_id"] == "tenant-abc-123"
        assert config["enabled"] is True

    def test_config_without_audience(self, monkeypatch):
        """Config returns enabled=False when MCP_JWT_AUDIENCE is not set."""
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.delenv("MCP_JWT_TENANT_ID", raising=False)

        config = get_entra_id_config()

        assert config["audience"] is None
        assert config["tenant_id"] is None
        assert config["enabled"] is False

    def test_config_with_empty_audience(self, monkeypatch):
        """Config returns enabled=False when MCP_JWT_AUDIENCE is empty string."""
        monkeypatch.setenv("MCP_JWT_AUDIENCE", "")

        config = get_entra_id_config()

        assert config["enabled"] is False


class TestFoundryAgentServiceAuth:
    """Tests for Foundry Agent Service authentication methods.

    Validates that the auth system supports the three Foundry auth methods:
    - Key-based (API key via project connection)
    - Entra agent identity (JWT with aud claim)
    - Entra project managed identity (JWT with aud claim)

    Requirements: 4.7
    """

    @pytest.fixture
    def verifier_with_entra(self):
        """Verifier configured for Entra ID + API key auth."""
        config = AuthConfig(
            admin_tokens={"foundry-api-key-abc123"},
            jwt_secret=TEST_JWT_SECRET,
            jwt_audience="api://primr-container-app",
        )
        return PrimrTokenVerifier(config)

    @pytest.mark.asyncio
    async def test_key_based_auth(self, verifier_with_entra):
        """Key-based auth: API key via Foundry project connection."""
        result = await verifier_with_entra.verify_token("foundry-api-key-abc123")
        assert result is not None
        assert "admin" in result.scopes

    @pytest.mark.asyncio
    async def test_entra_agent_identity(self, verifier_with_entra):
        """Entra agent identity: JWT with matching audience."""
        token = create_signed_jwt(
            {
                "sub": "foundry-agent-identity",
                "aud": "api://primr-container-app",
                "iss": "https://login.microsoftonline.com/tenant-id/v2.0",
                "exp": int(time.time()) + 3600,
            }
        )
        result = await verifier_with_entra.verify_token(token)
        assert result is not None
        assert result.client_id == "foundry-agent-identity"

    @pytest.mark.asyncio
    async def test_entra_managed_identity(self, verifier_with_entra):
        """Entra project managed identity: JWT with matching audience."""
        token = create_signed_jwt(
            {
                "sub": "managed-identity-object-id",
                "aud": "api://primr-container-app",
                "oid": "managed-identity-object-id",
                "exp": int(time.time()) + 3600,
            }
        )
        result = await verifier_with_entra.verify_token(token)
        assert result is not None

    @pytest.mark.asyncio
    async def test_entra_wrong_audience_rejected(self, verifier_with_entra):
        """Entra token with wrong audience is rejected."""
        token = create_signed_jwt(
            {
                "sub": "foundry-agent",
                "aud": "api://wrong-app-id",
                "exp": int(time.time()) + 3600,
            }
        )
        result = await verifier_with_entra.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_api_key_rejected(self, verifier_with_entra):
        """Invalid API key is rejected."""
        result = await verifier_with_entra.verify_token("invalid-key")
        assert result is None


class TestJwtSecretCloudEnforcement:
    """Tests for L3: JWT secret length enforcement in cloud mode."""

    def test_short_secret_raises_in_cloud_mode(self, monkeypatch):
        """In cloud mode, short JWT secret raises ValueError."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("MCP_JWT_SECRET", "short")
        monkeypatch.delenv("MCP_ADMIN_TOKENS", raising=False)
        monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.delenv("MCP_ADMIN_TOKEN_MAX_AGE_HOURS", raising=False)

        with pytest.raises(ValueError, match="at least"):
            AuthConfig.from_env()

    def test_short_secret_warns_in_local_mode(self, monkeypatch, caplog):
        """In local mode, short JWT secret only logs a warning."""
        import logging

        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.setenv("MCP_JWT_SECRET", "short")
        monkeypatch.delenv("MCP_ADMIN_TOKENS", raising=False)
        monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.delenv("MCP_ADMIN_TOKEN_MAX_AGE_HOURS", raising=False)

        with caplog.at_level(logging.WARNING):
            config = AuthConfig.from_env()

        assert config.jwt_secret == "short"
        assert "shorter than" in caplog.text

    def test_long_secret_ok_in_cloud_mode(self, monkeypatch):
        """In cloud mode, sufficiently long JWT secret is accepted."""
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("MCP_JWT_SECRET", TEST_JWT_SECRET)
        monkeypatch.delenv("MCP_ADMIN_TOKENS", raising=False)
        monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.delenv("MCP_ADMIN_TOKEN_MAX_AGE_HOURS", raising=False)

        config = AuthConfig.from_env()
        assert config.jwt_secret == TEST_JWT_SECRET


class TestJwtSecretPlaceholderRejection:
    """Tests for L3b: refuse known placeholder JWT secrets.

    A long-but-public placeholder (e.g. the IaC's old 47-char
    "placeholder-replace-before-exposing-public-fqdn") passes the length
    floor yet lets anyone forge admin bearer tokens. Cloud deployments must
    fail closed rather than serve traffic with a guessable signing key.
    """

    # The exact literal the Azure Bicep used to seed into Key Vault.
    OLD_IAC_PLACEHOLDER = "placeholder-replace-before-exposing-public-fqdn"

    def _clean_env(self, monkeypatch):
        monkeypatch.delenv("MCP_ADMIN_TOKENS", raising=False)
        monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.delenv("MCP_ADMIN_TOKEN_MAX_AGE_HOURS", raising=False)

    def test_old_iac_placeholder_rejected_in_cloud_mode(self, monkeypatch):
        """The historical IaC placeholder is long enough to pass the length
        check but must still be refused in cloud mode."""
        assert len(self.OLD_IAC_PLACEHOLDER) >= 32  # premise: passes length floor
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("MCP_JWT_SECRET", self.OLD_IAC_PLACEHOLDER)
        self._clean_env(monkeypatch)

        with pytest.raises(ValueError, match="placeholder"):
            AuthConfig.from_env()

    @pytest.mark.parametrize(
        "placeholder",
        [
            "placeholder-replace-before-exposing-public-fqdn",
            "CHANGEME-CHANGEME-CHANGEME-CHANGEME-1234",
            "set-your-secret-here-set-your-secret-here",
            "dummy-secret-dummy-secret-dummy-secret12",
        ],
    )
    def test_assorted_placeholders_rejected_in_cloud_mode(self, monkeypatch, placeholder):
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("MCP_JWT_SECRET", placeholder)
        self._clean_env(monkeypatch)

        with pytest.raises(ValueError, match="placeholder"):
            AuthConfig.from_env()

    def test_placeholder_warns_in_local_mode(self, monkeypatch, caplog):
        """Local (non-cloud) mode only warns — stdio dev runs aren't network
        exposed, so we don't hard-fail and break local workflows."""
        import logging

        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.setenv("MCP_JWT_SECRET", self.OLD_IAC_PLACEHOLDER)
        self._clean_env(monkeypatch)

        with caplog.at_level(logging.WARNING):
            config = AuthConfig.from_env()

        assert config.jwt_secret == self.OLD_IAC_PLACEHOLDER
        assert "placeholder" in caplog.text.lower()

    def test_real_random_secret_accepted_in_cloud_mode(self, monkeypatch):
        """A genuine random secret (no placeholder markers) is accepted."""
        # 48 hex chars: random-looking, length-safe, and cannot contain any
        # placeholder marker (markers use letters absent from the hex alphabet).
        random_secret = "f3a9c1e87b6d4a2f90e5c7d1b8a4f6e2c3d9a0b1f4e6c8d2"
        monkeypatch.setenv("AZURE_CLIENT_ID", "some-client-id")
        monkeypatch.setenv("MCP_JWT_SECRET", random_secret)
        self._clean_env(monkeypatch)

        config = AuthConfig.from_env()
        assert config.jwt_secret == random_secret


class TestAdminTokenMaxAge:
    """Tests for L4: Admin token max age expiry."""

    @pytest.mark.asyncio
    async def test_admin_token_expires_after_max_age(self):
        """Admin token is rejected after max age from first use."""
        config = AuthConfig(
            admin_tokens={"expiring-token"},
            admin_token_max_age_hours=1.0,  # 1 hour
        )
        verifier = PrimrTokenVerifier(config)

        # First use — should succeed
        result = await verifier.verify_token("expiring-token")
        assert result is not None

        # Simulate time passing beyond max age
        token_hash = verifier._hash_token("expiring-token")
        verifier._admin_token_first_use[token_hash] = time.time() - 7200  # 2 hours ago
        verifier.clear_cache()  # Clear cache to force re-check

        result = await verifier.verify_token("expiring-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_admin_token_no_expiry_by_default(self):
        """Admin tokens don't expire when max age is not set."""
        config = AuthConfig(
            admin_tokens={"forever-token"},
            admin_token_max_age_hours=None,
        )
        verifier = PrimrTokenVerifier(config)

        result = await verifier.verify_token("forever-token")
        assert result is not None

    @pytest.mark.asyncio
    async def test_admin_token_within_max_age(self):
        """Admin token is accepted within max age window."""
        config = AuthConfig(
            admin_tokens={"fresh-token"},
            admin_token_max_age_hours=24.0,
        )
        verifier = PrimrTokenVerifier(config)

        result = await verifier.verify_token("fresh-token")
        assert result is not None

        # Clear cache but keep first-use time (recent)
        verifier.clear_cache()
        result = await verifier.verify_token("fresh-token")
        assert result is not None

    def test_max_age_from_env(self, monkeypatch):
        """MCP_ADMIN_TOKEN_MAX_AGE_HOURS is loaded from environment."""
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("MCP_JWT_SECRET", raising=False)
        monkeypatch.delenv("MCP_ADMIN_TOKENS", raising=False)
        monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.setenv("MCP_ADMIN_TOKEN_MAX_AGE_HOURS", "48")

        config = AuthConfig.from_env()
        assert config.admin_token_max_age_hours == 48.0

    def test_invalid_max_age_ignored(self, monkeypatch, caplog):
        """Invalid MCP_ADMIN_TOKEN_MAX_AGE_HOURS is ignored with warning."""
        import logging

        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("MCP_JWT_SECRET", raising=False)
        monkeypatch.delenv("MCP_ADMIN_TOKENS", raising=False)
        monkeypatch.delenv("MCP_JWT_ISSUER", raising=False)
        monkeypatch.delenv("MCP_JWT_AUDIENCE", raising=False)
        monkeypatch.setenv("MCP_ADMIN_TOKEN_MAX_AGE_HOURS", "not-a-number")

        with caplog.at_level(logging.WARNING):
            config = AuthConfig.from_env()

        assert config.admin_token_max_age_hours is None
        assert "Invalid MCP_ADMIN_TOKEN_MAX_AGE_HOURS" in caplog.text


class TestAuthMiddlewareEnforcement:
    """End-to-end proof that create_auth_middleware actually enforces auth.

    Regression: the previous implementation called RequireAuthMiddleware with
    the wrong argument and no required_scopes, so it raised at startup and the
    middleware was never installed (A2A swallowed the error and ran open; MCP
    crashed). These tests drive a real ASGI request through the wrapped app.
    """

    def _wrapped_app(self, token: str = "secret-admin-token"):
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route

        async def _ok(_request: object) -> PlainTextResponse:
            return PlainTextResponse("ok")

        inner = Starlette(routes=[Route("/x", _ok)])
        verifier = PrimrTokenVerifier(AuthConfig(admin_tokens={token}))
        return create_auth_middleware(verifier)(inner)

    def test_rejects_request_without_token(self):
        from starlette.testclient import TestClient

        client = TestClient(self._wrapped_app())
        assert client.get("/x").status_code == 401

    def test_rejects_invalid_token(self):
        from starlette.testclient import TestClient

        client = TestClient(self._wrapped_app())
        resp = client.get("/x", headers={"Authorization": "Bearer not-the-token"})
        assert resp.status_code == 401

    def test_accepts_valid_token(self):
        from starlette.testclient import TestClient

        client = TestClient(self._wrapped_app(token="secret-admin-token"))
        resp = client.get("/x", headers={"Authorization": "Bearer secret-admin-token"})
        assert resp.status_code == 200
        assert resp.text == "ok"
