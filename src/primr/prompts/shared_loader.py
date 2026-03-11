"""
Shared component loader for the prompt architecture.

This module loads and caches shared components (epistemic rules, formatting,
personas) from YAML files in the shared/ directory.

Usage:
    loader = SharedComponentLoader()
    components = loader.load()

    # Get a specific persona
    persona = components.get_persona("senior_consultant")

    # Get all epistemic rules
    rules = components.epistemic_rules
"""

from pathlib import Path
from typing import Any

import yaml

from primr.prompts.schema import SharedComponents
from primr.utils.logging_config import get_logger

logger = get_logger("prompts.shared_loader")

# Directory containing shared YAML files
SHARED_DIR = Path(__file__).parent / "shared"


class SharedComponentLoader:
    """
    Loads shared components from YAML files with caching.

    Components are loaded once and cached for the lifetime of the loader.
    Use reload() to force a fresh load.

    Example:
        loader = SharedComponentLoader()
        components = loader.load()

        # Access epistemic rules
        for name, rule in components.epistemic_rules.items():
            print(f"{name}: {rule}")
    """

    def __init__(self, shared_dir: Path | None = None):
        """
        Initialize the loader.

        Args:
            shared_dir: Optional custom path to shared components directory.
                       Defaults to src/primr/prompts/shared/
        """
        self._shared_dir = shared_dir or SHARED_DIR
        self._cache: SharedComponents | None = None

    @property
    def shared_dir(self) -> Path:
        """Get the shared components directory path."""
        return self._shared_dir

    def load(self) -> SharedComponents:
        """
        Load all shared components.

        Returns cached components if already loaded.

        Returns:
            SharedComponents with all loaded data

        Raises:
            FileNotFoundError: If shared directory doesn't exist
        """
        if self._cache is not None:
            return self._cache

        if not self._shared_dir.exists():
            raise FileNotFoundError(f"Shared components directory not found: {self._shared_dir}")

        components = SharedComponents()

        # Load epistemic rules
        epistemic_path = self._shared_dir / "epistemic_rules.yaml"
        if epistemic_path.exists():
            epistemic_data = self._load_yaml(epistemic_path)
            components.epistemic_rules = epistemic_data.get("rules", {})
            components.strategy_rules = epistemic_data.get("strategy_rules", {})
            logger.debug(f"Loaded {len(components.epistemic_rules)} epistemic rules")

        # Load formatting rules
        formatting_path = self._shared_dir / "formatting.yaml"
        if formatting_path.exists():
            formatting_data = self._load_yaml(formatting_path)
            components.formatting_rules = formatting_data.get("rules", {})
            components.structure_rules = formatting_data.get("structure", {})
            components.table_rules = formatting_data.get("table_rules", {})
            logger.debug(f"Loaded {len(components.formatting_rules)} formatting rules")

        # Load personas
        personas_path = self._shared_dir / "personas.yaml"
        if personas_path.exists():
            personas_data = self._load_yaml(personas_path)
            components.personas = personas_data.get("personas", {})
            components.default_persona = personas_data.get("default", "senior_consultant")
            logger.debug(f"Loaded {len(components.personas)} personas")

        self._cache = components
        return components

    def reload(self) -> SharedComponents:
        """
        Force reload of all shared components.

        Clears the cache and loads fresh from disk.

        Returns:
            SharedComponents with freshly loaded data
        """
        self._cache = None
        return self.load()

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """
        Load a YAML file.

        Args:
            path: Path to the YAML file

        Returns:
            Parsed YAML content as dictionary

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If YAML is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {path}")

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data is None:
                    return {}
                if not isinstance(data, dict):
                    raise ValueError(f"YAML must be a dictionary: {path}")
                return data
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}") from e


# Module-level singleton for convenience
_default_loader: SharedComponentLoader | None = None


def get_shared_loader() -> SharedComponentLoader:
    """
    Get the default shared component loader.

    Returns a singleton instance for convenience.

    Returns:
        SharedComponentLoader instance
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = SharedComponentLoader()
    return _default_loader


def load_shared_components() -> SharedComponents:
    """
    Load shared components using the default loader.

    Convenience function for quick access to shared components.

    Returns:
        SharedComponents with all loaded data
    """
    return get_shared_loader().load()
