"""
Tests for pipeline runner.

Task 19: Heartbeat updates and pipeline wiring.
"""

import os
import tempfile
from pathlib import Path

import pytest

from primr.mcp_server.doctor_status import (
    DIRECT_PROVIDER_KEY_ENV_VARS,
    attach_cloud_diagnostics,
    get_doctor_status,
)
from primr.mcp_server.pipeline_runner import (
    PUBLIC_RESEARCH_FAILURE_MESSAGE,
    PipelineRunner,
    _collect_trace_artifacts,
    _with_trace_artifacts,
    _with_verification_artifacts,
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
        recent.write_text(
            f'{{"schema_version": "1.1", "run_id": "{job.job_id}"}}\n',
            encoding="utf-8",
        )
        stale.write_text(
            f'{{"schema_version": "1.1", "run_id": "{job.job_id}"}}\n',
            encoding="utf-8",
        )
        other.write_text(
            f'{{"schema_version": "1.1", "run_id": "{job.job_id}"}}\n',
            encoding="utf-8",
        )

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
        trace.write_text(
            f'{{"schema_version": "1.1", "run_id": "{job.job_id}"}}\n',
            encoding="utf-8",
        )

        start_ts = job.start_time.timestamp()
        os.utime(trace, (start_ts + 10, start_ts + 10))

        expected = str(Path("logs") / "scrape_traces" / trace.name)
        assert _collect_trace_artifacts(job) == [expected]

    def test_overlapping_trace_window_attaches_only_matching_run_id(
        self, server, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        job = server.job_store.create("Test Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        trace_dir = tmp_path / "logs" / "scrape_traces"
        trace_dir.mkdir(parents=True)
        owned = trace_dir / "Test_Corp_20260628_120000_000001.jsonl"
        foreign = trace_dir / "Test_Corp_20260628_120000_000002.jsonl"
        owned.write_text(
            f'{{"schema_version": "1.1", "run_id": "{job.job_id}"}}\n',
            encoding="utf-8",
        )
        foreign.write_text(
            '{"schema_version": "1.1", "run_id": "another-job"}\n',
            encoding="utf-8",
        )
        within_window = job.start_time.timestamp() + 10
        os.utime(owned, (within_window, within_window))
        os.utime(foreign, (within_window, within_window))

        expected = str(Path("logs") / "scrape_traces" / owned.name)
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

    def test_status_and_checks_match_agent_contract(self, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        for env_var in DIRECT_PROVIDER_KEY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        result = get_doctor_status()

        assert result["status"] == "degraded"
        assert {check["component"] for check in result["checks"]} == {
            "configuration",
            "provider_keys",
            "output_directory",
        }
        assert result["orphaned_stores_count"] == 0

    def test_audit_health_is_projected_without_removing_legacy_fields(self, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))

        class AuditHealth:
            def health_snapshot(self):
                return {
                    "schema_version": "1.0",
                    "status": "degraded",
                    "sink": "jsonl",
                    "last_write_succeeded": False,
                }

        result = get_doctor_status(audit_log=AuditHealth())

        assert result["audit_log"]["status"] == "degraded"
        assert result["status"] == "degraded"
        assert any(check["component"] == "audit_log" for check in result["checks"])
        assert any("Audit persistence is degraded" in warning for warning in result["warnings"])
        assert "config_valid" in result

    def test_unobserved_audit_sink_degrades_overall_status(self, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "configured")

        class AuditHealth:
            def health_snapshot(self):
                return {"schema_version": "1.0", "status": "not_observed", "sink": "jsonl"}

        result = get_doctor_status(audit_log=AuditHealth())

        assert result["status"] == "degraded"
        assert any("not been observed" in warning for warning in result["warnings"])

    def test_output_directory_is_probed_after_validation(self, monkeypatch, tmp_path):
        output_dir = tmp_path / "created-by-validation"
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(output_dir))

        class ValidationResult:
            errors: list[str] = []

        def validate_and_create():
            output_dir.mkdir()
            return ValidationResult()

        monkeypatch.setattr("primr.config.config.validate_config", validate_and_create)

        result = get_doctor_status()
        output_check = next(
            check for check in result["checks"] if check["component"] == "output_directory"
        )
        assert output_check["status"] == "ok"

    def test_configuration_details_and_paths_are_not_returned(self, monkeypatch, tmp_path):
        output_dir = tmp_path / "private-output-path"
        private_detail = f"cannot create {output_dir}"
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(output_dir))

        class ValidationResult:
            errors = [private_detail]

        monkeypatch.setattr("primr.config.config.validate_config", ValidationResult)

        result = get_doctor_status()
        serialized = str(result)
        assert result["status"] == "unhealthy"
        assert private_detail not in serialized
        assert str(output_dir) not in serialized

    def test_cloud_failure_is_folded_into_overall_status(self):
        response = {"status": "healthy", "checks": [], "warnings": []}

        attach_cloud_diagnostics(
            response,
            {"container_app_health": {"status": "error", "probe_performed": True}},
        )

        assert response["status"] == "degraded"
        assert response["checks"] == [
            {"component": "cloud.container_app_health", "status": "error"}
        ]

    def test_non_gemini_or_keyless_state_is_not_a_configuration_failure(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        for env_var in DIRECT_PROVIDER_KEY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        result = get_doctor_status()

        assert result["config_valid"] is True
        assert result["status"] == "degraded"
        assert not any("Config: GEMINI_API_KEY" in warning for warning in result["warnings"])


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
            assert job.error_message == PUBLIC_RESEARCH_FAILURE_MESSAGE
