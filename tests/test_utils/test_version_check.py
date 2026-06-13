"""Tests for primr.utils.version_check (PyPI update checking)."""

from __future__ import annotations

import json
import time

import pytest

from primr.utils import version_check as vc


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Point the user cache (and thus the update-check cache) at tmp_path."""
    monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("PRIMR_NO_UPDATE_CHECK", raising=False)
    return


# --- version parsing / comparison ---


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.31.0", (1, 31, 0)),
        ("v2.0", (2, 0)),
        ("1.31.0rc1", (1, 31, 0)),
        ("  1.2.3  ", (1, 2, 3)),
        ("garbage", ()),
        ("", ()),
    ],
)
def test_parse_version(value, expected):
    assert vc.parse_version(value) == expected


@pytest.mark.parametrize(
    "candidate,current,expected",
    [
        ("1.32.0", "1.31.0", True),
        ("2.0", "1.31.0", True),
        ("1.31.0", "1.31.0", False),
        ("1.30.0", "1.31.0", False),
        ("1.31.1", "1.31.0", True),
        ("garbage", "1.31.0", False),
    ],
)
def test_is_newer(candidate, current, expected):
    assert vc.is_newer(candidate, current) is expected


# --- opt-out ---


def test_update_check_disabled_env(monkeypatch):
    monkeypatch.setenv("PRIMR_NO_UPDATE_CHECK", "1")
    assert vc.update_check_disabled() is True
    monkeypatch.setenv("PRIMR_NO_UPDATE_CHECK", "yes")
    assert vc.update_check_disabled() is True
    monkeypatch.setenv("PRIMR_NO_UPDATE_CHECK", "0")
    assert vc.update_check_disabled() is False


def test_get_latest_version_respects_optout(monkeypatch):
    monkeypatch.setenv("PRIMR_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(vc, "fetch_latest_version", lambda *a, **k: pytest.fail("network!"))
    assert vc.get_latest_version() is None


def test_force_bypasses_optout(monkeypatch):
    monkeypatch.setenv("PRIMR_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(vc, "fetch_latest_version", lambda *a, **k: "9.9.9")
    assert vc.get_latest_version(force=True) == "9.9.9"


# --- caching ---


def test_caches_fetched_version(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(*_a, **_k):
        calls["n"] += 1
        return "1.40.0"

    monkeypatch.setattr(vc, "fetch_latest_version", fake_fetch)

    assert vc.get_latest_version() == "1.40.0"
    # Second call within TTL serves from cache, no extra network hit.
    assert vc.get_latest_version() == "1.40.0"
    assert calls["n"] == 1


def test_stale_cache_refetches(monkeypatch):
    # Pre-seed a stale cache entry.
    cache_file = vc._cache_path()
    cache_file.write_text(
        json.dumps(
            {"checked_at": time.time() - (vc._CACHE_TTL_SECONDS + 10), "latest_version": "1.0.0"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(vc, "fetch_latest_version", lambda *a, **k: "2.0.0")
    assert vc.get_latest_version() == "2.0.0"


def test_corrupt_cache_is_ignored(monkeypatch):
    vc._cache_path().write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(vc, "fetch_latest_version", lambda *a, **k: "3.0.0")
    assert vc.get_latest_version() == "3.0.0"


def test_network_failure_returns_none(monkeypatch):
    monkeypatch.setattr(vc, "fetch_latest_version", lambda *a, **k: None)
    assert vc.get_latest_version() is None


# --- check_for_update ---


def test_check_for_update_newer(monkeypatch):
    monkeypatch.setattr(vc, "get_latest_version", lambda **k: "5.0.0")
    assert vc.check_for_update("1.31.0") == "5.0.0"


def test_check_for_update_uptodate(monkeypatch):
    monkeypatch.setattr(vc, "get_latest_version", lambda **k: "1.31.0")
    assert vc.check_for_update("1.31.0") is None


def test_check_for_update_swallows_errors(monkeypatch):
    def boom(**_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(vc, "get_latest_version", boom)
    # Must never propagate.
    assert vc.check_for_update("1.31.0") is None


# --- install-method detection ---


def test_detect_pipx_install(monkeypatch):
    monkeypatch.setattr(vc.sys, "prefix", "/home/u/.local/pipx/venvs/primr")
    method = vc.detect_install_method()
    assert method.kind == "pipx"
    assert method.upgrade_command == ["pipx", "upgrade", "primr"]


def test_detect_pip_install(monkeypatch):
    monkeypatch.setattr(vc.sys, "prefix", "/usr/local")
    method = vc.detect_install_method()
    assert method.kind == "pip"
    assert method.upgrade_command[-3:] == ["install", "--upgrade", "primr"]
