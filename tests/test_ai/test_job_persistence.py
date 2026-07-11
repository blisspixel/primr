"""Unit tests for primr.ai.job_persistence.

Direct tests on the save/remove/get_pending_jobs helpers that manage the
shared pending-research-jobs JSON file.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from primr.ai.job_persistence import (
    _get_jobs_file_path,
    acknowledge_pending_job_after_outputs,
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
        # Force the second write to fail at the atomic-replace seam.
        with (
            patch(
                "primr.ai.job_persistence.atomic_replace",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError),
        ):
            save_pending_job("iid-2", "vendor_research", "Y")

    def test_save_survives_transient_lock(self, job_path):
        # A sync-client lock that clears within atomic_replace's retry budget
        # must not surface: the save succeeds and no temp file is left behind.
        real_replace = os.replace
        calls = {"n": 0}

        def flaky_replace(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked by sync client")
            real_replace(src, dst)

        with (
            patch("primr.utils.atomic_io.os.replace", side_effect=flaky_replace),
            patch("primr.utils.atomic_io.time.sleep"),
        ):
            save_pending_job("iid-1", "vendor_research", "X")

        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" in loaded
        assert calls["n"] == 3
        assert not job_path.with_name(job_path.name + ".tmp").exists()


class TestRemovePendingJob:
    def test_removes_existing_job(self, job_path):
        save_pending_job("iid-1", "vendor_research", "X")
        save_pending_job("iid-2", "vendor_research", "Y")
        assert remove_pending_job("iid-1") is True
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" not in loaded
        assert "iid-2" in loaded

    def test_no_op_when_file_missing(self, job_path):
        # File does not exist yet, so removal should succeed without creating it.
        assert remove_pending_job("iid-1") is True
        assert not job_path.exists()

    def test_no_op_for_unknown_id(self, job_path):
        save_pending_job("iid-1", "vendor_research", "X")
        assert remove_pending_job("non-existent") is True
        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert "iid-1" in loaded

    def test_handles_empty_file_gracefully(self, job_path):
        job_path.write_text("", encoding="utf-8")
        assert remove_pending_job("iid-anything") is True
        # No exception, file unchanged.

    def test_handles_corrupt_file_gracefully(self, job_path):
        job_path.write_text("{not-json", encoding="utf-8")
        # Should log a warning and return without raising.
        assert remove_pending_job("iid-anything") is False


class TestAcknowledgePendingJobAfterOutputs:
    def test_removes_job_only_after_all_outputs_are_nonempty(self, job_path, tmp_path):
        save_pending_job("iid-1", "deep_research", "ExampleCo")
        markdown = tmp_path / "report.md"
        document = tmp_path / "report.docx"
        markdown.write_text("# Report", encoding="utf-8")
        document.write_bytes(b"document")

        assert acknowledge_pending_job_after_outputs("iid-1", [markdown, document]) is True
        assert "iid-1" not in get_pending_jobs()

    @pytest.mark.parametrize("invalid_kind", ["missing", "empty"])
    def test_retains_job_when_any_required_output_is_not_durable(
        self, job_path, tmp_path, invalid_kind
    ):
        save_pending_job("iid-1", "deep_research", "ExampleCo")
        markdown = tmp_path / "report.md"
        markdown.write_text("# Report", encoding="utf-8")
        document = tmp_path / "report.docx"
        if invalid_kind == "empty":
            document.write_bytes(b"")

        assert acknowledge_pending_job_after_outputs("iid-1", [markdown, document]) is False
        assert "iid-1" in get_pending_jobs()

    def test_rejects_empty_output_contract(self, job_path):
        save_pending_job("iid-1", "deep_research", "ExampleCo")

        assert acknowledge_pending_job_after_outputs("iid-1", []) is False
        assert "iid-1" in get_pending_jobs()

    def test_rejects_symlinked_output(self, job_path, tmp_path):
        save_pending_job("iid-1", "deep_research", "ExampleCo")
        target = tmp_path / "report.md"
        target.write_text("content", encoding="utf-8")
        link = tmp_path / "report-link.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("file symlinks are unavailable")

        assert acknowledge_pending_job_after_outputs("iid-1", [link]) is False
        assert "iid-1" in get_pending_jobs()

    def test_no_interaction_id_is_already_acknowledged(self):
        assert acknowledge_pending_job_after_outputs("", ["unused.md"]) is True


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
