"""LLM-backed source relevance filtering for fast-mode external sources."""

from __future__ import annotations

import json
import time
from typing import Any

from primr.ai import stage_routing
from primr.ai.host_agent_cli import run_host_agent_stage
from primr.ai.host_agent_runner import (
    HostAgentBillingMode,
    HostAgentKind,
    HostAgentPolicy,
    HostAgentStagePacket,
)
from primr.ai.llm import llm
from primr.ai.provider_availability import LocalCapacityBusyError
from primr.utils.observability import log_structured

_SOURCE_RELEVANCE_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {"type": "integer"},
}


def _assess_source_relevance(
    company_name: str,
    external_data: dict[str, str],
    folder_path: str | None = None,
) -> dict[str, str]:
    """Filter external sources by relevance using LLM assessment."""

    if len(external_data) <= 5:
        return external_data

    source_summaries: list[str] = []
    url_list = list(external_data.keys())
    for i, url in enumerate(url_list):
        snippet = external_data[url][:500].replace("\n", " ")
        source_summaries.append(f"{i + 1}. {url}\n   {snippet}")

    instructions = _source_relevance_instructions(company_name, len(url_list))
    prompt = f"""{instructions}

SOURCES:
{chr(10).join(source_summaries)}"""
    route: stage_routing.StageModelRoute | None = None
    usage_before: stage_routing.StageUsageByModel | None = None
    start_time = time.monotonic()
    try:
        route = stage_routing.resolve_stage_model("fast.source_relevance", legacy_model_type="fast")
        log_structured("info", "Source relevance route selected", **route.log_metadata())
        execution_mode = getattr(route, "execution_mode", "llm")
        if execution_mode == "unavailable":
            _record_source_route(
                folder_path,
                route,
                outcome="fallback",
                input_count=len(external_data),
                output_count=len(external_data),
                duration_seconds=time.monotonic() - start_time,
                failure_class=stage_routing.stage_route_failure_class(route),
            )
            return external_data

        if execution_mode == "host_agent":
            response = _run_source_relevance_host_agent(
                route,
                instructions,
                source_summaries,
            ).strip()
        else:
            usage_before = stage_routing.capture_stage_usage()
            response = llm(
                prompt, model_type="fast", streaming=False, model=route.model_name
            ).strip()
        text = response.strip()
        if text.startswith("```"):
            first_nl = text.find("\n")
            text = text[first_nl + 1 :] if first_nl != -1 else text[3:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()
        bracket_start = text.find("[")
        bracket_end = text.rfind("]")
        if bracket_start != -1 and bracket_end > bracket_start:
            keep_indices = json.loads(text[bracket_start : bracket_end + 1])
        else:
            _record_source_route(
                folder_path,
                route,
                outcome="fallback",
                input_count=len(external_data),
                output_count=len(external_data),
                duration_seconds=time.monotonic() - start_time,
                failure_class="unparseable_response",
                usage_delta=stage_routing.stage_usage_delta(usage_before)
                if usage_before is not None
                else None,
            )
            return external_data

        keep_set = {round(n) - 1 for n in keep_indices if isinstance(n, (int, float))}
        filtered = {
            url_list[i]: external_data[url_list[i]] for i in keep_set if 0 <= i < len(url_list)
        }

        if len(filtered) < 3:
            _record_source_route(
                folder_path,
                route,
                outcome="fallback",
                input_count=len(external_data),
                output_count=len(external_data),
                duration_seconds=time.monotonic() - start_time,
                failure_class="too_few_sources",
                usage_delta=stage_routing.stage_usage_delta(usage_before)
                if usage_before is not None
                else None,
            )
            return external_data

        dropped = len(external_data) - len(filtered)
        _record_source_route(
            folder_path,
            route,
            outcome="selected",
            input_count=len(external_data),
            output_count=len(filtered),
            duration_seconds=time.monotonic() - start_time,
            usage_delta=stage_routing.stage_usage_delta(usage_before)
            if usage_before is not None
            else None,
        )
        if dropped > 0:
            log_structured(
                "info",
                "Source quality filter dropped low-relevance sources",
                kept=len(filtered),
                dropped=dropped,
            )
        return filtered
    except LocalCapacityBusyError as e:
        if route is not None:
            _record_source_route(
                folder_path,
                route,
                outcome="fallback",
                input_count=len(external_data),
                output_count=len(external_data),
                duration_seconds=time.monotonic() - start_time,
                failure_class=stage_routing.stage_route_failure_class(route, e),
                failure=e,
                usage_delta=stage_routing.stage_usage_delta(usage_before)
                if usage_before is not None
                else None,
            )
        log_structured(
            "warning",
            "Source relevance local capacity busy",
            source_count=len(external_data),
            **e.as_metadata(),
        )
        raise
    except Exception as e:
        if route is not None:
            _record_source_route(
                folder_path,
                route,
                outcome="fallback",
                input_count=len(external_data),
                output_count=len(external_data),
                duration_seconds=time.monotonic() - start_time,
                failure_class=type(e).__name__,
                usage_delta=stage_routing.stage_usage_delta(usage_before)
                if usage_before is not None
                else None,
            )
        log_structured(
            "warning",
            "Source relevance assessment failed, keeping all sources",
            error=str(e),
            source_count=len(external_data),
        )
        return external_data


def _source_relevance_instructions(company_name: str, source_count: int) -> str:
    return f"""You are evaluating {source_count} external research sources about {company_name}.

For each source, decide: KEEP or DROP.

KEEP a source if it provides SPECIFIC, USEFUL intelligence about {company_name}:
- Names executives, financials, deals, partnerships, or strategies
- Provides industry analysis mentioning this company specifically
- Contains news, press releases, or analyst coverage about this company

DROP a source if it is:
- Generic industry content that barely mentions the company
- A directory listing, job board, or social media page with no substance
- Duplicate information already covered by another KEPT source
- Tangentially related but not genuinely informative

IMPORTANT: For smaller or less prominent companies, it is BETTER to keep 5 high-quality
sources than 25 mediocre ones. Be selective. Quality over quantity.

Return ONLY a JSON array of the source NUMBERS to KEEP (e.g. [1, 3, 5, 8]).

No prose, no explanation."""


def _run_source_relevance_host_agent(
    route: stage_routing.StageModelRoute,
    instructions: str,
    source_summaries: list[str],
) -> str:
    runner_kind = route.host_agent_kind or HostAgentKind.CODEX.value
    result = run_host_agent_stage(
        HostAgentStagePacket(
            stage_id="fast.source_relevance",
            role="utility",
            instructions=instructions,
            evidence={
                f"source_{idx}": summary for idx, summary in enumerate(source_summaries, start=1)
            },
            output_schema=_SOURCE_RELEVANCE_OUTPUT_SCHEMA,
            policy=HostAgentPolicy(
                billing_mode=HostAgentBillingMode(route.billing_mode),
                max_wall_seconds=180,
                max_output_chars=10_000,
            ),
        ),
        kind=runner_kind,
    )
    return result.text


def _record_source_route(
    folder_path: str | None,
    route: stage_routing.StageModelRoute,
    *,
    outcome: str,
    input_count: int,
    output_count: int,
    duration_seconds: float,
    failure_class: str | None = None,
    failure: Exception | None = None,
    usage_delta: dict[str, Any] | None = None,
) -> None:
    stage_routing.record_stage_route_usage(
        folder_path,
        route,
        outcome=outcome,
        input_items=input_count,
        output_items=output_count,
        duration_seconds=duration_seconds,
        failure_class=failure_class,
        failure=failure,
        usage_delta=usage_delta,
    )
