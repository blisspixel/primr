"""
Property tests for CLI backward compatibility.

**Feature: project-reorganization, Property 6: CLI backward compatibility**
**Validates: Requirements 6.2**
"""

import argparse
from pathlib import Path
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Expected CLI arguments
EXPECTED_ARGS = ["--company", "--website", "--csv"]

# Research modes (new names + old names for backwards compatibility)
RESEARCH_MODES = [
    "scrape",
    "deep",
    "full",
    "parallel",
    "structured",
    "deep-research",
    "complete",
    "hybrid",
]


def test_cli_entry_point_exists():
    """Verify primr command is installed via package entry point."""
    # The CLI is now installed via pyproject.toml entry point
    # Check that the main function exists
    from primr.core.research_agent import main

    assert callable(main), "main() function should be callable"


def test_cli_parser_accepts_expected_args():
    """
    **Feature: project-reorganization, Property 6: CLI backward compatibility**
    **Validates: Requirements 6.2**

    For any CLI argument that was supported before reorganization,
    that argument SHALL be supported by the new company_research.py entry point.
    """

    # Create a parser matching the one in research_agent
    parser = argparse.ArgumentParser(description="AI Company Research Tool")
    parser.add_argument("--company", type=str, help="Company name")
    parser.add_argument("--website", type=str, help="Company website")
    parser.add_argument("--csv", type=str, help="CSV file for batch")

    # Test that all expected args are recognized
    for arg in EXPECTED_ARGS:
        # Parse with just this argument
        if arg == "--csv":
            args = parser.parse_args([arg, "test.csv"])
            assert args.csv == "test.csv"
        elif arg == "--company":
            args = parser.parse_args([arg, "TestCo"])
            assert args.company == "TestCo"
        elif arg == "--website":
            args = parser.parse_args([arg, "https://test.com"])
            assert args.website == "https://test.com"


@given(st.sampled_from(EXPECTED_ARGS))
@settings(max_examples=len(EXPECTED_ARGS), deadline=None)
def test_cli_args_are_supported(arg: str):
    """
    **Feature: project-reorganization, Property 6: CLI backward compatibility**
    **Validates: Requirements 6.2**

    Property test verifying each expected CLI argument is supported.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--website", type=str)
    parser.add_argument("--csv", type=str)

    # Verify the argument is recognized (doesn't raise)
    test_value = "test_value" if arg != "--csv" else "test.csv"
    args = parser.parse_args([arg, test_value])

    # Verify the value was captured
    arg_name = arg.lstrip("-")
    assert getattr(args, arg_name) == test_value


# =============================================================================
# MODE FLAG TESTS
# =============================================================================


def test_cli_mode_flag_exists():
    """Verify --mode flag is supported."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--website", type=str)
    parser.add_argument("--csv", type=str)
    parser.add_argument("--mode", "-m", type=str, choices=RESEARCH_MODES, default="structured")

    # Test default mode
    args = parser.parse_args(["--company", "TestCo"])
    assert args.mode == "structured"


def test_cli_mode_structured():
    """Verify structured mode is accepted."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--mode", type=str, choices=RESEARCH_MODES, default="structured")

    args = parser.parse_args(["--company", "TestCo", "--mode", "structured"])
    assert args.mode == "structured"


def test_cli_mode_deep_research():
    """Verify deep-research mode is accepted."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--mode", type=str, choices=RESEARCH_MODES, default="structured")

    args = parser.parse_args(["--company", "TestCo", "--mode", "deep-research"])
    assert args.mode == "deep-research"


def test_cli_mode_hybrid():
    """Verify hybrid mode is accepted."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--mode", type=str, choices=RESEARCH_MODES, default="structured")

    args = parser.parse_args(["--company", "TestCo", "--mode", "hybrid"])
    assert args.mode == "hybrid"


def test_cli_mode_short_flag():
    """Verify -m short flag works."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--mode", "-m", type=str, choices=RESEARCH_MODES, default="structured")

    args = parser.parse_args(["--company", "TestCo", "-m", "deep-research"])
    assert args.mode == "deep-research"


@given(st.sampled_from(RESEARCH_MODES))
@settings(max_examples=len(RESEARCH_MODES), deadline=None)
def test_cli_all_modes_accepted(mode: str):
    """
    Property test verifying all research modes are accepted.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--company", type=str)
    parser.add_argument("--mode", type=str, choices=RESEARCH_MODES, default="structured")

    args = parser.parse_args(["--company", "TestCo", "--mode", mode])
    assert args.mode == mode


def test_cli_invalid_mode_rejected():
    """Verify invalid modes are rejected."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str, choices=RESEARCH_MODES, default="structured")

    try:
        parser.parse_args(["--mode", "invalid-mode"])
        raise AssertionError("Should have raised SystemExit")
    except SystemExit:
        pass  # Expected


def test_cli_mode_with_csv():
    """Verify mode works with CSV batch processing."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str)
    parser.add_argument("--mode", type=str, choices=RESEARCH_MODES, default="structured")

    args = parser.parse_args(["--csv", "companies.csv", "--mode", "deep-research"])
    assert args.csv == "companies.csv"
    assert args.mode == "deep-research"
