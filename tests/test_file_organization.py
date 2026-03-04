"""
Property tests for test file organization.

**Feature: project-reorganization, Property 5: Test file organization**
**Validates: Requirements 4.1**
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Test files that should NOT be in root
ROOT_TEST_FILES_TO_MOVE = [
    "test_googlesearch.py",
    "test_googlesimplesearch.py",
    "test_scrape_demo.py",
]


def test_no_test_files_in_root():
    """
    **Feature: project-reorganization, Property 5: Test file organization**
    **Validates: Requirements 4.1**

    For any test file (test_*.py) that existed in the project root,
    that file SHALL be moved to the tests/ directory structure.
    """
    root_files = list(PROJECT_ROOT.glob("test_*.py"))

    # Filter out any that might be intentionally in root
    unexpected_test_files = [
        f for f in root_files
        if f.name in ROOT_TEST_FILES_TO_MOVE
    ]

    assert len(unexpected_test_files) == 0, \
        f"Test files still in root: {[f.name for f in unexpected_test_files]}"


def test_tests_directory_exists():
    """Verify tests directory exists."""
    tests_dir = PROJECT_ROOT / "tests"
    assert tests_dir.exists(), "tests/ directory does not exist"
    assert tests_dir.is_dir(), "tests/ is not a directory"


def test_test_subdirectories_exist():
    """Verify test subdirectories exist."""
    expected_subdirs = [
        "test_core",
        "test_data",
        "test_ai",
        "test_output",
        "test_config",
        "test_utils",
    ]

    tests_dir = PROJECT_ROOT / "tests"

    for subdir in expected_subdirs:
        subdir_path = tests_dir / subdir
        assert subdir_path.exists(), f"Missing test subdirectory: {subdir}"


def test_moved_test_files_exist_in_tests():
    """Verify moved test files exist in tests/manual/ (renamed to demo_* to avoid pytest collection)."""
    manual_dir = PROJECT_ROOT / "tests" / "manual"

    # These were renamed from test_* to demo_* because they're manual test scripts,
    # not proper pytest tests (they have function parameters pytest interprets as fixtures)
    # Moved to tests/manual/ since they require manual execution with real API keys
    expected_files = [
        "demo_googlesearch.py",
        "demo_googlesimplesearch.py",
    ]

    for filename in expected_files:
        file_path = manual_dir / filename
        assert file_path.exists(), f"Missing moved test file: {filename}"
