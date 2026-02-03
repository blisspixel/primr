"""
Base classes for the Subagent Architecture.

This module defines the foundational types and abstract base class
for all research subagents. Subagents are specialized components
that handle distinct phases of the research pipeline.

Key Concepts:
    - SubagentStatus: Lifecycle state of a subagent
    - SubagentContext: Isolated context passed to subagents
    - SubagentResult: Structured result from subagent execution
    - Subagent: Abstract base class for all subagents

Design Principles:
    - Context Isolation: Subagents only access data explicitly passed
    - Type Safety: Generic result types for type-safe pipelines
    - Lifecycle Management: Clear state transitions during execution
    - Error Propagation: Structured error handling with cause chains

Example:
    class MySubagent(Subagent[MyResult]):
        async def execute(self) -> SubagentResult[MyResult]:
            self._status = SubagentStatus.RUNNING
            try:
                result = await self._do_work()
                self._status = SubagentStatus.COMPLETED
                return SubagentResult(status=self._status, data=result)
            except Exception as e:
                self._status = SubagentStatus.FAILED
                return SubagentResult(status=self._status, error=str(e))

        def get_required_tools(self) -> list[str]:
            return ["my_tool"]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from primr.agentic.models import Hypothesis


# =============================================================================
# ENUMS
# =============================================================================

class SubagentStatus(Enum):
    """
    Lifecycle status of a subagent.

    State transitions:
        IDLE -> RUNNING -> COMPLETED
        IDLE -> RUNNING -> FAILED

    Attributes:
        IDLE: Subagent created but not yet started
        RUNNING: Subagent is currently executing
        COMPLETED: Subagent finished successfully
        FAILED: Subagent encountered an error
    """

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SubagentContext:
    """
    Isolated context for a subagent.

    Each subagent receives a context containing only the data it needs
    to perform its task. This enforces context isolation and prevents
    subagents from accessing data they shouldn't have.

    Attributes:
        company_name: Name of the company being researched
        company_url: Primary URL for the company
        working_dir: Directory for intermediate files
        prior_hypotheses: Hypotheses from previous research sessions
        parent_results: Results from parent/upstream subagents
        config: Optional configuration overrides

    Example:
        context = SubagentContext(
            company_name="Acme Corp",
            company_url="https://acme.com",
            working_dir=Path("./output/acme"),
            parent_results={"corpus_path": Path("./corpus")},
        )
    """

    company_name: str
    company_url: str
    working_dir: Path
    prior_hypotheses: list[Hypothesis] = field(default_factory=list)
    parent_results: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Ensure working_dir is a Path object."""
        if isinstance(self.working_dir, str):
            self.working_dir = Path(self.working_dir)

    def get_parent_result(self, key: str, default: Any = None) -> Any:
        """
        Get a result from a parent subagent.

        Args:
            key: Key to look up in parent_results
            default: Default value if key not found

        Returns:
            The value from parent_results or default
        """
        return self.parent_results.get(key, default)

    def with_parent_results(self, **kwargs: Any) -> SubagentContext:
        """
        Create a new context with additional parent results.

        Args:
            **kwargs: Key-value pairs to add to parent_results

        Returns:
            New SubagentContext with merged parent_results
        """
        merged = {**self.parent_results, **kwargs}
        return SubagentContext(
            company_name=self.company_name,
            company_url=self.company_url,
            working_dir=self.working_dir,
            prior_hypotheses=list(self.prior_hypotheses),
            parent_results=merged,
            config=dict(self.config),
        )


# Type variable for generic result data
T = TypeVar("T")


@dataclass
class SubagentResult(Generic[T]):
    """
    Result from subagent execution.

    Encapsulates the outcome of a subagent's work, including:
    - Status indicating success or failure
    - Typed data payload (if successful)
    - Error message (if failed)
    - Generated hypotheses (for analyst subagent)
    - Performance metrics

    Attributes:
        status: Final status of the subagent
        data: Typed result data (None if failed)
        error: Error message (None if successful)
        hypotheses: Hypotheses generated during execution
        metrics: Performance metrics (timing, counts, etc.)

    Example:
        # Successful result
        result = SubagentResult(
            status=SubagentStatus.COMPLETED,
            data=ScrapeResult(pages_scraped=10, corpus_path=Path("./corpus")),
            metrics={"duration_seconds": 45.2},
        )

        # Failed result
        result = SubagentResult(
            status=SubagentStatus.FAILED,
            error="Connection timeout after 30 seconds",
        )
    """

    status: SubagentStatus
    data: T | None = None
    error: str | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """Check if the result indicates success."""
        return self.status == SubagentStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        """Check if the result indicates failure."""
        return self.status == SubagentStatus.FAILED

    def get_metric(self, key: str, default: float = 0.0) -> float:
        """
        Get a metric value.

        Args:
            key: Metric key
            default: Default value if not found

        Returns:
            Metric value or default
        """
        return self.metrics.get(key, default)


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class Subagent(ABC, Generic[T]):
    """
    Abstract base class for specialized research subagents.

    Subagents are the workhorses of the agentic architecture. Each
    subagent handles a specific phase of the research pipeline:

    - ScraperSubagent: Content extraction with tier escalation
    - AnalystSubagent: Insight synthesis and hypothesis generation
    - WriterSubagent: Report generation with citations
    - QASubagent: Quality assessment and feedback

    Subclasses must implement:
    - execute(): Perform the subagent's specialized task
    - get_required_tools(): List MCP tools needed by this subagent

    Attributes:
        name: Human-readable name for logging
        context: Isolated context for this subagent

    Example:
        class MySubagent(Subagent[MyResult]):
            async def execute(self) -> SubagentResult[MyResult]:
                self._status = SubagentStatus.RUNNING
                # ... do work ...
                self._status = SubagentStatus.COMPLETED
                return SubagentResult(status=self._status, data=result)

            def get_required_tools(self) -> list[str]:
                return []
    """

    def __init__(
        self,
        context: SubagentContext,
        name: str | None = None,
    ):
        """
        Initialize subagent.

        Args:
            context: Isolated context for this subagent
            name: Human-readable name (defaults to class name)
        """
        self._context = context
        self._status = SubagentStatus.IDLE
        self._name = name or self.__class__.__name__

    @property
    def name(self) -> str:
        """Get the subagent name."""
        return self._name

    @property
    def status(self) -> SubagentStatus:
        """Get the current status."""
        return self._status

    @property
    def context(self) -> SubagentContext:
        """Get the subagent context."""
        return self._context

    @property
    def company_name(self) -> str:
        """Get the company name from context."""
        return self._context.company_name

    @property
    def company_url(self) -> str:
        """Get the company URL from context."""
        return self._context.company_url

    @property
    def working_dir(self) -> Path:
        """Get the working directory from context."""
        return self._context.working_dir

    @abstractmethod
    async def execute(self) -> SubagentResult[T]:
        """
        Execute the subagent's specialized task.

        Implementations should:
        1. Set status to RUNNING at start
        2. Perform the specialized work
        3. Set status to COMPLETED or FAILED
        4. Return a SubagentResult with appropriate data

        Returns:
            SubagentResult containing status, data, and metrics

        Raises:
            SubagentError: If execution fails catastrophically
        """
        pass

    @abstractmethod
    def get_required_tools(self) -> list[str]:
        """
        Return list of MCP tools this subagent needs.

        Used by the orchestrator to validate that required tools
        are available before starting execution.

        Returns:
            List of MCP tool names (empty if using internal pipeline)
        """
        pass

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"company={self.company_name!r}, "
            f"status={self._status.value})"
        )
