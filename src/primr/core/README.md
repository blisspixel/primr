# Core Module

This module contains the research orchestration logic that coordinates all other modules.

## Components

### Research Orchestrator (`research_orchestrator.py`)

The central coordinator that routes research requests to the appropriate engine.

```python
from primr.core.research_orchestrator import (
    ResearchOrchestrator,
    ResearchMode,
    ResearchConfig,
    OrchestratorResult
)

orchestrator = ResearchOrchestrator()
result = await orchestrator.research(
    "Tesla",
    "https://tesla.com",
    mode=ResearchMode.COMPLETE
)
```

### Research Modes

| Mode | Description | Duration |
|------|-------------|----------|
| `STRUCTURED` | Website scraping + Google search | 20-25 min |
| `DEEP_RESEARCH` | Autonomous web research | 10-15 min |
| `COMPLETE` | Two-phase: structured then deep | 30-40 min |

### Research Agent (`research_agent.py`)

The main research pipeline for Scrape Mode:

```python
from primr.core.research_agent import run_research, perform_research

# Synchronous API
sections = run_research("Tesla", "https://tesla.com")

# CLI entry point
perform_research("Tesla", "https://tesla.com", mode="full")
```

### Report Models (`report_models.py`)

Data structures for research results and reports.

### Container (`container.py`)

Dependency injection container for component wiring.

## Complete Mode Architecture

Complete Mode uses a 4-phase architecture:

```
Phase 0: Data Collection
    └── Structured Pipeline (scraping + search)
    └── Context File Generation
    └── File Search Store Upload

Phase 1: Planning
    └── Master Architect
    └── Chapter Plan (10 chapters)

Phase 2: Parallel Execution
    └── Research Node Executor
    └── 3 concurrent Deep Research tasks
    └── Shared File Search Store context

Phase 3: Aggregation
    └── Report Aggregator
    └── TOC generation
    └── Citation consolidation
```

## Key Patterns

### Progress Callbacks

All research methods support progress callbacks:

```python
def on_progress(message: str):
    print(f"Progress: {message}")

result = await orchestrator.research(
    "Tesla",
    "https://tesla.com",
    on_progress=on_progress
)
```

### Graceful Degradation

If Phase 0 fails, Complete Mode continues with limited context:

```python
if not structured_result.success:
    logger.warning("Structured Pipeline failed, continuing with limited context")
```

### Metrics Emission

Research operations emit structured metrics:

```python
self._emit_research_metrics(
    operation="research",
    company_name=company_name,
    mode=mode.value,
    duration=duration,
    success=True,
    section_count=len(result.section_results)
)
```

## CLI Entry Point

The CLI is defined in `research_agent.py`:

```bash
primr "Tesla" https://tesla.com --mode full
primr doctor
primr --check-jobs
```

## Configuration

Research behavior is configured via:

- `ResearchConfig`: Per-request configuration
- `AIConfig`: AI model settings
- `ScrapingConfig`: Scraping behavior
- `PathConfig`: Output directories
