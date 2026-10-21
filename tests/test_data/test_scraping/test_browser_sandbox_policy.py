"""Keep Chromium containment policy at every SDK launch boundary."""

import ast
from pathlib import Path

import pytest

from primr.data.scraping import chromium_config


@pytest.mark.parametrize("headless", [True, False])
@pytest.mark.parametrize("opt_out", [True, False])
def test_sdk_options_preserve_headless_and_explicit_sandbox_policy(monkeypatch, headless, opt_out):
    monkeypatch.setattr(chromium_config, "SANDBOX_OPT_OUT", opt_out)
    options = chromium_config.browser_launch_options(headless)
    assert options["headless"] is headless
    assert options["chromium_sandbox"] is (not opt_out)


def test_every_production_playwright_launch_uses_owned_sandbox_options():
    root = Path(chromium_config.__file__).parent
    launches = []
    for name in ("browsers.py", "stealth_browser.py", "vision_browser.py"):
        for node in ast.walk(ast.parse((root / name).read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"launch", "launch_persistent_context"}:
                continue
            launches.append((name, node.lineno))
            assert any(
                keyword.arg is None
                and isinstance(keyword.value, ast.Call)
                and isinstance(keyword.value.func, ast.Name)
                and keyword.value.func.id == "browser_launch_options"
                for keyword in node.keywords
            ), f"{name}:{node.lineno} bypasses sandbox launch policy"
    assert launches
