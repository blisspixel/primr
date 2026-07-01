"""
API authentication for the research service.

This module provides:
- API key generation and validation
- Key rotation with grace periods
- Key revocation
- Rate limit tracking per key
- Expiration support
"""

import hashlib
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from primr.utils.logging_config import get_logger

logger = get_logger("api.auth")

# Default rotation grace period (both old and new keys work)
DEFAULT_ROTATION_GRACE_HOURS = 24

# Default key expiration (0 = never expires)
DEFAULT_KEY_EXPIRATION_DAYS = 0


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

    # Rotation support
    expires_at: datetime | None = None  # Key expiration time
    rotated_from: str | None = None  # Hash of previous key (for rotation tracking)
    rotation_grace_until: datetime | None = None  # Grace period end for old key


class APIKeyAuth:
    """
    API key authentication manager with rotation support.

    Features:
    - Secure key generation with cr_ prefix
    - Key rotation with configurable grace period
    - Key expiration support
    - Usage tracking and rate limiting

    Example:
        auth = APIKeyAuth()
        key = auth.create_key("my-app")

        if auth.verify(key):
            print("Valid key")

        # Rotate key (old key works during grace period)
        new_key = auth.rotate_key(key, grace_hours=24)
    """

    def __init__(self):
        """Initialize the auth manager."""
        self._keys: dict[str, APIKeyInfo] = {}
        self._lock = threading.Lock()
        self._rotation_callbacks: list[Callable[[str, str, str], None]] = []
        logger.debug("APIKeyAuth initialized")

    def create_key(
        self,
        name: str,
        rate_limit: int = 100,
        scopes: set[str] | None = None,
        expires_in_days: int = DEFAULT_KEY_EXPIRATION_DAYS,
    ) -> str:
        """
        Create a new API key.

        Args:
            name: Name/description for the key
            rate_limit: Requests per hour limit
            scopes: Permission scopes
            expires_in_days: Days until key expires (0 = never)

        Returns:
            The generated API key (only returned once!)
        """
        # Generate a secure random key
        key = f"cr_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(key)

        expires_at = None
        if expires_in_days > 0:
            expires_at = datetime.now() + timedelta(days=expires_in_days)

        with self._lock:
            self._keys[key_hash] = APIKeyInfo(
                key_hash=key_hash,
                name=name,
                rate_limit=rate_limit,
                scopes=scopes or {"read", "write"},
                expires_at=expires_at,
            )

        logger.info(f"Created API key: {name}")
        return key

    def rotate_key(
        self,
        old_key: str,
        grace_hours: int = DEFAULT_ROTATION_GRACE_HOURS,
    ) -> str | None:
        """
        Rotate an API key, generating a new one while keeping the old one valid.

        During the grace period, both old and new keys will work.
        After the grace period, only the new key works.

        Args:
            old_key: The current API key to rotate
            grace_hours: Hours to keep old key valid (default: 24)

        Returns:
            New API key, or None if old key is invalid

        Example:
            # Rotate with 24-hour grace period
            new_key = auth.rotate_key(old_key, grace_hours=24)

            # Update your application to use new_key
            # Old key continues working for 24 hours
        """
        old_hash = self._hash_key(old_key)

        with self._lock:
            old_info = self._keys.get(old_hash)
            if old_info is None or not old_info.is_active:
                logger.warning("Attempted to rotate invalid/inactive key")
                return None

            # Mirror verify()'s expiry/grace gates here. Without these
            # checks an old key whose rotation grace had already elapsed
            # (but which had not yet been seen by verify() or
            # cleanup_expired()) could still mint a brand-new active key
            # — effectively reviving a retired credential indefinitely.
            now = datetime.now()
            if old_info.expires_at and now > old_info.expires_at:
                logger.warning("Refusing to rotate expired key: %s", old_info.name)
                old_info.is_active = False
                return None
            if old_info.rotation_grace_until and now > old_info.rotation_grace_until:
                logger.warning(
                    "Refusing to rotate key whose grace window has elapsed: %s",
                    old_info.name,
                )
                old_info.is_active = False
                return None

            # Generate new key
            new_key = f"cr_{secrets.token_urlsafe(32)}"
            new_hash = self._hash_key(new_key)

            # Set grace period on old key
            grace_until = now + timedelta(hours=grace_hours)
            old_info.rotation_grace_until = grace_until

            # Create new key info, inheriting settings from old key
            new_info = APIKeyInfo(
                key_hash=new_hash,
                name=old_info.name,
                rate_limit=old_info.rate_limit,
                scopes=old_info.scopes.copy(),
                rotated_from=old_hash,
                expires_at=old_info.expires_at,  # Inherit expiration
            )
            self._keys[new_hash] = new_info

            logger.info(
                f"Rotated API key: {old_info.name}, grace period until {grace_until.isoformat()}"
            )

        # Notify callbacks
        for callback in self._rotation_callbacks:
            try:
                callback(old_info.name, old_key[:12] + "...", new_key[:12] + "...")
            except Exception as e:
                logger.error(f"Rotation callback failed: {e}")

        return new_key

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

            # Check expiration
            if info.expires_at and datetime.now() > info.expires_at:
                logger.warning(f"Expired API key used: {info.name}")
                return False

            # Check if in rotation grace period (old key being phased out)
            if info.rotation_grace_until:
                if datetime.now() > info.rotation_grace_until:
                    # Grace period expired, deactivate old key
                    info.is_active = False
                    logger.info(f"Rotation grace period expired: {info.name}")
                    return False
                else:
                    logger.debug(f"Key in rotation grace period: {info.name}")

            # Update usage stats
            info.last_used = datetime.now()
            info.request_count += 1

            return True

    def on_rotation(self, callback: Callable[[str, str, str], None]) -> None:
        """
        Register a callback for key rotation events.

        Callback receives: (key_name, old_key_prefix, new_key_prefix)

        Useful for:
        - Sending notifications about key rotation
        - Updating external systems
        - Audit logging

        Args:
            callback: Function to call on rotation
        """
        self._rotation_callbacks.append(callback)

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

    def get_expiring_keys(self, within_days: int = 7) -> list[dict]:
        """
        Get keys expiring within the specified number of days.

        Useful for sending expiration warnings.

        Args:
            within_days: Number of days to look ahead

        Returns:
            List of key info dicts for expiring keys
        """
        threshold = datetime.now() + timedelta(days=within_days)
        expiring = []

        with self._lock:
            for info in self._keys.values():
                if info.is_active and info.expires_at and info.expires_at <= threshold:
                    expiring.append(
                        {
                            "name": info.name,
                            "expires_at": info.expires_at.isoformat(),
                            "days_remaining": (info.expires_at - datetime.now()).days,
                        }
                    )

        return expiring

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
                    "expires_at": info.expires_at.isoformat() if info.expires_at else None,
                    "in_rotation": info.rotation_grace_until is not None,
                }
                for info in self._keys.values()
            }

    def cleanup_expired(self) -> int:
        """
        Remove expired and rotated-out keys from memory.

        Call periodically to prevent memory growth.

        Returns:
            Number of keys cleaned up
        """
        now = datetime.now()
        to_remove = []

        with self._lock:
            for key_hash, info in self._keys.items():
                # Remove if expired
                if (info.expires_at and now > info.expires_at) or (
                    info.rotation_grace_until and now > info.rotation_grace_until
                ):
                    to_remove.append(key_hash)

            for key_hash in to_remove:
                del self._keys[key_hash]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} expired/rotated keys")

        return len(to_remove)

    def _hash_key(self, key: str) -> str:
        """Fingerprint a generated high-entropy API key for in-memory lookup."""
        return hashlib.blake2b(
            key.encode(),
            digest_size=32,
            person=b"primr-api-key",
        ).hexdigest()


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_auth: APIKeyAuth | None = None
_auth_lock = threading.Lock()


def get_auth() -> APIKeyAuth:
    """Get the global auth instance.

    Double-check locking so concurrent FastAPI workers don't race to
    create two different APIKeyAuth instances — that would split key
    revocations / rotations across instances, so a key revoked on one
    worker could still authenticate on another until process restart.
    """
    global _auth
    if _auth is None:
        with _auth_lock:
            if _auth is None:
                _auth = APIKeyAuth()
    return _auth


def reset_auth() -> None:
    """Reset the global auth (useful for testing)."""
    global _auth
    with _auth_lock:
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


def create_api_key(
    name: str,
    rate_limit: int = 100,
    expires_in_days: int = 0,
) -> str:
    """
    Create a new API key.

    Args:
        name: Name for the key
        rate_limit: Requests per hour
        expires_in_days: Days until expiration (0 = never)

    Returns:
        The generated API key
    """
    return get_auth().create_key(name, rate_limit, expires_in_days=expires_in_days)


def rotate_api_key(key: str, grace_hours: int = 24) -> str | None:
    """
    Rotate an API key.

    Args:
        key: Current key to rotate
        grace_hours: Hours to keep old key valid

    Returns:
        New API key, or None if rotation failed
    """
    return get_auth().rotate_key(key, grace_hours)


def revoke_api_key(key: str) -> bool:
    """
    Revoke an API key.

    Args:
        key: The key to revoke

    Returns:
        True if revoked
    """
    return get_auth().revoke(key)
