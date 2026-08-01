"""Fast-run report-section writing stage (roadmap #23, Batch D).

Extracted verbatim from stage 5 (Phase 4 banner) of ``perform_fast_research``
— no behavior change. Writes report sections in parallel within parts,
assembles the report, and runs the coherence pass.

Tangle point handled here (refactor map #3): each part's worker pool shares a
FROZEN snapshot of prior sections (``prior_sections = list(written_sections)``
captured via default-arg binding before the pool dispatches), and the
executive summary is popped from its batch and written LAST with ALL completed
sections as synthesis context, then inserted at position 0.

Side effects preserved from the original: phase banner/completion, per-part
and per-section console lines, constrained-evidence announcement, and the
all-sections-failed error path (signalled by ``report_content=None``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from primr.core.fast_mode_helpers import _assemble_fast_report
from primr.core.section_planning import (
    _PART_LABELS,
    _determine_section_reasoning_mode,
    _group_sections_by_part,
)
from primr.utils.console import console
from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from primr.output.final_artifact import GeneratedSection
    from primr.prompts.loader import SectionConfig

logger = get_logger("core.fast_run_sections")

REPORT_SYSTEM_PROMPT = (
    "You are a senior strategic analyst writing a consulting dossier — internal prep "
    "before a discovery conversation. Your reader is a partner walking into a meeting.\n\n"
    "The bar is maximally useful strategic analysis: long-form, specific, strategically sharp, and written "
    "to get a consultant maximally up to speed before talking with the company.\n\n"
    "CORE DISCIPLINE:\n"
    "- STRESS-TEST the company's narrative. Do NOT paraphrase their marketing. "
    "When they claim 'only purpose-built' or '9x ROI', challenge it with evidence.\n"
    "- Frame every major claim as a hypothesis with counter-evidence. "
    "What would disprove it? What's the alternative explanation?\n"
    "- For each section, surface 'what to validate in conversation' — specific "
    "questions a consultant would ask to test the hypothesis.\n"
    "- Be CONSERVATIVE on financial estimates. Use wide ranges, note low confidence. "
    "Never state an inference as if it were confirmed.\n\n"
    "EPISTEMIC RULES:\n"
    "- Label claims: Confirmed (filings/official), Reported (credible 3rd party), "
    "Estimated (inferred), Hypothesis (our speculation)\n"
    "- CONFIDENCE RESET per section: don't inherit confidence from prior sections\n"
    "- NARRATIVE CEILING: don't escalate stakes. 'Opportunity' stays 'opportunity', "
    "not 'transformational opportunity'. Keep scope realistic.\n"
    "- NUMERIC PRECISION: ranges for estimates ('$800M-$1.2B'), note source/date\n"
    "- AVOID OVERREACH: don't claim inside knowledge of board decisions, precise "
    "market share in opaque markets, or causal certainty\n"
    "- REASON UNDER CONSTRAINT: if company-specific evidence is thin, still produce deep strategic analysis by combining "
    "observed facts, industry structure, competitive analogs, likely buyer behavior, and explicit scenario logic\n\n"
    "FORMATTING:\n"
    "- Full paragraphs with evidence and strategic interpretation, not bullet dumps\n"
    "- Tables for financials, competitors, timelines\n"
    "- Keep citations compact, usually at paragraph ends, and avoid cluttering every sentence\n"
    "- Use [cite: N] references in the body; keep the densest reference inventory in the final Sources appendix\n"
    "- Sub-headings (###) within sections for readability\n"
    "- Each insight lives in ONE section — cross-reference, don't repeat"
)


@dataclass(frozen=True)
class SectionWritingResult:
    """Outputs of the section-writing stage.

    ``report_content`` is None when every section failed — the orchestrator
    propagates this as a run failure (the original early-return path).
    """

    report_content: str | None
    written_sections: list[GeneratedSection] = field(default_factory=list)
    total_words: int = 0


def write_report_sections(
    *,
    company_label: str,
    website: str | None,
    analysis_workbook: str,
    raw_corpus: str,
    external_sources_raw: str,
    source_urls: list[str],
    grok_writing: str,
    recovery_executor,
    folder_path: str,
    total_phases: int,
    framing_block: str = "",
) -> SectionWritingResult:
    """Write all report sections, assemble the report, run the coherence pass.

    ``framing_block`` carries operator intent (``ResearchFraming``) into every
    section-write prompt. It is run-shared, so it sits in the cached prompt
    prefix and stays byte-identical across the parallel section writes. Empty
    when no framing was supplied.
    """
    # Lazy import: research_agent imports this module, so the LLM-backed
    # section writer and coherence pass (which stay there until their own
    # extraction) must be resolved at call time to avoid a circular import.
    from primr.core.research_agent import _fast_coherence_pass, _write_section_with_retry

    console.phase_banner(
        4,
        total_phases,
        "Report Writing (Grok)",
        "Writing sections (parallel within parts)",
        "3-5 min",
    )

    routed = _resolve_report_sections_route(grok_writing, folder_path)
    if routed is None:
        return SectionWritingResult(report_content=None)
    writing_model, route, usage_before, route_start = routed

    # Build a raw data subset for evidence (~100k chars; workbook already distills
    # corpus). Default: leading slice (scrape order). With
    # PRIMR_SECTION_EVIDENCE_CURATION=1, spend the budget on the corpus pages most
    # relevant to the workbook instead of whatever was scraped first — context
    # assembly, shared across sections (preserves the cached prefix), eval-gated
    # (docs/design/eval-plan.md Eval 4). Default off => byte-identical to before.
    _CORPUS_BUDGET = 100_000
    if len(raw_corpus) <= _CORPUS_BUDGET:
        raw_corpus_subset = raw_corpus
    elif os.environ.get("PRIMR_SECTION_EVIDENCE_CURATION") == "1":
        from primr.core.context_curation import rank_corpus_by_relevance

        raw_corpus_subset = rank_corpus_by_relevance(raw_corpus, analysis_workbook, _CORPUS_BUDGET)
    else:
        raw_corpus_subset = raw_corpus[:_CORPUS_BUDGET]

    # Fence the scraped material ONCE, after slicing and before any prompt
    # build: slices of a fenced string would tear the markers, and fencing
    # inside the per-section builders would break the byte-identical cached
    # prefix (each fence carries a per-call nonce). Fenced once here, the same
    # string flows to every section write and regeneration in this run.
    from primr.utils.content_sanitizer import fence_untrusted

    raw_corpus_subset = fence_untrusted("WEBSITE_CORPUS", raw_corpus_subset)
    external_sources_raw = fence_untrusted("EXTERNAL_SOURCES", external_sources_raw)

    report_system = REPORT_SYSTEM_PROMPT

    from concurrent.futures import ThreadPoolExecutor, as_completed

    section_batches = _group_sections_by_part()

    # Use constrained-evidence reasoning for thin-signal sections instead of skipping them.
    section_reasoning_modes: dict[str, str] = {}
    constrained_sections: list[str] = []
    for batch in section_batches:
        for sec in batch:
            mode = _determine_section_reasoning_mode(sec, analysis_workbook)
            section_reasoning_modes[sec.id] = mode
            if mode == "constrained_evidence":
                constrained_sections.append(sec.name)
    if constrained_sections:
        console.info(
            "Using constrained-evidence strategic reasoning for "
            f"{len(constrained_sections)} section(s): {', '.join(constrained_sections)}"
        )

    # Pop executive_summary — write it LAST so it can synthesize the full report
    exec_summary_section = None
    for batch in section_batches:
        for sec in batch:
            if sec.id == "executive_summary":
                exec_summary_section = sec
                batch.remove(sec)
                break
        if exec_summary_section:
            break
    # Remove empty batches (if exec summary was the only section in its batch)
    section_batches = [b for b in section_batches if b]

    # Rebuild section names from the post-pop batches so indices align with
    # global_offset used in _write_one.  Exec summary is written last, so it
    # should NOT be in the ToC during batch writing — avoids off-by-one where
    # [NOW] marker points to the wrong section name.
    all_section_names = [s.name for batch in section_batches for s in batch]
    written_sections: list[GeneratedSection] = []
    effective_name = company_label

    global_offset = 0
    for part_num, part_sections in enumerate(section_batches):
        part_label = _PART_LABELS.get(part_sections[0].part, f"Part {part_sections[0].part}")
        console.info(
            f"Part {part_num + 1}/{len(section_batches)} ({part_label}): "
            f"{len(part_sections)} section(s) in parallel"
        )

        # Snapshot written_sections — threads in this part share the same frozen prior context
        prior_sections = list(written_sections)

        def _write_one(
            idx_section: tuple[int, SectionConfig],
            _offset: int = global_offset,
            _prior: list[GeneratedSection] = prior_sections,
        ) -> tuple[int, GeneratedSection | None]:
            local_idx, sec = idx_section

            def _do_write():
                result = _write_section_with_retry(
                    sec,
                    _offset + local_idx,
                    all_section_names,
                    _prior,
                    effective_name,
                    website,
                    analysis_workbook,
                    raw_corpus_subset,
                    external_sources_raw,
                    source_urls,
                    report_system,
                    section_reasoning_modes.get(sec.id, "standard"),
                    model=writing_model,
                    framing_block=framing_block,
                )
                if result is None:
                    raise RuntimeError(f"Section '{sec.name}' returned empty")
                return result

            from primr.pipeline.integration import write_section_with_recovery

            stage_result = write_section_with_recovery(recovery_executor, _do_write, folder_path)
            if stage_result.success:
                # The recovery channel is typed dict-or-None but carries the
                # GeneratedSection produced by _do_write through unchanged.
                return (local_idx, cast("GeneratedSection | None", stage_result.output))
            return (local_idx, None)

        results: list[tuple[int, GeneratedSection | None]] = []
        if len(part_sections) == 1:
            results.append(_write_one((0, part_sections[0])))
        else:
            with ThreadPoolExecutor(max_workers=min(len(part_sections), 4)) as executor:
                futures = {
                    executor.submit(_write_one, (i, s)): i for i, s in enumerate(part_sections)
                }
                for future in as_completed(futures):
                    results.append(future.result())

        # Sort by local index to maintain canonical section order
        results.sort(key=lambda x: x[0])
        seen_titles: set[str] = {s.title.lower().strip() for s in written_sections}
        for local_idx, parsed in results:
            if parsed:
                title_key = parsed.title.lower().strip()
                if title_key in seen_titles:
                    console.warn(f"  {parsed.title} — duplicate, skipping")
                    continue
                seen_titles.add(title_key)
                written_sections.append(parsed)
                console.ok(f"  {parsed.title} ({parsed.words:,} words)")
            else:
                sec_name = part_sections[local_idx].name
                console.warn(f"  {sec_name} — skipped (failed or empty)")

        global_offset += len(part_sections)

    # Write executive summary LAST — it now has full report context to synthesize
    if exec_summary_section is not None:
        console.info("Writing Executive Summary (with full report context)")
        exec_parsed = _write_section_with_retry(
            exec_summary_section,
            0,  # section_index 0 — first section in final report
            all_section_names,
            written_sections,  # ALL completed sections → full synthesis context
            effective_name,
            website,
            analysis_workbook,
            raw_corpus_subset,
            external_sources_raw,
            source_urls,
            report_system,
            section_reasoning_modes.get(exec_summary_section.id, "standard"),
            model=writing_model,
            framing_block=framing_block,
        )
        if exec_parsed:
            written_sections.insert(0, exec_parsed)
            console.ok(f"  {exec_parsed.title} ({exec_parsed.words:,} words)")
        else:
            console.warn("  Executive Summary — skipped (failed or empty)")

    if not written_sections:
        console.error("All report sections failed — no sections written")
        _record_report_sections_route(
            folder_path,
            route,
            usage_before=usage_before,
            route_start=route_start,
            section_count=len(all_section_names),
            written_count=0,
        )
        return SectionWritingResult(report_content=None)

    report_content = _assemble_fast_report(company_label, website, written_sections)

    # Coherence pass: deduplicate and smooth transitions
    with console.timed_operation("Running coherence pass"):
        report_content = _fast_coherence_pass(
            company_label, website, report_content, model=writing_model
        )

    _record_report_sections_route(
        folder_path,
        route,
        usage_before=usage_before,
        route_start=route_start,
        section_count=len(all_section_names),
        written_count=len(written_sections),
    )

    total_words = len(report_content.split())
    console.phase_complete(
        "Report Writing (Grok)",
        [("Sections", str(len(written_sections))), ("Words", f"{total_words:,}")],
    )

    return SectionWritingResult(
        report_content=report_content,
        written_sections=written_sections,
        total_words=total_words,
    )


def _resolve_report_sections_route(
    grok_writing: str,
    folder_path: str,
) -> tuple[str, object | None, object | None, float] | None:
    """Resolve writing model for report sections; None means fail-closed exit."""

    import time

    from primr.ai import stage_routing
    from primr.utils.observability import log_structured

    writing_model = grok_writing
    route = None
    usage_before = None
    route_start = time.monotonic()
    try:
        route = stage_routing.resolve_stage_model(
            "fast.report_sections",
            legacy_model_type="writing",
        )
        log_structured("info", "Report sections route selected", **route.log_metadata())
        if getattr(route, "execution_mode", "llm") == "unavailable":
            failure = stage_routing.stage_route_failure_class(route)
            stage_routing.record_stage_route_usage(
                folder_path,
                route,
                outcome="fallback",
                input_items=0,
                output_items=0,
                duration_seconds=time.monotonic() - route_start,
                failure_class=failure,
            )
            console.error(f"Report writing skipped ({failure}) — no writing backend available")
            return None
        if route.model_name:
            writing_model = route.model_name
        usage_before = stage_routing.capture_stage_usage()
    except Exception as e:
        logger.warning("Report sections route resolution failed: %s", e, exc_info=True)
    return writing_model, route, usage_before, route_start


def _record_report_sections_route(
    folder_path: str,
    route: object | None,
    *,
    usage_before: object | None,
    route_start: float,
    section_count: int,
    written_count: int,
) -> None:
    """Append body-free report-sections route metadata when a route was resolved."""

    if route is None:
        return

    import time

    from primr.ai import stage_routing

    stage_routing.record_stage_route_usage(
        folder_path,
        route,  # type: ignore[arg-type]
        outcome="selected" if written_count else "fallback",
        input_items=section_count,
        output_items=written_count,
        duration_seconds=time.monotonic() - route_start,
        failure_class=None if written_count else "no_sections_written",
        usage_delta=stage_routing.stage_usage_delta(usage_before)  # type: ignore[arg-type]
        if usage_before is not None
        else None,
    )
