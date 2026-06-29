from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import primr
from primr.core.cli_keys import create_keys_parser
from primr.core.cli_parser import CLI_EPILOG

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_roadmap_text() -> str:
    return (REPO_ROOT / "ROADMAP.md").read_text(encoding="utf-8")


def _read_pyproject_version() -> str:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    match = re.search(
        r'^\s*version\s*=\s*"(?P<version>\d+\.\d+\.\d+)"\s*$',
        pyproject_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, "pyproject.toml must declare project.version"
    return match.group("version")


def _read_pyproject() -> dict:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    return tomllib.loads(pyproject_path.read_text(encoding="utf-8"))


def _read_pyproject_python_floor() -> str:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    match = re.search(
        r'^\s*requires-python\s*=\s*">=(?P<floor>\d+\.\d+)"\s*$',
        pyproject_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, "pyproject.toml must declare a >=N.N requires-python floor"
    return match.group("floor")


def _read_roadmap_current_state_version() -> str:
    match = re.search(
        r"^Current State:\s+v(?P<version>\d+\.\d+\.\d+)\b",
        _read_roadmap_text(),
        re.MULTILINE,
    )
    assert match is not None, "ROADMAP.md must declare a 'Current State: vX.Y.Z' line"
    return match.group("version")


def _read_citation_version() -> str:
    citation_path = REPO_ROOT / "CITATION.cff"
    match = re.search(
        r"^version:\s*(?P<version>\d+\.\d+\.\d+)\s*$",
        citation_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, "CITATION.cff must declare a 'version: X.Y.Z' field"
    return match.group("version")


def test_package_version_matches_pyproject() -> None:
    assert primr.__version__ == _read_pyproject_version()


def test_roadmap_current_state_matches_package_version() -> None:
    assert _read_roadmap_current_state_version() == primr.__version__


def test_roadmap_changelog_contains_current_state_version() -> None:
    version = _read_roadmap_current_state_version()
    pattern = rf"^\|\s*{re.escape(version)}\s*\|"

    assert re.search(pattern, _read_roadmap_text(), re.MULTILINE), (
        "ROADMAP.md changelog table must include the Current State version"
    )


def test_citation_version_matches_package_version() -> None:
    assert _read_citation_version() == primr.__version__


def test_package_metadata_declares_pep639_apache_license() -> None:
    pyproject = _read_pyproject()
    classifiers = pyproject["project"]["classifiers"]
    license_classifiers = [
        classifier for classifier in classifiers if classifier.startswith("License ::")
    ]

    assert pyproject["project"]["license"] == "Apache-2.0"
    assert license_classifiers == []
    assert "License :: OSI Approved :: MIT License" not in classifiers


def test_release_workflow_builds_on_supported_python_floor() -> None:
    floor = _read_pyproject_python_floor()
    release_workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert release_workflow.count(f"python-version: '{floor}'") == 2
    assert f"Set up Python {floor}" in release_workflow
    assert "python-version: '3.11'" not in release_workflow


def test_package_manifest_excludes_agent_working_files() -> None:
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "prune .agent" in manifest
    assert "prune docs/.agent" in manifest


def test_cli_epilog_uses_current_default_cost_band() -> None:
    assert "~$0.89-$1.01" in CLI_EPILOG
    assert "~$6" not in CLI_EPILOG
    assert "60-90 min" not in CLI_EPILOG


def test_keys_set_help_mentions_all_common_llm_providers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        create_keys_parser().parse_args(["set", "--help"])

    assert exc_info.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "Common choices: xai, gemini, openai, anthropic, ollama" in help_text
