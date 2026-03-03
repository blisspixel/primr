"""
Property tests for configuration and runtime directory handling.

**Feature: project-reorganization, Property 7: Runtime directory handling**
**Validates: Requirements 7.2, 7.3**
"""

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Runtime directories that should exist in project root
RUNTIME_DIRS = ["logs", "output", "working"]


def test_project_root_detection():
    """Verify project root is correctly detected."""
    from primr.config.config import PROJECT_ROOT as CONFIG_ROOT

    # Project root should contain key files
    assert (Path(CONFIG_ROOT) / "pyproject.toml").exists() or \
           (Path(CONFIG_ROOT) / ".env").exists(), \
           f"Project root {CONFIG_ROOT} doesn't contain expected files"


def test_runtime_directories_resolve_to_project_root():
    """
    **Feature: project-reorganization, Property 7: Runtime directory handling**
    **Validates: Requirements 7.2, 7.3**
    
    Runtime directories should resolve to project root, not package location.
    """
    from primr.config.config import LOGS_DIR, OUTPUT_DIR, PROJECT_ROOT, WORKING_DIR

    project_root = Path(PROJECT_ROOT)

    # All runtime dirs should be under project root
    assert Path(OUTPUT_DIR).parent == project_root or \
           Path(OUTPUT_DIR) == project_root / "output", \
           f"OUTPUT_DIR {OUTPUT_DIR} not under project root"

    assert Path(WORKING_DIR).parent == project_root or \
           Path(WORKING_DIR) == project_root / "working", \
           f"WORKING_DIR {WORKING_DIR} not under project root"

    # LOGS_DIR is logs/chat_history
    assert project_root in Path(LOGS_DIR).parents, \
           f"LOGS_DIR {LOGS_DIR} not under project root"


@given(st.sampled_from(RUNTIME_DIRS))
@settings(max_examples=len(RUNTIME_DIRS))
def test_runtime_directories_exist(dir_name: str):
    """
    **Feature: project-reorganization, Property 7: Runtime directory handling**
    **Validates: Requirements 7.2, 7.3**
    
    For any runtime directory, the application SHALL create that directory 
    if it does not exist.
    """
    from primr.config.config import PROJECT_ROOT

    dir_path = Path(PROJECT_ROOT) / dir_name
    assert dir_path.exists(), f"Runtime directory {dir_name} does not exist"
    assert dir_path.is_dir(), f"{dir_name} is not a directory"
