"""
Strategy Module Registry for the prompt architecture.

This module discovers and manages strategy modules from the strategies/ directory.
Each strategy module is a YAML configuration that defines a specific type of
strategic analysis (AI, cloud, data, security, etc.).

Usage:
    registry = StrategyModuleRegistry()
    strategies = registry.discover()
    
    # Get a specific strategy
    ai_strategy = registry.get("ai")
    
    # Get context files for a strategy
    context_files = registry.get_context_files("ai", vendor="azure")
"""

from pathlib import Path
from typing import Any

import yaml

from primr.prompts.exceptions import (
    PromptConfigValidationError,
    StrategyModuleNotFoundError,
)
from primr.prompts.schema import DataSource, StrategyModule
from primr.utils.logging_config import get_logger

logger = get_logger("prompts.registry")

# Default directories
PROMPTS_DIR = Path(__file__).parent
STRATEGIES_DIR = PROMPTS_DIR / "strategies"
DATA_DIR = Path(__file__).parent.parent.parent.parent / "docs"  # Project root/docs


class StrategyModuleRegistry:
    """
    Registry for discovering and loading strategy modules.

    Automatically discovers modules from the strategies/ directory.
    Each module can specify associated data sources that provide
    current context to the Deep Research agent.

    Example:
        registry = StrategyModuleRegistry()
        
        # List all strategies
        for name in registry.list_names():
            print(name)
        
        # Get context files for AI strategy with Azure vendor
        files = registry.get_context_files("ai", vendor="azure")
    """

    def __init__(
        self,
        strategies_dir: Path | None = None,
        data_dir: Path | None = None,
    ):
        """
        Initialize the registry.

        Args:
            strategies_dir: Path to strategies/ YAML configs
            data_dir: Path to data files (defaults to docs/)
        """
        self._strategies_dir = strategies_dir or STRATEGIES_DIR
        self._data_dir = data_dir or DATA_DIR
        self._cache: dict[str, StrategyModule] | None = None

    @property
    def strategies_dir(self) -> Path:
        """Get the strategies directory path."""
        return self._strategies_dir

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return self._data_dir

    def discover(self) -> list[StrategyModule]:
        """
        Discover all available strategy modules.

        Scans the strategies/ directory for YAML files and loads their metadata.

        Returns:
            List of StrategyModule objects
        """
        if self._cache is not None:
            return list(self._cache.values())

        self._cache = {}

        if not self._strategies_dir.exists():
            logger.debug(f"Strategies directory not found: {self._strategies_dir}")
            return []

        for path in self._strategies_dir.glob("*.yaml"):
            try:
                module = self._load_module(path)
                self._cache[module.name] = module
                logger.debug(f"Discovered strategy module: {module.name}")
            except Exception as e:
                logger.warning(f"Failed to load strategy module {path}: {e}")

        return list(self._cache.values())

    def get(self, name: str) -> StrategyModule | None:
        """
        Get a specific strategy module by name.

        Args:
            name: Strategy name (e.g., "ai", "cloud")

        Returns:
            StrategyModule if found, None otherwise
        """
        # Ensure discovery has run
        if self._cache is None:
            self.discover()

        return self._cache.get(name) if self._cache else None

    def list_names(self) -> list[str]:
        """
        List all strategy module names.

        Returns:
            Sorted list of strategy names
        """
        # Ensure discovery has run
        if self._cache is None:
            self.discover()

        return sorted(self._cache.keys()) if self._cache else []

    def get_context_files(
        self,
        name: str,
        vendor: str | None = None,
    ) -> list[Path]:
        """
        Get context files for a strategy module.

        Args:
            name: Strategy name (e.g., "ai")
            vendor: Optional vendor filter (e.g., "azure", "aws", "gcp")

        Returns:
            List of paths to existing context files
        """
        module = self.get(name)
        if module is None:
            return []

        return module.get_context_files(self._data_dir, vendor)

    def reload(self) -> list[StrategyModule]:
        """
        Force reload of all strategy modules.

        Clears the cache and rediscovers modules.

        Returns:
            List of StrategyModule objects
        """
        self._cache = None
        return self.discover()

    def _load_module(self, path: Path) -> StrategyModule:
        """
        Load a strategy module from a YAML file.

        Args:
            path: Path to the YAML file

        Returns:
            StrategyModule with metadata

        Raises:
            ValueError: If the YAML is invalid
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise PromptConfigValidationError(
                config_path=str(path),
                errors=[f"YAML parse error: {e}"],
            ) from e

        if not data:
            raise PromptConfigValidationError(
                config_path=str(path),
                errors=["Empty YAML file"],
            )

        meta = data.get("meta", {})

        # Extract name from filename or meta
        name = path.stem
        if name.endswith("_strategy"):
            name = name[:-9]  # Remove _strategy suffix

        # Parse data sources
        data_sources = []
        for ds_data in data.get("data_sources", []):
            data_sources.append(DataSource.from_dict(ds_data))

        return StrategyModule(
            name=name,
            display_name=meta.get("name", name.replace("_", " ").title()),
            description=meta.get("description", ""),
            config_path=path,
            is_builtin=True,  # All discovered modules are considered builtin
            data_sources=data_sources,
        )


# Module-level singleton for convenience
_default_registry: StrategyModuleRegistry | None = None


def get_registry() -> StrategyModuleRegistry:
    """
    Get the default strategy module registry.

    Returns a singleton instance for convenience.

    Returns:
        StrategyModuleRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = StrategyModuleRegistry()
    return _default_registry


def list_strategies() -> list[str]:
    """
    List all available strategy modules.

    Convenience function for quick access.

    Returns:
        List of strategy names
    """
    return get_registry().list_names()
