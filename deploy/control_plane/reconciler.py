"""
State Reconciler - Reconciliation logic for stuck/orphaned jobs.

This module provides reconciliation for jobs that get stuck:
- Jobs RUNNING beyond max_duration → mark FAILED (timeout_reconciled)
- Jobs RUNNING but manifest exists → update status from manifest
- Jobs CANCEL_REQUESTED beyond grace period → mark FAILED (cancellation_timeout)
- If runner couldn't write manifest, annotate with no_runner_manifest: true

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from deploy.control_plane.job_store import (
    JobRecord,
    JobStatus,
    JobStore,
    format_timestamp,
    utc_now,
)

if TYPE_CHECKING:
    from deploy.storage import ArtifactStore

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationConfig:
    """Configuration for reconciliation."""
    # Maximum job duration before timeout (default 2 hours)
    max_duration_seconds: int = 7200
    # Grace period for cancellation (default 5 minutes)
    cancellation_grace_seconds: int = 300
    # Heartbeat staleness threshold (default 10 minutes)
    heartbeat_stale_seconds: int = 600


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""
    jobs_checked: int = 0
    timeout_reconciled: int = 0
    manifest_reconciled: int = 0
    cancellation_timeout: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobs_checked": self.jobs_checked,
            "timeout_reconciled": self.timeout_reconciled,
            "manifest_reconciled": self.manifest_reconciled,
            "cancellation_timeout": self.cancellation_timeout,
            "errors": self.errors,
        }


class Reconciler:
    """
    State reconciler for stuck jobs.

    Runs periodically to detect and fix jobs that are stuck in
    intermediate states due to runner failures or network issues.
    """

    def __init__(
        self,
        job_store: JobStore,
        artifact_store: ArtifactStore,
        config: ReconciliationConfig | None = None,
    ) -> None:
        """
        Initialize reconciler.

        Args:
            job_store: Job state store
            artifact_store: Artifact store for manifest checks
            config: Reconciliation configuration
        """
        self.job_store = job_store
        self.artifact_store = artifact_store
        self.config = config or ReconciliationConfig()

    def reconcile(self) -> ReconciliationResult:
        """
        Run reconciliation for all stuck jobs.

        Returns:
            ReconciliationResult with counts of actions taken
        """
        result = ReconciliationResult()
        now = utc_now()

        # Get all jobs in active states
        active_statuses = [
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ]
        active_jobs = self.job_store.query_by_status(active_statuses)

        for job in active_jobs:
            result.jobs_checked += 1

            try:
                if job.status == JobStatus.RUNNING:
                    self._reconcile_running_job(job, now, result)
                elif job.status == JobStatus.CANCEL_REQUESTED:
                    self._reconcile_cancel_requested_job(job, now, result)
            except Exception as e:
                logger.error(f"Error reconciling job {job.job_id}: {e}")
                result.errors += 1

        logger.info(f"Reconciliation complete: {result.to_dict()}")
        return result

    def _reconcile_running_job(
        self,
        job: JobRecord,
        now: datetime,
        result: ReconciliationResult,
    ) -> None:
        """
        Reconcile a job in RUNNING state.

        Checks:
        1. If manifest exists → update status from manifest
        2. If running too long → mark as timeout
        """
        # Check if manifest exists (job actually completed)
        manifest = self.artifact_store.get_manifest(job.job_id)
        if manifest:
            # Job completed but status wasn't updated
            logger.info(f"Job {job.job_id} has manifest, updating status to {manifest.status}")

            new_status = self._status_from_manifest(manifest.status)
            job.status = new_status
            job.timing.completed_at = manifest.timing.completed_at
            job.error_message = manifest.error
            self.job_store.update(job)

            result.manifest_reconciled += 1
            return

        # Check if job has been running too long
        started_at = self._parse_timestamp(job.timing.started_at)
        if started_at:
            duration = (now - started_at).total_seconds()
            if duration > self.config.max_duration_seconds:
                logger.warning(f"Job {job.job_id} timed out after {duration:.0f}s")

                job.status = JobStatus.FAILED
                job.timing.completed_at = format_timestamp(now)
                job.error_message = "timeout_reconciled"
                job.no_runner_manifest = True
                self.job_store.update(job)

                result.timeout_reconciled += 1
                return

        # Check heartbeat staleness
        heartbeat = self._get_heartbeat(job.job_id)
        if heartbeat:
            last_heartbeat = self._parse_timestamp(heartbeat.get("last_heartbeat"))
            if last_heartbeat:
                staleness = (now - last_heartbeat).total_seconds()
                if staleness > self.config.heartbeat_stale_seconds:
                    logger.warning(f"Job {job.job_id} heartbeat stale for {staleness:.0f}s")
                    # Don't fail yet, just log - runner might recover

    def _reconcile_cancel_requested_job(
        self,
        job: JobRecord,
        now: datetime,
        result: ReconciliationResult,
    ) -> None:
        """
        Reconcile a job in CANCEL_REQUESTED state.

        Checks:
        1. If manifest exists → update status from manifest
        2. If grace period exceeded → mark as cancellation timeout
        """
        # Check if manifest exists (runner wrote CANCELLED manifest)
        manifest = self.artifact_store.get_manifest(job.job_id)
        if manifest:
            logger.info(f"Job {job.job_id} has manifest after cancel request, status: {manifest.status}")

            new_status = self._status_from_manifest(manifest.status)
            job.status = new_status
            job.timing.completed_at = manifest.timing.completed_at
            job.error_message = manifest.error
            self.job_store.update(job)

            result.manifest_reconciled += 1
            return

        # Check if grace period exceeded
        # Use started_at as proxy for when cancel was requested
        # (In production, you'd track cancel_requested_at separately)
        started_at = self._parse_timestamp(job.timing.started_at)
        if started_at:
            duration = (now - started_at).total_seconds()
            if duration > self.config.max_duration_seconds + self.config.cancellation_grace_seconds:
                logger.warning(f"Job {job.job_id} cancellation timed out")

                job.status = JobStatus.FAILED
                job.timing.completed_at = format_timestamp(now)
                job.error_message = "cancellation_timeout"
                job.no_runner_manifest = True
                self.job_store.update(job)

                result.cancellation_timeout += 1

    def _status_from_manifest(self, manifest_status: str) -> JobStatus:
        """Convert manifest status string to JobStatus enum."""
        status_map = {
            "SUCCEEDED": JobStatus.SUCCEEDED,
            "FAILED": JobStatus.FAILED,
            "CANCELLED": JobStatus.CANCELLED,
        }
        return status_map.get(manifest_status, JobStatus.FAILED)

    def _parse_timestamp(self, ts: str | None) -> datetime | None:
        """Parse ISO 8601 timestamp string."""
        if not ts:
            return None
        try:
            # Handle both Z and +00:00 formats
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    def _get_heartbeat(self, job_id: str) -> dict[str, Any] | None:
        """Get heartbeat data for a job."""
        import json

        data = self.artifact_store.get(f"{job_id}/_heartbeat.json")
        if not data:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None


def create_reconciler_handler(
    job_store: JobStore,
    artifact_store: ArtifactStore,
    config: ReconciliationConfig | None = None,
) -> callable:
    """
    Create a handler function for serverless invocation.

    Returns a function that can be used as:
    - AWS Lambda handler
    - Azure Function handler
    - GCP Cloud Function handler

    Args:
        job_store: Job state store
        artifact_store: Artifact store
        config: Reconciliation configuration

    Returns:
        Handler function
    """
    reconciler = Reconciler(job_store, artifact_store, config)

    def handler(event: Any = None, context: Any = None) -> dict[str, Any]:
        """
        Reconciliation handler for serverless invocation.

        Args:
            event: Event data (ignored)
            context: Execution context (ignored)

        Returns:
            Reconciliation result as dict
        """
        result = reconciler.reconcile()
        return {
            "statusCode": 200,
            "body": result.to_dict(),
        }

    return handler
