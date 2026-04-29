"""
Per-host rate-limit memory.

When a host returns HTTP 429 (or similar sustained block), burning 60+ seconds
on every scrape attempt is wasteful. This module records which hosts are
currently rate-limited and how long we should skip live-scrape attempts
against them.

Skip windows are persisted to disk at ``logs/rate_limit_state.json`` so they
survive process restarts — which matters because rate limits set server-side
often outlive the Python process that triggered them.

Usage:
    from primr.data.scraping.rate_limit_state import (
        record_rate_limit, is_rate_limited, clear_rate_limit,
    )

    record_rate_limit("www.example.com", reason="Kasada 429", duration=1200)
    if is_rate_limited("www.example.com"):
        # skip browser tiers, fall through to Wayback / EDGAR / Wikipedia
        ...
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from primr.config.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

STATE_FILE = Path(PROJECT_ROOT) / "logs" / "rate_limit_state.json"

# Default cooldown window when the caller doesn't specify one. Matches the
# duration most WAFs use for 429 cooldowns on unauthenticated bot traffic.
DEFAULT_COOLDOWN_SECONDS = 1200  # 20 minutes

_lock = threading.Lock()
_cache: dict[str, RateLimitEntry] | None = None


@dataclass
class RateLimitEntry:
    """A recorded rate-limit cooldown for a host."""

    host: str
    blocked_until: float  # unix timestamp
    reason: str

    def remaining_seconds(self) -> int:
        return max(0, int(self.blocked_until - time.time()))

    def is_active(self) -> bool:
        return time.time() < self.blocked_until

    def to_dict(self) -> dict:
        return {
            "host": self.host,
            "blocked_until": self.blocked_until,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RateLimitEntry:
        return cls(
            host=str(data["host"]),
            blocked_until=float(data["blocked_until"]),
            reason=str(data.get("reason", "unspecified")),
        )


def _load_state() -> dict[str, RateLimitEntry]:
    """Read state file; returns {} if missing or corrupt."""
    if not STATE_FILE.exists():
        return {}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("rate_limit_state unreadable (%s); resetting", e)
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, RateLimitEntry] = {}
    for host, entry in raw.items():
        try:
            result[host] = RateLimitEntry.from_dict(entry)
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _save_state(state: dict[str, RateLimitEntry]) -> None:
    """Write state to disk. Prunes expired entries on the way out."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        serializable = {host: entry.to_dict() for host, entry in state.items() if entry.is_active()}
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
    except OSError as e:
        logger.debug("failed to write rate_limit_state: %s", e)


def _get_cache() -> dict[str, RateLimitEntry]:
    global _cache
    if _cache is None:
        _cache = _load_state()
    return _cache


def _normalize_host(host: str) -> str:
    return host.strip().lower().lstrip(".").removeprefix("www.")


def record_rate_limit(
    host: str,
    reason: str = "HTTP 429",
    duration: int = DEFAULT_COOLDOWN_SECONDS,
) -> RateLimitEntry:
    """Mark a host as rate-limited for `duration` seconds from now."""
    key = _normalize_host(host)
    entry = RateLimitEntry(
        host=key,
        blocked_until=time.time() + max(60, duration),
        reason=reason,
    )
    with _lock:
        cache = _get_cache()
        # If an existing entry has a later expiration, keep it — back-off
        # should only grow, not shrink, on repeated 429s.
        existing = cache.get(key)
        if existing and existing.is_active() and existing.blocked_until > entry.blocked_until:
            return existing
        cache[key] = entry
        _save_state(cache)
    logger.info(
        "rate_limit: %s blocked for %ss (reason=%s)",
        key,
        entry.remaining_seconds(),
        reason,
    )
    return entry


def get_rate_limit(host: str) -> RateLimitEntry | None:
    """Return the active rate-limit entry for a host, or None."""
    key = _normalize_host(host)
    with _lock:
        cache = _get_cache()
        entry = cache.get(key)
        if entry and entry.is_active():
            return entry
        if entry:
            # expired — evict
            del cache[key]
            _save_state(cache)
    return None


def is_rate_limited(host: str) -> bool:
    return get_rate_limit(host) is not None


def clear_rate_limit(host: str) -> None:
    """Remove a host's rate-limit entry (e.g. after a successful scrape)."""
    key = _normalize_host(host)
    with _lock:
        cache = _get_cache()
        if key in cache:
            del cache[key]
            _save_state(cache)


def format_cooldown(entry: RateLimitEntry) -> str:
    """Human-friendly cooldown message for console output."""
    remaining = entry.remaining_seconds()
    minutes = remaining // 60
    seconds = remaining % 60
    if minutes >= 1:
        return f"{entry.host} rate-limited for {minutes}m {seconds}s ({entry.reason})"
    return f"{entry.host} rate-limited for {seconds}s ({entry.reason})"


def reset_all_for_testing() -> None:
    """Test helper: clear all state both in-memory and on disk."""
    global _cache
    with _lock:
        _cache = {}
        if STATE_FILE.exists():
            try:
                STATE_FILE.unlink()
            except OSError:
                pass
