"""Regression tests for bug-hunt round 5 (spend honesty).

Each class pins a defect so it cannot silently return.
"""

from __future__ import annotations

import inspect

from primr.agentic.cost_guard import CostGuardHook
from primr.agentic.hooks import HookContext, HookResult, HookType
from primr.core.cli import process_batch as cli_process_batch
from primr.core.cli_batch_runtime import _fallback_estimate, process_batch
from primr.utils.cost_estimator import CostEstimate


def _estimate(cost: float, *, notes: list[str] | None = None) -> CostEstimate:
    return CostEstimate(
        mode="complete",
        estimated_input_tokens=1,
        estimated_output_tokens=1,
        estimated_search_queries=0,
        input_cost=0.0,
        output_cost=cost,
        search_cost=0.0,
        total_cost=cost,
        duration_minutes="10-20",
        notes=notes or [],
    )


class TestCostGuardExhaustedZeroEstimate:
    def test_exhausted_budget_blocks_zero_cost_stage(self) -> None:
        import asyncio

        hook = CostGuardHook(max_cost_usd=2.0)
        hook.set_spent(2.0)
        response = asyncio.run(
            hook.execute(
                HookContext(
                    hook_type=HookType.PRE_TOOL_USE,
                    arguments={"estimated_cost_usd": 0.0},
                )
            )
        )
        assert response.result == HookResult.BLOCK


class TestProcessBatchFailClosedDefault:
    def test_library_default_is_not_skip_confirm(self) -> None:
        assert inspect.signature(process_batch).parameters["skip_confirm"].default is False
        assert inspect.signature(cli_process_batch).parameters["skip_confirm"].default is False


class TestSsrfFailClosedEmbeddings:
    def test_unparseable_resolved_address_is_blocked(self, monkeypatch) -> None:
        import socket

        from primr.utils.security import is_safe_url

        def fake_getaddrinfo(host, port, *a, **k):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("fe80::1%eth0", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        ok, reason = is_safe_url("http://example.com/")
        assert ok is False
        assert reason is not None

    def test_ipv4_translated_loopback_blocked(self, monkeypatch) -> None:
        import socket

        from primr.utils.security import is_safe_url

        def fake_getaddrinfo(host, port, *a, **k):
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:0:7f00:1", 0, 0, 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        ok, _reason = is_safe_url("http://example.com/")
        assert ok is False

    def test_ipv4_compatible_loopback_blocked(self, monkeypatch) -> None:
        import socket

        from primr.utils.security import is_safe_url

        def fake_getaddrinfo(host, port, *a, **k):
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::7f00:1", 0, 0, 0))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        ok, _reason = is_safe_url("http://example.com/")
        assert ok is False


class TestBatchFallbackUsesPlanningFloor:
    def test_cheap_historical_cannot_undercut_planning(self, monkeypatch) -> None:
        def fake_estimate(mode, include_ai_strategy=False, use_historical=False, **kwargs):
            cost = 0.10 if use_historical else 4.27
            notes = ["Based on 3 historical runs"] if use_historical else []
            return _estimate(cost, notes=notes)

        monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", fake_estimate)
        estimate = _fallback_estimate(
            mode="complete",
            ai_strategy=True,
            platforms=None,
            lite_strategy=False,
            fast_mode=True,
            premium_mode=False,
            verify=False,
            grok_tier="hybrid",
            strategies=None,
        )
        assert estimate.total_cost == 4.27

    def test_higher_historical_still_raises_the_floor(self, monkeypatch) -> None:
        def fake_estimate(mode, include_ai_strategy=False, use_historical=False, **kwargs):
            cost = 9.50 if use_historical else 4.27
            notes = ["Based on 3 historical runs"] if use_historical else []
            return _estimate(cost, notes=notes)

        monkeypatch.setattr("primr.utils.cost_estimator.estimate_cost", fake_estimate)
        estimate = _fallback_estimate(
            mode="complete",
            ai_strategy=False,
            platforms=None,
            lite_strategy=False,
            fast_mode=False,
            premium_mode=False,
            verify=False,
            grok_tier="hybrid",
            strategies=None,
        )
        assert estimate.total_cost == 9.50
