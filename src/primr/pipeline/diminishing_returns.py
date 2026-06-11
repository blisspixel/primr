"""Diminishing-returns detection for cross-validation regeneration loops.

The cross-validation pass regenerates weak sections one at a time. Each
regeneration costs a writing-tier LLM call; when the loop is no longer
producing meaningful improvement, continuing just burns token budget.
This module provides a small pure tracker the loop consults after every
regeneration: it measures the improvement each rewrite produced (word
growth, new citations) and signals an early stop after N consecutive
low-improvement regenerations.

Thresholds are deliberately conservative (3 consecutive, <5% improvement)
per the roadmap — tune them against eval results, not intuition.

Pure logic, no I/O, no LLM calls — fully unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A regeneration counts as "low improvement" when its improvement score is
# below this fraction.
DEFAULT_IMPROVEMENT_THRESHOLD = 0.05
# Stop after this many consecutive low-improvement regenerations.
DEFAULT_CONSECUTIVE_LIMIT = 3

_CITE_RE = re.compile(r"\[cite:\s*\d+\]")


@dataclass(frozen=True)
class SectionImprovement:
    """Measured improvement from one section regeneration."""

    section_title: str
    word_delta_ratio: float  # (new_words - old_words) / old_words
    new_citations: int  # citation markers gained
    score: float  # combined improvement score (0.0 = no improvement)


def assess_improvement(
    section_title: str,
    original: str,
    regenerated: str,
) -> SectionImprovement:
    """Measure how much a regeneration improved a section.

    The score is the larger of two signals, each expressed as a fraction:

    - word growth ratio: substantive new content (clamped at 0 — a rewrite
      that *shrinks* a section is not negative improvement, just zero)
    - citation gain: each net-new ``[cite: N]`` marker counts as 5% — new
      evidence is the whole point of the enrichment loop, so a rewrite that
      adds grounded citations counts as improvement even at similar length
    """
    original_words = len(original.split())
    regenerated_words = len(regenerated.split())
    if original_words > 0:
        word_delta_ratio = (regenerated_words - original_words) / original_words
    else:
        word_delta_ratio = 1.0 if regenerated_words > 0 else 0.0

    original_cites = len(_CITE_RE.findall(original))
    regenerated_cites = len(_CITE_RE.findall(regenerated))
    new_citations = max(0, regenerated_cites - original_cites)

    score = max(0.0, word_delta_ratio, new_citations * 0.05)
    return SectionImprovement(
        section_title=section_title,
        word_delta_ratio=word_delta_ratio,
        new_citations=new_citations,
        score=score,
    )


@dataclass
class DiminishingReturnsDetector:
    """Tracks per-regeneration improvement and signals an early stop.

    Usage::

        detector = DiminishingReturnsDetector()
        for section in weak_sections:
            regenerated = regenerate(section)
            detector.record(assess_improvement(title, original, regenerated))
            if detector.should_stop():
                log(detector.stop_reason())
                break
    """

    improvement_threshold: float = DEFAULT_IMPROVEMENT_THRESHOLD
    consecutive_limit: int = DEFAULT_CONSECUTIVE_LIMIT
    history: list[SectionImprovement] = field(default_factory=list)
    _consecutive_low: int = 0

    def record(self, improvement: SectionImprovement) -> None:
        """Record one regeneration's measured improvement."""
        self.history.append(improvement)
        if improvement.score < self.improvement_threshold:
            self._consecutive_low += 1
        else:
            self._consecutive_low = 0

    @property
    def consecutive_low(self) -> int:
        return self._consecutive_low

    def should_stop(self) -> bool:
        """True when the last ``consecutive_limit`` regenerations were all low-improvement."""
        return self._consecutive_low >= self.consecutive_limit

    def stop_reason(self) -> str:
        """Human-readable early-stop line for the QA summary / run log."""
        return (
            f"cross-validation: stopped early (diminishing returns after "
            f"{len(self.history)} iteration(s) — last {self._consecutive_low} "
            f"below {self.improvement_threshold:.0%} improvement)"
        )

    def summary(self) -> dict:
        """JSON-serializable summary for ``cross_validation.json``."""
        return {
            "iterations": len(self.history),
            "stopped_early": self.should_stop(),
            "consecutive_low_improvement": self._consecutive_low,
            "improvement_threshold": self.improvement_threshold,
            "per_section": [
                {
                    "section": imp.section_title,
                    "word_delta_ratio": round(imp.word_delta_ratio, 4),
                    "new_citations": imp.new_citations,
                    "score": round(imp.score, 4),
                }
                for imp in self.history
            ],
        }
