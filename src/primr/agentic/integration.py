"""
Integration module for agentic architecture with existing primr infrastructure.

This module provides integration points between the agentic architecture
and existing primr components:

- State Machine Integration: Orchestrator uses JobStateMachine for lifecycle
- OpenTelemetry Integration: Subagents emit tracing spans
- Circuit Breaker Integration: Subagents use circuit breakers for fault tolerance

Design Principles:
    - Non-Invasive: Integration is opt-in and doesn't break existing code
    - Graceful Degradation: Works even if dependencies are unavailable
    - Observable: All integrations emit appropriate telemetry

Requirements: 8.2, 8.4, 8.5
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from primr.agentic.orchestrator import OrchestratorState
    from primr.agentic.subagents import SubagentResult

logger = logging.getLogger(__name__)


# =============================================================================
# STATE MACHINE INTEGRATION
# =============================================================================

@dataclass
class OrchestratorStateMachineAdapter:
    """
    Adapter to integrate orchestrator with JobStateMachine.

    Maps OrchestratorState to JobState for consistent lifecycle tracking
    across the primr system.

    Attributes:
        job_id: Unique identifier for this orchestration job
        _state_machine: Underlying JobStateMachine instance

    Example:
        adapter = OrchestratorStateMachineAdapter("research-123")
        adapter.transition_to(OrchestratorState.SCRAPING)
        adapter.save("jobs/research-123.json")

    Requirements: 8.2
    """

    job_id: str
    _state_machine: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize the underlying state machine."""
        try:
            from primr.utils.state_machine import create_job_state_machine
            self._state_machine = create_job_state_machine(self.job_id)
        except ImportError:
            logger.debug("State machine module not available")
            self._state_machine = None

    @property
    def is_available(self) -> bool:
        """Check if state machine integration is available."""
        return self._state_machine is not None

    def transition_to(self, orchestrator_state: OrchestratorState) -> bool:
        """
        Transition state machine based on orchestrator state.

        Args:
            orchestrator_state: Target orchestrator state

        Returns:
            True if transition succeeded, False otherwise
        """
        if not self._state_machine:
            return False

        from primr.agentic.orchestrator import OrchestratorState

        # Map orchestrator states to job state machine triggers
        trigger_map = {
            OrchestratorState.SCRAPING: "start",
            OrchestratorState.ANALYZING: None,  # No transition needed
            OrchestratorState.WRITING: None,
            OrchestratorState.QA: None,
            OrchestratorState.COMPLETED: "complete",
            OrchestratorState.FAILED: "fail",
        }

        trigger = trigger_map.get(orchestrator_state)
        if trigger is None:
            return True  # No transition needed

        try:
            self._state_machine.transition(trigger)
            return True
        except Exception as e:
            logger.warning(f"State transition failed: {e}")
            return False

    def save(self, path: str) -> bool:
        """
        Save state machine to file.

        Args:
            path: File path for persistence

        Returns:
            True if save succeeded
        """
        if not self._state_machine:
            return False

        try:
            self._state_machine.save(path)
            return True
        except Exception as e:
            logger.warning(f"State machine save failed: {e}")
            return False

    def get_history(self) -> list[dict[str, Any]]:
        """
        Get state transition history.

        Returns:
            List of state change events
        """
        if not self._state_machine:
            return []

        return [event.to_dict() for event in self._state_machine.history]


# =============================================================================
# OPENTELEMETRY INTEGRATION
# =============================================================================

@dataclass
class TelemetryIntegration:
    """
    OpenTelemetry integration for agentic components.

    Provides tracing spans for subagent operations and hook execution.
    Gracefully degrades when telemetry is disabled or unavailable.

    Attributes:
        service_name: Service name for tracing
        _telemetry: TelemetrySystem instance

    Example:
        telemetry = TelemetryIntegration()

        async with telemetry.subagent_span("scraper", "scrape") as span:
            result = await scraper.execute()
            span.set_attribute("pages_scraped", result.data.pages_scraped)

    Requirements: 8.4
    """

    service_name: str = "primr-agentic"
    _telemetry: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize telemetry system."""
        try:
            from primr.utils.telemetry import TelemetryConfig, TelemetrySystem
            config = TelemetryConfig(
                enabled=False,  # Opt-in by default
                service_name=self.service_name,
            )
            self._telemetry = TelemetrySystem(config)
        except ImportError:
            logger.debug("Telemetry module not available")
            self._telemetry = None

    @property
    def is_available(self) -> bool:
        """Check if telemetry integration is available."""
        return self._telemetry is not None

    @property
    def is_enabled(self) -> bool:
        """Check if telemetry is enabled."""
        if not self._telemetry:
            return False
        return getattr(self._telemetry, 'is_enabled', False)

    @contextmanager
    def subagent_span(
        self,
        subagent_name: str,
        stage: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """
        Create a tracing span for subagent execution.

        Args:
            subagent_name: Name of the subagent
            stage: Pipeline stage name
            **attributes: Additional span attributes

        Yields:
            Span object (or NullSpan if disabled)
        """
        if not self._telemetry:
            yield _NullSpan()
            return

        operation_name = f"subagent.{subagent_name}.{stage}"
        with self._telemetry.span(
            operation_name,
            phase="agentic",
            attributes={
                "subagent.name": subagent_name,
                "subagent.stage": stage,
                **attributes,
            },
        ) as span:
            yield span

    @contextmanager
    def hook_span(
        self,
        hook_name: str,
        hook_type: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """
        Create a tracing span for hook execution.

        Args:
            hook_name: Name of the hook
            hook_type: Type of hook (pre_tool_use, post_tool_use)
            **attributes: Additional span attributes

        Yields:
            Span object (or NullSpan if disabled)
        """
        if not self._telemetry:
            yield _NullSpan()
            return

        operation_name = f"hook.{hook_name}"
        with self._telemetry.span(
            operation_name,
            phase="governance",
            attributes={
                "hook.name": hook_name,
                "hook.type": hook_type,
                **attributes,
            },
        ) as span:
            yield span

    @contextmanager
    def orchestrator_span(
        self,
        company_name: str,
        mode: str,
        **attributes: Any,
    ) -> Generator[Any, None, None]:
        """
        Create a tracing span for orchestrator execution.

        Args:
            company_name: Company being researched
            mode: Research mode
            **attributes: Additional span attributes

        Yields:
            Span object (or NullSpan if disabled)
        """
        if not self._telemetry:
            yield _NullSpan()
            return

        operation_name = "orchestrator.research"
        with self._telemetry.span(
            operation_name,
            phase="orchestration",
            attributes={
                "company.name": company_name,
                "research.mode": mode,
                **attributes,
            },
        ) as span:
            yield span

    def record_subagent_result(
        self,
        span: Any,
        result: SubagentResult,
    ) -> None:
        """
        Record subagent result attributes on span.

        Args:
            span: Span to record on
            result: Subagent result
        """
        if span is None or isinstance(span, _NullSpan):
            return

        try:
            span.set_attribute("subagent.status", result.status.value)
            span.set_attribute("subagent.success", result.is_success)

            if result.error:
                span.set_attribute("subagent.error", result.error)

            for key, value in result.metrics.items():
                span.set_attribute(f"subagent.metric.{key}", value)
        except Exception as e:
            logger.debug(f"Failed to record span attributes: {e}")


class _NullSpan:
    """Null span for when telemetry is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op."""

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        """No-op."""

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op."""


# =============================================================================
# CIRCUIT BREAKER INTEGRATION
# =============================================================================

@dataclass
class CircuitBreakerIntegration:
    """
    Circuit breaker integration for subagent fault tolerance.

    Wraps subagent execution with circuit breaker protection to prevent
    cascading failures when external services are unavailable.

    Attributes:
        _breaker: CircuitBreaker instance

    Example:
        cb = CircuitBreakerIntegration()

        if cb.can_execute("scraper"):
            try:
                result = await scraper.execute()
                cb.record_success("scraper")
            except Exception as e:
                cb.record_failure("scraper")
                raise

    Requirements: 8.5
    """

    _breaker: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize circuit breaker."""
        try:
            from primr.utils.circuit_breaker import CircuitBreaker
            self._breaker = CircuitBreaker(name="agentic")
        except ImportError:
            logger.debug("Circuit breaker module not available")
            self._breaker = None

    @property
    def is_available(self) -> bool:
        """Check if circuit breaker integration is available."""
        return self._breaker is not None

    def can_execute(self, key: str) -> bool:
        """
        Check if execution is allowed for a key.

        Args:
            key: Circuit key (e.g., subagent name)

        Returns:
            True if circuit is closed or half-open
        """
        if not self._breaker:
            return True  # Allow if not available

        result: bool = self._breaker.can_execute(key)
        return result

    def record_success(self, key: str) -> None:
        """
        Record a successful execution.

        Args:
            key: Circuit key
        """
        if self._breaker:
            self._breaker.record_success(key)

    def record_failure(self, key: str) -> None:
        """
        Record a failed execution.

        Args:
            key: Circuit key
        """
        if self._breaker:
            self._breaker.record_failure(key)

    def get_state(self, key: str) -> str:
        """
        Get circuit state for a key.

        Args:
            key: Circuit key

        Returns:
            State name ("closed", "open", "half_open") or "unknown"
        """
        if not self._breaker:
            return "unknown"

        try:
            state = self._breaker.get_state(key)
            state_value: str = state.value
            return state_value
        except Exception as e:
            logger.warning("Failed to get circuit state for key=%s: %s", key, e)
            return "unknown"

    def reset(self, key: str) -> None:
        """
        Reset circuit for a key.

        Args:
            key: Circuit key
        """
        if self._breaker:
            self._breaker.reset(key)

    @asynccontextmanager
    async def protected_execution(
        self,
        key: str,
    ) -> AsyncGenerator[bool, None]:
        """
        Context manager for circuit-breaker-protected execution.

        Args:
            key: Circuit key

        Yields:
            True if execution is allowed

        Example:
            async with cb.protected_execution("scraper") as allowed:
                if allowed:
                    result = await scraper.execute()
        """
        if not self.can_execute(key):
            logger.warning(f"Circuit open for {key}, skipping execution")
            yield False
            return

        try:
            yield True
            self.record_success(key)
        except Exception:
            self.record_failure(key)
            raise


# =============================================================================
# COMBINED INTEGRATION
# =============================================================================

@dataclass
class AgenticIntegration:
    """
    Combined integration for all agentic infrastructure.

    Provides a single entry point for state machine, telemetry, and
    circuit breaker integration.

    Attributes:
        job_id: Job identifier for state machine
        state_machine: State machine adapter
        telemetry: Telemetry integration
        circuit_breaker: Circuit breaker integration

    Example:
        integration = AgenticIntegration(job_id="research-123")

        with integration.telemetry.orchestrator_span("Acme", "full"):
            integration.state_machine.transition_to(OrchestratorState.SCRAPING)

            async with integration.circuit_breaker.protected_execution("scraper"):
                result = await scraper.execute()

    Requirements: 8.2, 8.4, 8.5
    """

    job_id: str = ""
    state_machine: OrchestratorStateMachineAdapter | None = field(default=None)
    telemetry: TelemetryIntegration | None = field(default=None)
    circuit_breaker: CircuitBreakerIntegration | None = field(default=None)

    def __post_init__(self) -> None:
        """Initialize all integrations."""
        if self.state_machine is None:
            self.state_machine = OrchestratorStateMachineAdapter(
                job_id=self.job_id or "default"
            )
        if self.telemetry is None:
            self.telemetry = TelemetryIntegration()
        if self.circuit_breaker is None:
            self.circuit_breaker = CircuitBreakerIntegration()

    @property
    def all_available(self) -> bool:
        """Check if all integrations are available."""
        return (
            self.state_machine is not None
            and self.state_machine.is_available
            and self.telemetry is not None
            and self.telemetry.is_available
            and self.circuit_breaker is not None
            and self.circuit_breaker.is_available
        )

    def get_status(self) -> dict[str, bool]:
        """
        Get availability status of all integrations.

        Returns:
            Dict mapping integration name to availability
        """
        return {
            "state_machine": self.state_machine.is_available if self.state_machine else False,
            "telemetry": self.telemetry.is_available if self.telemetry else False,
            "circuit_breaker": self.circuit_breaker.is_available if self.circuit_breaker else False,
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "AgenticIntegration",
    "CircuitBreakerIntegration",
    "OrchestratorStateMachineAdapter",
    "TelemetryIntegration",
]
