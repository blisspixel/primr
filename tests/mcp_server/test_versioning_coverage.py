"""
Coverage tests for versioning.py.

Exercises SemanticVersion ordering/parse/bump/compat, deprecation handling,
migration guide generation, and the version registry.
"""

import pytest

from primr.mcp_server.versioning import (
    DeprecationWarning,
    MCPVersionRegistry,
    SemanticVersion,
    ToolSchemaMetadata,
    VersionChangeType,
    VersionHistoryEntry,
    extract_deprecation_warnings,
    get_version_registry,
    inject_version_metadata,
)


class TestSemanticVersion:
    def test_str(self):
        assert str(SemanticVersion(1, 2, 3)) == "1.2.3"

    def test_eq_and_noneq(self):
        assert SemanticVersion(1, 0, 0) == SemanticVersion(1, 0, 0)
        assert SemanticVersion(1, 0, 0) != SemanticVersion(1, 0, 1)
        assert SemanticVersion(1, 0, 0) != "not a version"

    def test_ordering(self):
        v1 = SemanticVersion(1, 0, 0)
        v2 = SemanticVersion(1, 2, 0)
        assert v1 < v2
        assert v2 > v1
        assert v1 <= v1
        assert v1 >= v1
        assert v1 <= v2
        assert v2 >= v1

    def test_hash(self):
        s = {SemanticVersion(1, 0, 0), SemanticVersion(1, 0, 0)}
        assert len(s) == 1

    def test_parse_valid(self):
        v = SemanticVersion.parse("2.3.4")
        assert (v.major, v.minor, v.patch) == (2, 3, 4)

    def test_parse_invalid(self):
        with pytest.raises(ValueError, match="Invalid version format"):
            SemanticVersion.parse("1.2")

    def test_bump_major(self):
        assert SemanticVersion(1, 2, 3).bump(VersionChangeType.MAJOR) == SemanticVersion(2, 0, 0)

    def test_bump_minor(self):
        assert SemanticVersion(1, 2, 3).bump(VersionChangeType.MINOR) == SemanticVersion(1, 3, 0)

    def test_bump_patch(self):
        assert SemanticVersion(1, 2, 3).bump(VersionChangeType.PATCH) == SemanticVersion(1, 2, 4)

    def test_is_compatible_with(self):
        assert SemanticVersion(1, 2, 0).is_compatible_with(SemanticVersion(1, 0, 0))
        assert not SemanticVersion(2, 0, 0).is_compatible_with(SemanticVersion(1, 0, 0))
        assert not SemanticVersion(1, 0, 0).is_compatible_with(SemanticVersion(1, 2, 0))


class TestDeprecationWarning:
    def test_to_dict_minimal(self):
        dw = DeprecationWarning(
            field_name="old_field",
            message="use new_field",
            deprecated_in=SemanticVersion(1, 0, 0),
        )
        d = dw.to_dict()
        assert d["field"] == "old_field"
        assert d["deprecated_in"] == "1.0.0"
        assert "removed_in" not in d
        assert "alternative" not in d

    def test_to_dict_full(self):
        dw = DeprecationWarning(
            field_name="old_field",
            message="msg",
            deprecated_in=SemanticVersion(1, 0, 0),
            removed_in=SemanticVersion(1, 2, 0),
            alternative="new_field",
        )
        d = dw.to_dict()
        assert d["removed_in"] == "1.2.0"
        assert d["alternative"] == "new_field"


class TestVersionHistoryEntry:
    def test_to_dict(self):
        from datetime import datetime

        entry = VersionHistoryEntry(
            version=SemanticVersion(1, 0, 0),
            date=datetime(2026, 1, 1),
            change_type=VersionChangeType.MAJOR,
            description="initial",
            new_features=["a"],
        )
        d = entry.to_dict()
        assert d["version"] == "1.0.0"
        assert d["change_type"] == "major"
        assert d["new_features"] == ["a"]


class TestToolSchemaMetadata:
    def test_to_dict_minimal(self):
        meta = ToolSchemaMetadata(tool_name="x", version=SemanticVersion(1, 0, 0))
        d = meta.to_dict()
        assert d["tool_name"] == "x"
        assert d["version"] == "1.0.0"
        assert "deprecation_warnings" not in d

    def test_to_dict_with_deprecation(self):
        meta = ToolSchemaMetadata(
            tool_name="x", version=SemanticVersion(1, 0, 0), description="desc"
        )
        meta.add_deprecation(
            field_name="f", message="m", deprecated_in=SemanticVersion(1, 0, 0)
        )
        d = meta.to_dict()
        assert d["description"] == "desc"
        assert len(d["deprecation_warnings"]) == 1


class TestRegistry:
    def test_get_tool_metadata(self):
        reg = MCPVersionRegistry()
        meta = reg.get_tool_metadata("estimate_run")
        assert meta is not None
        assert meta.tool_name == "estimate_run"

    def test_get_tool_metadata_missing(self):
        reg = MCPVersionRegistry()
        assert reg.get_tool_metadata("not_a_tool") is None

    def test_get_all_tool_metadata(self):
        reg = MCPVersionRegistry()
        all_meta = reg.get_all_tool_metadata()
        assert "research_company" in all_meta

    def test_get_version_history_sorted(self):
        reg = MCPVersionRegistry()
        history = reg.get_version_history()
        assert len(history) >= 1

    def test_add_deprecation(self):
        reg = MCPVersionRegistry()
        reg.add_deprecation("estimate_run", "old", "msg", alternative="new")
        meta = reg.get_tool_metadata("estimate_run")
        assert len(meta.deprecated_fields) == 1
        # removed_in is current + 2 minor versions
        assert meta.deprecated_fields[0].removed_in.minor == reg.CURRENT_VERSION.minor + 2

    def test_add_deprecation_unknown_tool_noop(self):
        reg = MCPVersionRegistry()
        # Should not raise
        reg.add_deprecation("ghost_tool", "old", "msg")

    def test_is_version_supported(self):
        reg = MCPVersionRegistry()
        assert reg.is_version_supported(SemanticVersion(1, 0, 0))
        assert not reg.is_version_supported(SemanticVersion(0, 9, 0))
        assert not reg.is_version_supported(SemanticVersion(2, 0, 0))

    def test_migration_guide_no_migration(self):
        reg = MCPVersionRegistry()
        guide = reg.get_migration_guide(SemanticVersion(1, 0, 0), SemanticVersion(1, 0, 0))
        assert "No migration needed" in guide

    def test_migration_guide_no_breaking(self):
        reg = MCPVersionRegistry()
        # from 1.0.0 to a higher version with no relevant history entries
        guide = reg.get_migration_guide(SemanticVersion(1, 0, 0), SemanticVersion(1, 5, 0))
        assert "No breaking changes" in guide

    def test_migration_guide_with_entries(self):
        reg = MCPVersionRegistry()
        # Inject a history entry with breaking changes + deprecations
        reg._version_history.append(
            VersionHistoryEntry(
                version=SemanticVersion(1, 1, 0),
                date=__import__("datetime").datetime(2026, 2, 1),
                change_type=VersionChangeType.MINOR,
                description="changes",
                breaking_changes=["removed X"],
                deprecations=["deprecated Y"],
            )
        )
        guide = reg.get_migration_guide(SemanticVersion(1, 0, 0), SemanticVersion(1, 1, 0))
        assert "Breaking Changes" in guide
        assert "removed X" in guide
        assert "Deprecations" in guide


class TestInjectAndExtract:
    def test_inject_version_metadata(self):
        meta = ToolSchemaMetadata(tool_name="x", version=SemanticVersion(1, 0, 0))
        schema = inject_version_metadata({"type": "object"}, meta)
        assert schema["metadata"]["tool_name"] == "x"
        assert schema["type"] == "object"

    def test_extract_no_deprecations(self):
        meta = ToolSchemaMetadata(tool_name="x", version=SemanticVersion(1, 0, 0))
        response = {"result": "ok"}
        out = extract_deprecation_warnings(response, meta)
        assert out == response

    def test_extract_with_matching_field(self):
        meta = ToolSchemaMetadata(tool_name="x", version=SemanticVersion(1, 0, 0))
        meta.add_deprecation(
            field_name="old_field", message="m", deprecated_in=SemanticVersion(1, 0, 0)
        )
        response = {"old_field": "value"}
        out = extract_deprecation_warnings(response, meta)
        assert "_deprecation_warnings" in out
        assert len(out["_deprecation_warnings"]) == 1

    def test_extract_no_matching_field(self):
        meta = ToolSchemaMetadata(tool_name="x", version=SemanticVersion(1, 0, 0))
        meta.add_deprecation(
            field_name="old_field", message="m", deprecated_in=SemanticVersion(1, 0, 0)
        )
        response = {"other_field": "value"}
        out = extract_deprecation_warnings(response, meta)
        assert "_deprecation_warnings" not in out


class TestGlobalRegistry:
    def test_singleton(self):
        r1 = get_version_registry()
        r2 = get_version_registry()
        assert r1 is r2
