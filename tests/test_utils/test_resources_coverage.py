"""Coverage tests for primr.utils.resources.

Targets paths the existing test_resources.py leaves out: managed_http_client,
CacheMetrics expirations, BoundedCache.log_metrics + validation errors,
ResourceManager process/handle (un)registration + error branches +
resource_counts, the get_resource_manager singleton, and the SIGINT
install/uninstall helpers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.utils import resources as res
from primr.utils.resources import (
    BoundedCache,
    CacheMetrics,
    ResourceManager,
    get_resource_manager,
    install_sigint_handler,
    managed_http_client,
    managed_temp_dir,
    uninstall_sigint_handler,
)


class TestManagedHttpClient:
    def test_yields_and_closes_client(self):
        fake_client = MagicMock()
        with patch("httpx.Client", return_value=fake_client) as ctor:
            with managed_http_client(timeout=5.0, max_connections=4, http2=False) as c:
                assert c is fake_client
            ctor.assert_called_once()
        fake_client.close.assert_called_once()

    def test_closes_on_exception(self):
        fake_client = MagicMock()
        with (
            patch("httpx.Client", return_value=fake_client),
            pytest.raises(RuntimeError),
            managed_http_client(),
        ):
            raise RuntimeError("boom")
        fake_client.close.assert_called_once()


class TestManagedTempDir:
    def test_cleanup_failure_logs_warning(self, caplog):
        import logging

        with (
            caplog.at_level(logging.WARNING),
            patch("shutil.rmtree", side_effect=OSError("locked")),
            managed_temp_dir() as d,
        ):
            assert d.exists()
        assert any("Failed to delete temp dir" in r.message for r in caplog.records)


class TestCacheMetricsAndCache:
    def test_metrics_to_dict_includes_expirations(self):
        m = CacheMetrics(hits=3, misses=1, evictions=2, expirations=5)
        d = m.to_dict()
        assert d["expirations"] == 5
        assert d["hit_rate"] == round(3 / 4, 4)

    def test_invalid_max_size_raises(self):
        with pytest.raises(ValueError, match="max_size"):
            BoundedCache(max_size=0)

    def test_invalid_ttl_raises(self):
        with pytest.raises(ValueError, match="ttl_seconds"):
            BoundedCache(max_size=5, ttl_seconds=-1)

    def test_get_metrics_includes_size_and_name(self):
        cache = BoundedCache(max_size=10, name="mycache")
        cache.set("a", 1)
        metrics = cache.get_metrics()
        assert metrics["size"] == 1
        assert metrics["max_size"] == 10
        assert metrics["name"] == "mycache"

    def test_log_metrics_runs(self, caplog):
        import logging

        cache = BoundedCache(max_size=10, name="logged")
        cache.set("a", 1)
        cache.get("a")
        with caplog.at_level(logging.INFO):
            cache.log_metrics()
        assert any("metrics" in r.message for r in caplog.records)

    def test_delete_missing_returns_false(self):
        cache = BoundedCache(max_size=5)
        assert cache.delete("nope") is False

    def test_evict_lru_on_empty_is_safe(self):
        cache = BoundedCache(max_size=5)
        cache._evict_lru()  # no entries, should not raise


class TestResourceManager:
    def test_register_and_unregister_process(self):
        mgr = ResourceManager()
        mgr.register_process(99999)
        assert mgr.resource_counts["processes"] == 1
        mgr.unregister_process(99999)
        assert mgr.resource_counts["processes"] == 0

    def test_register_and_unregister_handle(self):
        mgr = ResourceManager()
        handle = MagicMock()
        mgr.register_handle(handle)
        assert mgr.resource_counts["handles"] == 1
        mgr.unregister_handle(handle)
        assert mgr.resource_counts["handles"] == 0

    def test_cleanup_only_runs_once(self, tmp_path):
        mgr = ResourceManager()
        f = tmp_path / "f.txt"
        f.write_text("x")
        mgr.register_temp_file(f)
        first = mgr.cleanup()
        assert first["temp_files"] == 1
        second = mgr.cleanup()
        assert second == {"temp_files": 0, "handles": 0, "processes": 0}

    def test_cleanup_handles_close_error(self, caplog):
        import logging

        mgr = ResourceManager()
        bad = MagicMock()
        bad.close.side_effect = RuntimeError("cannot close")
        mgr.register_handle(bad)
        with caplog.at_level(logging.WARNING):
            results = mgr.cleanup()
        # Close was attempted; error logged, count not incremented.
        assert results["handles"] == 0
        assert any("Failed to close handle" in r.message for r in caplog.records)

    def test_cleanup_handles_missing_temp_file(self, tmp_path):
        mgr = ResourceManager()
        missing = tmp_path / "ghost.txt"
        mgr.register_temp_file(missing)
        results = mgr.cleanup()
        # File never existed, so it isn't counted.
        assert results["temp_files"] == 0

    def test_cleanup_terminates_process(self):
        mgr = ResourceManager()
        mgr.register_process(4242)
        with patch("os.kill") as mock_kill:
            results = mgr.cleanup()
        mock_kill.assert_called_once()
        assert results["processes"] == 1

    def test_cleanup_process_already_dead(self):
        mgr = ResourceManager()
        mgr.register_process(4242)
        with patch("os.kill", side_effect=ProcessLookupError()):
            results = mgr.cleanup()
        assert results["processes"] == 0

    def test_context_manager_cleans_up(self, tmp_path):
        f = tmp_path / "ctx.txt"
        f.write_text("data")
        with ResourceManager() as mgr:
            mgr.register_temp_file(f)
        assert not f.exists()


class TestGlobalResourceManager:
    def test_returns_singleton(self, monkeypatch):
        monkeypatch.setattr(res, "_resource_manager", None)
        with patch("atexit.register"):
            first = get_resource_manager()
            second = get_resource_manager()
        assert first is second
        assert isinstance(first, ResourceManager)


class TestSigintHandlers:
    def test_install_and_uninstall(self):
        # Save state, ensure clean start.
        already = res._sigint_installed
        if already:
            uninstall_sigint_handler()
        try:
            install_sigint_handler()
            assert res._sigint_installed is True
            # Idempotent second install.
            install_sigint_handler()
            assert res._sigint_installed is True
        finally:
            uninstall_sigint_handler()
            assert res._sigint_installed is False

    def test_uninstall_when_not_installed_is_noop(self):
        if res._sigint_installed:
            uninstall_sigint_handler()
        # Already uninstalled -> early return, no error.
        uninstall_sigint_handler()
        assert res._sigint_installed is False

    def test_handler_triggers_cleanup(self, monkeypatch):
        if res._sigint_installed:
            uninstall_sigint_handler()
        captured = {}

        def fake_signal(signum, handler):
            captured["handler"] = handler
            return None  # no original handler

        monkeypatch.setattr("signal.signal", fake_signal)
        install_sigint_handler()
        try:
            handler = captured["handler"]
            with patch.object(res, "get_resource_manager") as mock_get:
                mock_get.return_value = MagicMock()
                with pytest.raises(SystemExit):
                    handler(2, None)
                mock_get.return_value.cleanup.assert_called_once()
        finally:
            res._sigint_installed = False
            res._original_sigint_handler = None
