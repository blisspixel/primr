"""Fast-run research-deepening stage (roadmap #23, Batch F).

Extracted verbatim from stage 3 (Phase 2 banner) of ``perform_fast_research``
— no behavior change. Asks the reasoning model for research gaps, searches the
gap queries in parallel, validates candidate sources under a hard deadline,
and rebuilds the external-sources bundle + insights file with whatever landed.

Tangle points handled here (refactor map #1 and #7):

- ``source_urls`` / ``source_urls_seen`` / ``external_text_parts`` /
  ``external_raw_parts`` are MUTATED IN PLACE — the caller's collections
  accumulate the new sources (O(1) ``source_urls_seen`` dedup preserved), and
  ``external_sources_raw`` / ``combined_insights`` are REBUILT (not mutated)
  via ``insights_assembly`` and returned.
- The validation pool uses the deadline + shutdown pattern copied precisely:
  ``shutdown(wait=False, cancel_futures=True)`` + ``detach_running_workers``
  so a hung worker can't block process exit.

Precision note: the search/scrape calls use the RAW ``company_name``
(possibly None) while the gap-analysis prompt uses the display label — this
function takes both, mirroring fast_run_validation.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from primr.core.insights_assembly import build_combined_insights, build_external_sources_raw
from primr.core.run_state_io import _update_run_state
from primr.data.scrape import scrape_external_sources_validated
from primr.data.search_utils import search_web
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured

logger = get_logger("core.fast_run_gaps")


@dataclass(frozen=True)
class GapDeepeningResult:
    """Outputs of the research-deepening stage that the orchestrator threads onward."""

    external_sources_raw: str
    combined_insights: str
    gap_new_sources: int
    gap_search_count: int


def deepen_research(
    *,
    company_name: str | None,
    company_label: str,
    website: str | None,
    raw_corpus: str,
    external_sources_raw: str,
    combined_insights: str,
    summarized: str,
    hiring_block: str,
    source_urls: list[str],
    source_urls_seen: set[str],
    external_text_parts: list[str],
    external_raw_parts: list[str],
    grok_reasoning: str,
    folder_path: str,
    insights_file: str,
    total_phases: int,
    hypothesis_block: str = "",
) -> GapDeepeningResult:
    """Identify research gaps, search + validate new sources, rebuild insights.

    When ``hypothesis_block`` is supplied (a framed run's Day-1 tree), gap
    analysis is steered to generate queries that *test under-evidenced branches*
    rather than fill generic data gaps (tradecraft Step 4). Empty -> unchanged.
    """
    # --budget checkpoint: research deepening issues additional gap searches and
    # external-source scrapes (real spend). When a run budget is active and
    # actual LLM spend has already reached the ceiling, skip deepening and ship
    # with the sources already collected rather than spending past the cap.
    # Mirrors the Phase-6 strategy checkpoint: the irreversible act (spend) is
    # gated, never the reasoning.
    from primr.utils.run_budget import get_run_budget

    _run_budget = get_run_budget()
    if _run_budget is not None:
        from primr.core.research_agent import _compute_session_llm_cost

        _spent_so_far = _compute_session_llm_cost()
        _run_budget.sync_spend(_spent_so_far)
        if _run_budget.exceeded():
            console.warn(
                f"Run budget ${_run_budget.max_cost:.2f} reached "
                f"(~${_spent_so_far:.2f} spent) — skipping research deepening"
            )
            with open(os.path.join(folder_path, "gap_analysis.md"), "w", encoding="utf-8") as f:
                f.write("(research deepening skipped: run budget reached)")
            _update_run_state(
                folder_path,
                gap_queries=0,
                gap_new_sources=0,
                external_sources_validated=len(source_urls),
            )
            return GapDeepeningResult(
                external_sources_raw=external_sources_raw,
                combined_insights=combined_insights,
                gap_new_sources=0,
                gap_search_count=0,
            )

    console.phase_banner(
        2,
        total_phases,
        "Research Deepening",
        "Identifying gaps and searching for additional evidence",
        "3-5 min",
    )

    with console.timed_operation("Analyzing research gaps via Grok"):
        gap_queries, gap_text = _fast_gap_analysis(
            company_label,
            website,
            raw_corpus,
            external_sources_raw,
            source_urls,
            model=grok_reasoning,
            hypothesis_block=hypothesis_block,
        )

    gap_new_sources = 0
    gap_search_count = 0

    if gap_queries:
        console.ok(f"Gap analysis: {len(gap_queries)} questions identified")
        max_gap_sources = 10

        _gap_start = time.time()

        def _gap_search_one(gq: str) -> list[dict]:
            """Search for a single gap query (thread-safe HTTP call)."""
            results = search_web(gq, company_name, website)
            if not results:
                return []
            return [
                r
                for r in results[:3]
                if (not website or website.lower() not in r.get("url", "").lower())
                and r.get("url", "") not in source_urls_seen
            ]

        # Phase 1: parallel searches (thread-safe HTTP calls)
        gap_search_results: list[dict] = []
        _gap_queries_done = 0
        console.status(f"Searching for gap-filling sources (0/{len(gap_queries)} queries)")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(_gap_search_one, gq) for gq in gap_queries]
            for future in as_completed(futures):
                try:
                    gap_search_results.extend(future.result())
                except Exception as e:
                    logger.warning("Gap search query failed: %s", e)
                _gap_queries_done += 1
                console.status(
                    f"Searching for gap-filling sources ({_gap_queries_done}/{len(gap_queries)} queries, {len(gap_search_results)} results)"
                )

        # Record how many gap searches we actually issued, so the usage
        # telemetry total (search_queries) includes them — gap_search_count
        # was previously summed into that total but never assigned.
        gap_search_count = _gap_queries_done

        # Phase 2: parallel validation with a hard attempt cap (same
        # design as the main external-source pass: 4 workers, cap at
        # 2x the target to bound runtime on noisy searches).
        _gap_candidates: list[dict] = []
        _gap_seen: set[str] = set()
        for result in gap_search_results:
            url = result.get("url")
            if not url or url in source_urls_seen or url in _gap_seen:
                continue
            _gap_seen.add(url)
            _gap_candidates.append(result)

        # Same 1.6x sizing as the main external pass — see comment there.
        _gap_attempt_cap = max(10, int(max_gap_sources * 1.6))
        _gap_candidates = _gap_candidates[:_gap_attempt_cap]
        _gap_check_idx = 0

        def _validate_gap_source(res: dict) -> dict[str, str]:
            return scrape_external_sources_validated(
                [res],
                company_name=company_name,
                website=website,
                max_sources=1,
            )

        # Same deadline pattern as the main external-source validation —
        # a hung worker can't block shutdown forever.
        _gap_deadline_s = 420.0  # 7 min total across all workers
        _gap_pool = ThreadPoolExecutor(max_workers=4)
        gap_futures = {_gap_pool.submit(_validate_gap_source, r): r for r in _gap_candidates}
        try:
            for fut in as_completed(gap_futures, timeout=_gap_deadline_s):
                _gap_check_idx += 1
                if gap_new_sources >= max_gap_sources:
                    break
                console.status(
                    f"Validating gap sources ({gap_new_sources} found, "
                    f"checking {_gap_check_idx}/{len(_gap_candidates)})"
                )
                try:
                    scraped = fut.result(timeout=0)
                except Exception as e:
                    logger.debug("Gap validation worker failed: %s", e)
                    continue
                for scraped_url, content in scraped.items():
                    if gap_new_sources >= max_gap_sources:
                        break
                    if scraped_url not in source_urls_seen:
                        source_urls.append(scraped_url)
                        source_urls_seen.add(scraped_url)
                        external_text_parts.append(f"[Source: {scraped_url}]\n{content[:12_000]}")
                        external_raw_parts.append(f"[Source: {scraped_url}]\n{content[:20_000]}")
                        gap_new_sources += 1
        except TimeoutError:
            console.warn(
                f"Gap-filling deadline ({int(_gap_deadline_s)}s) reached — "
                f"continuing with {gap_new_sources} new sources "
                f"({_gap_check_idx}/{len(_gap_candidates)} workers checked)"
            )
        finally:
            from primr.utils.async_utils import detach_running_workers

            _gap_pool.shutdown(wait=False, cancel_futures=True)
            detach_running_workers(_gap_pool)

        console.ok(f"Searching for gap-filling sources ({console._elapsed(_gap_start)})")

        console.ok(f"Found {gap_new_sources} additional sources")

        # Rebuild external_sources_raw with the new sources and refresh
        # the insights file. The previous combined_insights is the
        # rebuild fallback so a degenerate refresh never erases data.
        external_sources_raw = build_external_sources_raw(external_raw_parts, hiring_block)
        combined_insights = build_combined_insights(
            summarized,
            external_text_parts,
            hiring_block,
            fallback=combined_insights,
        )
        with open(insights_file, "w", encoding="utf-8") as f:
            f.write(combined_insights)
    else:
        # Distinguish between "no gaps found" (good) and "gap analysis failed" (bad)
        if gap_text and "failed" in gap_text.lower():
            console.warn(f"Gap analysis failed — skipping research deepening ({gap_text})")
        else:
            console.info("Gap analysis found no research gaps — skipping")

    # Save gap analysis output to working folder
    gap_analysis_path = os.path.join(folder_path, "gap_analysis.md")
    with open(gap_analysis_path, "w", encoding="utf-8") as f:
        f.write(gap_text if gap_text else "(no gap analysis performed)")

    total_external = len(source_urls)
    _update_run_state(
        folder_path,
        gap_queries=len(gap_queries or []),
        gap_new_sources=gap_new_sources,
        external_sources_validated=total_external,
    )
    console.phase_complete(
        "Research Deepening",
        [("New sources", str(gap_new_sources)), ("Total external", str(total_external))],
    )

    return GapDeepeningResult(
        external_sources_raw=external_sources_raw,
        combined_insights=combined_insights,
        gap_new_sources=gap_new_sources,
        gap_search_count=gap_search_count,
    )


def _fast_gap_analysis(
    company_name: str,
    website: str | None,
    raw_corpus: str,
    external_sources: str,
    source_urls: list[str],
    model: str | None = None,
    hypothesis_block: str = "",
) -> tuple[list[str], str]:
    """
    Phase 2 helper: Grok identifies research gaps and returns targeted search queries.

    When ``hypothesis_block`` is supplied (a framed run's Day-1 tree), the task is
    reframed from "what data is missing" to "which working hypotheses are
    under-evidenced, and what search would confirm or refute each" (tradecraft
    Step 4). The output contract (GAP/QUERY/PRIORITY) is unchanged either way, and
    the unframed prompt is byte-identical to the prior behavior.

    Returns:
        (list of search queries, gap analysis text for logging)
    """

    # Build corpus summary — first 500 chars of each page
    corpus_lines = raw_corpus.split("\n\n")
    corpus_summary_parts: list[str] = []
    for block in corpus_lines:
        if block.startswith("[Page:"):
            corpus_summary_parts.append(block[:500])
    corpus_summary = (
        "\n\n".join(corpus_summary_parts[:80]) if corpus_summary_parts else raw_corpus[:30_000]
    )

    # Build external source summary — first 500 chars each
    ext_lines = external_sources.split("\n\n")
    ext_summary_parts: list[str] = []
    for block in ext_lines:
        if block.startswith("[Source:"):
            ext_summary_parts.append(block[:500])
    ext_summary = "\n\n".join(ext_summary_parts) if ext_summary_parts else external_sources[:5_000]

    if hypothesis_block:
        # Hypothesis-steered (tradecraft Step 4): queries test branches, not data gaps.
        prompt = f"""You've reviewed primary sources for {company_name}. As a strategic analyst,
find where the WORKING HYPOTHESES below are under-evidenced, and for each, the web
search that would best CONFIRM OR REFUTE it. Prefer diagnostic evidence (which
discriminates between competing explanations) over generic background; a branch with
no supporting or counter evidence in the sources is the top priority to test.

WORKING HYPOTHESES (test these, do not just describe the company):
{hypothesis_block}

SOURCES REVIEWED:
{corpus_summary}

EXTERNAL SOURCES:
{ext_summary}

KNOWN SOURCE URLS (do NOT repeat these):
{chr(10).join(source_urls[:30])}

Return exactly 8 items in this format (one per block, no extra text):
GAP: [which hypothesis or sub-claim is under-evidenced]
QUERY: [web search query that would confirm or refute it]
PRIORITY: CRITICAL | IMPORTANT

Prioritize third-party validation sources: analyst reports, industry publications,
financial filings, customer case studies, employee reviews, regulatory documents.
"""
    else:
        prompt = f"""You've reviewed primary sources for {company_name}. As a strategic analyst, identify
what's MISSING — gaps that would weaken a consulting brief.

SOURCES REVIEWED:
{corpus_summary}

EXTERNAL SOURCES:
{ext_summary}

KNOWN SOURCE URLS (do NOT repeat these):
{chr(10).join(source_urls[:30])}

Return exactly 8 items in this format (one per block, no extra text):
GAP: [what's missing]
QUERY: [web search query to fill it]
PRIORITY: CRITICAL | IMPORTANT

Prioritize third-party validation sources: analyst reports, industry publications,
financial filings, customer case studies, employee reviews, regulatory documents.
Also cover: financials, competitive positioning, leadership changes, customer evidence,
technology direction, recent news, risk factors.
"""

    system_prompt = (
        "You are a research gap analyst for a consulting firm. "
        "Identify what's missing from preliminary research and suggest "
        "targeted web searches to fill those gaps. Be specific and actionable."
    )

    # Gap analysis is a REASONING-class call: a quota event here would
    # silently abort gap-driven external search. Route through the
    # circuit breaker so we fall through ANALYSIS_FALLBACK_CHAIN.
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    try:
        response = call_with_failover(
            LLMRole.REASONING,
            prompt,
            preferred_model=model,
            max_tokens=5_000,
            temperature=0.4,
            system_prompt=system_prompt,
        )
    except Exception as e:
        log_structured("warning", "Gap analysis failed", error=str(e))
        return [], f"Gap analysis failed: {e}"

    if not response or not response.strip():
        return [], "Gap analysis returned empty response"

    # Parse queries from response
    queries: list[str] = []
    for line in response.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("QUERY:"):
            query = line[6:].strip().strip("\"'[]")
            if query:
                queries.append(query)

    return queries[:8], response
