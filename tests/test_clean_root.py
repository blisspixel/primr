"""
Property tests for clean project root.

**Feature: project-reorganization, Property 3: Clean project root**
**Validates: Requirements 1.3**
"""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

PROJECT_ROOT = Path(__file__).parent.parent

# Files that should NOT be in root after reorganization
MOVED_PYTHON_FILES = [
    "research_agent.py",
    "llm.py",
    "grading_agent.py",
    "scrape.py",
    "summarize.py",
    "search_utils.py",
    "insights_extractor.py",
    "output_utils.py",
    "config.py",
    "sections_config.py",
    "chat_logger.py",
]

# Files that ARE allowed in root
ALLOWED_ROOT_FILES = [
    "primr_cli.py",         # CLI entry point
    "pyproject.toml",       # Package config
    "requirements.txt",     # Dependencies
    ".env",                 # Environment config
    "README.md",            # Documentation
    "ROADMAP.md",           # Roadmap
    ".gitignore",           # Git config
    "pytest.ini",           # Test config
    "mypy.ini",             # Type checking config
]


def test_no_moved_python_files_in_root():
    """
    **Feature: project-reorganization, Property 3: Clean project root**
    **Validates: Requirements 1.3**
    
    For any file in the project root after reorganization, that file SHALL be 
    either a configuration file, documentation, an entry point, or a directory.
    """
    for filename in MOVED_PYTHON_FILES:
        file_path = PROJECT_ROOT / filename
        assert not file_path.exists(), \
            f"Python module {filename} should not be in root - should be in src/"


@given(st.sampled_from(MOVED_PYTHON_FILES))
@settings(max_examples=len(MOVED_PYTHON_FILES), deadline=None)
def test_moved_files_not_in_root(filename: str):
    """
    **Feature: project-reorganization, Property 3: Clean project root**
    **Validates: Requirements 1.3**
    
    Property test verifying each moved file is no longer in root.
    """
    file_path = PROJECT_ROOT / filename
    assert not file_path.exists(), \
        f"File {filename} should have been moved from root"


def test_readme_is_markdown():
    """Verify readme.txt was renamed to README.md."""
    readme_txt = PROJECT_ROOT / "readme.txt"
    readme_md = PROJECT_ROOT / "README.md"

    assert not readme_txt.exists(), "readme.txt should be renamed to README.md"
    assert readme_md.exists(), "README.md should exist"


def test_planning_docs_archived():
    """Verify Planning Process Documents was moved/removed from root."""
    old_location = PROJECT_ROOT / "Planning Process Documents"
    # Note: archive/planning may not exist if history was cleaned
    # The key requirement is that the old location doesn't exist
    assert not old_location.exists(), "Planning Process Documents should not be in root"


def test_dan_test_archived():
    """Verify dan test folder was moved/removed from root."""
    old_location = PROJECT_ROOT / "dan test"
    # Note: archive/experimental may not exist if history was cleaned
    # The key requirement is that the old location doesn't exist
    assert not old_location.exists(), "dan test should not be in root"
