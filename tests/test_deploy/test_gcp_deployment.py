"""
Unit tests for GCP deployment script structure.

Verifies:
- Prerequisite checks
- Secrets commands
- Configuration files structure

Requirements: 7.9, 7.11
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def gcp_dir() -> Path:
    """Get the GCP deploy directory path."""
    return Path(__file__).parent.parent.parent / "deploy" / "gcp"


class TestGCPDeployScriptExists:
    """Test that required GCP deployment files exist."""

    def test_deploy_sh_exists(self, gcp_dir: Path) -> None:
        """deploy.sh should exist."""
        assert (gcp_dir / "deploy.sh").exists()

    def test_service_yaml_exists(self, gcp_dir: Path) -> None:
        """service.yaml should exist."""
        assert (gcp_dir / "service.yaml").exists()

    def test_job_yaml_exists(self, gcp_dir: Path) -> None:
        """job.yaml should exist."""
        assert (gcp_dir / "job.yaml").exists()


class TestGCPDeployScriptContent:
    """Test GCP deploy.sh script content."""

    def test_has_shebang(self, gcp_dir: Path) -> None:
        """Script should have bash shebang."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_has_strict_mode(self, gcp_dir: Path) -> None:
        """Script should use strict mode."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "set -euo pipefail" in content

    def test_sources_common_sh(self, gcp_dir: Path) -> None:
        """Script should source common.sh."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "source" in content
        assert "common.sh" in content

    def test_has_deploy_command(self, gcp_dir: Path) -> None:
        """Script should have deploy command."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "cmd_deploy" in content

    def test_has_destroy_command(self, gcp_dir: Path) -> None:
        """Script should have destroy command."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "cmd_destroy" in content

    def test_has_validate_command(self, gcp_dir: Path) -> None:
        """Script should have validate command."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "cmd_validate" in content

    def test_has_secrets_command(self, gcp_dir: Path) -> None:
        """Script should have secrets command."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "cmd_secrets" in content

    def test_has_prerequisite_checks(self, gcp_dir: Path) -> None:
        """Script should check prerequisites."""
        content = (gcp_dir / "deploy.sh").read_text()
        assert "check_prerequisites" in content
        assert "check_gcp_cli" in content


class TestGCPServiceConfig:
    """Test GCP Cloud Run service configuration."""

    def test_is_valid_yaml(self, gcp_dir: Path) -> None:
        """service.yaml should be valid YAML."""
        import yaml

        content = (gcp_dir / "service.yaml").read_text()
        config = yaml.safe_load(content)
        assert isinstance(config, dict)

    def test_has_scale_to_zero(self, gcp_dir: Path) -> None:
        """Cloud Run service should support scale-to-zero."""
        content = (gcp_dir / "service.yaml").read_text()
        assert 'minScale: "0"' in content


class TestGCPJobConfig:
    """Test GCP Cloud Run Job configuration."""

    def test_is_valid_yaml(self, gcp_dir: Path) -> None:
        """job.yaml should be valid YAML."""
        import yaml

        content = (gcp_dir / "job.yaml").read_text()
        config = yaml.safe_load(content)
        assert isinstance(config, dict)

    def test_has_timeout(self, gcp_dir: Path) -> None:
        """Job should have timeout configuration."""
        content = (gcp_dir / "job.yaml").read_text()
        assert "timeoutSeconds: 7200" in content

    def test_has_secrets(self, gcp_dir: Path) -> None:
        """Job should reference secrets for LLM keys."""
        content = (gcp_dir / "job.yaml").read_text()
        assert "secretKeyRef" in content


class TestGCPSecurityContext:
    """Guard the non-root posture of the Cloud Run manifests.

    Non-root execution on Cloud Run fully managed is enforced by the runtime
    image (deploy/Dockerfile runs `USER primr`, uid 1000), which Cloud Run
    honors. The v1 YAML schema does NOT expose a container `securityContext`
    (runAsNonRoot is unsupported and `gcloud run ... replace` rejects it), so
    Trivy's KSV0118 is a justified-ignored platform false-positive (.trivyignore).

    These tests pin that contract so a well-meaning contributor cannot "fix"
    KSV0118 by adding a securityContext block that would break the deploy.
    """

    @pytest.mark.parametrize("manifest", ["job.yaml", "service.yaml"])
    def test_no_security_context(self, gcp_dir: Path, manifest: str) -> None:
        """Cloud Run manifests must not declare a securityContext.

        The field is unsupported by Cloud Run fully managed; adding it breaks
        `gcloud run ... replace`. Non-root is enforced via the Dockerfile USER.
        """
        import yaml

        config = yaml.safe_load((gcp_dir / manifest).read_text())
        spec = config["spec"]["template"]["spec"]
        # Cloud Run Job nests a second template; Service does not.
        if "template" in spec:
            spec = spec["template"]["spec"]
        for container in spec["containers"]:
            assert "securityContext" not in container, (
                f"{manifest} declares a container securityContext; Cloud Run fully "
                "managed does not support it and the deploy will be rejected. "
                "Non-root is enforced via the Dockerfile USER directive."
            )

    def test_dockerfile_enforces_non_root(self) -> None:
        """The image these manifests run must enforce non-root (USER primr)."""
        dockerfile = (Path(__file__).parent.parent.parent / "deploy" / "Dockerfile").read_text()
        assert "USER primr" in dockerfile, (
            "deploy/Dockerfile must run as non-root (USER primr) — this is where "
            "the Cloud Run non-root guarantee lives, since the manifests cannot."
        )
