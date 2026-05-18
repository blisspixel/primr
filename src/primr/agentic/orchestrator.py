"""
Research Orchestrator for coordinating subagent execution.

This module implements the ResearchOrchestrator, which coordinates
the execution of specialized subagents through the research pipeline
with context isolation, hook integration, and memory persistence.

Key Responsibilities:
    - Coordinate subagent lifecycle (scrape -> analyze -> write -> qa)
    - Manage context derivation between stages
    - Integrate with hook system for governance
    - Persist research state to memory
    - Handle failures with partial result recovery

Design Principles:
    - Context Isolation: Each subagent gets only the data it needs
    - Fail-Safe: Partial results preserved on failure
    - Observable: Hooks enable monitoring and policy enforcement
    - Stateful: Memory enables cross-session learning

Example:
    from primr.agentic import ResearchOrchestrator, ResearchMemory, HookSystem

    memory = ResearchMemory()
    hooks = HookSystem()
    hooks.register(CostGuardHook(max_cost_usd=5.0))

    orchestrator = ResearchOrchestrator(
        memory=memory,
        hook_system=hooks,
    )

    result = await orchestrator.research(
        company_name="Acme Corp",
        company_url="https://acme.com",
        mode="full",
    )

    if result.state == OrchestratorState.COMPLETED:
        print(f"Report: {result.report_path}")
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any

from primr.agentic.errors import OrchestratorError, SubagentError

# Type alias for user input callback (v1.11.0)
# Signature: (prompt: str, options: list[str] | None) -> Awaitable[str]
UserInputCallback = Callable[[str, list[str] | None], Awaitable[str]]
from primr.agentic.subagents import (
    AnalystSubagent,
    QASubagent,
    ScraperSubagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
    VerifierSubagent,
    WriterSubagent,
)

if TYPE_CHECKING:
    from primr.agentic.hooks import HookSystem
    from primr.agentic.memory import ResearchMemory
    from primr.agentic.models import Hypothesis

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class OrchestratorState(Enum):
    """
    State of the research orchestrator.

    State transitions:
        IDLE -> SCRAPING -> ANALYZING -> WRITING -> QA -> COMPLETED
        Any state -> FAILED (on error)
        Any active state -> PAUSED (v1.11.0 interactive mode)
        PAUSED -> previous state (on resume)

    Attributes:
        IDLE: Orchestrator created but not started
        SCRAPING: Executing scraper subagent
        ANALYZING: Executing analyst subagent
        WRITING: Executing writer subagent
        QA: Executing QA subagent
        COMPLETED: All stages completed successfully
        FAILED: One or more stages failed
        PAUSED: Execution paused, awaiting user input (v1.11.0)
    """

    IDLE = "idle"
    SCRAPING = "scraping"
    ANALYZING = "analyzing"
    WRITING = "writing"
    QA = "qa"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class OrchestratorConfig:
    """
    Configuration for the research orchestrator.

    Attributes:
        fail_fast: Stop on first subagent failure (default: False)
        max_retries: Maximum retries per stage (default: 2)
        output_dir: Base directory for output (default: ./output)
        qa_min_score: Minimum QA score to pass (default: 70)
        hypothesis_expiry_days: Days until hypotheses expire (default: 90)
        enable_interactive: Enable interactive mode with pause/resume (v1.11.0)
        user_input_callback: Callback to request user input (v1.11.0)
        pause_on_error: Pause and ask user on recoverable errors (v1.11.0)
        pause_between_stages: Pause between stages for user confirmation (v1.11.0)

    Example:
        config = OrchestratorConfig(
            fail_fast=True,
            max_retries=3,
            qa_min_score=80,
        )

        # v1.11.0 Interactive mode example
        async def get_user_input(prompt: str, options: list[str] | None) -> str:
            return input(prompt)

        interactive_config = OrchestratorConfig(
            enable_interactive=True,
            user_input_callback=get_user_input,
            pause_on_error=True,
        )
    """

    fail_fast: bool = False
    max_retries: int = 2
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    qa_min_score: int = 70
    hypothesis_expiry_days: int = 90
    enable_verification: bool = False
    # v1.11.0 Interactive mode settings
    enable_interactive: bool = False
    user_input_callback: UserInputCallback | None = None
    pause_on_error: bool = False
    pause_between_stages: bool = False

    def __post_init__(self) -> None:
        """Ensure output_dir is a Path and validate interactive settings."""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        # Validate interactive mode requirements
        if self.enable_interactive and self.user_input_callback is None:
            logger.warning(
                "Interactive mode enabled but no user_input_callback provided. "
                "Interactive features will be disabled."
            )
            self.enable_interactive = False


# =============================================================================
# RESULT
# =============================================================================


@dataclass
class OrchestratorResult:
    """
    Result from orchestrator execution.

    Attributes:
        state: Final state of the orchestrator
        report_path: Path to generated report (if successful)
        hypotheses: All hypotheses (prior + generated)
        stage_results: Results from each stage
        errors: List of error messages
        started_at: When execution started
        completed_at: When execution completed
        duration_seconds: Total execution time
        paused_at_stage: Stage where execution was paused (v1.11.0)
        user_decisions: Record of user decisions during interactive mode (v1.11.0)

    Example:
        result = await orchestrator.research(company, url)

        if result.state == OrchestratorState.COMPLETED:
            print(f"Report: {result.report_path}")
            print(f"Hypotheses: {len(result.hypotheses)}")
        else:
            for error in result.errors:
                print(f"Error: {error}")
    """

    state: OrchestratorState
    report_path: Path | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    stage_results: dict[str, SubagentResult[Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    # v1.11.0 Interactive mode
    paused_at_stage: str | None = None
    user_decisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Check if orchestration completed successfully."""
        return self.state == OrchestratorState.COMPLETED

    @property
    def is_failure(self) -> bool:
        """Check if orchestration failed."""
        return self.state == OrchestratorState.FAILED

    @property
    def is_paused(self) -> bool:
        """Check if orchestration is paused (v1.11.0)."""
        return self.state == OrchestratorState.PAUSED

    @property
    def completed_stages(self) -> list[str]:
        """Get list of successfully completed stages."""
        return [
            name
            for name, result in self.stage_results.items()
            if result.status == SubagentStatus.COMPLETED
        ]

    @property
    def failed_stages(self) -> list[str]:
        """Get list of failed stages."""
        return [
            name
            for name, result in self.stage_results.items()
            if result.status == SubagentStatus.FAILED
        ]

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "state": self.state.value,
            "report_path": str(self.report_path) if self.report_path else None,
            "hypothesis_count": len(self.hypotheses),
            "completed_stages": self.completed_stages,
            "failed_stages": self.failed_stages,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "paused_at_stage": self.paused_at_stage,
            "user_decisions": self.user_decisions,
        }


# =============================================================================
# ORCHESTRATOR
# =============================================================================


class ResearchOrchestrator:
    """
    Coordinates subagent execution with context isolation.

    The orchestrator manages the research pipeline, coordinating
    specialized subagents through distinct phases:

    1. Scraping: Extract content from company website
    2. Analysis: Generate insights and hypotheses
    3. Writing: Create research report
    4. QA: Assess report quality

    Features:
        - Context Isolation: Each subagent gets minimal required context
        - Hook Integration: Pre/post hooks for governance
        - Memory Persistence: Cross-session hypothesis tracking
        - Failure Handling: Partial results on failure

    Example:
        orchestrator = ResearchOrchestrator(
            config=OrchestratorConfig(fail_fast=True),
            memory=ResearchMemory(),
            hook_system=HookSystem(),
        )

        result = await orchestrator.research(
            company_name="Acme Corp",
            company_url="https://acme.com",
        )
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        memory: ResearchMemory | None = None,
        hook_system: HookSystem | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            config: Orchestrator configuration
            memory: Research memory for persistence
            hook_system: Hook system for governance
        """
        self._config = config or OrchestratorConfig()
        self._memory = memory
        self._hooks = hook_system
        self._state = OrchestratorState.IDLE
        self._working_dir_sequence = 0
        # v1.11.0 Interactive mode state
        self._paused_at_stage: str | None = None
        self._previous_state: OrchestratorState | None = None
        self._user_decisions: list[dict[str, Any]] = []

    @property
    def state(self) -> OrchestratorState:
        """Get current orchestrator state."""
        return self._state

    @property
    def config(self) -> OrchestratorConfig:
        """Get orchestrator configuration."""
        return self._config

    @property
    def is_interactive(self) -> bool:
        """Check if interactive mode is enabled (v1.11.0)."""
        return self._config.enable_interactive

    @property
    def user_decisions(self) -> list[dict[str, Any]]:
        """Get record of user decisions (v1.11.0)."""
        return list(self._user_decisions)

    async def _request_user_input(
        self,
        prompt: str,
        options: list[str] | None = None,
        context: str | None = None,
    ) -> str:
        """
        Request input from user via callback (v1.11.0).

        Args:
            prompt: Question or prompt for the user
            options: Optional list of valid options
            context: Optional context information

        Returns:
            User's response string

        Raises:
            OrchestratorError: If interactive mode not available
        """
        if not self._config.enable_interactive or not self._config.user_input_callback:
            raise OrchestratorError(
                message="Interactive mode not available",
                state=self._state.value,
                completed_stages=[],
            )

        full_prompt = prompt
        if context:
            full_prompt = f"{context}\n\n{prompt}"

        response = await self._config.user_input_callback(full_prompt, options)

        # Record the decision
        self._user_decisions.append(
            {
                "prompt": prompt,
                "options": options,
                "response": response,
                "timestamp": datetime.now().isoformat(),
                "stage": self._state.value,
            }
        )

        return response

    async def _handle_stage_transition(
        self,
        from_stage: str,
        to_stage: str,
    ) -> bool:
        """
        Handle transition between stages with optional pause (v1.11.0).

        Args:
            from_stage: Stage just completed
            to_stage: Stage about to start

        Returns:
            True to continue, False to abort
        """
        if not self._config.pause_between_stages:
            return True

        if not self._config.enable_interactive:
            return True

        try:
            response = await self._request_user_input(
                prompt=f"Continue to {to_stage} stage?",
                options=["continue", "skip", "abort"],
                context=f"Completed: {from_stage}",
            )

            response = response.lower().strip()
            if response == "abort":
                return False
            # "continue" or "skip" both proceed

        except Exception as e:
            logger.warning(f"User input failed during stage transition: {e}")
            # Default to continue on error

        return True

    async def _handle_error_recovery(
        self,
        stage_name: str,
        error: Exception,
        retry_count: int,
    ) -> str:
        """
        Handle error with optional user input (v1.11.0).

        Args:
            stage_name: Stage where error occurred
            error: The exception that was raised
            retry_count: Current retry attempt number

        Returns:
            Recovery action: "retry", "skip", or "abort"
        """
        # First, run error recovery hooks if available
        if self._hooks:
            from primr.agentic.hooks import HookContext, HookResult, HookType

            recovery_context = HookContext(
                hook_type=HookType.ERROR_RECOVERY,
                stage_name=stage_name,
                arguments={
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "retry_count": retry_count,
                },
                user_input_callback=self._config.user_input_callback,
            )
            response = await self._hooks.run_error_recovery_hooks(
                stage_name, error, recovery_context
            )

            if response.result == HookResult.ALLOW:
                return "retry"
            elif response.result == HookResult.WARN:
                return "skip"
            # BLOCK falls through to user input or default

        # Ask user if interactive and pause_on_error is enabled
        if self._config.pause_on_error and self._config.enable_interactive:
            try:
                user_choice = await self._request_user_input(
                    prompt=f"Error in {stage_name}: {error}\n\nHow should we proceed?",
                    options=["retry", "skip", "abort"],
                    context=f"Retry attempt: {retry_count}/{self._config.max_retries}",
                )
                return user_choice.lower().strip()
            except Exception as e:
                logger.warning(f"User input failed during error recovery: {e}")

        # Default behavior: abort on fail_fast, otherwise skip
        return "abort" if self._config.fail_fast else "skip"

    def pause(self) -> bool:
        """
        Pause orchestrator execution (v1.11.0).

        Can only pause from an active state.

        Returns:
            True if paused successfully, False otherwise
        """
        active_states = {
            OrchestratorState.SCRAPING,
            OrchestratorState.ANALYZING,
            OrchestratorState.WRITING,
            OrchestratorState.QA,
            OrchestratorState.VERIFYING,
        }

        if self._state in active_states:
            self._previous_state = self._state
            self._paused_at_stage = self._state.value
            self._state = OrchestratorState.PAUSED
            logger.info(f"Orchestrator paused at stage: {self._paused_at_stage}")
            return True

        return False

    def resume(self) -> bool:
        """
        Resume orchestrator execution from paused state (v1.11.0).

        Returns:
            True if resumed successfully, False otherwise
        """
        if self._state == OrchestratorState.PAUSED and self._previous_state:
            self._state = self._previous_state
            logger.info(f"Orchestrator resumed to state: {self._state.value}")
            self._previous_state = None
            return True

        return False

    async def research(
        self,
        company_name: str,
        company_url: str,
        mode: str = "full",
    ) -> OrchestratorResult:
        """
        Execute research pipeline with subagent coordination.

        Args:
            company_name: Name of the company to research
            company_url: Primary URL for the company
            mode: Research mode ("scrape", "full")

        Returns:
            OrchestratorResult with final state and results

        Raises:
            OrchestratorError: If orchestration fails catastrophically
        """
        start_time = time.time()
        started_at = datetime.now()

        logger.info(f"Starting research for {company_name} (url={company_url}, mode={mode})")

        # Reset interactive state from any prior run
        self._paused_at_stage = None
        self._previous_state = None
        self._user_decisions = []

        # Load prior hypotheses from memory
        prior_hypotheses: list[Hypothesis] = []
        if self._memory:
            try:
                prior_hypotheses = self._memory.get_hypotheses(company_name)
                logger.debug(f"Loaded {len(prior_hypotheses)} prior hypotheses")
            except Exception as e:
                logger.warning(f"Failed to load prior hypotheses: {e}")

        # Create working directory
        working_dir = self._create_working_dir(company_name)

        # Create base context
        base_context = SubagentContext(
            company_name=company_name,
            company_url=company_url,
            working_dir=working_dir,
            prior_hypotheses=prior_hypotheses,
            config={
                "qa_min_score": self._config.qa_min_score,
                "hypothesis_expiry_days": self._config.hypothesis_expiry_days,
            },
        )

        # Initialize result tracking
        stage_results: dict[str, SubagentResult[Any]] = {}
        all_hypotheses: list[Hypothesis] = list(prior_hypotheses)
        errors: list[str] = []
        report_path: Path | None = None

        try:
            # Stage 1: Scraping
            if mode in ("scrape", "full"):
                self._state = OrchestratorState.SCRAPING
                scrape_result = await self._execute_stage(
                    "scrape",
                    ScraperSubagent(base_context),
                )
                stage_results["scrape"] = scrape_result

                if scrape_result.is_failure:
                    errors.append(f"Scrape failed: {scrape_result.error}")
                    if self._config.fail_fast:
                        raise SubagentError(
                            message=scrape_result.error or "Scrape failed",
                            subagent="scraper",
                            stage="scrape",
                        )

            # Stage 2: Analysis
            if mode in ("scrape", "full") and "scrape" in stage_results:
                scrape_data = stage_results["scrape"].data
                if scrape_data:
                    self._state = OrchestratorState.ANALYZING
                    analyst_context = self._derive_context(
                        base_context,
                        corpus_path=scrape_data.corpus_path,
                    )
                    analyze_result = await self._execute_stage(
                        "analyze",
                        AnalystSubagent(analyst_context),
                    )
                    stage_results["analyze"] = analyze_result

                    # Accumulate hypotheses even from partial failures
                    if analyze_result.hypotheses:
                        all_hypotheses.extend(analyze_result.hypotheses)
                    if analyze_result.is_failure:
                        errors.append(f"Analysis failed: {analyze_result.error}")
                        if self._config.fail_fast:
                            raise SubagentError(
                                message=analyze_result.error or "Analysis failed",
                                subagent="analyst",
                                stage="analyze",
                            )

            # Stage 3: Writing (full mode only)
            if mode == "full" and "analyze" in stage_results:
                analyze_data = stage_results["analyze"].data
                if analyze_data:
                    self._state = OrchestratorState.WRITING
                    writer_context = self._derive_context(
                        base_context,
                        insights_path=analyze_data.insights_path,
                        hypotheses=all_hypotheses,
                    )
                    write_result = await self._execute_stage(
                        "write",
                        WriterSubagent(writer_context),
                    )
                    stage_results["write"] = write_result

                    if write_result.is_success and write_result.data:
                        report_path = write_result.data.report_path
                    elif write_result.is_failure:
                        errors.append(f"Writing failed: {write_result.error}")
                        if self._config.fail_fast:
                            raise SubagentError(
                                message=write_result.error or "Writing failed",
                                subagent="writer",
                                stage="write",
                            )

            # Stage 4: QA
            if report_path:
                self._state = OrchestratorState.QA
                qa_context = self._derive_context(
                    base_context,
                    report_path=report_path,
                )
                qa_result = await self._execute_stage(
                    "qa",
                    QASubagent(qa_context, min_score=self._config.qa_min_score),
                )
                stage_results["qa"] = qa_result

                if qa_result.is_failure:
                    errors.append(f"QA failed: {qa_result.error}")

            # Stage 5: Verification (optional, non-blocking)
            if report_path and self._config.enable_verification:
                self._state = OrchestratorState.VERIFYING
                verify_context = self._derive_context(
                    base_context,
                    report_path=report_path,
                )
                try:
                    verify_result = await self._execute_stage(
                        "verify",
                        VerifierSubagent(verify_context),
                    )
                    stage_results["verify"] = verify_result

                    if verify_result.is_failure:
                        logger.warning(
                            f"Verification failed for {company_name}: {verify_result.error}"
                        )
                    elif verify_result.is_success and verify_result.data:
                        logger.info(
                            f"Verification complete for {company_name}: "
                            f"trust={verify_result.data.trust_percentage}%"
                        )
                except Exception as e:
                    logger.warning(f"Verification stage failed: {e}")

            # Persist hypotheses to memory
            if self._memory and all_hypotheses:
                try:
                    self._memory.save_hypotheses(company_name, all_hypotheses)
                    logger.debug(f"Saved {len(all_hypotheses)} hypotheses to memory")
                except Exception as e:
                    logger.warning(f"Failed to save hypotheses: {e}")

            # Determine final state
            if errors:
                self._state = OrchestratorState.FAILED
            else:
                self._state = OrchestratorState.COMPLETED

            duration = time.time() - start_time
            completed_at = datetime.now()

            logger.info(
                f"Research completed for {company_name}: "
                f"state={self._state.value}, duration={duration:.1f}s"
            )

            return OrchestratorResult(
                state=self._state,
                report_path=report_path,
                hypotheses=all_hypotheses,
                stage_results=stage_results,
                errors=errors,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                paused_at_stage=self._paused_at_stage,
                user_decisions=list(self._user_decisions),
            )

        except SubagentError as e:
            duration = time.time() - start_time
            self._state = OrchestratorState.FAILED

            logger.error(f"Research failed for {company_name}: {e}")

            return OrchestratorResult(
                state=self._state,
                hypotheses=all_hypotheses,
                stage_results=stage_results,
                errors=[*errors, str(e)],
                started_at=started_at,
                completed_at=datetime.now(),
                duration_seconds=duration,
                paused_at_stage=self._paused_at_stage,
                user_decisions=list(self._user_decisions),
            )

        except Exception as e:
            duration = time.time() - start_time
            self._state = OrchestratorState.FAILED

            logger.error(f"Unexpected error during research: {e}")

            raise OrchestratorError(
                message=str(e),
                state=self._state.value,
                completed_stages=list(stage_results.keys()),
            ) from e

    async def _execute_stage(
        self,
        stage_name: str,
        subagent: Any,
    ) -> SubagentResult[Any]:
        """
        Execute a subagent with hook integration.

        Args:
            stage_name: Name of the stage
            subagent: Subagent to execute

        Returns:
            SubagentResult from the subagent
        """
        logger.debug(f"Executing stage: {stage_name}")

        # Hoist the import once so the names are bound for both pre- and
        # post-hook blocks even if `self._hooks` evaluates differently
        # between the two checks.
        if self._hooks:
            from primr.agentic.hooks import HookContext, HookResult, HookType

            pre_context = HookContext(
                hook_type=HookType.PRE_TOOL_USE,
                stage_name=stage_name,
                arguments={"subagent": subagent.name},
                company_name=subagent.company_name,
            )
            response = await self._hooks.run_pre_hooks(stage_name, pre_context)

            if response.result == HookResult.BLOCK:
                logger.warning(f"Stage {stage_name} blocked by hook")
                blocked_result: SubagentResult[Any] = SubagentResult(
                    status=SubagentStatus.FAILED,
                    error=f"Blocked by hook: {response.message}",
                )
                return blocked_result

        # Execute subagent
        result: SubagentResult[Any] = await subagent.execute()

        # Run post-hooks
        if self._hooks:
            from primr.agentic.hooks import HookContext, HookType

            post_context = HookContext(
                hook_type=HookType.POST_TOOL_USE,
                stage_name=stage_name,
                result=result,
                company_name=subagent.company_name,
            )
            await self._hooks.run_post_hooks(stage_name, result, post_context)

        return result

    def _derive_context(
        self,
        base: SubagentContext,
        **kwargs: Any,
    ) -> SubagentContext:
        """
        Create derived context with additional parent results.

        Args:
            base: Base context to derive from
            **kwargs: Additional parent results

        Returns:
            New SubagentContext with merged parent_results
        """
        return base.with_parent_results(**kwargs)

    def _create_working_dir(self, company_name: str) -> Path:
        """
        Create working directory for a company.

        Args:
            company_name: Company name

        Returns:
            Path to working directory
        """
        safe_name = (company_name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_"))[
            :50
        ]

        self._working_dir_sequence += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        working_dir = self._config.output_dir / (
            f"{safe_name}_{timestamp}_{self._working_dir_sequence:04d}"
        )
        working_dir.mkdir(parents=True, exist_ok=True)

        return working_dir

    def reset(self) -> None:
        """Reset orchestrator to IDLE state."""
        self._state = OrchestratorState.IDLE
        # v1.11.0: Reset interactive mode state
        self._paused_at_stage = None
        self._previous_state = None
        self._user_decisions = []
