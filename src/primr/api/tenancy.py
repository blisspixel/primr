"""
Multi-tenancy support for the Primr API.

Provides isolated workspaces, per-tenant configuration, and usage tracking.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class TenantTier(Enum):
    """Tenant subscription tiers."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class TenantStatus(Enum):
    """Tenant account status."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"
    DELETED = "deleted"


@dataclass
class TenantLimits:
    """Resource limits for a tenant."""
    max_requests_per_day: int = 100
    max_requests_per_month: int = 1000
    max_concurrent_jobs: int = 2
    max_pages_per_research: int = 20
    max_report_size_mb: float = 10.0
    max_storage_mb: float = 100.0
    priority_boost: int = 0  # Higher = more priority

    @classmethod
    def for_tier(cls, tier: TenantTier) -> TenantLimits:
        """Get default limits for a tier."""
        limits = {
            TenantTier.FREE: cls(
                max_requests_per_day=10,
                max_requests_per_month=100,
                max_concurrent_jobs=1,
                max_pages_per_research=10,
                max_report_size_mb=5.0,
                max_storage_mb=50.0,
                priority_boost=0,
            ),
            TenantTier.STARTER: cls(
                max_requests_per_day=50,
                max_requests_per_month=500,
                max_concurrent_jobs=2,
                max_pages_per_research=25,
                max_report_size_mb=10.0,
                max_storage_mb=200.0,
                priority_boost=1,
            ),
            TenantTier.PROFESSIONAL: cls(
                max_requests_per_day=200,
                max_requests_per_month=2000,
                max_concurrent_jobs=5,
                max_pages_per_research=50,
                max_report_size_mb=25.0,
                max_storage_mb=1000.0,
                priority_boost=2,
            ),
            TenantTier.ENTERPRISE: cls(
                max_requests_per_day=1000,
                max_requests_per_month=10000,
                max_concurrent_jobs=20,
                max_pages_per_research=100,
                max_report_size_mb=100.0,
                max_storage_mb=10000.0,
                priority_boost=3,
            ),
        }
        return limits.get(tier, cls())


@dataclass
class TenantConfig:
    """Per-tenant configuration."""
    custom_prompts: dict[str, str] = field(default_factory=dict)
    default_output_format: str = "markdown"
    webhook_url: str | None = None
    webhook_secret: str | None = None
    allowed_domains: list[str] = field(default_factory=list)  # Empty = all allowed
    blocked_domains: list[str] = field(default_factory=list)
    custom_headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "custom_prompts": self.custom_prompts,
            "default_output_format": self.default_output_format,
            "webhook_url": self.webhook_url,
            "webhook_secret": self.webhook_secret,
            "allowed_domains": self.allowed_domains,
            "blocked_domains": self.blocked_domains,
            "custom_headers": self.custom_headers,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TenantConfig:
        """Create from dictionary."""
        return cls(
            custom_prompts=data.get("custom_prompts", {}),
            default_output_format=data.get("default_output_format", "markdown"),
            webhook_url=data.get("webhook_url"),
            webhook_secret=data.get("webhook_secret"),
            allowed_domains=data.get("allowed_domains", []),
            blocked_domains=data.get("blocked_domains", []),
            custom_headers=data.get("custom_headers", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Tenant:
    """A tenant (organization/user) in the system."""
    tenant_id: str
    name: str
    tier: TenantTier
    status: TenantStatus
    limits: TenantLimits
    config: TenantConfig
    created_at: datetime
    updated_at: datetime
    owner_email: str | None = None

    @property
    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == TenantStatus.ACTIVE

    def can_access_domain(self, domain: str) -> bool:
        """Check if tenant can access a domain."""
        domain = domain.lower()

        # Check blocked domains first
        for blocked in self.config.blocked_domains:
            if domain.endswith(blocked.lower()):
                return False

        # If allowed_domains is set, check whitelist
        if self.config.allowed_domains:
            for allowed in self.config.allowed_domains:
                if domain.endswith(allowed.lower()):
                    return True
            return False

        return True


@dataclass
class UsageRecord:
    """A usage record for tracking."""
    tenant_id: str
    timestamp: datetime
    request_type: str
    resource_used: str
    quantity: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageSummary:
    """Summary of tenant usage."""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_pages_scraped: int
    total_ai_tokens: int
    total_storage_mb: float
    requests_by_type: dict[str, int] = field(default_factory=dict)


class TenantManager:
    """Manages tenants and their resources."""

    def __init__(self, db_path: str | None = None):
        """Initialize tenant manager.

        Args:
            db_path: Path to SQLite database. Uses in-memory if None.
        """
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._tenant_cache: dict[str, Tenant] = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamps: dict[str, float] = {}
        # Always use persistent connection to avoid connection leaks
        self._persistent_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return self._persistent_conn
    
    def close(self) -> None:
        """Close the database connection."""
        if self._persistent_conn is not None:
            self._persistent_conn.close()
            self._persistent_conn = None

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        conn = self._get_connection()
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor

    def _executemany(self, query: str, params_list: list) -> None:
        """Execute a query with multiple parameter sets."""
        conn = self._get_connection()
        conn.executemany(query, params_list)
        conn.commit()

    def _fetchone(self, query: str, params: tuple = ()) -> sqlite3.Row | None:
        """Execute query and fetch one row."""
        conn = self._get_connection()
        result = conn.execute(query, params).fetchone()
        return result  # type: ignore[no-any-return]

    def _fetchall(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Execute query and fetch all rows."""
        conn = self._get_connection()
        return conn.execute(query, params).fetchall()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tier TEXT NOT NULL,
                status TEXT NOT NULL,
                limits_json TEXT NOT NULL,
                config_json TEXT NOT NULL,
                owner_email TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS usage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                request_type TEXT NOT NULL,
                resource_used TEXT NOT NULL,
                quantity REAL NOT NULL,
                metadata_json TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            );

            CREATE INDEX IF NOT EXISTS idx_usage_tenant_time
            ON usage_records(tenant_id, timestamp);

            CREATE TABLE IF NOT EXISTS tenant_workspaces (
                tenant_id TEXT PRIMARY KEY,
                workspace_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            );
        """)
        conn.commit()

    def create_tenant(
        self,
        name: str,
        tier: TenantTier = TenantTier.FREE,
        owner_email: str | None = None,
        config: TenantConfig | None = None,
    ) -> Tenant:
        """Create a new tenant.

        Args:
            name: Tenant name
            tier: Subscription tier
            owner_email: Owner's email
            config: Custom configuration

        Returns:
            Created tenant
        """
        tenant_id = self._generate_tenant_id(name)
        now = datetime.utcnow()
        limits = TenantLimits.for_tier(tier)
        config = config or TenantConfig()

        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            tier=tier,
            status=TenantStatus.ACTIVE,
            limits=limits,
            config=config,
            created_at=now,
            updated_at=now,
            owner_email=owner_email,
        )

        with self._lock:
            self._execute(
                """
                INSERT INTO tenants
                (tenant_id, name, tier, status, limits_json, config_json,
                 owner_email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant.tenant_id,
                    tenant.name,
                    tenant.tier.value,
                    tenant.status.value,
                    json.dumps(tenant.limits.__dict__),
                    json.dumps(tenant.config.to_dict()),
                    tenant.owner_email,
                    tenant.created_at.isoformat(),
                    tenant.updated_at.isoformat(),
                ),
            )

            self._tenant_cache[tenant_id] = tenant
            self._cache_timestamps[tenant_id] = time.time()

        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant or None if not found
        """
        with self._lock:
            # Check cache
            if tenant_id in self._tenant_cache:
                cache_time = self._cache_timestamps.get(tenant_id, 0)
                if time.time() - cache_time < self._cache_ttl:
                    return self._tenant_cache[tenant_id]

            # Load from database
            row = self._fetchone(
                "SELECT * FROM tenants WHERE tenant_id = ?",
                (tenant_id,),
            )

            if not row:
                return None

            tenant = self._row_to_tenant(row)
            self._tenant_cache[tenant_id] = tenant
            self._cache_timestamps[tenant_id] = time.time()

            return tenant

    def update_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        tier: TenantTier | None = None,
        status: TenantStatus | None = None,
        config: TenantConfig | None = None,
        limits: TenantLimits | None = None,
    ) -> Tenant | None:
        """Update a tenant.

        Args:
            tenant_id: Tenant ID
            name: New name
            tier: New tier
            status: New status
            config: New configuration
            limits: New limits (overrides tier defaults)

        Returns:
            Updated tenant or None if not found
        """
        with self._lock:
            tenant = self.get_tenant(tenant_id)
            if not tenant:
                return None

            if name is not None:
                tenant.name = name
            if tier is not None:
                tenant.tier = tier
                if limits is None:
                    tenant.limits = TenantLimits.for_tier(tier)
            if status is not None:
                tenant.status = status
            if config is not None:
                tenant.config = config
            if limits is not None:
                tenant.limits = limits

            tenant.updated_at = datetime.utcnow()

            self._execute(
                """
                UPDATE tenants SET
                    name = ?,
                    tier = ?,
                    status = ?,
                    limits_json = ?,
                    config_json = ?,
                    updated_at = ?
                WHERE tenant_id = ?
                """,
                (
                    tenant.name,
                    tenant.tier.value,
                    tenant.status.value,
                    json.dumps(tenant.limits.__dict__),
                    json.dumps(tenant.config.to_dict()),
                    tenant.updated_at.isoformat(),
                    tenant_id,
                ),
            )

            self._tenant_cache[tenant_id] = tenant
            self._cache_timestamps[tenant_id] = time.time()

            return tenant

    def delete_tenant(self, tenant_id: str, hard_delete: bool = False) -> bool:
        """Delete a tenant.

        Args:
            tenant_id: Tenant ID
            hard_delete: If True, permanently delete. Otherwise, mark as deleted.

        Returns:
            True if deleted
        """
        with self._lock:
            if hard_delete:
                self._execute(
                    "DELETE FROM usage_records WHERE tenant_id = ?",
                    (tenant_id,),
                )
                self._execute(
                    "DELETE FROM tenant_workspaces WHERE tenant_id = ?",
                    (tenant_id,),
                )
                cursor = self._execute(
                    "DELETE FROM tenants WHERE tenant_id = ?",
                    (tenant_id,),
                )
                deleted = cursor.rowcount > 0
            else:
                updated_tenant = self.update_tenant(tenant_id, status=TenantStatus.DELETED)
                deleted = updated_tenant is not None

            if tenant_id in self._tenant_cache:
                del self._tenant_cache[tenant_id]
            if tenant_id in self._cache_timestamps:
                del self._cache_timestamps[tenant_id]

            return deleted

    def list_tenants(
        self,
        status: TenantStatus | None = None,
        tier: TenantTier | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tenant]:
        """List tenants with optional filtering.

        Args:
            status: Filter by status
            tier: Filter by tier
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of tenants
        """
        query = "SELECT * FROM tenants WHERE 1=1"
        params: list[Any] = []

        if status is not None:
            query += " AND status = ?"
            params.append(status.value)
        if tier is not None:
            query += " AND tier = ?"
            params.append(tier.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._fetchall(query, tuple(params))

        return [self._row_to_tenant(row) for row in rows]

    def record_usage(
        self,
        tenant_id: str,
        request_type: str,
        resource_used: str,
        quantity: float,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record resource usage for a tenant.

        Args:
            tenant_id: Tenant ID
            request_type: Type of request (research, scrape, etc.)
            resource_used: Resource type (requests, pages, tokens, storage)
            quantity: Amount used
            metadata: Additional metadata

        Returns:
            Usage record
        """
        record = UsageRecord(
            tenant_id=tenant_id,
            timestamp=datetime.utcnow(),
            request_type=request_type,
            resource_used=resource_used,
            quantity=quantity,
            metadata=metadata or {},
        )

        self._execute(
            """
            INSERT INTO usage_records
            (tenant_id, timestamp, request_type, resource_used, quantity, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.tenant_id,
                record.timestamp.isoformat(),
                record.request_type,
                record.resource_used,
                record.quantity,
                json.dumps(record.metadata),
            ),
        )

        return record

    def get_usage_summary(
        self,
        tenant_id: str,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> UsageSummary:
        """Get usage summary for a tenant.

        Args:
            tenant_id: Tenant ID
            period_start: Start of period (default: start of current month)
            period_end: End of period (default: now)

        Returns:
            Usage summary
        """
        now = datetime.utcnow()
        if period_start is None:
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if period_end is None:
            period_end = now

        # Get total requests
        row = self._fetchone(
            """
            SELECT COUNT(*) as count FROM usage_records
            WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
            AND resource_used = 'requests'
            """,
            (tenant_id, period_start.isoformat(), period_end.isoformat()),
        )
        total_requests = row["count"] if row else 0

        # Get pages scraped
        row = self._fetchone(
            """
            SELECT COALESCE(SUM(quantity), 0) as total FROM usage_records
            WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
            AND resource_used = 'pages'
            """,
            (tenant_id, period_start.isoformat(), period_end.isoformat()),
        )
        total_pages = int(row["total"]) if row else 0

        # Get AI tokens
        row = self._fetchone(
            """
            SELECT COALESCE(SUM(quantity), 0) as total FROM usage_records
            WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
            AND resource_used = 'tokens'
            """,
            (tenant_id, period_start.isoformat(), period_end.isoformat()),
        )
        total_tokens = int(row["total"]) if row else 0

        # Get storage
        row = self._fetchone(
            """
            SELECT COALESCE(MAX(quantity), 0) as total FROM usage_records
            WHERE tenant_id = ? AND resource_used = 'storage'
            """,
            (tenant_id,),
        )
        total_storage = float(row["total"]) if row else 0.0

        # Get requests by type
        rows = self._fetchall(
            """
            SELECT request_type, COUNT(*) as count FROM usage_records
            WHERE tenant_id = ? AND timestamp >= ? AND timestamp <= ?
            GROUP BY request_type
            """,
            (tenant_id, period_start.isoformat(), period_end.isoformat()),
        )
        requests_by_type = {row["request_type"]: row["count"] for row in rows}

        return UsageSummary(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_requests=total_requests,
            total_pages_scraped=total_pages,
            total_ai_tokens=total_tokens,
            total_storage_mb=total_storage,
            requests_by_type=requests_by_type,
        )

    def check_limits(self, tenant_id: str) -> dict[str, Any]:
        """Check if tenant is within limits.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dict with limit status for each resource
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}

        now = datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get daily usage
        daily_summary = self.get_usage_summary(tenant_id, day_start, now)
        monthly_summary = self.get_usage_summary(tenant_id, month_start, now)

        return {
            "tenant_id": tenant_id,
            "tier": tenant.tier.value,
            "daily_requests": {
                "used": daily_summary.total_requests,
                "limit": tenant.limits.max_requests_per_day,
                "remaining": max(0, tenant.limits.max_requests_per_day - daily_summary.total_requests),
                "exceeded": daily_summary.total_requests >= tenant.limits.max_requests_per_day,
            },
            "monthly_requests": {
                "used": monthly_summary.total_requests,
                "limit": tenant.limits.max_requests_per_month,
                "remaining": max(0, tenant.limits.max_requests_per_month - monthly_summary.total_requests),
                "exceeded": monthly_summary.total_requests >= tenant.limits.max_requests_per_month,
            },
            "storage_mb": {
                "used": monthly_summary.total_storage_mb,
                "limit": tenant.limits.max_storage_mb,
                "remaining": max(0, tenant.limits.max_storage_mb - monthly_summary.total_storage_mb),
                "exceeded": monthly_summary.total_storage_mb >= tenant.limits.max_storage_mb,
            },
        }

    def get_workspace_path(self, tenant_id: str, base_path: str | None = None) -> Path:
        """Get or create isolated workspace for tenant.

        Args:
            tenant_id: Tenant ID
            base_path: Base directory for workspaces

        Returns:
            Path to tenant's workspace
        """
        base = Path(base_path) if base_path else Path("workspaces")

        row = self._fetchone(
            "SELECT workspace_path FROM tenant_workspaces WHERE tenant_id = ?",
            (tenant_id,),
        )

        if row:
            return Path(row["workspace_path"])

        # Create new workspace
        workspace_path = base / tenant_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (workspace_path / "cache").mkdir(exist_ok=True)
        (workspace_path / "output").mkdir(exist_ok=True)
        (workspace_path / "logs").mkdir(exist_ok=True)

        self._execute(
            """
            INSERT INTO tenant_workspaces (tenant_id, workspace_path, created_at)
            VALUES (?, ?, ?)
            """,
            (tenant_id, str(workspace_path), datetime.utcnow().isoformat()),
        )

        return workspace_path

    def _generate_tenant_id(self, name: str) -> str:
        """Generate a unique tenant ID."""
        timestamp = str(time.time_ns())
        data = f"{name}:{timestamp}".encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def _row_to_tenant(self, row: sqlite3.Row) -> Tenant:
        """Convert database row to Tenant object."""
        limits_data = json.loads(row["limits_json"])
        config_data = json.loads(row["config_json"])

        return Tenant(
            tenant_id=row["tenant_id"],
            name=row["name"],
            tier=TenantTier(row["tier"]),
            status=TenantStatus(row["status"]),
            limits=TenantLimits(**limits_data),
            config=TenantConfig.from_dict(config_data),
            owner_email=row["owner_email"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def clear_cache(self) -> None:
        """Clear the tenant cache."""
        with self._lock:
            self._tenant_cache.clear()
            self._cache_timestamps.clear()


# Global instance
_tenant_manager: TenantManager | None = None
_manager_lock = threading.Lock()


def get_tenant_manager(db_path: str | None = None) -> TenantManager:
    """Get the global tenant manager instance.

    Args:
        db_path: Database path (only used on first call)

    Returns:
        TenantManager instance
    """
    global _tenant_manager
    with _manager_lock:
        if _tenant_manager is None:
            _tenant_manager = TenantManager(db_path)
        return _tenant_manager


def reset_tenant_manager() -> None:
    """Reset the global tenant manager (for testing)."""
    global _tenant_manager
    with _manager_lock:
        _tenant_manager = None


# Convenience functions
def create_tenant(
    name: str,
    tier: TenantTier = TenantTier.FREE,
    owner_email: str | None = None,
) -> Tenant:
    """Create a new tenant."""
    return get_tenant_manager().create_tenant(name, tier, owner_email)


def get_tenant(tenant_id: str) -> Tenant | None:
    """Get a tenant by ID."""
    return get_tenant_manager().get_tenant(tenant_id)


def record_usage(
    tenant_id: str,
    request_type: str,
    resource_used: str,
    quantity: float,
) -> UsageRecord:
    """Record resource usage."""
    return get_tenant_manager().record_usage(
        tenant_id, request_type, resource_used, quantity
    )


def check_tenant_limits(tenant_id: str) -> dict[str, Any]:
    """Check tenant limits."""
    return get_tenant_manager().check_limits(tenant_id)
