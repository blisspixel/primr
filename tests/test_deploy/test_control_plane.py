"""
Unit tests for the control plane service.

Tests cover:
- Idempotency logic with identical inputs
- Idempotency rejection with different inputs (409)
- Deployment namespace prevents cross-environment collisions
- Concurrent submission handling
- Quota enforcement
- Job state transitions including cancellation
- /status returns last_event
- /results returns 425 when no manifest

Requirements: 3.4, 3.5, 3.6, 3.7, 3.11, 3.17, 4.5, 4.6
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from deploy.control_plane.api import app, configure_app
from deploy.control_plane.cancellation import CancellationResult, CancellationService
from deploy.control_plane.cost_governor import (
    CostGovernor,
    QuotaConfig,
    QuotaExceededError,
    estimate_cost,
)
from deploy.control_plane.job_store import (
    ConditionalCheckFailedError,
    CosmosStore,
    CostEstimate,
    InMemoryJobStore,
    JobInputs,
    JobRecord,
    JobStatus,
    JobTiming,
    canonicalize_inputs,
    get_expected_artifacts,
    hash_api_key,
    hash_inputs,
    hash_job_id,
)
from deploy.control_plane.queue import InMemoryQueue, QueueMessage
from deploy.storage import LocalStore

if TYPE_CHECKING:
    from pathlib import Path

CONTROL_PLANE_TEST_TOKEN = "unit-test-token-bravo"

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def job_store() -> InMemoryJobStore:
    """Create a fresh in-memory job store."""
    return InMemoryJobStore()


@pytest.fixture
def queue() -> InMemoryQueue:
    """Create a fresh in-memory queue."""
    return InMemoryQueue()


@pytest.fixture
def artifact_store(tmp_path: Path) -> LocalStore:
    """Create a local artifact store."""
    return LocalStore(tmp_path, deployment="test")


@pytest.fixture
def cost_governor(job_store: InMemoryJobStore) -> CostGovernor:
    """Create a cost governor."""
    return CostGovernor(job_store)


@pytest.fixture
def cancellation_service(job_store: InMemoryJobStore) -> CancellationService:
    """Create a cancellation service."""
    return CancellationService(job_store)


@pytest.fixture
def client(
    job_store: InMemoryJobStore,
    queue: InMemoryQueue,
    artifact_store: LocalStore,
    cost_governor: CostGovernor,
    cancellation_service: CancellationService,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Create a test client with configured app.

    Registers the bearer token the tests use so the get_api_key dependency
    (which now fails closed when no verifier is configured) accepts it.
    """
    monkeypatch.setenv("PRIMR_CONTROL_PLANE_API_KEYS", CONTROL_PLANE_TEST_TOKEN)
    configure_app(
        job_store=job_store,
        queue=queue,
        artifact_store=artifact_store,
        cost_governor=cost_governor,
        cancellation_service=cancellation_service,
        deployment="test",
    )
    return TestClient(app)


# =============================================================================
# JOB STORE TESTS
# =============================================================================


class TestJobStore:
    """Tests for InMemoryJobStore."""

    def test_put_and_get(self, job_store: InMemoryJobStore) -> None:
        """Test basic put and get operations."""
        job = JobRecord(
            job_id="test-123",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.QUEUED,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=["report.docx"],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )

        job_store.put_if_not_exists(job)
        retrieved = job_store.get("test-123")

        assert retrieved is not None
        assert retrieved.job_id == "test-123"
        assert retrieved.status == JobStatus.QUEUED

    def test_put_if_not_exists_fails_on_duplicate(self, job_store: InMemoryJobStore) -> None:
        """Test that put_if_not_exists fails if job exists."""
        job = JobRecord(
            job_id="test-123",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.QUEUED,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )

        job_store.put_if_not_exists(job)

        with pytest.raises(ConditionalCheckFailedError):
            job_store.put_if_not_exists(job)

    def test_update(self, job_store: InMemoryJobStore) -> None:
        """Test job update."""
        job = JobRecord(
            job_id="test-123",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.QUEUED,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )

        job_store.put_if_not_exists(job)

        job.status = JobStatus.RUNNING
        job_store.update(job)

        retrieved = job_store.get("test-123")
        assert retrieved is not None
        assert retrieved.status == JobStatus.RUNNING

    def test_query_by_status(self, job_store: InMemoryJobStore) -> None:
        """Test querying jobs by status."""
        for i, status in enumerate([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED]):
            job = JobRecord(
                job_id=f"test-{i}",
                deployment="test",
                idempotency_key=f"key-{i}",
                api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
                canonical_hash=f"hash-{i}",
                status=status,
                inputs=JobInputs(
                    company_name="Acme",
                    company_url="https://acme.example",
                    mode="full",
                ),
                expected_artifacts=[],
                estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
                timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
            )
            job_store.put_if_not_exists(job)

        running = job_store.query_by_status([JobStatus.RUNNING])
        assert len(running) == 1
        assert running[0].job_id == "test-1"

    def test_cosmos_query_by_status_uses_parameters(self) -> None:
        """Cosmos status queries keep status values out of the SQL text."""

        job = JobRecord(
            job_id="test-1",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.RUNNING,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )

        class FakeContainer:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def query_items(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(kwargs)
                item = job.to_dict()
                item["id"] = job.job_id
                return [item]

        container = FakeContainer()
        store = CosmosStore(
            database_name="db",
            container_name="jobs",
            connection_string="AccountEndpoint=https://example;AccountKey=test;",
            container=container,
        )

        results = store.query_by_status([JobStatus.RUNNING, JobStatus.QUEUED])

        assert [result.job_id for result in results] == ["test-1"]
        call = container.calls[0]
        assert call["query"] == "SELECT * FROM c WHERE ARRAY_CONTAINS(@statuses, c.status)"
        assert "RUNNING" not in str(call["query"])
        assert call["parameters"] == [
            {"name": "@statuses", "value": ["RUNNING", "QUEUED"]},
        ]


# =============================================================================
# IDEMPOTENCY TESTS
# =============================================================================


class TestIdempotency:
    """Tests for idempotency logic."""

    def test_same_inputs_returns_same_job_id(self, client: TestClient) -> None:
        """Same (deployment, idempotency_key, api_key) + same inputs returns same job_id."""
        # Validates: Requirements 3.5
        request = {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "mode": "full",
            "idempotency_key": "test-key-1",
            "approve": True,
        }

        # First submission
        response1 = client.post(
            "/submit",
            json=request,
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response1.status_code == 200
        data1 = response1.json()

        # Second submission with same inputs
        response2 = client.post(
            "/submit",
            json=request,
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response2.status_code == 200
        data2 = response2.json()

        # Should return same job_id
        assert data1["job_id"] == data2["job_id"]
        assert data2["is_existing"] is True

    def test_different_inputs_returns_409(self, client: TestClient) -> None:
        """Same idempotency_key + different inputs returns 409."""
        # Validates: Requirements 3.6
        request1 = {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "mode": "full",
            "idempotency_key": "test-key-2",
            "approve": True,
        }

        # First submission
        response1 = client.post(
            "/submit",
            json=request1,
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response1.status_code == 200

        # Second submission with different inputs but same idempotency_key
        request2 = {
            "company_name": "Different Corp",  # Different!
            "company_url": "https://different.example",  # Different!
            "mode": "full",
            "idempotency_key": "test-key-2",  # Same key
            "approve": True,
        }

        response2 = client.post(
            "/submit",
            json=request2,
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )

        # Should return 409 Conflict
        assert response2.status_code == 409

    def test_different_deployment_returns_different_job_id(self) -> None:
        """Different deployment + same idempotency_key returns different job_id."""
        # Validates: Requirements 3.7
        idempotency_key = "same-key"
        api_key = "same-api-key"

        job_id_dev = hash_job_id("dev", idempotency_key, api_key)
        job_id_prod = hash_job_id("prod", idempotency_key, api_key)

        assert job_id_dev != job_id_prod

    def test_different_api_key_returns_different_job_id(self) -> None:
        """Different api_key + same idempotency_key returns different job_id."""
        idempotency_key = "same-key"
        deployment = "prod"

        job_id_1 = hash_job_id(deployment, idempotency_key, "api-key-1")
        job_id_2 = hash_job_id(deployment, idempotency_key, "api-key-2")

        assert job_id_1 != job_id_2


# =============================================================================
# CONCURRENT SUBMISSION TESTS
# =============================================================================


class TestConcurrentSubmission:
    """Tests for concurrent submission handling."""

    def test_concurrent_submissions_one_wins(self, job_store: InMemoryJobStore) -> None:
        """Concurrent submissions should result in only one job created."""
        # Validates: Requirements 3.8
        results: list[tuple[bool, str | None]] = []
        errors: list[Exception] = []

        def submit_job(idx: int) -> None:
            try:
                job = JobRecord(
                    job_id="concurrent-test",
                    deployment="test",
                    idempotency_key="key-1",
                    api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
                    canonical_hash="hash-1",
                    status=JobStatus.QUEUED,
                    inputs=JobInputs(
                        company_name="Acme",
                        company_url="https://acme.example",
                        mode="full",
                    ),
                    expected_artifacts=[],
                    estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
                    timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
                )
                job_store.put_if_not_exists(job)
                results.append((True, job.job_id))
            except ConditionalCheckFailedError:
                results.append((False, None))
            except Exception as e:
                errors.append(e)

        # Start multiple threads
        threads = [threading.Thread(target=submit_job, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one should succeed
        assert len(errors) == 0
        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]

        assert len(successes) == 1
        assert len(failures) == 9


# =============================================================================
# QUOTA ENFORCEMENT TESTS
# =============================================================================


class TestQuotaEnforcement:
    """Tests for quota enforcement."""

    def test_quota_exceeded_concurrent_jobs(
        self,
        job_store: InMemoryJobStore,
        cost_governor: CostGovernor,
    ) -> None:
        """Quota should be enforced for concurrent jobs."""
        # Validates: Requirements 4.5
        api_key_hash = "sha256:test"

        # Set low quota
        cost_governor.set_quota(api_key_hash, QuotaConfig(max_concurrent_jobs=2))

        # Create 2 active jobs
        for i in range(2):
            job = JobRecord(
                job_id=f"job-{i}",
                deployment="test",
                idempotency_key=f"key-{i}",
                api_key_hash=api_key_hash,
                canonical_hash=f"hash-{i}",
                status=JobStatus.RUNNING,
                inputs=JobInputs(
                    company_name="Acme",
                    company_url="https://acme.example",
                    mode="full",
                ),
                expected_artifacts=[],
                estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
                timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
            )
            job_store.put_if_not_exists(job)

        # Third job should exceed quota
        estimate = CostEstimate(cost_usd=1.0, duration_minutes=30)

        with pytest.raises(QuotaExceededError) as exc_info:
            cost_governor.check_quota(api_key_hash, estimate)

        assert "concurrent jobs" in str(exc_info.value).lower()

    def test_quota_exceeded_daily_cost(
        self,
        job_store: InMemoryJobStore,
        cost_governor: CostGovernor,
    ) -> None:
        """Quota should be enforced for daily cost."""
        # Validates: Requirements 4.6
        api_key_hash = "sha256:test"

        # Set low daily cost quota
        cost_governor.set_quota(api_key_hash, QuotaConfig(max_daily_cost_usd=5.0))

        # Record some cost
        cost_governor.record_job_cost(api_key_hash, 4.5)

        # New job with cost that would exceed daily limit
        estimate = CostEstimate(cost_usd=1.0, duration_minutes=30)

        with pytest.raises(QuotaExceededError) as exc_info:
            cost_governor.check_quota(api_key_hash, estimate)

        assert "daily cost" in str(exc_info.value).lower()

    def test_quota_returns_429(self, client: TestClient, cost_governor: CostGovernor) -> None:
        """API should return 429 when quota exceeded."""
        api_key_hash = hash_api_key(CONTROL_PLANE_TEST_TOKEN)

        # Set very low quota
        cost_governor.set_quota(api_key_hash, QuotaConfig(max_concurrent_jobs=0))

        request = {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "mode": "full",
            "idempotency_key": "quota-test",
            "approve": True,
        }

        response = client.post(
            "/submit",
            json=request,
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )

        assert response.status_code == 429


# =============================================================================
# JOB STATE TRANSITION TESTS
# =============================================================================


class TestJobStateTransitions:
    """Tests for job state transitions including cancellation."""

    def test_queued_to_cancelled(
        self,
        job_store: InMemoryJobStore,
        cancellation_service: CancellationService,
    ) -> None:
        """QUEUED job should transition immediately to CANCELLED."""
        # Validates: Requirements 3.13
        job = JobRecord(
            job_id="cancel-test-1",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.QUEUED,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )
        job_store.put_if_not_exists(job)

        result = cancellation_service.cancel_job("cancel-test-1")

        assert result.result == CancellationResult.CANCELLED
        assert result.status == JobStatus.CANCELLED

        # Verify job was updated
        updated = job_store.get("cancel-test-1")
        assert updated is not None
        assert updated.status == JobStatus.CANCELLED

    def test_running_to_cancel_requested(
        self,
        job_store: InMemoryJobStore,
    ) -> None:
        """RUNNING job should transition to CANCEL_REQUESTED."""
        # Validates: Requirements 3.14
        job = JobRecord(
            job_id="cancel-test-2",
            deployment="test",
            idempotency_key="key-2",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-2",
            status=JobStatus.RUNNING,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
            execution_id="task-123",
        )
        job_store.put_if_not_exists(job)

        # Use a provider that returns False (stop pending)
        class PendingStopProvider:
            def stop_job(self, execution_id: str) -> bool:
                return False

        service = CancellationService(job_store, PendingStopProvider())
        result = service.cancel_job("cancel-test-2")

        assert result.result == CancellationResult.CANCEL_REQUESTED
        assert result.status == JobStatus.CANCEL_REQUESTED

    def test_completed_job_cannot_be_cancelled(
        self,
        job_store: InMemoryJobStore,
        cancellation_service: CancellationService,
    ) -> None:
        """Completed jobs should not be cancellable."""
        job = JobRecord(
            job_id="cancel-test-3",
            deployment="test",
            idempotency_key="key-3",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-3",
            status=JobStatus.SUCCEEDED,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )
        job_store.put_if_not_exists(job)

        result = cancellation_service.cancel_job("cancel-test-3")

        assert result.result == CancellationResult.ALREADY_COMPLETED

    def test_pending_approval_to_queued(
        self, client: TestClient, job_store: InMemoryJobStore
    ) -> None:
        """PENDING_APPROVAL job should transition to QUEUED on approval."""
        # Create a pending job
        request = {
            "company_name": "Acme Corp",
            "company_url": "https://acme.example",
            "mode": "full",
            "idempotency_key": "approval-test",
            "approve": False,  # Don't auto-approve
        }

        response = client.post(
            "/submit",
            json=request,
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING_APPROVAL"

        job_id = data["job_id"]

        # Approve the job (now requires owner auth)
        response = client.post(
            f"/approve/{job_id}",
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 200

        # Verify status changed
        job = job_store.get(job_id)
        assert job is not None
        assert job.status == JobStatus.QUEUED


# =============================================================================
# STATUS ENDPOINT TESTS
# =============================================================================


class TestStatusEndpoint:
    """Tests for /status endpoint."""

    def test_status_returns_404_for_unknown_job(self, client: TestClient) -> None:
        """Status should return 404 for unknown job."""
        # Validates: Requirements 3.10
        response = client.get(
            "/status/unknown-job-id",
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 404

    def test_status_returns_last_event(
        self,
        client: TestClient,
        job_store: InMemoryJobStore,
        artifact_store: LocalStore,
    ) -> None:
        """Status should include last_event from events.jsonl."""
        # Validates: Requirements 3.11
        # Create a job
        job = JobRecord(
            job_id="status-test-1",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.RUNNING,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )
        job_store.put_if_not_exists(job)

        # Write events.jsonl
        events = [
            {"ts": "2024-01-01T00:01:00Z", "stage": "scrape", "percent": 20, "message": "Scraping"},
            {
                "ts": "2024-01-01T00:02:00Z",
                "stage": "insights",
                "percent": 50,
                "message": "Extracting",
            },
        ]
        events_content = "\n".join(json.dumps(e) for e in events)
        artifact_store.put("status-test-1/events.jsonl", events_content.encode())

        # Get status
        response = client.get(
            "/status/status-test-1",
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["last_event"] is not None
        assert data["last_event"]["stage"] == "insights"
        assert data["last_event"]["percent"] == 50


# =============================================================================
# RESULTS ENDPOINT TESTS
# =============================================================================


class TestResultsEndpoint:
    """Tests for /results endpoint."""

    def test_results_returns_404_for_unknown_job(self, client: TestClient) -> None:
        """Results should return 404 for unknown job."""
        # Validates: Requirements 3.16
        response = client.get(
            "/results/unknown-job-id",
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 404

    def test_results_returns_425_when_no_manifest(
        self,
        client: TestClient,
        job_store: InMemoryJobStore,
    ) -> None:
        """Results should return 425 when job exists but no manifest."""
        # Validates: Requirements 3.17
        # Create a job without manifest
        job = JobRecord(
            job_id="results-test-1",
            deployment="test",
            idempotency_key="key-1",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-1",
            status=JobStatus.RUNNING,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=[],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )
        job_store.put_if_not_exists(job)

        # Get results (no manifest exists)
        response = client.get(
            "/results/results-test-1",
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 425

    def test_results_returns_manifest_and_presigned_urls(
        self,
        client: TestClient,
        job_store: InMemoryJobStore,
        artifact_store: LocalStore,
    ) -> None:
        """Results should return manifest and presigned URLs when complete."""
        from deploy.manifest import ArtifactMeta, JobCost, JobManifest, JobVersions
        from deploy.manifest import JobInputs as ManifestInputs
        from deploy.manifest import JobTiming as ManifestTiming

        # Create a job
        job = JobRecord(
            job_id="results-test-2",
            deployment="test",
            idempotency_key="key-2",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            canonical_hash="hash-2",
            status=JobStatus.SUCCEEDED,
            inputs=JobInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=["report.txt"],
            estimate=CostEstimate(cost_usd=1.0, duration_minutes=30),
            timing=JobTiming(submitted_at="2024-01-01T00:00:00Z"),
        )
        job_store.put_if_not_exists(job)

        # Write artifact
        artifact_store.put("results-test-2/report.txt", b"Test report content")

        # Write manifest
        manifest = JobManifest(
            job_id="results-test-2",
            idempotency_key="key-2",
            deployment="test",
            execution_id="exec-1",
            attempt=1,
            status="SUCCEEDED",
            inputs=ManifestInputs(
                company_name="Acme",
                company_url="https://acme.example",
                mode="full",
            ),
            expected_artifacts=["report.txt"],
            timing=ManifestTiming(
                submitted_at="2024-01-01T00:00:00Z",
                completed_at="2024-01-01T00:30:00Z",
            ),
            cost=JobCost(estimated_usd=1.0),
            artifacts={"report.txt": ArtifactMeta(size_bytes=19, checksum_sha256="abc123")},
            versions=JobVersions(primr="1.0.0", runner="1.0.0"),
        )
        artifact_store.put_manifest("results-test-2", manifest)

        # Get results
        response = client.get(
            "/results/results-test-2",
            headers={"Authorization": f"Bearer {CONTROL_PLANE_TEST_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["job_id"] == "results-test-2"
        assert data["status"] == "SUCCEEDED"
        assert "report.txt" in data["artifacts"]
        assert "presigned_url" in data["artifacts"]["report.txt"]


# =============================================================================
# CANONICALIZATION TESTS
# =============================================================================


class TestCanonicalization:
    """Tests for input canonicalization."""

    def test_url_normalization(self) -> None:
        """URLs should be normalized consistently."""
        inputs1 = canonicalize_inputs(
            company_name="Acme",
            company_url="https://ACME.EXAMPLE/path/",
            mode="full",
        )
        inputs2 = canonicalize_inputs(
            company_name="Acme",
            company_url="https://acme.example/path",
            mode="full",
        )

        assert inputs1.company_url == inputs2.company_url
        assert hash_inputs(inputs1) == hash_inputs(inputs2)

    def test_whitespace_stripping(self) -> None:
        """Company name whitespace should be stripped."""
        inputs1 = canonicalize_inputs(
            company_name="  Acme Corp  ",
            company_url="https://acme.example",
            mode="full",
        )
        inputs2 = canonicalize_inputs(
            company_name="Acme Corp",
            company_url="https://acme.example",
            mode="full",
        )

        assert inputs1.company_name == inputs2.company_name
        assert hash_inputs(inputs1) == hash_inputs(inputs2)

    def test_options_sorting(self) -> None:
        """Options should be sorted for consistent hashing."""
        inputs1 = canonicalize_inputs(
            company_name="Acme",
            company_url="https://acme.example",
            mode="full",
            options={"b": 2, "a": 1},
        )
        inputs2 = canonicalize_inputs(
            company_name="Acme",
            company_url="https://acme.example",
            mode="full",
            options={"a": 1, "b": 2},
        )

        assert hash_inputs(inputs1) == hash_inputs(inputs2)


# =============================================================================
# QUEUE TESTS
# =============================================================================


class TestQueue:
    """Tests for InMemoryQueue."""

    def test_enqueue_dequeue(self, queue: InMemoryQueue) -> None:
        """Test basic enqueue and dequeue."""
        message = QueueMessage(
            job_id="test-job",
            deployment="test",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            inputs={"company_name": "Acme"},
            enqueued_at="2024-01-01T00:00:00Z",
        )

        queue.enqueue(message)

        messages = queue.dequeue(max_messages=1)
        assert len(messages) == 1
        assert messages[0].job_id == "test-job"

    def test_visibility_timeout(self, queue: InMemoryQueue) -> None:
        """Messages should become visible again after timeout."""
        message = QueueMessage(
            job_id="test-job",
            deployment="test",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            inputs={"company_name": "Acme"},
            enqueued_at="2024-01-01T00:00:00Z",
        )

        queue.enqueue(message)

        # Dequeue with very short timeout
        messages = queue.dequeue(max_messages=1, visibility_timeout=0)
        assert len(messages) == 1

        # Should be visible again immediately
        messages = queue.dequeue(max_messages=1)
        assert len(messages) == 1

    def test_delete_removes_message(self, queue: InMemoryQueue) -> None:
        """Deleted messages should not reappear."""
        message = QueueMessage(
            job_id="test-job",
            deployment="test",
            api_key_hash=hash_api_key(CONTROL_PLANE_TEST_TOKEN),
            inputs={"company_name": "Acme"},
            enqueued_at="2024-01-01T00:00:00Z",
        )

        queue.enqueue(message)

        messages = queue.dequeue(max_messages=1, visibility_timeout=0)
        assert len(messages) == 1

        queue.delete(messages[0].receipt_handle)

        # Should not be visible again
        messages = queue.dequeue(max_messages=1)
        assert len(messages) == 0


# =============================================================================
# COST ESTIMATION TESTS
# =============================================================================


class TestCostEstimation:
    """Tests for cost estimation."""

    def test_scrape_mode_estimate(self) -> None:
        """Scrape mode should have lowest cost estimate."""
        estimate = estimate_cost("scrape")
        assert estimate.cost_usd <= 0.10
        assert estimate.duration_minutes <= 15

    def test_deep_mode_estimate(self) -> None:
        """Deep mode should have moderate cost estimate."""
        estimate = estimate_cost("deep")
        assert 0.50 <= estimate.cost_usd <= 3.00
        assert estimate.duration_minutes <= 20

    def test_full_mode_estimate(self) -> None:
        """Full mode should have highest cost estimate."""
        estimate = estimate_cost("full")
        assert estimate.cost_usd >= 1.00
        assert estimate.duration_minutes >= 30


# =============================================================================
# EXPECTED ARTIFACTS TESTS
# =============================================================================


class TestExpectedArtifacts:
    """Tests for expected artifacts by mode."""

    def test_scrape_mode_artifacts(self) -> None:
        """Scrape mode should expect minimal artifacts."""
        artifacts = get_expected_artifacts("scrape")
        assert "scraped_content.txt" in artifacts
        assert "insights.txt" in artifacts
        assert "dossier.txt" not in artifacts

    def test_deep_mode_artifacts(self) -> None:
        """Deep mode should expect research artifacts."""
        artifacts = get_expected_artifacts("deep")
        assert "dossier.txt" in artifacts
        assert "report.docx" in artifacts
        assert "scraped_content.txt" not in artifacts

    def test_full_mode_artifacts(self) -> None:
        """Full mode should expect all artifacts."""
        artifacts = get_expected_artifacts("full")
        assert "scraped_content.txt" in artifacts
        assert "insights.txt" in artifacts
        assert "dossier.txt" in artifacts
        assert "report.docx" in artifacts
        assert "report.md" in artifacts
