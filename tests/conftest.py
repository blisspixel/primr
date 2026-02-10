"""
Shared pytest fixtures and configuration for Company Researcher tests.
"""

import asyncio
import sys
import warnings
from pathlib import Path
import pytest

# Add src to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def src_dir():
    """Return the src directory."""
    return PROJECT_ROOT / "src"


@pytest.fixture
def package_dir():
    """Return the company_researcher package directory."""
    return PROJECT_ROOT / "src" / "primr"


def pytest_configure(config):
    """Configure pytest to suppress external library warnings."""
    # Set a generous Hypothesis deadline globally so property tests don't flake
    # on slower machines or CI. Individual tests can still override with @settings.
    from hypothesis import settings as hypothesis_settings
    hypothesis_settings.register_profile("ci", deadline=None)
    hypothesis_settings.load_profile("ci")

    # Suppress unclosed event loop warnings from asyncio
    warnings.filterwarnings(
        "ignore",
        message="unclosed event loop",
        category=ResourceWarning
    )
    
    # Suppress legacy error deprecation warnings during test runs
    # These are intentionally used in tests to verify backward compatibility
    warnings.filterwarnings(
        "ignore",
        message=".*is deprecated and will be removed in v2.0.*",
        category=DeprecationWarning,
        module="primr.utils.errors"
    )
