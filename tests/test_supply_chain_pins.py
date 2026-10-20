"""Supply-chain fitness gates for immutable automation dependencies."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
ACTION_USE_RE = re.compile(r"\buses:\s+([^\s@]+)@([^\s#]+)")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}(?:\s|$)")
IGNORED_TREES = {
    ".agent",
    ".git",
    ".pytest_cache",
    ".tox",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "output",
    "working",
}


def _dockerfiles() -> list[Path]:
    paths: list[Path] = []
    for directory, child_directories, filenames in os.walk(ROOT):
        child_directories[:] = [name for name in child_directories if name not in IGNORED_TREES]
        paths.extend(
            Path(directory) / filename
            for filename in filenames
            if filename.startswith("Dockerfile")
        )
    return sorted(paths)


def test_remote_github_actions_are_commit_pinned() -> None:
    violations: list[str] = []
    for workflow in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        for line_number, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            match = ACTION_USE_RE.search(line)
            if match is None or match.group(1).startswith("./"):
                continue
            if not COMMIT_SHA_RE.fullmatch(match.group(2)):
                violations.append(
                    f"{workflow.relative_to(ROOT).as_posix()}:{line_number}: {match.group(0)}"
                )

    assert not violations, "Remote actions must use immutable commit SHAs:\n" + "\n".join(
        violations
    )


def test_docker_base_images_are_digest_pinned() -> None:
    violations: list[str] = []
    for dockerfile in _dockerfiles():
        for line_number, line in enumerate(
            dockerfile.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            stripped = line.strip()
            if not stripped.startswith("FROM ") or stripped.split()[1] == "scratch":
                continue
            if IMAGE_DIGEST_RE.search(stripped) is None:
                violations.append(
                    f"{dockerfile.relative_to(ROOT).as_posix()}:{line_number}: {stripped}"
                )

    assert not violations, "Docker base images must use immutable digests:\n" + "\n".join(
        violations
    )


def test_pillow_security_floor_excludes_known_vulnerable_release() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = {
        requirement.replace(" ", "").lower() for requirement in pyproject["project"]["dependencies"]
    }

    assert "pillow>=12.3.0" in dependencies


@pytest.mark.parametrize(
    ("extra", "package", "vulnerable", "patched"),
    [
        (None, "mcp", "2.0.0", "2.2.0"),
        (None, "mcp", "2.1.1", "2.2.0"),
        (None, "httpx2", "2.9.1", "2.12.0"),
        (None, "httpx2", "2.10.0", "2.12.0"),
        (None, "httpx2", "2.11.0", "2.12.0"),
        (None, "urllib3", "2.7.0", "2.8.0"),
        (None, "certifi", "2026.5.20", "2026.10.19"),
        ("docs", "mkdocs-material", "9.7.6", "9.7.7"),
    ],
)
def test_dependency_security_floors_exclude_affected_versions(
    extra: str | None, package: str, vulnerable: str, patched: str
) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = (
        project["dependencies"] if extra is None else project["optional-dependencies"][extra]
    )
    requirement = next(
        Requirement(value) for value in requirements if Requirement(value).name == package
    )

    assert vulnerable not in requirement.specifier
    assert patched in requirement.specifier
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = [entry["version"] for entry in lock["package"] if entry["name"] == package]
    assert versions, f"{package} must remain in the existing dependency graph"
    assert all(version in requirement.specifier for version in versions)


@pytest.mark.parametrize(
    ("package", "vulnerable", "patched"),
    [
        ("anyio", "4.14.1", "4.14.2"),
        ("pyjwt", "2.14.0", "2.15.1"),
        ("soupsieve", "2.8.4", "2.9.0"),
        ("virtualenv", "21.14.3", "21.14.4"),
    ],
)
def test_transitive_security_constraints_and_locked_versions(
    package: str, vulnerable: str, patched: str
) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = map(Requirement, project["tool"]["uv"]["constraint-dependencies"])
    constraints = {requirement.name.lower(): requirement for requirement in requirements}
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = [entry["version"] for entry in lock["package"] if entry["name"] == package]
    specifier = constraints[package].specifier

    assert vulnerable not in specifier
    assert patched in specifier
    assert versions, f"{package} must remain in the existing dependency graph"
    assert all(version in specifier for version in versions)


def test_scheduled_audits_and_grouped_dependency_proposals() -> None:
    workflow = WORKFLOW_DIR / "dependency-audit.yml"

    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "uv sync --locked --all-extras" in text
    assert "uv run --no-sync pip-audit" in text
    assert "aquasecurity/trivy-action@" in text
    updates = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    assert updates["version"] == 2
    assert {entry["package-ecosystem"] for entry in updates["updates"]} == {
        "uv",
        "github-actions",
        "docker",
    }
    for entry in updates["updates"]:
        assert entry["open-pull-requests-limit"] <= 2
        assert entry["schedule"]["interval"] == "weekly"
        groups = list(entry["groups"].values())
        assert any(group.get("applies-to") == "security-updates" for group in groups)
        version_groups = [
            group
            for group in groups
            if group.get("applies-to", "version-updates") == "version-updates"
        ]
        assert version_groups
        assert all(set(group["update-types"]) <= {"minor", "patch"} for group in version_groups)
    docker = next(entry for entry in updates["updates"] if entry["package-ecosystem"] == "docker")
    assert set(docker["directories"]) == {"/deploy", "/openclaw"}


def test_setup_uv_actions_pin_the_export_tool_version() -> None:
    for workflow in WORKFLOW_DIR.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        setup_count = text.count("astral-sh/setup-uv@")
        assert text.count('version: "0.11.33"') == setup_count, (
            f"{workflow.name} must pin uv 0.11.33 at every setup-uv step"
        )


def test_container_requirement_exports_match_uv_lock() -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is required to verify deployment lock exports"
    installed_version = subprocess.run(
        [uv, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[1]
    assert installed_version == "0.11.33", "use the repository-pinned uv release"
    exports = {
        ROOT / "deploy" / "runtime-requirements.lock": ["--no-dev", "--extra", "api"],
        ROOT / "deploy" / "build-requirements.lock": [
            "--only-group",
            "release",
            "--prune",
            "cyclonedx-bom",
            "--prune",
            "twine",
        ],
    }

    with tempfile.TemporaryDirectory() as directory:
        for tracked_path, selection_args in exports.items():
            generated_path = Path(directory) / tracked_path.name
            subprocess.run(
                [
                    uv,
                    "export",
                    "--locked",
                    *selection_args,
                    "--no-emit-project",
                    "--no-header",
                    "--no-annotate",
                    "--output-file",
                    str(generated_path),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            assert tracked_path.read_bytes() == generated_path.read_bytes()


def test_container_requirement_exports_have_stable_checkout_line_endings() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "deploy/*-requirements.lock text eol=lf" in attributes.splitlines()


def test_container_installs_are_hash_locked_and_local_project_only() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    deploy = (ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    openclaw = (ROOT / "openclaw" / "Dockerfile.primr").read_text(encoding="utf-8")

    for dockerfile in (deploy, openclaw):
        assert "build-requirements.lock" in dockerfile
        assert "runtime-requirements.lock" in dockerfile
        assert "pip install --no-cache-dir --require-hashes" in dockerfile
        assert "pip install --no-cache-dir --no-deps" in dockerfile
    assert "pip install --no-cache-dir fastapi pydantic uvicorn" not in deploy
    assert "pip install --user --no-cache-dir primr" not in openclaw
    assert f"ARG PRIMR_VERSION={version}" in openclaw

    ci = (WORKFLOW_DIR / "ci.yml").read_text(encoding="utf-8")
    assert "docker build --file deploy/Dockerfile" in ci
    assert 'docker build --file "$context/Dockerfile.primr"' in ci
    assert 'cp -R openclaw/. "$context/"' in ci
    assert "cp pyproject.toml MANIFEST.in README.md" in ci
    assert 'cp -R src "$context/src"' in ci
    assert "import deploy.runner; import deploy.storage" in ci
    assert "primr-mcp --help" in ci

    openclaw_docs = (ROOT / "docs" / "OPENCLAW.md").read_text(encoding="utf-8")
    assert "cp pyproject.toml MANIFEST.in README.md" in openclaw_docs
    assert "cp -r src" in openclaw_docs
    assert "build-requirements.lock" in openclaw_docs
