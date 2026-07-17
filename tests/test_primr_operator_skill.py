"""Contracts for paid-to-zero routing in Primr operator guidance."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILL = REPO_ROOT / "claude-code" / "skills" / "primr" / "SKILL.md"
AGENT_GUIDE = REPO_ROOT / "AGENTS.md"


def test_claude_operator_skill_frontmatter_is_valid() -> None:
    content = CLAUDE_SKILL.read_text(encoding="utf-8")
    frontmatter = content.split("---", 2)[1]
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "primr"
    assert "free" in metadata["description"]
    assert metadata["argument-hint"].startswith('"Company Name" https://')


def test_operator_guides_intercept_zero_cost_requests_before_billable_modes() -> None:
    for path in (CLAUDE_SKILL, AGENT_GUIDE):
        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.split())

        assert "## Zero-cost host handoff (precedes billable modes)" in content
        assert "This routing decision takes precedence over the billable cost gate" in normalized
        assert 'Never answer "there is no free tier"' in normalized
        assert "after a paid estimate was shown, declined, or cancelled" in normalized
        assert "If the dedicated `primr-zero` skill is available, use it." in content
        assert "It is not Primr Zero" in content
        assert content.index("## Zero-cost host handoff") < content.index(
            "## The billable cost gate"
        )


def test_inline_zero_cost_fallback_is_complete() -> None:
    content = CLAUDE_SKILL.read_text(encoding="utf-8")

    for command in (
        "primr --version",
        'primr prep "Company" https://company.example --dry-run',
        'primr prep "Company" https://company.example',
    ):
        assert command in content
    for artifact in (
        "prep_manifest.json",
        "source_index.json",
        "research_packet.md",
        "HOST_WORKFLOW.md",
        "primr-zero/SKILL.md",
    ):
        assert artifact in content


def test_claude_plugin_version_matches_package_and_bundles_zero_skill() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = json.loads(
        (REPO_ROOT / "claude-code" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    skill_root = REPO_ROOT / "claude-code" / "skills"

    assert plugin["version"] == pyproject["project"]["version"]
    assert {
        "company-brief",
        "primr",
        "primr-zero",
    } <= {path.name for path in skill_root.iterdir() if path.is_dir()}
    assert (skill_root / "primr-zero" / "SKILL.md").is_file()
