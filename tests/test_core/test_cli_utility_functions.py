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


@pytest.fixture(autouse=True)
def _bridge_pending_job_test_seam(monkeypatch):
    import primr.ai.deep_research as deep_research
    from primr.core import cli_recovery

    monkeypatch.setattr(
        cli_recovery,
        "_read_pending_jobs",
        lambda: (True, deep_research.get_pending_jobs()),
    )


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """Redirect OUTPUT_DIR to tmp_path."""
    monkeypatch.setattr("primr.core.cli.OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
    od = tmp_path / "output"
    od.mkdir()
    working = tmp_path / "working"
    working.mkdir()
    logs = tmp_path / "logs" / "chat_history"
    logs.mkdir(parents=True)
    monkeypatch.setattr("primr.core.cli.WORKING_DIR", str(working))
    monkeypatch.setattr("primr.core.cli.LOGS_DIR", str(logs))
    return od


@pytest.fixture
def working_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.cli.WORKING_DIR", str(tmp_path / "working"))
    monkeypatch.setattr("primr.config.config.WORKING_DIR", str(tmp_path / "working"))
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
        assert "Deliverables:" in captured.out
        assert "report_0.docx" in captured.out
        assert "| docx" in captured.out

    def test_separates_primary_deliverables_from_diagnostics(self, output_dir, capsys):
        (output_dir / "Acme_Strategic_Overview.md").write_text("report", encoding="utf-8")
        (output_dir / "Acme_Strategic_Overview.md.calibration.json").write_text(
            "{}", encoding="utf-8"
        )
        (output_dir / "Acme_QA.json").write_text("{}", encoding="utf-8")

        list_recent_outputs()
        out = capsys.readouterr().out

        assert "Deliverables:" in out
        assert "Diagnostics:" in out
        deliverables_index = out.index("Deliverables:")
        diagnostics_index = out.index("Diagnostics:")
        assert deliverables_index < diagnostics_index
        assert "Acme_Strategic_Overview.md" in out
        assert "calibration.json" in out
        assert "| calibration" in out
        assert "| markdown" in out
        # Primary reports must not be buried under the diagnostics-only bucket.
        deliverable_block = out[deliverables_index:diagnostics_index]
        assert "Acme_Strategic_Overview.md" in deliverable_block
        assert "calibration.json" not in deliverable_block

    def test_ranks_named_reports_above_empty_incidental_files(self, output_dir, capsys):
        import os
        import time

        incidental = output_dir / "scratch_notes.md"
        empty_report = output_dir / "empty_scratch.md"
        primary = output_dir / "Acme_Strategic_Overview_07-15-2026.md"
        incidental.write_text("noise", encoding="utf-8")
        empty_report.write_text("", encoding="utf-8")
        primary.write_text("full report body", encoding="utf-8")
        # Make incidental newest so mtime alone would rank it first.
        now = time.time()
        os.utime(incidental, (now + 10, now + 10))
        os.utime(empty_report, (now + 20, now + 20))
        os.utime(primary, (now, now))

        list_recent_outputs()
        out = capsys.readouterr().out
        deliverable_block = out[
            out.index("Deliverables:") : out.index("-" * 60, out.index("Deliverables:"))
        ]
        primary_pos = deliverable_block.index("Acme_Strategic_Overview_07-15-2026.md")
        incidental_pos = deliverable_block.index("scratch_notes.md")
        empty_pos = deliverable_block.index("empty_scratch.md")
        assert primary_pos < incidental_pos < empty_pos

    def test_caps_listing_at_20(self, output_dir, capsys):
        # Create 25 fake .docx files
        for i in range(25):
            (output_dir / f"report_{i:02d}.docx").write_text("x", encoding="utf-8")
        list_recent_outputs()
        captured = capsys.readouterr()
        assert "and 5 more files" in captured.out

    def test_json_lists_output_run_state_and_trace(self, output_dir, tmp_path, capsys):
        import json

        overview = output_dir / "Acme_Strategic_Overview_07-17-2026.md"
        overview.write_text("body", encoding="utf-8")
        run_dir = tmp_path / "working" / "Acme" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "_run_state.json").write_text("{}", encoding="utf-8")
        trace_dir = tmp_path / "logs" / "scrape_traces"
        trace_dir.mkdir()
        (trace_dir / "scrape_trace_job.jsonl").write_text("{}\n", encoding="utf-8")

        assert list_recent_outputs(json_output=True) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "primr.artifact-inventory"
        assert payload["schema_version"] == "1.1"
        assert {row["artifact_type"] for row in payload["artifacts"]} >= {
            "report_markdown",
            "run_state",
            "scrape_trace",
        }
        by_name = {row["file_name"]: row for row in payload["artifacts"]}
        assert by_name[overview.name]["artifact_role"] == "primary_report"

    def test_missing_custom_output_root_returns_nonzero(self, output_dir, tmp_path, capsys):
        assert list_recent_outputs(output_dir=str(tmp_path / "missing")) == 1
        assert "Unable to scan artifact roots" in capsys.readouterr().out


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
        monkeypatch.setattr("primr.config.settings.get_settings", lambda: fake_settings)
        assert check_api_quota() == 1
        captured = capsys.readouterr()
        assert "GEMINI_API_KEY" in captured.out

    def test_quota_available(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.api.gemini_key = "AI" + "x" * 30
        monkeypatch.setattr("primr.config.settings.get_settings", lambda: fake_settings)
        fake = MagicMock()
        client = MagicMock()
        client.models.get.return_value = MagicMock()
        fake.Client.return_value = client
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            assert check_api_quota() == 0
        client.models.get.assert_called_once()
        client.models.generate_content.assert_not_called()

    def test_quota_exhausted(self, monkeypatch, capsys):
        fake_settings = MagicMock()
        fake_settings.api.gemini_key = "AI" + "x" * 30
        monkeypatch.setattr("primr.config.settings.get_settings", lambda: fake_settings)
        fake = MagicMock()
        fake.Client.return_value.models.get.side_effect = RuntimeError(
            "RESOURCE_EXHAUSTED: per_day quota"
        )
        with (
            patch.dict("sys.modules", {"google": MagicMock(genai=fake)}),
            patch("google.genai", fake, create=True),
        ):
            assert check_api_quota() == 1
        captured = capsys.readouterr()
        assert "EXHAUSTED" in captured.out


class TestCheckPendingJobs:
    def test_unreadable_registry_is_visible_and_nonzero(self, monkeypatch, capsys):
        from primr.core import cli_recovery

        monkeypatch.setattr(cli_recovery, "_read_pending_jobs", lambda: (False, {}))

        assert check_pending_jobs() == 1
        assert "could not read the recovery registry" in capsys.readouterr().out

    def test_unreadable_registry_json_is_visible_and_nonzero(self, monkeypatch, capsys):
        import json

        from primr.core import cli_recovery

        monkeypatch.setattr(cli_recovery, "_read_pending_jobs", lambda: (False, {}))

        assert check_pending_jobs(json_output=True) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "error"
        assert payload["error"]["kind"] == "recovery_registry_unreadable"
        assert payload["jobs"] == []

    def test_json_status_is_one_versioned_object(self, monkeypatch, capsys):
        import json

        import primr.ai.deep_research as dr
        from primr.core import cli_recovery

        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {"j1": {"description": "ExampleCo", "started": "2026-07-10T00:00:00Z"}},
        )
        client = MagicMock()
        client.check_job.return_value = {"status": "in_progress", "error": None}
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        monkeypatch.setattr(cli_recovery, "_find_latest_run_state", lambda: None)

        assert check_pending_jobs(json_output=True) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "primr.job-status-list"
        assert payload["jobs"][0]["lifecycle_state"] == "in_progress"
        assert payload["jobs"][0]["source"] == "provider_recovery"

    def test_json_check_error_is_observation_and_nonzero(self, monkeypatch, capsys):
        import json

        import primr.ai.deep_research as dr
        from primr.core import cli_recovery

        monkeypatch.setattr(dr, "get_pending_jobs", lambda: {"j1": {}})
        client = MagicMock()
        client.check_job.return_value = {
            "status": "check_error",
            "error": "network down",
            "error_source": "local",
        }
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)
        monkeypatch.setattr(cli_recovery, "_find_latest_run_state", lambda: None)

        assert check_pending_jobs(json_output=True) == 1
        job = json.loads(capsys.readouterr().out)["jobs"][0]
        assert job["lifecycle_state"] == "unknown"
        assert job["error"]["kind"] == "observation"

    def test_no_pending_jobs_also_shows_latest_local_state(self, monkeypatch, tmp_path, capsys):
        import primr.ai.deep_research as dr
        from primr.core import cli_recovery

        monkeypatch.setattr(dr, "get_pending_jobs", dict)
        run_dir = tmp_path / "ExampleCo" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / "_run_state.json").write_text(
            '{"status":"running","current_phase":"scrape"}',
            encoding="utf-8",
        )
        monkeypatch.setattr(cli_recovery, "WORKING_DIR", str(tmp_path))
        assert check_pending_jobs() == 0
        captured = capsys.readouterr()
        assert "No pending cloud jobs" in captured.out
        assert "Latest local run state" in captured.out
        assert "Company: ExampleCo" in captured.out

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
        assert check_pending_jobs() == 0

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
        assert check_pending_jobs() == 1

    def test_status_check_error_returns_nonzero_and_keeps_retry_guidance(self, monkeypatch, capsys):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr,
            "get_pending_jobs",
            lambda: {"j1": {"description": "ExampleCo", "started": "now"}},
        )
        client = MagicMock()
        client.check_job.return_value = {
            "status": "check_error",
            "error": "network down",
            "error_source": "local",
        }
        monkeypatch.setattr(dr, "get_deep_research_client", lambda: client)

        assert check_pending_jobs() == 1
        output = capsys.readouterr().out
        assert "CHECK ERROR" in output
        assert "Re-run `primr --check-jobs` later" in output

    def test_completed_status_is_read_only_and_points_to_resume(self, monkeypatch, capsys):
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
        save_mock = MagicMock(return_value={"md": "/x.md", "txt": "/x.txt", "docx": "/x.docx"})
        monkeypatch.setattr("primr.core.cli_recovery._save_recovered_outputs", save_mock)
        assert check_pending_jobs() == 0
        save_mock.assert_not_called()
        assert "primr --resume-latest" in capsys.readouterr().out
