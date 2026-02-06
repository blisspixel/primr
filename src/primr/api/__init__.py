"""
API module - REST API for company research service.
"""

from primr.api.auth import (
    APIKeyAuth,
    create_api_key,
    revoke_api_key,
    verify_api_key,
)
from primr.api.metrics import (
    Histogram,
    MetricsCollector,
    MetricType,
    RequestMetrics,
    export_metrics,
    get_metrics_collector,
    increment_counter,
    observe_histogram,
    reset_metrics_collector,
    set_gauge,
)
from primr.api.rate_limit import (
    RateLimitConfig,
    RateLimiter,
    check_rate_limit,
)
from primr.api.service import (
    HealthResponse,
    JobStatus,
    ResearchRequest,
    ResearchResponse,
    ResearchStatus,
    create_app,
)
from primr.api.tenancy import (
    Tenant,
    TenantConfig,
    TenantLimits,
    TenantManager,
    TenantStatus,
    TenantTier,
    UsageRecord,
    UsageSummary,
    check_tenant_limits,
    create_tenant,
    get_tenant,
    get_tenant_manager,
    record_usage,
    reset_tenant_manager,
)

__all__ = [
    # Auth
    "APIKeyAuth",
    "HealthResponse",
    "Histogram",
    "JobStatus",
    "MetricType",
    # Metrics
    "MetricsCollector",
    "RateLimitConfig",
    # Rate limiting
    "RateLimiter",
    "RequestMetrics",
    "ResearchRequest",
    "ResearchResponse",
    "ResearchStatus",
    "Tenant",
    "TenantConfig",
    "TenantLimits",
    # Tenancy
    "TenantManager",
    "TenantStatus",
    "TenantTier",
    "UsageRecord",
    "UsageSummary",
    "check_rate_limit",
    "check_tenant_limits",
    "create_api_key",
    # Service
    "create_app",
    "create_tenant",
    "export_metrics",
    "get_metrics_collector",
    "get_tenant",
    "get_tenant_manager",
    "increment_counter",
    "observe_histogram",
    "record_usage",
    "reset_metrics_collector",
    "reset_tenant_manager",
    "revoke_api_key",
    "set_gauge",
    "verify_api_key",
]
