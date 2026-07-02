"""
Tests for pipeline runner.

Task 19: Heartbeat updates and pipeline wiring.
"""

import os
import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.pipeline_runner import (
    DIRECT_PROVIDER_KEY_ENV_VARS,
    PipelineRunner,
    _collect_trace_artifacts,
    _with_trace_artifacts,
    _with_verification_artifacts,
    get_doctor_status,
)
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage


class TestPipelineRunner:
    """Tests for PipelineRunner class."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            s.rate_limiter.reset()
            yield s

    @pytest.fixture
    def runner(self, server):
        """Create a pipeline runner."""
        return PipelineRunner(server)

    def test_runner_creation(self, runner):
        """Runner can be created."""
        assert runner is not None
        assert runner._cancel_requested is False

    def test_request_cancel(self, runner):
        """Cancel can be requested."""
        runner.request_cancel()
        assert runner._cancel_requested is True


class TestTraceArtifactCollection:
    """Tests for same-run scrape trace attachment."""

    @pytest.fixture
    def server(self, tmp_path):
        journal_path = str(tmp_path / "test_journal.json")
        s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
        s.rate_limiter.reset()
        return s

    def test_collects_only_same_company_trace_files_in_job_window(
        self, server, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        job = server.job_store.create("Test Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        trace_dir = tmp_path / "logs" / "scrape_traces"
        trace_dir.mkdir(parents=True)

        recent = trace_dir / "Test_Corp_20260628_120000.jsonl"
        stale = trace_dir / "Test_Corp_20260627_120000.jsonl"
        other = trace_dir / "Other_Corp_20260628_120000.jsonl"
        for path in (recent, stale, other):
            path.write_text('{"schema_version": "1.1"}\n', encoding="utf-8")

        start_ts = job.start_time.timestamp()
        os.utime(recent, (start_ts + 10, start_ts + 10))
        os.utime(stale, (start_ts - 120, start_ts - 120))
        os.utime(other, (start_ts + 10, start_ts + 10))

        expected = str(Path("logs") / "scrape_traces" / recent.name)
        assert _collect_trace_artifacts(job) == [expected]
        assert _with_trace_artifacts(["report.md"], job) == ["report.md", expected]

    def test_trace_company_slug_matches_trace_logger_filename_rules(
        self, server, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        job = server.job_store.create("Test/Company\\Name", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        trace_dir = tmp_path / "logs" / "scrape_traces"
        trace_dir.mkdir(parents=True)
        trace = trace_dir / "Test_Company_Name_20260628_120000.jsonl"
        trace.write_text('{"schema_version": "1.1"}\n', encoding="utf-8")

        start_ts = job.start_time.timestamp()
        os.utime(trace, (start_ts + 10, start_ts + 10))

        expected = str(Path("logs") / "scrape_traces" / trace.name)
        assert _collect_trace_artifacts(job) == [expected]


class TestVerificationArtifactCollection:
    """Tests for same-run verification artifact attachment."""

    def test_appends_adjacent_verification_artifact_once(self, tmp_path):
        report = tmp_path / "report.md"
        verification = tmp_path / "verification.json"
        report.write_text("# Report", encoding="utf-8")
        verification.write_text('{"trust_score": 1.0}', encoding="utf-8")

        result = _with_verification_artifacts([str(report)])

        assert result == [str(report), str(verification)]
        assert _with_verification_artifacts(result) == result

    def test_ignores_missing_verification_artifact(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report", encoding="utf-8")

        assert _with_verification_artifacts([str(report)]) == [str(report)]


class TestDoctorStatus:
    """Tests for get_doctor_status function."""

    def test_returns_dict(self):
        """Doctor status returns a dict."""
        result = get_doctor_status()

        assert isinstance(result, dict)
        assert "orphaned_stores_count" in result
        assert "config_valid" in result
        assert "api_keys_configured" in result
        assert "warnings" in result

    def test_warnings_is_list(self):
        """Warnings is a list."""
        result = get_doctor_status()
        assert isinstance(result["warnings"], list)

    def test_api_keys_check(self, monkeypatch):
        """API keys check works."""
        for env_var in DIRECT_PROVIDER_KEY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        result = get_doctor_status()
        assert result["api_keys_configured"] is False
        assert any("direct LLM provider key" in w for w in result["warnings"])

        for env_var in DIRECT_PROVIDER_KEY_ENV_VARS:
            for key_name in DIRECT_PROVIDER_KEY_ENV_VARS:
                monkeypatch.delenv(key_name, raising=False)
            monkeypatch.setenv(env_var, "test-key")
            result = get_doctor_status()
            assert result["api_keys_configured"] is True


class TestHeartbeatIntegration:
    """Tests for heartbeat functionality."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            s = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            s.rate_limiter.reset()
            yield s

    def test_job_heartbeat_updates_timestamp(self, server):
        """Heartbeat updates the job timestamp."""
        import time

        job = server.job_store.create(
            company_name="Test Corp",
            mode="full",
            owner_client_id="test",
        )

        initial_time = job.last_heartbeat_time
        time.sleep(0.1)

        job.heartbeat()
        server.job_store.update(job)

        updated_job = server.job_store.get(job.job_id)
        assert updated_job.last_heartbeat_time > initial_time

    def test_job_heartbeat_updates_progress(self, server):
        """Heartbeat can update progress."""
        job = server.job_store.create(
            company_name="Test Corp",
            mode="full",
            owner_client_id="test",
        )

        job.advance_stage(ResearchStage.SCRAPING)
        job.heartbeat(progress=50)
        server.job_store.update(job)

        updated_job = server.job_store.get(job.job_id)
        assert updated_job.stage_progress_percent == 50


class TestPerJobAccountingReset:
    """Every job starts with fresh usage accounting (bug-hunt finding: a
    long-lived server bled prior jobs' Gemini spend into later jobs'
    checkpoints and usage records)."""

    @pytest.mark.asyncio
    async def test_run_research_resets_usage_accounting_first(self, monkeypatch):
        from unittest.mock import MagicMock

        # The reset is the first act inside the job's try block: raising from
        # it proves the call AND that a broken reset fails THIS job (recorded
        # FAILED) instead of escaping and wedging the single-job store.
        sentinel = MagicMock(side_effect=RuntimeError("stop-after-reset"))
        monkeypatch.setattr("primr.ai.client.reset_run_usage_accounting", sentinel)

        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "journal.json")
            server = create_mcp_server(journal_path=journal_path, skip_background_tasks=True)
            runner = PipelineRunner(server)

            job = server.job_store.create(company_name="Acme Corp", mode="full")
            await runner.run_research(job, "https://acme.example", "full")

            sentinel.assert_called_once()
            assert job.current_stage == ResearchStage.FAILED
            assert "stop-after-reset" in (job.error_message or "")
