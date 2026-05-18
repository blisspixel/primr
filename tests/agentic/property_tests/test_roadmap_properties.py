"""
Property-based tests for Roadmap API.

This module validates the correctness properties of the Roadmap API
using the Hypothesis library. Each test corresponds to a formal
property from the design document.

Properties tested:
- Property 1: Roadmap API Round-Trip Consistency
- Property 2: Roadmap Cache Invalidation
- Property 3: Roadmap Dependency Graph Acyclicity
- Property 4: Roadmap Status Partitioning

Validates: Requirements 2.1, 2.4, 2.5, 2.6, 2.7
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.agentic.models import VersionStatus
from primr.agentic.roadmap_api import RoadmapAPI

# =============================================================================
# STRATEGIES
# =============================================================================

# Strategy for version numbers
version_numbers = st.from_regex(r"[1-9]\.[0-9]\.[0-9]", fullmatch=True)

# Strategy for version titles (ASCII only for Windows compatibility)
version_titles = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), max_codepoint=127),
    min_size=5,
    max_size=50,
).filter(lambda x: x.strip())

# Strategy for feature names (ASCII only for Windows compatibility)
feature_names = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs"), max_codepoint=127),
    min_size=3,
    max_size=30,
).filter(lambda x: x.strip())

# Strategy for version status
version_statuses = st.sampled_from(list(VersionStatus))


@st.composite
def roadmap_content(draw, num_versions: int | None = None):
    """
    Strategy for generating valid ROADMAP.md content.

    Args:
        num_versions: Number of versions to generate (random if None)
    """
    if num_versions is None:
        num_versions = draw(st.integers(min_value=1, max_value=5))

    lines = ["# Roadmap\n"]

    # Generate versions in order
    for i in range(num_versions):
        major = 1
        minor = i
        patch = 0
        version_num = f"{major}.{minor}.{patch}"

        title = draw(version_titles)
        status = draw(version_statuses)

        # Add version header
        status_hint = f"({status.value})" if status != VersionStatus.PLANNED else ""
        lines.append(f"\n### v{version_num} - {title} {status_hint}\n")

        # Add some features
        num_features = draw(st.integers(min_value=0, max_value=3))
        for _j in range(num_features):
            feature_name = draw(feature_names)
            lines.append(f"- {feature_name}\n")

    return "\n".join(lines)


# =============================================================================
# PROPERTY 1: Roadmap API Round-Trip Consistency
# =============================================================================


# Feature: agentic-architecture, Property 1: Roadmap API Round-Trip Consistency
@given(content=roadmap_content())
@settings(max_examples=20, deadline=None)
def test_roadmap_round_trip(content: str):
    """
    Parsing and serializing roadmap preserves structure.

    For any valid ROADMAP.md content, parsing into the data model
    and then serializing to JSON and deserializing should produce
    an equivalent data structure.

    Validates: Requirements 2.1, 2.6
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        roadmap_path.write_text(content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)

        # Get all versions
        versions = api.list_all_versions()

        # Serialize to dict
        data = api.to_dict()

        # Verify structure
        assert "versions" in data
        assert "dependency_graph" in data

        # Verify version count matches
        assert len(data["versions"]) == len(versions)

        # Verify each version is present
        for v in versions:
            assert v.number in data["versions"]
            v_data = data["versions"][v.number]
            assert v_data["number"] == v.number
            assert v_data["status"] == v.status.value


# =============================================================================
# PROPERTY 2: Roadmap Cache Invalidation
# =============================================================================


# Feature: agentic-architecture, Property 2: Roadmap Cache Invalidation
def test_cache_invalidation():
    """
    Roadmap API reflects file changes without restart.

    For any modification to ROADMAP.md, the next query to RoadmapAPI
    should reflect the updated content without requiring a restart.

    Validates: Requirements 2.7
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"

        # Initial content
        initial_content = """# Roadmap

### v1.0.0 - Initial Release (Complete)
- Feature A
"""
        roadmap_path.write_text(initial_content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)

        # Verify initial state
        versions = api.list_all_versions()
        assert len(versions) == 1
        assert versions[0].number == "1.0.0"

        # Wait a moment to ensure mtime changes
        time.sleep(0.1)

        # Update content
        updated_content = """# Roadmap

### v1.0.0 - Initial Release (Complete)
- Feature A

### v1.1.0 - Second Release (Planned)
- Feature B
"""
        roadmap_path.write_text(updated_content, encoding="utf-8")

        # Query again - should see new version
        versions = api.list_all_versions()
        assert len(versions) == 2

        version_nums = {v.number for v in versions}
        assert "1.0.0" in version_nums
        assert "1.1.0" in version_nums


# =============================================================================
# PROPERTY 3: Roadmap Dependency Graph Acyclicity
# =============================================================================


# Feature: agentic-architecture, Property 3: Roadmap Dependency Graph Acyclicity
@given(content=roadmap_content(num_versions=3))
@settings(max_examples=20, deadline=None)
def test_dependency_graph_acyclic(content: str):
    """
    Dependency graph contains no cycles.

    For any roadmap with version dependencies, the dependency graph
    returned by get_dependency_graph() should be acyclic (no version
    can transitively depend on itself).

    Validates: Requirements 2.4
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        roadmap_path.write_text(content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)
        graph = api.get_dependency_graph()

        # Check for cycles using DFS
        def has_cycle(node: str, visited: set, rec_stack: set) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        visited: set[str] = set()
        for node in graph:
            if node not in visited:
                assert not has_cycle(node, visited, set()), f"Cycle detected starting from {node}"


# =============================================================================
# PROPERTY 4: Roadmap Status Partitioning
# =============================================================================


# Feature: agentic-architecture, Property 4: Roadmap Status Partitioning
@given(content=roadmap_content())
@settings(max_examples=20, deadline=None)
def test_status_partitioning(content: str):
    """
    Status filters partition all versions.

    For any roadmap, the union of list_by_status(COMPLETED),
    list_by_status(IN_PROGRESS), list_by_status(PLANNED), and
    list_by_status(DEFERRED) should equal the set of all versions.

    Validates: Requirements 2.5
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        roadmap_path.write_text(content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)

        # Get all versions
        all_versions = {v.number for v in api.list_all_versions()}

        # Get versions by each status
        completed = {v.number for v in api.list_by_status(VersionStatus.COMPLETED)}
        in_progress = {v.number for v in api.list_by_status(VersionStatus.IN_PROGRESS)}
        planned = {v.number for v in api.list_by_status(VersionStatus.PLANNED)}
        deferred = {v.number for v in api.list_by_status(VersionStatus.DEFERRED)}

        # Union should equal all versions
        union = completed | in_progress | planned | deferred
        assert union == all_versions, (
            f"Status partition mismatch: union={union}, all={all_versions}"
        )

        # Sets should be disjoint (no version in multiple statuses)
        assert completed.isdisjoint(in_progress)
        assert completed.isdisjoint(planned)
        assert completed.isdisjoint(deferred)
        assert in_progress.isdisjoint(planned)
        assert in_progress.isdisjoint(deferred)
        assert planned.isdisjoint(deferred)


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================


def test_get_version_not_found():
    """Getting a non-existent version returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        roadmap_path.write_text("# Roadmap\n\n### v1.0.0 - Test\n", encoding="utf-8")

        api = RoadmapAPI(roadmap_path)

        assert api.get_version("2.0.0") is None
        assert api.get_version("v2.0.0") is None


def test_get_blockers_with_dependencies():
    """Blockers include incomplete dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        content = """# Roadmap

### v1.0.0 - First (Planned)
- Feature A

### v1.1.0 - Second (Planned)
- Feature B
"""
        roadmap_path.write_text(content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)

        # v1.1.0 should be blocked by v1.0.0
        blockers = api.get_blockers("1.1.0")
        assert len(blockers) > 0
        assert any("1.0.0" in b for b in blockers)


def test_missing_roadmap_file():
    """Missing roadmap file results in empty versions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        # Don't create the file

        api = RoadmapAPI(roadmap_path)

        versions = api.list_all_versions()
        assert len(versions) == 0


def test_json_serialization():
    """JSON serialization produces valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        content = """# Roadmap

### v1.0.0 - Test Release (Complete)
- Feature A
- Feature B
"""
        roadmap_path.write_text(content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)
        json_str = api.to_json()

        # Should be valid JSON
        import json

        data = json.loads(json_str)

        assert "versions" in data
        assert "dependency_graph" in data
        assert isinstance(data["versions"], list)


def test_version_with_v_prefix():
    """Version queries work with or without 'v' prefix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        roadmap_path = Path(tmpdir) / "ROADMAP.md"
        content = """# Roadmap

### v1.0.0 - Test
- Feature
"""
        roadmap_path.write_text(content, encoding="utf-8")

        api = RoadmapAPI(roadmap_path)

        # Both should work
        v1 = api.get_version("1.0.0")
        v2 = api.get_version("v1.0.0")

        assert v1 is not None
        assert v2 is not None
        assert v1.number == v2.number
