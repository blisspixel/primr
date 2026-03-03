"""
Unit tests for Azure deployment script structure.

Verifies:
- Prerequisite checks
- Secrets commands
- Configuration files structure

Requirements: 6.9, 6.11
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def azure_dir() -> Path:
    """Get the Azure deploy directory path."""
    return Path(__file__).parent.parent.parent / "deploy" / "azure"


class TestAzureDeployScriptExists:
    """Test that required Azure deployment files exist."""

    def test_deploy_sh_exists(self, azure_dir: Path) -> None:
        """deploy.sh should exist."""
        assert (azure_dir / "deploy.sh").exists()

    def test_container_app_yaml_exists(self, azure_dir: Path) -> None:
        """container-app.yaml should exist."""
        assert (azure_dir / "container-app.yaml").exists()

    def test_job_template_yaml_exists(self, azure_dir: Path) -> None:
        """job-template.yaml should exist."""
        assert (azure_dir / "job-template.yaml").exists()


class TestAzureDeployScriptContent:
    """Test Azure deploy.sh script content."""

    def test_has_shebang(self, azure_dir: Path) -> None:
        """Script should have bash shebang."""
        content = (azure_dir / "deploy.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_has_strict_mode(self, azure_dir: Path) -> None:
        """Script should use strict mode."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "set -euo pipefail" in content

    def test_sources_common_sh(self, azure_dir: Path) -> None:
        """Script should source common.sh."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "source" in content and "common.sh" in content

    def test_has_deploy_command(self, azure_dir: Path) -> None:
        """Script should have deploy command."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "cmd_deploy" in content

    def test_has_destroy_command(self, azure_dir: Path) -> None:
        """Script should have destroy command."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "cmd_destroy" in content

    def test_has_validate_command(self, azure_dir: Path) -> None:
        """Script should have validate command."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "cmd_validate" in content

    def test_has_secrets_command(self, azure_dir: Path) -> None:
        """Script should have secrets command."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "cmd_secrets" in content

    def test_has_prerequisite_checks(self, azure_dir: Path) -> None:
        """Script should check prerequisites."""
        content = (azure_dir / "deploy.sh").read_text()
        assert "check_prerequisites" in content
        assert "check_azure_cli" in content


class TestAzureContainerAppConfig:
    """Test Azure Container App configuration."""

    def test_is_valid_yaml(self, azure_dir: Path) -> None:
        """container-app.yaml should be valid YAML."""
        import yaml
        content = (azure_dir / "container-app.yaml").read_text()
        config = yaml.safe_load(content)
        assert isinstance(config, dict)

    def test_has_scale_to_zero(self, azure_dir: Path) -> None:
        """Container App should support scale-to-zero."""
        content = (azure_dir / "container-app.yaml").read_text()
        assert "minReplicas: 0" in content


class TestAzureJobTemplateConfig:
    """Test Azure Container Apps Job configuration."""

    def test_is_valid_yaml(self, azure_dir: Path) -> None:
        """job-template.yaml should be valid YAML."""
        import yaml
        content = (azure_dir / "job-template.yaml").read_text()
        config = yaml.safe_load(content)
        assert isinstance(config, dict)

    def test_has_timeout(self, azure_dir: Path) -> None:
        """Job should have timeout configuration."""
        content = (azure_dir / "job-template.yaml").read_text()
        assert "replicaTimeout: 7200" in content

    def test_has_secrets(self, azure_dir: Path) -> None:
        """Job should reference secrets for LLM keys."""
        content = (azure_dir / "job-template.yaml").read_text()
        assert "keyVaultUrl" in content or "secretRef" in content
