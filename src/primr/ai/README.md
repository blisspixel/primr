# AI Package

`primr.ai` owns model execution, provider adapters, routing policy, and the
premium Deep Research implementation. Pipeline coordination belongs in
`primr.core`; recovery orchestration belongs in `primr.pipeline`.

## Concern map

| Area | Modules | Responsibility |
|------|---------|----------------|
| Model calls | `client.py`, `async_client.py`, `llm.py` | Synchronous, asynchronous, and legacy-compatible model-call seams with usage tracking |
| Providers | `providers/`, `grok_client.py`, `openai_compatible_client.py` | xAI, Gemini, OpenAI-compatible, Anthropic, and related provider transports |
| Default routing | `routing.py` | Role-to-model and provider selection backed by the model registry |
| Capability routing | `capability_routing.py`, `stage_routing.py` | Pure stage requirement matching plus the production bridge for routed stages |
| Availability | `provider_availability.py`, `provider_availability_collectors.py` | Sanitized provider and local-capacity observations used by routing |
| Alternate execution | `host_agent_runner.py`, `host_agent_cli.py`, `local_inference.py` | Bounded official host-runner contracts and local OpenAI-compatible execution support |
| Deep Research | `deep_research.py`, `deep_research_execution.py`, `deep_research_parsing.py`, `deep_research_polling.py` | Deep Research submission, polling, parsing, recovery, and normalization |
| Premium report planning | `report_architect.py`, `research_executor.py`, `report_aggregator.py` | Chapter planning, parallel research execution, and report aggregation |
| Analysis helpers | `summarize.py`, `competitive.py`, `insight_engine.py`, `insights.py`, `grading_agent.py`, `quality_grader.py` | Focused summarization, analysis, and grading operations |
| Durable resources | `file_search_resources.py`, `job_persistence.py`, `citation_resolution.py` | Provider resources, recoverable jobs, and citation URL resolution |
| Shared policy | `error_policy.py`, `preflight.py`, `genai_factory.py` | Error classification, readiness checks, and Gemini client construction |

## Routing shape

```text
core.stage_inventory
        |
        v
ai.stage_routing -> ai.capability_routing
        |
        +-> ai.providers
        +-> internal/eval-only official host runner adapters
        +-> local OpenAI-compatible adapter
        |
        v
pipeline.llm_failover and usage accounting
```

Capability routing is incremental. A production stage must declare its needs
in `core/stage_inventory.py`, provide a stage-specific execution adapter, and
clear its evaluation gate before a new backend can replace the established
route.

## Package boundaries

- Model identifiers and pricing come from `primr.config.models`, not from
  call-site constants.
- Provider-specific authentication, quota handling, and request details stay
  inside provider-owned modules.
- Untrusted scraped content is fenced before it enters prompts.
- Cross-provider retry and circuit-breaker behavior uses `primr.pipeline`.
- `primr.ai.__init__` exposes the supported public symbols lazily so importing
  the package does not eagerly load every optional provider dependency.
