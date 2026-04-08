"""
Cost Governor - Quota enforcement and cost estimation.

This module provides cost controls and approval gates:
- Cost estimation on submit
- Per-API-key quotas (max concurrent jobs, max daily cost)
- PENDING_APPROVAL state support

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from deploy.control_plane.job_store import (
    CostEstimate,
    JobStatus,
    JobStore,
)


class QuotaExceededError(Exception):
    """Raised when quota is exceeded."""

    def __init__(self, message: str, quota: QuotaConfig, usage: QuotaUsage) -> None:
        super().__init__(message)
        self.quota = quota
        self.usage = usage


@dataclass
class QuotaConfig:
    """Quota configuration for an API key."""

    max_concurrent_jobs: int = 5
    max_daily_cost_usd: float = 50.0
    max_job_cost_usd: float = 10.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_daily_cost_usd": self.max_daily_cost_usd,
            "max_job_cost_usd": self.max_job_cost_usd,
        }


@dataclass
class QuotaUsage:
    """Current quota usage for an API key."""

    concurrent_jobs: int = 0
    daily_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "concurrent_jobs": self.concurrent_jobs,
            "daily_cost_usd": self.daily_cost_usd,
        }


# Cost estimates by mode (in USD)
MODE_COST_ESTIMATES = {
    "scrape": CostEstimate(cost_usd=0.10, duration_minutes=10),
    "deep": CostEstimate(cost_usd=2.50, duration_minutes=15),
    "full": CostEstimate(cost_usd=3.50, duration_minutes=40),
}


def estimate_cost(mode: str) -> CostEstimate:
    """
    Estimate cost and duration for a job mode.

    Cost estimates are rough approximations:
    - scrape: ~$0.10 (minimal LLM usage, 5-10 min)
    - deep: ~$2.50 (Deep Research flat fee, 8-15 min)
    - full: ~$3.50 (Deep Research + token costs, 25-40 min)

    Args:
        mode: Job mode (scrape, deep, full)

    Returns:
        CostEstimate with cost_usd and duration_minutes
    """
    return MODE_COST_ESTIMATES.get(mode, MODE_COST_ESTIMATES["full"])


class CostGovernor:
    """
    Cost governor for quota enforcement.

    Tracks per-API-key usage and enforces quotas.
    """

    def __init__(
        self,
        job_store: JobStore,
        default_quota: QuotaConfig | None = None,
    ) -> None:
        """
        Initialize cost governor.

        Args:
            job_store: Job state store
            default_quota: Default quota config for all API keys
        """
        self.job_store = job_store
        self.default_quota = default_quota or QuotaConfig()
        self._quotas: dict[str, QuotaConfig] = {}  # api_key_hash -> quota
        self._daily_costs: dict[str, dict[str, float]] = {}  # api_key_hash -> {date: cost}
        self._lock = threading.Lock()

    def set_quota(self, api_key_hash: str, quota: QuotaConfig) -> None:
        """Set quota for an API key."""
        with self._lock:
            self._quotas[api_key_hash] = quota

    def get_quota(self, api_key_hash: str) -> QuotaConfig:
        """Get quota for an API key."""
        with self._lock:
            return self._quotas.get(api_key_hash, self.default_quota)

    def get_usage(self, api_key_hash: str) -> QuotaUsage:
        """
        Get current usage for an API key.

        Counts concurrent jobs (QUEUED, RUNNING, PENDING_APPROVAL, CANCEL_REQUESTED)
        and daily cost from completed jobs.
        """
        # Count concurrent jobs
        active_statuses = [
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.PENDING_APPROVAL,
            JobStatus.CANCEL_REQUESTED,
        ]
        active_jobs = self.job_store.query_by_status(active_statuses)
        concurrent = sum(1 for job in active_jobs if job.api_key_hash == api_key_hash)

        # Get daily cost
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            daily_costs = self._daily_costs.get(api_key_hash, {})
            daily_cost = daily_costs.get(today, 0.0)

        return QuotaUsage(
            concurrent_jobs=concurrent,
            daily_cost_usd=daily_cost,
        )

    def check_quota(
        self,
        api_key_hash: str,
        estimate: CostEstimate,
    ) -> None:
        """
        Check if a new job would exceed quota.

        Args:
            api_key_hash: Hashed API key
            estimate: Cost estimate for the new job

        Raises:
            QuotaExceededError: If quota would be exceeded
        """
        quota = self.get_quota(api_key_hash)
        usage = self.get_usage(api_key_hash)

        # Check concurrent jobs
        if usage.concurrent_jobs >= quota.max_concurrent_jobs:
            raise QuotaExceededError(
                f"Maximum concurrent jobs ({quota.max_concurrent_jobs}) exceeded",
                quota,
                usage,
            )

        # Check daily cost
        if usage.daily_cost_usd + estimate.cost_usd > quota.max_daily_cost_usd:
            raise QuotaExceededError(
                f"Daily cost limit (${quota.max_daily_cost_usd:.2f}) would be exceeded",
                quota,
                usage,
            )

        # Check single job cost
        if estimate.cost_usd > quota.max_job_cost_usd:
            raise QuotaExceededError(
                f"Job cost (${estimate.cost_usd:.2f}) exceeds maximum (${quota.max_job_cost_usd:.2f})",
                quota,
                usage,
            )

    def record_job_cost(self, api_key_hash: str, cost_usd: float) -> None:
        """
        Record cost for a completed job.

        Args:
            api_key_hash: Hashed API key
            cost_usd: Actual or estimated cost
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with self._lock:
            if api_key_hash not in self._daily_costs:
                self._daily_costs[api_key_hash] = {}

            if today not in self._daily_costs[api_key_hash]:
                self._daily_costs[api_key_hash][today] = 0.0

            self._daily_costs[api_key_hash][today] += cost_usd

    def cleanup_old_costs(self, days_to_keep: int = 7) -> None:
        """
        Clean up old daily cost records.

        Args:
            days_to_keep: Number of days to keep
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")

        with self._lock:
            for api_key_hash in self._daily_costs:
                self._daily_costs[api_key_hash] = {
                    date: cost
                    for date, cost in self._daily_costs[api_key_hash].items()
                    if date >= cutoff
                }

    def should_require_approval(
        self,
        estimate: CostEstimate,
        threshold_usd: float = 5.0,
    ) -> bool:
        """
        Check if a job should require approval based on cost.

        Args:
            estimate: Cost estimate for the job
            threshold_usd: Cost threshold for requiring approval

        Returns:
            True if job should require approval
        """
        return estimate.cost_usd >= threshold_usd
