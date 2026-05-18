from __future__ import annotations

from pathlib import Path
import re

import primr

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_pyproject_version() -> str:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    match = re.search(
        r'^\s*version\s*=\s*"(?P<version>\d+\.\d+\.\d+)"\s*$',
        pyproject_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, "pyproject.toml must declare project.version"
    return match.group("version")


def _read_roadmap_current_state_version() -> str:
    roadmap_path = REPO_ROOT / "ROADMAP.md"
    match = re.search(
        r"^Current State:\s+v(?P<version>\d+\.\d+\.\d+)\b",
        roadmap_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, "ROADMAP.md must declare a 'Current State: vX.Y.Z' line"
    return match.group("version")


def test_package_version_matches_pyproject() -> None:
    assert primr.__version__ == _read_pyproject_version()


def test_roadmap_current_state_matches_package_version() -> None:
    assert _read_roadmap_current_state_version() == primr.__version__
