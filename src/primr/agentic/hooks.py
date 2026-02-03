"""
Hook-based governance system for agentic operations.

This module implements an event-driven hook system that enables policy
enforcement, cost tracking, security validation, and quality gates
throughout the research pipeline.

The hook system follows a priority-based execution model where hooks
are registered with priorities and executed in ascending order (lower
priority number executes first).

Hook Types:
    - PRE_TOOL_USE: Runs before tool/subagent execution (can block)
    - POST_TOOL_USE: Runs after tool/subagent execution (observational)
    - SESSION_START: Runs at session initialization

Built-in Hooks:
    - CostGuardHook: Budget enforcement
    - SSRFGuardHook: URL security validation
    - QAGateHook: Quality threshold enforcement
    - MemoryPersistenceHook: Research state persistence

Example:
    from primr.agentic.hooks import HookSystem, CostGuardHook, SSRFGuardHook

    hooks = HookSystem()
    hooks.register(CostGuardHook(max_cost_usd=5.0))
    hooks.register(SSRFGuardHook())

    # In orchestrator
    response = await hooks.run_pre_hooks("scrape", context)
    if response.result == HookResult.BLOCK:
        raise HookError(response.message)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from primr.agentic.errors import HookError

if TYPE_CHECKING:
    from primr.agentic.memory import ResearchMemory

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class HookType(Enum):
    """Types of hooks in the system."""

    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    SESSION_START = "session_start"


class HookResult(Enum):
    """Result of hook execution."""

    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class HookContext:
    """
    Context passed to hooks during execution.

    Attributes:
        hook_type: Type of hook being executed
        tool_name: Name of the tool being invoked (if applicable)
        stage_name: Name of the pipeline stage (if applicable)
        arguments: Arguments passed to the tool/stage
        result: Result from tool execution (for post hooks)
        company_name: Company being researched (if applicable)
    """

    hook_type: HookType
    tool_name: str | None = None
    stage_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    company_name: str | None = None


@dataclass
class HookResponse:
    """
    Response from a hook execution.

    Attributes:
        result: Whether to allow, block, or warn
        message: Optional message explaining the result
        modified_args: Optional modified arguments (for pre hooks)
    """

    result: HookResult
    message: str | None = None
    modified_args: dict[str, Any] | None = None


# =============================================================================
# HOOK BASE CLASS
# =============================================================================

class Hook(ABC):
    """
    Abstract base class for hooks.

    Hooks are executed in priority order (lower priority number executes
    first). Subclasses must implement the `execute` method and define
    their `hook_type`.

    Attributes:
        priority: Execution priority (lower = runs first)
        name: Human-readable name for logging

    Example:
        class MyHook(Hook):
            @property
            def hook_type(self) -> HookType:
                return HookType.PRE_TOOL_USE

            async def execute(self, context: HookContext) -> HookResponse:
                # Custom logic
                return HookResponse(result=HookResult.ALLOW)
    """

    def __init__(self, priority: int = 100, name: str | None = None):
        """
        Initialize hook.

        Args:
            priority: Execution priority (lower = runs first)
            name: Human-readable name (defaults to class name)
        """
        self.priority = priority
        self.name = name or self.__class__.__name__

    @property
    @abstractmethod
    def hook_type(self) -> HookType:
        """Return the type of this hook."""
        pass

    @abstractmethod
    async def execute(self, context: HookContext) -> HookResponse:
        """
        Execute the hook logic.

        Args:
            context: Hook execution context

        Returns:
            HookResponse indicating result
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(priority={self.priority})"


# =============================================================================
# HOOK SYSTEM
# =============================================================================

class HookSystem:
    """
    Manages hook registration and execution.

    The HookSystem maintains separate lists of hooks by type and executes
    them in priority order. For PRE_TOOL_USE hooks, execution stops on
    the first BLOCK result.

    Attributes:
        on_error: Error handling strategy ("log", "raise", "skip")

    Example:
        hooks = HookSystem(on_error="log")
        hooks.register(CostGuardHook(max_cost_usd=5.0))
        hooks.register(SSRFGuardHook())

        # Run pre-hooks before operation
        response = await hooks.run_pre_hooks("scrape", context)
        if response.result == HookResult.BLOCK:
            return  # Operation blocked

        # Execute operation...

        # Run post-hooks after operation
        await hooks.run_post_hooks("scrape", result)
    """

    def __init__(self, on_error: str = "log"):
        """
        Initialize hook system.

        Args:
            on_error: Error handling strategy
                - "log": Log error and continue
                - "raise": Re-raise the exception
                - "skip": Silently skip the failed hook
        """
        if on_error not in ("log", "raise", "skip"):
            raise ValueError(f"Invalid on_error value: {on_error}")

        self._hooks: dict[HookType, list[Hook]] = {
            HookType.PRE_TOOL_USE: [],
            HookType.POST_TOOL_USE: [],
            HookType.SESSION_START: [],
        }
        self._on_error = on_error

    @property
    def on_error(self) -> str:
        """Get the error handling strategy."""
        return self._on_error

    def register(self, hook: Hook) -> None:
        """
        Register a hook.

        Hooks are automatically sorted by priority after registration.

        Args:
            hook: Hook to register
        """
        self._hooks[hook.hook_type].append(hook)
        # Sort by priority (lower first)
        self._hooks[hook.hook_type].sort(key=lambda h: h.priority)
        logger.debug(f"Registered hook: {hook.name} (priority={hook.priority})")

    def unregister(self, hook: Hook) -> bool:
        """
        Unregister a hook.

        Args:
            hook: Hook to unregister

        Returns:
            True if hook was found and removed, False otherwise
        """
        hooks = self._hooks[hook.hook_type]
        if hook in hooks:
            hooks.remove(hook)
            logger.debug(f"Unregistered hook: {hook.name}")
            return True
        return False

    def get_hooks(self, hook_type: HookType) -> list[Hook]:
        """
        Get all hooks of a specific type.

        Args:
            hook_type: Type of hooks to retrieve

        Returns:
            List of hooks sorted by priority
        """
        return list(self._hooks[hook_type])

    async def run_pre_hooks(
        self,
        stage: str,
        context: HookContext | None = None,
    ) -> HookResponse:
        """
        Run all pre-tool-use hooks.

        Execution stops on the first BLOCK result.

        Args:
            stage: Name of the pipeline stage
            context: Optional pre-built context

        Returns:
            HookResponse (BLOCK if any hook blocked, ALLOW otherwise)
        """
        if context is None:
            context = HookContext(
                hook_type=HookType.PRE_TOOL_USE,
                stage_name=stage,
            )

        for hook in self._hooks[HookType.PRE_TOOL_USE]:
            try:
                response = await hook.execute(context)
                if response.result == HookResult.BLOCK:
                    logger.warning(
                        f"Hook {hook.name} blocked stage {stage}: {response.message}"
                    )
                    return response
                elif response.result == HookResult.WARN:
                    logger.warning(
                        f"Hook {hook.name} warning for stage {stage}: {response.message}"
                    )
            except Exception as e:
                self._handle_error(hook, e)

        return HookResponse(result=HookResult.ALLOW)

    async def run_post_hooks(
        self,
        stage: str,
        result: Any,
        context: HookContext | None = None,
    ) -> None:
        """
        Run all post-tool-use hooks.

        Post hooks are observational and cannot block.

        Args:
            stage: Name of the pipeline stage
            result: Result from the stage execution
            context: Optional pre-built context
        """
        if context is None:
            context = HookContext(
                hook_type=HookType.POST_TOOL_USE,
                stage_name=stage,
                result=result,
            )

        for hook in self._hooks[HookType.POST_TOOL_USE]:
            try:
                response = await hook.execute(context)
                if response.result == HookResult.WARN:
                    logger.warning(
                        f"Hook {hook.name} warning for stage {stage}: {response.message}"
                    )
            except Exception as e:
                self._handle_error(hook, e)

    async def run_session_hooks(self) -> HookResponse:
        """
        Run all session start hooks.

        Returns:
            HookResponse (BLOCK if any hook blocked, ALLOW otherwise)
        """
        context = HookContext(hook_type=HookType.SESSION_START)

        for hook in self._hooks[HookType.SESSION_START]:
            try:
                response = await hook.execute(context)
                if response.result == HookResult.BLOCK:
                    logger.warning(
                        f"Hook {hook.name} blocked session start: {response.message}"
                    )
                    return response
            except Exception as e:
                self._handle_error(hook, e)

        return HookResponse(result=HookResult.ALLOW)

    def _handle_error(self, hook: Hook, error: Exception) -> None:
        """
        Handle hook execution errors.

        Args:
            hook: Hook that raised the error
            error: The exception that was raised
        """
        if self._on_error == "raise":
            raise HookError(
                message=f"Hook {hook.name} failed: {error}",
                hook_name=hook.name,
                cause=error,
            ) from error
        elif self._on_error == "log":
            logger.error(f"Hook {hook.name} failed: {error}")
        # "skip" does nothing



# =============================================================================
# BUILT-IN HOOKS
# =============================================================================

class CostGuardHook(Hook):
    """
    PreToolUse hook that blocks operations exceeding budget.

    Tracks cumulative cost and blocks operations that would exceed
    the configured maximum budget.

    Attributes:
        max_cost_usd: Maximum allowed cost in USD
        spent: Current cumulative spend

    Example:
        hook = CostGuardHook(max_cost_usd=5.0)
        hooks.register(hook)

        # After operation completes
        hook.record_cost(0.50)
    """

    def __init__(self, max_cost_usd: float = 5.0, priority: int = 10):
        """
        Initialize cost guard.

        Args:
            max_cost_usd: Maximum allowed cost in USD
            priority: Execution priority (default 10 = runs early)
        """
        super().__init__(priority=priority, name="CostGuard")
        self._max_cost = max_cost_usd
        self._spent = 0.0

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    @property
    def max_cost(self) -> float:
        """Get the maximum allowed cost."""
        return self._max_cost

    @property
    def spent(self) -> float:
        """Get the current cumulative spend."""
        return self._spent

    @property
    def remaining(self) -> float:
        """Get the remaining budget."""
        return max(0.0, self._max_cost - self._spent)

    async def execute(self, context: HookContext) -> HookResponse:
        """Check if operation would exceed budget."""
        estimated_cost = context.arguments.get("estimated_cost_usd", 0.0)

        if self._spent + estimated_cost > self._max_cost:
            return HookResponse(
                result=HookResult.BLOCK,
                message=(
                    f"Budget exceeded: ${self._spent:.2f} spent, "
                    f"${estimated_cost:.2f} requested, "
                    f"${self._max_cost:.2f} limit"
                ),
            )

        return HookResponse(result=HookResult.ALLOW)

    def record_cost(self, cost: float) -> None:
        """
        Record actual cost after operation.

        Args:
            cost: Cost in USD to record
        """
        self._spent += cost
        logger.debug(f"CostGuard: recorded ${cost:.2f}, total ${self._spent:.2f}")

    def reset(self) -> None:
        """Reset the spent counter."""
        self._spent = 0.0


class SSRFGuardHook(Hook):
    """
    PreToolUse hook that validates URLs against SSRF patterns.

    Uses the existing security module to validate URLs before
    allowing scraping operations.

    Example:
        hook = SSRFGuardHook()
        hooks.register(hook)
    """

    def __init__(self, priority: int = 5):
        """
        Initialize SSRF guard.

        Args:
            priority: Execution priority (default 5 = runs very early)
        """
        super().__init__(priority=priority, name="SSRFGuard")

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        """Validate URL against SSRF patterns."""
        # Extract URL from various argument names
        url = (
            context.arguments.get("url")
            or context.arguments.get("company_url")
            or context.arguments.get("target_url")
        )

        if not url:
            return HookResponse(result=HookResult.ALLOW)

        try:
            # Delegate to existing security module
            from primr.mcp_server.security import URLValidator

            validator = URLValidator()
            result = validator.validate(url)

            if result.valid:
                return HookResponse(result=HookResult.ALLOW)
            else:
                return HookResponse(
                    result=HookResult.BLOCK,
                    message=f"SSRF protection: {result.error_message}",
                )
        except ImportError:
            # Security module not available, allow but warn
            logger.warning("Security module not available for SSRF validation")
            return HookResponse(
                result=HookResult.WARN,
                message="SSRF validation skipped: security module not available",
            )


class QAGateHook(Hook):
    """
    PostToolUse hook that enforces quality thresholds.

    Checks report quality after the write stage and warns if
    the score is below the configured threshold.

    Attributes:
        min_score: Minimum acceptable QA score (0-100)

    Example:
        hook = QAGateHook(min_score=70)
        hooks.register(hook)
    """

    def __init__(self, min_score: int = 70, priority: int = 50):
        """
        Initialize QA gate.

        Args:
            min_score: Minimum acceptable score (0-100)
            priority: Execution priority
        """
        super().__init__(priority=priority, name="QAGate")
        self._min_score = min_score
        self._last_score: int | None = None
        self._last_feedback: list[str] = []

    @property
    def hook_type(self) -> HookType:
        return HookType.POST_TOOL_USE

    @property
    def min_score(self) -> int:
        """Get the minimum acceptable score."""
        return self._min_score

    @property
    def last_score(self) -> int | None:
        """Get the last QA score."""
        return self._last_score

    @property
    def last_feedback(self) -> list[str]:
        """Get the last QA feedback."""
        return list(self._last_feedback)

    async def execute(self, context: HookContext) -> HookResponse:
        """Check report quality after write stage."""
        # Only run for write stage
        if context.stage_name != "write":
            return HookResponse(result=HookResult.ALLOW)

        # Get report path from result
        report_path = None
        if context.result:
            if hasattr(context.result, "report_path"):
                report_path = context.result.report_path
            elif hasattr(context.result, "data") and context.result.data:
                report_path = getattr(context.result.data, "report_path", None)

        if not report_path:
            return HookResponse(result=HookResult.ALLOW)

        try:
            # Run basic QA check on the report
            from pathlib import Path

            report_file = Path(report_path)
            if not report_file.exists():
                return HookResponse(
                    result=HookResult.WARN,
                    message="Report file not found",
                )

            content = report_file.read_text(encoding="utf-8")

            # Basic quality checks
            word_count = len(content.split())
            has_sections = content.count("#") >= 3
            has_citations = "[" in content and "]" in content

            # Simple scoring
            score = 50
            if word_count >= 500:
                score += 20
            if has_sections:
                score += 15
            if has_citations:
                score += 15

            self._last_score = score
            self._last_feedback = []

            if not has_sections:
                self._last_feedback.append("Report lacks clear section structure")
            if word_count < 500:
                self._last_feedback.append(f"Report is short ({word_count} words)")

            if score < self._min_score:
                return HookResponse(
                    result=HookResult.WARN,
                    message=(
                        f"QA score {score} below threshold {self._min_score}"
                    ),
                )

            return HookResponse(result=HookResult.ALLOW)
        except Exception as e:
            logger.error(f"QA analysis failed: {e}")
            return HookResponse(result=HookResult.ALLOW)


class MemoryPersistenceHook(Hook):
    """
    PostToolUse hook that saves research state to memory.

    Automatically persists hypotheses generated during research
    to the research memory system.

    Example:
        memory = ResearchMemory()
        hook = MemoryPersistenceHook(memory)
        hooks.register(hook)
    """

    def __init__(self, memory: ResearchMemory, priority: int = 90):
        """
        Initialize memory persistence hook.

        Args:
            memory: ResearchMemory instance to persist to
            priority: Execution priority (default 90 = runs late)
        """
        super().__init__(priority=priority, name="MemoryPersistence")
        self._memory = memory

    @property
    def hook_type(self) -> HookType:
        return HookType.POST_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        """Persist hypotheses to memory."""
        # Extract hypotheses from result
        hypotheses = []
        if context.result:
            if hasattr(context.result, "hypotheses"):
                hypotheses = context.result.hypotheses
            elif hasattr(context.result, "data") and context.result.data:
                hypotheses = getattr(context.result.data, "hypotheses", [])

        # Get company name
        company = (
            context.company_name
            or context.arguments.get("company_name")
            or context.arguments.get("company")
        )

        if hypotheses and company:
            try:
                self._memory.save_hypotheses(company, hypotheses)
                logger.debug(
                    f"MemoryPersistence: saved {len(hypotheses)} hypotheses for {company}"
                )
            except Exception as e:
                logger.error(f"Failed to persist hypotheses: {e}")

        return HookResponse(result=HookResult.ALLOW)
