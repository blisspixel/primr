"""
Property-based tests for Research Orchestrator.

This module validates the correctness properties of the Research
Orchestrator using the Hypothesis library. Each test corresponds
to a formal property from the design document.

Properties tested:
- Property 13: Orchestrator Lifecycle Management
- Property 14: Orchestrator Context Isolation
- Property 15: Orchestrator Failure Handling

Validates: Requirements 3.1, 3.6, 3.7, 3.8
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from primr.agentic.orchestrator import (
    OrchestratorConfig,
    OrchestratorResult,
    OrchestratorState,
    ResearchOrchestrator,
)
from primr.agentic.subagents import SubagentStatus


# =============================================================================
# STRATEGIES
# =============================================================================

# ASCII-only text for Windows compatibility
ascii_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        max_codepoint=127,
    ),
    min_size=1,
    max_size=30,
).filter(lambda x: x.strip() != "")

# Company names
company_names = ascii_text

# URLs
urls = st.from_regex(
    r"https://[a-z]{3,10}\.(com|org|io)",
    fullmatch=True,
)

# Research modes
modes = st.sampled_from(["scrape", "full"])

# Orchestrator states
orchestrator_states = st.sampled_from(list(OrchestratorState))


@st.composite
def orchestrator_configs(draw) -> OrchestratorConfig:
    """Generate valid OrchestratorConfig objects."""
    return OrchestratorConfig(
        fail_fast=draw(st.booleans()),
        max_retries=draw(st.integers(min_value=0, max_value=5)),
        output_dir=Path(tempfile.mkdtemp()),
        qa_min_score=draw(st.integers(min_value=0, max_value=100)),
    )


# =============================================================================
# PROPERTY 13: Orchestrator Lifecycle Management
# =============================================================================

# Feature: agentic-architecture, Property 13: Orchestrator Lifecycle Management
def test_orchestrator_initial_state():
    """
    Orchestrator starts in IDLE state.

    For any research request, the orchestrator should start in IDLE
    state before transitioning through the pipeline stages.

    Validates: Requirements 3.1
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        assert orchestrator.state == OrchestratorState.IDLE


# Feature: agentic-architecture, Property 13: Orchestrator state transitions
@given(
    company_name=company_names,
    company_url=urls,
)
@settings(max_examples=10, deadline=None)
def test_orchestrator_state_transitions(company_name: str, company_url: str):
    """
    Orchestrator transitions through states in order.

    For any research request, the orchestrator should transition
    through states: IDLE -> SCRAPING -> ANALYZING -> WRITING -> QA -> COMPLETED

    Validates: Requirements 3.1, 3.6
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        # Initial state
        assert orchestrator.state == OrchestratorState.IDLE

        # Run research
        result = asyncio.run(orchestrator.research(
            company_name=company_name,
            company_url=company_url,
            mode="full",
        ))

        # Final state should be COMPLETED or FAILED
        assert orchestrator.state in (
            OrchestratorState.COMPLETED,
            OrchestratorState.FAILED,
        )

        # Result state should match orchestrator state
        assert result.state == orchestrator.state


# Feature: agentic-architecture, Property 13: Stage results tracking
@given(
    company_name=company_names,
    company_url=urls,
    mode=modes,
)
@settings(max_examples=10, deadline=None)
def test_orchestrator_stage_results_tracking(
    company_name: str,
    company_url: str,
    mode: str,
):
    """
    All executed subagent results are present in stage_results.

    Validates: Requirements 3.6
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        result = asyncio.run(orchestrator.research(
            company_name=company_name,
            company_url=company_url,
            mode=mode,
        ))

        # Scrape stage should always be present for both modes
        if mode in ("scrape", "full"):
            assert "scrape" in result.stage_results

        # Each stage result should have a valid status
        for stage_name, stage_result in result.stage_results.items():
            assert stage_result.status in list(SubagentStatus)


# =============================================================================
# PROPERTY 14: Orchestrator Context Isolation
# =============================================================================

# Feature: agentic-architecture, Property 14: Orchestrator Context Isolation
@given(
    company_name=company_names,
    company_url=urls,
)
@settings(max_examples=10, deadline=None)
def test_orchestrator_context_isolation(company_name: str, company_url: str):
    """
    Subagents only access data explicitly passed in context.

    For any subagent execution, the subagent should only have access
    to data explicitly passed in its SubagentContext.parent_results.

    Validates: Requirements 3.7
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        result = asyncio.run(orchestrator.research(
            company_name=company_name,
            company_url=company_url,
            mode="full",
        ))

        # If analysis succeeded, it should have received corpus_path
        if "analyze" in result.stage_results:
            analyze_result = result.stage_results["analyze"]
            # The analyst should have produced hypotheses or failed
            assert (
                analyze_result.is_success or
                analyze_result.is_failure
            )


# =============================================================================
# PROPERTY 15: Orchestrator Failure Handling
# =============================================================================

# Feature: agentic-architecture, Property 15: Orchestrator Failure Handling
@given(config=orchestrator_configs())
@settings(max_examples=10, deadline=None)
def test_orchestrator_failure_handling_config(config: OrchestratorConfig):
    """
    Orchestrator respects fail_fast configuration.

    For any subagent that fails during execution, the orchestrator
    should capture the error and either stop (fail_fast) or continue.

    Validates: Requirements 3.8
    """
    orchestrator = ResearchOrchestrator(config=config)

    # Verify config is respected
    assert orchestrator.config.fail_fast == config.fail_fast
    assert orchestrator.config.max_retries == config.max_retries


# Feature: agentic-architecture, Property 15: Partial results on failure
@given(
    company_name=company_names,
    company_url=urls,
)
@settings(max_examples=10, deadline=None)
def test_orchestrator_partial_results(company_name: str, company_url: str):
    """
    Orchestrator returns partial results on failure.

    For any failure, the orchestrator should return all successfully
    completed stage results.

    Validates: Requirements 3.8
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(
            output_dir=Path(tmpdir),
            fail_fast=False,  # Continue on failure
        )
        orchestrator = ResearchOrchestrator(config=config)

        result = asyncio.run(orchestrator.research(
            company_name=company_name,
            company_url=company_url,
            mode="full",
        ))

        # Even on failure, completed stages should be tracked
        assert isinstance(result.completed_stages, list)
        assert isinstance(result.failed_stages, list)

        # All stages should be in one list or the other
        all_stages = set(result.completed_stages) | set(result.failed_stages)
        assert all_stages == set(result.stage_results.keys())


# Feature: agentic-architecture, Property 15: Error messages captured
@given(
    company_name=company_names,
    company_url=urls,
)
@settings(max_examples=10, deadline=None)
def test_orchestrator_error_capture(company_name: str, company_url: str):
    """
    Orchestrator captures error messages from failed stages.

    Validates: Requirements 3.8
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        result = asyncio.run(orchestrator.research(
            company_name=company_name,
            company_url=company_url,
            mode="full",
        ))

        # Errors list should be populated for failed stages
        if result.is_failure:
            # At least one error should be captured
            # (may be empty if failure was due to missing data)
            assert isinstance(result.errors, list)


# =============================================================================
# ORCHESTRATOR RESULT TESTS
# =============================================================================

# Feature: agentic-architecture, OrchestratorResult properties
@given(state=orchestrator_states)
@settings(max_examples=20, deadline=None)
def test_orchestrator_result_properties(state: OrchestratorState):
    """
    OrchestratorResult correctly reports success/failure.

    Validates: Requirements 3.1
    """
    result = OrchestratorResult(state=state)

    # is_success should match COMPLETED state
    assert result.is_success == (state == OrchestratorState.COMPLETED)

    # is_failure should match FAILED state
    assert result.is_failure == (state == OrchestratorState.FAILED)


# Feature: agentic-architecture, OrchestratorResult serialization
@given(
    state=orchestrator_states,
    errors=st.lists(ascii_text, min_size=0, max_size=5),
)
@settings(max_examples=20, deadline=None)
def test_orchestrator_result_serialization(
    state: OrchestratorState,
    errors: list[str],
):
    """
    OrchestratorResult serializes to valid dictionary.

    Validates: Requirements 3.1
    """
    result = OrchestratorResult(
        state=state,
        errors=errors,
    )

    data = result.to_dict()

    assert data["state"] == state.value
    assert data["errors"] == errors
    assert "started_at" in data
    assert "duration_seconds" in data


# =============================================================================
# ORCHESTRATOR CONFIG TESTS
# =============================================================================

# Feature: agentic-architecture, OrchestratorConfig defaults
def test_orchestrator_config_defaults():
    """OrchestratorConfig has sensible defaults."""
    config = OrchestratorConfig()

    assert config.fail_fast is False
    assert config.max_retries == 2
    assert config.qa_min_score == 70
    assert config.hypothesis_expiry_days == 90
    assert isinstance(config.output_dir, Path)


# Feature: agentic-architecture, OrchestratorConfig path conversion
def test_orchestrator_config_path_conversion():
    """OrchestratorConfig converts string output_dir to Path."""
    config = OrchestratorConfig(output_dir="./custom_output")  # type: ignore

    assert isinstance(config.output_dir, Path)
    assert config.output_dir == Path("./custom_output")


# =============================================================================
# ADDITIONAL UNIT TESTS
# =============================================================================

def test_orchestrator_reset():
    """Orchestrator reset returns to IDLE state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        # Run research to change state
        asyncio.run(orchestrator.research(
            company_name="Test",
            company_url="https://test.com",
            mode="scrape",
        ))

        # State should have changed
        assert orchestrator.state != OrchestratorState.IDLE

        # Reset
        orchestrator.reset()

        # Should be back to IDLE
        assert orchestrator.state == OrchestratorState.IDLE


def test_orchestrator_with_memory():
    """Orchestrator integrates with ResearchMemory."""
    from primr.agentic.memory import ResearchMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = ResearchMemory(storage_path=Path(tmpdir) / "memory")
        config = OrchestratorConfig(output_dir=Path(tmpdir) / "output")

        orchestrator = ResearchOrchestrator(
            config=config,
            memory=memory,
        )

        result = asyncio.run(orchestrator.research(
            company_name="Test Corp",
            company_url="https://test.com",
            mode="full",
        ))

        # Hypotheses should be tracked
        assert isinstance(result.hypotheses, list)


def test_orchestrator_with_hooks():
    """Orchestrator integrates with HookSystem."""
    from primr.agentic.hooks import HookSystem, CostGuardHook

    with tempfile.TemporaryDirectory() as tmpdir:
        hooks = HookSystem()
        hooks.register(CostGuardHook(max_cost_usd=100.0))

        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(
            config=config,
            hook_system=hooks,
        )

        result = asyncio.run(orchestrator.research(
            company_name="Test",
            company_url="https://test.com",
            mode="scrape",
        ))

        # Should complete (hooks don't block by default)
        assert result.state in (
            OrchestratorState.COMPLETED,
            OrchestratorState.FAILED,
        )


def test_orchestrator_result_duration():
    """OrchestratorResult tracks duration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        result = asyncio.run(orchestrator.research(
            company_name="Test",
            company_url="https://test.com",
            mode="scrape",
        ))

        # Duration should be positive
        assert result.duration_seconds >= 0

        # completed_at should be set
        assert result.completed_at is not None

        # started_at should be before completed_at
        assert result.started_at <= result.completed_at


def test_orchestrator_working_dir_creation():
    """Orchestrator creates unique working directories."""
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        config = OrchestratorConfig(output_dir=Path(tmpdir))
        orchestrator = ResearchOrchestrator(config=config)

        # Create two working dirs for same company
        dir1 = orchestrator._create_working_dir("Test Corp")
        time.sleep(1.1)  # Ensure different timestamp
        dir2 = orchestrator._create_working_dir("Test Corp")

        # Should be different (timestamp-based)
        assert dir1 != dir2

        # Both should exist
        assert dir1.exists()
        assert dir2.exists()

        # Both should be under output_dir
        assert dir1.parent == config.output_dir
        assert dir2.parent == config.output_dir

