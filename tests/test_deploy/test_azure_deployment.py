"""
Unit tests for Azure deployment script structure.

Verifies:
- Prerequisite checks
- Secrets commands
- Configuration files structure

Requirements: 6.9, 6.11
"""

from __future__ import annotations

import json
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
        assert "source" in content
        assert "common.sh" in content

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
    """Test the separate Cosmos-backed primr-api control-plane template."""

    def test_is_valid_yaml(self, azure_dir: Path) -> None:
        """container-app.yaml should be valid YAML."""
        import yaml

        content = (azure_dir / "container-app.yaml").read_text()
        config = yaml.safe_load(content)
        assert isinstance(config, dict)

    def test_has_scale_to_zero(self, azure_dir: Path) -> None:
        """The shared-state control-plane API may support scale-to-zero."""
        content = (azure_dir / "container-app.yaml").read_text()
        assert "minReplicas: 0" in content


class TestContainerAppMcpAuth:
    """Regression guards for the public-MCP authentication posture.

    The Container App bicep module starts `primr-mcp --http` behind a public
    external ingress. A prior revision passed `--no-auth`, which exposed
    research_company / check_jobs / cancel_job to any unauthenticated caller
    on the internet (a critical disclosure + cloud-spend vuln). These tests
    pin the fix so it can't silently regress.
    """

    @pytest.fixture
    def bicep(self, azure_dir: Path) -> str:
        return (azure_dir / "bicep" / "modules" / "container-app.bicep").read_text()

    def test_mcp_command_does_not_disable_auth(self, bicep: str) -> None:
        # The actual command array (not the explanatory comment) must not
        # carry --no-auth. Scan only the `command:` line to ignore the
        # comment block that documents the removal.
        command_lines = [
            line for line in bicep.splitlines() if "command:" in line and "primr-mcp" in line
        ]
        assert command_lines, "expected a primr-mcp command line in the bicep module"
        for line in command_lines:
            assert "--no-auth" not in line, f"public MCP must require auth: {line.strip()}"

    def test_mcp_jwt_secret_is_wired(self, bicep: str) -> None:
        # Auth middleware reads MCP_JWT_SECRET; it must be sourced from Key
        # Vault, never inlined, so the authenticated path actually works.
        assert "MCP_JWT_SECRET" in bicep
        assert "secretRef: 'mcp-jwt-secret'" in bicep

    def test_ingress_terminates_tls(self, bicep: str) -> None:
        assert "allowInsecure: false" in bicep


class TestContainerAppMcpControllerTopology:
    """Pin the process-local MCP controller to one persistent replica."""

    @pytest.fixture
    def main_bicep(self, azure_dir: Path) -> str:
        return (azure_dir / "bicep" / "main.bicep").read_text()

    @pytest.fixture
    def module_bicep(self, azure_dir: Path) -> str:
        return (azure_dir / "bicep" / "modules" / "container-app.bicep").read_text()

    def test_main_template_constrains_both_replica_parameters(self, main_bicep: str) -> None:
        assert main_bicep.count("@minValue(1)") >= 2
        assert main_bicep.count("@maxValue(1)") >= 2
        assert "param minReplicas int = 1" in main_bicep
        assert "param maxReplicas int = 1" in main_bicep

    def test_mcp_module_is_single_replica_without_http_scaler(self, module_bicep: str) -> None:
        assert "param minReplicas int = 1" in module_bicep
        assert "param maxReplicas int = 1" in module_bicep
        assert "activeRevisionsMode: 'Single'" in module_bicep
        assert "http-scaling" not in module_bicep

    def test_liveness_and_readiness_use_distinct_routes(self, module_bicep: str) -> None:
        assert module_bicep.count("type: 'Liveness'") == 1
        assert module_bicep.count("type: 'Readiness'") == 1
        assert module_bicep.count("path: '/healthz'") == 1
        assert module_bicep.count("path: '/readyz'") == 1

    def test_deployment_wrappers_pass_exactly_one_replica(self, azure_dir: Path) -> None:
        shell = (azure_dir / "deploy.sh").read_text()
        powershell = (azure_dir / "deploy.ps1").read_text()

        assert "MIN_REPLICAS=1" in shell
        assert "MAX_REPLICAS=1" in shell
        assert '"https://${fqdn}/readyz"' in shell
        assert '"minReplicas=1"' in powershell
        assert '"maxReplicas=1"' in powershell
        assert '"https://$fqdn/readyz"' in powershell

    def test_validation_wrappers_fail_closed(self, azure_dir: Path) -> None:
        shell = (azure_dir / "deploy.sh").read_text()
        powershell = (azure_dir / "deploy.ps1").read_text()

        assert "Invoke-Expression" not in powershell
        assert "$LASTEXITCODE -eq 0" in powershell
        assert "Smoke test: FAIL (Container App FQDN unavailable)" in powershell
        assert 'if [[ -z "$fqdn" ]]; then' in shell
        assert 'log_error "Cannot determine Container App FQDN"' in shell
        assert (
            "return 1"
            in shell.split('if [[ -z "$fqdn" ]]; then', maxsplit=1)[1].split("else", maxsplit=1)[0]
        )

    def test_compiled_template_matches_controller_contract(self, azure_dir: Path) -> None:
        template = json.loads((azure_dir / "bicep" / "main.json").read_text())
        for parameter in ("minReplicas", "maxReplicas"):
            assert template["parameters"][parameter]["defaultValue"] == 1
            assert template["parameters"][parameter]["minValue"] == 1
            assert template["parameters"][parameter]["maxValue"] == 1

        deployment = next(
            resource
            for resource in template["resources"]
            if resource["name"] == "[format('{0}-container-app', parameters('deploymentName'))]"
        )
        container_app = next(
            resource
            for resource in deployment["properties"]["template"]["resources"]
            if resource["type"] == "Microsoft.App/containerApps"
        )
        probes = container_app["properties"]["template"]["containers"][0]["probes"]
        assert container_app["properties"]["configuration"]["activeRevisionsMode"] == "Single"
        assert [(probe["type"], probe["httpGet"]["path"]) for probe in probes] == [
            ("Liveness", "/healthz"),
            ("Readiness", "/readyz"),
        ]


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
