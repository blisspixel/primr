"""Fast-run data-collection stage (roadmap #23, Batch G — the last stage out).

Extracted verbatim from stage 1 (Phase 1 banner) of ``perform_fast_research``
— no behavior change. Scrapes the website, summarizes it, builds the raw
corpus, calibrates external-search depth adaptively, runs the parallel
external search + validation pools under the 600s deadline, applies the
quality filter, and seeds the source pools every later stage reads or
mutates.

Structural notes:

- This stage CREATES the recovery executor (pipeline resilience listener +
  executor) that stages 4/5/6/9 consume — it is returned on the result and
  threaded onward by the orchestrator.
- It also creates the four source pools (``source_urls``,
  ``source_urls_seen``, ``external_text_parts``, ``external_raw_parts``)
  that the gap-deepening and cross-validation stages later MUTATE IN PLACE.
  The result carries the same objects, preserving the mutation chain.
- The validation pool uses the deadline + shutdown pattern copied precisely
  (tangle #7): ``shutdown(wait=False, cancel_futures=True)`` +
  ``detach_running_workers`` so a hung worker can't block process exit.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from primr.ai.summarize import summarize_scraped_content
from primr.core.resilience_listeners import _build_resilience_event_listener
from primr.core.run_state_io import _update_run_state
from primr.data.scrape import fetch_web_content, scrape_external_sources_validated
from primr.data.search_utils import generate_external_search_queries, search_web
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured

logger = get_logger("core.fast_run_collection")


@dataclass(frozen=True)
class DataCollectionResult:
    """Outputs of the data-collection stage.

    ``source_urls`` / ``source_urls_seen`` / ``external_text_parts`` /
    ``external_raw_parts`` are the live pool objects later stages mutate.
    ``recovery_executor`` is the pipeline resilience executor constructed
    here and consumed by the workbook, section-writing, cross-validation,
    and strategy stages.
    """

    scraped_data: dict[str, str]
    pages_scraped: int
    summarized: str
    raw_corpus: str
    total_scraped_chars: int
    external_data: dict
    external_query_count: int
    source_urls: list[str] = field(default_factory=list)
    source_urls_seen: set[str] = field(default_factory=set)
    external_text_parts: list[str] = field(default_factory=list)
    external_raw_parts: list[str] = field(default_factory=list)
    recovery_executor: Any = None


def collect_research_data(
    *,
    company_name: str | None,
    website: str | None,
    folder_path: str,
    total_phases: int,
) -> DataCollectionResult:
    """Scrape the site, search + validate external sources, seed the pools."""
    # Lazy import: research_agent imports this module, so the LLM-backed
    # relevance filter (which stays there until its own extraction) must be
    # resolved at call time to avoid a circular import.
    from primr.core.research_agent import _assess_source_relevance

    scan_domain = urlparse(website or "").netloc.replace("www.", "") if website else "website"
    console.phase_banner(
        1,
        total_phases,
        "Data Collection (fast)",
        f"Scraping {scan_domain} + external sources",
        "5-8 min",
    )

    # Scrape website (50 pages for enhanced fast mode)
    with console.timed_operation(f"Website scrape ({scan_domain})", show_spinner=False):
        scraped_data = (
            fetch_web_content(website, company_name, max_pages=50, working_folder=folder_path)
            if website
            else {}
        )
        pages_scraped = len(scraped_data)
    log_structured("info", "Fast mode: website scraping complete", pages=pages_scraped)

    if pages_scraped == 0 and website:
        console.warn("Limited website access — report will rely on web research")

    # Summarize scraped content with Flash (for insights.txt working file)
    summarized = ""
    if scraped_data:
        with console.timed_operation("Extracting insights"):
            summarized = summarize_scraped_content(company_name, website, scraped_data, folder_path)

    # Build raw corpus from scraped data (truncate each page to 30k chars)
    raw_corpus_parts: list[str] = []
    for url, content in scraped_data.items():
        truncated = content[:30_000] if len(content) > 30_000 else content
        raw_corpus_parts.append(f"[Page: {url}]\n{truncated}")
    raw_corpus = "\n\n".join(raw_corpus_parts) if raw_corpus_parts else ""

    # Adaptive depth: assess data richness to calibrate search effort
    total_scraped_chars = sum(len(v or "") for v in scraped_data.values())
    if total_scraped_chars > 200_000 and pages_scraped > 30:
        # Rich website — data is abundant; a small number of high-signal
        # externals is enough for cross-validation.
        _search_depth = "rich"
        _ext_query_count = 8
        _max_ext = 12
        log_structured(
            "info",
            "Adaptive depth: rich website, reducing external search",
            pages=pages_scraped,
            chars=total_scraped_chars,
        )
    elif total_scraped_chars < 20_000:
        # Thin website — compensate with more externals, but not a firehose.
        # Fallback_sources already filled in EDGAR / Wikipedia / IR if the
        # main site was blocked; we don't need to re-validate 40 DDG hits.
        _search_depth = "thin"
        _ext_query_count = 12
        _max_ext = 22
        console.info(
            f"Thin website data ({pages_scraped} pages, {total_scraped_chars} chars) "
            "— increasing external search depth"
        )
        log_structured(
            "info",
            "Adaptive depth: thin website, increasing external search",
            pages=pages_scraped,
            chars=total_scraped_chars,
        )
    else:
        # Normal — 18 validated externals is plenty for a 23-section brief.
        _search_depth = "normal"
        _ext_query_count = 10
        _max_ext = 18

    # External research (adaptive query count)
    source_urls: list[str] = []
    source_urls_seen: set[str] = set()  # O(1) dedup across phases
    external_text_parts: list[str] = []
    external_raw_parts: list[str] = []
    external_queries = generate_external_search_queries(
        company_name,
        website,
        max_queries=_ext_query_count,
    )
    external_data: dict = {}
    max_external_sources = _max_ext
    _ext_search_start = time.time()

    def _search_one(query: str) -> list[dict]:
        """Search for a single query (thread-safe HTTP call)."""
        results = search_web(query, company_name, website)
        if not results:
            return []
        return [
            r for r in results[:5] if not website or website.lower() not in r.get("url", "").lower()
        ]

    # Phase 1: parallel searches (thread-safe HTTP calls)
    console.status(f"Searching external sources (0/{len(external_queries)} queries)")
    all_search_results: list[dict] = []
    _queries_done = 0
    _queries_failed = 0
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_search_one, q) for q in external_queries]
        for future in as_completed(futures):
            try:
                all_search_results.extend(future.result())
            except Exception as e:
                _queries_failed += 1
                logger.warning("External search query failed: %s", e)
            _queries_done += 1
            console.status(
                f"Searching external sources ({_queries_done}/{len(external_queries)} queries, {len(all_search_results)} results)"
            )

    if _queries_failed > 0:
        console.warn(
            f"{_queries_failed}/{len(external_queries)} search queries failed"
            " — external source coverage may be reduced"
        )
        log_structured(
            "warning",
            "External search queries failed",
            failed=_queries_failed,
            total=len(external_queries),
        )

    # Phase 2: parallel validation with a hard attempt cap.
    # External validation used to iterate *every* search result serially,
    # which on noisy queries meant 75-150+ Grok validation calls and 20+
    # minutes of wall time. We now:
    #   - hard-cap attempts at max_external_sources * 2 (empirically
    #     enough to fill the quota on any reasonable rejection rate)
    #   - run 4 attempts in parallel (external scrape now uses a
    #     Patchright-free orchestrator, so no browser contention)
    from primr.pipeline.integration import create_pipeline_executor, scrape_page_with_recovery

    _resilience_listener = _build_resilience_event_listener(folder_path)
    _recovery_executor = create_pipeline_executor(folder_path, event_listener=_resilience_listener)

    # Deduplicate and cap candidate list up front.
    _candidates: list[dict] = []
    _seen_candidate_urls: set[str] = set()
    for result in all_search_results:
        url = result.get("url")
        if not url or url in _seen_candidate_urls or url in external_data:
            continue
        _seen_candidate_urls.add(url)
        _candidates.append(result)

    # Attempt cap sized at 1.6x the quota. Empirically ~35% of DDG
    # results get LLM-rejected as "wrong company" (similar-name but
    # unrelated business), so 1.6x fills the quota in the normal case
    # while keeping total work bounded. Was 2x before 1.19.1 — that
    # was overcautious and turned a 20-source quota into a 60-HTTP-call
    # validation marathon on companies with lots of hits (any large,
    # well-known brand with a heavily-indexed web presence).
    _attempt_cap = max(12, int(max_external_sources * 1.6))
    _candidates = _candidates[:_attempt_cap]
    _scrape_total = len(_candidates)
    _failed_scrape_urls: list[str] = []
    _completed_checks = 0

    def _do_scrape(_r: dict, _u: str):
        wrapped = lambda: scrape_external_sources_validated(  # noqa: E731
            [_r],
            company_name=company_name,
            website=website,
            max_sources=1,
        )
        return scrape_page_with_recovery(_recovery_executor, wrapped, _u, folder_path)

    # Total wall-clock deadline for this phase. A single hung worker
    # (stuck HTTP, stuck Grok validation call) used to block the whole
    # pipeline because ThreadPoolExecutor's __exit__ waits for every
    # running thread to finish and fut.cancel() only cancels queued
    # work. Deadline + manual shutdown(wait=False, cancel_futures=True)
    # lets us abandon stuck workers and move on.
    _validation_deadline_s = 600.0  # 10 min total across all workers
    _val_pool = ThreadPoolExecutor(max_workers=4)
    _val_futures = {
        _val_pool.submit(_do_scrape, result, result["url"]): result for result in _candidates
    }
    _val_abandoned = False
    try:
        for fut in as_completed(_val_futures, timeout=_validation_deadline_s):
            _completed_checks += 1
            if len(external_data) >= max_external_sources:
                # Enough accepted sources — stop waiting for the rest.
                break
            result = _val_futures[fut]
            url = result["url"]
            console.status(
                f"Validating external sources ({len(external_data)} validated, "
                f"checking {_completed_checks}/{_scrape_total})"
            )
            try:
                scrape_result = fut.result(timeout=0)
            except Exception as e:
                logger.debug("External validation worker failed for %s: %s", url, e)
                continue
            if scrape_result.success and scrape_result.output:
                external_data.update(scrape_result.output)
            elif scrape_result.skipped:
                _failed_scrape_urls.append(url)
                logger.info("Scrape skipped for %s: %s", url, scrape_result.skip_reason)
    except TimeoutError:
        _val_abandoned = True
        console.warn(
            f"External validation deadline ({int(_validation_deadline_s)}s) reached — "
            f"continuing with {len(external_data)} validated sources "
            f"({_completed_checks}/{_scrape_total} workers checked)"
        )
    finally:
        # Don't block on hung threads — cancel queued work and detach
        # still-running workers from the stdlib atexit join hook so
        # they can't hang the process at interpreter shutdown.
        from primr.utils.async_utils import detach_running_workers

        _val_pool.shutdown(wait=False, cancel_futures=True)
        detach_running_workers(_val_pool)

    if _val_abandoned:
        _update_run_state(
            folder_path,
            external_validation_abandoned=True,
            external_validation_completed=_completed_checks,
            external_validation_total=_scrape_total,
        )

    # Log failed pages in run state (Req 2.3)
    if _failed_scrape_urls:
        _update_run_state(folder_path, failed_scrape_urls=_failed_scrape_urls)

    console.ok(f"Searching external sources ({console._elapsed(_ext_search_start)})")

    # Adaptive quality filter: drop low-relevance sources
    pre_filter_count = len(external_data)
    external_data = _assess_source_relevance(company_name, external_data)
    if len(external_data) < pre_filter_count:
        console.info(
            f"Quality filter: {pre_filter_count} -> {len(external_data)} sources (dropped {pre_filter_count - len(external_data)} low-relevance)"
        )

    for url, content in external_data.items():
        source_urls.append(url)
        source_urls_seen.add(url)
        external_text_parts.append(f"[Source: {url}]\n{content[:12_000]}")
        external_raw_parts.append(f"[Source: {url}]\n{content[:20_000]}")

    log_structured("info", "Fast mode: external sources complete", sources=len(external_data))
    _update_run_state(
        folder_path,
        pages_scraped=pages_scraped,
        website_chars=total_scraped_chars,
        external_sources_initial=len(external_data),
        search_depth=_search_depth,
    )
    console.phase_complete(
        "Data Collection (fast)",
        [("Pages", str(pages_scraped)), ("External", str(len(external_data)))],
    )

    return DataCollectionResult(
        scraped_data=scraped_data,
        pages_scraped=pages_scraped,
        summarized=summarized,
        raw_corpus=raw_corpus,
        total_scraped_chars=total_scraped_chars,
        external_data=external_data,
        external_query_count=len(external_queries),
        source_urls=source_urls,
        source_urls_seen=source_urls_seen,
        external_text_parts=external_text_parts,
        external_raw_parts=external_raw_parts,
        recovery_executor=_recovery_executor,
    )
