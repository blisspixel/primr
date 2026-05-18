"""
Unit tests for the budget tracker module.

Tests cover:
- BudgetTracker per-job, daily, monthly limit enforcement
- Usage recording and aggregation
- BudgetExceededError with correct limit_type and reset_at
- InMemoryUsageStore CRUD operations
- /usage/{api_key_hash} endpoint
- Environment variable loading for limits

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from deploy.control_plane.api import app, configure_app
from deploy.control_plane.budget_tracker import (
    BudgetExceededError,
    BudgetLimits,
    BudgetTracker,
    InMemoryUsageStore,
    JobCostRecord,
    UsageRecord,
    load_limits_from_env,
)
from deploy.control_plane.cancellation import CancellationService
from deploy.control_plane.cost_governor import CostGovernor
from deploy.control_plane.job_store import InMemoryJobStore
from deploy.control_plane.queue import InMemoryQueue
from deploy.storage import LocalStore

if TYPE_CHECKING:
    from pathlib import Path


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def usage_store() -> InMemoryUsageStore:
    """Create a fresh in-memory usage store."""
    return InMemoryUsageStore()


@pytest.fixture
def budget_tracker(usage_store: InMemoryUsageStore) -> BudgetTracker:
    """Create a budget tracker with default limits."""
    return BudgetTracker(
        usage_store=usage_store,
        default_limits=BudgetLimits(
            max_job_cost_usd=1.0,
            max_daily_cost_usd=10.0,
            max_monthly_cost_usd=100.0,
        ),
    )


@pytest.fixture
def client(
    tmp_path: Path,
    budget_tracker: BudgetTracker,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Create a test client with configured app including budget tracker.

    Sets PRIMR_CONTROL_PLANE_API_KEYS so the auth dependency (which now
    fails closed when no verifier is configured) accepts the "test-key-with-min-len-16"
    bearer used by the test cases below.
    """
    monkeypatch.setenv("PRIMR_CONTROL_PLANE_API_KEYS", "test-key-with-min-len-16")
    job_store = InMemoryJobStore()
    configure_app(
        job_store=job_store,
        queue=InMemoryQueue(),
        artifact_store=LocalStore(tmp_path, deployment="test"),
        cost_governor=CostGovernor(job_store),
        cancellation_service=CancellationService(job_store),
        budget_tracker=budget_tracker,
        deployment="test",
    )
    return TestClient(app)


# =============================================================================
# IN-MEMORY USAGE STORE TESTS
# =============================================================================


class TestInMemoryUsageStore:
    """Tests for InMemoryUsageStore."""

    def test_get_nonexistent_returns_none(self, usage_store: InMemoryUsageStore) -> None:
        assert usage_store.get_usage_record("sha256:abc", "2026-01-15") is None

    def test_put_and_get(self, usage_store: InMemoryUsageStore) -> None:
        record = UsageRecord(
            api_key_hash="sha256:abc",
            date="2026-01-15",
            job_count=1,
            total_cost_usd=0.50,
            jobs=[
                JobCostRecord(
                    job_id="j1", cost_usd=0.50, mode="scrape", submitted_at="2026-01-15T10:00:00Z"
                )
            ],
            ttl=9999999,
        )
        usage_store.put_usage_record(record)
        result = usage_store.get_usage_record("sha256:abc", "2026-01-15")
        assert result is not None
        assert result.total_cost_usd == 0.50
        assert result.job_count == 1

    def test_get_records_for_month(self, usage_store: InMemoryUsageStore) -> None:
        for day in range(1, 4):
            usage_store.put_usage_record(
                UsageRecord(
                    api_key_hash="sha256:abc",
                    date=f"2026-01-{day:02d}",
                    job_count=1,
                    total_cost_usd=1.0,
                )
            )
        # Different month
        usage_store.put_usage_record(
            UsageRecord(
                api_key_hash="sha256:abc", date="2026-02-01", job_count=1, total_cost_usd=5.0
            )
        )
        records = usage_store.get_usage_records_for_month("sha256:abc", 2026, 1)
        assert len(records) == 3
        assert sum(r.total_cost_usd for r in records) == 3.0

    def test_get_all_records(self, usage_store: InMemoryUsageStore) -> None:
        usage_store.put_usage_record(
            UsageRecord(
                api_key_hash="sha256:abc", date="2026-01-01", job_count=1, total_cost_usd=1.0
            )
        )
        usage_store.put_usage_record(
            UsageRecord(
                api_key_hash="sha256:abc", date="2026-02-01", job_count=2, total_cost_usd=3.0
            )
        )
        # Different key
        usage_store.put_usage_record(
            UsageRecord(
                api_key_hash="sha256:xyz", date="2026-01-01", job_count=1, total_cost_usd=2.0
            )
        )
        records = usage_store.get_all_usage_records("sha256:abc")
        assert len(records) == 2
        assert sum(r.total_cost_usd for r in records) == 4.0

    def test_clear(self, usage_store: InMemoryUsageStore) -> None:
        usage_store.put_usage_record(
            UsageRecord(
                api_key_hash="sha256:abc", date="2026-01-01", job_count=1, total_cost_usd=1.0
            )
        )
        usage_store.clear()
        assert usage_store.get_all_usage_records("sha256:abc") == []


# =============================================================================
# BUDGET TRACKER TESTS
# =============================================================================


class TestBudgetTrackerLimits:
    """Tests for BudgetTracker limit enforcement."""

    def test_per_job_limit_exceeded(self, budget_tracker: BudgetTracker) -> None:
        with pytest.raises(BudgetExceededError) as exc_info:
            budget_tracker.check_budget("sha256:abc", 1.50)
        assert exc_info.value.limit_type == "per_job"
        assert exc_info.value.limits.max_job_cost_usd == 1.0

    def test_per_job_limit_at_boundary(self, budget_tracker: BudgetTracker) -> None:
        # Exactly at limit should pass
        budget_tracker.check_budget("sha256:abc", 1.0)

    def test_daily_limit_exceeded(self, budget_tracker: BudgetTracker) -> None:
        # Record enough cost to approach daily limit
        for i in range(9):
            budget_tracker.record_job_cost("sha256:abc", f"job-{i}", 1.0, "scrape")

        # This should still pass (9.0 + 1.0 = 10.0 == limit)
        budget_tracker.check_budget("sha256:abc", 1.0)

        # Record one more
        budget_tracker.record_job_cost("sha256:abc", "job-9", 1.0, "scrape")

        # Now exceeding daily limit
        with pytest.raises(BudgetExceededError) as exc_info:
            budget_tracker.check_budget("sha256:abc", 0.50)
        assert exc_info.value.limit_type == "daily"
        assert exc_info.value.reset_at is not None

    def test_monthly_limit_exceeded(self, budget_tracker: BudgetTracker) -> None:
        # Set a low monthly limit for testing
        budget_tracker.set_limits(
            "sha256:abc",
            BudgetLimits(max_job_cost_usd=5.0, max_daily_cost_usd=50.0, max_monthly_cost_usd=10.0),
        )
        budget_tracker.record_job_cost("sha256:abc", "job-1", 5.0, "full")
        budget_tracker.record_job_cost("sha256:abc", "job-2", 5.0, "full")

        with pytest.raises(BudgetExceededError) as exc_info:
            budget_tracker.check_budget("sha256:abc", 1.0)
        assert exc_info.value.limit_type == "monthly"
        assert exc_info.value.reset_at is not None

    def test_custom_limits_per_key(self, budget_tracker: BudgetTracker) -> None:
        budget_tracker.set_limits(
            "sha256:vip",
            BudgetLimits(
                max_job_cost_usd=50.0, max_daily_cost_usd=500.0, max_monthly_cost_usd=5000.0
            ),
        )
        # This would fail with default limits but passes with custom
        budget_tracker.check_budget("sha256:vip", 25.0)

    def test_no_error_when_within_limits(self, budget_tracker: BudgetTracker) -> None:
        budget_tracker.check_budget("sha256:abc", 0.50)


class TestBudgetTrackerRecording:
    """Tests for BudgetTracker cost recording."""

    def test_record_job_cost(self, budget_tracker: BudgetTracker) -> None:
        budget_tracker.record_job_cost("sha256:abc", "job-1", 0.50, "scrape")
        usage = budget_tracker.get_usage("sha256:abc")
        assert usage.daily_cost_usd == 0.50
        assert usage.daily_job_count == 1

    def test_record_multiple_jobs(self, budget_tracker: BudgetTracker) -> None:
        budget_tracker.record_job_cost("sha256:abc", "job-1", 0.50, "scrape")
        budget_tracker.record_job_cost("sha256:abc", "job-2", 1.00, "deep")
        usage = budget_tracker.get_usage("sha256:abc")
        assert usage.daily_cost_usd == 1.50
        assert usage.daily_job_count == 2

    def test_separate_tracking_per_key(self, budget_tracker: BudgetTracker) -> None:
        budget_tracker.record_job_cost("sha256:abc", "job-1", 0.50, "scrape")
        budget_tracker.record_job_cost("sha256:xyz", "job-2", 1.00, "deep")
        usage_abc = budget_tracker.get_usage("sha256:abc")
        usage_xyz = budget_tracker.get_usage("sha256:xyz")
        assert usage_abc.daily_cost_usd == 0.50
        assert usage_xyz.daily_cost_usd == 1.00


class TestBudgetStatus:
    """Tests for BudgetTracker budget status."""

    def test_budget_status_with_no_usage(self, budget_tracker: BudgetTracker) -> None:
        status = budget_tracker.get_budget_status("sha256:abc")
        assert status.usage.daily_cost_usd == 0.0
        assert status.remaining_daily_usd == 10.0
        assert status.remaining_monthly_usd == 100.0
        assert status.daily_reset_at != ""
        assert status.monthly_reset_at != ""

    def test_budget_status_with_usage(self, budget_tracker: BudgetTracker) -> None:
        budget_tracker.record_job_cost("sha256:abc", "job-1", 3.0, "full")
        status = budget_tracker.get_budget_status("sha256:abc")
        assert status.usage.daily_cost_usd == 3.0
        assert status.remaining_daily_usd == 7.0
        assert status.remaining_monthly_usd == 97.0

    def test_budget_status_serialization(self, budget_tracker: BudgetTracker) -> None:
        status = budget_tracker.get_budget_status("sha256:abc")
        d = status.to_dict()
        assert "usage" in d
        assert "limits" in d
        assert "remaining_daily_usd" in d
        assert "remaining_monthly_usd" in d


# =============================================================================
# ENV VAR LOADING TESTS
# =============================================================================


class TestLoadLimitsFromEnv:
    """Tests for loading limits from environment variables."""

    def test_defaults_when_no_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PRIMR_MAX_JOB_COST_USD", raising=False)
        monkeypatch.delenv("PRIMR_MAX_DAILY_COST_USD", raising=False)
        monkeypatch.delenv("PRIMR_MAX_MONTHLY_COST_USD", raising=False)
        limits = load_limits_from_env()
        assert limits.max_job_cost_usd == 1.0
        assert limits.max_daily_cost_usd == 10.0
        assert limits.max_monthly_cost_usd == 100.0

    def test_custom_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PRIMR_MAX_JOB_COST_USD", "5.0")
        monkeypatch.setenv("PRIMR_MAX_DAILY_COST_USD", "50.0")
        monkeypatch.setenv("PRIMR_MAX_MONTHLY_COST_USD", "500.0")
        limits = load_limits_from_env()
        assert limits.max_job_cost_usd == 5.0
        assert limits.max_daily_cost_usd == 50.0
        assert limits.max_monthly_cost_usd == 500.0


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================


class TestUsageEndpoint:
    """Tests for the /usage/{api_key_hash} endpoint."""

    def test_usage_returns_empty_for_new_key(self, client: TestClient) -> None:
        # The caller's api_key_hash must match the path parameter (H2 authorization fix)
        from deploy.control_plane.job_store import hash_api_key

        caller_hash = hash_api_key("test-key-with-min-len-16")
        response = client.get(
            f"/usage/{caller_hash}",
            headers={"Authorization": "Bearer test-key-with-min-len-16"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["usage"]["daily_cost_usd"] == 0.0
        assert data["usage"]["monthly_cost_usd"] == 0.0
        assert data["remaining_daily_usd"] == 10.0
        assert data["remaining_monthly_usd"] == 100.0

    def test_usage_reflects_recorded_costs(
        self, client: TestClient, budget_tracker: BudgetTracker
    ) -> None:
        from deploy.control_plane.job_store import hash_api_key

        caller_hash = hash_api_key("test-key-with-min-len-16")
        budget_tracker.record_job_cost(caller_hash, "job-1", 2.5, "deep")
        response = client.get(
            f"/usage/{caller_hash}",
            headers={"Authorization": "Bearer test-key-with-min-len-16"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["usage"]["daily_cost_usd"] == 2.5
        assert data["usage"]["daily_job_count"] == 1
        assert data["remaining_daily_usd"] == 7.5

    def test_usage_requires_auth(self, client: TestClient) -> None:
        response = client.get("/usage/sha256:abc")
        assert response.status_code == 401

    def test_usage_rejects_mismatched_hash(self, client: TestClient) -> None:
        """Callers cannot query usage for a different API key (H2 fix)."""
        response = client.get(
            "/usage/sha256:someone_elses_hash",
            headers={"Authorization": "Bearer test-key-with-min-len-16"},
        )
        assert response.status_code == 403
