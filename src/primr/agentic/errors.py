"""
Error hierarchy for the agentic architecture.

This module extends primr's typed error hierarchy with agentic-specific
errors. All errors integrate with the existing error handling patterns
including correlation IDs, recovery classification, and structured logging.

The error hierarchy follows the principle that errors should be:
- Self-documenting: Include context about what failed and why
- Recoverable-aware: Indicate whether retry is appropriate
- Traceable: Include correlation IDs for distributed tracing
- Actionable: Provide guidance for resolution

Example:
    try:
        result = await subagent.execute()
    except SubagentError as e:
        if e.recoverable:
            # Retry with backoff
            await asyncio.sleep(e.retry_after or 1.0)
            result = await subagent.execute()
        else:
            # Log and propagate
            logger.error(e.debug_message())
            raise
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from primr.utils.errors import PrimrError, TransientError, PermanentError


@dataclass
class AgenticError(PrimrError):
    """
    Base class for all agentic architecture errors.

    This serves as the root of the agentic error hierarchy, enabling
    catch-all handling for agentic operations while preserving the
    ability to catch specific error types.

    Attributes:
        message: Human-readable error description
        category: Always "agentic" for base agentic errors
        component: The agentic component that raised the error

    Example:
        try:
            result = await orchestrator.research(company, url)
        except AgenticError as e:
            # Handle any agentic error
            logger.error(f"Agentic operation failed: {e}")
    """

    category: str = "agentic"
    component: str = ""

    def _debug_attributes(self) -> list[str]:
        """Include component in debug output."""
        return ["component"]


@dataclass
class SubagentError(AgenticError, TransientError):
    """
    Error during subagent execution.

    Raised when a subagent fails during its specialized task. Subagent
    errors are typically transient (recoverable) because they often
    result from external service failures.

    Attributes:
        subagent: Name of the subagent that failed
        stage: Pipeline stage where failure occurred
        partial_result: Any partial results before failure

    Example:
        try:
            result = await scraper_subagent.execute()
        except SubagentError as e:
            logger.warning(f"Subagent '{e.subagent}' failed at stage '{e.stage}'")
            if e.partial_result:
                # Use partial results
                process_partial(e.partial_result)
    """

    subagent: str = ""
    stage: str = ""
    partial_result: Any = None
    component: str = "subagent"
    recoverable: bool = True

    def __post_init__(self) -> None:
        """Enhance message with subagent context."""
        if self.subagent and not self.message.startswith(f"Subagent '{self.subagent}'"):
            self.message = f"Subagent '{self.subagent}' failed: {self.message}"
        super().__post_init__()

    def _debug_attributes(self) -> list[str]:
        """Include subagent details in debug output."""
        return ["subagent", "stage"]


@dataclass
class OrchestratorError(AgenticError):
    """
    Error during orchestration.

    Raised when the orchestrator encounters an error coordinating
    subagents or managing the research pipeline.

    Attributes:
        state: Orchestrator state when error occurred
        completed_stages: List of stages that completed successfully
        failed_stage: The stage that failed (if applicable)

    Example:
        try:
            result = await orchestrator.research(company, url)
        except OrchestratorError as e:
            logger.error(f"Orchestration failed in state '{e.state}'")
            # Check what completed before failure
            for stage in e.completed_stages:
                logger.info(f"Stage '{stage}' completed successfully")
    """

    state: str = ""
    completed_stages: list[str] = field(default_factory=list)
    failed_stage: str = ""
    component: str = "orchestrator"

    def __post_init__(self) -> None:
        """Enhance message with state context."""
        if self.state and "state" not in self.message.lower():
            self.message = f"Orchestrator error in state '{self.state}': {self.message}"
        super().__post_init__()

    def _debug_attributes(self) -> list[str]:
        """Include orchestrator details in debug output."""
        return ["state", "completed_stages", "failed_stage"]


@dataclass
class HookError(AgenticError):
    """
    Error during hook execution.

    Raised when a hook fails during pre/post tool execution. Hook
    errors can be configured to be logged, raised, or skipped based
    on the HookSystem's on_error configuration.

    Attributes:
        hook_name: Name of the hook that failed
        hook_type: Type of hook (pre_tool_use, post_tool_use, session_start)
        blocked: Whether the hook blocked the operation

    Example:
        try:
            await hook_system.run_pre_hooks(stage, subagent)
        except HookError as e:
            if e.blocked:
                logger.warning(f"Operation blocked by hook '{e.hook_name}'")
            else:
                logger.error(f"Hook '{e.hook_name}' failed: {e.message}")
    """

    hook_name: str = ""
    hook_type: str = ""
    blocked: bool = False
    component: str = "hook"

    def __post_init__(self) -> None:
        """Enhance message with hook context."""
        if self.hook_name and not self.message.startswith(f"Hook '{self.hook_name}'"):
            self.message = f"Hook '{self.hook_name}' failed: {self.message}"
        super().__post_init__()

    def _debug_attributes(self) -> list[str]:
        """Include hook details in debug output."""
        return ["hook_name", "hook_type", "blocked"]


@dataclass
class MemoryError(AgenticError, PermanentError):
    """
    Error during memory operations.

    Raised when research memory operations fail, such as loading,
    saving, or querying hypotheses. Memory errors are typically
    permanent because they often indicate file system or data
    corruption issues.

    Attributes:
        operation: The memory operation that failed (load, save, query)
        company: Company name associated with the memory
        file_path: Path to the memory file (if applicable)

    Example:
        try:
            hypotheses = memory.get_hypotheses(company)
        except MemoryError as e:
            logger.error(f"Memory {e.operation} failed for '{e.company}'")
            # Fall back to empty state
            hypotheses = []
    """

    operation: str = ""
    company: str = ""
    file_path: str = ""
    component: str = "memory"
    recoverable: bool = False

    def __post_init__(self) -> None:
        """Enhance message with memory context."""
        if self.operation and "operation" not in self.message.lower():
            self.message = f"Memory {self.operation} failed: {self.message}"
        super().__post_init__()

    def _debug_attributes(self) -> list[str]:
        """Include memory details in debug output."""
        return ["operation", "company", "file_path"]


@dataclass
class RoadmapParseError(AgenticError, PermanentError):
    """
    Error parsing ROADMAP.md.

    Raised when the roadmap parser encounters invalid or unexpected
    content in ROADMAP.md. Parse errors are permanent because they
    require manual correction of the roadmap file.

    Attributes:
        line: Line number where the error occurred
        content: The problematic content (truncated)
        expected: What the parser expected to find

    Example:
        try:
            roadmap = RoadmapAPI()
            versions = roadmap.list_by_status(VersionStatus.PLANNED)
        except RoadmapParseError as e:
            logger.error(f"ROADMAP.md parse error at line {e.line}: {e.message}")
            # Return empty roadmap data
            versions = []
    """

    line: int = 0
    content: str = ""
    expected: str = ""
    component: str = "roadmap"
    recoverable: bool = False

    def __post_init__(self) -> None:
        """Enhance message with parse context."""
        if self.line > 0 and "line" not in self.message.lower():
            self.message = f"ROADMAP.md parse error at line {self.line}: {self.message}"
        super().__post_init__()

    def _debug_attributes(self) -> list[str]:
        """Include parse details in debug output."""
        attrs = ["line"]
        if self.content:
            attrs.append("content")
        if self.expected:
            attrs.append("expected")
        return attrs
