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
from dataclasses import dataclass, field

from primr.core.fast_mode_helpers import (
    _compute_fast_report_qa_metrics,
    _enforce_fast_section_quality_guards,
)
from primr.core.report_cleanup import _clean_fast_report_output, compute_repair_report
from primr.core.strategy_artifacts import _normalize_fast_citations
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("core.fast_run_trust")


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
    from primr.core.research_agent import (
        _polish_fast_report_for_trust,
        _repair_fast_report_citation_integrity,
    )

    # Trust polish is a low-cost editorial pass to improve evidence discipline.
    report_content = _polish_fast_report_for_trust(
        company_label,
        website,
        report_content,
        source_urls,
        model=grok_writing,
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
    if qa_metrics["citations_used"] == 0 or qa_metrics["citations_defined"] == 0:
        repaired_report = _repair_fast_report_citation_integrity(
            company_label,
            website,
            report_content,
            source_urls,
            model=grok_writing,
        )
        if repaired_report != report_content:
            report_content = repaired_report
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
    if qa_metrics.get("unresolved_contradictions", 0) > 0:
        report_trust_stats.append(("Contradictions", str(qa_metrics["unresolved_contradictions"])))

    return FastTrustResult(
        report_content=report_content,
        qa_metrics=qa_metrics,
        report_trust_stats=report_trust_stats,
    )
