"""
Job state management with persistence.

This module provides the JobStore abstraction for managing research job state,
including persistence to a JSON journal for restart safety.

Requirements: 2.2, 5.8, 5.9, 19.1-19.6, 20.2
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from primr.mcp_server.types import JobStatus, ResearchStage


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class JobInProgressError(Exception):
    """
    Raised when attempting to create a job while one is in progress.

    Requirements: 5.11
    """

    def __init__(self, active_job_id: str):
        self.active_job_id = active_job_id
        super().__init__(f"Job {active_job_id} already in progress")


@dataclass
class ResearchJobState:
    """
    Tracks a single research job state.

    Implements state machine invariants:
    - status and current_stage MUST be consistent
    - completion_time is immutable once set
    - stage_progress_percent bounded [0..100]
    - Stage transitions are monotonic (cannot regress)

    Requirements: 2.9, 2.10, 2.11, Job State Machine invariants
    """

    job_id: str
    company_name: str
    mode: str
    start_time: datetime
    owner_client_id: str | None = None  # None in stdio mode (implicit ownership)
    current_stage: ResearchStage = ResearchStage.IDLE
    stage_progress_percent: int = 0
    stage_started_at: datetime | None = None
    last_heartbeat_time: datetime | None = None
    completion_time: datetime | None = None
    output_paths: list[str] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    deep_research_job_id: str | None = None  # For recovery after restart
    qa_score: int | None = None  # QA score (0-100) when available

    # Stage ordering for monotonic progression
    _STAGE_ORDER: list[ResearchStage] = field(
        default_factory=lambda: [
            ResearchStage.IDLE,
            ResearchStage.ACCEPTED,
            ResearchStage.SCRAPING,
            ResearchStage.EXTRACTING,
            ResearchStage.DEEP_RESEARCH,
            ResearchStage.WRITING,
            ResearchStage.QA,
            ResearchStage.COMPLETED,
        ],
        repr=False,
    )

    # Best-effort stage duration heuristics (minutes)
    _STAGE_EXPECTED_MINUTES: dict[ResearchStage, int] = field(
        default_factory=lambda: {
            ResearchStage.ACCEPTED: 1,
            ResearchStage.SCRAPING: 8,
            ResearchStage.EXTRACTING: 2,
            ResearchStage.DEEP_RESEARCH: 15,
            ResearchStage.WRITING: 10,
            ResearchStage.QA: 3,
        },
        repr=False,
    )

    def heartbeat(self, progress: int | None = None) -> None:
        """
        Update heartbeat timestamp and optionally progress.

        Args:
            progress: Optional progress percentage (0-100)

        Requirements: 2.12
        """
        self.last_heartbeat_time = _utcnow()
        if progress is not None:
            self.stage_progress_percent = min(100, max(0, progress))

    def advance_stage(self, new_stage: ResearchStage, progress: int = 0) -> bool:
        """
        Advance to new stage. Returns False if regression attempted.

        Stages are monotonic - cannot go backwards except to terminal states.

        Args:
            new_stage: The stage to advance to
            progress: Initial progress for the new stage (default 0)

        Returns:
            True if stage was advanced, False if regression was attempted

        Requirements: 2.9, Job State Machine invariants
        """
        # Terminal states can always be set
        if new_stage in (ResearchStage.FAILED, ResearchStage.CANCELLED):
            self.current_stage = new_stage
            if self.completion_time is None:  # Immutable once set
                self.completion_time = _utcnow()
            self.last_heartbeat_time = _utcnow()
            return True

        try:
            current_idx = self._STAGE_ORDER.index(self.current_stage)
            new_idx = self._STAGE_ORDER.index(new_stage)
            if new_idx > current_idx:
                self.current_stage = new_stage
                self.stage_progress_percent = min(100, max(0, progress))
                self.stage_started_at = _utcnow()
                self.last_heartbeat_time = _utcnow()
                if new_stage == ResearchStage.COMPLETED:
                    if self.completion_time is None:  # Immutable once set
                        self.completion_time = _utcnow()
                return True
        except ValueError:
            pass  # new_stage not in ResearchStage — return False below
        return False

    def get_status(self) -> JobStatus:
        """
        Get the high-level job status from current stage.

        Returns:
            JobStatus corresponding to current_stage

        Requirements: 2.10 (status/stage consistency)
        """
        if self.current_stage == ResearchStage.IDLE:
            return JobStatus.IDLE
        elif self.current_stage == ResearchStage.COMPLETED:
            return JobStatus.COMPLETED
        elif self.current_stage == ResearchStage.FAILED:
            return JobStatus.FAILED
        elif self.current_stage == ResearchStage.CANCELLED:
            return JobStatus.CANCELLED
        else:
            return JobStatus.IN_PROGRESS

    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.current_stage in (
            ResearchStage.COMPLETED,
            ResearchStage.FAILED,
            ResearchStage.CANCELLED,
        )

    def is_possibly_stuck(self, threshold_seconds: int = 120) -> bool:
        """
        Check if job appears stuck (no heartbeat within threshold).

        Args:
            threshold_seconds: Seconds without heartbeat to consider stuck

        Returns:
            True if heartbeat is stale beyond threshold

        Requirements: 2.12
        """
        if self.last_heartbeat_time is None:
            return False
        elapsed = (_utcnow() - self.last_heartbeat_time).total_seconds()
        return elapsed > threshold_seconds

    def get_expected_minutes(self) -> int | None:
        """Get expected duration for current stage in minutes."""
        return self._STAGE_EXPECTED_MINUTES.get(self.current_stage)

    def to_journal_dict(self) -> dict:
        """
        Serialize to dict for JSON journal persistence.

        Requirements: 19.2
        """
        return {
            "job_id": self.job_id,
            "company_name": self.company_name,
            "mode": self.mode,
            "start_time": self.start_time.isoformat(),
            "owner_client_id": self.owner_client_id,
            "current_stage": self.current_stage.value,
            "stage_progress_percent": self.stage_progress_percent,
            "stage_started_at": self.stage_started_at.isoformat()
            if self.stage_started_at
            else None,
            "last_heartbeat_time": self.last_heartbeat_time.isoformat()
            if self.last_heartbeat_time
            else None,
            "completion_time": self.completion_time.isoformat() if self.completion_time else None,
            "output_paths": self.output_paths,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "deep_research_job_id": self.deep_research_job_id,
            "qa_score": self.qa_score,
        }

    @classmethod
    def from_journal_dict(cls, data: dict) -> "ResearchJobState":
        """
        Deserialize from journal dict.

        Requirements: 19.4
        """
        job = cls(
            job_id=data["job_id"],
            company_name=data["company_name"],
            mode=data["mode"],
            start_time=datetime.fromisoformat(data["start_time"]),
        )
        job.owner_client_id = data.get("owner_client_id")
        job.current_stage = ResearchStage(data["current_stage"])
        job.stage_progress_percent = data.get("stage_progress_percent", 0)
        job.stage_started_at = (
            datetime.fromisoformat(data["stage_started_at"])
            if data.get("stage_started_at")
            else None
        )
        job.last_heartbeat_time = (
            datetime.fromisoformat(data["last_heartbeat_time"])
            if data.get("last_heartbeat_time")
            else None
        )
        job.completion_time = (
            datetime.fromisoformat(data["completion_time"]) if data.get("completion_time") else None
        )
        job.output_paths = data.get("output_paths", [])
        job.error_type = data.get("error_type")
        job.error_message = data.get("error_message")
        job.deep_research_job_id = data.get("deep_research_job_id")
        job.qa_score = data.get("qa_score")
        return job


class JobStore(ABC):
    """
    Abstraction for job storage.

    v1 uses SingleJobStore (in-memory, one job).
    Future: MultiJobStore backed by sqlite/redis for concurrent jobs.

    Requirements: 2.1, 2.2
    """

    @abstractmethod
    def create(
        self,
        company_name: str,
        mode: str,
        owner_client_id: str | None = None,
    ) -> ResearchJobState:
        """
        Create a new job.

        Args:
            company_name: Name of the company being researched
            mode: Research mode (scrape, deep, full)
            owner_client_id: Client ID for job ownership (HTTP mode)

        Returns:
            New ResearchJobState

        Raises:
            JobInProgressError: If a job is already in progress (single-job model)
        """

    @abstractmethod
    def get(self, job_id: str) -> ResearchJobState | None:
        """Get job by ID."""

    @abstractmethod
    def get_by_id(self, job_id: str) -> ResearchJobState | None:
        """Get job by ID (alias for get)."""

    @abstractmethod
    def get_active(self) -> ResearchJobState | None:
        """Get currently active job, if any."""

    @abstractmethod
    def get_latest_terminal(self) -> ResearchJobState | None:
        """Get most recent terminal job by completion_time."""

    @abstractmethod
    def update(self, job: ResearchJobState) -> None:
        """Update job state."""

    @abstractmethod
    def mark_shutdown(self) -> None:
        """
        Mark active job as failed due to shutdown.

        Requirements: 20.2
        """

    @abstractmethod
    async def wait_for_status_change(
        self,
        job_id: str,
        current_status: JobStatus,
        timeout_seconds: float = 60.0,
    ) -> tuple[bool, JobStatus | None]:
        """
        Wait for job status to change from current_status.

        Args:
            job_id: The job ID to monitor
            current_status: The current status to wait for change from
            timeout_seconds: Maximum time to wait

        Returns:
            Tuple of (changed, new_status). If changed is False, timeout occurred.
        """


class SingleJobStore(JobStore):
    """
    In-memory single-job store for v1 with journal persistence.

    Thread-safe operations with Lock.
    Persists to JSON journal for restart safety.

    Requirements: 5.8, 19.1, 19.3, 19.6
    """

    DEFAULT_JOURNAL_PATH = "output/.mcp_job_journal.json"

    def __init__(self, journal_path: str | None = None):
        self._job: ResearchJobState | None = None
        self._lock = Lock()
        self._journal_path = Path(journal_path or self.DEFAULT_JOURNAL_PATH)
        self._status_change_event: asyncio.Event | None = None
        self._load_journal()

    def _load_journal(self) -> None:
        """
        Load job state from journal on startup.

        Requirements: 19.4
        """
        if self._journal_path.exists():
            try:
                with open(self._journal_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._job = ResearchJobState.from_journal_dict(data)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                import logging

                logging.getLogger(__name__).warning(
                    "Corrupted job journal at %s, starting fresh: %s", self._journal_path, e
                )
                self._job = None

    def _save_journal(self) -> None:
        """
        Persist job state to journal (atomic write).

        Requirements: 19.3, 19.6
        """
        if self._job is None:
            # missing_ok=True avoids a TOCTOU FileNotFoundError if the
            # journal disappears between exists() and unlink() — e.g.
            # operator manually wiping output/ during a shutdown handler.
            self._journal_path.unlink(missing_ok=True)
            return

        self._journal_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._journal_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self._job.to_journal_dict(), f, indent=2)
        temp_path.replace(self._journal_path)  # Atomic rename

    def create(
        self,
        company_name: str,
        mode: str,
        owner_client_id: str | None = None,
    ) -> ResearchJobState:
        """
        Create a new job.

        Requirements: 5.8 (job_in_progress error)
        """
        with self._lock:
            if self._job and not self._job.is_terminal():
                raise JobInProgressError(self._job.job_id)

            self._job = ResearchJobState(
                job_id=str(uuid.uuid4()),
                company_name=company_name,
                mode=mode,
                start_time=_utcnow(),
                owner_client_id=owner_client_id,
                current_stage=ResearchStage.ACCEPTED,
                stage_started_at=_utcnow(),
                last_heartbeat_time=_utcnow(),
            )
            self._save_journal()
            return self._job

    def get(self, job_id: str) -> ResearchJobState | None:
        """Get job by ID."""
        with self._lock:
            if self._job and self._job.job_id == job_id:
                return self._job
            return None

    def get_by_id(self, job_id: str) -> ResearchJobState | None:
        """Get job by ID (alias for get)."""
        return self.get(job_id)

    def get_active(self) -> ResearchJobState | None:
        """Get currently active job, if any."""
        with self._lock:
            if self._job and not self._job.is_terminal():
                return self._job
            return None

    def get_latest_terminal(self) -> ResearchJobState | None:
        """Get most recent terminal job by completion_time."""
        with self._lock:
            if self._job and self._job.is_terminal():
                return self._job
            return None

    def update(self, job: ResearchJobState) -> None:
        """Update job state."""
        with self._lock:
            if self._job and self._job.job_id == job.job_id:
                self._job = job
                self._save_journal()
                # Notify waiters of state change
                self._notify_status_change()

    def mark_shutdown(self) -> None:
        """
        Mark active job as failed due to shutdown.

        Requirements: 20.2
        """
        with self._lock:
            if self._job and not self._job.is_terminal():
                self._job.current_stage = ResearchStage.FAILED
                self._job.error_type = "server_shutdown"
                self._job.error_message = "Server shutdown while job in progress"
                self._job.completion_time = _utcnow()
                self._save_journal()
        # Notify outside the lock to avoid potential deadlock
        self._notify_status_change()

    def clear(self) -> None:
        """Clear job state (for testing)."""
        with self._lock:
            self._job = None
            # Same TOCTOU fix as _save_journal — use missing_ok rather
            # than exists()+unlink().
            self._journal_path.unlink(missing_ok=True)

    def _notify_status_change(self) -> None:
        """Notify waiters that status has changed."""
        if self._status_change_event is not None:
            self._status_change_event.set()

    def _get_or_create_event(self) -> asyncio.Event:
        """Get or create the status change event."""
        if self._status_change_event is None:
            self._status_change_event = asyncio.Event()
        return self._status_change_event

    async def wait_for_status_change(
        self,
        job_id: str,
        current_status: JobStatus,
        timeout_seconds: float = 60.0,
    ) -> tuple[bool, JobStatus | None]:
        """
        Wait for job status to change from current_status.

        Uses asyncio.Event for efficient notification-based waiting
        instead of polling.

        Args:
            job_id: The job ID to monitor
            current_status: The current status to wait for change from
            timeout_seconds: Maximum time to wait

        Returns:
            Tuple of (changed, new_status). If changed is False, timeout occurred.
        """
        event = self._get_or_create_event()
        event.clear()

        deadline = asyncio.get_running_loop().time() + timeout_seconds

        while True:
            # Check current status
            job = self.get(job_id)
            if job is None:
                return (False, None)

            new_status = job.get_status()
            if new_status != current_status:
                return (True, new_status)

            # Calculate remaining time
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return (False, current_status)

            # Wait for notification or timeout
            try:
                await asyncio.wait_for(event.wait(), timeout=min(remaining, 5.0))
            except Exception as exc:
                # asyncio.wait_for timeout behavior varies by runtime and can surface
                # different TimeoutError classes.
                is_asyncio_timeout = (
                    exc.__class__.__name__ == "TimeoutError"
                    and exc.__class__.__module__.startswith("asyncio")
                )
                if isinstance(exc, TimeoutError) or is_asyncio_timeout:
                    pass
                else:
                    raise
            finally:
                event.clear()  # Reset for next wait (must clear after timeout too)
