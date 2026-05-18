"""Property tests for TypeScript adapter error handling.

Property 5: TypeScript Adapter Error Handling
Validates: FR-4.3, OR-1.1, OR-1.2
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ADAPTER_PATH = (
    Path(__file__).parent.parent.parent
    / "openclaw"
    / "skills"
    / "primr-research"
    / "scripts"
    / "research-status.ts"
)


def check_npx_available() -> bool:
    """Check if npx is actually available and working."""
    if not shutil.which("npx"):
        return False
    try:
        result = subprocess.run(
            ["npx", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# Check if npx is available
NPX_AVAILABLE = check_npx_available()

# Skip all tests if npx is not available
pytestmark = pytest.mark.skipif(
    not NPX_AVAILABLE, reason="npx not available - TypeScript adapter tests require Node.js/npx"
)


def run_adapter(input_json: str) -> tuple[str, str, int]:
    """Run the TypeScript adapter with given input.

    Returns (stdout, stderr, return_code).
    """
    # Use npx tsx to run TypeScript directly
    result = subprocess.run(
        ["npx", "tsx", str(ADAPTER_PATH), input_json],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout, result.stderr, result.returncode


# Strategy for generating valid ResearchStatus objects
valid_status_strategy = st.fixed_dictionaries(
    {
        "status": st.sampled_from(["idle", "in_progress", "completed", "failed", "cancelled"]),
    }
).map(lambda d: json.dumps(d))

# Strategy for generating invalid inputs
# Excludes null bytes (mangled by OS process arg handling) and valid JSON objects
invalid_input_strategy = st.one_of(
    st.just(""),
    st.just("not json"),
    st.just("{invalid}"),
    st.just("null"),
    st.just("[]"),
    st.just("42"),
    st.just('"a string"'),
    st.text(min_size=1, max_size=100, alphabet=st.characters(blacklist_characters="\x00")).filter(
        lambda s: not s.startswith("{")
    ),
)


class TestAdapterValidInput:
    """Test adapter with valid input."""

    @pytest.mark.parametrize("status", ["idle", "in_progress", "completed", "failed", "cancelled"])
    def test_valid_status_returns_success(self, status: str) -> None:
        """FR-4.3: Valid status input returns success JSON."""
        input_json = json.dumps({"status": status})
        stdout, stderr, code = run_adapter(input_json)

        assert code == 0, f"Expected success, got code {code}: {stderr}"

        output = json.loads(stdout)
        assert output["status"] == "success"
        assert "summary" in output
        assert "details" in output

    def test_idle_status_summary(self) -> None:
        """FR-4.1: Idle status produces correct summary."""
        input_json = json.dumps({"status": "idle"})
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        assert "ready" in output["summary"].lower() or "no active" in output["summary"].lower()

    def test_in_progress_with_details(self) -> None:
        """FR-4.1: In-progress status includes progress info."""
        input_json = json.dumps(
            {
                "status": "in_progress",
                "company_name": "Acme Corp",
                "progress": 45,
                "current_stage": "deep_research",
            }
        )
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        assert "Acme Corp" in output["summary"]
        assert "45%" in output["summary"]

    def test_completed_suggests_next_action(self) -> None:
        """FR-4.3: Completed status suggests retrieving results."""
        input_json = json.dumps(
            {
                "status": "completed",
                "company_name": "Acme Corp",
                "artifacts": ["report.md", "insights.txt"],
            }
        )
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        assert "action_required" in output
        assert (
            "output" in output["action_required"].lower()
            or "qa" in output["action_required"].lower()
        )


class TestAdapterPossiblyStuckDetection:
    """Test possibly_stuck detection logic."""

    def test_possibly_stuck_flag_detected(self) -> None:
        """FR-4.2: possibly_stuck field triggers action_required."""
        input_json = json.dumps({"status": "in_progress", "possibly_stuck": True})
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        assert "action_required" in output
        assert (
            "stuck" in output["action_required"].lower()
            or "cancel" in output["action_required"].lower()
        )

    def test_not_stuck_no_action(self) -> None:
        """FR-4.2: Normal in_progress doesn't suggest stuck action."""
        input_json = json.dumps({"status": "in_progress", "possibly_stuck": False, "progress": 50})
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        # Should not have stuck-related action
        if "action_required" in output:
            assert "stuck" not in output["action_required"].lower()


class TestAdapterErrorHandling:
    """Test adapter error handling."""

    def test_invalid_json_returns_error(self) -> None:
        """OR-1.2: Invalid JSON returns error with message."""
        stdout, stderr, code = run_adapter("not valid json")

        assert code != 0

        # Error should be in stderr
        error = json.loads(stderr)
        assert error["status"] == "error"
        assert "message" in error
        assert len(error["message"]) > 0

    def test_empty_input_returns_error(self) -> None:
        """OR-1.2: Empty input returns error."""
        stdout, stderr, code = run_adapter("")

        assert code != 0
        error = json.loads(stderr)
        assert error["status"] == "error"

    def test_error_output_is_valid_json(self) -> None:
        """OR-1.1: Error output is valid JSON."""
        _, stderr, code = run_adapter("{malformed")

        assert code != 0
        # Should not raise - stderr should be valid JSON
        error = json.loads(stderr)
        assert isinstance(error, dict)


class TestPropertyBasedErrorHandling:
    """Property-based tests for error handling."""

    @settings(max_examples=100)
    @given(invalid_input_strategy)
    def test_invalid_input_always_returns_error_json(self, invalid_input: str) -> None:
        """Property 5: All invalid inputs produce valid error JSON."""
        stdout, stderr, code = run_adapter(invalid_input)

        # Should fail
        assert code != 0

        # stderr should be valid JSON with required fields
        error = json.loads(stderr)
        assert error["status"] == "error"
        assert "message" in error
        assert len(error["message"]) > 0

    @settings(max_examples=100)
    @given(valid_status_strategy)
    def test_valid_input_always_returns_success_json(self, valid_input: str) -> None:
        """Property 5: All valid inputs produce valid success JSON."""
        stdout, stderr, code = run_adapter(valid_input)

        # Should succeed
        assert code == 0

        # stdout should be valid JSON with required fields
        output = json.loads(stdout)
        assert output["status"] == "success"
        assert "summary" in output
        assert "details" in output


class TestFailureActionSuggestions:
    """Test failure action suggestions."""

    def test_ssrf_error_suggests_deep_mode(self) -> None:
        """Failed with SSRF suggests deep mode."""
        input_json = json.dumps(
            {"status": "failed", "error_message": "URL blocked: SSRF protection triggered"}
        )
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        assert "action_required" in output
        assert "deep" in output["action_required"].lower()

    def test_api_error_suggests_retry(self) -> None:
        """Failed with API error suggests retry."""
        input_json = json.dumps({"status": "failed", "error_message": "API rate limit exceeded"})
        stdout, _, code = run_adapter(input_json)

        assert code == 0
        output = json.loads(stdout)
        assert "action_required" in output
        assert (
            "retry" in output["action_required"].lower()
            or "wait" in output["action_required"].lower()
        )
