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
