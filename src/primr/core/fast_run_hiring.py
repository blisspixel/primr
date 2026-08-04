"""Hiring-signals stage (fast pipeline + Deep Research paths).

Extracted verbatim from stage 2 of ``perform_fast_research`` — no behavior
change. Discovers open job postings via the ATS fan-out, extracts strategic
signals, and renders the hiring block that rides along through BOTH the
initial insights build and the Phase 2 gap-filling rebuild so it survives
every refresh of ``insights.txt`` and the raw external-sources bundle.
The Deep Research paths (premium / --mode deep) consume the same stage via
``collect_fenced_hiring_block``, which fences the block for the stage-1
context boundary (the fast path fences it later, inside the corpus bundles).

Side effects preserved from the original: console announcements, run-state
update (postings found/selected/extracted + slug), and the ``_hiring/``
artifacts written by ``gather_hiring_signals`` itself. Ordinary discovery and
extraction errors degrade to an empty hiring block. A typed local-capacity busy
result propagates so an external caller can honor its bounded retry guidance.
"""

from __future__ import annotations

from primr.ai.provider_availability import LocalCapacityBusyError
from primr.core.run_state_io import _update_run_state
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("core.fast_run_hiring")


def collect_hiring_block(
    *,
    company_label: str,
    website: str | None,
    scraped_data: dict[str, str],
    folder_path: str,
) -> str:
    """Gather hiring signals and return the prompt-ready hiring block ('' if none)."""
    hiring_block = ""
    try:
        from primr.data.hiring_signals import gather_hiring_signals, render_for_prompt

        console.info("Hiring Signals — scanning for open job postings")
        hiring_signals = gather_hiring_signals(
            company_label,
            website,
            corpus=scraped_data,
            working_folder=folder_path,
        )
    except LocalCapacityBusyError:
        raise
    except Exception as e:
        logger.warning("Hiring signals stage failed: %s", e)
        hiring_signals = None

    if hiring_signals and not hiring_signals.is_empty():
        console.ok(
            f"Hiring Signals: {hiring_signals.postings_extracted} postings analysed via "
            f"{hiring_signals.source} "
            f"({len(hiring_signals.tech_stack)} tech items, "
            f"{len(hiring_signals.strategic_initiatives)} initiatives)",
            show_time=False,
        )
        _update_run_state(
            folder_path,
            hiring_signals={
                "source": hiring_signals.source,
                "postings_found": hiring_signals.postings_found,
                "postings_selected": hiring_signals.postings_selected,
                "postings_extracted": hiring_signals.postings_extracted,
                "company_slug": hiring_signals.company_slug,
            },
        )
        hiring_block = "=== HIRING SIGNALS ===\n" + render_for_prompt(hiring_signals)
        _refresh_working_brief_hiring(
            folder_path=folder_path,
            company_label=company_label,
            website=website,
            postings_found=hiring_signals.postings_found,
            postings_extracted=hiring_signals.postings_extracted,
            source=hiring_signals.source,
        )
    else:
        if hiring_signals is None:
            logger.info("Hiring signals: skipped (disabled or no slug candidates)")
        else:
            console.info(
                "Hiring Signals: no public postings found — continuing without hiring data"
            )
        _update_run_state(
            folder_path,
            hiring_signals={
                "source": hiring_signals.source if hiring_signals else "skipped",
                "postings_found": hiring_signals.postings_found if hiring_signals else 0,
                "postings_extracted": 0,
            },
        )
        _refresh_working_brief_hiring(
            folder_path=folder_path,
            company_label=company_label,
            website=website,
            postings_found=hiring_signals.postings_found if hiring_signals else 0,
            postings_extracted=0,
            source=hiring_signals.source if hiring_signals else "skipped",
        )

    return hiring_block


def _refresh_working_brief_hiring(
    *,
    folder_path: str,
    company_label: str,
    website: str | None,
    postings_found: int,
    postings_extracted: int,
    source: str,
) -> None:
    """Refresh the Layer-1 working brief with hiring counts. Fail-open."""
    try:
        from primr.core.run_state_io import _load_run_state
        from primr.output.working_brief import (
            WorkingBriefInput,
            read_recon_excerpt,
            resolve_public_output_dir,
            write_working_brief,
        )

        state = _load_run_state(folder_path)
        brief_paths = write_working_brief(
            WorkingBriefInput(
                company_name=company_label or "Company",
                website=website,
                run_id=folder_path,
                pages_scraped=int(state.get("pages_scraped") or 0),
                external_source_count=int(state.get("external_sources_initial") or 0),
                recon_excerpt=read_recon_excerpt(folder_path),
                hiring_postings_found=postings_found,
                hiring_postings_extracted=postings_extracted,
                hiring_source=source,
            ),
            working_folder=folder_path,
            public_output_dir=resolve_public_output_dir(folder_path),
        )
        if brief_paths:
            _update_run_state(
                folder_path,
                working_brief_paths=[str(path) for path in brief_paths],
            )
    except Exception as exc:
        logger.warning("Working brief hiring refresh skipped: %s", exc)


def collect_fenced_hiring_block(
    *,
    company_label: str,
    website: str | None,
    scraped_data: dict[str, str],
    folder_path: str,
) -> str:
    """Hiring block fenced for the Deep Research stage-1 context boundary.

    Stage-1 context is otherwise trusted LLM output; the hiring block carries
    scraped posting titles, so it enters that boundary only as fenced data.
    This pre-fence is load-bearing where stage-1 context is consumed verbatim
    (the File Search Store upload); the deep section prompts additionally
    re-fence the whole stage-1 slice, which redacts these inner markers -
    fail-safe (the outer fence still classifies everything as data). The
    fast pipeline must NOT use this variant: it fences the block inside its
    corpus bundles, where a second fence would be the only one corrupted.
    Returns '' when no signals were found (callers can cleanly omit it).
    """
    from primr.utils.content_sanitizer import fence_untrusted

    hiring_block = collect_hiring_block(
        company_label=company_label,
        website=website,
        scraped_data=scraped_data,
        folder_path=folder_path,
    )
    return fence_untrusted("HIRING_SIGNALS", hiring_block) if hiring_block else ""
