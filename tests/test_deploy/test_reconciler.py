"""
Tests for state reconciliation.

Tests:
- Timeout detection
- Manifest-based status update
- Cancellation timeout handling

Requirements: 12.2, 12.3, 12.4
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta

import pytest

from deploy.control_plane.job_store import (
    CostEstimate,
    InMemoryJobStore,
    JobInputs,
    JobRecord,
    JobStatus,
    JobTiming,
    format_timestamp,
    utc_now,
)
from deploy.control_plane.reconciler import (
    Reconciler,
    ReconciliationConfig,
    ReconciliationResult,
)
from deploy.manifest import ArtifactMeta, JobCost, JobManifest, JobVersions
from deploy.storage import LocalStore


def create_test_job(
    job_id: str,
    status: JobStatus,
    started_at: datetime | None = None,
) -> JobRecord:
    """Create a test job record."""
    now = utc_now()
    return JobRecord(
        job_id=job_id,
        deployment="test",
        idempotency_key=f"key-{job_id}",
        api_key_hash="test_key",
        canonical_hash=f"hash-{job_id}",
        status=status,
        inputs=JobInputs(company_name="Test", company_url="https://test.com", mode="scrape"),
        expected_artifacts=["test.txt"],
        estimate=CostEstimate(cost_usd=0.1, duration_minutes=5),
        timing=JobTiming(
            submitted_at=format_timestamp(now - timedelta(hours=1)),
            started_at=format_timestamp(started_at)
            if started_at
            else format_timestamp(now - timedelta(minutes=30)),
        ),
    )


def create_test_manifest(
    job_id: str,
    status: str,
    completed_at: datetime | None = None,
    error: str | None = None,
) -> JobManifest:
    """Create a test manifest."""
    from deploy.manifest import JobInputs, JobTiming

    now = utc_now()
    return JobManifest(
        job_id=job_id,
        idempotency_key=f"key-{job_id}",
        deployment="test",
        execution_id="exec-123",
        attempt=1,
        status=status,
        inputs=JobInputs(
            company_name="Test Co",
            company_url="https://test.com",
            mode="scrape",
        ),
        expected_artifacts=["test.txt"],
        timing=JobTiming(
            submitted_at=format_timestamp(now - timedelta(hours=1)),
            started_at=format_timestamp(now - timedelta(minutes=30)),
            completed_at=format_timestamp(completed_at) if completed_at else format_timestamp(now),
        ),
        cost=JobCost(estimated_usd=0.1),
        artifacts={
            "test.txt": ArtifactMeta(
                size_bytes=100,
                checksum_sha256="abc123",
            ),
        },
        versions=JobVersions(primr="1.0.0", runner="1.0.0"),
        error=error,
    )


class TestReconciler:
    """Tests for the Reconciler class."""

    @pytest.fixture
    def job_store(self) -> InMemoryJobStore:
        """Create a test job store."""
        return InMemoryJobStore()

    @pytest.fixture
    def artifact_store(self) -> LocalStore:
        """Create a test artifact store."""
        temp_dir = tempfile.mkdtemp(prefix="test_artifacts_")
        return LocalStore(temp_dir, "test")

    @pytest.fixture
    def reconciler(self, job_store: InMemoryJobStore, artifact_store: LocalStore) -> Reconciler:
        """Create a test reconciler."""
        config = ReconciliationConfig(
            max_duration_seconds=3600,  # 1 hour
            cancellation_grace_seconds=300,  # 5 minutes
            heartbeat_stale_seconds=600,  # 10 minutes
        )
        return Reconciler(job_store, artifact_store, config)

    def test_reconcile_empty_store(self, reconciler: Reconciler) -> None:
        """Reconciliation with no jobs returns zero counts."""
        result = reconciler.reconcile()

        assert result.jobs_checked == 0
        assert result.timeout_reconciled == 0
        assert result.manifest_reconciled == 0
        assert result.cancellation_timeout == 0
        assert result.errors == 0

    def test_timeout_detection(
        self,
        reconciler: Reconciler,
        job_store: InMemoryJobStore,
    ) -> None:
        """Jobs running beyond max_duration are marked as timeout."""
        # Create a job that started 2 hours ago (beyond 1 hour limit)
        old_start = utc_now() - timedelta(hours=2)
        job = create_test_job("timeout-job", JobStatus.RUNNING, started_at=old_start)
        job_store.put_if_not_exists(job)

        result = reconciler.reconcile()

        assert result.jobs_checked == 1
        assert result.timeout_reconciled == 1

        # Verify job was updated
        updated = job_store.get("timeout-job")
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.error_message == "timeout_reconciled"
        assert updated.no_runner_manifest is True

    def test_manifest_reconciliation(
        self,
        reconciler: Reconciler,
        job_store: InMemoryJobStore,
        artifact_store: LocalStore,
    ) -> None:
        """Jobs with manifest are updated to manifest status."""
        # Create a running job
        job = create_test_job("manifest-job", JobStatus.RUNNING)
        job_store.put_if_not_exists(job)

        # Write a manifest indicating success
        manifest = create_test_manifest("manifest-job", "SUCCEEDED")
        artifact_store.put_manifest("manifest-job", manifest)

        result = reconciler.reconcile()

        assert result.jobs_checked == 1
        assert result.manifest_reconciled == 1

        # Verify job was updated
        updated = job_store.get("manifest-job")
        assert updated is not None
        assert updated.status == JobStatus.SUCCEEDED

    def test_cancellation_timeout(
        self,
        reconciler: Reconciler,
        job_store: InMemoryJobStore,
    ) -> None:
        """Jobs in CANCEL_REQUESTED beyond grace period are marked as timeout."""
        # Create a job that was cancel-requested long ago
        old_start = utc_now() - timedelta(hours=2)
        job = create_test_job("cancel-job", JobStatus.CANCEL_REQUESTED, started_at=old_start)
        job_store.put_if_not_exists(job)

        result = reconciler.reconcile()

        assert result.jobs_checked == 1
        assert result.cancellation_timeout == 1

        # Verify job was updated
        updated = job_store.get("cancel-job")
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.error_message == "cancellation_timeout"
        assert updated.no_runner_manifest is True

    def test_cancel_with_manifest(
        self,
        reconciler: Reconciler,
        job_store: InMemoryJobStore,
        artifact_store: LocalStore,
    ) -> None:
        """Jobs in CANCEL_REQUESTED with manifest are updated from manifest."""
        # Create a cancel-requested job
        job = create_test_job("cancel-manifest-job", JobStatus.CANCEL_REQUESTED)
        job_store.put_if_not_exists(job)

        # Write a CANCELLED manifest
        manifest = create_test_manifest("cancel-manifest-job", "CANCELLED")
        artifact_store.put_manifest("cancel-manifest-job", manifest)

        result = reconciler.reconcile()

        assert result.jobs_checked == 1
        assert result.manifest_reconciled == 1

        # Verify job was updated
        updated = job_store.get("cancel-manifest-job")
        assert updated is not None
        assert updated.status == JobStatus.CANCELLED

    def test_healthy_job_not_modified(
        self,
        reconciler: Reconciler,
        job_store: InMemoryJobStore,
    ) -> None:
        """Jobs within time limits are not modified."""
        # Create a job that started recently
        recent_start = utc_now() - timedelta(minutes=10)
        job = create_test_job("healthy-job", JobStatus.RUNNING, started_at=recent_start)
        job_store.put_if_not_exists(job)

        result = reconciler.reconcile()

        assert result.jobs_checked == 1
        assert result.timeout_reconciled == 0
        assert result.manifest_reconciled == 0

        # Verify job was not modified
        updated = job_store.get("healthy-job")
        assert updated is not None
        assert updated.status == JobStatus.RUNNING

    def test_queued_jobs_not_checked(
        self,
        reconciler: Reconciler,
        job_store: InMemoryJobStore,
    ) -> None:
        """Jobs in QUEUED state are not checked."""
        job = create_test_job("queued-job", JobStatus.QUEUED)
        job_store.put_if_not_exists(job)

        result = reconciler.reconcile()

        # QUEUED jobs are not in active_statuses
        assert result.jobs_checked == 0

    def test_result_to_dict(self) -> None:
        """ReconciliationResult can be serialized to dict."""
        result = ReconciliationResult(
            jobs_checked=10,
            timeout_reconciled=2,
            manifest_reconciled=3,
            cancellation_timeout=1,
            errors=0,
        )

        d = result.to_dict()
        assert d["jobs_checked"] == 10
        assert d["timeout_reconciled"] == 2
        assert d["manifest_reconciled"] == 3
        assert d["cancellation_timeout"] == 1
        assert d["errors"] == 0
