"""
Tests for the dependency injection container.

Tests service registration, resolution, and mocking.
"""

import pytest
import threading
from unittest.mock import Mock, MagicMock

from primr.core.container import (
    Container,
    ServiceDescriptor,
    create_default_container,
    get_container,
    set_container,
    reset_container,
    get_ai_client,
    get_scraper,
    get_cache,
)
from primr.types import AIClientProtocol, ScraperProtocol, CacheProtocol


# =============================================================================
# SERVICE DESCRIPTOR TESTS
# =============================================================================

class TestServiceDescriptor:
    """Tests for ServiceDescriptor dataclass."""
    
    def test_default_values(self):
        """Test default descriptor values."""
        descriptor = ServiceDescriptor(factory=lambda: "test")
        
        assert descriptor.singleton is True
        assert descriptor.instance is None
    
    def test_custom_values(self):
        """Test custom descriptor values."""
        descriptor = ServiceDescriptor(
            factory=lambda: "test",
            singleton=False,
            instance="existing"
        )
        
        assert descriptor.singleton is False
        assert descriptor.instance == "existing"


# =============================================================================
# CONTAINER TESTS
# =============================================================================

class TestContainer:
    """Tests for Container class."""
    
    def test_initialization(self):
        """Test container initialization."""
        container = Container()
        assert container is not None
    
    def test_register_and_resolve(self):
        """Test basic registration and resolution."""
        container = Container()
        container.register("test_service", lambda: "test_value")
        
        result = container.resolve("test_service")
        
        assert result == "test_value"
    
    def test_singleton_behavior(self):
        """Test that singleton services return same instance."""
        container = Container()
        call_count = 0
        
        def factory():
            nonlocal call_count
            call_count += 1
            return {"id": call_count}
        
        container.register("service", factory, singleton=True)
        
        result1 = container.resolve("service")
        result2 = container.resolve("service")
        
        assert result1 is result2
        assert call_count == 1
    
    def test_transient_behavior(self):
        """Test that transient services return new instances."""
        container = Container()
        call_count = 0
        
        def factory():
            nonlocal call_count
            call_count += 1
            return {"id": call_count}
        
        container.register("service", factory, singleton=False)
        
        result1 = container.resolve("service")
        result2 = container.resolve("service")
        
        assert result1 is not result2
        assert call_count == 2
    
    def test_resolve_unregistered_raises(self):
        """Test that resolving unregistered service raises."""
        container = Container()
        
        with pytest.raises(KeyError, match="not registered"):
            container.resolve("nonexistent")
    
    def test_has_service(self):
        """Test checking if service exists."""
        container = Container()
        container.register("exists", lambda: "value")
        
        assert container.has("exists") is True
        assert container.has("not_exists") is False
    
    def test_reset_single_service(self):
        """Test resetting a single service."""
        container = Container()
        container.register("service", lambda: object())
        
        instance1 = container.resolve("service")
        container.reset("service")
        instance2 = container.resolve("service")
        
        assert instance1 is not instance2
    
    def test_reset_all_services(self):
        """Test resetting all services."""
        container = Container()
        container.register("service1", lambda: object())
        container.register("service2", lambda: object())
        
        instance1a = container.resolve("service1")
        instance2a = container.resolve("service2")
        
        container.reset()
        
        instance1b = container.resolve("service1")
        instance2b = container.resolve("service2")
        
        assert instance1a is not instance1b
        assert instance2a is not instance2b
    
    def test_clear(self):
        """Test clearing all services."""
        container = Container()
        container.register("service", lambda: "value")
        
        container.clear()
        
        assert container.has("service") is False
    
    def test_overwrite_registration(self):
        """Test that re-registering overwrites."""
        container = Container()
        container.register("service", lambda: "original")
        container.register("service", lambda: "new")
        
        result = container.resolve("service")
        
        assert result == "new"


# =============================================================================
# CONVENIENCE METHOD TESTS
# =============================================================================

class TestConvenienceMethods:
    """Tests for convenience methods."""
    
    def test_register_and_get_ai_client(self):
        """Test AI client convenience methods."""
        container = Container()
        mock_client = Mock(spec=AIClientProtocol)
        
        container.register_ai_client(lambda: mock_client)
        result = container.get_ai_client()
        
        assert result is mock_client
    
    def test_register_and_get_scraper(self):
        """Test scraper convenience methods."""
        container = Container()
        mock_scraper = Mock(spec=ScraperProtocol)
        
        container.register_scraper(lambda: mock_scraper)
        result = container.get_scraper()
        
        assert result is mock_scraper
    
    def test_register_and_get_cache(self):
        """Test cache convenience methods."""
        container = Container()
        mock_cache = Mock(spec=CacheProtocol)
        
        container.register_cache(lambda: mock_cache)
        result = container.get_cache()
        
        assert result is mock_cache


# =============================================================================
# DEFAULT CONTAINER TESTS
# =============================================================================

class TestDefaultContainer:
    """Tests for default container creation."""
    
    def test_create_default_container(self):
        """Test creating default container."""
        container = create_default_container()
        
        assert container.has("ai_client")
        assert container.has("scraper")
        assert container.has("cache")
        assert container.has("http_client")
        assert container.has("adaptive_scraper")
        assert container.has("domain_learner")
    
    def test_default_services_are_lazy(self):
        """Test that default services are created lazily."""
        container = create_default_container()
        
        # Services should not be instantiated yet
        descriptor = container._services["ai_client"]
        assert descriptor.instance is None


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for global container singleton."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_container()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_container()
    
    def test_get_container_singleton(self):
        """Test that get_container returns singleton."""
        container1 = get_container()
        container2 = get_container()
        
        assert container1 is container2
    
    def test_set_container(self):
        """Test setting custom container."""
        custom_container = Container()
        custom_container.register("custom", lambda: "custom_value")
        
        set_container(custom_container)
        
        result = get_container()
        assert result is custom_container
        assert result.resolve("custom") == "custom_value"
    
    def test_reset_container(self):
        """Test resetting container."""
        container1 = get_container()
        reset_container()
        container2 = get_container()
        
        assert container1 is not container2


# =============================================================================
# SERVICE LOCATOR TESTS
# =============================================================================

class TestServiceLocators:
    """Tests for service locator functions."""
    
    def setup_method(self):
        """Reset singleton before each test."""
        reset_container()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_container()
    
    def test_get_ai_client_from_locator(self):
        """Test getting AI client via locator."""
        container = Container()
        mock_client = Mock(spec=AIClientProtocol)
        container.register_ai_client(lambda: mock_client)
        set_container(container)
        
        result = get_ai_client()
        
        assert result is mock_client
    
    def test_get_scraper_from_locator(self):
        """Test getting scraper via locator."""
        container = Container()
        mock_scraper = Mock(spec=ScraperProtocol)
        container.register_scraper(lambda: mock_scraper)
        set_container(container)
        
        result = get_scraper()
        
        assert result is mock_scraper
    
    def test_get_cache_from_locator(self):
        """Test getting cache via locator."""
        container = Container()
        mock_cache = Mock(spec=CacheProtocol)
        container.register_cache(lambda: mock_cache)
        set_container(container)
        
        result = get_cache()
        
        assert result is mock_cache


# =============================================================================
# THREAD SAFETY TESTS
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety."""
    
    def test_concurrent_registration(self):
        """Test concurrent service registration."""
        container = Container()
        errors = []
        
        def register_services(start: int, count: int):
            try:
                for i in range(count):
                    container.register(f"service_{start + i}", lambda i=i: i)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=register_services, args=(i * 100, 100))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(container._services) == 500
    
    def test_concurrent_resolution(self):
        """Test concurrent service resolution."""
        container = Container()
        container.register("service", lambda: object())
        
        results = []
        errors = []
        lock = threading.Lock()
        
        def resolve_service(count: int):
            try:
                for _ in range(count):
                    result = container.resolve("service")
                    with lock:
                        results.append(result)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=resolve_service, args=(100,))
            for _ in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        # All should be same instance (singleton)
        assert all(r is results[0] for r in results)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for container usage."""
    
    def test_mock_services_for_testing(self):
        """Test using container for mocking in tests."""
        # Create test container with mocks
        container = Container()
        
        mock_ai = Mock(spec=AIClientProtocol)
        mock_ai.generate.return_value = "Mocked response"
        
        mock_scraper = Mock(spec=ScraperProtocol)
        mock_scraper.scrape.return_value = "Mocked content"
        
        container.register_ai_client(lambda: mock_ai)
        container.register_scraper(lambda: mock_scraper)
        
        # Use services
        ai = container.get_ai_client()
        scraper = container.get_scraper()
        
        assert ai.generate("test") == "Mocked response"
        assert scraper.scrape("https://test.com") == "Mocked content"
    
    def test_service_dependencies(self):
        """Test services that depend on other services."""
        container = Container()
        
        # Register base service
        container.register("config", lambda: {"timeout": 30})
        
        # Register service that depends on config
        def create_client():
            config = container.resolve("config")
            return {"client": True, "timeout": config["timeout"]}
        
        container.register("client", create_client)
        
        client = container.resolve("client")
        
        assert client["timeout"] == 30
