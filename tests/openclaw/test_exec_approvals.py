"""Unit tests for exec-approvals.json configuration.

Tests SR-1.6, SR-1.7 requirements.
"""

import json
from pathlib import Path

import pytest


EXEC_APPROVALS_PATH = Path(__file__).parent.parent.parent / "openclaw" / "exec-approvals.json"


@pytest.fixture
def exec_approvals() -> dict:
    """Load and parse exec-approvals.json."""
    with open(EXEC_APPROVALS_PATH) as f:
        return json.load(f)


class TestExecApprovalsStructure:
    """Test exec-approvals.json structure is valid."""

    def test_json_is_valid_and_parseable(self, exec_approvals: dict) -> None:
        """JSON validates and parses without error."""
        assert isinstance(exec_approvals, dict)
        assert "version" in exec_approvals

    def test_has_approvals_array(self, exec_approvals: dict) -> None:
        """approvals array exists."""
        assert "approvals" in exec_approvals
        assert isinstance(exec_approvals["approvals"], list)

    def test_has_allow_without_approval_array(self, exec_approvals: dict) -> None:
        """allow_without_approval array exists."""
        assert "allow_without_approval" in exec_approvals
        assert isinstance(exec_approvals["allow_without_approval"], list)


class TestApprovalRules:
    """Test approval rules for cost-incurring tools."""

    def test_research_company_requires_approval(self, exec_approvals: dict) -> None:
        """SR-1.6: research_company requires approval."""
        approvals = exec_approvals["approvals"]
        research_rule = next((a for a in approvals if a["pattern"] == "research_company"), None)
        
        assert research_rule is not None
        assert research_rule["approval"] == "required"
        assert "timeout_seconds" in research_rule
        assert research_rule["timeout_seconds"] == 600

    def test_generate_strategy_requires_approval(self, exec_approvals: dict) -> None:
        """SR-1.6: generate_strategy requires approval."""
        approvals = exec_approvals["approvals"]
        strategy_rule = next((a for a in approvals if a["pattern"] == "generate_strategy"), None)
        
        assert strategy_rule is not None
        assert strategy_rule["approval"] == "required"
        assert "timeout_seconds" in strategy_rule

    def test_clear_jobs_requires_approval(self, exec_approvals: dict) -> None:
        """SR-1.6: clear_jobs requires approval."""
        approvals = exec_approvals["approvals"]
        clear_rule = next((a for a in approvals if a["pattern"] == "clear_jobs"), None)
        
        assert clear_rule is not None
        assert clear_rule["approval"] == "required"

    def test_approval_rules_have_messages(self, exec_approvals: dict) -> None:
        """All approval rules have user-facing messages."""
        for rule in exec_approvals["approvals"]:
            assert "message" in rule, f"Rule {rule['pattern']} missing message"
            assert len(rule["message"]) > 0


class TestAllowWithoutApproval:
    """Test tools that don't require approval."""

    def test_estimate_run_no_approval(self, exec_approvals: dict) -> None:
        """SR-1.7: estimate_run does NOT require approval."""
        allowed = exec_approvals["allow_without_approval"]
        assert "estimate_run" in allowed

    def test_check_jobs_no_approval(self, exec_approvals: dict) -> None:
        """SR-1.7: check_jobs does NOT require approval."""
        allowed = exec_approvals["allow_without_approval"]
        assert "check_jobs" in allowed

    def test_doctor_no_approval(self, exec_approvals: dict) -> None:
        """SR-1.7: doctor does NOT require approval."""
        allowed = exec_approvals["allow_without_approval"]
        assert "doctor" in allowed

    def test_run_qa_no_approval(self, exec_approvals: dict) -> None:
        """SR-1.7: run_qa does NOT require approval."""
        allowed = exec_approvals["allow_without_approval"]
        assert "run_qa" in allowed

    def test_cancel_job_no_approval(self, exec_approvals: dict) -> None:
        """SR-1.7: cancel_job does NOT require approval."""
        allowed = exec_approvals["allow_without_approval"]
        assert "cancel_job" in allowed


class TestNoOverlap:
    """Test that approval and no-approval lists don't overlap."""

    def test_no_overlap_between_lists(self, exec_approvals: dict) -> None:
        """Tools should not appear in both lists."""
        approval_patterns = {a["pattern"] for a in exec_approvals["approvals"]}
        allowed = set(exec_approvals["allow_without_approval"])
        
        overlap = approval_patterns & allowed
        assert len(overlap) == 0, f"Tools in both lists: {overlap}"
