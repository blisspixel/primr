"""Synchronize the canonical Primr Zero skill into host-specific packaging."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / ".agents" / "skills" / "primr-zero"
TARGETS = (
    REPO_ROOT / "claude-code" / "skills" / "primr-zero",
    REPO_ROOT / "src" / "primr" / "resources" / "skills" / "primr-zero",
)


def _file_map(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def mirrors_match() -> tuple[bool, list[str]]:
    """Return whether every packaged mirror is byte-identical to the source."""

    expected = _file_map(SOURCE)
    failures: list[str] = []
    if not expected:
        failures.append(f"Canonical skill is missing or empty: {SOURCE}")
        return False, failures
    for target in TARGETS:
        actual = _file_map(target)
        if actual == expected:
            continue
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(
            name for name in set(expected) & set(actual) if expected[name] != actual[name]
        )
        failures.append(
            f"{target.relative_to(REPO_ROOT)}: missing={missing}, extra={extra}, changed={changed}"
        )
    return not failures, failures


def sync_mirrors() -> None:
    """Copy the canonical skill and remove stale mirror-only files."""

    expected = _file_map(SOURCE)
    if not expected:
        raise FileNotFoundError(f"Canonical skill is missing or empty: {SOURCE}")
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        for relative, content in expected.items():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or destination.read_bytes() != content:
                shutil.copy2(SOURCE / relative, destination)
        for existing in sorted(target.rglob("*"), reverse=True):
            if existing.is_file() and existing.relative_to(target).as_posix() not in expected:
                existing.unlink()
            elif existing.is_dir() and not any(existing.iterdir()):
                existing.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when a mirror is stale.")
    args = parser.parse_args()

    if not args.check:
        sync_mirrors()
    matches, failures = mirrors_match()
    if matches:
        print("Primr Zero skill mirrors are current.")
        return 0
    for failure in failures:
        print(failure)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
