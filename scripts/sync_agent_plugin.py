"""Build the portable Agent Plugins distribution from canonical skills."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "agent-plugin"
SKILL_SOURCES = {
    "primr": REPO_ROOT / "claude-code" / "skills" / "primr",
    "primr-zero": REPO_ROOT / ".agents" / "skills" / "primr-zero",
}

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
_HOST_ONLY_FRONTMATTER = {"allowed-tools", "argument-hint"}


def _package_version() -> str:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _normalize_newlines(content: bytes) -> bytes:
    """Make generated text comparisons independent of checkout line endings."""

    return content.replace(b"\r\n", b"\n")


def _plugin_manifest() -> bytes:
    return _json_bytes(
        {
            "$schema": PLUGIN_SCHEMA,
            "name": "primr",
            "version": _package_version(),
            "description": (
                "Company intelligence through Primr Zero or the estimate-gated "
                "provider-backed Primr pipeline."
            ),
            "author": {
                "name": "blisspixel",
                "url": "https://github.com/blisspixel",
            },
            "homepage": "https://github.com/blisspixel/primr",
            "repository": "https://github.com/blisspixel/primr",
            "license": "Apache-2.0",
            "keywords": ["company-research", "strategic-intelligence", "primr"],
        }
    )


def _mcp_config() -> bytes:
    return _json_bytes(
        {
            "$schema": MCP_SCHEMA,
            "mcpServers": {
                "primr": {
                    "type": "stdio",
                    "command": "primr",
                    "args": ["mcp"],
                }
            },
        }
    )


def _portable_skill_markdown(content: bytes) -> bytes:
    """Remove host-only frontmatter while leaving instructions byte-stable."""

    text = content.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise ValueError("SKILL.md frontmatter is not closed")

    portable_lines = [lines[0]]
    for line in lines[1:closing_index]:
        key = line.split(":", 1)[0].strip()
        if key not in _HOST_ONLY_FRONTMATTER:
            portable_lines.append(line)
    portable_lines.extend(lines[closing_index:])
    return "".join(portable_lines).encode("utf-8")


def _file_map(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def _expected_skill_files() -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    for skill_name, source in SKILL_SOURCES.items():
        files = _file_map(source)
        if not files:
            raise FileNotFoundError(f"Canonical skill is missing or empty: {source}")
        for relative, content in files.items():
            if relative == "SKILL.md":
                content = _portable_skill_markdown(content)
            expected[f"{skill_name}/{relative}"] = content
    return expected


def package_matches() -> tuple[bool, list[str]]:
    """Return whether manifests and generated skill files are current."""

    expected_roots = {
        "plugin.json": _plugin_manifest(),
        "mcp.json": _mcp_config(),
    }
    failures: list[str] = []
    for relative, expected in expected_roots.items():
        path = PLUGIN_ROOT / relative
        actual = path.read_bytes() if path.is_file() else None
        if actual is None or _normalize_newlines(actual) != expected:
            failures.append(f"agent-plugin/{relative} is missing or stale")

    expected_skills = _expected_skill_files()
    actual_skills = _file_map(PLUGIN_ROOT / "skills")
    if actual_skills != expected_skills:
        missing = sorted(set(expected_skills) - set(actual_skills))
        extra = sorted(set(actual_skills) - set(expected_skills))
        changed = sorted(
            name
            for name in set(expected_skills) & set(actual_skills)
            if expected_skills[name] != actual_skills[name]
        )
        failures.append(f"agent-plugin/skills: missing={missing}, extra={extra}, changed={changed}")
    return not failures, failures


def sync_package() -> None:
    """Regenerate the portable manifests and skill mirrors."""

    PLUGIN_ROOT.mkdir(parents=True, exist_ok=True)
    (PLUGIN_ROOT / "plugin.json").write_bytes(_plugin_manifest())
    (PLUGIN_ROOT / "mcp.json").write_bytes(_mcp_config())

    skills_root = PLUGIN_ROOT / "skills"
    expected = _expected_skill_files()
    skills_root.mkdir(parents=True, exist_ok=True)
    for relative, content in expected.items():
        destination = skills_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != content:
            destination.write_bytes(content)
    for existing in sorted(skills_root.rglob("*"), reverse=True):
        relative = existing.relative_to(skills_root).as_posix()
        if existing.is_file() and relative not in expected:
            existing.unlink()
        elif existing.is_dir() and not any(existing.iterdir()):
            existing.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when the package is stale.")
    args = parser.parse_args()

    if not args.check:
        sync_package()
    matches, failures = package_matches()
    if matches:
        print("Portable Agent Plugins package is current.")
        return 0
    for failure in failures:
        print(failure)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
