"""Fast-run trust polish + citation repair stage (roadmap #23, Batch B).

Extracted verbatim from stage 7 of ``perform_fast_research`` — no behavior
change. Runs the low-cost editorial trust polish, the deterministic shipping
cleanup chain (scaffolding removal, citation normalization, section quality
guards), the repair-report diagnostic, the QA-metric computation, and the
conditional citation-integrity repair pass.

Side effects preserved from the original: console QA line, shipping-repair
info line, and the ``_shipping_repair.json`` diagnostic written to the
working folder (diagnostics never fail the run).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from primr.core.fast_mode_helpers import (
    _compute_fast_report_qa_metrics,
    _enforce_fast_section_quality_guards,
)
from primr.core.report_cleanup import _clean_fast_report_output, compute_repair_report
from primr.core.strategy_artifacts import _normalize_fast_citations
from primr.qa.label_calibration import label_citations_trust_row
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured

if TYPE_CHECKING:
    from primr.ai.stage_routing import StageModelRoute

logger = get_logger("core.fast_run_trust")

_LABEL_HONESTY_ENV = "PRIMR_LABEL_HONESTY"
_TRUTHY = frozenset({"1", "true", "yes"})


def _maybe_apply_label_honesty(report_content: str, folder_path: str) -> str:
    """Optionally downgrade ungrounded confidence labels (opt-in, fail-safe).

    Closes the measured grounding gap (1.x step 3 / roadmap #4): a (Confirmed)
    or (Reported) label whose cited source is judged not to support the claim
    is rewritten to (Estimated). Gated by ``PRIMR_LABEL_HONESTY`` because it
    adds judge LLM calls + source fetches; default-off keeps the standard run
    byte-identical until eval validates the recipe. An audit sidecar is written
    whenever the pass runs, and any failure leaves the report untouched -- a
    label audit must never break shipping.

    When enabled, model selection is recorded through the capability router for
    ``fast.label_honesty``. Agent/local profiles without a qualifying adapter
    skip the judge pass and leave the report unchanged.
    """
    if os.getenv(_LABEL_HONESTY_ENV, "").strip().lower() not in _TRUTHY:
        return report_content
    route_start = time.monotonic()
    route: StageModelRoute | None = None
    try:
        from primr.ai import stage_routing

        route = stage_routing.resolve_stage_model(
            "fast.label_honesty",
            legacy_model_type="fast",
        )
        log_structured("info", "Label honesty route selected", **route.log_metadata())
        if getattr(route, "execution_mode", "llm") == "unavailable":
            failure = stage_routing.stage_route_failure_class(route)
            stage_routing.record_stage_route_usage(
                folder_path,
                route,
                outcome="fallback",
                input_items=1,
                output_items=0,
                duration_seconds=time.monotonic() - route_start,
                failure_class=failure,
            )
            logger.debug("Label-honesty pass skipped: %s", failure)
            return report_content
    except Exception as route_err:
        logger.debug("Label-honesty route resolution failed: %s", route_err)
    try:
        from primr.qa.label_honesty import apply_label_honesty

        result = apply_label_honesty(report_content)
        with open(os.path.join(folder_path, "_label_honesty.json"), "w", encoding="utf-8") as _lf:
            json.dump(result.to_dict(), _lf, indent=2)
        if route is not None:
            from primr.ai import stage_routing as stage_routing_mod

            stage_routing_mod.record_stage_route_usage(
                folder_path,
                route,
                outcome="selected",
                input_items=1,
                output_items=len(result.downgrades) if result.changed else 0,
                duration_seconds=time.monotonic() - route_start,
            )
        if result.changed:
            console.info(
                f"Label honesty: downgraded {len(result.downgrades)} "
                "ungrounded label(s) to (Estimated)"
            )
            return result.report_content
    except Exception as _honesty_err:
        if route is not None:
            from primr.ai import stage_routing as stage_routing_mod

            stage_routing_mod.record_stage_route_usage(
                folder_path,
                route,
                outcome="fallback",
                input_items=1,
                output_items=0,
                duration_seconds=time.monotonic() - route_start,
                failure_class=type(_honesty_err).__name__,
            )
        logger.debug("Label-honesty pass skipped: %s", _honesty_err)
    return report_content


@dataclass(frozen=True)
class FastTrustResult:
    """Outputs of the trust stage that the orchestrator threads onward."""

    report_content: str
    qa_metrics: dict
    report_trust_stats: list[tuple[str, str]] = field(default_factory=list)


def polish_and_gate_fast_report(
    *,
    company_label: str,
    website: str | None,
    report_content: str,
    source_urls: list[str],
    grok_writing: str,
    folder_path: str,
    unresolved_contradictions: int,
) -> FastTrustResult:
    """Polish the fast-mode report for trust and compute its QA gate."""
    # Lazy import: research_agent imports this module, so the LLM-backed
    # polish/repair helpers (which stay there until their own extraction)
    # must be resolved at call time to avoid a circular import.
    from primr.ai import stage_routing
    from primr.core.research_agent import (
        _polish_fast_report_for_trust,
        _repair_fast_report_citation_integrity,
    )

    writing_model = grok_writing
    route: StageModelRoute | None = None
    usage_before: stage_routing.StageUsageByModel | None = None
    route_start = time.monotonic()
    skip_llm_polish = False
    try:
        route = stage_routing.resolve_stage_model(
            "fast.trust_polish",
            legacy_model_type="writing",
        )
        log_structured("info", "Trust polish route selected", **route.log_metadata())
        if getattr(route, "execution_mode", "llm") == "unavailable":
            skip_llm_polish = True
            failure = stage_routing.stage_route_failure_class(route)
            _record_trust_route(
                folder_path,
                route,
                outcome="fallback",
                input_count=1,
                output_count=0,
                duration_seconds=time.monotonic() - route_start,
                failure_class=failure,
            )
            console.info(f"Trust polish LLM pass skipped ({failure}) — deterministic cleanup only")
        elif route.model_name:
            writing_model = route.model_name
            usage_before = stage_routing.capture_stage_usage()
        else:
            usage_before = stage_routing.capture_stage_usage()
    except Exception as e:
        logger.warning("Trust polish route resolution failed: %s", e, exc_info=True)

    # Trust polish is a low-cost editorial pass to improve evidence discipline.
    if not skip_llm_polish:
        report_content = _polish_fast_report_for_trust(
            company_label,
            website,
            report_content,
            source_urls,
            model=writing_model,
        )
    pre_repair_content = report_content
    report_content = _clean_fast_report_output(report_content)
    report_content = _normalize_fast_citations(report_content, source_urls=source_urls)
    report_content = _enforce_fast_section_quality_guards(report_content)
    # Observability: measure how much the deterministic cleanup actually had
    # to repair. The goal is to push consistency upstream so this trends to
    # zero; surfacing it makes a writer that emits dirty markdown visible
    # instead of silently patched. Never let diagnostics fail the run.
    try:
        repair_report = compute_repair_report(pre_repair_content, report_content)
        if not repair_report["writer_output_clean"]:
            console.info(
                "Shipping repair: "
                f"{repair_report['scaffolding_removed']} scaffolding marker(s) removed, "
                f"{repair_report['chars_removed']} chars stripped"
            )
        with open(os.path.join(folder_path, "_shipping_repair.json"), "w", encoding="utf-8") as _rf:
            json.dump(repair_report, _rf, indent=2)
    except Exception as _repair_err:
        # Diagnostics must never break shipping.
        logger.debug("Repair report skipped: %s", _repair_err)
    qa_metrics = _compute_fast_report_qa_metrics(
        report_content,
        unresolved_contradictions=unresolved_contradictions,
    )
    if not skip_llm_polish and (
        qa_metrics["citations_used"] == 0 or qa_metrics["citations_defined"] == 0
    ):
        repaired_report = _repair_fast_report_citation_integrity(
            company_label,
            website,
            report_content,
            source_urls,
            model=writing_model,
        )
        if repaired_report != report_content:
            report_content = repaired_report
            qa_metrics = _compute_fast_report_qa_metrics(
                report_content,
                unresolved_contradictions=unresolved_contradictions,
            )
    # Opt-in label-honesty pass: downgrade confidence labels that don't trace to
    # their cited source. Runs on the final, citation-repaired content so the
    # labels are audited exactly as they ship. Default-off; recompute QA when it
    # changes anything (a downgrade shifts the per-label distribution).
    honest_content = _maybe_apply_label_honesty(report_content, folder_path)
    if honest_content != report_content:
        report_content = honest_content
        qa_metrics = _compute_fast_report_qa_metrics(
            report_content,
            unresolved_contradictions=unresolved_contradictions,
        )
    qa_parts = [
        f"labels={qa_metrics['confidence_labels']}",
        f"cites={qa_metrics['citations_used']}/{qa_metrics['citations_defined']}",
        f"validate={qa_metrics['sections_with_validate']}/{qa_metrics['section_count']}",
    ]
    if qa_metrics.get("duplicate_sections", 0) > 0:
        qa_parts.append(f"dupes={qa_metrics['duplicate_sections']}")
    if qa_metrics.get("thin_sections", 0) > 0:
        qa_parts.append(f"thin={qa_metrics['thin_sections']}")
    if qa_metrics.get("unresolved_contradictions", 0) > 0:
        qa_parts.append(f"contradictions={qa_metrics['unresolved_contradictions']}")
    qa_parts.append(f"gate={'PASS' if qa_metrics['qa_gate_passed'] else 'WARN'}")
    console.info("Fast QA: " + ", ".join(qa_parts))
    report_trust_stats = [
        ("Report Gate", "PASS" if qa_metrics["qa_gate_passed"] else "WARN"),
        (
            "Citations",
            f"{qa_metrics['citations_used']}/{qa_metrics['citations_defined']} defined",
        ),
        (
            "Validate Lines",
            f"{qa_metrics['sections_with_validate']}/{qa_metrics['section_count']} sections",
        ),
    ]
    # Deterministic, judge-free label-honesty signal (the no_source slice): how
    # many Confirmed/Reported claims carry a resolvable citation. Always on -
    # gives a label-traceability signal for free when the paid label-honesty
    # pass is off. Computed once in the QA metrics; omitted when there are no
    # such claims. Report-only; shares the deep path's row formatter.
    _label_row = label_citations_trust_row(
        int(qa_metrics.get("traceable_labeled_claims_cited", 0)),
        int(qa_metrics.get("traceable_labeled_claims", 0)),
    )
    if _label_row:
        report_trust_stats.append(_label_row)
    if qa_metrics.get("unresolved_contradictions", 0) > 0:
        report_trust_stats.append(("Contradictions", str(qa_metrics["unresolved_contradictions"])))

    if route is not None and not skip_llm_polish:
        _record_trust_route(
            folder_path,
            route,
            outcome="selected",
            input_count=1,
            output_count=1,
            duration_seconds=time.monotonic() - route_start,
            usage_delta=stage_routing.stage_usage_delta(usage_before)
            if usage_before is not None
            else None,
        )

    return FastTrustResult(
        report_content=report_content,
        qa_metrics=qa_metrics,
        report_trust_stats=report_trust_stats,
    )


def _record_trust_route(
    folder_path: str | None,
    route: StageModelRoute,
    *,
    outcome: str,
    input_count: int,
    output_count: int,
    duration_seconds: float,
    failure_class: str | None = None,
    usage_delta: dict[str, Any] | None = None,
) -> None:
    """Append body-free trust-polish route metadata to run state."""

    from primr.ai import stage_routing

    stage_routing.record_stage_route_usage(
        folder_path,
        route,
        outcome=outcome,
        input_items=input_count,
        output_items=output_count,
        duration_seconds=duration_seconds,
        failure_class=failure_class,
        usage_delta=usage_delta,
    )
