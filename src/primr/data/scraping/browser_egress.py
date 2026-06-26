"""Browser egress controls for Chromium-backed scraper tiers."""

from __future__ import annotations

import ipaddress
import logging
import weakref
from dataclasses import dataclass
from urllib.parse import urlparse

from primr.utils.security import is_safe_url, resolve_safe_url_for_connect

from .browser_proxy import BrowserEgressProxy, browser_proxy_launch_args

logger = logging.getLogger(__name__)

_GUARDED_CONTEXT_IDS: set[int] = set()
_GUARDED_CONTEXT_REFS: dict[int, weakref.ReferenceType[object]] = {}


@dataclass(frozen=True, slots=True)
class BrowserEgressPlan:
    """Validated browser connection target and Chromium resolver override."""

    url: str
    hostname: str
    resolved_ip: str
    resolver_rule: str | None
    launch_arg: str | None


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _format_chromium_resolve_address(address: str) -> str:
    return f"[{address}]" if ":" in address else address


def plan_browser_egress(url: str) -> tuple[BrowserEgressPlan | None, str | None]:
    """Resolve ``url`` once and build Chromium launch args that pin that result."""

    resolution, error = resolve_safe_url_for_connect(url)
    if error or resolution is None:
        return None, error

    parsed = urlparse(resolution.original_url)
    hostname = parsed.hostname
    if not hostname:
        return None, "URL must include a hostname"

    resolver_rule = None
    launch_arg = None
    if not _is_ip_literal(hostname):
        address = _format_chromium_resolve_address(resolution.resolved_ip)
        resolver_rule = f"MAP {hostname} {address}"
        launch_arg = f"--host-resolver-rules={resolver_rule}"

    return (
        BrowserEgressPlan(
            url=resolution.original_url,
            hostname=hostname,
            resolved_ip=resolution.resolved_ip,
            resolver_rule=resolver_rule,
            launch_arg=launch_arg,
        ),
        None,
    )


def browser_launch_args(
    base_args: list[str],
    plan: BrowserEgressPlan | None,
    proxy: BrowserEgressProxy | None = None,
) -> list[str]:
    """Return Chromium launch args with an optional DNS pin appended."""

    args = list(base_args)
    if plan and plan.launch_arg:
        args.append(plan.launch_arg)
    args.extend(browser_proxy_launch_args(proxy))
    return args


def browser_request_allowed(url: str) -> tuple[bool, str | None]:
    """Validate browser HTTP requests before Playwright lets them reach the network."""

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return True, None
    return is_safe_url(url)


def _drop_guarded_context(context_id: int):
    def _drop(_ref: weakref.ReferenceType[object]) -> None:
        _GUARDED_CONTEXT_REFS.pop(context_id, None)

    return _drop


def _context_already_guarded(context: object) -> bool:
    context_id = id(context)
    context_ref = _GUARDED_CONTEXT_REFS.get(context_id)
    if context_ref is not None:
        if context_ref() is context:
            return True
        _GUARDED_CONTEXT_REFS.pop(context_id, None)

    return context_id in _GUARDED_CONTEXT_IDS


def _mark_context_guarded(context: object) -> None:
    context_id = id(context)
    try:
        _GUARDED_CONTEXT_REFS[context_id] = weakref.ref(
            context,
            _drop_guarded_context(context_id),
        )
    except TypeError:
        _GUARDED_CONTEXT_IDS.add(context_id)


def install_playwright_egress_guard(context, tier_name: str) -> None:
    """Install a Playwright route guard that aborts unsafe browser requests."""

    if _context_already_guarded(context):
        return

    def _guard(route) -> None:
        request_url = route.request.url
        try:
            allowed, reason = browser_request_allowed(request_url)
        except Exception as exc:
            logger.warning(
                "%s: aborted browser request %s after guard failure: %s",
                tier_name,
                request_url,
                exc,
            )
            route.abort()
            return

        if allowed:
            route.continue_()
            return

        logger.info("%s: blocked browser request %s (%s)", tier_name, request_url, reason)
        route.abort()

    context.route("**/*", _guard)
    _mark_context_guarded(context)
