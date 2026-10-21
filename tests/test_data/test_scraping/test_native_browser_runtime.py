"""Explicit offline native-browser gate, separate from the hermetic unit suite."""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("PRIMR_BROWSER_SMOKE") != "1",
    reason="Explicit native browser gate requires installed Chromium",
)


@pytest.mark.parametrize("package", ["playwright", "patchright"])
def test_sync_browser_renders_offline_in_child_process(package):
    # A native-runtime crash must fail this gate rather than kill pytest.
    program = f"""
from {package}.sync_api import sync_playwright
from primr.data.scraping.chromium_config import browser_launch_options
with sync_playwright() as driver:
    browser = driver.chromium.launch(**browser_launch_options(True))
    page = browser.new_page(offline=True)
    page.set_content('<title>ExampleCo</title><main>Offline evidence control.</main>')
    assert page.title() == 'ExampleCo'
    assert page.locator('main').inner_text() == 'Offline evidence control.'
    browser.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
