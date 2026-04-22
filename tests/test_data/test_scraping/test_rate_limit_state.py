"""Tests for per-host rate-limit memory."""

from __future__ import annotations

import time

import pytest

from primr.data.scraping import rate_limit_state as rls


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    """Redirect state file into tmp_path and clear in-memory cache."""
    state_file = tmp_path / "rate_limit_state.json"
    monkeypatch.setattr(rls, "STATE_FILE", state_file)
    rls.reset_all_for_testing()
    yield
    rls.reset_all_for_testing()


def test_record_and_retrieve_rate_limit():
    rls.record_rate_limit("www.example.com", reason="HTTP 429", duration=300)
    entry = rls.get_rate_limit("www.example.com")
    assert entry is not None
    assert entry.host == "example.com"  # www. stripped
    assert 290 <= entry.remaining_seconds() <= 300
    assert entry.reason == "HTTP 429"


def test_is_rate_limited_strips_www_prefix():
    rls.record_rate_limit("example.com", duration=300)
    assert rls.is_rate_limited("example.com")
    assert rls.is_rate_limited("www.example.com")
    assert rls.is_rate_limited("WWW.Example.COM")


def test_expired_entries_are_evicted_on_read():
    # Record an entry in the past (already expired).
    entry = rls.RateLimitEntry(
        host="expired.com",
        blocked_until=time.time() - 60,
        reason="old",
    )
    cache = rls._get_cache()
    cache["expired.com"] = entry
    assert rls.get_rate_limit("expired.com") is None
    assert "expired.com" not in rls._get_cache()


def test_repeated_rate_limits_only_extend():
    rls.record_rate_limit("example.com", duration=600)
    first = rls.get_rate_limit("example.com")
    assert first is not None

    # A shorter duration must NOT shorten the existing cooldown.
    rls.record_rate_limit("example.com", duration=60)
    second = rls.get_rate_limit("example.com")
    assert second is not None
    assert second.blocked_until >= first.blocked_until


def test_clear_rate_limit():
    rls.record_rate_limit("example.com", duration=600)
    assert rls.is_rate_limited("example.com")
    rls.clear_rate_limit("example.com")
    assert not rls.is_rate_limited("example.com")


def test_format_cooldown_message_readable():
    rls.record_rate_limit("example.com", reason="Kasada 429", duration=180)
    entry = rls.get_rate_limit("example.com")
    assert entry is not None
    msg = rls.format_cooldown(entry)
    assert "example.com" in msg
    assert "Kasada 429" in msg
    assert "m " in msg or "s " in msg


def test_state_persists_across_reloads():
    rls.record_rate_limit("persist.com", reason="test", duration=600)
    # Force reload from disk.
    rls._cache = None
    entry = rls.get_rate_limit("persist.com")
    assert entry is not None
    assert entry.reason == "test"


def test_corrupt_state_file_is_ignored(tmp_path, monkeypatch):
    state_file = tmp_path / "corrupt.json"
    state_file.write_text("this is not JSON {{{ broken")
    monkeypatch.setattr(rls, "STATE_FILE", state_file)
    rls._cache = None
    assert not rls.is_rate_limited("anything.com")


def test_minimum_duration_enforced():
    """Durations under 60s are clamped up to prevent thrashing."""
    rls.record_rate_limit("example.com", duration=5)
    entry = rls.get_rate_limit("example.com")
    assert entry is not None
    assert entry.remaining_seconds() >= 55
