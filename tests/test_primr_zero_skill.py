"""Contract tests for the portable Primr Zero Agent Skill."""

from __future__ import annotations

import re
from importlib.resources import files

import yaml

from scripts.sync_primr_zero_skill import SOURCE, mirrors_match


def test_primr_zero_skill_uses_portable_frontmatter() -> None:
    content = (SOURCE / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match is not None
    metadata = yaml.safe_load(match.group(1))
    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == "primr-zero"
    assert "zero Primr model API spend" in metadata["description"]
    assert "bare Primr company-and-URL request" in metadata["description"]
    assert "Verify that the host is plan-backed" in metadata["description"]
    assert "TODO" not in content


def test_primr_zero_is_the_agent_host_default_without_changing_cli_semantics() -> None:
    content = (SOURCE / "SKILL.md").read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    assert "## Agent-host default" in content
    assert 'primr "Company" https://company.example' in content
    assert "use this skill by default" in normalized
    assert "Do not ask the user to choose a Primr mode" in normalized
    assert "do not infer spend consent from configured provider keys" in normalized
    assert "does not change the provider-backed behavior" in normalized


def test_primr_zero_references_are_present() -> None:
    expected = {
        "host-capabilities.md",
        "local-capacity.md",
        "report-contract.md",
        "subscription-boundaries.md",
    }
    actual = {path.name for path in (SOURCE / "references").glob("*.md")}
    assert actual == expected


def test_primr_zero_defines_a_tool_neutral_downstream_handoff() -> None:
    content = (SOURCE / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())

    assert "primr --list-recent --json" in content
    assert "artifact_role: primary_report" in content
    assert "artifact_role: strategy_module" in content
    assert "Do not assume a specific skill" in normalized_content


def test_packaged_skill_mirrors_are_current() -> None:
    matches, failures = mirrors_match()
    assert matches, "\n".join(failures)


def test_openai_interface_mentions_the_skill() -> None:
    metadata_path = SOURCE / "agents" / "openai.yaml"
    data = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    prompt = data["interface"]["default_prompt"]
    assert "$primr-zero" in prompt
    assert "verify the host billing basis" in prompt.lower()
    assert 25 <= len(data["interface"]["short_description"]) <= 64


def test_installed_package_exposes_primr_zero_skill() -> None:
    root = files("primr").joinpath("resources", "skills", "primr-zero")
    assert root.joinpath("SKILL.md").is_file()
    assert {path.name for path in root.joinpath("references").iterdir() if path.is_file()} == {
        "host-capabilities.md",
        "local-capacity.md",
        "report-contract.md",
        "subscription-boundaries.md",
    }
