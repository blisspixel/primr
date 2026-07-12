"""
Tests for JobStore and ResearchJobState.

Task 2: JobStore and concurrency model
- 2.1-2.13: JobStore lifecycle, stage monotonicity, invariants, persistence
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from primr.mcp_server.job_store import (
    ControllerLease,
    ControllerLeaseError,
    JobInProgressError,
    ResearchJobState,
    SingleJobStore,
)
from primr.mcp_server.types import JobStatus, ResearchStage


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class TestResearchJobState:
    """Tests for ResearchJobState dataclass."""

    def test_create_job_state(self):
        """Job state can be created with required fields."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
        )

        assert job.job_id == "test-123"
        assert job.company_name == "Acme Corp"
        assert job.mode == "full"
        assert job.current_stage == ResearchStage.IDLE
        assert job.stage_progress_percent == 0

    def test_heartbeat_updates_timestamp(self):
        """Heartbeat updates last_heartbeat_time."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
        )

        old_time = job.last_heartbeat_time
        job.heartbeat()

        assert job.last_heartbeat_time is not None
        assert job.last_heartbeat_time != old_time

    def test_heartbeat_updates_progress(self):
        """Heartbeat can update progress percentage."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
        )

        job.heartbeat(progress=50)

        assert job.stage_progress_percent == 50

    def test_heartbeat_clamps_progress(self):
        """Heartbeat clamps progress to [0, 100]."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
        )

        job.heartbeat(progress=150)
        assert job.stage_progress_percent == 100

        job.heartbeat(progress=-10)
        assert job.stage_progress_percent == 0


class TestStageProgression:
    """Tests for stage monotonicity (Requirement 2.9)."""

    def test_advance_stage_forward(self):
        """Can advance to later stages."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
        )

        assert job.advance_stage(ResearchStage.ACCEPTED)
        assert job.current_stage == ResearchStage.ACCEPTED

        assert job.advance_stage(ResearchStage.SCRAPING)
        assert job.current_stage == ResearchStage.SCRAPING

    def test_cannot_regress_stage(self):
        """Cannot go back to earlier stages."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.SCRAPING,
        )

        # Try to go back to ACCEPTED
        assert not job.advance_stage(ResearchStage.ACCEPTED)
        assert job.current_stage == ResearchStage.SCRAPING

    def test_can_advance_to_terminal_failed(self):
        """Can always advance to FAILED terminal state."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.SCRAPING,
        )

        assert job.advance_stage(ResearchStage.FAILED)
        assert job.current_stage == ResearchStage.FAILED
        assert job.completion_time is not None

    def test_can_advance_to_terminal_cancelled(self):
        """Can always advance to CANCELLED terminal state."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.DEEP_RESEARCH,
        )

        assert job.advance_stage(ResearchStage.CANCELLED)
        assert job.current_stage == ResearchStage.CANCELLED
        assert job.completion_time is not None

    def test_completion_time_immutable(self):
        """Completion time cannot be changed once set."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
        )

        job.advance_stage(ResearchStage.COMPLETED)
        first_completion = job.completion_time

        # Try to set again via FAILED
        assert not job.advance_stage(ResearchStage.FAILED)

        # The complete terminal outcome and its timestamp are both immutable.
        assert job.current_stage == ResearchStage.COMPLETED
        assert job.completion_time == first_completion

    @pytest.mark.parametrize(
        "terminal_stage",
        [ResearchStage.COMPLETED, ResearchStage.FAILED, ResearchStage.CANCELLED],
    )
    @pytest.mark.parametrize(
        "attempted_stage",
        [
            ResearchStage.WRITING,
            ResearchStage.COMPLETED,
            ResearchStage.FAILED,
            ResearchStage.CANCELLED,
        ],
    )
    def test_terminal_stage_rejects_every_later_transition(
        self,
        terminal_stage,
        attempted_stage,
    ):
        """A terminal outcome cannot be replaced or resumed."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.SCRAPING,
        )
        assert job.advance_stage(terminal_stage)
        completion_time = job.completion_time

        assert not job.advance_stage(attempted_stage)
        assert job.current_stage == terminal_stage
        assert job.completion_time == completion_time

    def test_advance_stage_resets_progress(self):
        """Advancing stage resets progress to specified value."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            stage_progress_percent=75,
        )

        job.advance_stage(ResearchStage.SCRAPING, progress=10)

        assert job.stage_progress_percent == 10


class TestStatusStageConsistency:
    """Tests for status/stage consistency (Requirement 2.10)."""

    def test_idle_status(self):
        """IDLE stage maps to IDLE status."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.IDLE,
        )

        assert job.get_status() == JobStatus.IDLE

    def test_in_progress_status(self):
        """Active stages map to IN_PROGRESS status."""
        for stage in [
            ResearchStage.ACCEPTED,
            ResearchStage.SCRAPING,
            ResearchStage.EXTRACTING,
            ResearchStage.DEEP_RESEARCH,
            ResearchStage.WRITING,
            ResearchStage.QA,
        ]:
            job = ResearchJobState(
                job_id="test-123",
                company_name="Acme Corp",
                mode="full",
                start_time=_utcnow(),
                current_stage=stage,
            )

            assert job.get_status() == JobStatus.IN_PROGRESS, f"Stage {stage} should be IN_PROGRESS"

    def test_completed_status(self):
        """COMPLETED stage maps to COMPLETED status."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.COMPLETED,
        )

        assert job.get_status() == JobStatus.COMPLETED

    def test_failed_status(self):
        """FAILED stage maps to FAILED status."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.FAILED,
        )

        assert job.get_status() == JobStatus.FAILED

    def test_cancelled_status(self):
        """CANCELLED stage maps to CANCELLED status."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            current_stage=ResearchStage.CANCELLED,
        )

        assert job.get_status() == JobStatus.CANCELLED


class TestStuckDetection:
    """Tests for stuck detection (Requirement 2.12)."""

    def test_not_stuck_with_recent_heartbeat(self):
        """Job is not stuck if heartbeat is recent."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            last_heartbeat_time=_utcnow(),
        )

        assert not job.is_possibly_stuck()

    def test_stuck_with_stale_heartbeat(self):
        """Job is stuck if heartbeat is stale."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            last_heartbeat_time=_utcnow() - timedelta(seconds=150),
        )

        assert job.is_possibly_stuck(threshold_seconds=120)

    def test_not_stuck_without_heartbeat(self):
        """Job is not stuck if no heartbeat has been recorded."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=_utcnow(),
            last_heartbeat_time=None,
        )

        assert not job.is_possibly_stuck()


class TestJournalSerialization:
    """Tests for journal serialization (Requirements 19.2, 19.4)."""

    def test_to_journal_dict(self):
        """Job state can be serialized to dict."""
        job = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            owner_client_id="client-456",
            current_stage=ResearchStage.SCRAPING,
            stage_progress_percent=50,
        )
        job.stage_started_at = datetime(2024, 1, 1, 12, 5, 0)
        job.last_heartbeat_time = datetime(2024, 1, 1, 12, 10, 0)

        data = job.to_journal_dict()

        assert data["job_id"] == "test-123"
        assert data["company_name"] == "Acme Corp"
        assert data["mode"] == "full"
        assert data["owner_client_id"] == "client-456"
        assert data["current_stage"] == "scraping"
        assert data["stage_progress_percent"] == 50

    def test_from_journal_dict(self):
        """Job state can be deserialized from dict."""
        data = {
            "job_id": "test-123",
            "company_name": "Acme Corp",
            "mode": "full",
            "start_time": "2024-01-01T12:00:00",
            "owner_client_id": "client-456",
            "current_stage": "scraping",
            "stage_progress_percent": 50,
            "stage_started_at": "2024-01-01T12:05:00",
            "last_heartbeat_time": "2024-01-01T12:10:00",
            "completion_time": None,
            "output_paths": ["/output/report.md"],
            "error_type": None,
            "error_message": None,
            "deep_research_job_id": "dr-789",
        }

        job = ResearchJobState.from_journal_dict(data)

        assert job.job_id == "test-123"
        assert job.company_name == "Acme Corp"
        assert job.current_stage == ResearchStage.SCRAPING
        assert job.deep_research_job_id == "dr-789"

    def test_roundtrip_serialization(self):
        """Job state survives roundtrip serialization."""
        original = ResearchJobState(
            job_id="test-123",
            company_name="Acme Corp",
            mode="full",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            current_stage=ResearchStage.DEEP_RESEARCH,
            stage_progress_percent=75,
        )
        original.error_type = "test_error"
        original.error_message = "Test error message"

        data = original.to_journal_dict()
        restored = ResearchJobState.from_journal_dict(data)

        assert restored.job_id == original.job_id
        assert restored.company_name == original.company_name
        assert restored.current_stage == original.current_stage
        assert restored.stage_progress_percent == original.stage_progress_percent
        assert restored.error_type == original.error_type
        assert restored.error_message == original.error_message


class TestSingleJobStore:
    """Tests for SingleJobStore (Requirements 5.8, 19.1, 19.3, 19.6)."""

    @pytest.fixture
    def temp_journal(self):
        """Create a temporary journal file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_journal.json"

    def test_create_job(self, temp_journal):
        """Can create a new job."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")

        assert job.job_id is not None
        assert job.company_name == "Acme Corp"
        assert job.mode == "full"
        assert job.current_stage == ResearchStage.ACCEPTED

    def test_create_job_with_owner(self, temp_journal):
        """Can create a job with owner_client_id."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full", owner_client_id="client-123")

        assert job.owner_client_id == "client-123"

    def test_create_job_raises_if_in_progress(self, temp_journal):
        """Creating a job while one is in progress raises JobInProgressError."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job1 = store.create("Acme Corp", "full")

        with pytest.raises(JobInProgressError) as exc_info:
            store.create("Other Corp", "deep")

        assert exc_info.value.active_job_id == job1.job_id

    def test_create_job_after_completion(self, temp_journal):
        """Can create a new job after previous one completes."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job1 = store.create("Acme Corp", "full")
        job1.advance_stage(ResearchStage.COMPLETED)
        store.update(job1)

        job2 = store.create("Other Corp", "deep")

        assert job2.job_id != job1.job_id
        assert job2.company_name == "Other Corp"

    def test_get_job_by_id(self, temp_journal):
        """Can retrieve job by ID."""
        store = SingleJobStore(journal_path=str(temp_journal))

        created = store.create("Acme Corp", "full")
        retrieved = store.get(created.job_id)

        assert retrieved is not None
        assert retrieved.job_id == created.job_id

    def test_get_nonexistent_job(self, temp_journal):
        """Getting nonexistent job returns None."""
        store = SingleJobStore(journal_path=str(temp_journal))

        result = store.get("nonexistent-id")

        assert result is None

    def test_get_active_job(self, temp_journal):
        """Can get active (non-terminal) job."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")

        active = store.get_active()

        assert active is not None
        assert active.job_id == job.job_id

    def test_get_active_returns_none_when_completed(self, temp_journal):
        """get_active returns None when job is completed."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        store.update(job)

        active = store.get_active()

        assert active is None

    def test_get_latest_terminal(self, temp_journal):
        """Can get most recent terminal job."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        store.update(job)

        terminal = store.get_latest_terminal()

        assert terminal is not None
        assert terminal.job_id == job.job_id

    def test_update_job(self, temp_journal):
        """Can update job state."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.SCRAPING)
        job.heartbeat(progress=50)
        store.update(job)

        retrieved = store.get(job.job_id)

        assert retrieved.current_stage == ResearchStage.SCRAPING
        assert retrieved.stage_progress_percent == 50

    def test_apply_worker_snapshot_preserves_parent_identity_and_notifies(self, temp_journal):
        """Worker progress applies without granting the worker identity ownership."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full", owner_client_id="client-123")
        canonical_start = job.start_time
        status_event = store._get_or_create_event()
        status_event.clear()

        snapshot = job.to_journal_dict()
        forged_heartbeat = "2099-01-01T00:00:00+00:00"
        snapshot.update(
            {
                "company_name": "Forged Corp",
                "mode": "premium",
                "start_time": "1999-01-01T00:00:00+00:00",
                "owner_client_id": "other-client",
                "current_stage": "scraping",
                "stage_progress_percent": 42,
                "last_heartbeat_time": forged_heartbeat,
                "output_paths": ["output/partial.txt"],
            }
        )

        assert store.apply_worker_snapshot(job.job_id, snapshot)
        applied = store.get(job.job_id)
        assert applied is not None
        assert applied.job_id == job.job_id
        assert applied.company_name == "Acme Corp"
        assert applied.mode == "full"
        assert applied.start_time == canonical_start
        assert applied.owner_client_id == "client-123"
        assert applied.current_stage == ResearchStage.SCRAPING
        assert applied.stage_progress_percent == 42
        assert applied.last_heartbeat_time is not None
        assert applied.last_heartbeat_time.year < 2099
        assert applied.stage_started_at == applied.last_heartbeat_time
        assert applied.output_paths == ["output/partial.txt"]
        assert status_event.is_set()

        persisted = json.loads(temp_journal.read_text(encoding="utf-8"))
        assert persisted["company_name"] == "Acme Corp"
        assert persisted["owner_client_id"] == "client-123"
        assert persisted["current_stage"] == "scraping"

    def test_apply_worker_snapshot_rejects_wrong_job_id(self, temp_journal):
        """A snapshot cannot update a different canonical job."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")
        original_journal = temp_journal.read_text(encoding="utf-8")
        snapshot = job.to_journal_dict()
        snapshot["job_id"] = "other-job"
        snapshot["current_stage"] = "scraping"

        assert not store.apply_worker_snapshot(job.job_id, snapshot)
        assert not store.apply_worker_snapshot("other-job", job.to_journal_dict())
        assert temp_journal.read_text(encoding="utf-8") == original_journal
        assert store.get(job.job_id).current_stage == ResearchStage.ACCEPTED

    @pytest.mark.parametrize(
        "field,value",
        [
            ("stage_progress_percent", "bad"),
            ("stage_progress_percent", 10000),
            ("output_paths", "output/report.md"),
            ("qa_score", -1),
        ],
    )
    def test_apply_worker_snapshot_rejects_malformed_values(
        self,
        temp_journal,
        field,
        value,
    ):
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")
        snapshot = job.to_journal_dict()
        snapshot["current_stage"] = "scraping"
        snapshot[field] = value

        assert not store.apply_worker_snapshot(job.job_id, snapshot)
        assert store.get(job.job_id).current_stage == ResearchStage.ACCEPTED

    def test_apply_worker_snapshot_rejects_stage_and_progress_regressions(self, temp_journal):
        """Stale worker snapshots cannot move stage or same-stage progress backward."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.EXTRACTING, progress=60)
        store.update(job)

        stage_regression = job.to_journal_dict()
        stage_regression["current_stage"] = "scraping"
        stage_regression["stage_progress_percent"] = 100
        assert not store.apply_worker_snapshot(job.job_id, stage_regression)

        progress_regression = job.to_journal_dict()
        progress_regression["stage_progress_percent"] = 59
        assert not store.apply_worker_snapshot(job.job_id, progress_regression)

        current = store.get(job.job_id)
        assert current.current_stage == ResearchStage.EXTRACTING
        assert current.stage_progress_percent == 60

    def test_apply_worker_snapshot_requires_explicit_terminal_permission(self, temp_journal):
        """Exactly one explicitly allowed worker terminal outcome may be committed."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")
        terminal = job.to_journal_dict()
        terminal["current_stage"] = "completed"
        worker_completion = datetime(2020, 1, 1, tzinfo=timezone.utc)
        terminal["completion_time"] = worker_completion.isoformat()
        terminal["last_heartbeat_time"] = worker_completion.isoformat()
        terminal["output_paths"] = ["output/report.md"]

        assert not store.apply_worker_snapshot(job.job_id, terminal)
        assert store.get(job.job_id).current_stage == ResearchStage.ACCEPTED

        assert store.apply_worker_snapshot(job.job_id, terminal, allow_terminal=True)
        completed = store.get(job.job_id)
        assert completed.current_stage == ResearchStage.COMPLETED
        assert completed.completion_time is not None
        assert completed.completion_time > worker_completion
        assert completed.last_heartbeat_time == completed.completion_time
        assert completed.stage_started_at == completed.completion_time
        first_completion = completed.completion_time

        late_failure = completed.to_journal_dict()
        late_failure["current_stage"] = "failed"
        late_failure["error_type"] = "late_worker_failure"
        assert not store.apply_worker_snapshot(job.job_id, late_failure, allow_terminal=True)

        unchanged = store.get(job.job_id)
        assert unchanged.current_stage == ResearchStage.COMPLETED
        assert unchanged.completion_time == first_completion
        assert unchanged.error_type is None

        persisted = json.loads(temp_journal.read_text(encoding="utf-8"))
        assert persisted["current_stage"] == "completed"

    def test_apply_worker_snapshot_rejects_nonterminal_after_parent_terminal(self, temp_journal):
        """A late progress snapshot cannot reopen a terminal parent job."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")
        late_progress = job.to_journal_dict()
        late_progress["current_stage"] = "writing"
        job.advance_stage(ResearchStage.CANCELLED)
        store.update(job)

        assert not store.apply_worker_snapshot(job.job_id, late_progress)
        assert store.get(job.job_id).current_stage == ResearchStage.CANCELLED

    def test_mark_shutdown(self, temp_journal):
        """mark_shutdown marks active job as FAILED."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")
        store.mark_shutdown()

        retrieved = store.get(job.job_id)

        assert retrieved.current_stage == ResearchStage.FAILED
        assert retrieved.error_type == "server_shutdown"
        assert retrieved.completion_time is not None

    def test_reconcile_interrupted_job_is_idempotent(self, temp_journal):
        """Restart reconciliation closes an active journal exactly once."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full", owner_client_id="client-1")
        job.advance_stage(ResearchStage.SCRAPING)
        store.update(job)

        assert store.reconcile_interrupted_job() == job.job_id
        reconciled = store.get(job.job_id)
        assert reconciled.current_stage == ResearchStage.FAILED
        assert reconciled.error_type == "server_restart"
        completion_time = reconciled.completion_time

        assert store.reconcile_interrupted_job() is None
        assert store.get(job.job_id).completion_time == completion_time


def test_controller_lease_excludes_second_owner_and_can_be_reacquired(tmp_path):
    journal_path = tmp_path / "journal.json"
    first = ControllerLease(journal_path)
    second = ControllerLease(journal_path)

    first.acquire()
    try:
        with pytest.raises(ControllerLeaseError, match="already owns"):
            second.acquire()
    finally:
        first.close()

    second.acquire()
    assert second.acquired is True
    second.close()
    second.close()


class TestJournalPersistence:
    """Tests for journal persistence (Requirements 19.3, 19.4, 19.6)."""

    @pytest.fixture
    def temp_journal(self):
        """Create a temporary journal file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_journal.json"

    def test_journal_created_on_job_create(self, temp_journal):
        """Journal file is created when job is created."""
        store = SingleJobStore(journal_path=str(temp_journal))

        store.create("Acme Corp", "full")

        assert temp_journal.exists()

    def test_journal_contains_job_data(self, temp_journal):
        """Journal file contains serialized job data."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")

        with open(temp_journal) as f:
            data = json.load(f)

        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme Corp"

    def test_journal_updated_on_update(self, temp_journal):
        """Journal file is updated when job is updated."""
        store = SingleJobStore(journal_path=str(temp_journal))

        job = store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.SCRAPING)
        store.update(job)

        with open(temp_journal) as f:
            data = json.load(f)

        assert data["current_stage"] == "scraping"

    def test_journal_loaded_on_startup(self, temp_journal):
        """Journal is loaded when store is created."""
        # Create first store and job
        store1 = SingleJobStore(journal_path=str(temp_journal))
        job = store1.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.DEEP_RESEARCH)
        store1.update(job)

        # Create second store (simulates restart)
        store2 = SingleJobStore(journal_path=str(temp_journal))

        # Should have the job from journal
        recovered = store2.get(job.job_id)

        assert recovered is not None
        assert recovered.company_name == "Acme Corp"
        assert recovered.current_stage == ResearchStage.DEEP_RESEARCH

    def test_corrupted_journal_starts_fresh(self, temp_journal):
        """Corrupted journal results in fresh start."""
        # Write corrupted data
        temp_journal.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_journal, "w") as f:
            f.write("not valid json {{{")

        # Should not raise, starts fresh
        store = SingleJobStore(journal_path=str(temp_journal))

        assert store.get_active() is None

    def test_atomic_write(self, temp_journal):
        """Journal write is atomic (uses temp file + rename)."""
        store = SingleJobStore(journal_path=str(temp_journal))

        store.create("Acme Corp", "full")

        # Temp file should not exist after write
        temp_file = temp_journal.with_suffix(".tmp")
        assert not temp_file.exists()

        # Journal should exist
        assert temp_journal.exists()

    def test_clear_removes_journal(self, temp_journal):
        """clear() removes the journal file."""
        store = SingleJobStore(journal_path=str(temp_journal))

        store.create("Acme Corp", "full")
        assert temp_journal.exists()

        store.clear()

        assert not temp_journal.exists()
        assert store.get_active() is None


class TestWaitForStatusChange:
    """Tests for wait_for_status_change (MCP Progress Subscriptions v1.9.0)."""

    @pytest.fixture
    def temp_journal(self):
        """Create a temporary journal file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_journal.json"

    @pytest.mark.asyncio
    async def test_wait_returns_immediately_for_changed_status(self, temp_journal):
        """wait_for_status_change returns immediately if status already changed."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")

        # Advance to SCRAPING
        job.advance_stage(ResearchStage.SCRAPING)
        store.update(job)

        # Wait for change from ACCEPTED (already changed)
        changed, new_status = await store.wait_for_status_change(
            job_id=job.job_id,
            current_status=JobStatus.IDLE,  # Already past this
            timeout_seconds=1.0,
        )

        assert changed is True
        assert new_status == JobStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_wait_returns_immediately_for_terminal_job(self, temp_journal):
        """wait_for_status_change returns immediately for terminal jobs."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")

        # Complete the job
        job.advance_stage(ResearchStage.COMPLETED)
        store.update(job)

        # Wait for change
        changed, new_status = await store.wait_for_status_change(
            job_id=job.job_id,
            current_status=JobStatus.IN_PROGRESS,
            timeout_seconds=1.0,
        )

        assert changed is True
        assert new_status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_wait_returns_none_for_unknown_job(self, temp_journal):
        """wait_for_status_change returns (False, None) for unknown job."""
        store = SingleJobStore(journal_path=str(temp_journal))

        changed, new_status = await store.wait_for_status_change(
            job_id="nonexistent-job",
            current_status=JobStatus.IN_PROGRESS,
            timeout_seconds=1.0,
        )

        assert changed is False
        assert new_status is None

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_wait_times_out_when_no_change(self, temp_journal):
        """wait_for_status_change times out when status doesn't change."""
        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")

        # Wait for change from current status with short timeout
        # Use 1 second to give enough time for internal loop iterations
        changed, new_status = await store.wait_for_status_change(
            job_id=job.job_id,
            current_status=JobStatus.IN_PROGRESS,
            timeout_seconds=1.0,
        )

        assert changed is False
        assert new_status == JobStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_wait_detects_update_notification(self, temp_journal):
        """wait_for_status_change detects status change from notification."""
        import asyncio

        store = SingleJobStore(journal_path=str(temp_journal))
        job = store.create("Acme Corp", "full")

        async def update_job_after_delay():
            await asyncio.sleep(0.2)
            job.advance_stage(ResearchStage.COMPLETED)
            store.update(job)

        # Start the update in the background
        update_task = asyncio.create_task(update_job_after_delay())

        # Wait for change
        changed, new_status = await store.wait_for_status_change(
            job_id=job.job_id,
            current_status=JobStatus.IN_PROGRESS,
            timeout_seconds=5.0,
        )

        await update_task

        assert changed is True
        assert new_status == JobStatus.COMPLETED
