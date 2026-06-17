"""
Tests for pipeline runner.

Task 19: Heartbeat updates and pipeline wiring.
"""

import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.pipeline_runner import (
    DIRECT_PROVIDER_KEY_ENV_VARS,
    PipelineRunner,
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
