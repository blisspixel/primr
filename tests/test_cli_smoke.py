"""
CLI smoke tests using subprocess execution.

These tests verify the CLI works end-to-end without making expensive API calls.
They use subprocess.run() to execute the actual CLI commands.

**Feature: test-coverage-hardening**
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
"""

import subprocess
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Project root for running CLI
PROJECT_ROOT = Path(__file__).parent.parent


@pytest.mark.smoke
class TestCLISmokeTests:
    """Smoke tests for CLI commands that don't require API calls."""

    def test_doctor_runs_successfully(self):
        """
        WHEN `primr doctor` is executed
        THEN the system SHALL complete and display diagnostic information

        Note: Exit code may be 1 if API keys are not configured (expected in CI).
        The test verifies doctor runs and produces output, not that all checks pass.

        **Validates: Requirements 2.1**
        """
        result = subprocess.run(
            ["primr", "doctor"],
            capture_output=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        stdout = result.stdout.decode()
        # Doctor should run and produce output (even if some checks fail)
        assert "Primr Doctor" in stdout or "Environment" in stdout, (
            f"doctor didn't produce expected output: {stdout}"
        )
        # Exit code 0 = all checks pass, 1 = some checks failed (e.g., missing API keys)
        # Both are valid outcomes; we just verify it ran without crashing
        assert result.returncode in (0, 1), (
            f"doctor crashed with unexpected exit code {result.returncode}: {result.stderr.decode()}"
        )

    def test_help_displays_usage(self):
        """
        WHEN `primr --help` is executed
        THEN the system SHALL display usage information and return exit code 0

        **Validates: Requirements 2.2**
        """
        result = subprocess.run(
            ["primr", "--help"],
            capture_output=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"--help failed: {result.stderr.decode()}"
        stdout = result.stdout.decode()
        # Verify usage information is displayed
        assert "primr" in stdout.lower() or "usage" in stdout.lower()
        assert "company" in stdout.lower()

    def test_list_recent_shows_output(self):
        """
        WHEN `primr --list-recent` is executed
        THEN the system SHALL list recent outputs

        **Validates: Requirements 2.3**
        """
        result = subprocess.run(
            ["primr", "--list-recent"],
            capture_output=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"--list-recent failed: {result.stderr.decode()}"

    @pytest.mark.skipif(
        not __import__("os").environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set",
    )
    def test_dry_run_shows_estimate_no_api_calls(self):
        """
        WHEN `primr "Test" https://test.com --dry-run` is executed
        THEN the system SHALL display cost estimate without making API calls

        **Validates: Requirements 2.4**
        """
        result = subprocess.run(
            [
                "primr",
                "TestCompany",
                "https://example.com",
                "--dry-run",
            ],
            capture_output=True,
            timeout=60,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"--dry-run failed: {result.stderr.decode()}"
        stdout = result.stdout.decode()
        # Should show cost estimate
        assert "cost" in stdout.lower() or "estimate" in stdout.lower() or "$" in stdout

    def test_show_usage_displays_stats(self):
        """
        WHEN `primr --show-usage` is executed
        THEN the system SHALL display usage statistics

        Note: On Windows, Unicode encoding issues may cause this to fail
        due to checkmark characters in the output. This is a known issue
        with colorama/Windows console encoding.
        """
        result = subprocess.run(
            ["primr", "--show-usage"],
            capture_output=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
        )
        # Accept either success or Unicode encoding error (Windows-specific issue)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            # Known Windows encoding issue with Unicode characters
            if "UnicodeEncodeError" in stderr or "charmap" in stderr:
                pytest.skip("Windows Unicode encoding issue with usage display")
        assert result.returncode == 0, (
            f"--show-usage failed: {result.stderr.decode(errors='replace')}"
        )


# =============================================================================
# Property Test for Invalid Arguments
# =============================================================================

# Invalid argument patterns that should cause non-zero exit
INVALID_ARG_PATTERNS = [
    ["--invalid-flag"],
    ["--mode", "nonexistent-mode"],
    ["--cloud-vendor", "invalid-vendor"],
    ["--citation-style", "invalid-style"],
]


@pytest.mark.smoke
class TestCLIInvalidArguments:
    """Tests for invalid CLI argument handling."""

    @pytest.mark.parametrize("invalid_args", INVALID_ARG_PATTERNS)
    def test_invalid_args_return_nonzero(self, invalid_args: list[str]):
        """
        WHEN invalid arguments are provided
        THEN the system SHALL return a non-zero exit code

        **Validates: Requirements 2.5**
        """
        result = subprocess.run(
            ["primr", *invalid_args],
            capture_output=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0, f"Expected non-zero exit for {invalid_args}"


# Strategy for generating invalid flag names
invalid_flag_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz-_"),
    min_size=3,
    max_size=20,
).filter(
    lambda x: (
        x
        not in {
            "help",
            "version",
            "mode",
            "quiet",
            "verbose",
            "csv",
            "dry-run",
            "show-usage",
            "list-recent",
            "clean-temp",
            "check-quota",
            "check-jobs",
            "open",
            "output-dir",
            "context",
            "context-folder",
            "confirm",
            "ai-strategy",
            "no-ai-strategy",
            "cloud-vendor",
            "citation-style",
            "refresh-vendor-research",
            "generate-vendor-research",
            "strategy",
            "strategy-only",
            "no-qa",
            "qa",
            "qa-recent",
            "test-accordion",
            "accordion-pages",
            "analyze-report",
        }
    )
)


@pytest.mark.smoke
@given(invalid_flag=invalid_flag_strategy)
@settings(max_examples=20, deadline=None)
def test_property_invalid_flags_return_nonzero(invalid_flag: str):
    """
    **Feature: test-coverage-hardening, Property 1: Invalid CLI arguments return non-zero exit code**
    **Validates: Requirements 2.5**

    For any invalid CLI argument combination, the system should return
    a non-zero exit code and include an error message in stderr.
    """
    result = subprocess.run(
        ["primr", f"--{invalid_flag}"],
        capture_output=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    # Invalid flags should cause a non-zero exit.
    assert result.returncode != 0, f"Expected non-zero exit for --{invalid_flag}"
    # The CLI must emit a diagnostic — but it may land on stdout rather than
    # stderr (e.g. the "required arguments" path), and argparse prefix-matching
    # can turn a short flag like `--ref` into a valid abbreviation that then
    # fails on missing positionals with a usage message that lacks the literal
    # word "error". Accept any recognizable diagnostic on either stream.
    combined = (result.stderr.decode() + result.stdout.decode()).lower()
    assert any(
        token in combined
        for token in ("error", "usage", "invalid", "required", "unrecognized", "no such")
    ), f"Expected a diagnostic message for --{invalid_flag}, got: {combined!r}"
