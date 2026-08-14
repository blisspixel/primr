"""Contracts for the generated portable Agent Plugins v1 artifact."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from scripts.sync_agent_plugin import (
    MCP_SCHEMA,
    PLUGIN_ROOT,
    PLUGIN_SCHEMA,
    SKILL_SOURCES,
    package_matches,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = REPO_ROOT / "tests" / "fixtures" / "agent_plugins_v1"
ALLOWED_SKILL_FRONTMATTER = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_metadata(skill_path: Path) -> dict:
    content = skill_path.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    assert match is not None, f"Missing YAML frontmatter: {skill_path}"
    metadata = yaml.safe_load(match.group(1))
    assert isinstance(metadata, dict)
    return metadata


def test_agent_plugin_manifests_validate_against_pinned_v1_schemas() -> None:
    plugin = _load_json(PLUGIN_ROOT / "plugin.json")
    mcp = _load_json(PLUGIN_ROOT / "mcp.json")
    plugin_schema = _load_json(SCHEMA_ROOT / "plugin.schema.json")
    mcp_schema = _load_json(SCHEMA_ROOT / "mcp.schema.json")

    assert plugin_schema["$id"] == PLUGIN_SCHEMA
    assert mcp_schema["$id"] == MCP_SCHEMA
    Draft202012Validator(plugin_schema).validate(plugin)
    Draft202012Validator(mcp_schema).validate(mcp)


def test_agent_plugin_identity_matches_the_python_package() -> None:
    plugin = _load_json(PLUGIN_ROOT / "plugin.json")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert plugin["name"] == "primr"
    assert plugin["version"] == pyproject["project"]["version"]
    assert plugin["license"] == "Apache-2.0"
    assert plugin["$schema"] == PLUGIN_SCHEMA


def test_agent_plugin_exposes_only_the_intended_stdio_server() -> None:
    config = _load_json(PLUGIN_ROOT / "mcp.json")

    assert config == {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            "primr": {
                "type": "stdio",
                "command": "primr",
                "args": ["mcp"],
            }
        },
    }


def test_agent_plugin_skills_are_immediate_valid_agent_skill_children() -> None:
    skills_root = PLUGIN_ROOT / "skills"
    skill_dirs = {path.name: path for path in skills_root.iterdir() if path.is_dir()}

    assert set(skill_dirs) == set(SKILL_SOURCES) == {"primr", "primr-zero"}
    for skill_name, skill_dir in skill_dirs.items():
        metadata = _skill_metadata(skill_dir / "SKILL.md")
        assert metadata["name"] == skill_name
        assert 1 <= len(metadata["description"]) <= 1024
        assert set(metadata) <= ALLOWED_SKILL_FRONTMATTER


def test_agent_plugin_has_no_paths_that_escape_its_root() -> None:
    resolved_root = PLUGIN_ROOT.resolve()
    for path in PLUGIN_ROOT.rglob("*"):
        assert not path.is_symlink()
        assert path.resolve().is_relative_to(resolved_root)


def test_agent_plugin_generated_files_match_canonical_sources() -> None:
    matches, failures = package_matches()
    assert matches, "\n".join(failures)

    portable_operator = (PLUGIN_ROOT / "skills" / "primr" / "SKILL.md").read_text(encoding="utf-8")
    assert "argument-hint:" not in portable_operator
    assert "allowed-tools:" not in portable_operator


def test_agent_plugin_drift_check_normalizes_manifest_newlines(monkeypatch) -> None:
    original_read_bytes = Path.read_bytes
    manifest_paths = {PLUGIN_ROOT / "plugin.json", PLUGIN_ROOT / "mcp.json"}

    def read_bytes_with_windows_newlines(path: Path) -> bytes:
        content = original_read_bytes(path)
        if path in manifest_paths:
            content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return content

    monkeypatch.setattr(Path, "read_bytes", read_bytes_with_windows_newlines)

    matches, failures = package_matches()

    assert matches, "\n".join(failures)


def test_agent_plugin_documents_experimental_scope_and_spend_boundary() -> None:
    readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    operator = (PLUGIN_ROOT / "skills" / "primr" / "SKILL.md").read_text(encoding="utf-8")
    normalized_operator = " ".join(operator.split())

    assert "v1.0.0 Working Draft" in readme
    assert "Claude Code is not claimed as a portable-v1 client" in readme
    assert "does not authorize a paid Primr run" in readme
    assert "Configured API keys are capability, not consent to spend" in readme
    assert "## The billable cost gate (non-negotiable)" in operator
    assert "fresh estimate and explicit approval" in normalized_operator
