"""Unit tests for openclaw.json configuration validity.

Tests FR-1.1, FR-1.2, FR-1.3 requirements.
"""

import json
import re
from pathlib import Path

import pytest


OPENCLAW_CONFIG_PATH = Path(__file__).parent.parent.parent / "openclaw" / "openclaw.json"


@pytest.fixture
def openclaw_config() -> dict:
    """Load and parse openclaw.json."""
    with open(OPENCLAW_CONFIG_PATH) as f:
        return json.load(f)


class TestOpenclawJsonValidity:
    """Test openclaw.json is valid and parseable."""

    def test_json_is_valid_and_parseable(self, openclaw_config: dict) -> None:
        """FR-1.1: JSON validates and parses without error."""
        assert isinstance(openclaw_config, dict)
        assert "version" in openclaw_config

    def test_has_plugins_section(self, openclaw_config: dict) -> None:
        """FR-1.1: plugins section exists."""
        assert "plugins" in openclaw_config
        assert "entries" in openclaw_config["plugins"]

    def test_xiaowan_plugin_configured(self, openclaw_config: dict) -> None:
        """FR-1.1: Xiaowan plugin is configured."""
        plugins = openclaw_config["plugins"]["entries"]
        assert "xiaowan" in plugins
        assert plugins["xiaowan"]["enabled"] is True

    def test_primr_server_structure(self, openclaw_config: dict) -> None:
        """FR-1.1: primr server has correct structure."""
        xiaowan = openclaw_config["plugins"]["entries"]["xiaowan"]
        servers = xiaowan["config"]["servers"]
        
        primr_server = next((s for s in servers if s["name"] == "primr"), None)
        assert primr_server is not None
        assert primr_server["transport"] == "stdio"
        assert primr_server["command"] == "primr-mcp"
        assert primr_server["args"] == ["--stdio"]


class TestEnvironmentVariablePassthrough:
    """Test environment variable configuration."""

    def test_env_uses_dollar_var_syntax(self, openclaw_config: dict) -> None:
        """FR-1.2: Environment variables use ${VAR} syntax."""
        xiaowan = openclaw_config["plugins"]["entries"]["xiaowan"]
        servers = xiaowan["config"]["servers"]
        primr_server = next((s for s in servers if s["name"] == "primr"), None)
        
        env = primr_server["env"]
        
        # Check each required env var uses ${VAR} syntax
        assert env["GEMINI_API_KEY"] == "${GEMINI_API_KEY}"
        assert env["SEARCH_API_KEY"] == "${SEARCH_API_KEY}"
        assert env["SEARCH_ENGINE_ID"] == "${SEARCH_ENGINE_ID}"

    def test_all_required_env_vars_present(self, openclaw_config: dict) -> None:
        """FR-1.2: All required environment variables are configured."""
        xiaowan = openclaw_config["plugins"]["entries"]["xiaowan"]
        servers = xiaowan["config"]["servers"]
        primr_server = next((s for s in servers if s["name"] == "primr"), None)
        
        env = primr_server["env"]
        required_vars = ["GEMINI_API_KEY", "SEARCH_API_KEY", "SEARCH_ENGINE_ID"]
        
        for var in required_vars:
            assert var in env, f"Missing required env var: {var}"


class TestSkillsEntries:
    """Test skills.entries configuration."""

    def test_skills_entries_exists(self, openclaw_config: dict) -> None:
        """FR-1.3: skills.entries section exists."""
        assert "skills" in openclaw_config
        assert "entries" in openclaw_config["skills"]

    def test_primr_research_skill_configured(self, openclaw_config: dict) -> None:
        """FR-1.3: primr-research skill is configured."""
        skills = openclaw_config["skills"]["entries"]
        assert "primr-research" in skills
        assert skills["primr-research"]["enabled"] is True
        assert "path" in skills["primr-research"]

    def test_primr_strategy_skill_configured(self, openclaw_config: dict) -> None:
        """FR-1.3: primr-strategy skill is configured."""
        skills = openclaw_config["skills"]["entries"]
        assert "primr-strategy" in skills
        assert skills["primr-strategy"]["enabled"] is True

    def test_primr_qa_skill_configured(self, openclaw_config: dict) -> None:
        """FR-1.3: primr-qa skill is configured."""
        skills = openclaw_config["skills"]["entries"]
        assert "primr-qa" in skills
        assert skills["primr-qa"]["enabled"] is True

    def test_per_skill_env_overrides(self, openclaw_config: dict) -> None:
        """FR-1.3: Per-skill environment overrides are supported."""
        skills = openclaw_config["skills"]["entries"]
        research_skill = skills["primr-research"]
        
        # primr-research has env overrides
        assert "env" in research_skill
        assert "PRIMR_OUTPUT_DIR" in research_skill["env"]


class TestWorkflowsConfiguration:
    """Test workflows configuration."""

    def test_workflows_entries_exists(self, openclaw_config: dict) -> None:
        """Workflows section exists."""
        assert "workflows" in openclaw_config
        assert "entries" in openclaw_config["workflows"]

    def test_research_pipeline_workflow_configured(self, openclaw_config: dict) -> None:
        """Research pipeline workflow is registered."""
        workflows = openclaw_config["workflows"]["entries"]
        assert "research-pipeline" in workflows
        assert workflows["research-pipeline"]["enabled"] is True
        assert "path" in workflows["research-pipeline"]


class TestSandboxConfiguration:
    """Test Docker sandbox configuration."""

    def test_sandbox_mode_is_docker(self, openclaw_config: dict) -> None:
        """Sandbox mode is docker."""
        assert "sandbox" in openclaw_config
        assert openclaw_config["sandbox"]["mode"] == "docker"

    def test_docker_config_present(self, openclaw_config: dict) -> None:
        """Docker configuration is present."""
        docker = openclaw_config["sandbox"]["docker"]
        assert "dockerfile" in docker
        assert "image" in docker
        assert "network" in docker
        assert "volumes" in docker

    def test_output_volume_is_rw(self, openclaw_config: dict) -> None:
        """Output volume is mounted read-write."""
        volumes = openclaw_config["sandbox"]["docker"]["volumes"]
        output_vol = next((v for v in volumes if "output" in v["container"]), None)
        assert output_vol is not None
        assert output_vol["mode"] == "rw"

    def test_docs_volume_is_ro(self, openclaw_config: dict) -> None:
        """Docs volume is mounted read-only."""
        volumes = openclaw_config["sandbox"]["docker"]["volumes"]
        docs_vol = next((v for v in volumes if "docs" in v["container"]), None)
        assert docs_vol is not None
        assert docs_vol["mode"] == "ro"
