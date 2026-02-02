"""Property tests for Lobster workflow structure validity.

Property 4: Lobster Workflow Structure Validity
Validates: FR-3.1, FR-3.2, FR-3.3
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from hypothesis import given, settings, strategies as st


WORKFLOWS_DIR = Path(__file__).parent.parent.parent / "openclaw" / "workflows"
WORKFLOW_FILES = list(WORKFLOWS_DIR.glob("*.yaml"))


def load_workflow(path: Path) -> dict:
    """Load and parse a workflow YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(params=WORKFLOW_FILES, ids=lambda p: p.stem)
def workflow_file(request) -> Path:
    """Parametrized fixture for all workflow files."""
    return request.param


@pytest.fixture
def workflow(workflow_file: Path) -> dict:
    """Load workflow from file."""
    return load_workflow(workflow_file)


class TestWorkflowYamlValidity:
    """Test workflow YAML is valid."""

    def test_yaml_parses_correctly(self, workflow: dict) -> None:
        """FR-3.1: YAML parses without errors."""
        assert isinstance(workflow, dict)

    def test_has_name_field(self, workflow: dict) -> None:
        """Workflow has name field."""
        assert "name" in workflow
        assert isinstance(workflow["name"], str)

    def test_has_version_field(self, workflow: dict) -> None:
        """Workflow has version field."""
        assert "version" in workflow

    def test_has_description_field(self, workflow: dict) -> None:
        """Workflow has description field."""
        assert "description" in workflow


class TestWorkflowStepsStructure:
    """Test workflow steps structure."""

    def test_has_steps_array(self, workflow: dict) -> None:
        """FR-3.1: steps array exists."""
        assert "steps" in workflow
        assert isinstance(workflow["steps"], list)
        assert len(workflow["steps"]) > 0

    def test_steps_have_unique_ids(self, workflow: dict) -> None:
        """FR-3.1: Each step has unique id."""
        steps = workflow["steps"]
        ids = [step["id"] for step in steps]
        
        assert len(ids) == len(set(ids)), f"Duplicate step IDs found: {ids}"

    def test_each_step_has_id(self, workflow: dict) -> None:
        """Each step has an id field."""
        for step in workflow["steps"]:
            assert "id" in step, f"Step missing id: {step}"
            assert isinstance(step["id"], str)

    def test_each_step_has_type_or_tool(self, workflow: dict) -> None:
        """Each step has type or tool field."""
        for step in workflow["steps"]:
            has_type = "type" in step
            has_tool = "tool" in step
            assert has_type or has_tool, f"Step {step.get('id')} missing type/tool"


class TestApprovalGate:
    """Test approval gate requirements."""

    def test_has_approval_step(self, workflow: dict) -> None:
        """FR-3.2: At least one step has approval: required."""
        steps = workflow["steps"]
        approval_steps = [s for s in steps if s.get("approval") == "required"]
        
        assert len(approval_steps) > 0, "No approval gate found in workflow"

    def test_approval_step_has_message(self, workflow: dict) -> None:
        """FR-3.2: Approval step has message."""
        steps = workflow["steps"]
        approval_steps = [s for s in steps if s.get("approval") == "required"]
        
        for step in approval_steps:
            assert "message" in step, f"Approval step {step['id']} missing message"

    def test_approval_step_has_timeout(self, workflow: dict) -> None:
        """FR-3.2: Approval step has timeout."""
        steps = workflow["steps"]
        approval_steps = [s for s in steps if s.get("approval") == "required"]
        
        for step in approval_steps:
            assert "timeout_minutes" in step, f"Approval step {step['id']} missing timeout"
            assert step["timeout_minutes"] == 10, "Approval timeout should be 10 minutes"

    def test_approval_step_has_token_length(self, workflow: dict) -> None:
        """SR-1.2: Approval step specifies token length."""
        steps = workflow["steps"]
        approval_steps = [s for s in steps if s.get("approval") == "required"]
        
        for step in approval_steps:
            assert "token_length" in step, f"Approval step {step['id']} missing token_length"
            assert step["token_length"] == 6, "Token length should be 6 characters"


class TestConditionFields:
    """Test condition fields on dependent steps."""

    def test_dependent_steps_have_conditions(self, workflow: dict) -> None:
        """FR-3.3: Dependent steps have condition fields."""
        steps = workflow["steps"]
        
        # Find steps that depend on approval
        for i, step in enumerate(steps):
            if i == 0:
                continue  # First step doesn't need condition
            
            # Steps after approval that use tools should have conditions
            if step.get("type") == "tool" or "tool" in step:
                # Check if this step references previous step outputs
                step_str = str(step)
                if "$approval" in step_str or "$research" in step_str or "$monitor" in step_str:
                    assert "condition" in step, f"Step {step['id']} references previous output but has no condition"


class TestErrorHandlers:
    """Test error handler configuration."""

    def test_has_on_failure_handler(self, workflow: dict) -> None:
        """FR-3.4: on_failure handler exists."""
        assert "on_failure" in workflow
        assert isinstance(workflow["on_failure"], list)
        assert len(workflow["on_failure"]) > 0

    def test_has_on_denial_handler(self, workflow: dict) -> None:
        """FR-3.4: on_denial handler exists."""
        assert "on_denial" in workflow
        assert isinstance(workflow["on_denial"], list)
        assert len(workflow["on_denial"]) > 0

    def test_failure_handler_has_content(self, workflow: dict) -> None:
        """on_failure handler has content."""
        for handler in workflow["on_failure"]:
            assert "content" in handler or "message" in handler

    def test_denial_handler_has_content(self, workflow: dict) -> None:
        """on_denial handler has content."""
        for handler in workflow["on_denial"]:
            assert "content" in handler or "message" in handler


class TestResearchPipelineSpecific:
    """Tests specific to research-pipeline.yaml."""

    @pytest.fixture
    def research_pipeline(self) -> dict:
        """Load research-pipeline.yaml."""
        path = WORKFLOWS_DIR / "research-pipeline.yaml"
        return load_workflow(path)

    def test_has_required_inputs(self, research_pipeline: dict) -> None:
        """FR-3.1: Has required inputs."""
        inputs = research_pipeline.get("inputs", {})
        
        assert "company_name" in inputs
        assert inputs["company_name"]["required"] is True
        
        assert "company_url" in inputs
        assert inputs["company_url"]["required"] is True

    def test_mode_input_has_enum(self, research_pipeline: dict) -> None:
        """Mode input has valid enum values."""
        inputs = research_pipeline.get("inputs", {})
        mode = inputs.get("mode", {})
        
        assert "enum" in mode
        assert set(mode["enum"]) == {"scrape", "deep", "full"}

    def test_has_estimate_step(self, research_pipeline: dict) -> None:
        """FR-3.1: Has estimate step."""
        steps = research_pipeline["steps"]
        estimate_step = next((s for s in steps if s["id"] == "estimate"), None)
        
        assert estimate_step is not None
        assert estimate_step.get("tool") == "estimate_run"

    def test_has_research_step(self, research_pipeline: dict) -> None:
        """FR-3.1: Has research step."""
        steps = research_pipeline["steps"]
        research_step = next((s for s in steps if s["id"] == "research"), None)
        
        assert research_step is not None
        assert research_step.get("tool") == "research_company"

    def test_has_monitor_step(self, research_pipeline: dict) -> None:
        """FR-3.1: Has monitor/poll step."""
        steps = research_pipeline["steps"]
        monitor_step = next((s for s in steps if s["id"] == "monitor"), None)
        
        assert monitor_step is not None
        assert monitor_step.get("type") == "poll"
        assert "primr://research/status" in monitor_step.get("resource", "")

    def test_step_order_is_correct(self, research_pipeline: dict) -> None:
        """Steps are in correct order: estimate → approval → research → monitor → retrieve."""
        steps = research_pipeline["steps"]
        step_ids = [s["id"] for s in steps]
        
        # Verify order
        assert step_ids.index("estimate") < step_ids.index("approval")
        assert step_ids.index("approval") < step_ids.index("research")
        assert step_ids.index("research") < step_ids.index("monitor")


class TestPropertyBasedWorkflowValidity:
    """Property-based tests for workflow validity."""

    @settings(max_examples=100)
    @given(st.sampled_from(WORKFLOW_FILES) if WORKFLOW_FILES else st.nothing())
    def test_all_workflows_have_valid_structure(self, workflow_path: Path) -> None:
        """Property 4: All workflows have valid structure."""
        workflow = load_workflow(workflow_path)
        
        # Required top-level fields
        assert "name" in workflow
        assert "steps" in workflow
        assert isinstance(workflow["steps"], list)
        assert len(workflow["steps"]) > 0
        
        # All steps have unique IDs
        ids = [s["id"] for s in workflow["steps"]]
        assert len(ids) == len(set(ids))
        
        # At least one approval step
        approval_steps = [s for s in workflow["steps"] if s.get("approval") == "required"]
        assert len(approval_steps) > 0
