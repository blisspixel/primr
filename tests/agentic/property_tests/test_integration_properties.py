"""
Property-based tests for Integration Module.

This module validates the correctness properties of the integration
between agentic architecture and existing primr infrastructure.

Properties tested:
- Property 22: Error Hierarchy Compliance
- Property 23: Disabled Mode Equivalence

Validates: Requirements 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st


# =============================================================================
# PROPERTY 22: Error Hierarchy Compliance
# =============================================================================

def test_agentic_errors_inherit_from_primr_error():
    """
    All agentic errors inherit from PrimrError.
    
    This ensures consistent error handling across the codebase.
    
    Validates: Requirements 8.3
    """
    from primr.utils.errors import PrimrError
    from primr.agentic.errors import (
        AgenticError,
        SubagentError,
        OrchestratorError,
        HookError,
        MemoryError,
        RoadmapParseError,
    )
    
    # All agentic errors should inherit from PrimrError
    assert issubclass(AgenticError, PrimrError)
    assert issubclass(SubagentError, PrimrError)
    assert issubclass(OrchestratorError, PrimrError)
    assert issubclass(HookError, PrimrError)
    assert issubclass(MemoryError, PrimrError)
    assert issubclass(RoadmapParseError, PrimrError)


def test_agentic_errors_have_required_attributes():
    """
    All agentic errors have the required PrimrError attributes.
    
    Validates: Requirements 8.3
    """
    from primr.agentic.errors import (
        AgenticError,
        SubagentError,
        OrchestratorError,
        HookError,
    )
    
    # Create instances and check attributes
    errors = [
        AgenticError(message="test"),
        SubagentError(message="test", subagent="scraper"),
        OrchestratorError(message="test", state="idle"),
        HookError(message="test", hook_name="cost_guard"),
    ]
    
    for error in errors:
        # All PrimrError attributes should be present
        assert hasattr(error, "message")
        assert hasattr(error, "category")
        assert hasattr(error, "recoverable")
        assert hasattr(error, "correlation_id")
        assert hasattr(error, "timestamp")
        
        # Should have to_dict method
        assert hasattr(error, "to_dict")
        error_dict = error.to_dict()
        assert "type" in error_dict
        assert "message" in error_dict
        assert "category" in error_dict


def test_subagent_error_is_transient():
    """
    SubagentError is classified as transient (recoverable).
    
    Validates: Requirements 8.3
    """
    from primr.agentic.errors import SubagentError
    from primr.utils.errors import TransientError
    
    # SubagentError should be a TransientError
    assert issubclass(SubagentError, TransientError)
    
    # Instance should be recoverable
    error = SubagentError(message="test", subagent="scraper")
    assert error.recoverable is True


def test_memory_error_is_permanent():
    """
    MemoryError is classified as permanent (not recoverable).
    
    Validates: Requirements 8.3
    """
    from primr.agentic.errors import MemoryError
    from primr.utils.errors import PermanentError
    
    # MemoryError should be a PermanentError
    assert issubclass(MemoryError, PermanentError)
    
    # Instance should not be recoverable
    error = MemoryError(message="test", operation="save")
    assert error.recoverable is False


# =============================================================================
# PROPERTY 23: Disabled Mode Equivalence
# =============================================================================

def test_integration_graceful_degradation():
    """
    Integration components work gracefully when dependencies unavailable.
    
    Validates: Requirements 8.6
    """
    from primr.agentic.integration import (
        OrchestratorStateMachineAdapter,
        TelemetryIntegration,
        CircuitBreakerIntegration,
        AgenticIntegration,
    )
    
    # All integrations should initialize without error
    sm = OrchestratorStateMachineAdapter(job_id="test")
    telemetry = TelemetryIntegration()
    cb = CircuitBreakerIntegration()
    combined = AgenticIntegration(job_id="test")
    
    # Should report availability status
    assert isinstance(sm.is_available, bool)
    assert isinstance(telemetry.is_available, bool)
    assert isinstance(cb.is_available, bool)
    
    # Combined should report all statuses
    status = combined.get_status()
    assert "state_machine" in status
    assert "telemetry" in status
    assert "circuit_breaker" in status


def test_state_machine_adapter_no_crash_when_unavailable():
    """
    State machine adapter doesn't crash when state machine unavailable.
    
    Validates: Requirements 8.2, 8.6
    """
    from primr.agentic.integration import OrchestratorStateMachineAdapter
    from primr.agentic.orchestrator import OrchestratorState
    
    adapter = OrchestratorStateMachineAdapter(job_id="test")
    
    # These should not raise even if state machine unavailable
    result = adapter.transition_to(OrchestratorState.SCRAPING)
    assert isinstance(result, bool)
    
    history = adapter.get_history()
    assert isinstance(history, list)
    
    save_result = adapter.save("test.json")
    assert isinstance(save_result, bool)


def test_telemetry_integration_no_crash_when_disabled():
    """
    Telemetry integration doesn't crash when telemetry disabled.
    
    Validates: Requirements 8.4, 8.6
    """
    from primr.agentic.integration import TelemetryIntegration
    
    telemetry = TelemetryIntegration()
    
    # Span context managers should work even when disabled
    with telemetry.subagent_span("scraper", "scrape") as span:
        # Should get a span-like object (possibly NullSpan)
        assert span is not None
        # Should be able to call span methods without error
        span.set_attribute("test", "value")
    
    with telemetry.hook_span("cost_guard", "pre_tool_use") as span:
        assert span is not None
    
    with telemetry.orchestrator_span("Acme", "full") as span:
        assert span is not None


def test_circuit_breaker_integration_no_crash_when_unavailable():
    """
    Circuit breaker integration doesn't crash when unavailable.
    
    Validates: Requirements 8.5, 8.6
    """
    from primr.agentic.integration import CircuitBreakerIntegration
    
    cb = CircuitBreakerIntegration()
    
    # These should not raise even if circuit breaker unavailable
    can_exec = cb.can_execute("test")
    assert isinstance(can_exec, bool)
    
    # Should default to allowing execution
    assert can_exec is True
    
    # Recording should not raise
    cb.record_success("test")
    cb.record_failure("test")
    
    # State should return something
    state = cb.get_state("test")
    assert isinstance(state, str)
    
    # Reset should not raise
    cb.reset("test")


@pytest.mark.asyncio
async def test_circuit_breaker_protected_execution():
    """
    Circuit breaker protected execution context manager works.
    
    Validates: Requirements 8.5
    """
    from primr.agentic.integration import CircuitBreakerIntegration
    
    cb = CircuitBreakerIntegration()
    
    # Should allow execution when circuit closed
    async with cb.protected_execution("test") as allowed:
        assert allowed is True


def test_combined_integration_initialization():
    """
    Combined AgenticIntegration initializes all components.
    
    Validates: Requirements 8.2, 8.4, 8.5
    """
    from primr.agentic.integration import AgenticIntegration
    
    integration = AgenticIntegration(job_id="test-123")
    
    # All components should be initialized
    assert integration.state_machine is not None
    assert integration.telemetry is not None
    assert integration.circuit_breaker is not None
    
    # Job ID should be set
    assert integration.job_id == "test-123"
    assert integration.state_machine.job_id == "test-123"


# =============================================================================
# STATE MACHINE INTEGRATION TESTS
# =============================================================================

def test_state_machine_adapter_transitions():
    """
    State machine adapter correctly maps orchestrator states.
    
    Validates: Requirements 8.2
    """
    from primr.agentic.integration import OrchestratorStateMachineAdapter
    from primr.agentic.orchestrator import OrchestratorState
    
    adapter = OrchestratorStateMachineAdapter(job_id="test")
    
    if adapter.is_available:
        # SCRAPING should trigger "start"
        result = adapter.transition_to(OrchestratorState.SCRAPING)
        assert result is True
        
        # COMPLETED should trigger "complete"
        result = adapter.transition_to(OrchestratorState.COMPLETED)
        assert result is True


def test_state_machine_adapter_history():
    """
    State machine adapter tracks transition history.
    
    Validates: Requirements 8.2
    """
    from primr.agentic.integration import OrchestratorStateMachineAdapter
    from primr.agentic.orchestrator import OrchestratorState
    
    adapter = OrchestratorStateMachineAdapter(job_id="test")
    
    if adapter.is_available:
        adapter.transition_to(OrchestratorState.SCRAPING)
        
        history = adapter.get_history()
        assert isinstance(history, list)
        # Should have at least one transition
        assert len(history) >= 1


# =============================================================================
# TELEMETRY INTEGRATION TESTS
# =============================================================================

def test_telemetry_record_subagent_result():
    """
    Telemetry can record subagent result attributes.
    
    Validates: Requirements 8.4
    """
    from primr.agentic.integration import TelemetryIntegration, _NullSpan
    from primr.agentic.subagents import SubagentResult, SubagentStatus
    
    telemetry = TelemetryIntegration()
    
    result = SubagentResult(
        status=SubagentStatus.COMPLETED,
        metrics={"duration_seconds": 10.5},
    )
    
    # Should not raise with NullSpan
    span = _NullSpan()
    telemetry.record_subagent_result(span, result)
    
    # Should not raise with None
    telemetry.record_subagent_result(None, result)


def test_telemetry_span_attributes():
    """
    Telemetry spans accept custom attributes.
    
    Validates: Requirements 8.4
    """
    from primr.agentic.integration import TelemetryIntegration
    
    telemetry = TelemetryIntegration()
    
    # Should accept custom attributes
    with telemetry.subagent_span(
        "scraper",
        "scrape",
        custom_attr="value",
        pages=10,
    ) as span:
        assert span is not None


# =============================================================================
# CIRCUIT BREAKER INTEGRATION TESTS
# =============================================================================

def test_circuit_breaker_state_tracking():
    """
    Circuit breaker tracks state correctly.
    
    Validates: Requirements 8.5
    """
    from primr.agentic.integration import CircuitBreakerIntegration
    
    cb = CircuitBreakerIntegration()
    
    if cb.is_available:
        # Initial state should be closed
        state = cb.get_state("new_key")
        assert state == "closed"
        
        # After success, should still be closed
        cb.record_success("new_key")
        state = cb.get_state("new_key")
        assert state == "closed"


def test_circuit_breaker_reset():
    """
    Circuit breaker reset works correctly.
    
    Validates: Requirements 8.5
    """
    from primr.agentic.integration import CircuitBreakerIntegration
    
    cb = CircuitBreakerIntegration()
    
    if cb.is_available:
        # Record some failures
        for _ in range(10):
            cb.record_failure("reset_test")
        
        # Reset should work
        cb.reset("reset_test")
        
        # Should be able to execute again
        assert cb.can_execute("reset_test") is True


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================

def test_null_span_methods():
    """
    NullSpan methods are no-ops that don't raise.
    """
    from primr.agentic.integration import _NullSpan
    
    span = _NullSpan()
    
    # All methods should be no-ops
    span.set_attribute("key", "value")
    span.set_attributes({"a": 1, "b": 2})
    span.add_event("test_event")
    span.add_event("test_event", {"attr": "value"})


@given(
    job_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), max_codepoint=127),
        min_size=1,
        max_size=20,
    ).filter(lambda x: x.strip()),
)
@settings(max_examples=20, deadline=None)
def test_integration_with_various_job_ids(job_id: str):
    """
    Integration handles various job ID formats.
    
    Validates: Requirements 8.2
    """
    from primr.agentic.integration import AgenticIntegration
    
    # Should not raise for any valid job ID
    integration = AgenticIntegration(job_id=job_id)
    
    assert integration.job_id == job_id
    assert integration.state_machine.job_id == job_id


def test_integration_exports():
    """
    All integration classes are properly exported.
    """
    from primr.agentic import (
        AgenticIntegration,
        CircuitBreakerIntegration,
        OrchestratorStateMachineAdapter,
        TelemetryIntegration,
    )
    
    # All should be importable
    assert AgenticIntegration is not None
    assert CircuitBreakerIntegration is not None
    assert OrchestratorStateMachineAdapter is not None
    assert TelemetryIntegration is not None
