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
    - CostGuardHook: Budget enforcement (lives in primr.agentic.cost_guard)
    - SSRFGuardHook: URL security validation
    - QAGateHook: Quality threshold enforcement
    - MemoryPersistenceHook: Research state persistence
    - ContentSanitizationHook: Prompt injection protection

Example:
    from primr.agentic import CostGuardHook, HookSystem, SSRFGuardHook

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
    ERROR_RECOVERY = "error_recovery"  # v1.11.0: Interactive error handling


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
        mutable_data: Mutable dict for hooks to pass data back (v1.11.0)
        user_input_callback: Optional callback to request user input (v1.11.0)
    """

    hook_type: HookType
    tool_name: str | None = None
    stage_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    company_name: str | None = None
    mutable_data: dict[str, Any] = field(default_factory=dict)
    user_input_callback: Any = None  # Callable[[str, list[str]], Awaitable[str]] | None


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

    @abstractmethod
    async def execute(self, context: HookContext) -> HookResponse:
        """
        Execute the hook logic.

        Args:
            context: Hook execution context

        Returns:
            HookResponse indicating result
        """

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
            HookType.ERROR_RECOVERY: [],
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

        merged_args: dict[str, Any] | None = None
        for hook in self._hooks[HookType.PRE_TOOL_USE]:
            try:
                response = await hook.execute(context)
                if response.result == HookResult.BLOCK:
                    logger.warning(f"Hook {hook.name} blocked stage {stage}: {response.message}")
                    return response
                elif response.result == HookResult.WARN:
                    logger.warning(
                        f"Hook {hook.name} warning for stage {stage}: {response.message}"
                    )
                # Propagate modified_args through the hook chain
                if response.modified_args:
                    if merged_args is None:
                        merged_args = dict(context.arguments)
                    merged_args.update(response.modified_args)
                    context.arguments.update(response.modified_args)
            except Exception as e:
                self._handle_error(hook, e)

        return HookResponse(result=HookResult.ALLOW, modified_args=merged_args)

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
                    logger.warning(f"Hook {hook.name} blocked session start: {response.message}")
                    return response
            except Exception as e:
                self._handle_error(hook, e)

        return HookResponse(result=HookResult.ALLOW)

    async def run_error_recovery_hooks(
        self,
        stage: str,
        error: Exception,
        context: HookContext | None = None,
    ) -> HookResponse:
        """
        Run all error recovery hooks (v1.11.0 Interactive Mode).

        Error recovery hooks can decide whether to retry, skip, or abort
        based on the error type. They can also request user input.

        Args:
            stage: Name of the pipeline stage where error occurred
            error: The exception that was raised
            context: Optional pre-built context

        Returns:
            HookResponse with recovery action (ALLOW=retry, WARN=skip, BLOCK=abort)
        """
        if context is None:
            context = HookContext(
                hook_type=HookType.ERROR_RECOVERY,
                stage_name=stage,
                arguments={
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )

        last_warn: HookResponse | None = None
        for hook in self._hooks[HookType.ERROR_RECOVERY]:
            try:
                response = await hook.execute(context)
                if response.result == HookResult.BLOCK:
                    logger.warning(
                        f"Hook {hook.name} aborted recovery for stage {stage}: {response.message}"
                    )
                    return response
                elif response.result == HookResult.ALLOW:
                    logger.info(
                        f"Hook {hook.name} allowing retry for stage {stage}: {response.message}"
                    )
                    return response
                elif response.result == HookResult.WARN:
                    logger.info(f"Hook {hook.name} warned for stage {stage}: {response.message}")
                    last_warn = response
            except Exception as e:
                self._handle_error(hook, e)

        # Return last WARN if any hooks warned, otherwise block
        if last_warn is not None:
            return last_warn

        # Default: no recovery, propagate error
        return HookResponse(
            result=HookResult.BLOCK,
            message="No error recovery hook handled the error",
        )

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
        else:
            # "skip" — still log at debug for diagnostics
            logger.debug(f"Hook {hook.name} skipped due to error: {error}")


# =============================================================================
# BUILT-IN HOOKS
# =============================================================================
# CostGuardHook (budget enforcement) lives in primr.agentic.cost_guard; it was
# extracted when this file hit its architecture ceiling. Import it from there
# (or from the primr.agentic package, which re-exports it).


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

        from primr.utils.security import is_safe_url

        ok, reason = is_safe_url(str(url))
        if ok:
            return HookResponse(result=HookResult.ALLOW)
        return HookResponse(
            result=HookResult.BLOCK,
            message=f"SSRF protection: {reason}",
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
            from pathlib import Path

            report_file = Path(report_path)
            if not report_file.exists():
                return HookResponse(
                    result=HookResult.WARN,
                    message="Report file not found",
                )

            # Use ReportAnalyzer for structured checks
            try:
                from primr.qa.report_analyzer import ReportAnalyzer

                analyzer = ReportAnalyzer(str(report_file))
                quality = analyzer.analyze_content_quality()
                structure = analyzer.analyze_structure()
                hypothesis = analyzer.analyze_hypothesis_coverage()
                citation_density = analyzer.analyze_citation_density()
                section_lengths = analyzer.analyze_section_lengths()

                score = 50  # base score
                self._last_feedback = []

                # Word count >= 500: +15
                if quality["word_count"] >= 500:
                    score += 15
                else:
                    self._last_feedback.append(f"Report is short ({quality['word_count']} words)")

                # Sections >= 3: +10
                if structure["total_sections"] >= 3:
                    score += 10
                else:
                    self._last_feedback.append("Report has too few sections")

                # Required sections present: +10
                if not structure["key_sections_missing"]:
                    score += 10
                else:
                    self._last_feedback.append(
                        f"Missing sections: {', '.join(structure['key_sections_missing'])}"
                    )

                # Hypothesis framing meets threshold: +5
                if hypothesis["meets_threshold"]:
                    score += 5
                else:
                    self._last_feedback.append(
                        f"Weak hypothesis framing ({hypothesis['total_signals']}"
                        f"/{hypothesis['threshold']} signals)"
                    )

                # Citation density meets threshold: +5
                if citation_density["meets_threshold"]:
                    score += 5
                else:
                    self._last_feedback.append(
                        f"Low citation density ({citation_density['density_per_1000_words']}"
                        f"/{citation_density['threshold']} per 1000 words)"
                    )

                # Truncated sections: -5 each (max -10)
                if section_lengths["truncated_sections"]:
                    penalty = min(10, section_lengths["truncated_count"] * 5)
                    score -= penalty
                    self._last_feedback.append(
                        f"{section_lengths['truncated_count']} truncated section(s): "
                        f"{', '.join(section_lengths['truncated_sections'][:3])}"
                    )

                score = max(0, min(95, score))

            except ImportError:
                # Fallback to basic checks if ReportAnalyzer unavailable
                content = report_file.read_text(encoding="utf-8")
                word_count = len(content.split())
                has_sections = content.count("#") >= 3

                score = 50
                self._last_feedback = []
                if word_count >= 500:
                    score += 20
                if has_sections:
                    score += 15

                if not has_sections:
                    self._last_feedback.append("Report lacks clear section structure")
                if word_count < 500:
                    self._last_feedback.append(f"Report is short ({word_count} words)")

            self._last_score = score

            if score < self._min_score:
                return HookResponse(
                    result=HookResult.WARN,
                    message=(f"QA score {score} below threshold {self._min_score}"),
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
                logger.debug(f"MemoryPersistence: saved {len(hypotheses)} hypotheses for {company}")
            except Exception as e:
                logger.error(f"Failed to persist hypotheses: {e}")

        return HookResponse(result=HookResult.ALLOW)


class InteractiveErrorRecoveryHook(Hook):
    """
    ErrorRecovery hook that requests user input on errors (v1.11.0).

    This hook demonstrates interactive error recovery where the user
    can decide how to handle recoverable errors during research.

    Attributes:
        retryable_errors: Set of error types that can be retried

    Example:
        hook = InteractiveErrorRecoveryHook()
        hooks.register(hook)

        # When an error occurs, user will be prompted to decide action
    """

    def __init__(
        self,
        retryable_errors: set[str] | None = None,
        priority: int = 50,
    ):
        """
        Initialize interactive error recovery hook.

        Args:
            retryable_errors: Set of error type names that can be retried
            priority: Execution priority
        """
        super().__init__(priority=priority, name="InteractiveErrorRecovery")
        self._retryable_errors = retryable_errors or {
            "TimeoutError",
            "ConnectionError",
            "RateLimitError",
            "TransientError",
        }

    @property
    def hook_type(self) -> HookType:
        return HookType.ERROR_RECOVERY

    async def execute(self, context: HookContext) -> HookResponse:
        """Handle error with optional user input."""
        error_type = context.arguments.get("error_type", "")
        error_message = context.arguments.get("error_message", "")
        retry_count = context.arguments.get("retry_count", 0)

        # Check if error is retryable
        is_retryable = error_type in self._retryable_errors

        # If user input callback is available, ask user
        if context.user_input_callback and is_retryable:
            try:
                prompt = (
                    f"Recoverable error: {error_type}\n"
                    f"Message: {error_message}\n"
                    f"Retry attempt: {retry_count}\n\n"
                    "How would you like to proceed?"
                )
                options = ["retry", "skip", "abort"]
                response = await context.user_input_callback(prompt, options)
                response = response.lower().strip()

                if response == "retry":
                    return HookResponse(
                        result=HookResult.ALLOW,
                        message="User requested retry",
                    )
                elif response == "skip":
                    return HookResponse(
                        result=HookResult.WARN,
                        message="User requested skip",
                    )
                else:
                    return HookResponse(
                        result=HookResult.BLOCK,
                        message="User requested abort",
                    )
            except Exception as e:
                logger.warning(f"User input failed: {e}")

        # Auto-retry for known transient errors (up to 3 times)
        if is_retryable and retry_count < 3:
            return HookResponse(
                result=HookResult.ALLOW,
                message=f"Auto-retrying {error_type}",
            )

        # Default: no recovery
        return HookResponse(
            result=HookResult.BLOCK,
            message=f"Cannot recover from {error_type}",
        )


class ContentSanitizationHook(Hook):
    """
    PreToolUse hook that sanitizes content against prompt injection.

    Validates and sanitizes content before it's passed to LLM prompts,
    protecting against prompt injection attacks from scraped web content.

    Attributes:
        mode: How to handle detected issues (BLOCK, STRIP, WARN)

    Example:
        hook = ContentSanitizationHook(mode="strip")
        hooks.register(hook)
    """

    def __init__(
        self,
        mode: str = "strip",
        priority: int = 15,
    ):
        """
        Initialize content sanitization hook.

        Args:
            mode: Sanitization mode ("block", "strip", "warn")
            priority: Execution priority (default 15 = runs early, after SSRF)
        """
        super().__init__(priority=priority, name="ContentSanitization")
        self._mode = mode.lower()

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    @property
    def mode(self) -> str:
        """Get the sanitization mode."""
        return self._mode

    async def execute(self, context: HookContext) -> HookResponse:
        """Sanitize content in arguments against prompt injection."""
        # Extract content from various argument names
        content_key: str | None = None
        for key in ("content", "text", "raw_text", "scraped_content"):
            if context.arguments.get(key):
                content_key = key
                break

        if content_key is None:
            return HookResponse(result=HookResult.ALLOW)

        content = context.arguments.get(content_key, "")

        if not content or not isinstance(content, str):
            return HookResponse(result=HookResult.ALLOW)

        try:
            from primr.utils.content_sanitizer import (
                ContentSanitizer,
                IssueType,
                SanitizationMode,
            )

            # Map string mode to enum
            mode_map = {
                "block": SanitizationMode.BLOCK,
                "strip": SanitizationMode.STRIP,
                "warn": SanitizationMode.WARN,
            }
            sanitization_mode = mode_map.get(self._mode, SanitizationMode.STRIP)

            sanitizer = ContentSanitizer(mode=sanitization_mode)
            result = sanitizer.sanitize(content)

            # Count injection issues specifically
            injection_count = sum(
                1 for i in result.issues if i.issue_type == IssueType.PROMPT_INJECTION
            )

            if result.blocked:
                return HookResponse(
                    result=HookResult.BLOCK,
                    message=f"Content blocked: {len(result.issues)} sanitization issues detected ({injection_count} prompt injection patterns)",
                )

            if result.issues:
                if sanitization_mode == SanitizationMode.WARN:
                    return HookResponse(
                        result=HookResult.WARN,
                        message=f"Content warning: {len(result.issues)} issues detected ({injection_count} prompt injection patterns)",
                    )
                else:
                    # STRIP mode - modify the arguments using the actual key
                    return HookResponse(
                        result=HookResult.WARN,
                        message=f"Content sanitized: {len(result.issues)} issues removed ({injection_count} prompt injection patterns)",
                        modified_args={content_key: result.sanitized},
                    )

            return HookResponse(result=HookResult.ALLOW)

        except ImportError:
            logger.warning("Content sanitizer module not available")
            return HookResponse(
                result=HookResult.WARN,
                message="Content sanitization skipped: module not available",
            )


class VerificationGateHook(Hook):
    """
    PostToolUse hook that warns when verification trust score is low.

    Runs after the verify stage and warns if the trust score
    falls below the configured threshold.

    Attributes:
        min_trust_score: Minimum acceptable trust score (0.0-1.0)

    Example:
        hook = VerificationGateHook(min_trust_score=0.5)
        hooks.register(hook)
    """

    def __init__(self, min_trust_score: float = 0.5, priority: int = 55):
        """
        Initialize verification gate.

        Args:
            min_trust_score: Minimum acceptable trust score (0.0-1.0)
            priority: Execution priority (default 55 = after QAGateHook)
        """
        super().__init__(priority=priority, name="VerificationGate")
        self._min_trust_score = min_trust_score
        self._last_trust_score: float | None = None

    @property
    def hook_type(self) -> HookType:
        return HookType.POST_TOOL_USE

    @property
    def min_trust_score(self) -> float:
        """Get the minimum acceptable trust score."""
        return self._min_trust_score

    @property
    def last_trust_score(self) -> float | None:
        """Get the last trust score."""
        return self._last_trust_score

    async def execute(self, context: HookContext) -> HookResponse:
        """Check verification trust score after verify stage."""
        if context.stage_name != "verify":
            return HookResponse(result=HookResult.ALLOW)

        trust_score = None
        if context.result:
            if hasattr(context.result, "data") and context.result.data:
                trust_score = getattr(context.result.data, "trust_score", None)

        if trust_score is None:
            return HookResponse(result=HookResult.ALLOW)

        self._last_trust_score = trust_score

        if trust_score < self._min_trust_score:
            pct = int(trust_score * 100)
            threshold_pct = int(self._min_trust_score * 100)
            return HookResponse(
                result=HookResult.WARN,
                message=(f"Trust score {pct}% below threshold {threshold_pct}%"),
            )

        return HookResponse(result=HookResult.ALLOW)
