"""Contracts for paid-to-zero routing in Primr operator guidance."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from scripts.sync_primr_operator_skill import mirrors_match as operator_mirrors_match

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILL = REPO_ROOT / "claude-code" / "skills" / "primr" / "SKILL.md"
AGENT_GUIDE = REPO_ROOT / "AGENTS.md"
README = REPO_ROOT / "README.md"
AGENT_INTEGRATION = REPO_ROOT / "docs" / "AGENT_INTEGRATION.md"
PROJECT_SKILL_ROOT = REPO_ROOT / ".claude" / "skills"


def test_claude_operator_skill_frontmatter_is_valid() -> None:
    content = CLAUDE_SKILL.read_text(encoding="utf-8")
    frontmatter = content.split("---", 2)[1]
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "primr"
    assert "bare Primr company-and-URL request" in metadata["description"]
    assert "Default to Primr Zero" in metadata["description"]
    assert "explicitly requests paid" in metadata["description"]
    assert metadata["argument-hint"].startswith('"Company Name" https://')
    allowed_tools = metadata["allowed-tools"]
    for tool in ("Read", "Write", "WebSearch", "WebFetch"):
        assert tool in allowed_tools


def test_bare_primr_agent_requests_default_to_zero_without_new_syntax() -> None:
    for path in (CLAUDE_SKILL, AGENT_GUIDE):
        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.split())

        assert "## Agent-host default" in content
        assert 'primr "Company" https://company.example' in content
        assert "Primr Zero by default" in normalized
        assert "Do not make the user choose" in normalized
        assert "Configured API keys are capability, not consent to spend" in normalized
        assert "not a CLI compatibility change" in normalized
        assert "primr start" not in content.lower()
        assert content.index("## Agent-host default") < content.index("## The billable cost gate")


def test_public_docs_explain_agent_default_and_direct_cli_boundary() -> None:
    for path in (README, AGENT_INTEGRATION):
        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.split())

        assert 'primr "Company" https://company.example' in content or (
            'primr "ExampleCo" https://example.co' in content
        )
        assert "defaults to Primr Zero" in normalized
        assert "provider-backed" in normalized
        assert "directly in a terminal" in normalized


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


def test_provider_backed_background_launch_uses_noninteractive_approval() -> None:
    for path in (CLAUDE_SKILL, AGENT_GUIDE):
        content = path.read_text(encoding="utf-8")
        normalized = " ".join(content.split())

        assert "replace `--dry-run` with `--skip-confirm`" in normalized
        assert "background command must include `--skip-confirm`" in normalized
        assert "pipe `y`" in normalized

    for path in (README, AGENT_INTEGRATION):
        normalized = " ".join(path.read_text(encoding="utf-8").split())
        assert "--skip-confirm" in normalized
        assert "background" in normalized


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

    normalized = " ".join(content.split())
    assert "Without shell access" in content
    assert "instead of writing from model memory" in normalized
    assert "when the Primr launcher is unavailable and installation is declined" in normalized
    assert "Do not stall on the missing launcher" in normalized


def test_project_claude_skills_are_discoverable_and_synchronized() -> None:
    matches, failures = operator_mirrors_match()

    assert matches, "\n".join(failures)
    assert (PROJECT_SKILL_ROOT / "primr" / "SKILL.md").is_file()
    assert (PROJECT_SKILL_ROOT / "primr-zero" / "SKILL.md").is_file()
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/.claude/*" in gitignore
    assert "!/.claude/skills/**" in gitignore


def test_client_guidance_keeps_zero_useful_without_a_launcher() -> None:
    content = (REPO_ROOT / "clients" / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    assert "host-native research when it does not" in normalized
    assert "Without one, the skill uses the host's official web research" in normalized
    assert ".claude/skills/primr-zero/" in content
    assert "needs the `primr-zero` skill and shell access" not in normalized


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
