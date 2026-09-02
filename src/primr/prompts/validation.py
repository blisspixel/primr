"""
Pydantic Configuration Validation for Prompt Configurations.

This module provides strict validation for YAML prompt configurations using Pydantic models.
It ensures configuration errors are caught at load time with clear error messages.

**Feature: phd-level-excellence**
**Validates: Requirements 6.1-6.8**

Components:
- SchemaVersion: Enum of supported schema versions
- SectionPosition: Enum for section positions in narrative flow
- SectionSpecModel: Pydantic model for section specification
- PromptMetaModel: Pydantic model for prompt metadata
- PromptConfigModel: Pydantic model for complete prompt configuration
- SchemaVersionError: Exception for unsupported schema versions
- ConfigValidator: Validates YAML configurations against Pydantic models
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class SchemaVersion(str, Enum):
    """Supported schema versions for prompt configurations."""

    V1_0 = "1.0"
    V1_1 = "1.1"
    V2_0 = "2.0"


# Current schema version - new configs should use this
CURRENT_SCHEMA_VERSION = SchemaVersion.V2_0


class SectionPosition(str, Enum):
    """Position of a section in the narrative flow."""

    OPENING = "opening"
    MIDDLE = "middle"
    CLOSING = "closing"
    FRAMEWORK = "framework"


class SectionSpecModel(BaseModel):
    """
    Pydantic model for section specification.

    Validates the structure of individual sections in a prompt configuration.
    """

    id: str = Field(..., min_length=1, description="Unique section identifier")
    name: str = Field(..., min_length=1, description="Section display name")
    part: int = Field(..., ge=1, le=5, description="Report part number (1-5)")
    purpose: str = Field(default="", description="Section purpose")
    covers: list[str] = Field(default_factory=list, description="Topics covered")
    depth: str = Field(default="", description="Expected depth of coverage")
    position: SectionPosition = Field(default=SectionPosition.MIDDLE)
    subsections: list[SectionSpecModel] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


class PromptMetaModel(BaseModel):
    """
    Pydantic model for prompt metadata.

    Validates the meta section of a prompt configuration.
    """

    name: str = Field(..., min_length=1, description="Prompt name")
    version: str = Field(
        ..., pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", description="Semantic version (e.g., 1.0.0)"
    )
    description: str = Field(default="", description="Prompt description")
    expected_pages: str = Field(default="", description="Expected page count")
    output_format: str = Field(default="markdown", description="Output format")
    schema_version: SchemaVersion = Field(default=CURRENT_SCHEMA_VERSION)

    model_config = {"extra": "allow"}  # Allow additional meta fields


class PromptConfigModel(BaseModel):
    """
    Pydantic model for complete prompt configuration.

    Validates the entire structure of a prompt YAML configuration file.
    """

    meta: PromptMetaModel
    document_purpose: str = Field(..., min_length=10, description="Document purpose statement")
    sections: list[SectionSpecModel] = Field(..., min_length=1, description="Report sections")
    epistemic_rules: dict[str, str] = Field(default_factory=dict)
    formatting: dict[str, str] = Field(default_factory=dict)

    # Optional fields for strategy prompts
    key_metrics: dict[str, str] = Field(default_factory=dict)
    accordion_method: dict[str, Any] = Field(default_factory=dict)
    vendor_guidance: dict[str, Any] = Field(default_factory=dict)
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    heuristics: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "allow"}  # Allow additional fields for extensibility

    @field_validator("sections")
    @classmethod
    def validate_unique_section_ids(
        cls, sections: list[SectionSpecModel]
    ) -> list[SectionSpecModel]:
        """Ensure all section IDs are unique."""
        ids = _collect_all_section_ids(sections)
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Section IDs must be unique. Duplicates found: {set(duplicates)}")
        return sections


def _collect_all_section_ids(sections: list[SectionSpecModel]) -> list[str]:
    """Recursively collect all section IDs including subsections."""
    ids = []
    for section in sections:
        ids.append(section.id)
        if section.subsections:
            ids.extend(_collect_all_section_ids(section.subsections))
    return ids


class SchemaVersionError(Exception):
    """
    Raised when schema version is unsupported.

    Provides migration guidance in the error message.
    """

    def __init__(self, message: str, current_version: str, unsupported_version: str | None = None):
        super().__init__(message)
        self.current_version = current_version
        self.unsupported_version = unsupported_version
        self.supported_versions = [v.value for v in SchemaVersion]

    def __str__(self) -> str:
        base_msg = super().__str__()
        migration_hint = (
            f"\n\nMigration guidance:\n"
            f"  - Current supported versions: {self.supported_versions}\n"
            f"  - Latest version: {self.current_version}\n"
            f"  - Update your config's schema_version to a supported version."
        )
        return base_msg + migration_hint


class ConfigValidator:
    """
    Validates YAML configurations against Pydantic models.

    Provides detailed error messages with field paths and expected types.
    """

    def validate_prompt_config(self, config: dict[str, Any]) -> PromptConfigModel:
        """
        Validate a prompt configuration dictionary.

        Args:
            config: Dictionary loaded from YAML configuration file

        Returns:
            Validated PromptConfigModel instance

        Raises:
            ValidationError: If validation fails, with detailed error messages
        """
        return PromptConfigModel.model_validate(config)

    def check_schema_version(self, config: dict[str, Any]) -> tuple[SchemaVersion, bool]:
        """
        Check schema version and compatibility.

        Args:
            config: Dictionary loaded from YAML configuration file

        Returns:
            Tuple of (detected_version, is_current_version)

        Raises:
            SchemaVersionError: If schema version is unsupported
        """
        version_str = config.get("meta", {}).get("schema_version", "1.0")

        try:
            version = SchemaVersion(version_str)
            is_current = version == CURRENT_SCHEMA_VERSION
            return version, is_current
        except ValueError as e:
            raise SchemaVersionError(
                f"Unknown schema version: {version_str}. "
                f"Supported versions: {[v.value for v in SchemaVersion]}",
                current_version=CURRENT_SCHEMA_VERSION.value,
                unsupported_version=version_str,
            ) from e

    def export_json_schema(self) -> dict[str, Any]:
        """
        Export JSON Schema for external tooling and IDE support.

        Returns:
            JSON Schema dictionary for PromptConfigModel
        """
        return PromptConfigModel.model_json_schema()

    def validate_with_version_check(self, config: dict[str, Any]) -> PromptConfigModel:
        """
        Validate configuration with schema version checking.

        This method first checks the schema version, then validates the config.

        Args:
            config: Dictionary loaded from YAML configuration file

        Returns:
            Validated PromptConfigModel instance

        Raises:
            SchemaVersionError: If schema version is unsupported
            ValidationError: If validation fails
        """
        # Check schema version first
        self.check_schema_version(config)

        # Then validate the full config
        return self.validate_prompt_config(config)


# Re-export ValidationError for convenience
__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ConfigValidator",
    "PromptConfigModel",
    "PromptMetaModel",
    "SchemaVersion",
    "SchemaVersionError",
    "SectionPosition",
    "SectionSpecModel",
    "ValidationError",
]
