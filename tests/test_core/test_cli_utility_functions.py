"""Unit tests for utility functions in primr.core.cli:
list_recent_outputs, clean_temp_files, check_api_quota, check_pending_jobs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.core.cli import (
    check_api_quota,
    check_pending_jobs,
    clean_temp_files,
    list_recent_outputs,
)


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Redirect OUTPUT_DIR to tmp_path."""
    monkeypatch.setattr("primr.core.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(
        "primr.config.config.OUTPUT_DIR", str(tmp_path / "output")
    )
    od = tmp_path / "output"
    od.mkdir()
    return od


@pytest.fixture
def working_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.cli.WORKING_DIR", str(tmp_path / "working"))
    monkeypatch.setattr(
        "primr.config.config.WORKING_DIR", str(tmp_path / "working")
    )
    wd = tmp_path / "working"
    wd.mkdir()
    return wd


class TestListRecentOutputs:
    def test_no_files_prints_message(self, output_dir, capsys):
        list_recent_outputs()
        captured = capsys.readouterr()
        assert "No recent outputs found" in captured.out

    def test_lists_existing_docx_files(self, output_dir, capsys):
        # Create several fake .docx files
        for i in range(3):
            (output_dir / f"report_{i}.docx").write_text("x", encoding="utf-8")
        list_recent_outputs()
        captured = capsys.readouterr()
        assert "RECENT RESEARCH OUTPUTS" in captured.out
        assert "report_0.docx" in captured.out

    def test_caps_listing_at_20(self, output_dir, capsys):
        # Create 25 fake .docx files
        for i in range(25):
            (output_dir / f"report_{i:02d}.docx").write_text("x", encoding="utf-8")
        list_recent_outputs()
        captured = capsys.readouterr()
        assert "and 5 more files" in captured.out


class TestCleanTempFiles:
    def test_no_files_prints_zero(self, working_dir, capsys):
        clean_temp_files()
        captured = capsys.readouterr()
        assert "Cleaned 0" in captured.out

    def test_removes_empty_subdirectories(self, working_dir, capsys):
        # Create empty subdirs
        (working_dir / "empty1").mkdir()
        (working_dir / "empty2").mkdir()
        # Non-empty subdir should NOT be removed
        non_empty = working_dir / "has_content"
        non_empty.mkdir()
        (non_empty / "x.txt").write_text("body", encoding="utf-8")

        clean_temp_files()
        assert not (working_dir / "empty1").exists()
        assert not (working_dir / "empty2").exists()
        assert non_empty.exists()

    def test_removes_tmp_files(self, working_dir):
        (working_dir / "x.tmp").write_text("body", encoding="utf-8")
        (working_dir / "y.tmp").write_text("body", encoding="utf-8")
        clean_temp_files()
        assert not (working_dir / "x.tmp").exists()


class TestCheckApiQuota:
    def test_no_api_key_returns_with_error(self, monkeypatch, capsys):
        fake_settings = MagicMock()
        fake_settings.api.gemini_key = ""
        monkeypatch.setattr(
            "primr.config.settings.get_settings", lambda: fake_settings
        )
        check_api_quota()
        captured = capsys.readouterr()
        assert "GEMINI_API_KEY" in captured.out

    def test_quota_available(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.api.gemini_key = "AI" + "x" * 30
        monkeypatch.setattr(
            "primr.config.settings.get_settings", lambda: fake_settings
        )
        fake = MagicMock()
        client = MagicMock()
        response = MagicMock()
        response.text = "OK"
        client.models.generate_content.return_value = response
        fake.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            check_api_quota()

    def test_quota_exhausted(self, monkeypatch, capsys):
        fake_settings = MagicMock()
        fake_settings.api.gemini_key = "AI" + "x" * 30
        monkeypatch.setattr(
            "primr.config.settings.get_settings", lambda: fake_settings
        )
        fake = MagicMock()
        fake.Client.return_value.models.generate_content.side_effect = RuntimeError(
            "RESOURCE_EXHAUSTED: per_day quota"
        )
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            check_api_quota()
        captured = capsys.readouterr()
        assert "EXHAUSTED" in captured.out


class TestCheckPendingJobs:
    def test_no_pending_jobs_prints_message(self, monkeypatch, capsys):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(dr, "get_pending_jobs", dict)
        check_pending_jobs()
        captured = capsys.readouterr()
        assert "No pending jobs" in captured.out

    def test_in_progress_status_logged(self, monkeypatch):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {"j1": {"description": "ExampleCo", "started": "now"}},
        )
        client = MagicMock()
        client.check_job.return_value = {"status": "in_progress", "error": None}
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        check_pending_jobs()

    def test_failed_status_logged(self, monkeypatch):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {"j1": {"description": "ExampleCo", "started": "now"}},
        )
        client = MagicMock()
        client.check_job.return_value = {
            "status": "failed",
            "error": "provider error",
            "error_source": "provider",
        }
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        check_pending_jobs()

    def test_completed_status_finalizes(self, monkeypatch, tmp_path):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {"j1": {"description": "ExampleCo", "started": "now"}},
        )
        client = MagicMock()
        client.check_job.return_value = {
            "status": "completed",
            "content": "full report body",
        }
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        save_mock = MagicMock(
            return_value={"md": "/x.md", "txt": "/x.txt", "docx": "/x.docx"}
        )
        monkeypatch.setattr("primr.core.cli._save_recovered_outputs", save_mock)
        check_pending_jobs()
        save_mock.assert_called_once()
