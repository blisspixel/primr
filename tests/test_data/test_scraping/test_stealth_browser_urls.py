"""Pure URL-filter tests for the stealth-browser tier."""

from primr.data.scraping.stealth_browser import _is_low_value_url


def test_low_value_domain_detection_ignores_explicit_port() -> None:
    assert _is_low_value_url("https://www.linkedin.com:8443/company/example")


def test_low_value_domain_detection_normalizes_root_dot() -> None:
    assert _is_low_value_url("https://www.linkedin.com./company/example")
