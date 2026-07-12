"""Supply-chain fitness gates for immutable automation dependencies."""

from __future__ import annotations

import os
import re
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
