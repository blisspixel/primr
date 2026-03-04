"""
Property tests for package structure verification.

**Feature: project-reorganization, Property 2: Package initialization**
**Validates: Requirements 1.2**
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "primr"

# Expected subpackages
EXPECTED_SUBPACKAGES = ["core", "data", "ai", "output", "config", "utils"]


def test_main_package_has_init():
    """Verify main package has __init__.py"""
    init_file = SRC_DIR / "__init__.py"
    assert init_file.exists(), f"Missing __init__.py in {SRC_DIR}"


@given(st.sampled_from(EXPECTED_SUBPACKAGES))
@settings(max_examples=len(EXPECTED_SUBPACKAGES))
def test_subpackages_have_init(subpackage: str):
    """
    **Feature: project-reorganization, Property 2: Package initialization**
    **Validates: Requirements 1.2**

    For any directory within src/primr/, that directory SHALL
    contain an __init__.py file making it importable as a Python package.
    """
    subpackage_dir = SRC_DIR / subpackage
    init_file = subpackage_dir / "__init__.py"

    assert subpackage_dir.exists(), f"Subpackage directory {subpackage} does not exist"
    assert init_file.exists(), f"Missing __init__.py in {subpackage_dir}"


def test_all_subpackages_exist():
    """Verify all expected subpackages exist."""
    for subpackage in EXPECTED_SUBPACKAGES:
        subpackage_dir = SRC_DIR / subpackage
        assert subpackage_dir.exists(), f"Missing subpackage: {subpackage}"
        assert subpackage_dir.is_dir(), f"{subpackage} is not a directory"
