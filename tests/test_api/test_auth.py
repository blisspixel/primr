"""
Tests for the API authentication module.
"""

import pytest

from primr.api.auth import (
    APIKeyAuth,
    APIKeyInfo,
    get_auth,
    reset_auth,
    verify_api_key,
    create_api_key,
    revoke_api_key,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_auth()
    yield
    reset_auth()


@pytest.fixture
def auth():
    """Create a fresh auth manager."""
    return APIKeyAuth()


# =============================================================================
# API KEY INFO TESTS
# =============================================================================

class TestAPIKeyInfo:
    """Tests for APIKeyInfo dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        info = APIKeyInfo(key_hash="abc123", name="test")
        assert info.is_active is True
        assert info.rate_limit == 100
        assert "read" in info.scopes
        assert "write" in info.scopes
    
    def test_request_count_starts_zero(self):
        """Test request count starts at zero."""
        info = APIKeyInfo(key_hash="abc123", name="test")
        assert info.request_count == 0


# =============================================================================
# API KEY AUTH TESTS
# =============================================================================

class TestAPIKeyAuth:
    """Tests for APIKeyAuth class."""
    
    def test_create_key(self, auth):
        """Test key creation."""
        key = auth.create_key("test-app")
        
        assert key is not None
        assert key.startswith("cr_")
        assert len(key) > 20
    
    def test_verify_valid_key(self, auth):
        """Test verifying a valid key."""
        key = auth.create_key("test-app")
        
        assert auth.verify(key) is True
    
    def test_verify_invalid_key(self, auth):
        """Test verifying an invalid key."""
        assert auth.verify("invalid-key") is False
    
    def test_verify_empty_key(self, auth):
        """Test verifying empty key."""
        assert auth.verify("") is False
        assert auth.verify(None) is False
    
    def test_verify_updates_stats(self, auth):
        """Test that verification updates usage stats."""
        key = auth.create_key("test-app")
        
        auth.verify(key)
        auth.verify(key)
        
        info = auth.get_key_info(key)
        assert info.request_count == 2
        assert info.last_used is not None
    
    def test_revoke_key(self, auth):
        """Test key revocation."""
        key = auth.create_key("test-app")
        
        assert auth.verify(key) is True
        assert auth.revoke(key) is True
        assert auth.verify(key) is False
    
    def test_revoke_invalid_key(self, auth):
        """Test revoking invalid key."""
        assert auth.revoke("invalid-key") is False
    
    def test_get_key_info(self, auth):
        """Test getting key info."""
        key = auth.create_key("test-app", rate_limit=50)
        
        info = auth.get_key_info(key)
        assert info is not None
        assert info.name == "test-app"
        assert info.rate_limit == 50
    
    def test_get_key_info_invalid(self, auth):
        """Test getting info for invalid key."""
        info = auth.get_key_info("invalid-key")
        assert info is None
    
    def test_has_scope(self, auth):
        """Test scope checking."""
        key = auth.create_key("test-app", scopes={"read"})
        
        assert auth.has_scope(key, "read") is True
        assert auth.has_scope(key, "write") is False
    
    def test_has_scope_invalid_key(self, auth):
        """Test scope checking with invalid key."""
        assert auth.has_scope("invalid", "read") is False
    
    def test_list_keys(self, auth):
        """Test listing keys."""
        auth.create_key("app-1")
        auth.create_key("app-2")
        
        keys = auth.list_keys()
        assert len(keys) == 2
        assert "app-1" in keys
        assert "app-2" in keys
    
    def test_custom_rate_limit(self, auth):
        """Test custom rate limit."""
        key = auth.create_key("test-app", rate_limit=500)
        
        info = auth.get_key_info(key)
        assert info.rate_limit == 500
    
    def test_custom_scopes(self, auth):
        """Test custom scopes."""
        key = auth.create_key("test-app", scopes={"read", "admin"})
        
        info = auth.get_key_info(key)
        assert info.scopes == {"read", "admin"}


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton access."""
    
    def test_get_auth_returns_same(self):
        """Test get_auth returns same instance."""
        a1 = get_auth()
        a2 = get_auth()
        assert a1 is a2
    
    def test_reset_auth(self):
        """Test reset creates new instance."""
        a1 = get_auth()
        reset_auth()
        a2 = get_auth()
        assert a1 is not a2


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_create_api_key_function(self):
        """Test create_api_key convenience function."""
        key = create_api_key("test-app")
        assert key is not None
        assert key.startswith("cr_")
    
    def test_verify_api_key_function(self):
        """Test verify_api_key convenience function."""
        key = create_api_key("test-app")
        assert verify_api_key(key) is True
        assert verify_api_key("invalid") is False
    
    def test_revoke_api_key_function(self):
        """Test revoke_api_key convenience function."""
        key = create_api_key("test-app")
        assert revoke_api_key(key) is True
        assert verify_api_key(key) is False


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety."""
    
    def test_concurrent_verification(self, auth):
        """Test concurrent key verification."""
        import threading
        
        key = auth.create_key("test-app")
        results = []
        
        def verify_key():
            for _ in range(100):
                results.append(auth.verify(key))
        
        threads = [threading.Thread(target=verify_key) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert all(results)
        
        info = auth.get_key_info(key)
        assert info.request_count == 500
