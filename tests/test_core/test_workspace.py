"""
Unit tests for the workspace module.

Tests working folder creation, consolidation, and file validation.
"""

import json
import os
import socket
import sys
import tempfile
from datetime import datetime as real_datetime
from multiprocessing import get_context
from pathlib import Path

import pytest

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _allocate_workspace_process(base_dir: str, result_queue) -> None:
    from primr.core.workspace import create_working_folder

    result_queue.put(create_working_folder("Sample Company", None, base_dir=base_dir))


def _hold_resume_lease_process(folder: str, ready, release) -> None:
    from primr.core.workspace import acquire_resume_lease, release_resume_lease

    acquire_resume_lease(folder)
    ready.set()
    release.wait(timeout=15)
    release_resume_lease(folder)


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig dataclass."""

    def test_folder_name_from_company_name(self):
        """Folder name derived from company name with spaces replaced."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(base_dir=Path("/tmp"), company_name="Acme Corp", website=None)

        assert config.folder_name == "Acme_Corp"

    def test_folder_name_normalizes_trailing_period_for_windows(self):
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(base_dir=Path("/tmp"), company_name="Acme, Inc.")

        assert config.folder_name == "Acme,_Inc"

    def test_folder_name_from_website(self):
        """Folder name derived from website when no company name."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(
            base_dir=Path("/tmp"), company_name="", website="https://www.example.com"
        )

        assert config.folder_name == "example_com"

    @pytest.mark.parametrize(
        ("website", "expected"),
        [
            ("https://www.example.com:8443", "example_com"),
            ("https://notwww.example.com", "notwww_example_com"),
        ],
    )
    def test_folder_name_uses_hostname_without_corrupting_domain(self, website, expected):
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(base_dir=Path("/tmp"), company_name="", website=website)

        assert config.folder_name == expected

    def test_folder_name_default(self):
        """Default folder name when neither company nor website provided."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(base_dir=Path("/tmp"), company_name="", website=None)

        assert config.folder_name == "Unknown_Company"

    def test_folder_path_combines_base_and_name(self):
        """Folder path combines base_dir and folder_name."""
        from primr.core.workspace import WorkspaceConfig

        config = WorkspaceConfig(
            base_dir=Path("/tmp/working"), company_name="Acme Corp", website=None
        )

        assert config.folder_path == Path("/tmp/working/Acme_Corp")


class TestCreateWorkingFolder:
    """Tests for create_working_folder function."""

    def test_creates_folder_with_company_name(self):
        """Creates folder using company name."""
        from primr.core.workspace import create_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override WORKING_DIR
            import primr.core.workspace as ws

            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                folder = create_working_folder("Test Company", None)
                assert os.path.exists(folder)
                assert "Test_Company" in folder
            finally:
                ws.WORKING_DIR = original_dir

    def test_creates_folder_from_website_when_no_name(self):
        """Creates folder from website domain when no company name."""
        from primr.core.workspace import create_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws

            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                folder = create_working_folder(None, "https://www.example.com")
                assert os.path.exists(folder)
                assert "example_com" in folder
            finally:
                ws.WORKING_DIR = original_dir

    def test_creates_folder_from_website_without_port(self):
        from primr.core.workspace import create_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws

            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir
            try:
                folder = create_working_folder(None, "https://www.example.com:8443")
                assert Path(folder).parent.parent == Path(tmpdir)
                assert Path(folder).parent.name == "example_com"
            finally:
                ws.WORKING_DIR = original_dir

    def test_same_timestamp_allocations_are_distinct(self, tmp_path, monkeypatch):
        from primr.core import workspace

        class FixedDateTime:
            @classmethod
            def now(cls):
                return real_datetime(2026, 7, 18, 12, 34)

        monkeypatch.setattr(workspace, "datetime", FixedDateTime)

        first = workspace.create_working_folder("Sample Company", None, base_dir=tmp_path)
        second = workspace.create_working_folder("Sample Company", None, base_dir=tmp_path)

        assert first != second
        assert Path(first).name == "2026-07-18_1234"
        assert Path(second).name == "2026-07-18_1234_001"

    def test_independent_processes_allocate_distinct_folders(self, tmp_path):
        context = get_context("spawn")
        result_queue = context.Queue()
        processes = [
            context.Process(
                target=_allocate_workspace_process,
                args=(str(tmp_path), result_queue),
            )
            for _ in range(2)
        ]

        for process in processes:
            process.start()
        results = [result_queue.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=15)

        assert all(process.exitcode == 0 for process in processes)
        assert len(set(results)) == 2

    def test_without_run_id_preserves_company_folder_behavior(self, tmp_path):
        from primr.core.workspace import create_working_folder

        first = create_working_folder("Sample Company", None, use_run_id=False, base_dir=tmp_path)
        second = create_working_folder("Sample Company", None, use_run_id=False, base_dir=tmp_path)

        assert first == second == str(tmp_path / "Sample_Company")


class TestResumeLease:
    def test_windows_access_denied_is_treated_as_unverifiably_live(self):
        from primr.core.workspace import _windows_process_is_running

        assert _windows_process_is_running(
            42,
            open_process=lambda *_args: 0,
            get_exit_code=lambda *_args: False,
            close_handle=lambda _handle: None,
            get_last_error=lambda: 5,
        )

    def test_windows_invalid_pid_is_not_running(self):
        from primr.core.workspace import _windows_process_is_running

        assert not _windows_process_is_running(
            42,
            open_process=lambda *_args: 0,
            get_exit_code=lambda *_args: False,
            close_handle=lambda _handle: None,
            get_last_error=lambda: 87,
        )

    def test_active_owner_is_refused_and_release_allows_reclaim(self, tmp_path):
        from primr.core.workspace import (
            ResumeLeaseError,
            acquire_resume_lease,
            release_resume_lease,
        )

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        acquire_resume_lease(run_folder)

        with pytest.raises(ResumeLeaseError, match="already being resumed"):
            acquire_resume_lease(run_folder)

        release_resume_lease(run_folder)
        acquire_resume_lease(run_folder)
        release_resume_lease(run_folder)

    def test_terminal_event_releases_current_process_lease(self, tmp_path):
        from primr.core.run_state_io import _append_run_event, _update_run_state
        from primr.core.workspace import acquire_resume_lease, release_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        acquire_resume_lease(run_folder)

        _update_run_state(str(run_folder), status="failed")
        _append_run_event(str(run_folder), "error", "failed", "bounded failure")
        acquire_resume_lease(run_folder)
        release_resume_lease(run_folder)

    def test_phase_completion_does_not_release_active_run(self, tmp_path):
        from primr.core.run_state_io import _append_run_event, _update_run_state
        from primr.core.workspace import (
            ResumeLeaseError,
            acquire_resume_lease,
            release_resume_lease,
        )

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        acquire_resume_lease(run_folder)
        _update_run_state(str(run_folder), status="running")

        _append_run_event(str(run_folder), "recon", "completed", "Recon completed")

        with pytest.raises(ResumeLeaseError, match="already being resumed"):
            acquire_resume_lease(run_folder)
        release_resume_lease(run_folder)

    def test_independent_process_owner_is_refused(self, tmp_path):
        from primr.core.workspace import ResumeLeaseError, acquire_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        context = get_context("spawn")
        ready = context.Event()
        release = context.Event()
        process = context.Process(
            target=_hold_resume_lease_process,
            args=(str(run_folder), ready, release),
        )
        process.start()
        assert ready.wait(timeout=15)
        try:
            with pytest.raises(ResumeLeaseError, match="already being resumed"):
                acquire_resume_lease(run_folder)
        finally:
            release.set()
            process.join(timeout=15)
        assert process.exitcode == 0

    def test_dead_local_owner_is_reclaimed(self, tmp_path):
        from primr.core.workspace import acquire_resume_lease, release_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        lease_path = run_folder / ".primr-resume-lease"
        lease_path.write_text(
            json.dumps(
                {
                    "hostname": socket.gethostname(),
                    "pid": 2_147_483_647,
                    "token": "dead-owner",
                }
            ),
            encoding="utf-8",
        )

        acquire_resume_lease(run_folder)
        release_resume_lease(run_folder)

    @pytest.mark.parametrize("pid", [None, True, 0, -1, "", "abc", "1.5", "999999999999999999999"])
    def test_malformed_same_host_owner_is_not_reclaimed(self, tmp_path, pid):
        from primr.core.workspace import ResumeLeaseError, acquire_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        lease_path = run_folder / ".primr-resume-lease"
        lease_path.write_text(
            json.dumps(
                {
                    "hostname": socket.gethostname(),
                    "pid": pid,
                    "token": "unverified-owner",
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(ResumeLeaseError, match="Invalid resume ownership"):
            acquire_resume_lease(run_folder)
        assert lease_path.exists()

    def test_stale_owner_unlink_failure_is_normalized(self, tmp_path, monkeypatch):
        from primr.core.workspace import ResumeLeaseError, acquire_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        lease_path = run_folder / ".primr-resume-lease"
        lease_path.write_text(
            json.dumps(
                {
                    "hostname": socket.gethostname(),
                    "pid": 2_147_483_647,
                    "token": "dead-owner",
                }
            ),
            encoding="utf-8",
        )
        original_unlink = Path.unlink

        def deny_stale_unlink(path, *args, **kwargs):
            if path == lease_path:
                raise PermissionError("sharing violation")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deny_stale_unlink)
        with pytest.raises(ResumeLeaseError, match="Could not reclaim stale"):
            acquire_resume_lease(run_folder)

    def test_temporary_lease_cleanup_failure_does_not_mask_acquire(self, tmp_path, monkeypatch):
        from primr.core.workspace import acquire_resume_lease, release_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        original_unlink = Path.unlink

        def deny_temporary_unlink(path, *args, **kwargs):
            if path.name.startswith("..primr-resume-lease") and path.name.endswith(".tmp"):
                raise PermissionError("sharing violation")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", deny_temporary_unlink)
        acquire_resume_lease(run_folder)
        release_resume_lease(run_folder)

    def test_cleanup_failure_is_nonfatal_and_retryable(self, tmp_path, monkeypatch):
        from primr.core.workspace import acquire_resume_lease, release_resume_lease

        run_folder = tmp_path / "run"
        run_folder.mkdir()
        lease_path = run_folder / ".primr-resume-lease"
        acquire_resume_lease(run_folder)
        original_unlink = Path.unlink

        def deny_lease_unlink(path, *args, **kwargs):
            if path == lease_path:
                raise PermissionError("sharing violation")
            return original_unlink(path, *args, **kwargs)

        with monkeypatch.context() as patch_context:
            patch_context.setattr(Path, "unlink", deny_lease_unlink)
            release_resume_lease(run_folder)

        assert lease_path.exists()
        acquire_resume_lease(run_folder)
        release_resume_lease(run_folder)
        assert not lease_path.exists()

    def test_company_lease_serializes_final_artifact_publication(self, tmp_path):
        from primr.core.workspace import (
            ResumeLeaseError,
            acquire_company_run_lease,
            release_company_run_lease,
        )

        first_run = tmp_path / "Sample_Company" / "2026-07-18_1200"
        second_run = tmp_path / "Sample_Company" / "2026-07-18_1200_001"
        first_run.mkdir(parents=True)
        second_run.mkdir()
        acquire_company_run_lease(first_run)

        with pytest.raises(ResumeLeaseError, match="active research process"):
            acquire_company_run_lease(second_run)
        release_company_run_lease(first_run)

    def test_corrupt_company_lease_preserves_verification_error(self, tmp_path):
        from primr.core.workspace import (
            ResumeLeaseError,
            acquire_company_run_lease_for_target,
        )

        company_root = tmp_path / "Sample_Company"
        company_root.mkdir()
        (company_root / ".primr-resume-lease").write_text("not-json", encoding="utf-8")

        with pytest.raises(ResumeLeaseError, match="Cannot verify resume ownership"):
            acquire_company_run_lease_for_target("Sample Company", None, base_dir=tmp_path)

    def test_foreign_host_owner_is_not_reported_as_verified_active(self, tmp_path):
        from primr.core.workspace import (
            ActiveRunLeaseError,
            ResumeLeaseError,
            acquire_company_run_lease_for_target,
        )

        company_root = tmp_path / "Sample_Company"
        company_root.mkdir()
        (company_root / ".primr-resume-lease").write_text(
            json.dumps({"hostname": "different-host", "pid": 123, "token": "foreign"}),
            encoding="utf-8",
        )

        with pytest.raises(ResumeLeaseError) as exc_info:
            acquire_company_run_lease_for_target("Sample Company", None, base_dir=tmp_path)
        assert not isinstance(exc_info.value, ActiveRunLeaseError)
        assert "unverified host" in str(exc_info.value)


class TestWorkingFolderContextManager:
    """Tests for working_folder context manager."""

    def test_creates_folder_on_entry(self):
        """Context manager creates folder on entry."""
        from primr.core.workspace import working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws

            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                with working_folder("Test", None) as folder:
                    assert folder.exists()
                    assert folder.is_dir()
            finally:
                ws.WORKING_DIR = original_dir

    def test_cleanup_on_exit_removes_folder(self):
        """Context manager removes folder when cleanup_on_exit=True."""
        from primr.core.workspace import working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            import primr.core.workspace as ws

            original_dir = ws.WORKING_DIR
            ws.WORKING_DIR = tmpdir

            try:
                with working_folder("Test", None, cleanup_on_exit=True) as folder:
                    folder_path = folder
                    assert folder.exists()

                # After context, folder should be removed
                assert not folder_path.exists()
            finally:
                ws.WORKING_DIR = original_dir


class TestSaveSectionOutput:
    """Tests for save_section_output function."""

    def test_saves_content_to_file(self):
        """Saves content to section file."""
        from primr.core.workspace import save_section_output

        with tempfile.TemporaryDirectory() as tmpdir:
            result = save_section_output(tmpdir, "industry", "Technology")

            assert result.exists()
            assert result.name == "industry.txt"
            assert result.read_text() == "Technology"

    def test_creates_parent_directories(self):
        """Creates parent directories if needed."""
        from primr.core.workspace import save_section_output

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "nested" / "folder"
            result = save_section_output(nested_path, "test", "content")

            assert result.exists()


class TestConsolidateWorkingFolder:
    """Tests for consolidate_working_folder function."""

    def test_consolidates_txt_files(self):
        """Consolidates all .txt files into single document."""
        from primr.core.workspace import consolidate_working_folder

        with tempfile.TemporaryDirectory() as tmpdir:
            folder = Path(tmpdir) / "Test_Company"
            folder.mkdir()

            # Create some section files
            (folder / "industry.txt").write_text("Technology sector")
            (folder / "overview.txt").write_text("Company overview here")

            result = consolidate_working_folder(folder)

            assert os.path.exists(result)
            content = Path(result).read_text()
            assert "Technology sector" in content
            assert "Company overview here" in content
            assert "Test Company" in content  # Company name from folder

    def test_raises_on_missing_folder(self):
        """Raises ValueError for non-existent folder."""
        from primr.core.workspace import consolidate_working_folder

        with pytest.raises(ValueError, match="not found"):
            consolidate_working_folder("/nonexistent/folder")

    def test_raises_on_empty_folder(self):
        """Raises ValueError when folder has no research files (.txt or .md)."""
        from primr.core.workspace import consolidate_working_folder

        with (
            tempfile.TemporaryDirectory() as tmpdir,
            pytest.raises(ValueError, match="No research files"),
        ):
            consolidate_working_folder(tmpdir)


class TestValidateContextFiles:
    """Tests for validate_context_files function."""

    def test_valid_txt_file(self):
        """Accepts valid .txt files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("test content")

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 1
            assert len(result.invalid_files) == 0

    def test_valid_pdf_file(self):
        """Accepts valid .pdf files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.pdf"
            filepath.write_bytes(b"fake pdf content")

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 1

    def test_rejects_missing_file(self):
        """Rejects files that don't exist."""
        from primr.core.workspace import validate_context_files

        result = validate_context_files(["/nonexistent/file.txt"])

        assert len(result.valid_files) == 0
        assert len(result.invalid_files) == 1
        assert "not found" in result.invalid_files[0][1].lower()

    def test_rejects_empty_file(self):
        """Rejects empty files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "empty.txt"
            filepath.touch()  # Create empty file

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 0
            assert len(result.invalid_files) == 1
            assert "empty" in result.invalid_files[0][1].lower()

    def test_rejects_docx_with_warning(self):
        """Rejects .docx files with helpful warning."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.docx"
            filepath.write_bytes(b"fake docx")

            result = validate_context_files([str(filepath)])
            assert len(result.valid_files) == 0
            assert len(result.invalid_files) == 1
            assert len(result.warnings) > 0
            assert "Word" in result.invalid_files[0][1]

    def test_all_valid_property(self):
        """all_valid property returns True when no invalid files."""
        from primr.core.workspace import validate_context_files

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("content")

            result = validate_context_files([str(filepath)])
            assert result.all_valid is True

    def test_all_valid_false_when_invalid(self):
        """all_valid property returns False when there are invalid files."""
        from primr.core.workspace import validate_context_files

        result = validate_context_files(["/nonexistent.txt"])
        assert result.all_valid is False


class TestListSectionFiles:
    """Tests for list_section_files function."""

    def test_lists_txt_files(self):
        """Lists all .txt files in folder."""
        from primr.core.workspace import list_section_files

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.txt").write_text("a")
            (Path(tmpdir) / "b.txt").write_text("b")
            (Path(tmpdir) / "c.pdf").write_text("c")  # Should be excluded

            result = list_section_files(tmpdir)

            assert len(result) == 2
            assert all(f.suffix == ".txt" for f in result)

    def test_returns_sorted_list(self):
        """Returns files sorted alphabetically."""
        from primr.core.workspace import list_section_files

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "z.txt").write_text("z")
            (Path(tmpdir) / "a.txt").write_text("a")
            (Path(tmpdir) / "m.txt").write_text("m")

            result = list_section_files(tmpdir)

            names = [f.name for f in result]
            assert names == ["a.txt", "m.txt", "z.txt"]

    def test_returns_empty_for_missing_folder(self):
        """Returns empty list for non-existent folder."""
        from primr.core.workspace import list_section_files

        result = list_section_files("/nonexistent/folder")
        assert result == []


class TestGetSectionContent:
    """Tests for get_section_content function."""

    def test_reads_section_content(self):
        """Reads content from section file."""
        from primr.core.workspace import get_section_content

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "industry.txt").write_text("Technology")

            result = get_section_content(tmpdir, "industry")
            assert result == "Technology"

    def test_returns_none_for_missing_section(self):
        """Returns None when section file doesn't exist."""
        from primr.core.workspace import get_section_content

        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_section_content(tmpdir, "nonexistent")
            assert result is None
