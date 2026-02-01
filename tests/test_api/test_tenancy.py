"""Tests for multi-tenancy support."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from primr.api.tenancy import (
    TenantManager,
    Tenant,
    TenantTier,
    TenantStatus,
    TenantLimits,
    TenantConfig,
    UsageRecord,
    UsageSummary,
    get_tenant_manager,
    reset_tenant_manager,
    create_tenant,
    get_tenant,
    record_usage,
    check_tenant_limits,
)


@pytest.fixture
def manager():
    """Create a fresh tenant manager for each test."""
    reset_tenant_manager()
    return TenantManager()


@pytest.fixture
def sample_tenant(manager):
    """Create a sample tenant."""
    return manager.create_tenant(
        name="Test Company",
        tier=TenantTier.PROFESSIONAL,
        owner_email="test@example.com",
    )


class TestTenantTier:
    """Tests for TenantTier enum."""
    
    def test_tier_values(self):
        """Test tier enum values."""
        assert TenantTier.FREE.value == "free"
        assert TenantTier.STARTER.value == "starter"
        assert TenantTier.PROFESSIONAL.value == "professional"
        assert TenantTier.ENTERPRISE.value == "enterprise"
    
    def test_all_tiers_exist(self):
        """Test all expected tiers exist."""
        tiers = list(TenantTier)
        assert len(tiers) == 4


class TestTenantStatus:
    """Tests for TenantStatus enum."""
    
    def test_status_values(self):
        """Test status enum values."""
        assert TenantStatus.ACTIVE.value == "active"
        assert TenantStatus.SUSPENDED.value == "suspended"
        assert TenantStatus.PENDING.value == "pending"
        assert TenantStatus.DELETED.value == "deleted"


class TestTenantLimits:
    """Tests for TenantLimits dataclass."""
    
    def test_default_limits(self):
        """Test default limit values."""
        limits = TenantLimits()
        assert limits.max_requests_per_day == 100
        assert limits.max_requests_per_month == 1000
        assert limits.max_concurrent_jobs == 2
    
    def test_free_tier_limits(self):
        """Test FREE tier limits."""
        limits = TenantLimits.for_tier(TenantTier.FREE)
        assert limits.max_requests_per_day == 10
        assert limits.max_requests_per_month == 100
        assert limits.max_concurrent_jobs == 1
        assert limits.priority_boost == 0
    
    def test_starter_tier_limits(self):
        """Test STARTER tier limits."""
        limits = TenantLimits.for_tier(TenantTier.STARTER)
        assert limits.max_requests_per_day == 50
        assert limits.max_requests_per_month == 500
        assert limits.max_concurrent_jobs == 2
        assert limits.priority_boost == 1
    
    def test_professional_tier_limits(self):
        """Test PROFESSIONAL tier limits."""
        limits = TenantLimits.for_tier(TenantTier.PROFESSIONAL)
        assert limits.max_requests_per_day == 200
        assert limits.max_requests_per_month == 2000
        assert limits.max_concurrent_jobs == 5
        assert limits.priority_boost == 2
    
    def test_enterprise_tier_limits(self):
        """Test ENTERPRISE tier limits."""
        limits = TenantLimits.for_tier(TenantTier.ENTERPRISE)
        assert limits.max_requests_per_day == 1000
        assert limits.max_requests_per_month == 10000
        assert limits.max_concurrent_jobs == 20
        assert limits.priority_boost == 3


class TestTenantConfig:
    """Tests for TenantConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = TenantConfig()
        assert config.custom_prompts == {}
        assert config.default_output_format == "markdown"
        assert config.webhook_url is None
        assert config.allowed_domains == []
        assert config.blocked_domains == []
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = TenantConfig(
            custom_prompts={"summary": "Custom prompt"},
            webhook_url="https://example.com/webhook",
        )
        data = config.to_dict()
        assert data["custom_prompts"] == {"summary": "Custom prompt"}
        assert data["webhook_url"] == "https://example.com/webhook"
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "custom_prompts": {"test": "value"},
            "default_output_format": "html",
            "blocked_domains": ["blocked.com"],
        }
        config = TenantConfig.from_dict(data)
        assert config.custom_prompts == {"test": "value"}
        assert config.default_output_format == "html"
        assert config.blocked_domains == ["blocked.com"]
    
    def test_from_dict_with_missing_keys(self):
        """Test from_dict handles missing keys."""
        config = TenantConfig.from_dict({})
        assert config.default_output_format == "markdown"
        assert config.allowed_domains == []


class TestTenant:
    """Tests for Tenant dataclass."""
    
    def test_is_active(self, sample_tenant):
        """Test is_active property."""
        assert sample_tenant.is_active is True
    
    def test_is_active_when_suspended(self, manager):
        """Test is_active when suspended."""
        tenant = manager.create_tenant("Test", TenantTier.FREE)
        manager.update_tenant(tenant.tenant_id, status=TenantStatus.SUSPENDED)
        updated = manager.get_tenant(tenant.tenant_id)
        assert updated.is_active is False
    
    def test_can_access_domain_default(self, sample_tenant):
        """Test domain access with no restrictions."""
        assert sample_tenant.can_access_domain("example.com") is True
        assert sample_tenant.can_access_domain("any-domain.org") is True
    
    def test_can_access_domain_blocked(self, manager):
        """Test blocked domain access."""
        config = TenantConfig(blocked_domains=["blocked.com", "evil.org"])
        tenant = manager.create_tenant("Test", config=config)
        
        assert tenant.can_access_domain("blocked.com") is False
        assert tenant.can_access_domain("sub.blocked.com") is False
        assert tenant.can_access_domain("allowed.com") is True
    
    def test_can_access_domain_whitelist(self, manager):
        """Test whitelisted domain access."""
        config = TenantConfig(allowed_domains=["allowed.com", "trusted.org"])
        tenant = manager.create_tenant("Test", config=config)
        
        assert tenant.can_access_domain("allowed.com") is True
        assert tenant.can_access_domain("sub.allowed.com") is True
        assert tenant.can_access_domain("other.com") is False


class TestTenantManager:
    """Tests for TenantManager class."""
    
    def test_create_tenant(self, manager):
        """Test tenant creation."""
        tenant = manager.create_tenant(
            name="New Company",
            tier=TenantTier.STARTER,
            owner_email="owner@company.com",
        )
        
        assert tenant.name == "New Company"
        assert tenant.tier == TenantTier.STARTER
        assert tenant.status == TenantStatus.ACTIVE
        assert tenant.owner_email == "owner@company.com"
        assert len(tenant.tenant_id) == 16
    
    def test_create_tenant_default_tier(self, manager):
        """Test tenant creation with default tier."""
        tenant = manager.create_tenant(name="Free User")
        assert tenant.tier == TenantTier.FREE
    
    def test_get_tenant(self, manager, sample_tenant):
        """Test getting tenant by ID."""
        retrieved = manager.get_tenant(sample_tenant.tenant_id)
        assert retrieved is not None
        assert retrieved.name == sample_tenant.name
        assert retrieved.tier == sample_tenant.tier
    
    def test_get_tenant_not_found(self, manager):
        """Test getting non-existent tenant."""
        result = manager.get_tenant("nonexistent")
        assert result is None
    
    def test_get_tenant_uses_cache(self, manager, sample_tenant):
        """Test that get_tenant uses cache."""
        # First call populates cache
        tenant1 = manager.get_tenant(sample_tenant.tenant_id)
        # Second call should use cache
        tenant2 = manager.get_tenant(sample_tenant.tenant_id)
        assert tenant1 is tenant2  # Same object from cache
    
    def test_update_tenant_name(self, manager, sample_tenant):
        """Test updating tenant name."""
        updated = manager.update_tenant(
            sample_tenant.tenant_id,
            name="Updated Name",
        )
        assert updated.name == "Updated Name"
    
    def test_update_tenant_tier(self, manager, sample_tenant):
        """Test updating tenant tier."""
        updated = manager.update_tenant(
            sample_tenant.tenant_id,
            tier=TenantTier.ENTERPRISE,
        )
        assert updated.tier == TenantTier.ENTERPRISE
        # Limits should be updated to match tier
        assert updated.limits.max_requests_per_day == 1000
    
    def test_update_tenant_status(self, manager, sample_tenant):
        """Test updating tenant status."""
        updated = manager.update_tenant(
            sample_tenant.tenant_id,
            status=TenantStatus.SUSPENDED,
        )
        assert updated.status == TenantStatus.SUSPENDED
    
    def test_update_tenant_config(self, manager, sample_tenant):
        """Test updating tenant config."""
        new_config = TenantConfig(webhook_url="https://new.webhook.com")
        updated = manager.update_tenant(
            sample_tenant.tenant_id,
            config=new_config,
        )
        assert updated.config.webhook_url == "https://new.webhook.com"
    
    def test_update_tenant_custom_limits(self, manager, sample_tenant):
        """Test updating tenant with custom limits."""
        custom_limits = TenantLimits(
            max_requests_per_day=500,
            max_concurrent_jobs=10,
        )
        updated = manager.update_tenant(
            sample_tenant.tenant_id,
            limits=custom_limits,
        )
        assert updated.limits.max_requests_per_day == 500
        assert updated.limits.max_concurrent_jobs == 10
    
    def test_update_nonexistent_tenant(self, manager):
        """Test updating non-existent tenant."""
        result = manager.update_tenant("nonexistent", name="New Name")
        assert result is None
    
    def test_delete_tenant_soft(self, manager, sample_tenant):
        """Test soft delete (mark as deleted)."""
        result = manager.delete_tenant(sample_tenant.tenant_id)
        assert result is True
        
        tenant = manager.get_tenant(sample_tenant.tenant_id)
        assert tenant.status == TenantStatus.DELETED
    
    def test_delete_tenant_hard(self, manager, sample_tenant):
        """Test hard delete (permanent)."""
        result = manager.delete_tenant(sample_tenant.tenant_id, hard_delete=True)
        assert result is True
        
        tenant = manager.get_tenant(sample_tenant.tenant_id)
        assert tenant is None
    
    def test_list_tenants(self, manager):
        """Test listing all tenants."""
        manager.create_tenant("Company A", TenantTier.FREE)
        manager.create_tenant("Company B", TenantTier.STARTER)
        manager.create_tenant("Company C", TenantTier.PROFESSIONAL)
        
        tenants = manager.list_tenants()
        assert len(tenants) == 3
    
    def test_list_tenants_filter_by_tier(self, manager):
        """Test listing tenants filtered by tier."""
        manager.create_tenant("Free 1", TenantTier.FREE)
        manager.create_tenant("Free 2", TenantTier.FREE)
        manager.create_tenant("Pro 1", TenantTier.PROFESSIONAL)
        
        free_tenants = manager.list_tenants(tier=TenantTier.FREE)
        assert len(free_tenants) == 2
    
    def test_list_tenants_filter_by_status(self, manager):
        """Test listing tenants filtered by status."""
        t1 = manager.create_tenant("Active", TenantTier.FREE)
        t2 = manager.create_tenant("Suspended", TenantTier.FREE)
        manager.update_tenant(t2.tenant_id, status=TenantStatus.SUSPENDED)
        
        active = manager.list_tenants(status=TenantStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].name == "Active"
    
    def test_list_tenants_pagination(self, manager):
        """Test listing tenants with pagination."""
        for i in range(5):
            manager.create_tenant(f"Company {i}", TenantTier.FREE)
        
        page1 = manager.list_tenants(limit=2, offset=0)
        page2 = manager.list_tenants(limit=2, offset=2)
        
        assert len(page1) == 2
        assert len(page2) == 2
    
    def test_clear_cache(self, manager, sample_tenant):
        """Test clearing the cache."""
        # Populate cache
        manager.get_tenant(sample_tenant.tenant_id)
        assert sample_tenant.tenant_id in manager._tenant_cache
        
        manager.clear_cache()
        assert len(manager._tenant_cache) == 0


class TestUsageTracking:
    """Tests for usage tracking."""
    
    def test_record_usage(self, manager, sample_tenant):
        """Test recording usage."""
        record = manager.record_usage(
            tenant_id=sample_tenant.tenant_id,
            request_type="research",
            resource_used="requests",
            quantity=1,
        )
        
        assert record.tenant_id == sample_tenant.tenant_id
        assert record.request_type == "research"
        assert record.resource_used == "requests"
        assert record.quantity == 1
    
    def test_record_usage_with_metadata(self, manager, sample_tenant):
        """Test recording usage with metadata."""
        record = manager.record_usage(
            tenant_id=sample_tenant.tenant_id,
            request_type="research",
            resource_used="pages",
            quantity=15,
            metadata={"company": "Example Corp", "job_id": "abc123"},
        )
        
        assert record.metadata["company"] == "Example Corp"
        assert record.metadata["job_id"] == "abc123"
    
    def test_get_usage_summary(self, manager, sample_tenant):
        """Test getting usage summary."""
        # Record some usage
        for _ in range(5):
            manager.record_usage(
                sample_tenant.tenant_id, "research", "requests", 1
            )
        manager.record_usage(
            sample_tenant.tenant_id, "research", "pages", 25
        )
        manager.record_usage(
            sample_tenant.tenant_id, "research", "tokens", 5000
        )
        
        summary = manager.get_usage_summary(sample_tenant.tenant_id)
        
        assert summary.tenant_id == sample_tenant.tenant_id
        assert summary.total_requests == 5
        assert summary.total_pages_scraped == 25
        assert summary.total_ai_tokens == 5000
    
    def test_get_usage_summary_by_type(self, manager, sample_tenant):
        """Test usage summary includes requests by type."""
        manager.record_usage(sample_tenant.tenant_id, "research", "requests", 1)
        manager.record_usage(sample_tenant.tenant_id, "research", "requests", 1)
        manager.record_usage(sample_tenant.tenant_id, "scrape", "requests", 1)
        
        summary = manager.get_usage_summary(sample_tenant.tenant_id)
        
        assert summary.requests_by_type.get("research", 0) == 2
        assert summary.requests_by_type.get("scrape", 0) == 1
    
    def test_get_usage_summary_custom_period(self, manager, sample_tenant):
        """Test usage summary with custom period."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        summary = manager.get_usage_summary(
            sample_tenant.tenant_id,
            period_start=yesterday,
            period_end=now,
        )
        
        assert summary.period_start == yesterday
        assert summary.period_end == now


class TestLimitChecking:
    """Tests for limit checking."""
    
    def test_check_limits_within_limits(self, manager, sample_tenant):
        """Test checking limits when within limits."""
        limits = manager.check_limits(sample_tenant.tenant_id)
        
        assert limits["tenant_id"] == sample_tenant.tenant_id
        assert limits["tier"] == "professional"
        assert limits["daily_requests"]["exceeded"] is False
        assert limits["monthly_requests"]["exceeded"] is False
    
    def test_check_limits_exceeded(self, manager):
        """Test checking limits when exceeded."""
        tenant = manager.create_tenant("Limited", TenantTier.FREE)
        
        # Record usage up to limit
        for _ in range(10):
            manager.record_usage(tenant.tenant_id, "research", "requests", 1)
        
        limits = manager.check_limits(tenant.tenant_id)
        
        assert limits["daily_requests"]["used"] == 10
        assert limits["daily_requests"]["limit"] == 10
        assert limits["daily_requests"]["remaining"] == 0
        assert limits["daily_requests"]["exceeded"] is True
    
    def test_check_limits_nonexistent_tenant(self, manager):
        """Test checking limits for non-existent tenant."""
        result = manager.check_limits("nonexistent")
        assert "error" in result


class TestWorkspaceIsolation:
    """Tests for workspace isolation."""
    
    def test_get_workspace_path(self, manager, sample_tenant):
        """Test getting workspace path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = manager.get_workspace_path(
                sample_tenant.tenant_id,
                base_path=tmpdir,
            )
            
            assert path.exists()
            assert sample_tenant.tenant_id in str(path)
    
    def test_workspace_creates_subdirectories(self, manager, sample_tenant):
        """Test workspace creates required subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = manager.get_workspace_path(
                sample_tenant.tenant_id,
                base_path=tmpdir,
            )
            
            assert (path / "cache").exists()
            assert (path / "output").exists()
            assert (path / "logs").exists()
    
    def test_workspace_path_cached(self, manager, sample_tenant):
        """Test workspace path is cached in database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path1 = manager.get_workspace_path(
                sample_tenant.tenant_id,
                base_path=tmpdir,
            )
            path2 = manager.get_workspace_path(
                sample_tenant.tenant_id,
                base_path=tmpdir,
            )
            
            assert path1 == path2


class TestGlobalFunctions:
    """Tests for global convenience functions."""
    
    def test_get_tenant_manager(self):
        """Test getting global tenant manager."""
        reset_tenant_manager()
        manager1 = get_tenant_manager()
        manager2 = get_tenant_manager()
        assert manager1 is manager2
    
    def test_create_tenant_function(self):
        """Test create_tenant convenience function."""
        reset_tenant_manager()
        tenant = create_tenant("Test Company", TenantTier.STARTER)
        assert tenant.name == "Test Company"
        assert tenant.tier == TenantTier.STARTER
    
    def test_get_tenant_function(self):
        """Test get_tenant convenience function."""
        reset_tenant_manager()
        created = create_tenant("Test")
        retrieved = get_tenant(created.tenant_id)
        assert retrieved.name == "Test"
    
    def test_record_usage_function(self):
        """Test record_usage convenience function."""
        reset_tenant_manager()
        tenant = create_tenant("Test")
        record = record_usage(tenant.tenant_id, "research", "requests", 1)
        assert record.quantity == 1
    
    def test_check_tenant_limits_function(self):
        """Test check_tenant_limits convenience function."""
        reset_tenant_manager()
        tenant = create_tenant("Test")
        limits = check_tenant_limits(tenant.tenant_id)
        assert "daily_requests" in limits


class TestPersistence:
    """Tests for database persistence."""
    
    def test_persistence_across_instances(self):
        """Test data persists across manager instances."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            # Create tenant with first manager
            manager1 = TenantManager(db_path)
            tenant = manager1.create_tenant("Persistent", TenantTier.PROFESSIONAL)
            tenant_id = tenant.tenant_id
            manager1.close()  # Close before creating second manager
            
            # Retrieve with second manager
            manager2 = TenantManager(db_path)
            retrieved = manager2.get_tenant(tenant_id)
            
            assert retrieved is not None
            assert retrieved.name == "Persistent"
            assert retrieved.tier == TenantTier.PROFESSIONAL
            manager2.close()  # Close before cleanup
        finally:
            os.unlink(db_path)
    
    def test_usage_persists(self):
        """Test usage records persist."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            manager1 = TenantManager(db_path)
            tenant = manager1.create_tenant("Test")
            manager1.record_usage(tenant.tenant_id, "research", "requests", 1)
            manager1.close()  # Close before creating second manager
            
            manager2 = TenantManager(db_path)
            summary = manager2.get_usage_summary(tenant.tenant_id)
            
            assert summary.total_requests == 1
            manager2.close()  # Close before cleanup
        finally:
            os.unlink(db_path)
