"""Fast-run cross-validation + enrichment stage (roadmap #23, Batch E).

Extracted from stage 6 (Phase 5 banner) of ``perform_fast_research``. Reviews
the assembled report for weak sections and contradictions, enriches flagged
sections with targeted external evidence under a per-section deadline, splices
regenerated sections back into the report serially, and resolves contradictions
with a structure-preservation guard.

The one behavioral addition over the original verbatim extraction is the
``--budget`` checkpoints (see inline notes): this phase is optional quality
polish on an already-assembled report, so when an active run budget reaches its
ceiling, the remaining enrichment and the contradiction-resolution call are
skipped and the report ships. Gates the irreversible act (spend), never the
reasoning, mirroring the Phase-2 deepening and Phase-6 strategy checkpoints.

Tangle points handled here (refactor map #2 and #4):

- ``_enrich_section_work`` binds its queries as a default argument to defeat
  the late-binding-in-closure trap, and returns its URL discoveries
  explicitly; the merge back into the caller's ``source_urls`` /
  ``source_urls_seen`` happens in the outer loop. Those two collections are
  MUTATED IN PLACE; the caller's objects accumulate the new URLs, exactly as
  the inline code did.
- The regex splice loop is strictly serial: each regenerated section is
  spliced into ``report_content`` before the next pattern is searched, so
  later matches depend on earlier splices. Never parallelize or reorder.

Precision note: the enrichment workers call ``search_web`` /
``scrape_external_sources_validated`` with the RAW ``company_name`` (possibly
None), not the display label. This is preserved exactly, which is why this function
takes both ``company_name`` and ``company_label``.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from primr.core.report_cleanup import _preserves_report_structure
from primr.core.section_regeneration import _fast_regenerate_section
from primr.data.scrape import scrape_external_sources_validated
from primr.data.search_utils import search_web
from primr.pipeline.llm_failover import LLMRole, call_with_failover
from primr.utils.async_utils import detach_running_workers
from primr.utils.atomic_io import atomic_write_text
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured
from primr.utils.run_budget import (
    get_run_budget,
    observed_session_spend,
    skip_stage_if_over_budget,
)
from primr.utils.url_helpers import web_url_is_external

logger = get_logger("core.fast_run_validation")


@dataclass(frozen=True)
class CrossValidationResult:
    """Outputs of the cross-validation stage that the orchestrator threads onward."""

    report_content: str
    unresolved_contradictions: int
    sections_enriched: int
    cv_search_count: int


def _normalize_review_output(
    output: object,
) -> tuple[dict[str, object], bool, list[dict[str, object]], list[str]]:
    """Return bounded, type-safe findings from an untrusted model response."""
    if isinstance(output, Mapping):
        review = dict(output)
        failed = bool(review.pop("_failed", False))
    else:
        logger.warning(
            "Cross-validation returned %s instead of an object; ignoring findings",
            type(output).__name__,
        )
        review = {}
        failed = True

    raw_weak_sections = review.get("weak_sections", [])
    weak_sections = (
        [dict(item) for item in raw_weak_sections if isinstance(item, Mapping)][:3]
        if isinstance(raw_weak_sections, list)
        else []
    )
    raw_contradictions = review.get("contradictions", [])
    contradictions = (
        [item.strip() for item in raw_contradictions if isinstance(item, str) and item.strip()][:3]
        if isinstance(raw_contradictions, list)
        else []
    )
    review["weak_sections"] = weak_sections
    review["contradictions"] = contradictions
    return review, failed, weak_sections, contradictions


def _is_external_candidate(candidate: object, website: str | None) -> bool:
    """Return whether a search result is a valid URL outside the company site."""
    if not isinstance(candidate, dict):
        return False
    url = candidate.get("url")
    if not isinstance(url, str) or not url.strip():
        return False
    return web_url_is_external(url, website)


def cross_validate_and_enrich(
    *,
    company_name: str | None,
    company_label: str,
    website: str | None,
    report_content: str,
    source_urls: list[str],
    source_urls_seen: set[str],
    review_report: Callable[..., dict[str, object]],
    analysis_workbook: str,
    grok_reasoning: str,
    grok_writing: str,
    reasoning_session,
    recovery_executor,
    folder_path: str,
    total_phases: int,
) -> CrossValidationResult:
    """Review the report, enrich weak sections, resolve contradictions."""

    def _over_budget(stage_label: str) -> bool:
        """True when an active ``--budget`` has been reached.

        Spend is computed lazily only when a budget is active, so the no-budget
        path (the default) does not inspect provider usage at all.
        """
        if get_run_budget() is None:
            return False
        return skip_stage_if_over_budget(observed_session_spend(), stage_label)

    console.phase_banner(
        5,
        total_phases,
        "Cross-Validation",
        "Reviewing report for gaps and weak sections",
        "2-4 min",
    )

    from primr.ai import stage_routing

    reasoning_model = grok_reasoning
    writing_model = grok_writing
    cv_route = None
    cv_usage_before = None
    cv_route_start = time.monotonic()
    try:
        cv_route = stage_routing.resolve_stage_model(
            "fast.cross_validation",
            legacy_model_type="reasoning",
        )
        log_structured("info", "Cross-validation route selected", **cv_route.log_metadata())
        if getattr(cv_route, "execution_mode", "llm") == "unavailable":
            failure = stage_routing.stage_route_failure_class(cv_route)
            stage_routing.record_stage_route_usage(
                folder_path,
                cv_route,
                outcome="fallback",
                input_items=1,
                output_items=0,
                duration_seconds=time.monotonic() - cv_route_start,
                failure_class=failure,
            )
            console.warn(f"Cross-validation skipped ({failure}); report not quality-checked")
            return CrossValidationResult(
                report_content=report_content,
                unresolved_contradictions=0,
                sections_enriched=0,
                cv_search_count=0,
            )
        if cv_route.model_name:
            reasoning_model = cv_route.model_name
        # Writing-side regeneration reuses the writing legacy type when available.
        writing_route = stage_routing.resolve_stage_model(
            "fast.report_sections",
            legacy_model_type="writing",
        )
        if (
            writing_route.model_name
            and getattr(writing_route, "execution_mode", "llm") != "unavailable"
        ):
            writing_model = writing_route.model_name
        cv_usage_before = stage_routing.capture_stage_usage()
    except Exception as e:
        logger.warning("Cross-validation route resolution failed: %s", e, exc_info=True)

    with console.timed_operation("Reviewing report quality via Grok"):
        from primr.pipeline.integration import cross_validate_with_recovery

        def _do_cross_validate():
            return review_report(
                company_label,
                website,
                report_content,
                source_urls,
                model=reasoning_model,
                reasoning_session=reasoning_session,
            )

        _cv_stage_result = cross_validate_with_recovery(
            recovery_executor, _do_cross_validate, folder_path
        )
        if _cv_stage_result.success:
            review_output = _cv_stage_result.output
        else:
            logger.info("Cross-validation skipped: %s", _cv_stage_result.skip_reason)
            review_output = {"weak_sections": [], "contradictions": [], "_failed": True}

    cv_result, cv_failed, weak_sections, contradictions = _normalize_review_output(review_output)
    unresolved_contradictions = len(contradictions)
    sections_enriched = 0
    cv_search_count = 0

    if cv_failed:
        console.warn("Cross-validation failed; report was not quality-checked")
    elif weak_sections:
        console.ok(f"Review complete: {len(weak_sections)} section(s) flagged for enrichment")

        # Build a lookup of report headings for case-insensitive matching
        report_headings = re.findall(r"^## (.+)$", report_content, re.MULTILINE)
        heading_lookup = {h.lower().strip(): h for h in report_headings}

        # Per-section enrichment deadline. Without this, a single slow
        # query (DDG hang, slow validator, deadlocked external scrape)
        # blocked the whole cross-validation phase indefinitely. This was caught
        # twice during the v1.24.0 eval where two cells deadlocked here
        # for 12-24 hours. The inner scrape_external_sources_validated
        # call has retry/backoff but no overarching wall-clock cap, so
        # we add one at this level instead. Matches the pattern used in
        # the external-source validation pool deadline.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from concurrent.futures import TimeoutError as _FutTimeout

        from primr.pipeline.diminishing_returns import (
            DiminishingReturnsDetector,
            assess_improvement,
        )

        _enrich_section_deadline_s = 300.0  # 5 min hard cap per section
        _returns_detector = DiminishingReturnsDetector()
        for ws in weak_sections:
            # --budget checkpoint: enriching a weak section issues external
            # searches and a regeneration LLM call (real spend). Enrichment is
            # optional polish on the already-assembled report, so once an active
            # --budget ceiling is reached we stop enriching further sections and
            # ship rather than spend past the cap. Gates the irreversible act
            # (spend), never the reasoning.
            if _over_budget("remaining cross-validation enrichment"):
                break

            raw_title = str(ws.get("title", "")).lstrip("#").strip()
            raw_queries = ws.get("queries", [])
            queries = [str(q) for q in raw_queries[:3]] if isinstance(raw_queries, list) else []

            if not raw_title or not queries:
                continue

            # Case-insensitive heading match
            section_title = heading_lookup.get(raw_title.lower(), raw_title)

            # Search for additional evidence, wrapped in a future so a
            # hung sub-call can be abandoned without blocking the whole
            # cross-validation phase. `_queries` is bound as a default arg
            # to defeat the late-binding-in-closure trap (otherwise each
            # iteration's submitted worker would capture the same `queries`
            # name and see whatever it resolves to at call time).
            def _enrich_section_work(
                _queries: list[str] = queries,
            ) -> tuple[list[str], int, list[str], set[str]]:
                local_evidence: list[str] = []
                local_new_sources = 0
                local_urls: list[str] = []
                local_urls_seen: set[str] = set()
                for q in _queries:
                    results = search_web(q, company_name, website)
                    if not results:
                        continue
                    filtered = [
                        r
                        for r in results[:3]
                        if _is_external_candidate(r, website)
                        and r["url"] not in source_urls_seen
                        and r["url"] not in local_urls_seen
                    ]
                    scraped = scrape_external_sources_validated(
                        filtered,
                        company_name=company_name,
                        website=website,
                        max_sources=3,
                    )
                    for url, content in scraped.items():
                        if url in source_urls_seen or url in local_urls_seen:
                            continue
                        local_urls.append(url)
                        local_urls_seen.add(url)
                        local_evidence.append(f"[Source: {url}]\n{content[:12_000]}")
                        local_new_sources += 1
                return local_evidence, local_new_sources, local_urls, local_urls_seen

            new_evidence_parts: list[str] = []
            cv_new_sources = 0
            _enrich_pool = ThreadPoolExecutor(max_workers=1)
            cv_search_count += len(queries)  # count queries even if abandoned
            with console.timed_operation(f"Enriching: {section_title}"):
                fut = _enrich_pool.submit(_enrich_section_work)
                try:
                    # Single-future as_completed with deadline. Raises
                    # TimeoutError if the worker hasn't finished in time.
                    for completed in as_completed([fut], timeout=_enrich_section_deadline_s):
                        (
                            _evidence,
                            _new_count,
                            _urls,
                            _seen,
                        ) = completed.result()
                        new_evidence_parts = _evidence
                        cv_new_sources = _new_count
                        # Merge per-section URL tracking back into outer scope
                        for url in _urls:
                            if url not in source_urls_seen:
                                source_urls.append(url)
                                source_urls_seen.add(url)
                except _FutTimeout:
                    console.warn(
                        f"Enrichment deadline ({int(_enrich_section_deadline_s)}s) "
                        f"exceeded for '{section_title}'; abandoning this section "
                        f"and continuing"
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        "Enrichment worker for %s failed: %s",
                        section_title,
                        e,
                    )
                    continue
                finally:
                    _enrich_pool.shutdown(wait=False, cancel_futures=True)
                    detach_running_workers(_enrich_pool)

            if not new_evidence_parts:
                continue

            new_evidence = "\n\n".join(new_evidence_parts)

            # Find the original section content in the report
            section_pattern = re.compile(
                rf"(## {re.escape(section_title)}\n.*?)(?=\n## |\Z)",
                re.DOTALL,
            )
            match = section_pattern.search(report_content)
            if not match:
                log_structured(
                    "warning",
                    "Cross-validation: section not found in report",
                    section=section_title,
                )
                continue

            original_section = match.group(1)

            # Re-generate the section with new evidence
            with console.timed_operation(f"Rewriting: {section_title}"):
                regenerated = _fast_regenerate_section(
                    company_label,
                    website,
                    section_title,
                    original_section,
                    analysis_workbook,
                    new_evidence,
                    source_urls,
                    model=writing_model,
                )

            # Splice back into report (preserve \n\n separator between sections)
            if regenerated and regenerated != original_section:
                if not regenerated.endswith("\n"):
                    regenerated += "\n"
                report_content = (
                    report_content[: match.start()] + regenerated + report_content[match.end() :]
                )
                sections_enriched += 1
                console.ok(f"Enriched: {section_title} ({cv_new_sources} new source(s))")

            # Diminishing-returns check: stop the regeneration loop early
            # when consecutive rewrites stop producing real improvement,
            # rather than spending the full token budget on the tail.
            _returns_detector.record(
                assess_improvement(section_title, original_section, regenerated or "")
            )
            if _returns_detector.should_stop():
                console.warn(_returns_detector.stop_reason())
                log_structured(
                    "info",
                    "Cross-validation regeneration stopped early",
                    **{k: v for k, v in _returns_detector.summary().items() if k != "per_section"},
                )
                break

        cv_result["diminishing_returns"] = _returns_detector.summary()
    else:
        console.ok("Review complete: no sections flagged for enrichment")

    if contradictions:
        for c in contradictions:
            console.info(f"Contradiction noted: {c[:100]}")

    # --budget checkpoint: contradiction resolution is one more WRITING call (an
    # optional standardization edit). Skip it when an active --budget ceiling is
    # reached and ship the report with contradictions noted but unresolved.
    if contradictions and not _over_budget("contradiction resolution"):
        # Resolve contradictions by asking Grok to standardize
        try:
            contradiction_list = "\n".join(f"- {c}" for c in contradictions)
            resolve_prompt = f"""You are editing a strategic report about {company_label}.

The cross-validation pass found these contradictions between sections:

{contradiction_list}

For EACH contradiction:
1. Determine which value has the strongest source/evidence
2. Standardize the report to use that value consistently
3. Add a confidence label if the value is uncertain

RULES:
- Do NOT delete, summarize, or condense any sections, paragraphs, or content
- Make ONLY surgical edits to the specific contradictory values/numbers
- Do NOT rewrite prose; change only the conflicting data points
- When evidence is ambiguous, use the most conservative estimate with a range
- Add "(Estimated)" or "(Reported)" labels to standardized values
- Preserve all ## headings, [cite: N] references, and structure
- Output MUST contain at least 98% of the original word count

Return the COMPLETE corrected report with all sections intact. No preamble.

--- REPORT ---
{report_content}
--- END ---"""

            resolved = call_with_failover(
                LLMRole.WRITING,
                resolve_prompt,
                preferred_model=writing_model,
                max_tokens=65_000,
                temperature=0.2,
                system_prompt="You are a fact-checker standardizing contradictory data points across report sections.",
            )
            if resolved and resolved.strip():
                resolved_words = len(resolved.split())
                original_words = len(report_content.split())
                if _preserves_report_structure(report_content, resolved):
                    report_content = resolved
                    unresolved_contradictions = 0
                    console.ok(f"Resolved {len(contradictions)} contradiction(s)")
                else:
                    logger.warning(
                        "Contradiction resolution changed structure too much (%d to %d words or headings changed), keeping original",
                        original_words,
                        resolved_words,
                    )
        except Exception as resolve_err:
            logger.warning("Contradiction resolution failed: %s", resolve_err)

    # This diagnostic is optional. A persistence failure must not discard the report.
    cv_output_path = Path(folder_path) / "cross_validation.json"
    try:
        atomic_write_text(cv_output_path, json.dumps(cv_result, indent=2) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Cross-validation diagnostic could not be persisted: %s", exc)

    # Extract section count from report for metrics
    report_section_count = len(re.findall(r"^## ", report_content, re.MULTILINE))
    cv_stats = [
        ("Sections reviewed", str(report_section_count)),
        ("Enriched", str(sections_enriched)),
    ]
    if cv_failed:
        cv_stats.append(("Status", "FAILED"))
    console.phase_complete("Cross-Validation", cv_stats)

    if cv_route is not None:
        from primr.ai import stage_routing as stage_routing_mod

        stage_routing_mod.record_stage_route_usage(
            folder_path,
            cv_route,
            outcome="fallback" if cv_failed else "selected",
            input_items=1,
            output_items=sections_enriched + (0 if unresolved_contradictions else 1),
            duration_seconds=time.monotonic() - cv_route_start,
            failure_class="cross_validation_failed" if cv_failed else None,
            usage_delta=stage_routing_mod.stage_usage_delta(cv_usage_before)
            if cv_usage_before is not None
            else None,
        )

    return CrossValidationResult(
        report_content=report_content,
        unresolved_contradictions=unresolved_contradictions,
        sections_enriched=sections_enriched,
        cv_search_count=cv_search_count,
    )
