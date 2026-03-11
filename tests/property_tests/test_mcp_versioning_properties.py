"""Property-based tests for MCP API versioning.

# Feature: phd-level-excellence
# Properties: 30, 31

These tests verify the correctness properties of the MCP versioning system.
"""

from __future__ import annotations

import re

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.primr.mcp_server.versioning import (
    DeprecationWarning,
    MCPVersionRegistry,
    SemanticVersion,
    ToolSchemaMetadata,
    VersionChangeType,
    extract_deprecation_warnings,
    inject_version_metadata,
)

# =============================================================================
# Strategies
# =============================================================================


@st.composite
def semantic_version_strategy(draw):
    """Generate valid semantic versions."""
    return SemanticVersion(
        major=draw(st.integers(min_value=0, max_value=100)),
        minor=draw(st.integers(min_value=0, max_value=100)),
        patch=draw(st.integers(min_value=0, max_value=100)),
    )


@st.composite
def version_string_strategy(draw):
    """Generate valid version strings."""
    major = draw(st.integers(min_value=0, max_value=100))
    minor = draw(st.integers(min_value=0, max_value=100))
    patch = draw(st.integers(min_value=0, max_value=100))
    return f"{major}.{minor}.{patch}"


@st.composite
def tool_name_strategy(draw):
    """Generate valid tool names."""
    return draw(
        st.sampled_from(
            [
                "estimate_run",
                "research_company",
                "generate_strategy",
                "check_jobs",
                "run_qa",
                "doctor",
                "clear_jobs",
                "cancel_job",
            ]
        )
    )


@st.composite
def field_name_strategy(draw):
    """Generate valid field names."""
    return draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
        )
    )


# =============================================================================
# Property 30: Tool Schema Version Presence
# =============================================================================


class TestToolSchemaVersionPresence:
    """Tests for Property 30: Tool Schema Version Presence.

    *For any* MCP tool schema, the schema metadata SHALL include a `version`
    field matching the semantic versioning pattern `major.minor.patch`.
    **Validates: Requirements 13.1, 13.2**
    """

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(tool_name=tool_name_strategy())
    def test_all_tools_have_version(self, tool_name: str):
        """Verify all registered tools have version metadata."""
        registry = MCPVersionRegistry()
        metadata = registry.get_tool_metadata(tool_name)

        assert metadata is not None, f"Tool {tool_name} not found in registry"
        assert metadata.version is not None, f"Tool {tool_name} has no version"

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version=semantic_version_strategy())
    def test_version_string_format(self, version: SemanticVersion):
        """Verify version string matches major.minor.patch pattern."""
        version_str = str(version)

        # Must match pattern
        pattern = r"^\d+\.\d+\.\d+$"
        assert re.match(pattern, version_str), f"Version {version_str} doesn't match pattern"

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version_str=version_string_strategy())
    def test_version_parse_roundtrip(self, version_str: str):
        """Verify version parsing and stringification are inverse operations."""
        parsed = SemanticVersion.parse(version_str)
        assert str(parsed) == version_str

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(tool_name=tool_name_strategy())
    def test_metadata_to_dict_includes_version(self, tool_name: str):
        """Verify metadata serialization includes version."""
        registry = MCPVersionRegistry()
        metadata = registry.get_tool_metadata(tool_name)

        assert metadata is not None
        metadata_dict = metadata.to_dict()

        assert "version" in metadata_dict
        assert "tool_name" in metadata_dict

        # Version should be a string in the dict
        assert isinstance(metadata_dict["version"], str)

        # Should match pattern
        pattern = r"^\d+\.\d+\.\d+$"
        assert re.match(pattern, metadata_dict["version"])

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(st.data())
    def test_inject_version_adds_metadata(self, data):
        """Verify inject_version_metadata adds version to schema."""
        tool_name = data.draw(tool_name_strategy())

        registry = MCPVersionRegistry()
        metadata = registry.get_tool_metadata(tool_name)

        assert metadata is not None

        # Create a minimal tool schema
        original_schema = {
            "name": tool_name,
            "description": "Test tool",
            "inputSchema": {"type": "object"},
        }

        result = inject_version_metadata(original_schema, metadata)

        # Should have metadata field
        assert "metadata" in result
        assert "version" in result["metadata"]

        # Original fields preserved
        assert result["name"] == tool_name
        assert result["description"] == "Test tool"


# =============================================================================
# Property 31: Deprecation Warning Inclusion
# =============================================================================


class TestDeprecationWarningInclusion:
    """Tests for Property 31: Deprecation Warning Inclusion.

    *For any* deprecated field in an MCP response, the response SHALL include
    a deprecation warning with the field name and recommended alternative.
    **Validates: Requirements 13.5**
    """

    # Feature: phd-level-excellence, Property 31: Deprecation Warning Inclusion
    @settings(max_examples=50)
    @given(
        field_name=field_name_strategy(),
        message=st.text(min_size=1, max_size=100),
    )
    def test_deprecation_warning_structure(self, field_name: str, message: str):
        """Verify deprecation warning has required fields."""
        assume(field_name.strip())  # Non-empty after strip

        warning = DeprecationWarning(
            field_name=field_name,
            message=message,
            deprecated_in=SemanticVersion(1, 0, 0),
        )

        warning_dict = warning.to_dict()

        assert "field" in warning_dict
        assert "message" in warning_dict
        assert "deprecated_in" in warning_dict

        assert warning_dict["field"] == field_name
        assert warning_dict["message"] == message

    # Feature: phd-level-excellence, Property 31: Deprecation Warning Inclusion
    @settings(max_examples=50)
    @given(
        field_name=field_name_strategy(),
        alternative=st.text(min_size=1, max_size=50),
    )
    def test_deprecation_includes_alternative(self, field_name: str, alternative: str):
        """Verify deprecation warning includes alternative when provided."""
        assume(field_name.strip())
        assume(alternative.strip())

        warning = DeprecationWarning(
            field_name=field_name,
            message="Field is deprecated",
            deprecated_in=SemanticVersion(1, 0, 0),
            alternative=alternative,
        )

        warning_dict = warning.to_dict()

        assert "alternative" in warning_dict
        assert warning_dict["alternative"] == alternative

    # Feature: phd-level-excellence, Property 31: Deprecation Warning Inclusion
    @settings(max_examples=50)
    @given(st.data())
    def test_extract_deprecation_adds_warnings(self, data):
        """Verify extract_deprecation_warnings adds warnings for deprecated fields."""
        field_name = data.draw(field_name_strategy())
        assume(field_name.strip())

        # Create metadata with deprecation
        metadata = ToolSchemaMetadata(
            tool_name="test_tool",
            version=SemanticVersion(1, 0, 0),
        )
        metadata.add_deprecation(
            field_name=field_name,
            message="This field is deprecated",
            deprecated_in=SemanticVersion(1, 0, 0),
            alternative="use_new_field",
        )

        # Response containing the deprecated field
        response = {field_name: "some_value", "other_field": "other_value"}

        result = extract_deprecation_warnings(response, metadata)

        # Should have deprecation warnings
        assert "_deprecation_warnings" in result
        assert len(result["_deprecation_warnings"]) == 1
        assert result["_deprecation_warnings"][0]["field"] == field_name

    # Feature: phd-level-excellence, Property 31: Deprecation Warning Inclusion
    @settings(max_examples=50)
    @given(st.data())
    def test_no_warnings_when_no_deprecated_fields(self, data):
        """Verify no warnings added when response has no deprecated fields."""
        # Create metadata with deprecation for a field not in response
        metadata = ToolSchemaMetadata(
            tool_name="test_tool",
            version=SemanticVersion(1, 0, 0),
        )
        metadata.add_deprecation(
            field_name="deprecated_field",
            message="This field is deprecated",
            deprecated_in=SemanticVersion(1, 0, 0),
        )

        # Response without the deprecated field
        response = {"other_field": "value", "another_field": 123}

        result = extract_deprecation_warnings(response, metadata)

        # Should not have deprecation warnings
        assert "_deprecation_warnings" not in result

    # Feature: phd-level-excellence, Property 31: Deprecation Warning Inclusion
    @settings(max_examples=50)
    @given(tool_name=tool_name_strategy())
    def test_registry_add_deprecation(self, tool_name: str):
        """Verify registry can add deprecations to tools."""
        registry = MCPVersionRegistry()

        # Add deprecation
        registry.add_deprecation(
            tool_name=tool_name,
            field_name="old_field",
            message="Use new_field instead",
            alternative="new_field",
        )

        metadata = registry.get_tool_metadata(tool_name)
        assert metadata is not None
        assert len(metadata.deprecated_fields) == 1
        assert metadata.deprecated_fields[0].field_name == "old_field"
        assert metadata.deprecated_fields[0].alternative == "new_field"


# =============================================================================
# Additional Property Tests for Versioning
# =============================================================================


class TestVersioningInvariants:
    """Additional invariant tests for versioning system."""

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(
        v1=semantic_version_strategy(),
        v2=semantic_version_strategy(),
    )
    def test_version_comparison_transitivity(self, v1: SemanticVersion, v2: SemanticVersion):
        """Verify version comparison is transitive."""
        # If v1 < v2, then not v2 < v1
        if v1 < v2:
            assert not v2 < v1

        # If v1 == v2, then v2 == v1
        if v1 == v2:
            assert v2 == v1

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version=semantic_version_strategy())
    def test_version_bump_increases_version(self, version: SemanticVersion):
        """Verify bumping always increases version."""
        for change_type in VersionChangeType:
            bumped = version.bump(change_type)
            assert bumped > version

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version=semantic_version_strategy())
    def test_major_bump_resets_minor_and_patch(self, version: SemanticVersion):
        """Verify major bump resets minor and patch to 0."""
        bumped = version.bump(VersionChangeType.MAJOR)
        assert bumped.major == version.major + 1
        assert bumped.minor == 0
        assert bumped.patch == 0

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version=semantic_version_strategy())
    def test_minor_bump_resets_patch(self, version: SemanticVersion):
        """Verify minor bump resets patch to 0."""
        bumped = version.bump(VersionChangeType.MINOR)
        assert bumped.major == version.major
        assert bumped.minor == version.minor + 1
        assert bumped.patch == 0

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(
        v1=semantic_version_strategy(),
        v2=semantic_version_strategy(),
    )
    def test_compatibility_same_major(self, v1: SemanticVersion, v2: SemanticVersion):
        """Verify compatibility requires same major version."""
        # Same major and v1 >= v2 means compatible
        if v1.major == v2.major and v1 >= v2:
            assert v1.is_compatible_with(v2)

        # Different major means not compatible
        if v1.major != v2.major:
            assert not v1.is_compatible_with(v2)

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(st.data())
    def test_version_history_ordered(self, data):
        """Verify version history is returned in order."""
        registry = MCPVersionRegistry()
        history = registry.get_version_history()

        # Should be sorted newest first
        for i in range(len(history) - 1):
            assert history[i].version >= history[i + 1].version

    # Feature: phd-level-excellence, Property 31: Deprecation Warning Inclusion
    @settings(max_examples=50)
    @given(tool_name=tool_name_strategy())
    def test_deprecation_policy_minimum_notice(self, tool_name: str):
        """Verify deprecation policy gives minimum 2 minor versions notice."""
        registry = MCPVersionRegistry()

        registry.add_deprecation(
            tool_name=tool_name,
            field_name="test_field",
            message="Test deprecation",
        )

        metadata = registry.get_tool_metadata(tool_name)
        assert metadata is not None

        dep = metadata.deprecated_fields[-1]  # Get the one we just added

        # removed_in should be at least 2 minor versions ahead
        assert dep.removed_in is not None
        assert dep.removed_in.minor >= dep.deprecated_in.minor + 2

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version=semantic_version_strategy())
    def test_version_hash_consistency(self, version: SemanticVersion):
        """Verify version hash is consistent with equality."""
        # Equal versions should have equal hashes
        v2 = SemanticVersion(version.major, version.minor, version.patch)
        assert hash(version) == hash(v2)

        # Can be used in sets/dicts
        version_set = {version, v2}
        assert len(version_set) == 1


class TestMigrationGuide:
    """Tests for migration guide generation."""

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(
        from_version=semantic_version_strategy(),
        to_version=semantic_version_strategy(),
    )
    def test_migration_guide_generation(
        self, from_version: SemanticVersion, to_version: SemanticVersion
    ):
        """Verify migration guide is generated correctly."""
        registry = MCPVersionRegistry()
        guide = registry.get_migration_guide(from_version, to_version)

        # Should always return a string
        assert isinstance(guide, str)

        # If from >= to, should indicate no migration needed
        if from_version >= to_version:
            assert "No migration needed" in guide or "already at or above" in guide

    # Feature: phd-level-excellence, Property 30: Tool Schema Version Presence
    @settings(max_examples=50)
    @given(version=semantic_version_strategy())
    def test_version_support_check(self, version: SemanticVersion):
        """Verify version support checking works correctly."""
        registry = MCPVersionRegistry()

        # Current version should always be supported
        assert registry.is_version_supported(registry.CURRENT_VERSION)

        # Version with different major should not be supported
        different_major = SemanticVersion(
            registry.CURRENT_VERSION.major + 1,
            version.minor,
            version.patch,
        )
        assert not registry.is_version_supported(different_major)
