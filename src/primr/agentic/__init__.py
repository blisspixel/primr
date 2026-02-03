"""
Agentic Architecture for Primr.

This module implements the agentic architecture that transforms primr into
an agent-native research system. It provides:

- Research Memory: Persistent cross-session state for hypotheses and patterns
- Roadmap API: Queryable interface to ROADMAP.md
- Hook System: Event-driven governance with cost guards and QA gates
- Subagent Architecture: Specialized agents for scraping, analysis, writing, QA
- Orchestrator: Coordinates subagent lifecycle and context isolation
- Integration: State machine, telemetry, and circuit breaker integration

The architecture follows Model Context Protocol patterns and Knowledge Work
Plugin principles to enable AI agents to efficiently navigate, coordinate,
and learn from research operations.

Example:
    from primr.agentic import ResearchOrchestrator, ResearchMemory

    memory = ResearchMemory()
    orchestrator = ResearchOrchestrator(memory=memory)
    result = await orchestrator.research("Acme Corp", "https://acme.com")
"""

from primr.agentic.errors import (
    AgenticError,
    HookError,
    MemoryError,
    OrchestratorError,
    RoadmapParseError,
    SubagentError,
)
from primr.agentic.hooks import (
    CostGuardHook,
    Hook,
    HookContext,
    HookResponse,
    HookResult,
    HookSystem,
    HookType,
    MemoryPersistenceHook,
    QAGateHook,
    SSRFGuardHook,
)
from primr.agentic.integration import (
    AgenticIntegration,
    CircuitBreakerIntegration,
    OrchestratorStateMachineAdapter,
    TelemetryIntegration,
)
from primr.agentic.memory import (
    CompanyMemory,
    ResearchMemory,
    ScrapePattern,
)
from primr.agentic.models import (
    ConfidenceLevel,
    Feature,
    Hypothesis,
    Version,
    VersionStatus,
)
from primr.agentic.orchestrator import (
    OrchestratorConfig,
    OrchestratorResult,
    OrchestratorState,
    ResearchOrchestrator,
)
from primr.agentic.roadmap_api import RoadmapAPI
from primr.agentic.subagents import (
    AnalysisResult,
    AnalystSubagent,
    QAResult,
    QASubagent,
    ScrapeResult,
    ScraperSubagent,
    Subagent,
    SubagentContext,
    SubagentResult,
    SubagentStatus,
    WriterResult,
    WriterSubagent,
)

__all__ = [
    # Errors
    "AgenticError",
    "HookError",
    "MemoryError",
    "OrchestratorError",
    "RoadmapParseError",
    "SubagentError",
    # Hooks
    "CostGuardHook",
    "Hook",
    "HookContext",
    "HookResponse",
    "HookResult",
    "HookSystem",
    "HookType",
    "MemoryPersistenceHook",
    "QAGateHook",
    "SSRFGuardHook",
    # Integration
    "AgenticIntegration",
    "CircuitBreakerIntegration",
    "OrchestratorStateMachineAdapter",
    "TelemetryIntegration",
    # Memory
    "CompanyMemory",
    "ResearchMemory",
    "ScrapePattern",
    # Models
    "ConfidenceLevel",
    "Feature",
    "Hypothesis",
    "Version",
    "VersionStatus",
    # Orchestrator
    "OrchestratorConfig",
    "OrchestratorResult",
    "OrchestratorState",
    "ResearchOrchestrator",
    # Roadmap
    "RoadmapAPI",
    # Subagents
    "AnalysisResult",
    "AnalystSubagent",
    "QAResult",
    "QASubagent",
    "ScrapeResult",
    "ScraperSubagent",
    "Subagent",
    "SubagentContext",
    "SubagentResult",
    "SubagentStatus",
    "WriterResult",
    "WriterSubagent",
]
