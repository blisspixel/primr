"""Unit tests for deploy/Dockerfile.

Tests Dockerfile structure for the Primr Job Runner:
- Multi-stage build (builder + runtime)
- Non-root user (primr, uid 1000)
- Entrypoint configuration
- Security best practices

Requirements: 1.1, 1.4
"""

import re
from pathlib import Path

import pytest

DOCKERFILE_PATH = Path(__file__).parent.parent.parent / "deploy" / "Dockerfile"


@pytest.fixture
def dockerfile_content() -> str:
    """Load Dockerfile content."""
    return DOCKERFILE_PATH.read_text()


@pytest.fixture
def dockerfile_lines(dockerfile_content: str) -> list[str]:
    """Split Dockerfile into lines."""
    return dockerfile_content.strip().split("\n")


class TestDockerfileExists:
    """Test Dockerfile exists and has basic structure."""

    def test_dockerfile_exists(self) -> None:
        """Dockerfile exists at deploy/Dockerfile."""
        assert DOCKERFILE_PATH.exists(), f"Dockerfile not found at {DOCKERFILE_PATH}"

    def test_dockerfile_not_empty(self, dockerfile_content: str) -> None:
        """Dockerfile is not empty."""
        assert len(dockerfile_content.strip()) > 0


class TestMultiStageBuild:
    """Test multi-stage build configuration.

    Requirements: 1.1 (job runner contract)
    """

    def test_has_builder_stage(self, dockerfile_content: str) -> None:
        """Has builder stage for building wheel."""
        # Look for "FROM ... AS builder" pattern
        assert re.search(r"FROM\s+\S+\s+AS\s+builder", dockerfile_content, re.IGNORECASE), (
            "Missing builder stage (FROM ... AS builder)"
        )

    def test_has_runtime_stage(self, dockerfile_content: str) -> None:
        """Has runtime stage (second FROM without AS builder)."""
        # Count FROM directives
        from_matches = re.findall(r"^FROM\s+", dockerfile_content, re.MULTILINE)
        assert len(from_matches) >= 2, "Multi-stage build requires at least 2 FROM directives"

    def test_builder_uses_supported_python_floor(self, dockerfile_content: str) -> None:
        """Builder stage uses the supported Python 3.12 floor."""
        # Find builder stage FROM line
        builder_match = re.search(
            r"FROM\s+(python:\S+)\s+AS\s+builder", dockerfile_content, re.IGNORECASE
        )
        assert builder_match is not None, "Builder stage not found"
        assert "3.12" in builder_match.group(1), "Builder should use Python 3.12"

    def test_runtime_uses_supported_python_floor(self, dockerfile_content: str) -> None:
        """Runtime stage uses the supported Python 3.12 slim image."""
        # Find the second FROM (runtime stage)
        from_matches = list(re.finditer(r"^FROM\s+(\S+)", dockerfile_content, re.MULTILINE))
        assert len(from_matches) >= 2, "Need at least 2 FROM directives"

        runtime_image = from_matches[1].group(1)
        assert "python:3.12-slim" in runtime_image, (
            f"Runtime should use python:3.12-slim, got {runtime_image}"
        )

    def test_builder_builds_wheel(self, dockerfile_content: str) -> None:
        """Builder stage builds a wheel."""
        # Look for python -m build --wheel
        assert "python -m build" in dockerfile_content, "Missing wheel build command"
        assert "--wheel" in dockerfile_content, "Missing --wheel flag"

    def test_copies_wheel_from_builder(self, dockerfile_content: str) -> None:
        """Runtime stage copies wheel from builder."""
        # Look for COPY --from=builder
        assert re.search(r"COPY\s+--from=builder", dockerfile_content, re.IGNORECASE), (
            "Missing COPY --from=builder directive"
        )

    def test_installs_wheel(self, dockerfile_content: str) -> None:
        """Runtime stage installs the wheel."""
        # Look for pip install *.whl
        assert re.search(r"pip\s+install.*\.whl", dockerfile_content), (
            "Missing pip install for wheel"
        )


class TestNonRootUser:
    """Test non-root user configuration.

    Requirements: 1.4 (non-root execution)
    """

    def test_creates_primr_user(self, dockerfile_content: str) -> None:
        """Creates primr user."""
        assert "useradd" in dockerfile_content, "Missing useradd command"
        assert "primr" in dockerfile_content, "Missing primr user"

    def test_user_has_uid_1000(self, dockerfile_content: str) -> None:
        """User has UID 1000."""
        # Look for -u 1000 in useradd command
        assert re.search(r"useradd.*-u\s*1000", dockerfile_content), "User should have UID 1000"

    def test_user_directive_sets_primr(self, dockerfile_content: str) -> None:
        """USER directive sets primr user."""
        user_match = re.search(r"^USER\s+(\w+)", dockerfile_content, re.MULTILINE)
        assert user_match is not None, "Missing USER directive"
        assert user_match.group(1) == "primr", f"USER should be primr, got {user_match.group(1)}"

    def test_user_directive_in_runtime_stage(self, dockerfile_lines: list[str]) -> None:
        """USER directive is in runtime stage (after second FROM)."""
        in_runtime = False
        from_count = 0
        user_found = False

        for line in dockerfile_lines:
            stripped = line.strip()
            if stripped.startswith("FROM "):
                from_count += 1
                if from_count >= 2:
                    in_runtime = True
            if in_runtime and stripped.startswith("USER primr"):
                user_found = True
                break

        assert user_found, "USER primr should be in runtime stage"


class TestEntrypoint:
    """Test entrypoint configuration.

    Requirements: 1.1 (job runner contract)
    """

    def test_has_entrypoint(self, dockerfile_content: str) -> None:
        """Has ENTRYPOINT directive."""
        assert "ENTRYPOINT" in dockerfile_content, "Missing ENTRYPOINT directive"

    def test_entrypoint_runs_runner(self, dockerfile_content: str) -> None:
        """ENTRYPOINT runs runner.py."""
        # Look for ENTRYPOINT with runner.py
        assert re.search(r"ENTRYPOINT\s+\[.*runner\.py.*\]", dockerfile_content), (
            "ENTRYPOINT should run runner.py"
        )

    def test_entrypoint_uses_python(self, dockerfile_content: str) -> None:
        """ENTRYPOINT uses python to run runner."""
        # Look for python in ENTRYPOINT
        assert re.search(r"ENTRYPOINT\s+\[.*python.*\]", dockerfile_content), (
            "ENTRYPOINT should use python"
        )


class TestRunnerFiles:
    """Test runner files are included."""

    def test_copies_runner_py(self, dockerfile_content: str) -> None:
        """Copies runner.py to container."""
        assert re.search(r"COPY.*runner\.py", dockerfile_content), "Missing COPY for runner.py"

    def test_copies_manifest_py(self, dockerfile_content: str) -> None:
        """Copies manifest.py to container."""
        assert re.search(r"COPY.*manifest\.py", dockerfile_content), "Missing COPY for manifest.py"

    def test_copies_runner_observability_dependency(self, dockerfile_content: str) -> None:
        """Copies the deployment observability module imported by runner.py."""
        assert "COPY deploy/observability.py /app/deploy/observability.py" in dockerfile_content


class TestSecurityBestPractices:
    """Test security best practices."""

    def test_uses_no_cache_for_pip(self, dockerfile_content: str) -> None:
        """Uses --no-cache-dir for pip install."""
        assert "--no-cache-dir" in dockerfile_content, "Should use --no-cache-dir for pip install"

    def test_cleans_apt_cache(self, dockerfile_content: str) -> None:
        """Cleans apt cache after install."""
        # Only check if apt-get is used
        if "apt-get" in dockerfile_content:
            assert "rm -rf /var/lib/apt/lists" in dockerfile_content, (
                "Should clean apt cache after install"
            )

    def test_no_hardcoded_secrets(self, dockerfile_content: str) -> None:
        """No hardcoded API keys or secrets."""
        # Check for common secret patterns
        secret_patterns = [
            r'GEMINI_API_KEY\s*=\s*["\'][^$\{][^"\']+["\']',  # Non-empty value
            r'SEARCH_API_KEY\s*=\s*["\'][^$\{][^"\']+["\']',
            r"AIza[0-9A-Za-z_-]{35}",  # Google API key pattern
            r"sk-[a-zA-Z0-9]{48}",  # OpenAI API key pattern
            r"AKIA[0-9A-Z]{16}",  # AWS access key pattern
        ]

        for pattern in secret_patterns:
            assert not re.search(pattern, dockerfile_content), (
                f"Found potential hardcoded secret matching pattern: {pattern}"
            )

    def test_no_root_operations_after_user_switch(self, dockerfile_lines: list[str]) -> None:
        """No root operations after USER switch."""
        user_switched = False

        for line in dockerfile_lines:
            stripped = line.strip()

            if stripped.startswith("USER primr"):
                user_switched = True
                continue

            if user_switched:
                # After USER switch, should not see operations requiring root
                assert not stripped.startswith("RUN apt-get"), (
                    "apt-get after USER switch requires root"
                )
                assert not stripped.startswith("RUN useradd"), (
                    "useradd after USER switch requires root"
                )

    def test_pythonunbuffered_set(self, dockerfile_content: str) -> None:
        """PYTHONUNBUFFERED is set for immediate log output."""
        assert "PYTHONUNBUFFERED" in dockerfile_content, (
            "Should set PYTHONUNBUFFERED for immediate log output"
        )


class TestWorkdir:
    """Test working directory configuration."""

    def test_has_workdir(self, dockerfile_content: str) -> None:
        """Has WORKDIR directive."""
        assert "WORKDIR" in dockerfile_content, "Missing WORKDIR directive"

    def test_workdir_is_app(self, dockerfile_content: str) -> None:
        """WORKDIR is /app in runtime stage."""
        # Find WORKDIR in runtime stage
        assert re.search(r"WORKDIR\s+/app", dockerfile_content), "WORKDIR should be /app"
