"""
Integration test harness for Open Claw integration.

This harness simulates the Open Claw runtime for CI testing without
requiring the actual Open Claw installation.

Requirements: SR-1.1, AP-1
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
import secrets

import yaml

# Paths to configuration files
OPENCLAW_DIR = Path(__file__).parent.parent.parent / "openclaw"
OPENCLAW_JSON = OPENCLAW_DIR / "openclaw.json"
EXEC_APPROVALS_JSON = OPENCLAW_DIR / "exec-approvals.json"
WORKFLOW_DIR = OPENCLAW_DIR / "workflows"
SKILLS_DIR = OPENCLAW_DIR / "skills"


def load_json(path: Path) -> dict:
    """Load and parse a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    """Load and parse a YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class MockMCPServer:
    """Mock MCP server for testing tool responses."""

    def __init__(self):
        self.jobs = {}
        self.active_job_id = None

    def estimate_run(self, company_name: str, company_url: str, mode: str = "full") -> dict:
        """Mock estimate_run tool."""
        cost_map = {"scrape": 0.14, "deep": 2.50, "full": 3.60}
        time_map = {"scrape": 10, "deep": 15, "full": 30}

        return {
            "cost_usd": cost_map.get(mode, 0.75),
            "time_minutes": time_map.get(mode, 30),
            "mode": mode,
            "company_name": company_name,
            "company_url": company_url,
        }

    def research_company(self, company_name: str, company_url: str, mode: str = "full") -> dict:
        """Mock research_company tool."""
        if self.active_job_id:
            return {"error": "job_in_progress", "message": "A job is already running"}

        job_id = secrets.token_hex(8)
        self.active_job_id = job_id
        self.jobs[job_id] = {
            "job_id": job_id,
            "company_name": company_name,
            "company_url": company_url,
            "mode": mode,
            "status": "in_progress",
            "start_time": datetime.now().isoformat(),
        }

        return {"job_id": job_id, "status": "started"}

    def check_jobs(self) -> dict:
        """Mock check_jobs tool."""
        return {"jobs": list(self.jobs.values())}

    def cancel_job(self, job_id: str | None = None) -> dict:
        """Mock cancel_job tool."""
        if job_id and job_id in self.jobs:
            self.jobs[job_id]["status"] = "cancelled"
            if self.active_job_id == job_id:
                self.active_job_id = None
            return {"status": "cancelled", "job_id": job_id}
        return {"error": "job_not_found"}

    def complete_job(self, job_id: str) -> None:
        """Simulate job completion (for testing)."""
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = "completed"
            self.jobs[job_id]["completion_time"] = datetime.now().isoformat()
            self.jobs[job_id]["output_paths"] = [
                f"output/{self.jobs[job_id]['company_name'].lower().replace(' ', '_')}/report.md"
            ]
            if self.active_job_id == job_id:
                self.active_job_id = None


class ApprovalTokenValidator:
    """Validates approval tokens per SR-1.2, SR-1.3, SR-1.4."""

    def __init__(self, token_length: int = 6, validity_minutes: int = 10):
        self.token_length = token_length
        self.validity_minutes = validity_minutes
        self.tokens = {}  # token -> {created_at, bound_to, used}

    def generate_token(self, bound_to: dict) -> str:
        """Generate a new approval token bound to an estimate."""
        token = secrets.token_hex(self.token_length // 2).upper()[: self.token_length]
        self.tokens[token] = {
            "created_at": datetime.now(),
            "bound_to": bound_to,
            "used": False,
        }
        return token

    def validate_token(self, token: str, estimate: dict) -> tuple[bool, str]:
        """Validate a token against an estimate.

        Returns (is_valid, error_message).
        """
        if token not in self.tokens:
            return False, "Invalid approval token"

        token_data = self.tokens[token]

        # Check if already used (SR-1.8)
        if token_data["used"]:
            return False, "Token already used"

        # Check expiry
        expires_at = token_data["created_at"] + timedelta(minutes=self.validity_minutes)
        if datetime.now() > expires_at:
            return False, "Approval token expired, please re-estimate"

        # Check binding (SR-1.3, SR-1.4)
        bound = token_data["bound_to"]
        if bound.get("cost_usd") != estimate.get("cost_usd"):
            return False, "Token does not match current estimate (cost mismatch)"
        if bound.get("mode") != estimate.get("mode"):
            return False, "Token does not match current estimate (mode mismatch)"
        if bound.get("company_url") != estimate.get("company_url"):
            return False, "Token does not match current estimate (URL mismatch)"

        return True, ""

    def use_token(self, token: str) -> None:
        """Mark a token as used."""
        if token in self.tokens:
            self.tokens[token]["used"] = True


class TestSchemaValidation:
    """Tests for configuration schema validation."""

    def test_openclaw_json_schema(self):
        """Validate openclaw.json structure."""
        config = load_json(OPENCLAW_JSON)

        # Required top-level keys
        assert "plugins" in config
        assert "skills" in config
        assert "workflows" in config

        # Xiaowan plugin structure (nested under entries)
        assert "entries" in config["plugins"]
        assert "xiaowan" in config["plugins"]["entries"]
        xiaowan = config["plugins"]["entries"]["xiaowan"]
        assert "config" in xiaowan
        assert "servers" in xiaowan["config"]

        # Find primr server
        servers = xiaowan["config"]["servers"]
        primr_server = next((s for s in servers if s["name"] == "primr"), None)
        assert primr_server is not None
        assert primr_server["command"] == "primr-mcp"

    def test_exec_approvals_json_schema(self):
        """Validate exec-approvals.json structure."""
        approvals = load_json(EXEC_APPROVALS_JSON)

        assert "approvals" in approvals
        assert "allow_without_approval" in approvals
        assert isinstance(approvals["approvals"], list)
        assert isinstance(approvals["allow_without_approval"], list)

    def test_workflow_yaml_schema(self):
        """Validate workflow YAML structure."""
        workflow_path = WORKFLOW_DIR / "research-pipeline.yaml"
        workflow = load_yaml(workflow_path)

        assert "name" in workflow
        assert "steps" in workflow
        assert isinstance(workflow["steps"], list)

        # Verify approval step exists
        approval_steps = [s for s in workflow["steps"] if s.get("approval") == "required"]
        assert len(approval_steps) > 0


class TestApprovalTokenValidation:
    """Tests for approval token validation logic."""

    def test_valid_token_accepted(self):
        """Valid token with matching estimate is accepted."""
        validator = ApprovalTokenValidator()

        estimate = {"cost_usd": 0.75, "mode": "full", "company_url": "https://acme.com"}
        token = validator.generate_token(estimate)

        is_valid, error = validator.validate_token(token, estimate)
        assert is_valid
        assert error == ""

    def test_invalid_token_rejected(self):
        """Invalid token is rejected."""
        validator = ApprovalTokenValidator()

        estimate = {"cost_usd": 0.75, "mode": "full", "company_url": "https://acme.com"}

        is_valid, error = validator.validate_token("INVALID", estimate)
        assert not is_valid
        assert "Invalid" in error

    def test_expired_token_rejected(self):
        """Expired token is rejected."""
        validator = ApprovalTokenValidator(validity_minutes=10)

        estimate = {"cost_usd": 0.75, "mode": "full", "company_url": "https://acme.com"}
        token = validator.generate_token(estimate)

        # Manually expire the token by backdating creation time
        validator.tokens[token]["created_at"] = datetime.now() - timedelta(minutes=15)

        # Token should be expired now
        is_valid, error = validator.validate_token(token, estimate)
        assert not is_valid
        assert "expired" in error.lower()

    def test_mismatched_estimate_rejected(self):
        """Token bound to different estimate is rejected."""
        validator = ApprovalTokenValidator()

        original_estimate = {"cost_usd": 0.75, "mode": "full", "company_url": "https://acme.com"}
        token = validator.generate_token(original_estimate)

        # Try with different estimate
        different_estimate = {"cost_usd": 0.50, "mode": "deep", "company_url": "https://acme.com"}

        is_valid, error = validator.validate_token(token, different_estimate)
        assert not is_valid
        assert "mismatch" in error.lower()

    def test_used_token_rejected(self):
        """SR-1.8: Used token is rejected on second use."""
        validator = ApprovalTokenValidator()

        estimate = {"cost_usd": 0.75, "mode": "full", "company_url": "https://acme.com"}
        token = validator.generate_token(estimate)

        # First use
        is_valid, _ = validator.validate_token(token, estimate)
        assert is_valid
        validator.use_token(token)

        # Second use
        is_valid, error = validator.validate_token(token, estimate)
        assert not is_valid
        assert "already used" in error.lower()


class TestMockMCPServer:
    """Tests for mock MCP server responses."""

    def test_estimate_run_returns_cost(self):
        """estimate_run returns cost estimate."""
        server = MockMCPServer()
        result = server.estimate_run("Acme Corp", "https://acme.com", "full")

        assert "cost_usd" in result
        assert "time_minutes" in result
        assert result["cost_usd"] > 0

    def test_research_company_returns_job_id(self):
        """research_company returns job_id."""
        server = MockMCPServer()
        result = server.research_company("Acme Corp", "https://acme.com")

        assert "job_id" in result
        assert result["status"] == "started"

    def test_concurrent_research_rejected(self):
        """SR-2.1: Concurrent research is rejected."""
        server = MockMCPServer()

        # Start first job
        result1 = server.research_company("Acme Corp", "https://acme.com")
        assert "job_id" in result1

        # Try to start second job
        result2 = server.research_company("Other Corp", "https://other.com")
        assert "error" in result2
        assert result2["error"] == "job_in_progress"

    def test_job_completion(self):
        """Job completion updates status."""
        server = MockMCPServer()

        result = server.research_company("Acme Corp", "https://acme.com")
        job_id = result["job_id"]

        # Complete the job
        server.complete_job(job_id)

        # Check status
        jobs = server.check_jobs()
        job = next(j for j in jobs["jobs"] if j["job_id"] == job_id)
        assert job["status"] == "completed"
        assert "output_paths" in job


class TestHighRiskSeams:
    """
    High-risk seam tests for approval + governance interaction.

    Requirements: SR-1.1, AP-1
    """

    def test_approval_required_via_workflow(self):
        """SR-1.1: Approval is required via workflow."""
        workflow_path = WORKFLOW_DIR / "research-pipeline.yaml"
        workflow = load_yaml(workflow_path)

        # Find approval step
        approval_steps = [s for s in workflow["steps"] if s.get("approval") == "required"]
        assert len(approval_steps) > 0, "Workflow must have approval step"

        # Verify approval comes before research
        step_ids = [s["id"] for s in workflow["steps"]]
        approval_idx = step_ids.index("approval")
        research_idx = step_ids.index("research")
        assert approval_idx < research_idx, "Approval must come before research"

    def test_approval_required_via_exec_approvals(self):
        """SR-1.1: Approval is required via exec-approvals.json."""
        approvals = load_json(EXEC_APPROVALS_JSON)

        # research_company should require approval
        approval_patterns = [a["pattern"] for a in approvals["approvals"]]
        assert "research_company" in approval_patterns, "research_company must require approval"

        # estimate_run should NOT require approval
        allow_list = approvals["allow_without_approval"]
        assert "estimate_run" in allow_list, "estimate_run should not require approval"

    def test_workflow_and_exec_approvals_consistent(self):
        """Workflow approval and exec-approvals.json are consistent."""
        workflow_path = WORKFLOW_DIR / "research-pipeline.yaml"
        workflow = load_yaml(workflow_path)
        approvals = load_json(EXEC_APPROVALS_JSON)

        # Get tools that require approval in exec-approvals.json
        approval_patterns = {a["pattern"] for a in approvals["approvals"]}

        # Get tools used in workflow after approval step
        step_ids = [s["id"] for s in workflow["steps"]]
        approval_idx = step_ids.index("approval")

        post_approval_tools = set()
        for step in workflow["steps"][approval_idx + 1 :]:
            if "tool" in step:
                post_approval_tools.add(step["tool"])

        # research_company is used after approval and requires approval
        if "research_company" in post_approval_tools:
            assert "research_company" in approval_patterns, (
                "research_company used after approval but not in exec-approvals"
            )

    def test_latest_output_includes_job_id_for_matching(self):
        """AP-1: Latest output includes job_id for provenance verification."""
        # This is tested via the mock server
        server = MockMCPServer()

        # Start and complete a job
        result = server.research_company("Acme Corp", "https://acme.com")
        job_id = result["job_id"]
        server.complete_job(job_id)

        # Verify job has output paths
        jobs = server.check_jobs()
        job = next(j for j in jobs["jobs"] if j["job_id"] == job_id)

        assert "output_paths" in job
        assert len(job["output_paths"]) > 0


class TestWorkflowSimulation:
    """Simulate workflow execution for integration testing."""

    def test_full_workflow_simulation(self):
        """Simulate complete research workflow."""
        server = MockMCPServer()
        validator = ApprovalTokenValidator()

        # Step 1: Estimate
        estimate = server.estimate_run("Acme Corp", "https://acme.com", "full")
        assert estimate["cost_usd"] == 3.60

        # Step 2: Generate approval token
        token = validator.generate_token(estimate)
        assert len(token) == 6

        # Step 3: Validate and use token
        is_valid, _ = validator.validate_token(token, estimate)
        assert is_valid
        validator.use_token(token)

        # Step 4: Start research
        result = server.research_company(
            estimate["company_name"], estimate["company_url"], estimate["mode"]
        )
        assert "job_id" in result
        job_id = result["job_id"]

        # Step 5: Complete job (simulated)
        server.complete_job(job_id)

        # Step 6: Verify completion
        jobs = server.check_jobs()
        job = next(j for j in jobs["jobs"] if j["job_id"] == job_id)
        assert job["status"] == "completed"

    def test_workflow_denial_simulation(self):
        """Simulate workflow denial (no cost incurred)."""
        server = MockMCPServer()
        validator = ApprovalTokenValidator()

        # Step 1: Estimate
        estimate = server.estimate_run("Acme Corp", "https://acme.com", "full")

        # Step 2: Generate token but don't use it (denial)
        validator.generate_token(estimate)

        # Step 3: Verify no job was started
        jobs = server.check_jobs()
        assert len(jobs["jobs"]) == 0

    def test_workflow_mode_change_requires_reestimate(self):
        """Mode change after estimate requires new approval."""
        server = MockMCPServer()
        validator = ApprovalTokenValidator()

        # Step 1: Estimate for full mode
        estimate_full = server.estimate_run("Acme Corp", "https://acme.com", "full")
        token = validator.generate_token(estimate_full)

        # Step 2: Try to use token with different mode
        estimate_deep = server.estimate_run("Acme Corp", "https://acme.com", "deep")

        is_valid, error = validator.validate_token(token, estimate_deep)
        assert not is_valid
        assert "mismatch" in error.lower()
