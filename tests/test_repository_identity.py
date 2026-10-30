"""Keep installation and public metadata on the canonical repository."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/pueo-labs/primr"


def test_package_and_citation_use_canonical_repository() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))

    assert project["name"] == "primr"
    assert project["urls"] == {
        "Homepage": REPOSITORY,
        "Documentation": f"{REPOSITORY}#readme",
        "Repository": REPOSITORY,
        "Bug Tracker": f"{REPOSITORY}/issues",
    }
    assert citation["repository-code"] == citation["url"] == REPOSITORY


@pytest.mark.parametrize(
    "manifest", ["claude-code/.claude-plugin/plugin.json", "agent-plugin/plugin.json"]
)
def test_plugin_owner_links_do_not_replace_author_attribution(manifest: str) -> None:
    plugin = json.loads((ROOT / manifest).read_text(encoding="utf-8"))

    assert plugin["homepage"] == plugin["repository"] == REPOSITORY
    assert plugin["author"] == {"name": "blisspixel", "url": "https://github.com/blisspixel"}


def test_pages_configuration_uses_transferred_owner() -> None:
    config = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))

    assert config["site_url"] == "https://pueo-labs.github.io/primr/"
    assert config["repo_url"] == REPOSITORY
    assert config["repo_name"] == "pueo-labs/primr"


@pytest.mark.parametrize("script", ["install.sh", "install.ps1"])
def test_installer_download_and_clone_examples_use_canonical_owner(script: str) -> None:
    installer = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    documentation = (ROOT / "docs" / "INSTALLATION.md").read_text(encoding="utf-8")

    assert f"git clone {REPOSITORY}.git" in installer
    assert f"https://raw.githubusercontent.com/pueo-labs/primr/main/scripts/{script}" in (
        documentation
    )
    assert "blisspixel/primr" not in installer + documentation


def test_claude_setup_loads_existing_plugin_without_a_marketplace() -> None:
    readme = (ROOT / "claude-code" / "README.md").read_text(encoding="utf-8")

    assert f"git clone {REPOSITORY}.git" in readme
    assert "claude --plugin-dir ./claude-code" in readme
    assert (ROOT / "claude-code" / ".claude-plugin" / "plugin.json").is_file()
    assert "/plugin install primr@" not in readme


def test_runtime_support_and_update_addresses() -> None:
    from primr.ai.providers.openrouter import OPENROUTER_APP_HEADERS
    from primr.core.cli_errors import ISSUES_URL
    from primr.utils.version_check import PYPI_JSON_URL

    assert f"{REPOSITORY}/issues" == ISSUES_URL
    assert OPENROUTER_APP_HEADERS["HTTP-Referer"] == REPOSITORY
    assert PYPI_JSON_URL == "https://pypi.org/pypi/primr/json"
