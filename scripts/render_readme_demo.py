#!/usr/bin/env python3
"""Render docs/images/primr-demo.png from the placeholder terminal HTML.

Requires Playwright Chromium (``uv run playwright install chromium``).
No network, no model calls, no real company data.

Usage::

    uv run --no-sync python scripts/render_readme_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    html = repo / "docs" / "images" / "primr-demo-terminal.html"
    out = repo / "docs" / "images" / "primr-demo.png"
    if not html.is_file():
        print(f"missing demo HTML: {html}", file=sys.stderr)
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is required: uv run playwright install chromium", file=sys.stderr)
        return 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1100, "height": 980},
            device_scale_factor=2,
        )
        page.goto(html.resolve().as_uri())
        page.wait_for_timeout(150)
        page.locator("#shot").screenshot(path=str(out), type="png")
        browser.close()

    size = out.stat().st_size
    print(f"wrote {out.relative_to(repo)} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
