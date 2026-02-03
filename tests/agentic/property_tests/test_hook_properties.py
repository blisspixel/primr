"""
Property-based tests for Hook System.

This module validates the correctness properties of the Hook System
using the Hypothesis library. Each test corresponds to a formal
property from the design document.

Properties tested:
- Property 6: Hook Execution Order
- Property 7: Hook Blocking Behavior
- Property 8: Hook Error Handling

Validates: Requirements 4.1, 4.2, 4.4, 4.5, 4.6, 4.9, 4.10
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from primr.agentic.hooks import (
    Hook,
    HookContext,
    HookResponse,
    HookResult,
    HookSystem,
    HookType,
    CostGuardHook,
    SSRFGuardHook,
)


# =============================================================================
# TEST HOOKS
# =============================================================================

class RecordingHook(Hook):
    """Hook that records when it was executed."""

    def __init__(self, priority: int, hook_type: HookType, execution_log: list[int]):
        super().__init__(priority=priority, name=f"RecordingHook_{priority}")
        self._hook_type = hook_type
        self._execution_log = execution_log

    @property
    def hook_type(self) -> HookType:
        return self._hook_type

    async def execute(self, context: HookContext) -> HookResponse:
        self._execution_log.append(self.priority)
        return HookResponse(result=HookResult.ALLOW)


class BlockingHook(Hook):
    """Hook that blocks execution."""

    def __init__(self, priority: int, message: str = "Blocked"):
        super().__init__(priority=priority, name=f"BlockingHook_{priority}")
        self._message = message

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        return HookResponse(result=HookResult.BLOCK, message=self._message)


class FailingHook(Hook):
    """Hook that raises an exception."""

    def __init__(self, priority: int, error_message: str = "Hook failed"):
        super().__init__(priority=priority, name=f"FailingHook_{priority}")
        self._error_message = error_message

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        raise RuntimeError(self._error_message)


# =============================================================================
# STRATEGIES
# =============================================================================

# Strategy for distinct priorities (no duplicates)
@st.composite
def distinct_priorities(draw, min_count: int = 2, max_count: int = 10):
    """Generate a list of distinct priority values."""
    count = draw(st.integers(min_value=min_count, max_value=max_count))
    priorities = draw(
        st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=count,
            max_size=count,
            unique=True,
        )
    )
    return priorities


# Strategy for cost values
cost_values = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)


# =============================================================================
# PROPERTY 6: Hook Execution Order
# =============================================================================

# Feature: agentic-architecture, Property 6: Hook Execution Order
@given(priorities=distinct_priorities(min_count=2, max_count=8))
@settings(max_examples=50, deadline=None)
def test_hook_execution_order(priorities: list[int]):
    """
    Hooks execute in ascending priority order.

    For any set of registered hooks with distinct priorities, hooks
    should execute in ascending priority order (lower priority number
    executes first).

    Validates: Requirements 4.1, 4.2, 4.10
    """
    execution_log: list[int] = []
    hooks = HookSystem()

    # Register hooks in random order
    for priority in priorities:
        hook = RecordingHook(priority, HookType.PRE_TOOL_USE, execution_log)
        hooks.register(hook)

    # Run hooks
    context = HookContext(hook_type=HookType.PRE_TOOL_USE, stage_name="test")
    asyncio.run(hooks.run_pre_hooks("test", context))

    # Verify execution order
    assert len(execution_log) == len(priorities), (
        f"Expected {len(priorities)} executions, got {len(execution_log)}"
    )

    # Execution log should be sorted (ascending priority)
    assert execution_log == sorted(priorities), (
        f"Hooks executed out of order: {execution_log}, expected {sorted(priorities)}"
    )


# Feature: agentic-architecture, Property 6: Hook Execution Order (post hooks)
@given(priorities=distinct_priorities(min_count=2, max_count=8))
@settings(max_examples=50, deadline=None)
def test_post_hook_execution_order(priorities: list[int]):
    """
    Post hooks also execute in ascending priority order.

    Validates: Requirements 4.1, 4.2, 4.10
    """
    execution_log: list[int] = []
    hooks = HookSystem()

    # Register post hooks in random order
    for priority in priorities:
        hook = RecordingHook(priority, HookType.POST_TOOL_USE, execution_log)
        hooks.register(hook)

    # Run hooks
    asyncio.run(hooks.run_post_hooks("test", result=None))

    # Verify execution order
    assert execution_log == sorted(priorities)


# =============================================================================
# PROPERTY 7: Hook Blocking Behavior
# =============================================================================

# Feature: agentic-architecture, Property 7: Hook Blocking Behavior
@given(
    block_priority=st.integers(min_value=1, max_value=100),
    other_priorities=st.lists(
        st.integers(min_value=101, max_value=200),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
@settings(max_examples=50, deadline=None)
def test_blocking_stops_execution(block_priority: int, other_priorities: list[int]):
    """
    PreToolUse hook that returns BLOCK stops further execution.

    For any PreToolUse hook that returns HookResult.BLOCK, the
    associated tool invocation should not execute and subsequent
    hooks should not run.

    Validates: Requirements 4.4, 4.5, 4.6
    """
    execution_log: list[int] = []
    hooks = HookSystem()

    # Register blocking hook with low priority (runs first)
    blocking_hook = BlockingHook(block_priority, message="Test block")
    hooks.register(blocking_hook)

    # Register recording hooks with higher priorities
    for priority in other_priorities:
        hook = RecordingHook(priority, HookType.PRE_TOOL_USE, execution_log)
        hooks.register(hook)

    # Run hooks
    response = asyncio.run(hooks.run_pre_hooks("test"))

    # Verify blocking behavior
    assert response.result == HookResult.BLOCK
    assert response.message == "Test block"

    # No hooks after the blocking hook should have executed
    assert len(execution_log) == 0, (
        f"Hooks executed after block: {execution_log}"
    )


# Feature: agentic-architecture, Property 7: Hook Blocking Behavior (message preserved)
@given(message=st.text(min_size=1, max_size=100, alphabet=st.characters(max_codepoint=127)))
@settings(max_examples=30, deadline=None)
def test_block_message_preserved(message: str):
    """
    Block message is preserved in response.

    Validates: Requirements 4.4
    """
    hooks = HookSystem()
    hooks.register(BlockingHook(priority=10, message=message))

    response = asyncio.run(hooks.run_pre_hooks("test"))

    assert response.result == HookResult.BLOCK
    assert response.message == message


# =============================================================================
# PROPERTY 8: Hook Error Handling
# =============================================================================

# Feature: agentic-architecture, Property 8: Hook Error Handling (log mode)
def test_error_handling_log_mode():
    """
    Hook errors are logged and execution continues in log mode.

    For any hook that raises an exception during execution, the
    HookSystem should log the error and continue with remaining hooks.

    Validates: Requirements 4.9
    """
    execution_log: list[int] = []
    hooks = HookSystem(on_error="log")

    # Register failing hook
    hooks.register(FailingHook(10, "Test error"))

    # Register recording hook that should still execute
    hooks.register(RecordingHook(20, HookType.PRE_TOOL_USE, execution_log))

    # Run hooks - should not raise
    response = asyncio.run(hooks.run_pre_hooks("test"))

    # Should complete with ALLOW (failing hook logged, not blocking)
    assert response.result == HookResult.ALLOW

    # Recording hook should have executed
    assert 20 in execution_log


# Feature: agentic-architecture, Property 8: Hook Error Handling (raise mode)
def test_error_handling_raise_mode():
    """
    Hook errors are re-raised in raise mode.

    Validates: Requirements 4.9
    """
    from primr.agentic.errors import HookError

    hooks = HookSystem(on_error="raise")
    hooks.register(FailingHook(10, "Test error"))

    # Should raise HookError
    with pytest.raises(HookError) as exc_info:
        asyncio.run(hooks.run_pre_hooks("test"))

    assert "FailingHook" in str(exc_info.value)


# Feature: agentic-architecture, Property 8: Hook Error Handling (skip mode)
def test_error_handling_skip_mode():
    """
    Hook errors are silently skipped in skip mode.

    Validates: Requirements 4.9
    """
    execution_log: list[int] = []
    hooks = HookSystem(on_error="skip")

    # Register failing hook
    hooks.register(FailingHook(10))

    # Register recording hook
    hooks.register(RecordingHook(20, HookType.PRE_TOOL_USE, execution_log))

    # Run hooks - should not raise
    response = asyncio.run(hooks.run_pre_hooks("test"))

    assert response.result == HookResult.ALLOW
    assert 20 in execution_log


# =============================================================================
# COST GUARD HOOK TESTS
# =============================================================================

# Feature: agentic-architecture, CostGuardHook budget enforcement
@given(
    max_cost=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    spent=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    requested=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, deadline=None)
def test_cost_guard_budget_enforcement(max_cost: float, spent: float, requested: float):
    """
    CostGuardHook blocks when budget would be exceeded.

    For any combination of max_cost, spent, and requested amounts,
    the hook should block if spent + requested > max_cost.

    Validates: Requirements 4.5
    """
    hook = CostGuardHook(max_cost_usd=max_cost)
    hook._spent = spent  # Simulate prior spending

    context = HookContext(
        hook_type=HookType.PRE_TOOL_USE,
        arguments={"estimated_cost_usd": requested},
    )

    response = asyncio.run(hook.execute(context))

    if spent + requested > max_cost:
        assert response.result == HookResult.BLOCK
        assert "Budget exceeded" in (response.message or "")
    else:
        assert response.result == HookResult.ALLOW


# Feature: agentic-architecture, CostGuardHook cost tracking
@given(costs=st.lists(cost_values, min_size=1, max_size=10))
@settings(max_examples=30, deadline=None)
def test_cost_guard_tracking(costs: list[float]):
    """
    CostGuardHook accurately tracks cumulative spending.

    Validates: Requirements 4.5
    """
    hook = CostGuardHook(max_cost_usd=1000.0)

    for cost in costs:
        hook.record_cost(cost)

    expected_total = sum(costs)
    assert abs(hook.spent - expected_total) < 0.001, (
        f"Expected spent={expected_total}, got {hook.spent}"
    )


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================

def test_hook_system_invalid_on_error():
    """Invalid on_error value raises ValueError."""
    with pytest.raises(ValueError):
        HookSystem(on_error="invalid")


def test_hook_registration_and_unregistration():
    """Hooks can be registered and unregistered."""
    hooks = HookSystem()
    hook = CostGuardHook()

    hooks.register(hook)
    assert hook in hooks.get_hooks(HookType.PRE_TOOL_USE)

    result = hooks.unregister(hook)
    assert result is True
    assert hook not in hooks.get_hooks(HookType.PRE_TOOL_USE)

    # Unregistering again returns False
    result = hooks.unregister(hook)
    assert result is False


def test_cost_guard_reset():
    """CostGuardHook reset clears spent amount."""
    hook = CostGuardHook(max_cost_usd=10.0)
    hook.record_cost(5.0)
    assert hook.spent == 5.0

    hook.reset()
    assert hook.spent == 0.0


def test_cost_guard_remaining():
    """CostGuardHook remaining returns correct value."""
    hook = CostGuardHook(max_cost_usd=10.0)
    assert hook.remaining == 10.0

    hook.record_cost(3.0)
    assert hook.remaining == 7.0

    hook.record_cost(10.0)  # Overspend
    assert hook.remaining == 0.0  # Never negative


def test_ssrf_guard_no_url():
    """SSRFGuardHook allows when no URL in arguments."""
    hook = SSRFGuardHook()
    context = HookContext(
        hook_type=HookType.PRE_TOOL_USE,
        arguments={"company_name": "Test"},
    )

    response = asyncio.run(hook.execute(context))
    assert response.result == HookResult.ALLOW


def test_hook_context_defaults():
    """HookContext has sensible defaults."""
    context = HookContext(hook_type=HookType.PRE_TOOL_USE)

    assert context.tool_name is None
    assert context.stage_name is None
    assert context.arguments == {}
    assert context.result is None
    assert context.company_name is None


def test_hook_response_defaults():
    """HookResponse has sensible defaults."""
    response = HookResponse(result=HookResult.ALLOW)

    assert response.message is None
    assert response.modified_args is None
