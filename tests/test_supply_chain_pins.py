"""Supply-chain fitness gates for immutable automation dependencies."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

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


def test_dependency_audits_run_on_a_schedule_without_bot_authored_prs() -> None:
    workflow = WORKFLOW_DIR / "dependency-audit.yml"

    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "uv sync --locked --all-extras" in text
    assert "uv run --no-sync pip-audit" in text
    assert "aquasecurity/trivy-action@" in text
    assert not (ROOT / ".github" / "dependabot.yml").exists()


def test_setup_uv_actions_pin_the_export_tool_version() -> None:
    for workflow in WORKFLOW_DIR.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        setup_count = text.count("astral-sh/setup-uv@")
        assert text.count('version: "0.11.17"') == setup_count, (
            f"{workflow.name} must pin uv 0.11.17 at every setup-uv step"
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
    assert installed_version == "0.11.17", "use the repository-pinned uv release"
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
