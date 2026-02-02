"""
Tests for HTTP authentication.

Task 12: HTTP authentication
"""

import base64
import json
import os
import time

import pytest

from primr.mcp_server.auth import (
    AuthConfig,
    AuthContext,
    AuthResult,
    PrimrTokenVerifier,
    log_auth_failure,
)


class TestAuthConfig:
    """Tests for AuthConfig."""
    
    def test_default_config(self):
        """Default config has empty admin tokens."""
        config = AuthConfig()
        assert config.admin_tokens == set()
        assert config.require_auth is True
    
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


class TestPrimrTokenVerifier:
    """Tests for PrimrTokenVerifier."""
    
    @pytest.fixture
    def verifier(self):
        """Create a verifier with test admin tokens."""
        config = AuthConfig(admin_tokens={"test-admin-token", "another-admin"})
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
    async def test_verify_jwt_token(self, verifier):
        """Valid JWT tokens are verified."""
        # Create a simple JWT (header.payload.signature)
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "user-123",
            "role": "user",
            "exp": int(time.time()) + 3600,  # 1 hour from now
        }).encode()).decode().rstrip("=")
        signature = "fake-signature"
        
        token = f"{header}.{payload}.{signature}"
        result = await verifier.verify_token(token)
        
        assert result is not None
        assert result.client_id == "user-123"
        assert "admin" not in result.scopes
    
    @pytest.mark.asyncio
    async def test_verify_jwt_admin_role(self, verifier):
        """JWT with admin role gets admin scope."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "admin-user",
            "role": "admin",
            "exp": int(time.time()) + 3600,
        }).encode()).decode().rstrip("=")
        signature = "fake-signature"
        
        token = f"{header}.{payload}.{signature}"
        result = await verifier.verify_token(token)
        
        assert result is not None
        assert result.client_id == "admin-user"
        assert "admin" in result.scopes
    
    @pytest.mark.asyncio
    async def test_verify_expired_jwt(self, verifier):
        """Expired JWT tokens are rejected."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "user-123",
            "exp": int(time.time()) - 3600,  # 1 hour ago
        }).encode()).decode().rstrip("=")
        signature = "fake-signature"
        
        token = f"{header}.{payload}.{signature}"
        result = await verifier.verify_token(token)
        
        assert result is None
    
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
        """Create a verifier with test admin tokens."""
        config = AuthConfig(admin_tokens={"valid-admin-token"})
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
        # Create expired JWT
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "user",
            "exp": int(time.time()) - 1,  # Expired
        }).encode()).decode().rstrip("=")
        token = f"{header}.{payload}.sig"
        
        result = await verifier.verify_token(token)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_client_id_extracted(self, verifier):
        """Client ID is extracted from token."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "client-abc-123",
            "exp": int(time.time()) + 3600,
        }).encode()).decode().rstrip("=")
        token = f"{header}.{payload}.sig"
        
        result = await verifier.verify_token(token)
        
        assert result is not None
        assert result.client_id == "client-abc-123"
