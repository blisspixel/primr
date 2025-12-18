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
    # Service
    "create_app",
    "ResearchRequest",
    "ResearchResponse",
    "ResearchStatus",
    "JobStatus",
    "HealthResponse",
    # Auth
    "APIKeyAuth",
    "verify_api_key",
    "create_api_key",
    "revoke_api_key",
    # Rate limiting
    "RateLimiter",
    "RateLimitConfig",
    "check_rate_limit",
    # Metrics
    "MetricsCollector",
    "MetricType",
    "Histogram",
    "RequestMetrics",
    "get_metrics_collector",
    "reset_metrics_collector",
    "increment_counter",
    "set_gauge",
    "observe_histogram",
    "export_metrics",
    # Tenancy
    "TenantManager",
    "Tenant",
    "TenantTier",
    "TenantStatus",
    "TenantLimits",
    "TenantConfig",
    "UsageRecord",
    "UsageSummary",
    "get_tenant_manager",
    "reset_tenant_manager",
    "create_tenant",
    "get_tenant",
    "record_usage",
    "check_tenant_limits",
]
