"""Unit tests for primr.ai.file_search_resources.

Focused tests on the Primr-ownership detector, the resource age
calculator, and the cleanup orchestrator's two-gate (ownership +
staleness) safety policy.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from primr.ai.file_search_resources import (
    _DEFAULT_STALE_AGE_SECONDS,
    _PRIMR_RESOURCE_PREFIX,
    _is_primr_owned,
    _resource_age_seconds,
    cleanup_orphaned_resources,
)

# ---------------------------------------------------------------------------
# _is_primr_owned
# ---------------------------------------------------------------------------


class TestIsPrimrOwned:
    def test_true_for_primr_prefix(self):
        assert _is_primr_owned(SimpleNamespace(display_name="primr-vendor_research_123"))

    def test_false_for_foreign_resource(self):
        assert not _is_primr_owned(SimpleNamespace(display_name="other-tenant-thing"))

    def test_false_for_missing_display_name(self):
        assert not _is_primr_owned(SimpleNamespace())

    def test_false_for_none_display_name(self):
        assert not _is_primr_owned(SimpleNamespace(display_name=None))

    def test_false_for_non_string_display_name(self):
        assert not _is_primr_owned(SimpleNamespace(display_name=12345))

    def test_constant_matches_expected(self):
        assert _PRIMR_RESOURCE_PREFIX == "primr-"
        assert _DEFAULT_STALE_AGE_SECONDS == 3600.0


# ---------------------------------------------------------------------------
# _resource_age_seconds
# ---------------------------------------------------------------------------


class TestResourceAgeSeconds:
    def test_uses_create_time_with_timestamp_method(self):
        now = datetime.now(timezone.utc)
        ct = MagicMock()
        ct.timestamp.return_value = now.timestamp() - 100
        age = _resource_age_seconds(SimpleNamespace(create_time=ct))
        assert age is not None
        assert 99 < age < 101

    def test_uses_create_time_iso_string(self):
        ten_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
        iso = ten_minutes_ago.isoformat().replace("+00:00", "Z")
        age = _resource_age_seconds(SimpleNamespace(create_time=iso))
        assert age is not None
        assert 590 < age < 610

    def test_falls_back_to_display_name_timestamp(self):
        ts = int(time.time()) - 200
        age = _resource_age_seconds(
            SimpleNamespace(display_name=f"primr-vendor_research_{ts}")
        )
        assert age is not None
        assert 199 < age < 201

    def test_returns_none_when_no_signal(self):
        assert _resource_age_seconds(SimpleNamespace()) is None

    def test_returns_none_when_display_name_lacks_timestamp(self):
        assert _resource_age_seconds(SimpleNamespace(display_name="primr-x_y_z")) is None

    def test_create_time_exception_falls_through(self):
        ct = MagicMock()
        ct.timestamp.side_effect = RuntimeError("bad")
        age = _resource_age_seconds(
            SimpleNamespace(create_time=ct, display_name="primr-x_1700000000")
        )
        # When create_time blows up, we fall through to the display_name parse.
        assert age is not None


# ---------------------------------------------------------------------------
# cleanup_orphaned_resources
# ---------------------------------------------------------------------------


class _FakeResource:
    def __init__(self, name, display_name, age_seconds=10000):
        self.name = name
        self.display_name = display_name
        self.create_time = MagicMock()
        self.create_time.timestamp.return_value = (
            datetime.now(timezone.utc).timestamp() - age_seconds
        )


def _fake_settings():
    api = SimpleNamespace(gemini_key="fake-key-1234567890")
    return SimpleNamespace(api=api)


def _patched_environ():
    """Return a patcher that scrubs the staleness override env var."""
    import os as _real_os

    backup = _real_os.environ.copy()
    _real_os.environ.pop("PRIMR_CLEANUP_STALE_AGE_SECONDS", None)
    return backup


class TestCleanupOrphanedResources:
    def _setup(self, monkeypatch, caches=None, stores=None):
        monkeypatch.delenv("PRIMR_CLEANUP_STALE_AGE_SECONDS", raising=False)
        # Patch the deferred imports
        client = MagicMock()
        client.caches.list.return_value = caches or []
        client.file_search_stores.list.return_value = stores or []
        # Document listing returns empty by default
        client.file_search_stores.documents.list.return_value = []

        fake_genai = MagicMock()
        fake_genai.Client.return_value = client

        monkeypatch.setattr("primr.config.settings.get_settings", _fake_settings)
        # Patch the deep_research imports used by cleanup_orphaned_resources.
        # Use module-object setattr because attribute-path resolution collides
        # with the same-named `deep_research` function exported at module top.
        import primr.ai.deep_research as dr_mod

        monkeypatch.setattr(dr_mod, "genai", fake_genai)
        monkeypatch.setattr(dr_mod, "_require_genai_dependency", lambda: None)
        return client

    def test_no_resources_returns_zero_counts(self, monkeypatch):
        self._setup(monkeypatch)
        result = cleanup_orphaned_resources()
        assert result == {"caches_deleted": 0, "stores_deleted": 0}

    def test_deletes_old_primr_cache(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            caches=[
                _FakeResource("c/1", "primr-x_1700000000", age_seconds=10000),
            ],
        )
        result = cleanup_orphaned_resources()
        assert result["caches_deleted"] == 1
        client.caches.delete.assert_called_once_with(name="c/1")

    def test_skips_non_primr_cache(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            caches=[
                _FakeResource("c/foreign", "other-tenant-thing", age_seconds=10000),
            ],
        )
        result = cleanup_orphaned_resources()
        assert result["caches_deleted"] == 0
        client.caches.delete.assert_not_called()

    def test_skips_young_primr_cache(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            caches=[
                _FakeResource("c/young", "primr-x_1700000000", age_seconds=10),
            ],
        )
        # Default threshold is 3600s; resource is 10s old -> too young.
        result = cleanup_orphaned_resources()
        assert result["caches_deleted"] == 0
        client.caches.delete.assert_not_called()

    def test_deletes_old_primr_store_with_documents(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            stores=[
                _FakeResource("s/1", "primr-store_1700000000", age_seconds=10000),
            ],
        )
        client.file_search_stores.documents.list.return_value = [
            SimpleNamespace(name="d/1"),
            SimpleNamespace(name="d/2"),
        ]
        result = cleanup_orphaned_resources()
        assert result["stores_deleted"] == 1
        # Should delete each document first, then the store
        assert client.file_search_stores.documents.delete.call_count == 2
        client.file_search_stores.delete.assert_called_once_with(name="s/1")

    def test_skips_non_primr_store(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            stores=[
                _FakeResource("s/foreign", "third-party-store", age_seconds=10000),
            ],
        )
        result = cleanup_orphaned_resources()
        assert result["stores_deleted"] == 0
        client.file_search_stores.delete.assert_not_called()

    def test_env_var_override_for_stale_age(self, monkeypatch):
        # Set the env var to a tighter window — 5s — so a 10s old resource qualifies.
        monkeypatch.setenv("PRIMR_CLEANUP_STALE_AGE_SECONDS", "5")
        self._setup(
            monkeypatch,
            caches=[
                _FakeResource("c/x", "primr-x_1700000000", age_seconds=10),
            ],
        )
        # _setup re-deletes the env var; re-set it after.
        monkeypatch.setenv("PRIMR_CLEANUP_STALE_AGE_SECONDS", "5")
        result = cleanup_orphaned_resources()
        assert result["caches_deleted"] == 1

    def test_invalid_env_var_uses_default(self, monkeypatch):
        self._setup(
            monkeypatch,
            caches=[
                _FakeResource("c/x", "primr-x_1700000000", age_seconds=100),
            ],
        )
        monkeypatch.setenv("PRIMR_CLEANUP_STALE_AGE_SECONDS", "not-a-number")
        result = cleanup_orphaned_resources()
        # Default window is 3600s; 100s-old resource skipped.
        assert result["caches_deleted"] == 0

    def test_explicit_stale_age_param_overrides_env(self, monkeypatch):
        self._setup(
            monkeypatch,
            caches=[
                _FakeResource("c/x", "primr-x_1700000000", age_seconds=200),
            ],
        )
        result = cleanup_orphaned_resources(stale_age_seconds=100.0)
        # 200s-old resource > 100s threshold -> deleted.
        assert result["caches_deleted"] == 1

    def test_explicit_api_key_used(self, monkeypatch):
        self._setup(monkeypatch)
        with patch("primr.ai.deep_research.genai") as fake_genai:
            client = MagicMock()
            client.caches.list.return_value = []
            client.file_search_stores.list.return_value = []
            fake_genai.Client.return_value = client
            cleanup_orphaned_resources(api_key="custom-key")
            fake_genai.Client.assert_called_with(api_key="custom-key")

    def test_list_caches_exception_swallowed(self, monkeypatch):
        client = self._setup(monkeypatch)
        client.caches.list.side_effect = RuntimeError("API down")
        # Should not raise; just logs and continues to store cleanup.
        result = cleanup_orphaned_resources()
        assert result["caches_deleted"] == 0

    def test_list_stores_exception_swallowed(self, monkeypatch):
        client = self._setup(monkeypatch)
        client.file_search_stores.list.side_effect = RuntimeError("API down")
        result = cleanup_orphaned_resources()
        assert result["stores_deleted"] == 0

    def test_delete_document_typeerror_falls_back(self, monkeypatch):
        client = self._setup(
            monkeypatch,
            stores=[
                _FakeResource("s/1", "primr-store_1700000000", age_seconds=10000),
            ],
        )
        client.file_search_stores.documents.list.return_value = [
            SimpleNamespace(name="d/1"),
        ]
        # Force the config-based delete to fail with TypeError -> retries without config.
        client.file_search_stores.documents.delete.side_effect = [
            TypeError("config unsupported"),
            None,
        ]
        result = cleanup_orphaned_resources()
        assert result["stores_deleted"] == 1

    def test_resource_with_unknown_age_treated_as_eligible(self, monkeypatch):
        # No create_time, no parseable display_name timestamp.
        resource = SimpleNamespace(name="c/1", display_name="primr-no-timestamp")
        self._setup(monkeypatch, caches=[resource])
        result = cleanup_orphaned_resources()
        # Age is None -> bypasses the staleness gate -> gets deleted.
        assert result["caches_deleted"] == 1
