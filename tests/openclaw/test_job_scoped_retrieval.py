"""Unit tests for job-scoped retrieval.

Tests FR-6.1, FR-6.2, SR-2.1, SR-2.3
"""

import json
from unittest.mock import MagicMock

import pytest

from primr.mcp_server.job_store import JobInProgressError, SingleJobStore
from primr.mcp_server.types import ResearchStage


class TestJobIdInLatestResponse:
    """Test job_id is included in primr://output/latest response."""

    def test_latest_output_includes_job_id(self, tmp_path) -> None:
        """FR-6.1: Response includes job_id field."""
        # Create a mock job store with a completed job
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))
        job = job_store.create("Test Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        job.output_paths = [str(tmp_path / "report.md")]
        job_store.update(job)

        # Create test report in a real output directory
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        report_path = output_dir / "report.md"
        report_path.write_text("# Test Report")

        # Create mock mcp_server
        mock_server = MagicMock()
        mock_server.job_store = job_store

        # Import and call the resource handler
        # Change to tmp_path so Path("output") resolves correctly
        import os

        from primr.mcp_server.resources import _read_latest_output

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _read_latest_output(mock_server, "primr://output/latest")
        finally:
            os.chdir(original_cwd)

        assert len(result) == 1
        data = json.loads(result[0].content)
        assert "job_id" in data

    def test_latest_output_job_id_matches_completed_job(self, tmp_path) -> None:
        """FR-6.1: job_id matches the completed job."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))
        job = job_store.create("Test Corp", "full")
        expected_job_id = job.job_id
        job.advance_stage(ResearchStage.COMPLETED)
        job_store.update(job)

        mock_server = MagicMock()
        mock_server.job_store = job_store

        # Change to tmp_path so Path("output") resolves correctly
        import os

        from primr.mcp_server.resources import _read_latest_output

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = _read_latest_output(mock_server, "primr://output/latest")
        finally:
            os.chdir(original_cwd)

        data = json.loads(result[0].content)
        assert data["job_id"] == expected_job_id


class TestOutputByJobResource:
    """Test primr://output/by_job/{job_id} resource."""

    def test_by_job_returns_correct_report(self, tmp_path) -> None:
        """FR-6.2: by_job resource returns correct report for job_id."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))
        job = job_store.create("Test Corp", "full")
        job_id = job.job_id
        job.advance_stage(ResearchStage.COMPLETED)
        job.output_paths = [str(tmp_path / "report.md")]
        job_store.update(job)

        # Create test report
        report_path = tmp_path / "report.md"
        report_path.write_text("# Test Report Content")

        mock_server = MagicMock()
        mock_server.job_store = job_store

        from primr.mcp_server.resources import _read_output_by_job

        result = _read_output_by_job(mock_server, f"primr://output/by_job/{job_id}")

        assert len(result) == 1
        data = json.loads(result[0].content)
        assert data["job_id"] == job_id
        assert "report_path" in data
        assert data["company_name"] == "Test Corp"

    def test_by_job_returns_404_for_unknown_job(self, tmp_path) -> None:
        """FR-6.2: by_job returns error for unknown job_id."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))

        mock_server = MagicMock()
        mock_server.job_store = job_store

        from primr.mcp_server.resources import _read_output_by_job

        result = _read_output_by_job(mock_server, "primr://output/by_job/nonexistent-id")

        assert len(result) == 1
        data = json.loads(result[0].content)
        assert data["error"] == "job_not_found"
        assert "nonexistent-id" in data["message"]

    def test_by_job_returns_no_output_for_incomplete_job(self, tmp_path) -> None:
        """FR-6.2: by_job returns error for job without output."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))
        job = job_store.create("Test Corp", "full")
        job_id = job.job_id
        # Don't complete the job, leave it in progress

        mock_server = MagicMock()
        mock_server.job_store = job_store

        from primr.mcp_server.resources import _read_output_by_job

        result = _read_output_by_job(mock_server, f"primr://output/by_job/{job_id}")

        assert len(result) == 1
        data = json.loads(result[0].content)
        assert data["error"] == "no_output"


class TestSingleJobConcurrency:
    """Test single-job concurrency enforcement."""

    def test_research_while_in_progress_returns_error(self, tmp_path) -> None:
        """SR-2.1: research_company while in_progress returns job_in_progress error."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))

        # Create first job (in progress)
        job1 = job_store.create("First Corp", "full")
        assert job1 is not None

        # Try to create second job - should fail
        with pytest.raises(JobInProgressError) as exc_info:
            job_store.create("Second Corp", "full")

        assert exc_info.value.active_job_id == job1.job_id

    def test_active_job_continues_unaffected(self, tmp_path) -> None:
        """SR-2.1: Active job continues unaffected after rejection."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))

        # Create first job
        job1 = job_store.create("First Corp", "full")
        original_job_id = job1.job_id

        # Try to create second job (will fail)
        try:
            job_store.create("Second Corp", "full")
        except JobInProgressError:
            pass

        # Verify first job is still active and unchanged
        active = job_store.get_active()
        assert active is not None
        assert active.job_id == original_job_id
        assert active.company_name == "First Corp"

    def test_no_job_queuing(self, tmp_path) -> None:
        """SR-2.3: Concurrent requests are rejected, not queued."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))

        # Create first job
        job_store.create("First Corp", "full")

        # Multiple attempts should all fail immediately
        for i in range(3):
            with pytest.raises(JobInProgressError):
                job_store.create(f"Company {i}", "full")

        # Still only one job
        active = job_store.get_active()
        assert active.company_name == "First Corp"

    def test_can_create_after_completion(self, tmp_path) -> None:
        """Can create new job after previous completes."""
        job_store = SingleJobStore(journal_path=str(tmp_path / "journal.json"))

        # Create and complete first job
        job1 = job_store.create("First Corp", "full")
        job1.advance_stage(ResearchStage.COMPLETED)
        job_store.update(job1)

        # Should be able to create new job
        job2 = job_store.create("Second Corp", "full")
        assert job2 is not None
        assert job2.company_name == "Second Corp"
