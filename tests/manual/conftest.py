"""
Configuration for manual/debug tests.

These tests are excluded from normal test runs because they:
- Require manual setup or real data files
- Make live network requests
- Are for debugging purposes only

To run manual tests explicitly:
    pytest tests/manual/ -v
"""

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip all tests in this folder unless explicitly requested."""
    # Check if we're running tests specifically from this folder
    # If pytest was invoked with tests/manual/ path, run them
    for item in items:
        if "manual" in str(item.fspath):
            item.add_marker(
                pytest.mark.skip(reason="Manual test - run explicitly with: pytest tests/manual/")
            )
