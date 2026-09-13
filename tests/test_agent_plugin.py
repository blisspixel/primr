"""Contracts for the generated portable Agent Plugins v1 artifact."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from scripts.sync_agent_plugin import (
    MCP_SCHEMA,
    PLUGIN_ROOT,
    PLUGIN_SCHEMA,
    SKILL_SOURCES,
    package_matches,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = REPO_ROOT / "tests" / "fixtures" / "agent_plugins_v1"
ALLOWED_SKILL_FRONTMATTER = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_metadata(skill_path: Path) -> dict:
    content = skill_path.read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    assert match is not None, f"Missing YAML frontmatter: {skill_path}"
    metadata = yaml.safe_load(match.group(1))
    assert isinstance(metadata, dict)
    return metadata


def test_agent_plugin_manifests_validate_against_pinned_v1_schemas() -> None:
    plugin = _load_json(PLUGIN_ROOT / "plugin.json")
    mcp = _load_json(PLUGIN_ROOT / "mcp.json")
    plugin_schema = _load_json(SCHEMA_ROOT / "plugin.schema.json")
    mcp_schema = _load_json(SCHEMA_ROOT / "mcp.schema.json")

    assert plugin_schema["$id"] == PLUGIN_SCHEMA
    assert mcp_schema["$id"] == MCP_SCHEMA
    Draft202012Validator(plugin_schema).validate(plugin)
    Draft202012Validator(mcp_schema).validate(mcp)


def test_agent_plugin_identity_matches_the_python_package() -> None:
    plugin = _load_json(PLUGIN_ROOT / "plugin.json")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert plugin["name"] == "primr"
    assert plugin["version"] == pyproject["project"]["version"]
    assert plugin["license"] == "Apache-2.0"
    assert plugin["$schema"] == PLUGIN_SCHEMA


def test_agent_plugin_exposes_only_the_intended_stdio_server() -> None:
    config = _load_json(PLUGIN_ROOT / "mcp.json")

    assert config == {
        "$schema": MCP_SCHEMA,
        "mcpServers": {
            "primr": {
                "type": "stdio",
                "command": "primr",
                "args": ["mcp"],
                "cwd": "${PLUGIN_DATA}",
            }
        },
    }


def test_agent_plugin_skills_are_immediate_valid_agent_skill_children() -> None:
    skills_root = PLUGIN_ROOT / "skills"
    skill_dirs = {path.name: path for path in skills_root.iterdir() if path.is_dir()}

    assert set(skill_dirs) == set(SKILL_SOURCES) == {"primr", "primr-zero"}
    for skill_name, skill_dir in skill_dirs.items():
        metadata = _skill_metadata(skill_dir / "SKILL.md")
        assert metadata["name"] == skill_name
        assert 1 <= len(metadata["description"]) <= 1024
        assert set(metadata) <= ALLOWED_SKILL_FRONTMATTER


def test_agent_plugin_has_no_paths_that_escape_its_root() -> None:
    resolved_root = PLUGIN_ROOT.resolve()
    for path in PLUGIN_ROOT.rglob("*"):
        assert not path.is_symlink()
        assert path.resolve().is_relative_to(resolved_root)


def test_agent_plugin_generated_files_match_canonical_sources() -> None:
    matches, failures = package_matches()
    assert matches, "\n".join(failures)

    portable_operator = (PLUGIN_ROOT / "skills" / "primr" / "SKILL.md").read_text(encoding="utf-8")
    assert "argument-hint:" not in portable_operator
    assert "allowed-tools:" not in portable_operator


def test_agent_plugin_drift_check_normalizes_manifest_newlines(monkeypatch) -> None:
    original_read_bytes = Path.read_bytes
    manifest_paths = {PLUGIN_ROOT / "plugin.json", PLUGIN_ROOT / "mcp.json"}

    def read_bytes_with_windows_newlines(path: Path) -> bytes:
        content = original_read_bytes(path)
        if path in manifest_paths:
            content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return content

    monkeypatch.setattr(Path, "read_bytes", read_bytes_with_windows_newlines)

    matches, failures = package_matches()

    assert matches, "\n".join(failures)


def test_agent_plugin_documents_experimental_scope_and_spend_boundary() -> None:
    readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    operator = (PLUGIN_ROOT / "skills" / "primr" / "SKILL.md").read_text(encoding="utf-8")
    normalized_operator = " ".join(operator.split())

    assert "published [Agent Plugins v1.0.0" in readme
    assert "Working Draft" not in readme
    assert "Claude Code is not claimed as a portable-v1 client" in readme
    assert "does not authorize a paid Primr run" in readme
    assert "Configured API keys are capability, not consent to spend" in readme
    assert "## The billable cost gate (non-negotiable)" in operator
    assert "fresh estimate and explicit approval" in normalized_operator


def test_vscode_native_config_uses_servers_instead_of_portable_mcp_servers() -> None:
    config = _load_json(REPO_ROOT / "clients" / "vscode" / "mcp.json")
    portable = _load_json(PLUGIN_ROOT / "mcp.json")["mcpServers"]["primr"]

    # VS Code's workspace schema differs from portable Agent Plugins and
    # Windsurf. Keep this directly usable at .vscode/mcp.json.
    assert set(config) == {"servers"}
    assert config["servers"] == {
        "primr": {key: portable[key] for key in ("type", "command", "args")}
    }
    readme = (REPO_ROOT / "clients" / "README.md").read_text(encoding="utf-8")
    assert "[`vscode/mcp.json`](vscode/mcp.json)" in readme


def test_installed_controller_preserves_state_across_plugin_replacement(tmp_path: Path) -> None:
    # Copy the package to an installed layout so repository-root detection
    # cannot conceal writes to the plugin directory. Use the current
    # interpreter's dependencies without installing or downloading anything.
    installed = tmp_path / "installed" / "site-packages"
    shutil.copytree(
        REPO_ROOT / "src" / "primr",
        installed / "primr",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    plugin_data = tmp_path / "persistent data"
    plugin_data.mkdir()
    script = textwrap.dedent(
        """\
        import asyncio
        import json
        import sys
        from pathlib import Path

        sys.path.insert(0, sys.argv[1])
        # Windows creates an internal loopback socket pair for the event
        # loop. Initialize that before denying application network calls.
        runner = asyncio.Runner()
        runner.get_loop()

        def deny_egress(event, args):
            if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen"}:
                raise AssertionError(f"Controller startup attempted egress: {event}")

        sys.addaudithook(deny_egress)
        from primr.config.config import OUTPUT_DIR, PROJECT_ROOT, WORKING_DIR
        from primr.mcp_server.server import create_mcp_server
        from primr.mcp_server.types import ResearchStage

        async def inspect_controller():
            server = create_mcp_server(skip_background_tasks=True)
            async with server.controller_lifecycle():
                ready, _ = server.readiness_snapshot()
                assert ready
                if sys.argv[2] == "plugin v1":
                    # Persist a synthetic terminal record without dispatching
                    # a worker, research tool, or provider call.
                    job = server.job_store.create("ExampleCo", "full")
                    job.advance_stage(ResearchStage.CANCELLED)
                    server.job_store.update(job)
                else:
                    job = server.job_store.get_latest_terminal()
                    assert job is not None
                    assert job.company_name == "ExampleCo"
                    assert job.current_stage == ResearchStage.CANCELLED
                result = {
                    "job_id": job.job_id,
                    "root": str(PROJECT_ROOT),
                    "output": str(Path(OUTPUT_DIR).resolve()),
                    "working": str(Path(WORKING_DIR).resolve()),
                    "journal": str(server.job_store.journal_path.resolve()),
                    "audit": str(server.audit_log.path.resolve()),
                }
            print(json.dumps(result))

        with runner:
            runner.run(inspect_controller())
        """
    )
    expected = {
        "root": str(plugin_data),
        "output": str(plugin_data / "output"),
        "working": str(plugin_data / "working"),
        "journal": str(plugin_data / "output" / ".mcp_job_journal.json"),
        "audit": str(plugin_data / "output" / ".mcp_audit_log.jsonl"),
    }
    retained_report = plugin_data / "output" / "retained-report.md"
    retained_job_id = None
    for installation in ("plugin v1", "plugin v2"):
        plugin_root = tmp_path / installation
        shutil.copytree(PLUGIN_ROOT, plugin_root)
        # Portable package directories may be immutable. File blockers make
        # accidental state creation fail on Windows as well as POSIX.
        for directory in ("output", "working", "logs"):
            (plugin_root / directory).write_text("package content", encoding="utf-8")
        manifest = _load_json(plugin_root / "mcp.json")["mcpServers"]["primr"]
        cwd = manifest.get("cwd", str(plugin_root)).replace("${PLUGIN_DATA}", str(plugin_data))
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"}
        }
        environment.update(
            PLUGIN_ROOT=str(plugin_root),
            PLUGIN_DATA=str(plugin_data),
            PRIMR_CONFIG_DIR=str(tmp_path / "empty-config"),
        )
        process = subprocess.run(
            [sys.executable, "-I", "-c", script, str(installed), installation],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert process.returncode == 0, process.stdout + process.stderr
        observed = json.loads(process.stdout.strip().splitlines()[-1])
        job_id = observed.pop("job_id")
        assert observed == expected
        assert Path(expected["journal"]).is_file()
        assert Path(expected["audit"]).is_file()
        if installation == "plugin v1":
            retained_job_id = job_id
            retained_report.write_text("retained deliverable", encoding="utf-8")
        else:
            assert job_id == retained_job_id
            assert retained_report.read_text(encoding="utf-8") == "retained deliverable"
        for directory in ("output", "working", "logs"):
            assert (plugin_root / directory).read_text(encoding="utf-8") == "package content"
