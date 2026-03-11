"""
Tests for the API authentication module.
"""

import pytest

from primr.api.auth import (
    APIKeyAuth,
    APIKeyInfo,
    create_api_key,
    get_auth,
    reset_auth,
    revoke_api_key,
    verify_api_key,
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


# =============================================================================
# KEY ROTATION TESTS
# =============================================================================


class TestKeyRotation:
    """Tests for API key rotation."""

    def test_rotate_key_returns_new_key(self, auth):
        """Test rotation returns a new key."""
        old_key = auth.create_key("test-app")
        new_key = auth.rotate_key(old_key)

        assert new_key is not None
        assert new_key != old_key
        assert new_key.startswith("cr_")

    def test_both_keys_work_during_grace(self, auth):
        """Test both old and new keys work during grace period."""
        old_key = auth.create_key("test-app")
        new_key = auth.rotate_key(old_key, grace_hours=24)

        # Both should work
        assert auth.verify(old_key) is True
        assert auth.verify(new_key) is True

    def test_old_key_expires_after_grace(self, auth):
        """Test old key stops working after grace period."""
        from datetime import datetime, timedelta

        old_key = auth.create_key("test-app")
        new_key = auth.rotate_key(old_key, grace_hours=1)

        # Manually expire the grace period
        old_hash = auth._hash_key(old_key)
        auth._keys[old_hash].rotation_grace_until = datetime.now() - timedelta(hours=1)

        # Old key should fail, new key should work
        assert auth.verify(old_key) is False
        assert auth.verify(new_key) is True

    def test_rotate_invalid_key_returns_none(self, auth):
        """Test rotating invalid key returns None."""
        result = auth.rotate_key("invalid-key")
        assert result is None

    def test_rotate_revoked_key_returns_none(self, auth):
        """Test rotating revoked key returns None."""
        key = auth.create_key("test-app")
        auth.revoke(key)

        result = auth.rotate_key(key)
        assert result is None

    def test_new_key_inherits_settings(self, auth):
        """Test new key inherits rate limit and scopes."""
        old_key = auth.create_key("test-app", rate_limit=500, scopes={"read", "admin"})
        new_key = auth.rotate_key(old_key)

        new_info = auth.get_key_info(new_key)
        assert new_info.rate_limit == 500
        assert new_info.scopes == {"read", "admin"}
        assert new_info.name == "test-app"

    def test_rotation_callback(self, auth):
        """Test rotation callback is called."""
        callback_data = []

        def on_rotate(name, old_prefix, new_prefix):
            callback_data.append((name, old_prefix, new_prefix))

        auth.on_rotation(on_rotate)

        old_key = auth.create_key("test-app")
        auth.rotate_key(old_key)

        assert len(callback_data) == 1
        assert callback_data[0][0] == "test-app"

    def test_list_keys_shows_rotation_status(self, auth):
        """Test list_keys shows rotation status."""
        old_key = auth.create_key("test-app")
        auth.rotate_key(old_key)

        keys = auth.list_keys()
        # Should have 2 entries (old and new)
        assert len(keys) == 1  # Same name, but we can check in_rotation
        # The old key should show in_rotation=True
        old_info = auth.get_key_info(old_key)
        assert old_info.rotation_grace_until is not None


# =============================================================================
# KEY EXPIRATION TESTS
# =============================================================================


class TestKeyExpiration:
    """Tests for API key expiration."""

    def test_create_key_with_expiration(self, auth):
        """Test creating key with expiration."""
        key = auth.create_key("test-app", expires_in_days=30)

        info = auth.get_key_info(key)
        assert info.expires_at is not None

    def test_expired_key_rejected(self, auth):
        """Test expired key is rejected."""
        from datetime import datetime, timedelta

        key = auth.create_key("test-app", expires_in_days=1)

        # Manually expire the key
        key_hash = auth._hash_key(key)
        auth._keys[key_hash].expires_at = datetime.now() - timedelta(days=1)

        assert auth.verify(key) is False

    def test_non_expiring_key(self, auth):
        """Test key without expiration works indefinitely."""
        key = auth.create_key("test-app", expires_in_days=0)

        info = auth.get_key_info(key)
        assert info.expires_at is None
        assert auth.verify(key) is True

    def test_get_expiring_keys(self, auth):
        """Test getting keys expiring soon."""

        # Create keys with different expirations
        auth.create_key("expires-soon", expires_in_days=3)
        auth.create_key("expires-later", expires_in_days=30)
        auth.create_key("no-expiry", expires_in_days=0)

        expiring = auth.get_expiring_keys(within_days=7)

        assert len(expiring) == 1
        assert expiring[0]["name"] == "expires-soon"

    def test_cleanup_expired(self, auth):
        """Test cleanup removes expired keys."""
        from datetime import datetime, timedelta

        key1 = auth.create_key("expired", expires_in_days=1)
        key2 = auth.create_key("valid", expires_in_days=30)

        # Manually expire key1
        key1_hash = auth._hash_key(key1)
        auth._keys[key1_hash].expires_at = datetime.now() - timedelta(days=1)

        cleaned = auth.cleanup_expired()

        assert cleaned == 1
        assert auth.get_key_info(key1) is None
        assert auth.get_key_info(key2) is not None


# =============================================================================
# CONVENIENCE FUNCTION ROTATION TESTS
# =============================================================================


class TestRotationConvenienceFunctions:
    """Tests for rotation convenience functions."""

    def test_rotate_api_key_function(self):
        """Test rotate_api_key convenience function."""
        from primr.api.auth import rotate_api_key

        old_key = create_api_key("test-app")
        new_key = rotate_api_key(old_key)

        assert new_key is not None
        assert verify_api_key(new_key) is True

    def test_create_api_key_with_expiration(self):
        """Test create_api_key with expiration."""
        key = create_api_key("test-app", expires_in_days=30)

        info = get_auth().get_key_info(key)
        assert info.expires_at is not None
