"""
Property tests for import resolution verification.

**Feature: project-reorganization, Property 4: Import resolution**
**Validates: Requirements 3.1, 4.3**
"""

from pathlib import Path
import sys

from hypothesis import given, settings
from hypothesis import strategies as st

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# All modules that should be importable
IMPORTABLE_MODULES = [
    "primr",
    "primr.config.config",
    "primr.config.sections_config",
    "primr.utils.chat_logger",
    "primr.ai.llm",
    "primr.ai.grading_agent",
    "primr.ai.summarize",
    "primr.data.scrape",
    "primr.data.search_utils",
    "primr.data.insights_extractor",
    "primr.output.output_utils",
    "primr.core.research_agent",
]


@given(st.sampled_from(IMPORTABLE_MODULES))
@settings(max_examples=len(IMPORTABLE_MODULES), deadline=None)
def test_module_imports_without_error(module_name: str):
    """
    **Feature: project-reorganization, Property 4: Import resolution**
    **Validates: Requirements 3.1, 4.3**

    For any module in the reorganized package, importing that module SHALL NOT
    raise an ImportError, verifying all internal imports are correctly updated.
    """
    import importlib

    try:
        # Clear any cached imports
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Attempt to import the module
        module = importlib.import_module(module_name)
        assert module is not None, f"Module {module_name} imported as None"

    except ImportError as e:
        raise AssertionError(f"Failed to import {module_name}: {e}") from e


def test_main_package_exports():
    """Verify main package can be imported."""
    import primr

    assert hasattr(primr, "__version__")


def test_config_exports():
    """Verify config module exports expected values."""
    from primr.config.config import GEMINI_API_KEY, OUTPUT_DIR, PROJECT_ROOT, WORKING_DIR

    assert GEMINI_API_KEY is not None
    assert OUTPUT_DIR is not None
    assert WORKING_DIR is not None
    assert PROJECT_ROOT is not None


def test_sections_config_exports():
    """Verify sections_config exports SECTION_KEY_MAP."""
    from primr.config.sections_config import SECTION_KEY_MAP

    assert isinstance(SECTION_KEY_MAP, dict)
    assert len(SECTION_KEY_MAP) > 0
