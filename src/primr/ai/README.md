# AI Module

This module handles all AI operations in Primr, including LLM interactions, deep research, and content analysis.

## Components

### Core Client (`client.py`)

Unified AI client with retry logic, fallback support, and token tracking.

```python
from primr.ai import get_client, AIClient

client = get_client()
response = client.generate("Analyze this company", thinking_level="high")
```

### Deep Research (`deep_research.py`)

Integration with Gemini's Deep Research Agent for autonomous multi-step research.

```python
from primr.ai import DeepResearchClient

client = DeepResearchClient()
result = await client.research("Research Tesla's competitive position")
```

### Recursive Hierarchical Architecture

For comprehensive reports, three components work together:

1. **Master Architect** (`report_architect.py`): Decomposes reports into chapters
2. **Research Executor** (`research_executor.py`): Runs chapters in parallel
3. **Report Aggregator** (`report_aggregator.py`): Combines chapters into final document

### Quality Grading (`grading_agent.py`, `quality_grader.py`)

Grades each section on a 0-100 scale and triggers refinement for low-quality sections.

### Analysis Components

- `competitive.py`: Competitive analysis and SWOT generation
- `insights.py`: Risk assessment and opportunity identification
- `insight_engine.py`: Strategic insight generation
- `summarize.py`: Content summarization

## Key Patterns

### Singleton Access

All major components use thread-safe singletons:

```python
from primr.ai import get_client, reset_client

client = get_client()  # Returns singleton
reset_client()         # Reset for testing
```

### Error Handling

AI operations raise `AIError` with context:

```python
from primr.utils.errors import AIError

try:
    response = client.generate(prompt)
except AIError as e:
    print(f"Model: {e.model}, Cause: {e.cause}")
```

### Token Tracking

```python
client = AIClient(track_usage=True)
# ... make calls ...
usage = client.get_usage_summary()
print(f"Cost: ${usage['total_cost']:.4f}")
```

## Configuration

AI behavior is configured via `AIConfig` in settings:

- `research_model`: Model for research operations
- `report_model`: Model for report generation
- `max_retries`: Retry count for failed calls
- `grade_threshold`: Quality threshold (0-100)
- `default_temperature`: Sampling temperature
- `model_fallbacks`: Fallback chains for each model
