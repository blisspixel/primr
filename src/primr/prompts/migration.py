"""
Configuration Migration Tooling for Prompt Configurations.

This module provides tools for migrating YAML prompt configurations between
schema versions, with backup/restore functionality and dry-run support.

**Feature: phd-level-excellence**
**Validates: Requirements 7.1-7.6**

Components:
- MigrationStep: Defines a single migration transformation
- MigrationTool: Orchestrates version detection and migration application
- MigrationResult: Result of a migration operation
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from primr.prompts.validation import (
    SchemaVersion,
    CURRENT_SCHEMA_VERSION,
    ConfigValidator,
    SchemaVersionError,
)


@dataclass
class MigrationStep:
    """
    Defines a single migration transformation between schema versions.
    
    Attributes:
        from_version: Source schema version
        to_version: Target schema version
        description: Human-readable description of the migration
        transform: Function that transforms the config dict
    """
    from_version: SchemaVersion
    to_version: SchemaVersion
    description: str
    transform: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class MigrationResult:
    """
    Result of a migration operation.
    
    Attributes:
        success: Whether the migration succeeded
        original_version: Schema version before migration
        final_version: Schema version after migration
        backup_path: Path to backup file (if created)
        steps_applied: List of migration steps that were applied
        error: Error message if migration failed
        dry_run: Whether this was a dry-run (no files modified)
        preview: Preview of changes (for dry-run mode)
    """
    success: bool
    original_version: SchemaVersion
    final_version: SchemaVersion
    backup_path: Path | None = None
    steps_applied: list[str] = field(default_factory=list)
    error: str | None = None
    dry_run: bool = False
    preview: dict[str, Any] | None = None


class MigrationError(Exception):
    """Raised when a migration operation fails."""
    
    def __init__(self, message: str, original_version: str, target_version: str):
        super().__init__(message)
        self.original_version = original_version
        self.target_version = target_version


class MigrationTool:
    """
    Orchestrates configuration migrations between schema versions.
    
    Provides version detection, sequential migration application,
    backup/restore functionality, and dry-run mode.
    """
    
    def __init__(self):
        self._validator = ConfigValidator()
        self._migrations: list[MigrationStep] = self._build_migration_chain()
    
    def _build_migration_chain(self) -> list[MigrationStep]:
        """Build the chain of available migrations."""
        return [
            MigrationStep(
                from_version=SchemaVersion.V1_0,
                to_version=SchemaVersion.V1_1,
                description="Add output_format field to meta",
                transform=self._migrate_1_0_to_1_1,
            ),
            MigrationStep(
                from_version=SchemaVersion.V1_1,
                to_version=SchemaVersion.V2_0,
                description="Add position field to sections, restructure subsections",
                transform=self._migrate_1_1_to_2_0,
            ),
        ]
    
    def detect_version(self, config: dict[str, Any]) -> SchemaVersion:
        """
        Detect the schema version of a configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Detected SchemaVersion
            
        Raises:
            SchemaVersionError: If version is unsupported
        """
        version_str = config.get("meta", {}).get("schema_version", "1.0")
        
        try:
            return SchemaVersion(version_str)
        except ValueError:
            raise SchemaVersionError(
                f"Unknown schema version: {version_str}",
                current_version=CURRENT_SCHEMA_VERSION.value,
                unsupported_version=version_str,
            )
    
    def detect_version_from_file(self, config_path: Path) -> SchemaVersion:
        """
        Detect the schema version from a configuration file.
        
        Args:
            config_path: Path to the YAML configuration file
            
        Returns:
            Detected SchemaVersion
        """
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return self.detect_version(config)
    
    def get_migration_path(
        self,
        from_version: SchemaVersion,
        to_version: SchemaVersion | None = None,
    ) -> list[MigrationStep]:
        """
        Get the sequence of migrations needed to upgrade from one version to another.
        
        Args:
            from_version: Starting schema version
            to_version: Target schema version (defaults to CURRENT_SCHEMA_VERSION)
            
        Returns:
            List of MigrationStep objects in order of application
        """
        if to_version is None:
            to_version = CURRENT_SCHEMA_VERSION
        
        if from_version == to_version:
            return []
        
        # Build migration path
        path = []
        current = from_version
        
        while current != to_version:
            # Find migration from current version
            migration = next(
                (m for m in self._migrations if m.from_version == current),
                None
            )
            
            if migration is None:
                raise MigrationError(
                    f"No migration path from {current.value} to {to_version.value}",
                    original_version=from_version.value,
                    target_version=to_version.value,
                )
            
            path.append(migration)
            current = migration.to_version
        
        return path
