"""Property-based invariants for CostGuardHook (budget enforcement).

CostGuard is the agent's spend ceiling. Two invariants must hold for any
sequence of recorded costs and any probe estimate:

  1. `remaining == max(0, max_cost - spent)` — never reports negative headroom.
  2. The pre-tool check BLOCKs when remaining is already exhausted
     (`spent >= max_cost`) or when `spent + max(0, estimate)` would exceed
     `max_cost`, and ALLOWs otherwise — no spend slips past the gate, and
     an affordable call is never wrongly blocked.
"""

from __future__ import annotations

import asyncio

from hypothesis import given
from hypothesis import strategies as st

from primr.agentic.cost_guard import CostGuardHook
from primr.agentic.hooks import HookContext, HookResult, HookType

_costs = st.lists(
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    max_size=20,
)
_max_cost = st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False)
_probe = st.floats(min_value=-10.0, max_value=200.0, allow_nan=False, allow_infinity=False)


class TestCostGuardInvariants:
    @given(_costs, _max_cost)
    def test_remaining_never_negative(self, costs, max_cost):
        hook = CostGuardHook(max_cost_usd=max_cost)
        for c in costs:
            hook.record_cost(c)
        assert hook.remaining == max(0.0, max_cost - hook.spent)
        assert hook.remaining >= 0.0

    @given(_costs, _max_cost, _probe)
    def test_block_decision_matches_budget_rule(self, costs, max_cost, probe):
        hook = CostGuardHook(max_cost_usd=max_cost)
        for c in costs:
            hook.record_cost(c)
        spent = hook.spent

        ctx = HookContext(
            hook_type=HookType.PRE_TOOL_USE,
            tool_name="research_company",
            arguments={"estimated_cost_usd": probe},
        )
        resp = asyncio.run(hook.execute(ctx))

        # Exhausted remaining blocks even a $0 estimate; otherwise the probe
        # is clamped at 0 and compared with a strict greater-than.
        estimated = max(0.0, probe)
        expected_block = spent >= max_cost or spent + estimated > max_cost
        assert (resp.result == HookResult.BLOCK) == expected_block
