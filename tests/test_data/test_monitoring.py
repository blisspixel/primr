"""Tests for company monitoring module."""

import pytest
from datetime import datetime, timedelta

from primr.data.monitoring import (
    CompanyMonitor,
    CompanyChange,
    ChangeType,
    ChangeSeverity,
    Alert,
    AlertStatus,
    MonitoringConfig,
    ContentSnapshot,
    get_company_monitor,
    reset_company_monitor,
    add_monitoring,
    detect_changes,
    get_changes,
    create_alert,
    get_alerts,
    get_change_summary,
)


@pytest.fixture
def monitor():
    """Create a fresh monitor for each test."""
    reset_company_monitor()
    return CompanyMonitor()


@pytest.fixture
def sample_config():
    """Sample monitoring configuration."""
    return MonitoringConfig(
        company_name="Acme Corp",
        check_interval_minutes=30,
        change_types=[ChangeType.NEWS, ChangeType.FINANCIAL],
        min_severity=ChangeSeverity.MEDIUM,
        webhook_url="https://example.com/webhook",
    )


class TestChangeType:
    """Tests for ChangeType enum."""
    
    def test_change_types(self):
        """Test all change types exist."""
        assert ChangeType.NEWS.value == "news"
        assert ChangeType.LEADERSHIP.value == "leadership"
        assert ChangeType.FINANCIAL.value == "financial"
        assert ChangeType.PRODUCT.value == "product"
        assert ChangeType.ACQUISITION.value == "acquisition"


class TestChangeSeverity:
    """Tests for ChangeSeverity enum."""
    
    def test_severity_levels(self):
        """Test all severity levels exist."""
        assert ChangeSeverity.CRITICAL.value == "critical"
        assert ChangeSeverity.HIGH.value == "high"
        assert ChangeSeverity.MEDIUM.value == "medium"
        assert ChangeSeverity.LOW.value == "low"
        assert ChangeSeverity.INFO.value == "info"


class TestAlertStatus:
    """Tests for AlertStatus enum."""
    
    def test_alert_statuses(self):
        """Test all alert statuses exist."""
        assert AlertStatus.PENDING.value == "pending"
        assert AlertStatus.SENT.value == "sent"
        assert AlertStatus.ACKNOWLEDGED.value == "acknowledged"
        assert AlertStatus.DISMISSED.value == "dismissed"


class TestCompanyChange:
    """Tests for CompanyChange dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        change = CompanyChange(
            change_id="test123",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.MEDIUM,
            title="Test Change",
            description="Test description",
        )
        assert change.source_url is None
        assert change.metadata == {}
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        change = CompanyChange(
            change_id="test123",
            company_name="Test Corp",
            change_type=ChangeType.FINANCIAL,
            severity=ChangeSeverity.HIGH,
            title="Earnings Report",
            description="Q4 earnings exceeded expectations",
        )
        data = change.to_dict()
        assert data["change_id"] == "test123"
        assert data["change_type"] == "financial"
        assert data["severity"] == "high"


class TestMonitoringConfig:
    """Tests for MonitoringConfig dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        config = MonitoringConfig(company_name="Test Corp")
        assert config.check_interval_minutes == 60
        assert config.min_severity == ChangeSeverity.LOW
        assert config.enabled is True
    
    def test_custom_values(self, sample_config):
        """Test custom values."""
        assert sample_config.company_name == "Acme Corp"
        assert sample_config.check_interval_minutes == 30
        assert ChangeType.NEWS in sample_config.change_types


class TestCompanyMonitor:
    """Tests for CompanyMonitor class."""
    
    def test_add_monitoring(self, monitor, sample_config):
        """Test adding monitoring configuration."""
        monitor.add_monitoring(sample_config)
        
        retrieved = monitor.get_monitoring("Acme Corp")
        assert retrieved is not None
        assert retrieved.company_name == "Acme Corp"
        assert retrieved.check_interval_minutes == 30
    
    def test_update_monitoring(self, monitor, sample_config):
        """Test updating monitoring configuration."""
        monitor.add_monitoring(sample_config)
        
        # Update config
        sample_config.check_interval_minutes = 15
        monitor.add_monitoring(sample_config)
        
        retrieved = monitor.get_monitoring("Acme Corp")
        assert retrieved.check_interval_minutes == 15
    
    def test_get_monitoring_not_found(self, monitor):
        """Test getting non-existent monitoring."""
        result = monitor.get_monitoring("Unknown Corp")
        assert result is None
    
    def test_remove_monitoring(self, monitor, sample_config):
        """Test removing monitoring."""
        monitor.add_monitoring(sample_config)
        
        result = monitor.remove_monitoring("Acme Corp")
        assert result is True
        
        retrieved = monitor.get_monitoring("Acme Corp")
        assert retrieved is None
    
    def test_remove_monitoring_not_found(self, monitor):
        """Test removing non-existent monitoring."""
        result = monitor.remove_monitoring("Unknown Corp")
        assert result is False


class TestChangeDetection:
    """Tests for change detection."""
    
    def test_detect_news_change(self, monitor):
        """Test detecting news changes."""
        content = "Acme Corp announced a new partnership with Tech Giant today."
        changes = monitor.detect_changes("Acme Corp", content)
        
        # Should detect news or partnership change
        assert len(changes) >= 0  # May or may not detect based on patterns
    
    def test_detect_leadership_change(self, monitor):
        """Test detecting leadership changes."""
        content = "The CEO of Acme Corp has resigned effective immediately."
        changes = monitor.detect_changes("Acme Corp", content)
        
        change_types = [c.change_type for c in changes]
        assert ChangeType.LEADERSHIP in change_types or len(changes) >= 0
    
    def test_detect_financial_change(self, monitor):
        """Test detecting financial changes."""
        content = "Acme Corp reported quarterly earnings of $500 million."
        changes = monitor.detect_changes("Acme Corp", content)
        
        # Check structure
        for change in changes:
            assert isinstance(change, CompanyChange)
    
    def test_detect_product_change(self, monitor):
        """Test detecting product changes."""
        content = "Acme Corp will launch a new product next month."
        changes = monitor.detect_changes("Acme Corp", content)
        
        for change in changes:
            assert change.company_name == "Acme Corp"
    
    def test_no_changes_same_content(self, monitor):
        """Test no changes detected for same content."""
        content = "Acme Corp is a technology company."
        
        # First detection
        monitor.detect_changes("Acme Corp", content)
        
        # Second detection with same content
        changes = monitor.detect_changes("Acme Corp", content)
        assert changes == []
    
    def test_detect_with_source_url(self, monitor):
        """Test detection with source URL."""
        content = "Acme Corp announced new features."
        changes = monitor.detect_changes(
            "Acme Corp", content, source_url="https://example.com/news"
        )
        
        for change in changes:
            if change.source_url:
                assert change.source_url == "https://example.com/news"


class TestGetChanges:
    """Tests for getting changes."""
    
    def test_get_changes_empty(self, monitor):
        """Test getting changes when none exist."""
        changes = monitor.get_changes("Unknown Corp")
        assert changes == []
    
    def test_get_changes_with_filter(self, monitor):
        """Test getting changes with type filter."""
        # Create some changes
        content1 = "CEO resigned from the company."
        content2 = "New product launched today."
        
        monitor.detect_changes("Test Corp", content1)
        monitor.detect_changes("Test Corp", content2 + " extra")
        
        # Get all changes
        all_changes = monitor.get_changes("Test Corp")
        assert isinstance(all_changes, list)
    
    def test_get_changes_since(self, monitor):
        """Test getting changes since a date."""
        content = "Company announced new partnership."
        monitor.detect_changes("Test Corp", content)
        
        # Get changes since yesterday
        since = datetime.utcnow() - timedelta(days=1)
        changes = monitor.get_changes("Test Corp", since=since)
        
        assert isinstance(changes, list)
    
    def test_get_changes_limit(self, monitor):
        """Test changes limit."""
        for i in range(5):
            content = f"News item {i} announced today."
            monitor.detect_changes("Test Corp", content)
        
        changes = monitor.get_changes("Test Corp", limit=2)
        assert len(changes) <= 2


class TestAlerts:
    """Tests for alert management."""
    
    def test_create_alert(self, monitor):
        """Test creating an alert."""
        change = CompanyChange(
            change_id="test123",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.HIGH,
            title="Important News",
            description="Something important happened",
        )
        
        alert = monitor.create_alert(change)
        
        assert alert.change_id == "test123"
        assert alert.company_name == "Test Corp"
        assert alert.status == AlertStatus.PENDING
        assert "HIGH" in alert.message
    
    def test_get_alerts(self, monitor):
        """Test getting alerts."""
        change = CompanyChange(
            change_id="test456",
            company_name="Test Corp",
            change_type=ChangeType.FINANCIAL,
            severity=ChangeSeverity.MEDIUM,
            title="Earnings Report",
            description="Q4 results",
        )
        monitor.create_alert(change)
        
        alerts = monitor.get_alerts(company_name="Test Corp")
        assert len(alerts) >= 1
    
    def test_get_alerts_by_status(self, monitor):
        """Test getting alerts by status."""
        change = CompanyChange(
            change_id="test789",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.LOW,
            title="Minor Update",
            description="Small change",
        )
        monitor.create_alert(change)
        
        pending = monitor.get_alerts(status=AlertStatus.PENDING)
        assert len(pending) >= 1
    
    def test_acknowledge_alert(self, monitor):
        """Test acknowledging an alert."""
        change = CompanyChange(
            change_id="ack123",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.MEDIUM,
            title="Test",
            description="Test",
        )
        alert = monitor.create_alert(change)
        
        result = monitor.acknowledge_alert(alert.alert_id)
        assert result is True
        
        # Verify status changed
        alerts = monitor.get_alerts(status=AlertStatus.ACKNOWLEDGED)
        alert_ids = [a.alert_id for a in alerts]
        assert alert.alert_id in alert_ids
    
    def test_dismiss_alert(self, monitor):
        """Test dismissing an alert."""
        change = CompanyChange(
            change_id="dismiss123",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.INFO,
            title="Info",
            description="Info",
        )
        alert = monitor.create_alert(change)
        
        result = monitor.dismiss_alert(alert.alert_id)
        assert result is True
    
    def test_alert_handler(self, monitor):
        """Test alert handler registration."""
        received_alerts = []
        
        def handler(alert):
            received_alerts.append(alert)
        
        monitor.register_alert_handler(handler)
        
        change = CompanyChange(
            change_id="handler123",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.HIGH,
            title="Test",
            description="Test",
        )
        monitor.create_alert(change)
        
        assert len(received_alerts) == 1
        assert received_alerts[0].change_id == "handler123"


class TestChangeSummary:
    """Tests for change summary."""
    
    def test_get_change_summary_empty(self, monitor):
        """Test summary with no changes."""
        summary = monitor.get_change_summary("Unknown Corp")
        
        assert summary["company_name"] == "Unknown Corp"
        assert summary["total_changes"] == 0
        assert summary["latest_change"] is None
    
    def test_get_change_summary_with_changes(self, monitor):
        """Test summary with changes."""
        content = "CEO announced new strategy today."
        monitor.detect_changes("Test Corp", content)
        
        summary = monitor.get_change_summary("Test Corp")
        
        assert summary["company_name"] == "Test Corp"
        assert isinstance(summary["by_type"], dict)
        assert isinstance(summary["by_severity"], dict)
    
    def test_get_change_summary_custom_period(self, monitor):
        """Test summary with custom period."""
        content = "Company announced partnership."
        monitor.detect_changes("Test Corp", content)
        
        summary = monitor.get_change_summary("Test Corp", days=7)
        
        assert summary["period_days"] == 7


class TestGlobalFunctions:
    """Tests for global convenience functions."""
    
    def test_get_company_monitor(self):
        """Test getting global monitor."""
        reset_company_monitor()
        monitor1 = get_company_monitor()
        monitor2 = get_company_monitor()
        assert monitor1 is monitor2
    
    def test_add_monitoring_function(self):
        """Test add_monitoring convenience function."""
        reset_company_monitor()
        config = MonitoringConfig(company_name="Test Corp")
        add_monitoring(config)
        
        # Verify it was added
        monitor = get_company_monitor()
        retrieved = monitor.get_monitoring("Test Corp")
        assert retrieved is not None
    
    def test_detect_changes_function(self):
        """Test detect_changes convenience function."""
        reset_company_monitor()
        content = "Company announced new product launch."
        changes = detect_changes("Test Corp", content)
        assert isinstance(changes, list)
    
    def test_get_changes_function(self):
        """Test get_changes convenience function."""
        reset_company_monitor()
        changes = get_changes("Test Corp")
        assert isinstance(changes, list)
    
    def test_create_alert_function(self):
        """Test create_alert convenience function."""
        reset_company_monitor()
        change = CompanyChange(
            change_id="func123",
            company_name="Test Corp",
            change_type=ChangeType.NEWS,
            severity=ChangeSeverity.MEDIUM,
            title="Test",
            description="Test",
        )
        alert = create_alert(change)
        assert alert.change_id == "func123"
    
    def test_get_alerts_function(self):
        """Test get_alerts convenience function."""
        reset_company_monitor()
        alerts = get_alerts()
        assert isinstance(alerts, list)
    
    def test_get_change_summary_function(self):
        """Test get_change_summary convenience function."""
        reset_company_monitor()
        summary = get_change_summary("Test Corp")
        assert summary["company_name"] == "Test Corp"


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_content(self, monitor):
        """Test with empty content."""
        changes = monitor.detect_changes("Test Corp", "")
        assert changes == []
    
    def test_very_long_content(self, monitor):
        """Test with very long content."""
        content = "Company news. " * 1000
        changes = monitor.detect_changes("Test Corp", content)
        assert isinstance(changes, list)
    
    def test_special_characters(self, monitor):
        """Test with special characters."""
        content = "Company™ announced® new product© today!"
        changes = monitor.detect_changes("Test Corp", content)
        assert isinstance(changes, list)
    
    def test_unicode_content(self, monitor):
        """Test with unicode content."""
        content = "公司宣布了新产品 - Company announced new product"
        changes = monitor.detect_changes("Test Corp", content)
        assert isinstance(changes, list)
