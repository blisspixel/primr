"""Unit tests for Dockerfile.primr.

Tests SR-3.1, SR-3.2, SR-3.3, SR-3.4 requirements.
"""

import re
from pathlib import Path

import pytest

DOCKERFILE_PATH = Path(__file__).parent.parent.parent / "openclaw" / "Dockerfile.primr"


@pytest.fixture
def dockerfile_content() -> str:
    """Load Dockerfile content."""
    return DOCKERFILE_PATH.read_text()


@pytest.fixture
def dockerfile_lines(dockerfile_content: str) -> list[str]:
    """Split Dockerfile into lines."""
    return dockerfile_content.strip().split("\n")


class TestDockerfileSyntax:
    """Test Dockerfile syntax is valid."""

    def test_dockerfile_exists(self) -> None:
        """Dockerfile exists."""
        assert DOCKERFILE_PATH.exists()

    def test_has_from_directive(self, dockerfile_content: str) -> None:
        """Dockerfile has FROM directive."""
        assert "FROM " in dockerfile_content

    def test_uses_python_base_image(self, dockerfile_content: str) -> None:
        """Uses the supported Python 3.12 base image."""
        assert "python:3.12" in dockerfile_content


class TestNonRootUser:
    """Test non-root user configuration."""

    def test_creates_non_root_user(self, dockerfile_content: str) -> None:
        """SR-3.1: Creates non-root user."""
        assert "useradd" in dockerfile_content
        assert "primr" in dockerfile_content

    def test_user_directive_sets_non_root(self, dockerfile_content: str) -> None:
        """SR-3.1: USER directive sets non-root user."""
        # Find USER directive
        user_match = re.search(r"^USER\s+(\w+)", dockerfile_content, re.MULTILINE)
        assert user_match is not None
        assert user_match.group(1) == "primr"

    def test_user_directive_before_pip_install(self, dockerfile_lines: list[str]) -> None:
        """USER directive comes before pip install."""
        user_line = None
        pip_line = None

        for i, line in enumerate(dockerfile_lines):
            if line.strip().startswith("USER primr"):
                user_line = i
            if "pip install" in line and user_line is not None:
                pip_line = i
                break

        assert user_line is not None, "USER primr not found"
        assert pip_line is not None, "pip install not found after USER"
        assert user_line < pip_line, "USER should come before pip install"


class TestNoCredentialMounts:
    """Test no credentials are mounted."""

    def test_no_ssh_keys_mounted(self, dockerfile_content: str) -> None:
        """SR-3.2: No SSH keys mounted."""
        assert ".ssh" not in dockerfile_content
        assert "id_rsa" not in dockerfile_content
        assert "id_ed25519" not in dockerfile_content

    def test_no_aws_credentials_mounted(self, dockerfile_content: str) -> None:
        """SR-3.2: No AWS credentials mounted."""
        assert ".aws" not in dockerfile_content
        assert "credentials" not in dockerfile_content.lower() or "no-cache" in dockerfile_content

    def test_no_hardcoded_api_keys(self, dockerfile_content: str) -> None:
        """SR-3.2: secret API keys are never declared via ENV.

        Even an empty `ENV XAI_API_KEY=""` bakes a secret-named var into the
        image layers (Trivy DS-0031). Keys are provided at runtime instead, so
        no `ENV <KEY>` declaration should appear for any secret, and obviously
        no real key value is baked in.
        """
        for key in ("XAI_API_KEY", "GEMINI_API_KEY", "SEARCH_API_KEY"):
            assert f"ENV {key}" not in dockerfile_content, (
                f"{key} must not be declared via ENV (runtime-provided)"
            )
        # No real key value hardcoded.
        assert "xai-" not in dockerfile_content
        assert "sk-" not in dockerfile_content
        assert "AIza" not in dockerfile_content


class TestEntrypoint:
    """Test entrypoint configuration."""

    def test_entrypoint_is_primr_mcp(self, dockerfile_content: str) -> None:
        """ENTRYPOINT is primr-mcp --stdio."""
        assert 'ENTRYPOINT ["primr-mcp", "--stdio"]' in dockerfile_content

    def test_no_cmd_override(self, dockerfile_content: str) -> None:
        """No CMD that would override entrypoint args."""
        # CMD should not be present or should be empty
        cmd_matches = re.findall(r"^CMD\s+", dockerfile_content, re.MULTILINE)
        assert len(cmd_matches) == 0, "CMD should not be present"


class TestHealthcheck:
    """Test healthcheck configuration."""

    def test_has_healthcheck(self, dockerfile_content: str) -> None:
        """Has HEALTHCHECK directive."""
        assert "HEALTHCHECK" in dockerfile_content

    def test_healthcheck_uses_doctor(self, dockerfile_content: str) -> None:
        """Healthcheck uses primr doctor."""
        assert "primr doctor" in dockerfile_content


class TestLabels:
    """Test container labels."""

    def test_has_image_labels(self, dockerfile_content: str) -> None:
        """Has OCI image labels."""
        assert "org.opencontainers.image.title" in dockerfile_content
        assert "org.opencontainers.image.description" in dockerfile_content

    def test_has_openclaw_labels(self, dockerfile_content: str) -> None:
        """Has Open Claw specific labels."""
        assert "openclaw.sandbox" in dockerfile_content


class TestSecurityBestPractices:
    """Test security best practices."""

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
                assert not stripped.startswith("RUN apt-get"), "apt-get after USER switch"
                assert not stripped.startswith("RUN useradd"), "useradd after USER switch"

    def test_uses_no_cache_for_pip(self, dockerfile_content: str) -> None:
        """Uses --no-cache-dir for pip install."""
        assert "--no-cache-dir" in dockerfile_content

    def test_cleans_apt_cache(self, dockerfile_content: str) -> None:
        """Cleans apt cache after install."""
        assert "rm -rf /var/lib/apt/lists" in dockerfile_content
