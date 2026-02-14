"""
Unit tests for the job runner contract.

Tests:
- Job spec parsing (Requirements 1.1)
- Exit code mapping (Requirements 1.8)
- SIGTERM handling (Requirements 1.10)

Requirements: 1.1, 1.2, 1.8, 1.10, 2.6
"""

import json
import os
import signal
import subprocess
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from deploy.runner import (
    EXIT_CANCELLED,
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
    EXPECTED_ARTIFACTS,
    EventWriter,
    HeartbeatWriter,
    JobSpec,
    RunnerState,
    StructuredLogger,
    _state,
    build_primr_command,
    format_timestamp,
    get_expected_artifacts,
    handle_sigterm,
    map_exit_code,
    parse_job_spec,
    run_primr,
    utc_now,
)


class TestJobSpec:
    """Tests for JobSpec dataclass and parsing."""

    def test_job_spec_from_dict_valid(self):
        """Test creating JobSpec from valid dictionary."""
        data = {
            "job_id": "test-123",
            "deployment": "prod",
            "execution_id": "ecs-task-abc",
            "attempt": 1,
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "mode": "full",
            "options": {"cloud_vendor": "aws"},
        }

        spec = JobSpec.from_dict(data)

        assert spec.job_id == "test-123"
        assert spec.deployment == "prod"
        assert spec.execution_id == "ecs-task-abc"
        assert spec.attempt == 1
        assert spec.company_name == "Acme Corp"
        assert spec.company_url == "https://acme.example"
        assert spec.mode == "full"
        assert spec.options == {"cloud_vendor": "aws"}

    def test_job_spec_from_dict_minimal(self):
        """Test creating JobSpec with minimal required fields."""
        data = {
            "job_id": "test-123",
            "deployment": "dev",
            "execution_id": "task-1",
            "company_name": "Test Co",
        }

        spec = JobSpec.from_dict(data)

        assert spec.job_id == "test-123"
        assert spec.mode == "full"  # Default
        assert spec.attempt == 1  # Default
        assert spec.options == {}  # Default

    def test_job_spec_missing_job_id(self):
        """Test that missing job_id raises ValueError."""
        data = {
            "deployment": "prod",
            "execution_id": "task-1",
            "company_name": "Test Co",
        }

        with pytest.raises(ValueError, match="job_id is required"):
            JobSpec.from_dict(data)

    def test_job_spec_missing_deployment(self):
        """Test that missing deployment raises ValueError."""
        data = {
            "job_id": "test-123",
            "execution_id": "task-1",
            "company_name": "Test Co",
        }

        with pytest.raises(ValueError, match="deployment is required"):
            JobSpec.from_dict(data)

    def test_job_spec_missing_execution_id(self):
        """Test that missing execution_id raises ValueError."""
        data = {
            "job_id": "test-123",
            "deployment": "prod",
            "company_name": "Test Co",
        }

        with pytest.raises(ValueError, match="execution_id is required"):
            JobSpec.from_dict(data)

    def test_job_spec_missing_company_info(self):
        """Test that missing both company_name and company_url raises ValueError."""
        data = {
            "job_id": "test-123",
            "deployment": "prod",
            "execution_id": "task-1",
        }

        with pytest.raises(ValueError, match="company_name or company_url is required"):
            JobSpec.from_dict(data)

    def test_job_spec_invalid_mode(self):
        """Test that invalid mode raises ValueError."""
        data = {
            "job_id": "test-123",
            "deployment": "prod",
            "execution_id": "task-1",
            "company_name": "Test Co",
            "mode": "invalid",
        }

        with pytest.raises(ValueError, match="Invalid mode"):
            JobSpec.from_dict(data)

    def test_job_spec_valid_modes(self):
        """Test all valid modes are accepted."""
        for mode in ["scrape", "deep", "full"]:
            data = {
                "job_id": "test-123",
                "deployment": "prod",
                "execution_id": "task-1",
                "company_name": "Test Co",
                "mode": mode,
            }
            spec = JobSpec.from_dict(data)
            assert spec.mode == mode

    def test_job_spec_invalid_attempt(self):
        """Test that attempt < 1 raises ValueError."""
        data = {
            "job_id": "test-123",
            "deployment": "prod",
            "execution_id": "task-1",
            "company_name": "Test Co",
            "attempt": 0,
        }

        with pytest.raises(ValueError, match="attempt must be >= 1"):
            JobSpec.from_dict(data)

    def test_job_spec_timeout_clamped(self):
        """Test that timeout is clamped to max value."""
        data = {
            "job_id": "test-123",
            "deployment": "prod",
            "execution_id": "task-1",
            "company_name": "Test Co",
            "timeout_seconds": 999999,  # Way over max
        }

        spec = JobSpec.from_dict(data)
        assert spec.timeout_seconds == 120 * 60  # Max is 120 minutes

    def test_job_spec_to_dict(self):
        """Test converting JobSpec back to dictionary."""
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=2,
            company_name="Test Co",
            company_url="https://test.example",
            mode="deep",
            options={"no_qa": True},
        )

        data = spec.to_dict()

        assert data["job_id"] == "test-123"
        assert data["deployment"] == "prod"
        assert data["attempt"] == 2
        assert data["mode"] == "deep"
        assert data["options"] == {"no_qa": True}


class TestParseJobSpec:
    """Tests for parse_job_spec function."""

    def test_parse_from_env_var(self):
        """Test parsing job spec from JOB_SPEC environment variable."""
        spec_data = {
            "job_id": "env-test-123",
            "deployment": "staging",
            "execution_id": "task-env",
            "company_name": "Env Test Co",
            "mode": "scrape",
        }

        with patch.dict(os.environ, {"JOB_SPEC": json.dumps(spec_data)}):
            spec = parse_job_spec()

        assert spec.job_id == "env-test-123"
        assert spec.deployment == "staging"
        assert spec.mode == "scrape"

    def test_parse_from_file(self, tmp_path):
        """Test parsing job spec from /job/spec.json file."""
        spec_data = {
            "job_id": "file-test-123",
            "deployment": "prod",
            "execution_id": "task-file",
            "company_name": "File Test Co",
            "mode": "full",
        }

        # Create temp spec file
        spec_file = tmp_path / "spec.json"
        spec_file.write_text(json.dumps(spec_data))

        with patch.dict(os.environ, {}, clear=True):
            # Remove JOB_SPEC if present
            os.environ.pop("JOB_SPEC", None)

            # Mock the file path
            with patch("deploy.runner.Path") as mock_path:
                mock_path.return_value.exists.return_value = True
                mock_path.return_value.read_text.return_value = json.dumps(spec_data)

                spec = parse_job_spec()

        assert spec.job_id == "file-test-123"

    def test_parse_invalid_json_env(self):
        """Test that invalid JSON in env var raises ValueError."""
        with patch.dict(os.environ, {"JOB_SPEC": "not valid json"}):
            with pytest.raises(ValueError, match="Invalid JSON"):
                parse_job_spec()

    def test_parse_no_spec_found(self):
        """Test that missing spec raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JOB_SPEC", None)

            with patch("deploy.runner.Path") as mock_path:
                mock_path.return_value.exists.return_value = False

                with pytest.raises(ValueError, match="No job spec found"):
                    parse_job_spec()


class TestExpectedArtifacts:
    """Tests for get_expected_artifacts function."""

    def test_scrape_mode_artifacts(self):
        """Test expected artifacts for scrape mode."""
        artifacts = get_expected_artifacts("scrape")
        assert artifacts == ["scraped_content.txt", "insights.txt"]

    def test_deep_mode_artifacts(self):
        """Test expected artifacts for deep mode."""
        artifacts = get_expected_artifacts("deep")
        assert artifacts == ["dossier.txt", "report.docx", "report.md"]

    def test_full_mode_artifacts(self):
        """Test expected artifacts for full mode."""
        artifacts = get_expected_artifacts("full")
        assert artifacts == [
            "scraped_content.txt",
            "insights.txt",
            "dossier.txt",
            "report.docx",
            "report.md",
        ]

    def test_unknown_mode_defaults_to_full(self):
        """Test that unknown mode returns full mode artifacts."""
        artifacts = get_expected_artifacts("unknown")
        assert artifacts == EXPECTED_ARTIFACTS["full"]


class TestExitCodeMapping:
    """Tests for exit code mapping."""

    def test_success_maps_to_zero(self):
        """Test that success maps to exit code 0."""
        assert map_exit_code(0, None) == EXIT_SUCCESS

    def test_failure_maps_to_one(self):
        """Test that failure maps to exit code 1."""
        assert map_exit_code(1, "some error") == EXIT_FAILURE

    def test_cancelled_maps_to_130(self):
        """Test that cancellation maps to exit code 130."""
        assert map_exit_code(0, "user_cancelled") == EXIT_CANCELLED

    def test_timeout_maps_to_124(self):
        """Test that timeout maps to exit code 124."""
        assert map_exit_code(0, "timeout") == EXIT_TIMEOUT


class TestRunPrimrCancellation:
    """Tests for run_primr cancellation behavior."""

    def test_cancel_timeout_still_returns_cancelled(self, tmp_path):
        """Cancellation should remain CANCELLED even if terminate wait times out."""
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://example.com",
            mode="scrape",
        )
        events = EventWriter(tmp_path / "events.jsonl")
        logs = StructuredLogger(tmp_path / "runner.jsonl")

        mock_proc = MagicMock()
        mock_proc.stdout = iter(["working\n"])
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="primr", timeout=10), 0]
        mock_proc.poll.return_value = None

        old_cancel = _state.cancel_requested
        _state.cancel_requested = True
        try:
            with patch("deploy.runner.subprocess.Popen", return_value=mock_proc):
                exit_code, error = run_primr(spec, tmp_path, events, logs)
        finally:
            _state.cancel_requested = old_cancel
            _state.process = None

        assert exit_code == EXIT_CANCELLED
        assert error == "user_cancelled"
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()


class TestRunnerState:
    """Tests for RunnerState thread-safe state management."""

    def test_initial_state(self):
        """Test initial state values."""
        state = RunnerState()
        assert state.cancel_requested is False
        assert state.current_stage == "initializing"
        assert state.percent == 0
        assert state.started_at is None
        assert state.process is None

    def test_cancel_requested_thread_safe(self):
        """Test that cancel_requested is thread-safe."""
        state = RunnerState()

        def set_cancel():
            state.cancel_requested = True

        thread = threading.Thread(target=set_cancel)
        thread.start()
        thread.join()

        assert state.cancel_requested is True

    def test_stage_updates(self):
        """Test stage and percent updates."""
        state = RunnerState()

        state.current_stage = "scraping"
        state.percent = 50

        assert state.current_stage == "scraping"
        assert state.percent == 50


class TestSIGTERMHandling:
    """Tests for SIGTERM signal handling."""

    @pytest.mark.skipif(os.name == "nt", reason="SIGTERM not available on Windows")
    def test_sigterm_sets_cancel_flag(self):
        """Test that SIGTERM handler sets cancel_requested flag."""
        # Reset global state
        _state.cancel_requested = False

        # Call handler directly (simulating signal)
        handle_sigterm(signal.SIGTERM, None)

        assert _state.cancel_requested is True

        # Reset for other tests
        _state.cancel_requested = False

    @pytest.mark.skipif(os.name == "nt", reason="SIGTERM not available on Windows")
    def test_sigterm_terminates_subprocess(self):
        """Test that SIGTERM handler terminates running subprocess."""
        _state.cancel_requested = False

        # Mock a running process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        _state.process = mock_process

        # Call handler
        handle_sigterm(signal.SIGTERM, None)

        assert _state.cancel_requested is True
        mock_process.terminate.assert_called_once()

        # Reset
        _state.cancel_requested = False
        _state.process = None

    def test_sigint_sets_cancel_flag(self):
        """Test that SIGINT handler sets cancel_requested flag (works on all platforms)."""
        # Reset global state
        _state.cancel_requested = False

        # Call handler directly (simulating signal) - SIGINT works on Windows too
        handle_sigterm(signal.SIGINT, None)

        assert _state.cancel_requested is True

        # Reset for other tests
        _state.cancel_requested = False


class TestBuildPrimrCommand:
    """Tests for building primr CLI command."""

    def test_basic_command(self, tmp_path):
        """Test basic command generation."""
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://test.example",
            mode="full",
        )

        cmd = build_primr_command(spec, tmp_path)

        assert "Test Co" in cmd
        assert "https://test.example" in cmd
        assert "--mode" in cmd
        assert "complete" in cmd  # full maps to complete
        assert "--skip-confirm" in cmd

    def test_scrape_mode_mapping(self, tmp_path):
        """Test that scrape mode maps to scrape-only."""
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://test.example",
            mode="scrape",
        )

        cmd = build_primr_command(spec, tmp_path)

        assert "scrape-only" in cmd

    def test_deep_mode_mapping(self, tmp_path):
        """Test that deep mode maps to deep-research."""
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://test.example",
            mode="deep",
        )

        cmd = build_primr_command(spec, tmp_path)

        assert "deep-research" in cmd

    def test_options_included(self, tmp_path):
        """Test that options are included in command."""
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://test.example",
            mode="full",
            options={"cloud_vendor": "aws", "no_qa": True},
        )

        cmd = build_primr_command(spec, tmp_path)

        assert "--cloud-vendor" in cmd
        assert "aws" in cmd
        assert "--no-qa" in cmd


class TestStructuredLogger:
    """Tests for StructuredLogger."""

    def test_log_creates_file(self, tmp_path):
        """Test that logging creates the log file."""
        log_file = tmp_path / "_logs" / "runner.jsonl"
        logger = StructuredLogger(log_file)

        logger.info("test_event", key="value")

        assert log_file.exists()

    def test_log_writes_json(self, tmp_path):
        """Test that log entries are valid JSON."""
        log_file = tmp_path / "_logs" / "runner.jsonl"
        logger = StructuredLogger(log_file)

        logger.info("test_event", key="value")

        content = log_file.read_text()
        entry = json.loads(content.strip())

        assert entry["event"] == "test_event"
        assert entry["key"] == "value"
        assert entry["level"] == "info"
        assert "ts" in entry

    def test_log_levels(self, tmp_path):
        """Test different log levels."""
        log_file = tmp_path / "_logs" / "runner.jsonl"
        logger = StructuredLogger(log_file)

        logger.info("info_event")
        logger.warning("warning_event")
        logger.error("error_event")

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

        entries = [json.loads(line) for line in lines]
        assert entries[0]["level"] == "info"
        assert entries[1]["level"] == "warning"
        assert entries[2]["level"] == "error"


class TestEventWriter:
    """Tests for EventWriter."""

    def test_write_event(self, tmp_path):
        """Test writing progress events."""
        events_file = tmp_path / "events.jsonl"
        writer = EventWriter(events_file)

        writer.write_event("scrape", 25, "Scraping website")

        assert events_file.exists()
        content = events_file.read_text()
        entry = json.loads(content.strip())

        assert entry["stage"] == "scrape"
        assert entry["percent"] == 25
        assert entry["message"] == "Scraping website"
        assert "ts" in entry

    def test_multiple_events(self, tmp_path):
        """Test writing multiple events."""
        events_file = tmp_path / "events.jsonl"
        writer = EventWriter(events_file)

        writer.write_event("starting", 0, "Starting")
        writer.write_event("scrape", 25, "Scraping")
        writer.write_event("complete", 100, "Done")

        lines = events_file.read_text().strip().split("\n")
        assert len(lines) == 3


class TestHeartbeatWriter:
    """Tests for HeartbeatWriter."""

    def test_initial_heartbeat(self, tmp_path):
        """Test that initial heartbeat is written on start."""
        heartbeat_file = tmp_path / "_heartbeat.json"
        spec = JobSpec(
            job_id="test-123",
            deployment="prod",
            execution_id="task-1",
            attempt=1,
            company_name="Test Co",
            company_url="https://test.example",
            mode="full",
        )

        writer = HeartbeatWriter(heartbeat_file, spec)
        writer.start()
        writer.stop()

        assert heartbeat_file.exists()
        content = json.loads(heartbeat_file.read_text())

        assert content["job_id"] == "test-123"
        assert content["execution_id"] == "task-1"
        assert content["attempt"] == 1
        assert "last_heartbeat" in content


class TestTimestampFormatting:
    """Tests for timestamp formatting."""

    def test_utc_now(self):
        """Test that utc_now returns UTC datetime."""
        now = utc_now()
        assert now.tzinfo == timezone.utc

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        dt = datetime(2026, 2, 3, 10, 30, 45, tzinfo=timezone.utc)
        formatted = format_timestamp(dt)
        assert formatted == "2026-02-03T10:30:45Z"
