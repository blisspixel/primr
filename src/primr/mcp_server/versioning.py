"""MCP API versioning support.

This module provides semantic versioning for MCP tool schemas, including:
- Version metadata for tool schemas
- Deprecation warning support
- Version history documentation

# Feature: phd-level-excellence
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class VersionChangeType(str, Enum):
    """Type of version change."""

    MAJOR = "major"  # Breaking changes
    MINOR = "minor"  # New features, backward compatible
    PATCH = "patch"  # Bug fixes, backward compatible


@dataclass
class SemanticVersion:
    """Semantic version following major.minor.patch pattern."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return False
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other: SemanticVersion) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: SemanticVersion) -> bool:
        return self == other or self < other

    def __gt__(self, other: SemanticVersion) -> bool:
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)

    def __ge__(self, other: SemanticVersion) -> bool:
        return self == other or self > other

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))

    @classmethod
    def parse(cls, version_str: str) -> SemanticVersion:
        """Parse a version string into a SemanticVersion.

        Args:
            version_str: Version string in format "major.minor.patch"

        Returns:
            SemanticVersion instance

        Raises:
            ValueError: If version string is invalid
        """
        pattern = r"^(\d+)\.(\d+)\.(\d+)$"
        match = re.match(pattern, version_str)
        if not match:
            raise ValueError(f"Invalid version format: {version_str}. Expected major.minor.patch")

        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def bump(self, change_type: VersionChangeType) -> SemanticVersion:
        """Create a new version with the specified bump.

        Args:
            change_type: Type of version change

        Returns:
            New SemanticVersion with bumped version
        """
        if change_type == VersionChangeType.MAJOR:
            return SemanticVersion(self.major + 1, 0, 0)
        elif change_type == VersionChangeType.MINOR:
            return SemanticVersion(self.major, self.minor + 1, 0)
        else:
            return SemanticVersion(self.major, self.minor, self.patch + 1)

    def is_compatible_with(self, other: SemanticVersion) -> bool:
        """Check if this version is backward compatible with another.

        A version is compatible if it has the same major version and
        is greater than or equal to the other version.

        Args:
            other: Version to check compatibility with

        Returns:
            True if compatible, False otherwise
        """
        return self.major == other.major and self >= other


@dataclass
class DeprecationWarning:
    """Warning about a deprecated field or feature."""

    field_name: str
    message: str
    deprecated_in: SemanticVersion
    removed_in: SemanticVersion | None = None
    alternative: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "field": self.field_name,
            "message": self.message,
            "deprecated_in": str(self.deprecated_in),
        }
        if self.removed_in:
            result["removed_in"] = str(self.removed_in)
        if self.alternative:
            result["alternative"] = self.alternative
        return result


@dataclass
class VersionHistoryEntry:
    """Entry in version history."""

    version: SemanticVersion
    date: datetime
    change_type: VersionChangeType
    description: str
    breaking_changes: list[str] = field(default_factory=list)
    new_features: list[str] = field(default_factory=list)
    deprecations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": str(self.version),
            "date": self.date.isoformat(),
            "change_type": self.change_type.value,
            "description": self.description,
            "breaking_changes": self.breaking_changes,
            "new_features": self.new_features,
            "deprecations": self.deprecations,
        }


@dataclass
class ToolSchemaMetadata:
    """Metadata for an MCP tool schema including version information."""

    tool_name: str
    version: SemanticVersion
    description: str = ""
    deprecated_fields: list[DeprecationWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for inclusion in tool schema."""
        result = {
            "tool_name": self.tool_name,
            "version": str(self.version),
        }
        if self.description:
            result["description"] = self.description
        if self.deprecated_fields:
            result["deprecation_warnings"] = [d.to_dict() for d in self.deprecated_fields]
        return result

    def add_deprecation(
        self,
        field_name: str,
        message: str,
        deprecated_in: SemanticVersion,
        removed_in: SemanticVersion | None = None,
        alternative: str | None = None,
    ) -> None:
        """Add a deprecation warning for a field.

        Args:
            field_name: Name of the deprecated field
            message: Deprecation message
            deprecated_in: Version when field was deprecated
            removed_in: Version when field will be removed (optional)
            alternative: Recommended alternative (optional)
        """
        self.deprecated_fields.append(
            DeprecationWarning(
                field_name=field_name,
                message=message,
                deprecated_in=deprecated_in,
                removed_in=removed_in,
                alternative=alternative,
            )
        )


class MCPVersionRegistry:
    """Registry for MCP tool schema versions and history.

    Maintains version information for all tools and provides
    version history documentation.
    """

    # Current API version
    CURRENT_VERSION = SemanticVersion(1, 0, 0)

    # Minimum supported version (for backward compatibility)
    MIN_SUPPORTED_VERSION = SemanticVersion(1, 0, 0)

    def __init__(self):
        """Initialize the version registry."""
        self._tool_metadata: dict[str, ToolSchemaMetadata] = {}
        self._version_history: list[VersionHistoryEntry] = []
        self._initialize_tools()
        self._initialize_history()

    def _initialize_tools(self) -> None:
        """Initialize tool metadata with current versions."""
        tools = [
            ("estimate_run", "Estimate cost and time for a research run"),
            ("estimate_strategy", "Estimate cost and time for a strategy document"),
            ("research_company", "Initiate company research pipeline"),
            ("generate_strategy", "Generate strategy document from existing report"),
            ("check_jobs", "Check status of pending Deep Research jobs"),
            ("run_qa", "Run quality assessment on a report"),
            ("doctor", "Check system health and configuration"),
            ("clear_jobs", "Clear stale pending jobs"),
            ("cancel_job", "Attempt best-effort cancellation of an active job"),
        ]

        for tool_name, description in tools:
            self._tool_metadata[tool_name] = ToolSchemaMetadata(
                tool_name=tool_name,
                version=self.CURRENT_VERSION,
                description=description,
            )

    def _initialize_history(self) -> None:
        """Initialize version history."""
        self._version_history = [
            VersionHistoryEntry(
                version=SemanticVersion(1, 0, 0),
                date=datetime(2026, 1, 1),
                change_type=VersionChangeType.MAJOR,
                description="Initial release of MCP API",
                new_features=[
                    "estimate_run tool for cost estimation",
                    "estimate_strategy tool for strategy cost estimation",
                    "research_company tool for initiating research",
                    "generate_strategy tool for strategy documents",
                    "check_jobs tool for job status",
                    "run_qa tool for quality assessment",
                    "doctor tool for system health",
                    "clear_jobs tool for cleanup",
                    "cancel_job tool for job cancellation",
                ],
            ),
        ]

    def get_tool_metadata(self, tool_name: str) -> ToolSchemaMetadata | None:
        """Get metadata for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolSchemaMetadata or None if not found
        """
        return self._tool_metadata.get(tool_name)

    def get_all_tool_metadata(self) -> dict[str, ToolSchemaMetadata]:
        """Get metadata for all tools.

        Returns:
            Dictionary mapping tool names to metadata
        """
        return dict(self._tool_metadata)

    def get_version_history(self) -> list[VersionHistoryEntry]:
        """Get complete version history.

        Returns:
            List of version history entries, newest first
        """
        return sorted(self._version_history, key=lambda e: e.version, reverse=True)

    def add_deprecation(
        self,
        tool_name: str,
        field_name: str,
        message: str,
        alternative: str | None = None,
    ) -> None:
        """Add a deprecation warning to a tool.

        Args:
            tool_name: Name of the tool
            field_name: Name of the deprecated field
            message: Deprecation message
            alternative: Recommended alternative (optional)
        """
        metadata = self._tool_metadata.get(tool_name)
        if metadata:
            # Deprecation policy: minimum 2 minor versions notice
            removed_in = SemanticVersion(
                self.CURRENT_VERSION.major,
                self.CURRENT_VERSION.minor + 2,
                0,
            )
            metadata.add_deprecation(
                field_name=field_name,
                message=message,
                deprecated_in=self.CURRENT_VERSION,
                removed_in=removed_in,
                alternative=alternative,
            )

    def is_version_supported(self, version: SemanticVersion) -> bool:
        """Check if a version is still supported.

        Args:
            version: Version to check

        Returns:
            True if supported, False otherwise
        """
        return version >= self.MIN_SUPPORTED_VERSION and version.major == self.CURRENT_VERSION.major

    def get_migration_guide(
        self, from_version: SemanticVersion, to_version: SemanticVersion
    ) -> str:
        """Get migration guide between versions.

        Args:
            from_version: Source version
            to_version: Target version

        Returns:
            Migration guide as markdown string
        """
        if from_version >= to_version:
            return "No migration needed - already at or above target version."

        lines = [
            f"# Migration Guide: {from_version} → {to_version}",
            "",
        ]

        # Find relevant history entries
        relevant = [
            entry for entry in self._version_history if from_version < entry.version <= to_version
        ]

        if not relevant:
            lines.append("No breaking changes between these versions.")
            return "\n".join(lines)

        for entry in sorted(relevant, key=lambda e: e.version):
            lines.append(f"## Version {entry.version}")
            lines.append("")

            if entry.breaking_changes:
                lines.append("### Breaking Changes")
                for change in entry.breaking_changes:
                    lines.append(f"- {change}")
                lines.append("")

            if entry.deprecations:
                lines.append("### Deprecations")
                for dep in entry.deprecations:
                    lines.append(f"- {dep}")
                lines.append("")

        return "\n".join(lines)


def inject_version_metadata(
    tool_schema: dict[str, Any], metadata: ToolSchemaMetadata
) -> dict[str, Any]:
    """Inject version metadata into a tool schema.

    Args:
        tool_schema: Original tool schema dictionary
        metadata: Version metadata to inject

    Returns:
        Tool schema with version metadata added
    """
    schema = dict(tool_schema)
    schema["metadata"] = metadata.to_dict()
    return schema


def extract_deprecation_warnings(
    response: dict[str, Any], metadata: ToolSchemaMetadata
) -> dict[str, Any]:
    """Add deprecation warnings to a tool response.

    Args:
        response: Original response dictionary
        metadata: Tool metadata with deprecation info

    Returns:
        Response with deprecation warnings added if applicable
    """
    if not metadata.deprecated_fields:
        return response

    result = dict(response)

    # Check which deprecated fields are present in response
    warnings = []
    for dep in metadata.deprecated_fields:
        if dep.field_name in response:
            warnings.append(dep.to_dict())

    if warnings:
        result["_deprecation_warnings"] = warnings

    return result


# Global registry instance
_registry: MCPVersionRegistry | None = None


def get_version_registry() -> MCPVersionRegistry:
    """Get the global version registry instance.

    Returns:
        MCPVersionRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = MCPVersionRegistry()
    return _registry
