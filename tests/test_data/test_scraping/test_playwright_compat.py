"""Tests for sync browser compatibility boundaries."""

from unittest.mock import MagicMock

import pytest

from primr.data.scraping import stealth_browser
from primr.data.scraping.playwright_compat import (
    SYNC_BROWSER_UNAVAILABLE_REASON,
    sync_browser_runtime_supported,
)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((3, 14), True),
        ((3, 15), False),
        ((3, 16), False),
    ],
)
def test_sync_browser_runtime_boundary(version, expected):
    assert sync_browser_runtime_supported(version) is expected


def test_unavailable_reason_is_actionable():
    assert "Python 3.15" in SYNC_BROWSER_UNAVAILABLE_REASON
    assert "Playwright" in SYNC_BROWSER_UNAVAILABLE_REASON
    assert "Python 3.12 through 3.14" in SYNC_BROWSER_UNAVAILABLE_REASON


def test_patchright_fails_closed_before_dependency_probe(monkeypatch):
    monkeypatch.setattr(stealth_browser, "sync_browser_runtime_supported", lambda: False)
    dependency_probe = MagicMock()
    monkeypatch.setattr(stealth_browser, "_patchright_available", dependency_probe)

    result = stealth_browser.scrape_with_patchright("https://example.com")

    assert result.success is False
    assert result.tier == "patchright"
    assert result.error == SYNC_BROWSER_UNAVAILABLE_REASON
    assert len(result.attempts) == 1
    dependency_probe.assert_not_called()
