"""
Unit tests for AWS deployment script structure.

Verifies:
- Prerequisite checks
- Secrets commands
- Configuration files structure

Requirements: 5.9, 5.11
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def deploy_dir() -> Path:
    """Get the deploy directory path."""
    return Path(__file__).parent.parent.parent / "deploy"


@pytest.fixture
def aws_dir(deploy_dir: Path) -> Path:
    """Get the AWS deploy directory path."""
    return deploy_dir / "aws"


@pytest.fixture
def lib_dir(deploy_dir: Path) -> Path:
    """Get the lib directory path."""
    return deploy_dir / "lib"


# =============================================================================
# SCRIPT STRUCTURE TESTS
# =============================================================================

class TestDeployScriptExists:
    """Test that required deployment files exist."""
    
    def test_deploy_sh_exists(self, aws_dir: Path) -> None:
        """deploy.sh should exist."""
        assert (aws_dir / "deploy.sh").exists()
    
    def test_sqs_queue_json_exists(self, aws_dir: Path) -> None:
        """sqs-queue.json should exist."""
        assert (aws_dir / "sqs-queue.json").exists()
    
    def test_step_function_json_exists(self, aws_dir: Path) -> None:
        """step-function.json should exist."""
        assert (aws_dir / "step-function.json").exists()
    
    def test_task_definition_json_exists(self, aws_dir: Path) -> None:
        """task-definition.json should exist."""
        assert (aws_dir / "task-definition.json").exists()
    
    def test_common_sh_exists(self, lib_dir: Path) -> None:
        """common.sh should exist."""
        assert (lib_dir / "common.sh").exists()


class TestDeployScriptContent:
    """Test deploy.sh script content."""
    
    def test_has_shebang(self, aws_dir: Path) -> None:
        """Script should have bash shebang."""
        content = (aws_dir / "deploy.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")
    
    def test_has_strict_mode(self, aws_dir: Path) -> None:
        """Script should use strict mode."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "set -euo pipefail" in content
    
    def test_sources_common_sh(self, aws_dir: Path) -> None:
        """Script should source common.sh."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "source" in content and "common.sh" in content
    
    def test_has_deploy_command(self, aws_dir: Path) -> None:
        """Script should have deploy command."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "cmd_deploy" in content
    
    def test_has_destroy_command(self, aws_dir: Path) -> None:
        """Script should have destroy command."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "cmd_destroy" in content

    def test_has_validate_command(self, aws_dir: Path) -> None:
        """Script should have validate command."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "cmd_validate" in content
    
    def test_has_secrets_command(self, aws_dir: Path) -> None:
        """Script should have secrets command."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "cmd_secrets" in content
    
    def test_has_prerequisite_checks(self, aws_dir: Path) -> None:
        """Script should check prerequisites."""
        content = (aws_dir / "deploy.sh").read_text()
        assert "check_prerequisites" in content
        assert "check_docker" in content
        assert "check_aws_cli" in content


class TestSQSQueueConfig:
    """Test SQS queue configuration."""
    
    def test_is_valid_json(self, aws_dir: Path) -> None:
        """sqs-queue.json should be valid JSON."""
        content = (aws_dir / "sqs-queue.json").read_text()
        config = json.loads(content)
        assert isinstance(config, dict)
    
    def test_is_fifo_queue(self, aws_dir: Path) -> None:
        """Queue should be configured as FIFO."""
        content = (aws_dir / "sqs-queue.json").read_text()
        config = json.loads(content)
        assert config.get("FifoQueue") == "true"
    
    def test_has_content_based_deduplication(self, aws_dir: Path) -> None:
        """Queue should have content-based deduplication."""
        content = (aws_dir / "sqs-queue.json").read_text()
        config = json.loads(content)
        assert config.get("ContentBasedDeduplication") == "true"
    
    def test_has_visibility_timeout(self, aws_dir: Path) -> None:
        """Queue should have visibility timeout for long jobs."""
        content = (aws_dir / "sqs-queue.json").read_text()
        config = json.loads(content)
        # Should be at least 2 hours (7200 seconds) for long-running jobs
        timeout = int(config.get("VisibilityTimeout", "0"))
        assert timeout >= 7200


class TestStepFunctionConfig:
    """Test Step Functions state machine configuration."""
    
    def test_is_valid_json(self, aws_dir: Path) -> None:
        """step-function.json should be valid JSON."""
        content = (aws_dir / "step-function.json").read_text()
        config = json.loads(content)
        assert isinstance(config, dict)
    
    def test_has_start_at(self, aws_dir: Path) -> None:
        """State machine should have StartAt."""
        content = (aws_dir / "step-function.json").read_text()
        config = json.loads(content)
        assert "StartAt" in config
    
    def test_has_states(self, aws_dir: Path) -> None:
        """State machine should have States."""
        content = (aws_dir / "step-function.json").read_text()
        config = json.loads(content)
        assert "States" in config
        assert len(config["States"]) > 0
    
    def test_has_run_fargate_task_state(self, aws_dir: Path) -> None:
        """State machine should have RunFargateTask state."""
        content = (aws_dir / "step-function.json").read_text()
        config = json.loads(content)
        assert "RunFargateTask" in config["States"]
    
    def test_has_error_handling(self, aws_dir: Path) -> None:
        """State machine should have error handling."""
        content = (aws_dir / "step-function.json").read_text()
        config = json.loads(content)
        run_task = config["States"].get("RunFargateTask", {})
        assert "Catch" in run_task
    
    def test_has_timeout(self, aws_dir: Path) -> None:
        """State machine should have timeout for Fargate task."""
        content = (aws_dir / "step-function.json").read_text()
        config = json.loads(content)
        run_task = config["States"].get("RunFargateTask", {})
        # Should have timeout (up to 2 hours = 7200 seconds)
        assert "TimeoutSeconds" in run_task
        assert run_task["TimeoutSeconds"] <= 7200


class TestTaskDefinitionConfig:
    """Test ECS task definition configuration."""
    
    def test_is_valid_json(self, aws_dir: Path) -> None:
        """task-definition.json should be valid JSON."""
        content = (aws_dir / "task-definition.json").read_text()
        config = json.loads(content)
        assert isinstance(config, dict)
    
    def test_is_fargate_compatible(self, aws_dir: Path) -> None:
        """Task should be Fargate compatible."""
        content = (aws_dir / "task-definition.json").read_text()
        config = json.loads(content)
        assert "FARGATE" in config.get("requiresCompatibilities", [])
    
    def test_has_container_definition(self, aws_dir: Path) -> None:
        """Task should have container definition."""
        content = (aws_dir / "task-definition.json").read_text()
        config = json.loads(content)
        assert "containerDefinitions" in config
        assert len(config["containerDefinitions"]) > 0
    
    def test_container_has_secrets(self, aws_dir: Path) -> None:
        """Container should reference secrets for LLM keys."""
        content = (aws_dir / "task-definition.json").read_text()
        config = json.loads(content)
        container = config["containerDefinitions"][0]
        assert "secrets" in container
        
        # Should have at least one LLM key secret
        secret_names = [s["name"] for s in container["secrets"]]
        assert any("API_KEY" in name for name in secret_names)
    
    def test_has_log_configuration(self, aws_dir: Path) -> None:
        """Container should have log configuration."""
        content = (aws_dir / "task-definition.json").read_text()
        config = json.loads(content)
        container = config["containerDefinitions"][0]
        assert "logConfiguration" in container
    
    def test_has_stop_timeout(self, aws_dir: Path) -> None:
        """Container should have stop timeout for graceful shutdown."""
        content = (aws_dir / "task-definition.json").read_text()
        config = json.loads(content)
        container = config["containerDefinitions"][0]
        # Should have stop timeout for SIGTERM handling
        assert "stopTimeout" in container
        assert container["stopTimeout"] >= 30


class TestCommonShContent:
    """Test common.sh shared functions."""
    
    def test_has_shebang(self, lib_dir: Path) -> None:
        """Script should have bash shebang."""
        content = (lib_dir / "common.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")
    
    def test_has_color_functions(self, lib_dir: Path) -> None:
        """Script should have color output functions."""
        content = (lib_dir / "common.sh").read_text()
        assert "log_info" in content
        assert "log_error" in content
        assert "log_success" in content
    
    def test_has_prerequisite_checks(self, lib_dir: Path) -> None:
        """Script should have prerequisite check functions."""
        content = (lib_dir / "common.sh").read_text()
        assert "check_docker" in content
        assert "check_aws_cli" in content
        assert "check_azure_cli" in content
        assert "check_gcp_cli" in content
    
    def test_has_resource_naming(self, lib_dir: Path) -> None:
        """Script should have resource naming functions."""
        content = (lib_dir / "common.sh").read_text()
        assert "resource_name" in content
    
    def test_has_secret_validation(self, lib_dir: Path) -> None:
        """Script should have secret validation."""
        content = (lib_dir / "common.sh").read_text()
        assert "validate_secret_name" in content
