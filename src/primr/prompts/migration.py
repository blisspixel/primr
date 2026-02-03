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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from primr.prompts.validation import (
    CURRENT_SCHEMA_VERSION,
    ConfigValidator,
    SchemaVersion,
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
        except ValueError as e:
            raise SchemaVersionError(
                f"Unknown schema version: {version_str}",
                current_version=CURRENT_SCHEMA_VERSION.value,
                unsupported_version=version_str,
            ) from e

    def detect_version_from_file(self, config_path: Path) -> SchemaVersion:
        """
        Detect the schema version from a configuration file.

        Args:
            config_path: Path to the YAML configuration file

        Returns:
            Detected SchemaVersion
        """
        with open(config_path, encoding="utf-8") as f:
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

    def migrate(
        self,
        config: dict[str, Any],
        to_version: SchemaVersion | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Migrate a configuration dictionary to a target version.

        Args:
            config: Configuration dictionary to migrate
            to_version: Target schema version (defaults to CURRENT_SCHEMA_VERSION)

        Returns:
            Tuple of (migrated_config, list_of_applied_step_descriptions)
        """
        if to_version is None:
            to_version = CURRENT_SCHEMA_VERSION

        from_version = self.detect_version(config)
        migrations = self.get_migration_path(from_version, to_version)

        result = config.copy()
        applied = []

        for migration in migrations:
            result = migration.transform(result)
            applied.append(migration.description)

        return result, applied

    def migrate_file(
        self,
        config_path: Path,
        to_version: SchemaVersion | None = None,
        dry_run: bool = False,
    ) -> MigrationResult:
        """
        Migrate a configuration file to a target version.

        Creates a backup before modification and restores on failure.

        Args:
            config_path: Path to the YAML configuration file
            to_version: Target schema version (defaults to CURRENT_SCHEMA_VERSION)
            dry_run: If True, preview changes without modifying files

        Returns:
            MigrationResult with details of the operation
        """
        if to_version is None:
            to_version = CURRENT_SCHEMA_VERSION

        config_path = Path(config_path)

        # Load original config
        with open(config_path, encoding="utf-8") as f:
            original_config = yaml.safe_load(f)

        original_version = self.detect_version(original_config)

        # Check if migration is needed
        if original_version == to_version:
            return MigrationResult(
                success=True,
                original_version=original_version,
                final_version=to_version,
                steps_applied=[],
                dry_run=dry_run,
            )

        # Perform migration
        try:
            migrated_config, steps = self.migrate(original_config, to_version)
        except Exception as e:
            return MigrationResult(
                success=False,
                original_version=original_version,
                final_version=original_version,
                error=str(e),
                dry_run=dry_run,
            )

        # Validate migrated config
        try:
            self._validator.validate_prompt_config(migrated_config)
        except Exception as e:
            return MigrationResult(
                success=False,
                original_version=original_version,
                final_version=original_version,
                error=f"Migrated config failed validation: {e}",
                dry_run=dry_run,
            )

        # Dry run - return preview without modifying files
        if dry_run:
            return MigrationResult(
                success=True,
                original_version=original_version,
                final_version=to_version,
                steps_applied=steps,
                dry_run=True,
                preview=migrated_config,
            )

        # Create backup
        backup_path = self._create_backup(config_path)

        # Write migrated config
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(migrated_config, f, default_flow_style=False, sort_keys=False)

            return MigrationResult(
                success=True,
                original_version=original_version,
                final_version=to_version,
                backup_path=backup_path,
                steps_applied=steps,
            )
        except Exception as e:
            # Restore from backup on failure
            self._restore_backup(config_path, backup_path)
            return MigrationResult(
                success=False,
                original_version=original_version,
                final_version=original_version,
                backup_path=backup_path,
                error=f"Failed to write migrated config: {e}",
            )

    def _create_backup(self, config_path: Path) -> Path:
        """Create a backup of the configuration file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path.with_suffix(f".{timestamp}.backup.yaml")
        shutil.copy2(config_path, backup_path)
        return backup_path

    def _restore_backup(self, config_path: Path, backup_path: Path) -> None:
        """Restore configuration from backup."""
        shutil.copy2(backup_path, config_path)

    # =========================================================================
    # MIGRATION TRANSFORMATIONS
    # =========================================================================

    @staticmethod
    def _migrate_1_0_to_1_1(config: dict[str, Any]) -> dict[str, Any]:
        """
        Migrate from schema version 1.0 to 1.1.

        Changes:
        - Add output_format field to meta (default: "markdown")
        - Update schema_version to 1.1
        """
        result = config.copy()
        result["meta"] = config.get("meta", {}).copy()

        # Add output_format if not present
        if "output_format" not in result["meta"]:
            result["meta"]["output_format"] = "markdown"

        # Update schema version
        result["meta"]["schema_version"] = "1.1"

        return result

    @staticmethod
    def _migrate_1_1_to_2_0(config: dict[str, Any]) -> dict[str, Any]:
        """
        Migrate from schema version 1.1 to 2.0.

        Changes:
        - Add position field to sections (default: "middle")
        - Ensure subsections field exists on all sections
        - Update schema_version to 2.0
        """
        result = config.copy()
        result["meta"] = config.get("meta", {}).copy()

        # Update sections
        if "sections" in result:
            result["sections"] = [
                MigrationTool._migrate_section_1_1_to_2_0(section)
                for section in result["sections"]
            ]

        # Update schema version
        result["meta"]["schema_version"] = "2.0"

        return result

    @staticmethod
    def _migrate_section_1_1_to_2_0(section: dict[str, Any]) -> dict[str, Any]:
        """Migrate a single section from 1.1 to 2.0 format."""
        result = section.copy()

        # Add position if not present
        if "position" not in result:
            result["position"] = "middle"

        # Ensure subsections exists
        if "subsections" not in result:
            result["subsections"] = []
        else:
            # Recursively migrate subsections
            result["subsections"] = [
                MigrationTool._migrate_section_1_1_to_2_0(sub)
                for sub in result["subsections"]
            ]

        return result


# Re-export for convenience
__all__ = [
    "MigrationStep",
    "MigrationResult",
    "MigrationError",
    "MigrationTool",
]
