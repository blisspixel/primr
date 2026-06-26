"""Tests for Chromium browser egress controls."""

from unittest.mock import MagicMock, patch

from primr.data.scraping.browser_egress import (
    browser_launch_args,
    browser_request_allowed,
    install_playwright_egress_guard,
    plan_browser_egress,
)
from primr.utils.url_security import SafeUrlResolution


def _resolution(
    *,
    original_url: str = "https://example.com/page",
    resolved_ip: str = "93.184.216.34",
) -> SafeUrlResolution:
    return SafeUrlResolution(
        original_url=original_url,
        request_url=f"https://{resolved_ip}/page",
        host_header="example.com",
        sni_hostname="example.com",
        resolved_ip=resolved_ip,
    )


def test_plan_browser_egress_builds_chromium_resolver_rule_for_hostname():
    resolution = _resolution()

    with patch(
        "primr.data.scraping.browser_egress.resolve_safe_url_for_connect",
        return_value=(resolution, None),
    ):
        plan, error = plan_browser_egress("https://example.com/page")

    assert error is None
    assert plan is not None
    assert plan.hostname == "example.com"
    assert plan.resolved_ip == "93.184.216.34"
    assert plan.resolver_rule == "MAP example.com 93.184.216.34"
    assert plan.launch_arg == "--host-resolver-rules=MAP example.com 93.184.216.34"


def test_plan_browser_egress_brackets_ipv6_resolver_addresses():
    resolution = _resolution(resolved_ip="2606:2800:220:1:248:1893:25c8:1946")

    with patch(
        "primr.data.scraping.browser_egress.resolve_safe_url_for_connect",
        return_value=(resolution, None),
    ):
        plan, error = plan_browser_egress("https://example.com/page")

    assert error is None
    assert plan is not None
    assert (
        plan.launch_arg
        == "--host-resolver-rules=MAP example.com [2606:2800:220:1:248:1893:25c8:1946]"
    )


def test_plan_browser_egress_does_not_add_resolver_rule_for_ip_literals():
    resolution = SafeUrlResolution(
        original_url="https://93.184.216.34/page",
        request_url="https://93.184.216.34/page",
        host_header="93.184.216.34",
        sni_hostname="93.184.216.34",
        resolved_ip="93.184.216.34",
    )

    with patch(
        "primr.data.scraping.browser_egress.resolve_safe_url_for_connect",
        return_value=(resolution, None),
    ):
        plan, error = plan_browser_egress("https://93.184.216.34/page")

    assert error is None
    assert plan is not None
    assert plan.launch_arg is None
    assert browser_launch_args(["--base"], plan) == ["--base"]


def test_browser_launch_args_appends_resolver_arg_for_hostname_plan():
    resolution = _resolution()
    with patch(
        "primr.data.scraping.browser_egress.resolve_safe_url_for_connect",
        return_value=(resolution, None),
    ):
        plan, _error = plan_browser_egress("https://example.com/page")

    assert browser_launch_args(["--base"], plan) == [
        "--base",
        "--host-resolver-rules=MAP example.com 93.184.216.34",
    ]


def test_browser_request_allowed_skips_non_http_schemes():
    with patch("primr.data.scraping.browser_egress.is_safe_url") as safe_url:
        allowed, reason = browser_request_allowed("data:text/plain,ok")

    assert allowed is True
    assert reason is None
    safe_url.assert_not_called()


def test_install_playwright_egress_guard_continues_safe_requests():
    context = MagicMock()
    route = MagicMock()
    route.request.url = "https://example.com/page"

    with patch(
        "primr.data.scraping.browser_egress.browser_request_allowed",
        return_value=(True, None),
    ):
        install_playwright_egress_guard(context, "test")
        handler = context.route.call_args.args[1]
        handler(route)

    context.route.assert_called_once_with("**/*", handler)
    route.continue_.assert_called_once()
    route.abort.assert_not_called()


def test_install_playwright_egress_guard_aborts_unsafe_requests():
    context = MagicMock()
    route = MagicMock()
    route.request.url = "http://127.0.0.1/admin"

    with patch(
        "primr.data.scraping.browser_egress.browser_request_allowed",
        return_value=(False, "Private/reserved IP addresses are blocked"),
    ):
        install_playwright_egress_guard(context, "test")
        handler = context.route.call_args.args[1]
        handler(route)

    route.abort.assert_called_once()
    route.continue_.assert_not_called()


def test_install_playwright_egress_guard_fails_closed_on_guard_error():
    context = MagicMock()
    route = MagicMock()
    route.request.url = "https://example.com/page"

    with patch(
        "primr.data.scraping.browser_egress.browser_request_allowed",
        side_effect=RuntimeError("resolver failed"),
    ):
        install_playwright_egress_guard(context, "test")
        handler = context.route.call_args.args[1]
        handler(route)

    route.abort.assert_called_once()
    route.continue_.assert_not_called()
