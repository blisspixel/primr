"""
Property tests for package structure completeness.

**Feature: project-reorganization, Property 1: Package structure completeness**
**Validates: Requirements 1.1**
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "primr"

# Original modules that should now be in the package
ORIGINAL_MODULES = {
    "research_agent.py": "core/research_agent.py",
    "llm.py": "ai/llm.py",
    "grading_agent.py": "ai/grading_agent.py",
    "summarize.py": "ai/summarize.py",
    "scrape.py": "data/scrape.py",
    "search_utils.py": "data/search_utils.py",
    "insights_extractor.py": "data/insights_extractor.py",
    "output_utils.py": "output/output_utils.py",
    "config.py": "config/config.py",
    "sections_config.py": "config/sections_config.py",
    "chat_logger.py": "utils/chat_logger.py",
}


@given(st.sampled_from(list(ORIGINAL_MODULES.keys())))
@settings(max_examples=len(ORIGINAL_MODULES), deadline=None)
def test_module_exists_in_package(original_name: str):
    """
    **Feature: project-reorganization, Property 1: Package structure completeness**
    **Validates: Requirements 1.1**
    
    For any Python module that existed in the project root before reorganization,
    that module SHALL exist within the src/primr/ package hierarchy.
    """
    new_path = ORIGINAL_MODULES[original_name]
    full_path = SRC_DIR / new_path

    assert full_path.exists(), \
        f"Module {original_name} should be at {new_path} but was not found"


def test_all_modules_moved():
    """Verify all original modules exist in their new locations."""
    missing = []

    for original, new_path in ORIGINAL_MODULES.items():
        full_path = SRC_DIR / new_path
        if not full_path.exists():
            missing.append(f"{original} -> {new_path}")

    assert len(missing) == 0, f"Missing modules: {missing}"


def test_package_structure_complete():
    """Verify the complete package structure exists."""
    expected_structure = [
        "__init__.py",
        "core/__init__.py",
        "core/research_agent.py",
        "data/__init__.py",
        "data/scrape.py",
        "data/search_utils.py",
        "data/insights_extractor.py",
        "ai/__init__.py",
        "ai/llm.py",
        "ai/grading_agent.py",
        "ai/summarize.py",
        "output/__init__.py",
        "output/output_utils.py",
        "config/__init__.py",
        "config/config.py",
        "config/sections_config.py",
        "utils/__init__.py",
        "utils/chat_logger.py",
    ]

    missing = []
    for path in expected_structure:
        full_path = SRC_DIR / path
        if not full_path.exists():
            missing.append(path)

    assert len(missing) == 0, f"Missing files in package: {missing}"
