"""Unit tests for primr.ai.job_persistence.

Direct tests on the save/remove/get_pending_jobs helpers that manage the
shared pending-research-jobs JSON file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from primr.ai.job_persistence import (
    _get_jobs_file_path,
    acknowledge_pending_job_after_outputs,
    get_pending_jobs,
    get_pending_jobs_with_status,
    remove_pending_job,
    remove_pending_jobs,
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

    def test_recovers_from_invalid_utf8(self, job_path):
        job_path.write_bytes(b"\xff\xfe")

        save_pending_job("iid-1", "vendor_research", "X")

        loaded = json.loads(job_path.read_text(encoding="utf-8"))
        assert set(loaded) == {"iid-1"}

    def test_primary_write_failure_uses_durable_recovery_receipt(self, job_path):
        save_pending_job("iid-1", "vendor_research", "X")
        with patch(
            "primr.ai.job_persistence.atomic_replace",
            side_effect=OSError("primary registry locked"),
        ):
            save_pending_job("iid-2", "vendor_research", "Y")

        receipts = job_path.with_name(job_path.name + ".recovery.jsonl")
        assert receipts.is_file()
        read_success, jobs = get_pending_jobs_with_status()
        assert read_success is True
        assert set(jobs) == {"iid-1", "iid-2"}
        assert jobs["iid-2"]["description"] == (
            "Emergency recovery receipt for accepted vendor_research"
        )

    def test_emergency_receipt_keeps_only_recovery_metadata(self, job_path):
        with patch(
            "primr.ai.job_persistence.atomic_replace",
            side_effect=OSError("primary registry locked"),
        ):
            save_pending_job(
                "iid-2",
                "deep_research",
                "sensitive prompt text",
                metadata={
                    "file_search_store": "stores/live",
                    "company_name": "ExampleCo",
                    "secret": "must-not-persist",
                },
            )

        job = get_pending_jobs()["iid-2"]
        assert job["metadata"] == {
            "company_name": "ExampleCo",
            "file_search_store": "stores/live",
        }
        assert "sensitive prompt text" not in json.dumps(job)
        assert "must-not-persist" not in json.dumps(job)

    def test_save_raises_when_primary_and_recovery_receipt_fail(self, job_path):
        with (
            patch(
                "primr.ai.job_persistence.atomic_replace",
                side_effect=OSError("primary registry locked"),
            ),
            patch(
                "primr.ai.job_persistence._append_recovery_receipt",
                side_effect=OSError("recovery volume unavailable"),
            ),
            pytest.raises(OSError, match="both failed"),
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


class TestRemovePendingJobs:
    def test_removes_only_selected_snapshot(self, job_path):
        save_pending_job("shown-1", "vendor_research", "A")
        save_pending_job("shown-2", "vendor_research", "B")
        save_pending_job("added-later", "vendor_research", "C")

        assert remove_pending_jobs(("shown-1", "shown-2")) == (True, 2)
        assert set(get_pending_jobs()) == {"added-later"}

    def test_missing_file_is_successful_no_op(self, job_path):
        assert remove_pending_jobs(("unknown",)) == (True, 0)
        assert not job_path.exists()

    def test_removes_emergency_only_record(self, job_path):
        with patch(
            "primr.ai.job_persistence.atomic_replace",
            side_effect=OSError("primary registry locked"),
        ):
            save_pending_job("accepted-1", "deep_research", "ExampleCo")

        receipts = job_path.with_name(job_path.name + ".recovery.jsonl")
        assert "accepted-1" in get_pending_jobs()
        assert remove_pending_jobs(("accepted-1",)) == (True, 1)
        assert get_pending_jobs() == {}
        assert not receipts.exists()

    def test_corrupt_file_fails_closed(self, job_path):
        job_path.write_text("{not-json", encoding="utf-8")

        assert remove_pending_jobs(("iid-1",)) == (False, 0)
        assert job_path.read_text(encoding="utf-8") == "{not-json"

    def test_invalid_utf8_fails_closed(self, job_path):
        original = b"\xff\xfe"
        job_path.write_bytes(original)

        assert remove_pending_jobs(("iid-1",)) == (False, 0)
        assert job_path.read_bytes() == original

    def test_atomic_replace_failure_preserves_original(self, job_path):
        save_pending_job("iid-1", "vendor_research", "A")
        original = job_path.read_text(encoding="utf-8")

        with patch(
            "primr.ai.job_persistence.atomic_replace",
            side_effect=OSError("disk full"),
        ):
            assert remove_pending_jobs(("iid-1",)) == (False, 0)

        assert job_path.read_text(encoding="utf-8") == original
        assert not job_path.with_name(job_path.name + ".tmp").exists()

    def test_lock_timeout_does_not_delete_foreign_temp_state(self, job_path):
        save_pending_job("iid-1", "vendor_research", "A")
        temp_path = job_path.with_name(job_path.name + ".tmp")
        temp_path.write_bytes(b"foreign-writer")

        with patch(
            "primr.ai.job_persistence._pending_jobs_mutation_lock",
            side_effect=TimeoutError("registry busy"),
        ):
            assert remove_pending_jobs(("iid-1",)) == (False, 0)

        assert temp_path.read_bytes() == b"foreign-writer"
        assert "iid-1" in get_pending_jobs()

    def test_parallel_process_mutations_preserve_new_records(self, tmp_path):
        jobs_file = tmp_path / "pending.json"
        ready_file = tmp_path / "remover-ready"
        writer_file = tmp_path / "writer-started"
        continue_file = tmp_path / "continue"
        jobs_file.write_text(
            json.dumps({"base": {"type": "research", "status": "pending"}}),
            encoding="utf-8",
        )

        remover_script = """
import sys
import time
from pathlib import Path
from primr.ai import job_persistence as persistence

jobs_path, ready_path, continue_path = sys.argv[1:]
persistence._get_jobs_file_path = lambda: jobs_path
real_loads = persistence.json.loads

def pause_after_read(content):
    result = real_loads(content)
    Path(ready_path).write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 10
    while not Path(continue_path).exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("parent did not release remover")
        time.sleep(0.01)
    return result

persistence.json.loads = pause_after_read
success, removed = persistence.remove_pending_jobs(("base",))
raise SystemExit(0 if success and removed == 1 else 2)
"""
        writer_script = """
import sys
from pathlib import Path
from primr.ai import job_persistence as persistence

jobs_path, started_path = sys.argv[1:]
persistence._get_jobs_file_path = lambda: jobs_path
Path(started_path).write_text("started", encoding="utf-8")
persistence.save_pending_job("added-later", "research", "new record")
"""

        remover = subprocess.Popen(
            [
                sys.executable,
                "-c",
                remover_script,
                str(jobs_file),
                str(ready_file),
                str(continue_file),
            ],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        writer: subprocess.Popen[str] | None = None
        try:
            self._wait_for_file(ready_file, remover)
            writer = subprocess.Popen(
                [sys.executable, "-c", writer_script, str(jobs_file), str(writer_file)],
                cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._wait_for_file(writer_file, writer)
            time.sleep(0.2)
            assert writer.poll() is None, "writer bypassed the interprocess registry lock"

            continue_file.write_text("continue", encoding="utf-8")
            remover_stdout, remover_stderr = remover.communicate(timeout=10)
            writer_stdout, writer_stderr = writer.communicate(timeout=10)
            assert remover.returncode == 0, remover_stdout + remover_stderr
            assert writer.returncode == 0, writer_stdout + writer_stderr
        finally:
            continue_file.touch()
            for process in (remover, writer):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

        assert set(json.loads(jobs_file.read_text(encoding="utf-8"))) == {"added-later"}

    @staticmethod
    def _wait_for_file(path: Path, process: subprocess.Popen[str]) -> None:
        deadline = time.monotonic() + 10
        while not path.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                pytest.fail(f"subprocess exited before {path.name}: {stdout}{stderr}")
            if time.monotonic() >= deadline:
                pytest.fail(f"timed out waiting for {path.name}")
            time.sleep(0.01)


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

    def test_status_distinguishes_empty_from_corrupt_state(self, job_path):
        assert get_pending_jobs_with_status() == (True, {})

        job_path.write_text("{not-json", encoding="utf-8")
        assert get_pending_jobs_with_status() == (False, {})

    def test_status_reports_invalid_utf8_as_corrupt(self, job_path):
        job_path.write_bytes(b"\xff\xfe")

        assert get_pending_jobs_with_status() == (False, {})

    def test_status_rejects_non_object_job_entry(self, job_path):
        job_path.write_text('{"j1": null}', encoding="utf-8")

        assert get_pending_jobs_with_status() == (False, {})
        assert get_pending_jobs() == {}

    def test_status_fails_closed_for_malformed_recovery_receipt(self, job_path):
        receipts = job_path.with_name(job_path.name + ".recovery.jsonl")
        receipts.write_text("{not-json\n", encoding="utf-8")

        assert get_pending_jobs_with_status() == (False, {})
        assert get_pending_jobs() == {}


class TestConcurrency:
    """Confirm the file lock prevents concurrent-write corruption."""

    def test_lock_is_module_level_singleton(self):
        from primr.ai import job_persistence

        # The lock should be a module-level attribute so concurrent callers serialize on it.
        assert hasattr(job_persistence, "_jobs_file_lock")
        assert job_persistence._jobs_file_lock is job_persistence._jobs_file_lock
