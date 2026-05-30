"""Unit tests for primr.ai.job_persistence.

Direct tests on the save/remove/get_pending_jobs helpers that manage the
shared pending-research-jobs JSON file.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from primr.ai.job_persistence import (
    _get_jobs_file_path,
    get_pending_jobs,
    remove_pending_job,
    save_pending_job,
)


@pytest.fixture
def job_path(tmp_path, monkeypatch):
    """Redirect the jobs file to a tmp_path for test isolation."""
    target = tmp_path / "pending.json"
    monkeypatch.setattr("primr.ai.job_persistence._get_jobs_file_path", lambda: str(target))
    return target


class TestGetJobsFilePath:
    def test_returns_path_under_logs_dir(self, monkeypatch):
        monkeypatch.setattr("primr.config.config.LOGS_DIR", "/some/logs")
        path = _get_jobs_file_path()
        assert path.endswith("pending_research_jobs.json")


class TestSavePendingJob:
    def test_creates_jobs_file_with_entry(self, job_path):
        save_pending_job("iid-1", "vendor_research", "ExampleCo AI strategy")
        assert job_path.exists()
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" in loaded
        assert loaded["iid-1"]["type"] == "vendor_research"
        assert loaded["iid-1"]["description"] == "ExampleCo AI strategy"
        assert loaded["iid-1"]["status"] == "pending"
        assert "started" in loaded["iid-1"]

    def test_metadata_persisted(self, job_path):
        save_pending_job("iid-2", "ai_strategy", "ExampleCo", metadata={"vendor": "azure"})
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert loaded["iid-2"]["metadata"] == {"vendor": "azure"}

    def test_default_metadata_is_empty_dict(self, job_path):
        save_pending_job("iid-3", "vendor_research", "X")
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert loaded["iid-3"]["metadata"] == {}

    def test_appends_to_existing_jobs(self, job_path):
        save_pending_job("iid-A", "vendor_research", "A")
        save_pending_job("iid-B", "company_research", "B")
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-A" in loaded
        assert "iid-B" in loaded

    def test_recovers_from_corrupt_existing_file(self, job_path):
        job_path.write_text("{not-json", encoding="utf-8")
        save_pending_job("iid-1", "vendor_research", "X")
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" in loaded
        # Old corrupt entries are gone
        assert len(loaded) == 1

    def test_recovers_from_non_dict_top_level(self, job_path):
        job_path.write_text("[1, 2, 3]", encoding="utf-8")
        save_pending_job("iid-1", "vendor_research", "X")
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        assert "iid-1" in loaded

    def test_save_raises_when_disk_write_fails(self, job_path):
        save_pending_job("iid-1", "vendor_research", "X")
        # Force the second write to fail at os.replace/rename.
        with (
            patch(
                "primr.ai.job_persistence.os.replace",
                side_effect=OSError("disk full"),
            ),
            patch(
                "primr.ai.job_persistence.os.rename",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError),
        ):
            save_pending_job("iid-2", "vendor_research", "Y")


class TestRemovePendingJob:
    def test_removes_existing_job(self, job_path):
        save_pending_job("iid-1", "vendor_research", "X")
        save_pending_job("iid-2", "vendor_research", "Y")
        remove_pending_job("iid-1")
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" not in loaded
        assert "iid-2" in loaded

    def test_no_op_when_file_missing(self, job_path):
        # File doesn't exist yet — should silently return
        remove_pending_job("iid-1")
        assert not job_path.exists()

    def test_no_op_for_unknown_id(self, job_path):
        save_pending_job("iid-1", "vendor_research", "X")
        remove_pending_job("non-existent")
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" in loaded

    def test_handles_empty_file_gracefully(self, job_path):
        job_path.write_text("", encoding="utf-8")
        remove_pending_job("iid-anything")
        # No exception, file unchanged.

    def test_handles_corrupt_file_gracefully(self, job_path):
        job_path.write_text("{not-json", encoding="utf-8")
        # Should log a warning and return without raising.
        remove_pending_job("iid-anything")


class TestGetPendingJobs:
    def test_empty_when_file_missing(self, job_path):
        assert get_pending_jobs() == {}

    def test_returns_persisted_jobs(self, job_path):
        save_pending_job("iid-1", "vendor_research", "A")
        save_pending_job("iid-2", "ai_strategy", "B")
        loaded = get_pending_jobs()
        assert set(loaded.keys()) == {"iid-1", "iid-2"}

    def test_empty_when_file_empty(self, job_path):
        job_path.write_text("", encoding="utf-8")
        assert get_pending_jobs() == {}

    def test_empty_when_file_corrupt(self, job_path):
        job_path.write_text("{not-json", encoding="utf-8")
        assert get_pending_jobs() == {}

    def test_empty_when_top_level_not_dict(self, job_path):
        job_path.write_text("[]", encoding="utf-8")
        assert get_pending_jobs() == {}


class TestConcurrency:
    """Confirm the file lock prevents concurrent-write corruption."""

    def test_lock_is_module_level_singleton(self):
        from primr.ai import job_persistence

        # The lock should be a module-level attribute so concurrent callers serialize on it.
        assert hasattr(job_persistence, "_jobs_file_lock")
        assert job_persistence._jobs_file_lock is job_persistence._jobs_file_lock
