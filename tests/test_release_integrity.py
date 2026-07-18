from __future__ import annotations

import os
import re
import subprocess
import tarfile
import tomllib
import zipfile
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


def _read_uv_lock() -> dict:
    lock_path = REPO_ROOT / "uv.lock"
    return tomllib.loads(lock_path.read_text(encoding="utf-8"))


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


def _read_citation_release_date() -> str:
    citation_path = REPO_ROOT / "CITATION.cff"
    match = re.search(
        r'^date-released:\s*"(?P<date>\d{4}-\d{2}-\d{2})"\s*$',
        citation_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match is not None, "CITATION.cff must declare date-released as YYYY-MM-DD"
    return match.group("date")


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


def test_citation_date_matches_current_changelog_release() -> None:
    changelog = (REPO_ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## \[{re.escape(primr.__version__)}\] - (?P<date>\d{{4}}-\d{{2}}-\d{{2}})$",
        changelog,
        re.MULTILINE,
    )
    assert match is not None
    assert _read_citation_release_date() == match.group("date")


def test_lockfile_project_version_matches_package_version() -> None:
    editable_packages = [
        package
        for package in _read_uv_lock()["package"]
        if package.get("name") == "primr" and package.get("source") == {"editable": "."}
    ]

    assert len(editable_packages) == 1, "uv.lock must contain one editable primr package"
    assert editable_packages[0]["version"] == primr.__version__


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


def test_release_requires_exact_tag_on_green_main_commit() -> None:
    release_workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "group: primr-release" in release_workflow
    assert release_workflow.count('ref: "refs/tags/${{ steps.meta.outputs.tag }}"') == 1
    assert "tag_sha: ${{ steps.provenance.outputs.tag_sha }}" in release_workflow
    assert "ref: ${{ needs.build.outputs.tag_sha }}" in release_workflow
    assert 'git show-ref --verify --quiet "refs/tags/$TAG"' in release_workflow
    assert 'git merge-base --is-ancestor "$TAG_SHA" origin/main' in release_workflow
    assert "runs?branch=main&head_sha=${TAG_SHA}&event=push" in release_workflow
    assert "gh api --paginate --slurp" not in release_workflow
    assert "seq 1 135" in release_workflow
    assert ".head_sha == $sha" in release_workflow
    assert '.event == "push"' in release_workflow
    assert '.head_branch == "main"' in release_workflow
    assert 'if [ "$REMOTE_TAG_SHA" != "$EXPECTED_TAG_SHA" ]' in release_workflow
    publish_step = "      - name: Publish to PyPI"
    assert release_workflow.index("Require tag unchanged before publication") < (
        release_workflow.index(publish_step)
    )


def test_release_requires_changelog_notes_and_verifies_pypi_hashes() -> None:
    release_workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert 'body = (m.group(1).strip() if m else f"Release {version}.")' not in release_workflow
    assert "No changelog section found" in release_workflow
    assert "scripts/verify_release_artifacts.py" in release_workflow
    assert "Verify published PyPI artifact hashes" in release_workflow
    assert "Check for an existing PyPI release before publishing" in release_workflow
    assert "--allow-absent" in release_workflow
    assert "uv sync --locked --only-group release --no-install-project --python 3.12" in (
        release_workflow
    )
    assert "python -m build --no-isolation" in release_workflow
    assert release_workflow.index("Extract required release notes") < release_workflow.index(
        "Publish to PyPI"
    )
    assert release_workflow.index(
        "Check for an existing PyPI release before publishing"
    ) < release_workflow.index("Publish to PyPI")
    assert "path: .agent/release-automation" not in release_workflow


def test_changelog_contains_current_package_version() -> None:
    version = _read_pyproject_version()
    changelog = (REPO_ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    match = re.search(
        rf"^## \[{re.escape(version)}\](?:\s+-[^\n]*)?\n(?P<body>.*?)(?=\n## \[|\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )

    assert match is not None
    assert match.group("body").strip()


def test_ci_builds_documentation_strictly() -> None:
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "--extra docs" in ci_workflow or "--all-extras" in ci_workflow
    assert "mkdocs build --strict" in ci_workflow


def test_public_install_guidance_avoids_remote_code_piping() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    powershell_installer = (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    shell_installer = (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    combined = "\n".join((readme, powershell_installer, shell_installer)).lower()

    assert readme.index("pipx install primr") < readme.index("convenience installers")
    assert "download and inspect" in readme.lower()
    assert re.search(r"\|\s*(?:iex|bash|sh)\b", combined) is None


def test_installers_separate_keyless_and_provider_backed_next_steps() -> None:
    installers = (
        (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8"),
        (REPO_ROOT / "scripts" / "install.sh").read_text(encoding="utf-8"),
    )

    for installer in installers:
        assert "Keyless agent-host path:" in installer
        assert "Provider-backed path:" in installer
        assert "prep" in installer
        assert "ExampleCo" in installer
        assert "https://example.co --dry-run" in installer
        assert "Review the estimate and approve spend" in installer
        assert "Quick start:" not in installer


def test_security_operations_match_supported_runtime_boundaries() -> None:
    guide = (REPO_ROOT / "docs" / "SECURITY_OPS.md").read_text(encoding="utf-8")
    normalized = " ".join(guide.split())

    assert "process-local development scaffold" in guide
    assert "not wired to the production pipeline" in normalized
    assert "primr://agent/audit/recent?limit=50" in guide
    assert "output/.mcp_audit_log.jsonl" in guide
    assert 'glob("*.log")' not in guide
    assert "log_file.unlink()" not in guide
    assert "rather than CI/CD" not in guide
    assert "Repository CI hard-gates Bandit" in guide
    testing_section = guide.split("## Security Testing", 1)[1].split("## Incident Response", 1)[0]
    assert "official client" in testing_section
    assert "process-local REST scaffold" in testing_section
    assert '"/research"' not in testing_section
    assert "X-API-Key" not in testing_section
    assert "staging-api.example.com" not in testing_section
    assert "provider credentials absent" in testing_section
    assert "provider egress blocked" in testing_section
    assert "separately estimated" in testing_section


def test_all_runtime_surfaces_use_supported_python_floor() -> None:
    floor = _read_pyproject_python_floor()
    compact_floor = floor.replace(".", "")
    pyproject = _read_pyproject()

    deploy_dockerfile = (REPO_ROOT / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    openclaw_dockerfile = (REPO_ROOT / "openclaw" / "Dockerfile.primr").read_text(encoding="utf-8")
    aws_deploy = (REPO_ROOT / "deploy" / "aws" / "deploy.sh").read_text(encoding="utf-8")
    azure_deploy = (REPO_ROOT / "deploy" / "azure" / "deploy.sh").read_text(encoding="utf-8")
    azure_function = (
        REPO_ROOT / "deploy" / "azure" / "bicep" / "modules" / "function.bicep"
    ).read_text(encoding="utf-8")
    compiled_azure_template = (REPO_ROOT / "deploy" / "azure" / "bicep" / "main.json").read_text(
        encoding="utf-8"
    )
    setup_script = (REPO_ROOT / "setup_env.py").read_text(encoding="utf-8")
    init_module = (REPO_ROOT / "src" / "primr" / "core" / "cli_init.py").read_text(encoding="utf-8")
    doctor_module = (REPO_ROOT / "src" / "primr" / "core" / "cli_doctor.py").read_text(
        encoding="utf-8"
    )

    assert deploy_dockerfile.count(f"FROM python:{floor}-slim") == 2
    assert f"FROM python:{floor}-slim" in openclaw_dockerfile
    assert f"--runtime python{floor}" in aws_deploy
    assert f"--runtime-version {floor}" in azure_deploy
    assert f"linuxFxVersion: 'PYTHON|{floor}'" in azure_function
    assert f'"linuxFxVersion": "PYTHON|{floor}"' in compiled_azure_template
    assert pyproject["tool"]["ruff"]["target-version"] == f"py{compact_floor}"

    major, minor = floor.split(".")
    assert f"(v.major, v.minor) >= ({major}, {minor})" in setup_script
    assert f"(v.major, v.minor) < ({major}, {minor})" in setup_script
    for module_text in (init_module, doctor_module):
        assert f"py_version >= ({major}, {minor})" in module_text
        assert f"need {floor}+" in module_text


def test_ci_matrix_matches_declared_python_classifiers() -> None:
    classifiers = _read_pyproject()["project"]["classifiers"]
    supported_versions = {
        classifier.rsplit(" :: ", 1)[-1]
        for classifier in classifiers
        if re.fullmatch(r"Programming Language :: Python :: 3\.\d+", classifier)
    }
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix_match = re.search(r"python-version:\s*\[(?P<versions>[^\]]+)\]", ci_workflow)

    assert matrix_match is not None
    matrix_versions = set(re.findall(r'"(3\.\d+)"', matrix_match.group("versions")))
    assert matrix_versions == supported_versions


def test_dependency_guidance_uses_supported_python_floor() -> None:
    floor = _read_pyproject_python_floor()
    ai_dir = REPO_ROOT / "src" / "primr" / "ai"
    guidance_files = (
        "client.py",
        "async_client.py",
        "deep_research.py",
        "llm.py",
        "report_architect.py",
        "report_aggregator.py",
        "research_executor.py",
    )

    for name in guidance_files:
        text = (ai_dir / name).read_text(encoding="utf-8")
        assert f"Python {floor}+ and project requirements" in text, name


def test_automation_rejects_stale_lockfile() -> None:
    ci_workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    sync_commands = re.findall(r"^\s*run:\s*(uv sync .+)$", ci_workflow, re.MULTILINE)
    export_commands = re.findall(r"^\s*(uv export .+)$", release_workflow, re.MULTILINE)
    assert sync_commands
    assert export_commands
    assert all("--locked" in command and "--frozen" not in command for command in sync_commands)
    assert all("--locked" in command and "--frozen" not in command for command in export_commands)

    assert 'PRIMR_VALIDATE_SDIST: "1"' in ci_workflow
    assert "::test_built_sdist_matches_release_inventory" in ci_workflow


def test_package_manifest_excludes_agent_working_files() -> None:
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "prune .agent" in manifest
    assert "prune docs/.agent" in manifest


def test_package_manifest_has_no_removed_root_inputs() -> None:
    manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "include requirements.txt" not in manifest
    assert "include pytest.ini" not in manifest
    assert "recursive-include docs/examples" not in manifest


def test_built_sdist_matches_release_inventory(tmp_path: Path) -> None:
    if os.environ.get("PRIMR_VALIDATE_SDIST") != "1":
        pytest.skip("Set PRIMR_VALIDATE_SDIST=1 to run the behavior-level packaging gate")

    build = subprocess.run(
        ["uv", "build", "--sdist", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=240,
    )
    assert build.returncode == 0, build.stdout + build.stderr

    build_log = (build.stdout + build.stderr).lower()
    assert "warning: no files found matching" not in build_log
    assert "warning: no previously-included files found matching" not in build_log

    archives = list(tmp_path.glob("*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], mode="r:gz") as archive:
        members = [Path(member.name) for member in archive.getmembers() if member.isfile()]

    roots = {member.parts[0] for member in members}
    assert len(roots) == 1
    paths = {Path(*member.parts[1:]).as_posix() for member in members}

    required_paths = {
        ".agents/skills/primr-zero/SKILL.md",
        ".env.example",
        "LICENSE",
        "README.md",
        "ROADMAP.md",
        "docs/images/primr-demo.png",
        "pyproject.toml",
        "src/primr/py.typed",
        "src/primr/resources/skills/primr-zero/SKILL.md",
    }
    assert required_paths <= paths

    forbidden_paths = {"requirements.txt", "pytest.ini", "setup_env.py"}
    forbidden_prefixes = (
        ".agent/",
        "archive/",
        "build/",
        "dist/",
        "logs/",
        "output/",
        "tests/",
        "working/",
    )
    assert forbidden_paths.isdisjoint(paths)
    assert not any(path.startswith(forbidden_prefixes) for path in paths)
    assert not any(path.endswith((".pyc", ".pyo")) or "__pycache__/" in path for path in paths)

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    skill_root = "primr/resources/skills/primr-zero/"
    with zipfile.ZipFile(wheels[0]) as wheel:
        wheel_paths = set(wheel.namelist())
        assert skill_root + "SKILL.md" in wheel_paths
        packaged_skill = wheel.read(skill_root + "SKILL.md").decode("utf-8")
    assert {
        skill_root + "references/host-capabilities.md",
        skill_root + "references/local-capacity.md",
        skill_root + "references/report-contract.md",
        skill_root + "references/subscription-boundaries.md",
    } <= wheel_paths
    assert "`(Inferred)`" not in packaged_skill
    assert "evidence-based inference under `(Estimated)`" in " ".join(packaged_skill.split())


def test_cli_epilog_uses_current_default_cost_band() -> None:
    assert "~$0.89-$1.01" in CLI_EPILOG
    assert "~$6" not in CLI_EPILOG
    assert "60-90 min" not in CLI_EPILOG
    commands = [line.partition("  #")[0].strip() for line in CLI_EPILOG.splitlines()]
    dry_run = 'primr "Acme Corp" https://acme.example --dry-run'
    launch = 'primr "Acme Corp" https://acme.example'
    assert commands.index(dry_run) < commands.index(launch)


def test_keys_set_help_mentions_all_common_llm_providers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        create_keys_parser().parse_args(["set", "--help"])

    assert exc_info.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "Common choices: xai, gemini, openai, anthropic, ollama" in help_text
