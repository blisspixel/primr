"""
Property-based tests for the Configuration Migration Tooling.

This module contains property tests that verify universal correctness properties
of the MigrationTool implementation as specified in the PhD-Level Excellence spec.

**Feature: phd-level-excellence**
**Validates: Requirements 7.1-7.6**
"""

import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from primr.prompts.migration import (
    CURRENT_SCHEMA_VERSION,
    MigrationTool,
    SchemaVersion,
)
from primr.prompts.validation import ConfigValidator, SchemaVersionError

# =============================================================================
# STRATEGIES FOR GENERATING TEST DATA
# =============================================================================

# Strategy for generating valid section IDs
section_id_strategy = st.from_regex(r'[a-z][a-z0-9_]{0,19}', fullmatch=True)

# Strategy for generating valid section names
section_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'Z')),
    min_size=1,
    max_size=30
).filter(lambda x: x.strip())

# Strategy for generating valid part numbers (1-5)
part_number_strategy = st.integers(min_value=1, max_value=5)

# Strategy for generating valid semantic versions
version_strategy = st.from_regex(r'\d{1,2}\.\d{1,2}\.\d{1,2}', fullmatch=True)


def generate_v1_0_section(
    section_id: str,
    name: str,
    part: int,
) -> dict[str, Any]:
    """Generate a v1.0 format section (no position, no subsections)."""
    return {
        "id": section_id,
        "name": name,
        "part": part,
        "purpose": "Test purpose",
        "covers": ["topic1", "topic2"],
        "depth": "Standard",
    }


def generate_v1_0_config(
    meta_name: str = "Test Prompt",
    meta_version: str = "1.0.0",
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a valid v1.0 configuration."""
    if sections is None:
        sections = [generate_v1_0_section("test_section", "Test Section", 1)]

    return {
        "meta": {
            "name": meta_name,
            "version": meta_version,
            "schema_version": "1.0",
            "description": "Test description",
        },
        "document_purpose": "This is a test document purpose with sufficient length.",
        "sections": sections,
        "epistemic_rules": {},
        "formatting": {},
    }


def generate_v1_1_config(
    meta_name: str = "Test Prompt",
    meta_version: str = "1.0.0",
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a valid v1.1 configuration."""
    config = generate_v1_0_config(meta_name, meta_version, sections)
    config["meta"]["schema_version"] = "1.1"
    config["meta"]["output_format"] = "markdown"
    return config


def generate_v2_0_section(
    section_id: str,
    name: str,
    part: int,
    position: str = "middle",
) -> dict[str, Any]:
    """Generate a v2.0 format section (with position and subsections)."""
    return {
        "id": section_id,
        "name": name,
        "part": part,
        "purpose": "Test purpose",
        "covers": ["topic1", "topic2"],
        "depth": "Standard",
        "position": position,
        "subsections": [],
    }


def generate_v2_0_config(
    meta_name: str = "Test Prompt",
    meta_version: str = "1.0.0",
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a valid v2.0 configuration."""
    if sections is None:
        sections = [generate_v2_0_section("test_section", "Test Section", 1)]

    return {
        "meta": {
            "name": meta_name,
            "version": meta_version,
            "schema_version": "2.0",
            "description": "Test description",
            "output_format": "markdown",
        },
        "document_purpose": "This is a test document purpose with sufficient length.",
        "sections": sections,
        "epistemic_rules": {},
        "formatting": {},
    }


# =============================================================================
# PROPERTY 19: MIGRATION PRODUCES VALID CONFIG
# =============================================================================

class TestMigrationProducesValidConfig:
    """
    **Property 19: Migration Produces Valid Config**

    For any configuration file with an older schema version, applying migrations
    SHALL produce a configuration that validates successfully against the target
    schema version.

    **Validates: Requirements 7.2, 7.4**
    """

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        section_id=section_id_strategy,
        section_name=section_name_strategy,
        part=part_number_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_v1_0_to_v2_0_produces_valid_config(
        self,
        meta_name: str,
        meta_version: str,
        section_id: str,
        section_name: str,
        part: int,
    ):
        """Migrating from v1.0 to v2.0 should produce a valid config."""
        # Feature: phd-level-excellence, Property 19: Migration Produces Valid Config

        config = generate_v1_0_config(
            meta_name=meta_name,
            meta_version=meta_version,
            sections=[generate_v1_0_section(section_id, section_name, part)],
        )

        tool = MigrationTool()
        migrated, steps = tool.migrate(config, SchemaVersion.V2_0)

        # Should have applied migrations
        assert len(steps) == 2  # 1.0 -> 1.1 -> 2.0

        # Migrated config should be valid
        validator = ConfigValidator()
        result = validator.validate_prompt_config(migrated)

        assert result.meta.schema_version == SchemaVersion.V2_0
        assert result.meta.name == meta_name
        assert len(result.sections) == 1
        assert result.sections[0].id == section_id

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        section_id=section_id_strategy,
        section_name=section_name_strategy,
        part=part_number_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_v1_1_to_v2_0_produces_valid_config(
        self,
        meta_name: str,
        meta_version: str,
        section_id: str,
        section_name: str,
        part: int,
    ):
        """Migrating from v1.1 to v2.0 should produce a valid config."""
        # Feature: phd-level-excellence, Property 19: Migration Produces Valid Config

        config = generate_v1_1_config(
            meta_name=meta_name,
            meta_version=meta_version,
            sections=[generate_v1_0_section(section_id, section_name, part)],
        )

        tool = MigrationTool()
        migrated, steps = tool.migrate(config, SchemaVersion.V2_0)

        # Should have applied one migration
        assert len(steps) == 1  # 1.1 -> 2.0

        # Migrated config should be valid
        validator = ConfigValidator()
        result = validator.validate_prompt_config(migrated)

        assert result.meta.schema_version == SchemaVersion.V2_0

    @given(
        num_sections=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_migration_preserves_multiple_sections(self, num_sections: int):
        """Migration should preserve all sections."""
        # Feature: phd-level-excellence, Property 19: Migration Produces Valid Config

        sections = [
            generate_v1_0_section(f"section_{i}", f"Section {i}", (i % 5) + 1)
            for i in range(num_sections)
        ]

        config = generate_v1_0_config(sections=sections)

        tool = MigrationTool()
        migrated, _ = tool.migrate(config, SchemaVersion.V2_0)

        # All sections should be preserved
        assert len(migrated["sections"]) == num_sections

        # Each section should have position and subsections added
        for section in migrated["sections"]:
            assert "position" in section
            assert "subsections" in section

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_migration_adds_output_format(self, meta_name: str, meta_version: str):
        """Migration from v1.0 should add output_format field."""
        # Feature: phd-level-excellence, Property 19: Migration Produces Valid Config

        config = generate_v1_0_config(meta_name=meta_name, meta_version=meta_version)

        # Ensure output_format is not present
        assert "output_format" not in config["meta"]

        tool = MigrationTool()
        migrated, _ = tool.migrate(config, SchemaVersion.V2_0)

        # output_format should be added
        assert "output_format" in migrated["meta"]
        assert migrated["meta"]["output_format"] == "markdown"

    def test_no_migration_needed_for_current_version(self):
        """Config at current version should not need migration."""
        # Feature: phd-level-excellence, Property 19: Migration Produces Valid Config

        config = generate_v2_0_config()

        tool = MigrationTool()
        migrated, steps = tool.migrate(config, CURRENT_SCHEMA_VERSION)

        # No steps should be applied
        assert len(steps) == 0

        # Config should be unchanged
        assert migrated["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION.value


# =============================================================================
# PROPERTY 20: MIGRATION BACKUP AND RESTORE
# =============================================================================

class TestMigrationBackupAndRestore:
    """
    **Property 20: Migration Backup and Restore**

    For any migration operation, a backup file SHALL be created before modification.
    If migration fails, the original file SHALL be restored from backup.

    **Validates: Requirements 7.3, 7.5**
    """

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_backup_created_before_migration(self, meta_name: str, meta_version: str):
        """A backup file should be created before modifying the original."""
        # Feature: phd-level-excellence, Property 20: Migration Backup and Restore

        config = generate_v1_0_config(meta_name=meta_name, meta_version=meta_version)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Write original config
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0)

            # Migration should succeed
            assert result.success

            # Backup should exist
            assert result.backup_path is not None
            assert result.backup_path.exists()

            # Backup should contain original content
            with open(result.backup_path, encoding="utf-8") as f:
                backup_content = yaml.safe_load(f)

            assert backup_content["meta"]["schema_version"] == "1.0"

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_original_file_updated_after_migration(
        self, meta_name: str, meta_version: str
    ):
        """The original file should be updated with migrated content."""
        # Feature: phd-level-excellence, Property 20: Migration Backup and Restore

        config = generate_v1_0_config(meta_name=meta_name, meta_version=meta_version)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0)

            assert result.success

            # Original file should now have migrated content
            with open(config_path, encoding="utf-8") as f:
                updated_content = yaml.safe_load(f)

            assert updated_content["meta"]["schema_version"] == "2.0"
            assert "output_format" in updated_content["meta"]

    def test_backup_path_includes_timestamp(self):
        """Backup filename should include a timestamp."""
        # Feature: phd-level-excellence, Property 20: Migration Backup and Restore

        config = generate_v1_0_config()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0)

            assert result.success
            assert result.backup_path is not None

            # Backup filename should contain timestamp pattern
            backup_name = result.backup_path.name
            assert "backup" in backup_name.lower()
            # Should have date-like pattern (YYYYMMDD)
            import re
            assert re.search(r'\d{8}', backup_name)

    def test_no_backup_for_already_current_version(self):
        """No backup should be created if config is already at target version."""
        # Feature: phd-level-excellence, Property 20: Migration Backup and Restore

        config = generate_v2_0_config()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0)

            assert result.success
            # No backup needed since no migration occurred
            assert result.backup_path is None
            assert len(result.steps_applied) == 0


# =============================================================================
# PROPERTY 21: DRY-RUN IDEMPOTENCE
# =============================================================================

class TestDryRunIdempotence:
    """
    **Property 21: Dry-Run Idempotence**

    For any migration in dry-run mode, the original configuration file SHALL
    remain unchanged (byte-for-byte identical) after the operation completes.

    **Validates: Requirements 7.6**
    """

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
        section_id=section_id_strategy,
        section_name=section_name_strategy,
        part=part_number_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_dry_run_does_not_modify_file(
        self,
        meta_name: str,
        meta_version: str,
        section_id: str,
        section_name: str,
        part: int,
    ):
        """Dry-run should not modify the original file."""
        # Feature: phd-level-excellence, Property 21: Dry-Run Idempotence

        config = generate_v1_0_config(
            meta_name=meta_name,
            meta_version=meta_version,
            sections=[generate_v1_0_section(section_id, section_name, part)],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            # Write original config
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            # Read original bytes
            original_bytes = config_path.read_bytes()

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0, dry_run=True)

            # Should succeed
            assert result.success
            assert result.dry_run

            # File should be unchanged
            after_bytes = config_path.read_bytes()
            assert original_bytes == after_bytes

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_dry_run_provides_preview(self, meta_name: str, meta_version: str):
        """Dry-run should provide a preview of the migrated config."""
        # Feature: phd-level-excellence, Property 21: Dry-Run Idempotence

        config = generate_v1_0_config(meta_name=meta_name, meta_version=meta_version)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0, dry_run=True)

            assert result.success
            assert result.dry_run

            # Preview should be provided
            assert result.preview is not None
            assert result.preview["meta"]["schema_version"] == "2.0"
            assert "output_format" in result.preview["meta"]

    @given(
        meta_name=section_name_strategy,
        meta_version=version_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_dry_run_does_not_create_backup(self, meta_name: str, meta_version: str):
        """Dry-run should not create a backup file."""
        # Feature: phd-level-excellence, Property 21: Dry-Run Idempotence

        config = generate_v1_0_config(meta_name=meta_name, meta_version=meta_version)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            # Count files before
            files_before = list(Path(tmpdir).iterdir())

            tool = MigrationTool()
            result = tool.migrate_file(config_path, SchemaVersion.V2_0, dry_run=True)

            assert result.success
            assert result.dry_run

            # No backup should be created
            assert result.backup_path is None

            # No new files should exist
            files_after = list(Path(tmpdir).iterdir())
            assert len(files_after) == len(files_before)

    @given(
        num_runs=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_dry_runs_are_idempotent(self, num_runs: int):
        """Multiple dry-runs should produce identical results."""
        # Feature: phd-level-excellence, Property 21: Dry-Run Idempotence

        config = generate_v1_0_config()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            original_bytes = config_path.read_bytes()

            tool = MigrationTool()
            previews = []

            for _ in range(num_runs):
                result = tool.migrate_file(config_path, SchemaVersion.V2_0, dry_run=True)
                assert result.success
                previews.append(result.preview)

                # File should still be unchanged
                assert config_path.read_bytes() == original_bytes

            # All previews should be identical
            for preview in previews[1:]:
                assert preview == previews[0]


# =============================================================================
# VERSION DETECTION TESTS
# =============================================================================

class TestVersionDetection:
    """Tests for version detection functionality."""

    @given(schema_version=st.sampled_from([v.value for v in SchemaVersion]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_supported_versions(self, schema_version: str):
        """Should correctly detect all supported schema versions."""
        # Feature: phd-level-excellence, Validates: Requirement 7.1

        config = {
            "meta": {
                "name": "Test",
                "version": "1.0.0",
                "schema_version": schema_version,
            },
            "document_purpose": "Test purpose with sufficient length.",
            "sections": [{"id": "test", "name": "Test", "part": 1}],
        }

        tool = MigrationTool()
        detected = tool.detect_version(config)

        assert detected.value == schema_version

    def test_detect_missing_version_defaults_to_1_0(self):
        """Missing schema_version should default to 1.0."""
        # Feature: phd-level-excellence, Validates: Requirement 7.1

        config = {
            "meta": {
                "name": "Test",
                "version": "1.0.0",
                # No schema_version
            },
            "document_purpose": "Test purpose with sufficient length.",
            "sections": [{"id": "test", "name": "Test", "part": 1}],
        }

        tool = MigrationTool()
        detected = tool.detect_version(config)

        assert detected == SchemaVersion.V1_0

    @given(
        invalid_version=st.text(min_size=1, max_size=10).filter(
            lambda x: x not in [v.value for v in SchemaVersion]
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_unsupported_version_raises_error(self, invalid_version: str):
        """Unsupported versions should raise SchemaVersionError."""
        # Feature: phd-level-excellence, Validates: Requirement 7.1

        config = {
            "meta": {
                "name": "Test",
                "version": "1.0.0",
                "schema_version": invalid_version,
            },
            "document_purpose": "Test purpose with sufficient length.",
            "sections": [{"id": "test", "name": "Test", "part": 1}],
        }

        tool = MigrationTool()

        with pytest.raises(SchemaVersionError):
            tool.detect_version(config)


# =============================================================================
# MIGRATION PATH TESTS
# =============================================================================

class TestMigrationPath:
    """Tests for migration path calculation."""

    def test_migration_path_1_0_to_2_0(self):
        """Should find correct path from 1.0 to 2.0."""
        # Feature: phd-level-excellence, Validates: Requirement 7.2

        tool = MigrationTool()
        path = tool.get_migration_path(SchemaVersion.V1_0, SchemaVersion.V2_0)

        assert len(path) == 2
        assert path[0].from_version == SchemaVersion.V1_0
        assert path[0].to_version == SchemaVersion.V1_1
        assert path[1].from_version == SchemaVersion.V1_1
        assert path[1].to_version == SchemaVersion.V2_0

    def test_migration_path_1_1_to_2_0(self):
        """Should find correct path from 1.1 to 2.0."""
        # Feature: phd-level-excellence, Validates: Requirement 7.2

        tool = MigrationTool()
        path = tool.get_migration_path(SchemaVersion.V1_1, SchemaVersion.V2_0)

        assert len(path) == 1
        assert path[0].from_version == SchemaVersion.V1_1
        assert path[0].to_version == SchemaVersion.V2_0

    def test_migration_path_same_version(self):
        """Same version should return empty path."""
        # Feature: phd-level-excellence, Validates: Requirement 7.2

        tool = MigrationTool()

        for version in SchemaVersion:
            path = tool.get_migration_path(version, version)
            assert len(path) == 0

    def test_migration_path_defaults_to_current(self):
        """Target version should default to CURRENT_SCHEMA_VERSION."""
        # Feature: phd-level-excellence, Validates: Requirement 7.2

        tool = MigrationTool()
        path = tool.get_migration_path(SchemaVersion.V1_0)

        # Should end at current version
        if path:
            assert path[-1].to_version == CURRENT_SCHEMA_VERSION
