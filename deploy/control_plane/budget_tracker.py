"""
Budget Tracker - Per-API-key usage tracking and spending limits.

This module provides per-API-key budget enforcement:
- Records estimated cost per job, keyed by API key hash
- Enforces configurable spending limits: per-job, daily, monthly
- Returns 429 with limit, current usage, and reset time when exceeded
- Supports both Cosmos DB backing store (cloud) and in-memory store (local)
- Stores usage records with 30-day TTL
- Loads limits from env vars: PRIMR_MAX_JOB_COST_USD, PRIMR_MAX_DAILY_COST_USD, PRIMR_MAX_MONTHLY_COST_USD

Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class BudgetLimits:
    """Configurable spending limits for an API key."""

    max_job_cost_usd: float = 1.0
    max_daily_cost_usd: float = 10.0
    max_monthly_cost_usd: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_job_cost_usd": self.max_job_cost_usd,
            "max_daily_cost_usd": self.max_daily_cost_usd,
            "max_monthly_cost_usd": self.max_monthly_cost_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BudgetLimits:
        return cls(
            max_job_cost_usd=data.get("max_job_cost_usd", 1.0),
            max_daily_cost_usd=data.get("max_daily_cost_usd", 10.0),
            max_monthly_cost_usd=data.get("max_monthly_cost_usd", 100.0),
        )


@dataclass
class JobCostRecord:
    """Record of a single job's cost."""

    job_id: str
    cost_usd: float
    mode: str
    submitted_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "cost_usd": self.cost_usd,
            "mode": self.mode,
            "submitted_at": self.submitted_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobCostRecord:
        return cls(
            job_id=data.get("job_id", ""),
            cost_usd=data.get("cost_usd", 0.0),
            mode=data.get("mode", ""),
            submitted_at=data.get("submitted_at", ""),
        )


@dataclass
class UsageRecord:
    """Daily usage record for an API key."""

    api_key_hash: str
    date: str  # YYYY-MM-DD
    job_count: int = 0
    total_cost_usd: float = 0.0
    jobs: list[JobCostRecord] = field(default_factory=list)
    ttl: int = 0  # Unix timestamp for auto-expiry

    @property
    def id(self) -> str:
        """Cosmos DB document ID."""
        return f"{self.api_key_hash}:{self.date}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "api_key_hash": self.api_key_hash,
            "date": self.date,
            "job_count": self.job_count,
            "total_cost_usd": self.total_cost_usd,
            "jobs": [j.to_dict() for j in self.jobs],
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UsageRecord:
        return cls(
            api_key_hash=data.get("api_key_hash", ""),
            date=data.get("date", ""),
            job_count=data.get("job_count", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            jobs=[JobCostRecord.from_dict(j) for j in data.get("jobs", [])],
            ttl=data.get("ttl", 0),
        )


@dataclass
class BudgetUsage:
    """Current budget usage summary for an API key."""

    daily_cost_usd: float = 0.0
    monthly_cost_usd: float = 0.0
    all_time_cost_usd: float = 0.0
    daily_job_count: int = 0
    monthly_job_count: int = 0
    all_time_job_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "daily_cost_usd": self.daily_cost_usd,
            "monthly_cost_usd": self.monthly_cost_usd,
            "all_time_cost_usd": self.all_time_cost_usd,
            "daily_job_count": self.daily_job_count,
            "monthly_job_count": self.monthly_job_count,
            "all_time_job_count": self.all_time_job_count,
        }


@dataclass
class BudgetStatus:
    """Full budget status including usage and remaining budget."""

    usage: BudgetUsage
    limits: BudgetLimits
    remaining_daily_usd: float = 0.0
    remaining_monthly_usd: float = 0.0
    daily_reset_at: str = ""
    monthly_reset_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "usage": self.usage.to_dict(),
            "limits": self.limits.to_dict(),
            "remaining_daily_usd": self.remaining_daily_usd,
            "remaining_monthly_usd": self.remaining_monthly_usd,
            "daily_reset_at": self.daily_reset_at,
            "monthly_reset_at": self.monthly_reset_at,
        }


# =============================================================================
# EXCEPTIONS
# =============================================================================


class BudgetExceededError(Exception):
    """Raised when a spending limit is exceeded."""

    def __init__(
        self,
        message: str,
        limit_type: str,
        limits: BudgetLimits,
        usage: BudgetUsage,
        reset_at: str | None = None,
    ) -> None:
        super().__init__(message)
        self.limit_type = limit_type
        self.limits = limits
        self.usage = usage
        self.reset_at = reset_at


# =============================================================================
# USAGE STORE PROTOCOL
# =============================================================================


@runtime_checkable
class UsageStore(Protocol):
    """Protocol for usage record persistence."""

    def get_usage_record(self, api_key_hash: str, date: str) -> UsageRecord | None:
        """Get usage record for an API key on a specific date."""
        ...

    def put_usage_record(self, record: UsageRecord) -> None:
        """Create or update a usage record."""
        ...

    def get_usage_records_for_month(
        self, api_key_hash: str, year: int, month: int
    ) -> list[UsageRecord]:
        """Get all usage records for an API key in a given month."""
        ...

    def get_all_usage_records(self, api_key_hash: str) -> list[UsageRecord]:
        """Get all usage records for an API key."""
        ...


# =============================================================================
# IN-MEMORY USAGE STORE
# =============================================================================


class InMemoryUsageStore:
    """
    In-memory usage store for local/testing use.

    Thread-safe implementation using locks.
    """

    def __init__(self) -> None:
        self._records: dict[str, UsageRecord] = {}  # key: "{api_key_hash}:{date}"
        self._lock = threading.Lock()

    def get_usage_record(self, api_key_hash: str, date: str) -> UsageRecord | None:
        """Get usage record for an API key on a specific date."""
        with self._lock:
            return self._records.get(f"{api_key_hash}:{date}")

    def put_usage_record(self, record: UsageRecord) -> None:
        """Create or update a usage record."""
        with self._lock:
            self._records[record.id] = record

    def get_usage_records_for_month(
        self, api_key_hash: str, year: int, month: int
    ) -> list[UsageRecord]:
        """Get all usage records for an API key in a given month."""
        prefix = f"{api_key_hash}:{year}-{month:02d}"
        with self._lock:
            return [
                record
                for key, record in self._records.items()
                if key.startswith(prefix)
            ]

    def get_all_usage_records(self, api_key_hash: str) -> list[UsageRecord]:
        """Get all usage records for an API key."""
        prefix = f"{api_key_hash}:"
        with self._lock:
            return [
                record
                for key, record in self._records.items()
                if key.startswith(prefix)
            ]

    def clear(self) -> None:
        """Clear all records (for testing)."""
        with self._lock:
            self._records.clear()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def load_limits_from_env() -> BudgetLimits:
    """
    Load budget limits from environment variables.

    Env vars:
        PRIMR_MAX_JOB_COST_USD: Per-job maximum (default: 1.0)
        PRIMR_MAX_DAILY_COST_USD: Daily maximum (default: 10.0)
        PRIMR_MAX_MONTHLY_COST_USD: Monthly maximum (default: 100.0)
    """
    return BudgetLimits(
        max_job_cost_usd=float(os.environ.get("PRIMR_MAX_JOB_COST_USD", "1.0")),
        max_daily_cost_usd=float(os.environ.get("PRIMR_MAX_DAILY_COST_USD", "10.0")),
        max_monthly_cost_usd=float(os.environ.get("PRIMR_MAX_MONTHLY_COST_USD", "100.0")),
    )


def _today_str() -> str:
    """Get today's date as YYYY-MM-DD string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _daily_reset_time() -> str:
    """Get the next daily reset time (midnight UTC)."""
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # If we're already past midnight, go to next day
    if tomorrow <= now:
        from datetime import timedelta

        tomorrow = tomorrow + timedelta(days=1)
    return tomorrow.strftime("%Y-%m-%dT%H:%M:%SZ")


def _monthly_reset_time() -> str:
    """Get the next monthly reset time (1st of next month, midnight UTC)."""
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return next_month.strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_ttl() -> int:
    """Get default TTL: 30 days from now as Unix timestamp."""
    return int(time.time()) + 30 * 24 * 3600


# =============================================================================
# BUDGET TRACKER
# =============================================================================


class BudgetTracker:
    """
    Per-API-key budget tracker with spending limit enforcement.

    Tracks job costs per API key and enforces configurable limits:
    - Per-job maximum
    - Daily maximum
    - Monthly maximum

    Supports both in-memory (local) and Cosmos DB (cloud) backing stores.
    """

    def __init__(
        self,
        usage_store: UsageStore | None = None,
        default_limits: BudgetLimits | None = None,
    ) -> None:
        """
        Initialize budget tracker.

        Args:
            usage_store: Backing store for usage records (defaults to InMemoryUsageStore)
            default_limits: Default spending limits (defaults to env vars or BudgetLimits defaults)
        """
        self.usage_store = usage_store or InMemoryUsageStore()
        self.default_limits = default_limits or load_limits_from_env()
        self._limits: dict[str, BudgetLimits] = {}  # api_key_hash -> custom limits
        self._lock = threading.Lock()

    def set_limits(self, api_key_hash: str, limits: BudgetLimits) -> None:
        """Set custom spending limits for an API key."""
        with self._lock:
            self._limits[api_key_hash] = limits

    def get_limits(self, api_key_hash: str) -> BudgetLimits:
        """Get spending limits for an API key."""
        with self._lock:
            return self._limits.get(api_key_hash, self.default_limits)

    def get_usage(self, api_key_hash: str) -> BudgetUsage:
        """
        Get current usage summary for an API key.

        Returns aggregated daily, monthly, and all-time spend.
        """
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        # Daily usage
        daily_record = self.usage_store.get_usage_record(api_key_hash, today)
        daily_cost = daily_record.total_cost_usd if daily_record else 0.0
        daily_jobs = daily_record.job_count if daily_record else 0

        # Monthly usage
        monthly_records = self.usage_store.get_usage_records_for_month(
            api_key_hash, now.year, now.month
        )
        monthly_cost = sum(r.total_cost_usd for r in monthly_records)
        monthly_jobs = sum(r.job_count for r in monthly_records)

        # All-time usage
        all_records = self.usage_store.get_all_usage_records(api_key_hash)
        all_time_cost = sum(r.total_cost_usd for r in all_records)
        all_time_jobs = sum(r.job_count for r in all_records)

        return BudgetUsage(
            daily_cost_usd=daily_cost,
            monthly_cost_usd=monthly_cost,
            all_time_cost_usd=all_time_cost,
            daily_job_count=daily_jobs,
            monthly_job_count=monthly_jobs,
            all_time_job_count=all_time_jobs,
        )

    def get_budget_status(self, api_key_hash: str) -> BudgetStatus:
        """
        Get full budget status including usage and remaining budget.

        Used by the /usage/{api_key_hash} endpoint.
        """
        usage = self.get_usage(api_key_hash)
        limits = self.get_limits(api_key_hash)

        return BudgetStatus(
            usage=usage,
            limits=limits,
            remaining_daily_usd=max(0.0, limits.max_daily_cost_usd - usage.daily_cost_usd),
            remaining_monthly_usd=max(0.0, limits.max_monthly_cost_usd - usage.monthly_cost_usd),
            daily_reset_at=_daily_reset_time(),
            monthly_reset_at=_monthly_reset_time(),
        )

    def check_budget(
        self,
        api_key_hash: str,
        estimated_cost_usd: float,
    ) -> None:
        """
        Check if a new job would exceed any spending limit.

        Args:
            api_key_hash: Hashed API key
            estimated_cost_usd: Estimated cost for the new job

        Raises:
            BudgetExceededError: If any limit would be exceeded
        """
        limits = self.get_limits(api_key_hash)
        usage = self.get_usage(api_key_hash)

        # Check per-job limit
        if estimated_cost_usd > limits.max_job_cost_usd:
            raise BudgetExceededError(
                f"Job cost (${estimated_cost_usd:.2f}) exceeds per-job limit (${limits.max_job_cost_usd:.2f})",
                limit_type="per_job",
                limits=limits,
                usage=usage,
            )

        # Check daily limit
        if usage.daily_cost_usd + estimated_cost_usd > limits.max_daily_cost_usd:
            raise BudgetExceededError(
                f"Daily spend (${usage.daily_cost_usd:.2f} + ${estimated_cost_usd:.2f}) "
                f"would exceed daily limit (${limits.max_daily_cost_usd:.2f})",
                limit_type="daily",
                limits=limits,
                usage=usage,
                reset_at=_daily_reset_time(),
            )

        # Check monthly limit
        if usage.monthly_cost_usd + estimated_cost_usd > limits.max_monthly_cost_usd:
            raise BudgetExceededError(
                f"Monthly spend (${usage.monthly_cost_usd:.2f} + ${estimated_cost_usd:.2f}) "
                f"would exceed monthly limit (${limits.max_monthly_cost_usd:.2f})",
                limit_type="monthly",
                limits=limits,
                usage=usage,
                reset_at=_monthly_reset_time(),
            )

    def record_job_cost(
        self,
        api_key_hash: str,
        job_id: str,
        cost_usd: float,
        mode: str = "",
    ) -> None:
        """
        Record the cost of a submitted job.

        Args:
            api_key_hash: Hashed API key
            job_id: Job identifier
            cost_usd: Estimated cost in USD
            mode: Research mode (scrape, deep, full)
        """
        today = _today_str()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        job_record = JobCostRecord(
            job_id=job_id,
            cost_usd=cost_usd,
            mode=mode,
            submitted_at=now_str,
        )

        with self._lock:
            # Get or create today's usage record
            existing = self.usage_store.get_usage_record(api_key_hash, today)
            if existing:
                existing.job_count += 1
                existing.total_cost_usd += cost_usd
                existing.jobs.append(job_record)
                self.usage_store.put_usage_record(existing)
            else:
                record = UsageRecord(
                    api_key_hash=api_key_hash,
                    date=today,
                    job_count=1,
                    total_cost_usd=cost_usd,
                    jobs=[job_record],
                    ttl=_default_ttl(),
                )
                self.usage_store.put_usage_record(record)
