"""
API authentication for the research service.

This module provides:
- API key generation and validation
- Key revocation
- Rate limit tracking per key
"""

import hashlib
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime

from primr.utils.logging_config import get_logger

logger = get_logger("api.auth")


@dataclass
class APIKeyInfo:
    """Information about an API key."""

    key_hash: str
    name: str
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime | None = None
    request_count: int = 0
    is_active: bool = True
    rate_limit: int = 100  # Requests per hour
    scopes: set[str] = field(default_factory=lambda: {"read", "write"})


class APIKeyAuth:
    """
    API key authentication manager.

    Example:
        auth = APIKeyAuth()
        key = auth.create_key("my-app")

        if auth.verify(key):
            print("Valid key")
    """

    def __init__(self):
        """Initialize the auth manager."""
        self._keys: dict[str, APIKeyInfo] = {}
        self._lock = threading.Lock()
        logger.debug("APIKeyAuth initialized")

    def create_key(
        self,
        name: str,
        rate_limit: int = 100,
        scopes: set[str] | None = None,
    ) -> str:
        """
        Create a new API key.

        Args:
            name: Name/description for the key
            rate_limit: Requests per hour limit
            scopes: Permission scopes

        Returns:
            The generated API key (only returned once!)
        """
        # Generate a secure random key
        key = f"cr_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(key)

        with self._lock:
            self._keys[key_hash] = APIKeyInfo(
                key_hash=key_hash,
                name=name,
                rate_limit=rate_limit,
                scopes=scopes or {"read", "write"},
            )

        logger.info(f"Created API key: {name}")
        return key

    def verify(self, key: str) -> bool:
        """
        Verify an API key.

        Args:
            key: The API key to verify

        Returns:
            True if valid and active
        """
        if not key:
            return False

        key_hash = self._hash_key(key)

        with self._lock:
            info = self._keys.get(key_hash)
            if info is None:
                logger.warning("Invalid API key attempted")
                return False

            if not info.is_active:
                logger.warning(f"Revoked API key used: {info.name}")
                return False

            # Update usage stats
            info.last_used = datetime.now()
            info.request_count += 1

            return True

    def get_key_info(self, key: str) -> APIKeyInfo | None:
        """
        Get information about an API key.

        Args:
            key: The API key

        Returns:
            APIKeyInfo or None if not found
        """
        key_hash = self._hash_key(key)

        with self._lock:
            return self._keys.get(key_hash)

    def revoke(self, key: str) -> bool:
        """
        Revoke an API key.

        Args:
            key: The API key to revoke

        Returns:
            True if revoked, False if not found
        """
        key_hash = self._hash_key(key)

        with self._lock:
            info = self._keys.get(key_hash)
            if info is None:
                return False

            info.is_active = False
            logger.info(f"Revoked API key: {info.name}")
            return True

    def has_scope(self, key: str, scope: str) -> bool:
        """
        Check if a key has a specific scope.

        Args:
            key: The API key
            scope: The scope to check

        Returns:
            True if key has the scope
        """
        info = self.get_key_info(key)
        if info is None:
            return False
        return scope in info.scopes

    def list_keys(self) -> dict[str, dict]:
        """
        List all API keys (without the actual keys).

        Returns:
            Dictionary of key info by name
        """
        with self._lock:
            return {
                info.name: {
                    "created_at": info.created_at.isoformat(),
                    "last_used": info.last_used.isoformat() if info.last_used else None,
                    "request_count": info.request_count,
                    "is_active": info.is_active,
                    "rate_limit": info.rate_limit,
                }
                for info in self._keys.values()
            }

    def _hash_key(self, key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_auth: APIKeyAuth | None = None


def get_auth() -> APIKeyAuth:
    """Get the global auth instance."""
    global _auth
    if _auth is None:
        _auth = APIKeyAuth()
    return _auth


def reset_auth() -> None:
    """Reset the global auth (useful for testing)."""
    global _auth
    _auth = None


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def verify_api_key(key: str) -> bool:
    """
    Verify an API key.

    Args:
        key: The API key to verify

    Returns:
        True if valid
    """
    return get_auth().verify(key)


def create_api_key(name: str, rate_limit: int = 100) -> str:
    """
    Create a new API key.

    Args:
        name: Name for the key
        rate_limit: Requests per hour

    Returns:
        The generated API key
    """
    return get_auth().create_key(name, rate_limit)


def revoke_api_key(key: str) -> bool:
    """
    Revoke an API key.

    Args:
        key: The key to revoke

    Returns:
        True if revoked
    """
    return get_auth().revoke(key)
