"""Tests for A2A task store adapter."""

import pytest

a2a = pytest.importorskip("a2a")

from a2a.types import TaskState

from primr.a2a.task_store import PrimrTaskStore, _job_to_task_state
from primr.a2a.types import A2ATaskMapping
from primr.mcp_server.job_store import SingleJobStore
from primr.mcp_server.types import ResearchStage


class TestStageToStateMapping:
    """Tests for Primr stage → A2A state mapping."""

    def test_idle_maps_to_submitted(self):
        job = _make_job(stage=ResearchStage.IDLE)
        assert _job_to_task_state(job) == TaskState.submitted

    def test_accepted_maps_to_submitted(self):
        job = _make_job(stage=ResearchStage.ACCEPTED)
        assert _job_to_task_state(job) == TaskState.submitted

    def test_scraping_maps_to_working(self):
        job = _make_job(stage=ResearchStage.SCRAPING)
        assert _job_to_task_state(job) == TaskState.working

    def test_completed_maps_to_completed(self):
        job = _make_job(stage=ResearchStage.COMPLETED)
        assert _job_to_task_state(job) == TaskState.completed

    def test_failed_maps_to_failed(self):
        job = _make_job(stage=ResearchStage.FAILED)
        assert _job_to_task_state(job) == TaskState.failed

    def test_cancelled_maps_to_canceled(self):
        job = _make_job(stage=ResearchStage.CANCELLED)
        assert _job_to_task_state(job) == TaskState.canceled


class TestPrimrTaskStore:
    """Tests for PrimrTaskStore."""

    @pytest.fixture
    def store(self, tmp_path):
        journal_path = str(tmp_path / "journal.json")
        job_store = SingleJobStore(journal_path=journal_path)
        return PrimrTaskStore(job_store), job_store

    def test_register_and_get_mapping(self, store):
        task_store, _ = store
        mapping = A2ATaskMapping(task_id="t-1", job_id="j-1", skill_id="check")
        task_store.register_mapping(mapping)
        result = task_store.get_mapping("t-1")
        assert result is not None
        assert result.job_id == "j-1"

    def test_get_mapping_missing(self, store):
        task_store, _ = store
        assert task_store.get_mapping("nonexistent") is None

    def test_get_job_id(self, store):
        task_store, _ = store
        mapping = A2ATaskMapping(task_id="t-1", job_id="j-1", skill_id="check")
        task_store.register_mapping(mapping)
        assert task_store.get_job_id("t-1") == "j-1"
        assert task_store.get_job_id("t-2") is None

    @pytest.mark.asyncio
    async def test_get_task_with_job(self, store):
        """Get task returns A2A task when job exists."""
        task_store, job_store = store
        job = job_store.create(company_name="Acme", mode="full", owner_client_id="test")
        mapping = A2ATaskMapping(task_id="t-1", job_id=job.job_id, skill_id="research")
        task_store.register_mapping(mapping)

        task = await task_store.get("t-1")
        assert task is not None
        assert task.id == "t-1"
        assert task.status.state in (TaskState.submitted, TaskState.working)

    @pytest.mark.asyncio
    async def test_get_task_missing_mapping(self, store):
        """Get task returns None for unknown task ID."""
        task_store, _ = store
        assert await task_store.get("unknown") is None

    @pytest.mark.asyncio
    async def test_save_is_noop(self, store):
        """Save is a no-op since job store is source of truth."""
        task_store, job_store = store
        job = job_store.create(company_name="Acme", mode="full", owner_client_id="test")
        mapping = A2ATaskMapping(task_id="t-1", job_id=job.job_id, skill_id="research")
        task_store.register_mapping(mapping)

        task = await task_store.get("t-1")
        await task_store.save(task)  # Should not raise

    @pytest.mark.asyncio
    async def test_delete_removes_mapping(self, store):
        task_store, _ = store
        mapping = A2ATaskMapping(task_id="t-1", job_id="j-1", skill_id="check")
        task_store.register_mapping(mapping)
        await task_store.delete("t-1")
        assert task_store.get_mapping("t-1") is None


def _make_job(stage=ResearchStage.IDLE):
    """Create a minimal ResearchJobState for testing."""
    from datetime import datetime, timezone

    from primr.mcp_server.job_store import ResearchJobState
    job = ResearchJobState(
        job_id="test-job-001",
        company_name="Test",
        mode="full",
        start_time=datetime.now(timezone.utc),
        owner_client_id="test",
    )
    if stage != ResearchStage.IDLE:
        job.advance_stage(stage)
    return job
