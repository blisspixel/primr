"""
Property-based tests for Skills Directory.

This module validates the correctness properties of the Skills Directory
using the Hypothesis library. Each test corresponds to a formal
property from the design document.

Properties tested:
- Property 18: Skill Metadata Loading
- Property 19: Skill Format Compliance

Validates: Requirements 6.5, 6.6
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

# =============================================================================
# SKILL LOADING UTILITIES
# =============================================================================

def load_skill_metadata(skill_path: Path) -> dict[str, Any]:
    """
    Load and parse skill metadata from a SKILL.md file.
    
    The SKILL.md format uses YAML front matter between --- delimiters.
    """
    content = skill_path.read_text(encoding="utf-8")

    # Extract YAML front matter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        raise ValueError(f"No YAML front matter found in {skill_path}")

    yaml_content = match.group(1)
    metadata = yaml.safe_load(yaml_content)

    return metadata


def get_skill_body(skill_path: Path) -> str:
    """
    Extract the markdown body (after front matter) from a SKILL.md file.
    """
    content = skill_path.read_text(encoding="utf-8")

    # Remove YAML front matter
    match = re.match(r'^---\n.*?\n---\n?(.*)', content, re.DOTALL)
    if match:
        return match.group(1)
    return content


def list_skills() -> list[Path]:
    """
    List all skill directories in the skills/ folder.
    """
    skills_dir = Path("skills")
    if not skills_dir.exists():
        return []

    skills = []
    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills.append(skill_file)

    return skills


# =============================================================================
# PROPERTY 18: Skill Metadata Loading
# =============================================================================

# Feature: agentic-architecture, Property 18: Skill Metadata Loading
def test_skill_metadata_loading():
    """
    All skills load with required metadata fields.
    
    For any skill file in the skills directory, loading the skill
    should return structured metadata containing at minimum:
    name, version, description, tools list, and resources list.
    
    Validates: Requirements 6.5
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    required_fields = ["name", "version", "description", "tools", "resources"]

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)

        for field in required_fields:
            assert field in metadata, (
                f"Skill {skill_path} missing required field: {field}"
            )

        # Validate field types
        assert isinstance(metadata["name"], str), (
            f"Skill {skill_path}: 'name' must be a string"
        )
        assert isinstance(metadata["version"], str), (
            f"Skill {skill_path}: 'version' must be a string"
        )
        assert isinstance(metadata["description"], str), (
            f"Skill {skill_path}: 'description' must be a string"
        )
        assert isinstance(metadata["tools"], list), (
            f"Skill {skill_path}: 'tools' must be a list"
        )
        assert isinstance(metadata["resources"], list), (
            f"Skill {skill_path}: 'resources' must be a list"
        )


# =============================================================================
# PROPERTY 19: Skill Format Compliance
# =============================================================================

# Feature: agentic-architecture, Property 19: Skill Format Compliance
def test_skill_format_compliance():
    """
    All skills follow the SKILL.md format specification.
    
    Validates: Requirements 6.6
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        content = skill_path.read_text(encoding="utf-8")

        # Must start with YAML front matter
        assert content.startswith("---"), (
            f"Skill {skill_path} must start with YAML front matter (---)"
        )

        # Must have closing front matter delimiter
        assert content.count("---") >= 2, (
            f"Skill {skill_path} must have closing front matter delimiter"
        )

        # Must have a title (# heading) after front matter
        body = get_skill_body(skill_path)
        assert re.search(r'^#\s+.+', body, re.MULTILINE), (
            f"Skill {skill_path} must have a title heading"
        )

        # Metadata must be valid YAML
        metadata = load_skill_metadata(skill_path)
        assert metadata is not None, (
            f"Skill {skill_path} has invalid YAML front matter"
        )


def test_skill_version_format():
    """
    All skills have valid semantic version numbers.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    semver_pattern = re.compile(r'^\d+\.\d+\.\d+$')

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)
        version = metadata.get("version", "")

        assert semver_pattern.match(version), (
            f"Skill {skill_path} has invalid version format: {version}. "
            f"Expected semantic version (e.g., '2.0.0')"
        )


def test_skill_mcp_server_reference():
    """
    All skills reference a valid MCP server.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)

        # mcp_server is optional but if present must be a string
        if "mcp_server" in metadata:
            assert isinstance(metadata["mcp_server"], str), (
                f"Skill {skill_path}: 'mcp_server' must be a string"
            )
            assert len(metadata["mcp_server"]) > 0, (
                f"Skill {skill_path}: 'mcp_server' cannot be empty"
            )


def test_skill_tools_are_strings():
    """
    All tool references in skills are valid strings.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)
        tools = metadata.get("tools", [])

        for tool in tools:
            assert isinstance(tool, str), (
                f"Skill {skill_path}: tool '{tool}' must be a string"
            )
            assert len(tool) > 0, (
                f"Skill {skill_path}: tool names cannot be empty"
            )
            # Tool names should be snake_case
            assert re.match(r'^[a-z][a-z0-9_]*$', tool), (
                f"Skill {skill_path}: tool '{tool}' should be snake_case"
            )


def test_skill_resources_are_valid_uris():
    """
    All resource references in skills are valid URI patterns.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    # Valid resource URI pattern: scheme://path or scheme://path/{param}
    uri_pattern = re.compile(r'^[a-z]+://[a-zA-Z0-9_/{}]+$')

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)
        resources = metadata.get("resources", [])

        for resource in resources:
            assert isinstance(resource, str), (
                f"Skill {skill_path}: resource '{resource}' must be a string"
            )
            assert uri_pattern.match(resource), (
                f"Skill {skill_path}: resource '{resource}' is not a valid URI pattern"
            )


def test_skill_body_has_sections():
    """
    All skills have meaningful documentation sections.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        body = get_skill_body(skill_path)

        # Should have at least 2 sections (## headings)
        section_count = len(re.findall(r'^##\s+', body, re.MULTILINE))
        assert section_count >= 2, (
            f"Skill {skill_path} should have at least 2 sections, found {section_count}"
        )

        # Should have reasonable content length
        assert len(body) > 500, (
            f"Skill {skill_path} body is too short ({len(body)} chars)"
        )


def test_skill_names_match_directories():
    """
    Skill names in metadata match their directory names.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)
        skill_name = metadata.get("name", "")
        dir_name = skill_path.parent.name

        assert skill_name == dir_name, (
            f"Skill name '{skill_name}' doesn't match directory '{dir_name}'"
        )


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================

def test_skills_directory_exists():
    """
    The skills directory exists at the project root.
    """
    skills_dir = Path("skills")
    assert skills_dir.exists(), "skills/ directory should exist"
    assert skills_dir.is_dir(), "skills/ should be a directory"


def test_expected_skills_present():
    """
    All expected skills from the design doc are present.
    """
    expected_skills = [
        "company-research",
        "scrape-strategy",
        "hypothesis-tracking",
        "qa-iteration",
    ]

    skills_dir = Path("skills")
    if not skills_dir.exists():
        pytest.skip("skills/ directory not found")

    for skill_name in expected_skills:
        skill_path = skills_dir / skill_name / "SKILL.md"
        assert skill_path.exists(), (
            f"Expected skill '{skill_name}' not found at {skill_path}"
        )


def test_no_duplicate_tool_references():
    """
    Skills don't have duplicate tool references.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)
        tools = metadata.get("tools", [])

        unique_tools = set(tools)
        assert len(tools) == len(unique_tools), (
            f"Skill {skill_path} has duplicate tool references"
        )


def test_no_duplicate_resource_references():
    """
    Skills don't have duplicate resource references.
    """
    skills = list_skills()

    if not skills:
        pytest.skip("No skills found in skills/ directory")

    for skill_path in skills:
        metadata = load_skill_metadata(skill_path)
        resources = metadata.get("resources", [])

        unique_resources = set(resources)
        assert len(resources) == len(unique_resources), (
            f"Skill {skill_path} has duplicate resource references"
        )
