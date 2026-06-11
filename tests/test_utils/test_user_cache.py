"""Tests for the per-user cache directory (roadmap #12)."""

from pathlib import Path

from primr.utils.user_cache import (
    get_user_cache_dir,
    get_user_cache_subdir,
    migrate_legacy_file,
)


class TestCacheDirResolution:
    def test_env_override_wins(self, tmp_path, monkeypatch):
        override = tmp_path / "custom-cache"
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(override))
        result = get_user_cache_dir()
        assert result == override
        assert result.is_dir()

    def test_default_is_under_user_profile(self, monkeypatch):
        monkeypatch.delenv("PRIMR_CACHE_DIR", raising=False)
        result = get_user_cache_dir()
        assert result.name == "primr"
        assert str(Path.home()) in str(result) or "primr" in str(result)
        assert result.is_dir()

    def test_subdir_created(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        sub = get_user_cache_subdir("vendor-research")
        assert sub.is_dir()
        assert sub.name == "vendor-research"
        assert sub.parent == tmp_path / "cache"


class TestLegacyMigration:
    def test_moves_legacy_file(self, tmp_path):
        legacy = tmp_path / "old" / "file.txt"
        legacy.parent.mkdir()
        legacy.write_text("legacy content", encoding="utf-8")
        new = tmp_path / "new" / "file.txt"

        assert migrate_legacy_file(legacy, new) is True
        assert not legacy.exists()
        assert new.read_text(encoding="utf-8") == "legacy content"

    def test_noop_when_legacy_missing(self, tmp_path):
        assert migrate_legacy_file(tmp_path / "missing.txt", tmp_path / "new.txt") is False

    def test_existing_new_file_wins(self, tmp_path):
        legacy = tmp_path / "old.txt"
        legacy.write_text("legacy", encoding="utf-8")
        new = tmp_path / "new.txt"
        new.write_text("current", encoding="utf-8")

        assert migrate_legacy_file(legacy, new) is False
        assert new.read_text(encoding="utf-8") == "current"
        assert legacy.exists()  # untouched


class TestVendorResearchUsesCache:
    def test_vendor_path_lives_in_user_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        from primr.core.vendor_research import get_vendor_research_path

        path = get_vendor_research_path("azure")
        assert str(tmp_path / "cache") in str(path)
        assert path.name.startswith("vendor-research-azure-")

    def test_legacy_vendor_file_migrates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        from primr.core import vendor_research as vr

        # Plant a legacy file at the old PROJECT_ROOT location shape
        monkeypatch.setattr(vr, "PROJECT_ROOT", str(tmp_path / "repo"))
        from datetime import datetime

        month = datetime.now().strftime("%Y-%m")
        legacy = tmp_path / "repo" / "vendor-research" / f"vendor-research-azure-{month}.txt"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("legacy research", encoding="utf-8")

        path = vr.get_vendor_research_path("azure")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "legacy research"
        assert not legacy.exists()


class TestVendorNewsTTL:
    def test_default_ttl(self, monkeypatch):
        monkeypatch.delenv("PRIMR_VENDOR_NEWS_TTL_DAYS", raising=False)
        from primr.core.vendor_research import (
            DEFAULT_VENDOR_NEWS_TTL_DAYS,
            get_vendor_news_ttl_days,
        )

        assert get_vendor_news_ttl_days() == DEFAULT_VENDOR_NEWS_TTL_DAYS

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PRIMR_VENDOR_NEWS_TTL_DAYS", "2")
        from primr.core.vendor_research import get_vendor_news_ttl_days

        assert get_vendor_news_ttl_days() == 2

    def test_invalid_values_fall_back(self, monkeypatch):
        from primr.core.vendor_research import (
            DEFAULT_VENDOR_NEWS_TTL_DAYS,
            get_vendor_news_ttl_days,
        )

        monkeypatch.setenv("PRIMR_VENDOR_NEWS_TTL_DAYS", "zero")
        assert get_vendor_news_ttl_days() == DEFAULT_VENDOR_NEWS_TTL_DAYS
        monkeypatch.setenv("PRIMR_VENDOR_NEWS_TTL_DAYS", "-3")
        assert get_vendor_news_ttl_days() == DEFAULT_VENDOR_NEWS_TTL_DAYS

    def test_ttl_drives_freshness_check(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        from primr.core import vendor_research as vr

        # No manual file interference
        monkeypatch.setattr(vr, "get_manual_research_path", lambda v: None)

        path = vr.get_vendor_research_path("aws")
        path.write_text("research", encoding="utf-8")

        # Fresh file passes regardless of TTL
        monkeypatch.setenv("PRIMR_VENDOR_NEWS_TTL_DAYS", "1")
        assert vr.is_vendor_research_current("aws") is True

        # Age the file beyond the TTL
        import os
        import time

        old = time.time() - 3 * 86_400  # 3 days old
        os.utime(path, (old, old))
        assert vr.is_vendor_research_current("aws") is False
        monkeypatch.setenv("PRIMR_VENDOR_NEWS_TTL_DAYS", "7")
        assert vr.is_vendor_research_current("aws") is True


class TestShowUsageVendorFreshness:
    def test_no_cached_files_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        from primr.core.cli import _format_vendor_research_freshness

        out = _format_vendor_research_freshness()
        assert "Vendor Research Freshness" in out
        assert "no cached vendor research" in out

    def test_lists_files_with_age_and_status(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRIMR_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("PRIMR_VENDOR_NEWS_TTL_DAYS", "7")
        from primr.core import vendor_research as vr
        from primr.core.cli import _format_vendor_research_freshness

        fresh = vr.get_vendor_research_path("azure")
        fresh.write_text("fresh", encoding="utf-8")

        stale = vr.get_vendor_research_path("aws")
        stale.write_text("stale", encoding="utf-8")
        import os
        import time

        old = time.time() - 10 * 86_400
        os.utime(stale, (old, old))

        out = _format_vendor_research_freshness()
        assert "vendor-research-azure-" in out
        assert "fresh" in out
        assert "stale (> 7d TTL)" in out
        assert "PRIMR_VENDOR_NEWS_TTL_DAYS" in out
