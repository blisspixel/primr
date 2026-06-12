"""Fast-run hiring-signals stage (roadmap #23, Batch C).

Extracted verbatim from stage 2 of ``perform_fast_research`` — no behavior
change. Discovers open job postings via the ATS fan-out, extracts strategic
signals, and renders the hiring block that rides along through BOTH the
initial insights build and the Phase 2 gap-filling rebuild so it survives
every refresh of ``insights.txt`` and the raw external-sources bundle.

Side effects preserved from the original: console announcements, run-state
update (postings found/selected/extracted + slug), and the ``_hiring/``
artifacts written by ``gather_hiring_signals`` itself. The stage never fails
the run — any error degrades to an empty hiring block.
"""

from __future__ import annotations

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

    return hiring_block
