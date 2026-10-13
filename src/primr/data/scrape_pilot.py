"""Pilot-sample policy for deciding whether a full site crawl should continue."""

from __future__ import annotations

from primr.config.config import (
    MIN_SCRAPED_CHARS,
    SCRAPE_PILOT_MIN_CHARS,
    SCRAPE_PILOT_MIN_SUCCESS_RATE,
)


def evaluate_scrape_pilot(
    pilot_success: int,
    pilot_attempts: int,
    pilot_chars_total: int,
) -> dict[str, float | int | bool]:
    """
    Evaluate whether the pilot sample is too weak to trust a full crawl.

    Relief is intentionally granted when a sparse pilot still yields a few
    content-rich pages. That pattern is common on bot-protected or uneven sites
    where the crawl is still worth continuing with heavier external research.
    """
    success_rate = pilot_success / max(pilot_attempts, 1)
    avg_chars = int(pilot_chars_total / max(pilot_success, 1)) if pilot_success else 0
    high_success_relief_rate = max(SCRAPE_PILOT_MIN_SUCCESS_RATE, 0.90)
    low_content_with_low_success = (
        avg_chars < SCRAPE_PILOT_MIN_CHARS and success_rate < high_success_relief_rate
    )

    # Permit a sparse pilot when the pages that did land are substantively
    # rich AND the success rate is at least half the configured floor.
    # Without the success-rate floor, an attacker-controlled site could
    # serve 3 rich pages and 7+ failures and still drive primr into the
    # full concurrent crawl phase, multiplying outbound work past the
    # documented pilot abort. Half the configured floor (0.35 at default)
    # preserves the legitimate "patchy site with a few good pages" case
    # while rejecting 3/50-style adversarial samples.
    rich_content_relief_floor = max(SCRAPE_PILOT_MIN_SUCCESS_RATE / 2, 0.30)
    rich_content_relief = (
        success_rate >= rich_content_relief_floor
        and avg_chars >= max(SCRAPE_PILOT_MIN_CHARS * 3, 2000)
        and (
            pilot_success >= 3
            or (pilot_success >= 2 and pilot_chars_total >= max(SCRAPE_PILOT_MIN_CHARS * 6, 4000))
        )
    )
    useful_corpus_relief = pilot_success >= 4 and pilot_chars_total >= max(MIN_SCRAPED_CHARS, 4000)

    should_abort = False
    if not (rich_content_relief or useful_corpus_relief) and (
        success_rate < SCRAPE_PILOT_MIN_SUCCESS_RATE or low_content_with_low_success
    ):
        should_abort = True

    return {
        "success_rate": success_rate,
        "avg_chars": avg_chars,
        "low_content_with_low_success": low_content_with_low_success,
        "rich_content_relief": rich_content_relief,
        "useful_corpus_relief": useful_corpus_relief,
        "should_abort": should_abort,
    }


def pilot_validation_abort_hint(*, suggest_skip_validation: bool) -> str:
    """Return the pilot-abort next step for the command that is running.

    ``primr prep`` does not accept ``--skip-scrape-validation``. Only the main
    research parser does, so prep must not be told to pass that flag.
    """
    if suggest_skip_validation:
        return "Re-run with --skip-scrape-validation to continue anyway"
    return "Re-run primr prep, or raise --max-pages, after checking why the sample failed."
