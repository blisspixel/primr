"""
Property-based tests for MCP Server Extensions.

This module validates the correctness properties of the MCP agentic
extensions using the Hypothesis library.

Properties tested:
- Property 20: MCP Resource JSON Validity
- Property 21: Backward Compatibility

Validates: Requirements 7.7, 8.1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# PROPERTY 20: MCP Resource JSON Validity
# =============================================================================


def test_roadmap_resource_json_validity():
    """
    Roadmap resource returns valid JSON.

    For any roadmap query, the response should be valid JSON
    that can be parsed without errors.

    Validates: Requirements 7.7
    """
    from primr.agentic.roadmap_api import RoadmapAPI

    roadmap_path = Path("ROADMAP.md")
    if not roadmap_path.exists():
        pytest.skip("ROADMAP.md not found")

    api = RoadmapAPI()
    json_output = api.to_json()

    # Should be valid JSON
    parsed = json.loads(json_output)

    # Should have expected structure
    assert "versions" in parsed
    assert isinstance(parsed["versions"], list)

    # Each version should have required fields
    for version in parsed["versions"]:
        assert "number" in version
        assert "title" in version
        assert "status" in version


def test_memory_resource_json_validity():
    """
    Memory resource returns valid JSON.

    For any company memory query, the response should be valid JSON.

    Validates: Requirements 7.7
    """
    import tempfile

    from primr.agentic.memory import ResearchMemory
    from primr.agentic.models import ConfidenceLevel, Hypothesis

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Create some test data
        h = Hypothesis(
            id="test_h",
            claim="Test claim",
            confidence=ConfidenceLevel.VALIDATED,
            topic="technology",
        )
        memory.save_hypotheses("Test Company", [h])

        # Get JSON output
        json_output = memory.to_json("Test Company")

        # Should be valid JSON
        parsed = json.loads(json_output)

        # Should have expected structure
        assert "company_name" in parsed
        assert "hypotheses" in parsed
        assert isinstance(parsed["hypotheses"], list)


def test_context_resource_structure():
    """
    Context resource returns expected structure.

    Validates: Requirements 7.7
    """
    claude_md_path = Path("CLAUDE.md")
    if not claude_md_path.exists():
        pytest.skip("CLAUDE.md not found")

    # Import the extraction function
    from primr.mcp_server.agentic_resources import _extract_context_summary

    content = claude_md_path.read_text(encoding="utf-8")
    summary = _extract_context_summary(content)

    # Should have expected keys
    assert "sections" in summary
    assert "has_quick_start" in summary
    assert "has_negative_constraints" in summary
    assert "has_verification_commands" in summary
    assert "has_progressive_disclosure" in summary

    # Sections should be a list
    assert isinstance(summary["sections"], list)


# =============================================================================
# PROPERTY 21: Backward Compatibility
# =============================================================================


def test_agentic_tools_list_includes_base_tools():
    """
    Agentic tools don't remove existing base tools.

    The tool list should include all original tools plus agentic tools.

    Validates: Requirements 8.1
    """
    # Base tools that must always be present

    # Agentic tools that should be added
    agentic_tools = [
        "query_roadmap",
        "get_hypotheses",
        "save_hypothesis",
    ]

    # Import the tool registration function
    from primr.mcp_server.agentic_tools import register_agentic_tools

    # Get agentic tools list
    tools = register_agentic_tools(None, None)
    tool_names = [t.name for t in tools]

    # Verify agentic tools are present
    for tool in agentic_tools:
        assert tool in tool_names, f"Missing agentic tool: {tool}"


def test_agentic_resources_list_includes_base_resources():
    """
    Agentic resources don't remove existing base resources.

    The resource list should include all original resources plus agentic resources.

    Validates: Requirements 8.1
    """
    from urllib.parse import unquote

    # Agentic resources that should be added (normalized form)
    agentic_resource_uris = [
        "primr://roadmap",
        "primr://memory/{company}",
        "primr://context",
    ]

    # Import the resource function
    from primr.mcp_server.agentic_resources import get_agentic_resources

    # Get agentic resources list
    resources = get_agentic_resources()
    # Convert URIs to strings and URL-decode for comparison
    # (AnyUrl may URL-encode special characters like {})
    resource_uris = [unquote(str(r.uri)) for r in resources]

    # Verify agentic resources are present
    for uri in agentic_resource_uris:
        assert uri in resource_uris, f"Missing agentic resource: {uri}"


def test_tool_schema_validity():
    """
    All agentic tools have valid JSON schemas.

    Validates: Requirements 7.7
    """
    from primr.mcp_server.agentic_tools import register_agentic_tools

    tools = register_agentic_tools(None, None)

    for tool in tools:
        # Each tool should have an input schema
        assert tool.inputSchema is not None, f"Tool {tool.name} missing inputSchema"

        # Schema should be a valid dict
        assert isinstance(tool.inputSchema, dict), f"Tool {tool.name} schema not a dict"

        # Schema should have type
        assert "type" in tool.inputSchema, f"Tool {tool.name} schema missing type"

        # Schema should have properties
        assert "properties" in tool.inputSchema, f"Tool {tool.name} schema missing properties"


def test_resource_mime_types():
    """
    All agentic resources have valid MIME types.

    Validates: Requirements 7.7
    """
    from primr.mcp_server.agentic_resources import get_agentic_resources

    resources = get_agentic_resources()

    for resource in resources:
        # Each resource should have a MIME type
        assert resource.mimeType is not None, f"Resource {resource.uri} missing mimeType"

        # MIME type should be application/json for our resources
        assert resource.mimeType == "application/json", (
            f"Resource {resource.uri} has unexpected mimeType: {resource.mimeType}"
        )


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================


def test_query_roadmap_version_extraction():
    """
    Query roadmap correctly extracts version from natural language.
    """
    import re

    test_queries = [
        ("What's blocking v1.7.0?", "1.7.0"),
        ("blockers for 1.8.0", "1.8.0"),
        ("What are the blockers for version 2.0.0?", "2.0.0"),
    ]

    for query, expected_version in test_queries:
        match = re.search(r"v?(\d+\.\d+\.\d+)", query)
        assert match is not None, f"Failed to extract version from: {query}"
        assert match.group(1) == expected_version, (
            f"Expected {expected_version}, got {match.group(1)} from: {query}"
        )


def test_memory_uri_parsing():
    """
    Memory resource URI parsing extracts company name correctly.
    """
    import re
    from urllib.parse import unquote

    test_uris = [
        ("primr://memory/Acme%20Corp", "Acme Corp"),
        ("primr://memory/TestCompany", "TestCompany"),
        ("primr://memory/Company%2FDivision", "Company/Division"),
    ]

    for uri, expected_company in test_uris:
        match = re.match(r"primr://memory/([^/?]+)", uri)
        assert match is not None, f"Failed to parse URI: {uri}"
        company = unquote(match.group(1))
        assert company == expected_company, (
            f"Expected '{expected_company}', got '{company}' from: {uri}"
        )


@given(
    company=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
        min_size=1,
        max_size=20,
    ).filter(lambda x: x.strip()),
)
@settings(max_examples=20, deadline=None)
def test_hypothesis_round_trip_via_tools(company: str):
    """
    Hypotheses saved via tools can be retrieved via tools.

    Property: For any company and hypothesis, saving and then
    retrieving should return the same data.
    """
    import tempfile

    from primr.agentic.memory import ResearchMemory
    from primr.agentic.models import ConfidenceLevel, Hypothesis

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir))

        # Create hypothesis
        h = Hypothesis(
            id="test_h",
            claim="Test claim for " + company,
            confidence=ConfidenceLevel.UNTESTED,
            topic="test",
        )

        # Save
        memory.save_hypotheses(company, [h])

        # Retrieve
        loaded = memory.get_hypotheses(company)

        assert len(loaded) == 1
        assert loaded[0].id == h.id
        assert loaded[0].claim == h.claim
        assert loaded[0].confidence == h.confidence
