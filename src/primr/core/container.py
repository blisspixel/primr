"""
Dependency injection container for the company researcher.

This module provides:
- Service registration and resolution
- Factory functions for creating configured services
- Easy mocking for tests

Usage:
    # Production
    container = get_container()
    scraper = container.get_scraper()

    # Testing
    container = Container()
    container.register_scraper(mock_scraper)
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from primr.types import (
    AIClientProtocol,
    CacheProtocol,
    ScraperProtocol,
)
from primr.utils.logging_config import get_logger

logger = get_logger("container")

T = TypeVar('T')


@dataclass
class ServiceDescriptor:
    """Describes how to create a service."""
    factory: Callable[[], Any]
    singleton: bool = True
    instance: Any | None = None


class Container:
    """
    Dependency injection container.

    Manages service registration and resolution with support for:
    - Singleton and transient services
    - Factory functions
    - Easy testing with mock services

    Example:
        container = Container()

        # Register services
        container.register("ai_client", lambda: AIClient())
        container.register("scraper", lambda: ParallelScraper())

        # Resolve services
        client = container.resolve("ai_client")

        # For testing
        container.register("ai_client", lambda: MockAIClient())
    """

    def __init__(self):
        """Initialize the container."""
        self._services: dict[str, ServiceDescriptor] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested resolution

    def register(
        self,
        name: str,
        factory: Callable[[], T],
        singleton: bool = True
    ) -> None:
        """
        Register a service.

        Args:
            name: Service name
            factory: Factory function to create the service
            singleton: If True, only one instance is created
        """
        with self._lock:
            self._services[name] = ServiceDescriptor(
                factory=factory,
                singleton=singleton
            )
            logger.debug(f"Registered service: {name} (singleton={singleton})")

    def resolve(self, name: str) -> Any:
        """
        Resolve a service by name.

        Args:
            name: Service name

        Returns:
            Service instance

        Raises:
            KeyError: If service is not registered
        """
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service '{name}' not registered")

            descriptor = self._services[name]

            if descriptor.singleton:
                if descriptor.instance is None:
                    descriptor.instance = descriptor.factory()
                return descriptor.instance
            else:
                return descriptor.factory()

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._services

    def reset(self, name: str | None = None) -> None:
        """
        Reset service instances.

        Args:
            name: Service name to reset, or None to reset all
        """
        with self._lock:
            if name is None:
                for descriptor in self._services.values():
                    descriptor.instance = None
            elif name in self._services:
                self._services[name].instance = None

    def clear(self) -> None:
        """Clear all registered services."""
        with self._lock:
            self._services.clear()

    # ==========================================================================
    # CONVENIENCE METHODS FOR COMMON SERVICES
    # ==========================================================================

    def register_ai_client(self, factory: Callable[[], AIClientProtocol]) -> None:
        """Register the AI client service."""
        self.register("ai_client", factory)

    def get_ai_client(self) -> AIClientProtocol:
        """Get the AI client service."""
        result: AIClientProtocol = self.resolve("ai_client")
        return result

    def register_scraper(self, factory: Callable[[], ScraperProtocol]) -> None:
        """Register the scraper service."""
        self.register("scraper", factory)

    def get_scraper(self) -> ScraperProtocol:
        """Get the scraper service."""
        result: ScraperProtocol = self.resolve("scraper")
        return result

    def register_cache(self, factory: Callable[[], CacheProtocol]) -> None:
        """Register the cache service."""
        self.register("cache", factory)

    def get_cache(self) -> CacheProtocol:
        """Get the cache service."""
        result: CacheProtocol = self.resolve("cache")
        return result


def create_default_container() -> Container:
    """
    Create a container with default production services.

    Returns:
        Configured Container instance
    """
    container = Container()

    # Register AI client
    def create_ai_client():
        from primr.ai.client import AIClient
        return AIClient()
    container.register("ai_client", create_ai_client)

    # Register parallel scraper
    def create_scraper():
        from primr.data.parallel_scraper import ParallelScraper
        return ParallelScraper()
    container.register("scraper", create_scraper)

    # Register adaptive scraper
    def create_adaptive_scraper():
        from primr.data.adaptive_scraper import AdaptiveScraper
        return AdaptiveScraper()
    container.register("adaptive_scraper", create_adaptive_scraper)

    # Register cache
    def create_cache():
        from primr.data.cache import ContentCache
        return ContentCache()
    container.register("cache", create_cache)

    # Register HTTP client
    def create_http_client():
        from primr.data.http_client import HTTPClient
        return HTTPClient()
    container.register("http_client", create_http_client)

    # Register domain learner
    def create_domain_learner():
        from primr.data.adaptive_scraper import DomainLearner
        return DomainLearner()
    container.register("domain_learner", create_domain_learner)

    logger.info("Default container created with production services")
    return container


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_container: Container | None = None
_container_lock = threading.Lock()


def get_container() -> Container:
    """
    Get the global container instance.

    Returns:
        Container instance with default services
    """
    global _container
    if _container is None:
        with _container_lock:
            if _container is None:
                _container = create_default_container()
    return _container


def set_container(container: Container) -> None:
    """
    Set the global container (useful for testing).

    Args:
        container: Container to use globally
    """
    global _container
    with _container_lock:
        _container = container


def reset_container() -> None:
    """Reset the global container."""
    global _container
    with _container_lock:
        _container = None


# =============================================================================
# SERVICE LOCATOR FUNCTIONS
# =============================================================================

def get_ai_client() -> AIClientProtocol:
    """Get the AI client from the global container."""
    return get_container().get_ai_client()


def get_scraper() -> ScraperProtocol:
    """Get the scraper from the global container."""
    return get_container().get_scraper()


def get_cache() -> CacheProtocol:
    """Get the cache from the global container."""
    return get_container().get_cache()
