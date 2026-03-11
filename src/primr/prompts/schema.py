"""
Schema definitions for the prompt architecture.

This module defines the dataclasses used throughout the prompt system:
- SharedComponents: Container for epistemic rules, formatting, personas
- SectionSpec: Definition of a report section
- PromptConfig: Complete prompt configuration from YAML
- DataSource: Associated data file for a strategy module
- StrategyModule: Metadata about a strategy module
- PromptContext: Runtime context for variable substitution
- ComposedPrompt: Result of prompt composition
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SharedComponents:
    """Container for all shared prompt components."""

    epistemic_rules: dict[str, str] = field(default_factory=dict)
    formatting_rules: dict[str, str] = field(default_factory=dict)
    personas: dict[str, str] = field(default_factory=dict)
    default_persona: str = "senior_consultant"

    # Strategy-specific rules (optional)
    strategy_rules: dict[str, str] = field(default_factory=dict)
    structure_rules: dict[str, str] = field(default_factory=dict)
    table_rules: dict[str, str] = field(default_factory=dict)

    def get_persona(self, name: str | None = None) -> str:
        """Get a persona by name, or the default if not specified."""
        if name is None:
            name = self.default_persona
        return self.personas.get(name, self.personas.get(self.default_persona, ""))

    def get_epistemic_rule(self, name: str) -> str:
        """Get a specific epistemic rule by name."""
        return self.epistemic_rules.get(name, "")

    def get_formatting_rule(self, name: str) -> str:
        """Get a specific formatting rule by name."""
        return self.formatting_rules.get(name, "")


@dataclass
class SectionSpec:
    """Specification for a single report section."""

    id: str
    name: str
    part: int  # 1-5 for the five parts of the report
    purpose: str = ""
    covers: list[str] = field(default_factory=list)
    depth: str = ""
    position: str = "middle"  # opening, middle, or closing - for narrative flow
    subsections: list["SectionSpec"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "part": self.part,
            "purpose": self.purpose,
            "covers": self.covers,
            "depth": self.depth,
            "position": self.position,
            "subsections": [s.to_dict() for s in self.subsections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectionSpec":
        """Create from dictionary."""
        subsections = [cls.from_dict(s) for s in data.get("subsections", [])]
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            part=data.get("part", 0),
            purpose=data.get("purpose", ""),
            covers=data.get("covers", []),
            depth=data.get("depth", ""),
            position=data.get("position", "middle"),
            subsections=subsections,
        )


@dataclass
class DataSource:
    """A data source associated with a strategy module."""

    name: str  # e.g., "azure_vendor_research"
    path: str  # Relative path to the data file
    description: str = ""
    vendor: str | None = None  # If set, only used when this vendor is selected
    required: bool = False  # If True, strategy fails without this file

    def resolve_path(self, base_dir: Path) -> Path:
        """Resolve the data source path relative to base directory."""
        return base_dir / self.path

    def exists(self, base_dir: Path) -> bool:
        """Check if the data source file exists."""
        return self.resolve_path(base_dir).exists()

    def matches_vendor(self, vendor: str | None) -> bool:
        """Check if this data source matches the specified vendor."""
        if self.vendor is None:
            # No vendor filter, always matches
            return True
        if vendor is None:
            # No vendor specified, only match sources without vendor filter
            return self.vendor is None
        return self.vendor.lower() == vendor.lower()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataSource":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            description=data.get("description", ""),
            vendor=data.get("vendor"),
            required=data.get("required", False),
        )


@dataclass
class PromptConfig:
    """Complete prompt configuration loaded from YAML."""

    meta: dict[str, Any] = field(default_factory=dict)
    document_purpose: str = ""
    sections: list[SectionSpec] = field(default_factory=list)
    raw_config: dict[str, Any] = field(default_factory=dict)

    # Optional overrides for shared components
    epistemic_rules_override: dict[str, str] = field(default_factory=dict)
    formatting_override: dict[str, str] = field(default_factory=dict)
    persona_override: str | None = None

    # Strategy-specific fields
    vendor_guidance: dict[str, Any] = field(default_factory=dict)
    data_sources: list[DataSource] = field(default_factory=list)
    heuristics: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Get the prompt name from meta."""
        return str(self.meta.get("name", "Unknown"))

    @property
    def version(self) -> str:
        """Get the prompt version from meta."""
        return str(self.meta.get("version", "0.0.0"))

    @property
    def description(self) -> str:
        """Get the prompt description from meta."""
        return str(self.meta.get("description", ""))

    @property
    def expected_pages(self) -> str:
        """Get expected page count from meta."""
        return str(self.meta.get("expected_pages", ""))

    def get_sections_by_part(self) -> dict[int, list[SectionSpec]]:
        """Group sections by part number."""
        result: dict[int, list[SectionSpec]] = {}
        for section in self.sections:
            if section.part not in result:
                result[section.part] = []
            result[section.part].append(section)
        return result


@dataclass
class StrategyModule:
    """Metadata about a strategy module."""

    name: str  # e.g., "ai", "cloud"
    display_name: str  # e.g., "AI Strategy", "Cloud Migration"
    description: str
    config_path: Path
    is_builtin: bool = True
    data_sources: list[DataSource] = field(default_factory=list)

    def get_context_files(self, base_dir: Path, vendor: str | None = None) -> list[Path]:
        """
        Get paths to context files for this strategy.

        For AI Strategy with vendor="azure", returns paths to Azure-specific
        vendor research files that should be uploaded to File Search Store.

        Args:
            base_dir: Base directory for resolving relative paths
            vendor: Optional vendor filter (e.g., "azure", "aws", "gcp")

        Returns:
            List of paths to existing context files
        """
        result = []
        for ds in self.data_sources:
            if ds.matches_vendor(vendor):
                path = ds.resolve_path(base_dir)
                if path.exists():
                    result.append(path)
        return result


@dataclass
class PromptContext:
    """Runtime context for prompt variable substitution."""

    company_name: str
    website_url: str | None = None
    cloud_vendor: str = "agnostic"
    current_date: str | None = None  # Auto-populated if None
    has_stage1_context: bool = False
    discovery_notes_path: str | None = None  # Path to discovery notes file
    discovery_notes_content: str | None = None  # Loaded content of discovery notes
    custom_vars: dict[str, str] = field(default_factory=dict)

    def get_variable(self, name: str) -> str | None:
        """Get a variable value by name."""
        if name == "company_name":
            return self.company_name
        elif name == "website_url":
            return self.website_url
        elif name == "cloud_vendor":
            return self.cloud_vendor
        elif name == "current_date":
            return self.current_date
        elif name == "discovery_notes_path":
            return self.discovery_notes_path
        else:
            return self.custom_vars.get(name)


@dataclass
class ComposedPrompt:
    """Result of prompt composition."""

    content: str
    source_files: list[str] = field(default_factory=list)
    section_count: int = 0
    variables_substituted: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        """Approximate word count of the content."""
        return len(self.content.split()) if self.content else 0
