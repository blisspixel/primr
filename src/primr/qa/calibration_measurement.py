"""Measurement helpers for label calibration.

The calibration gate needs four things the live judge path did not provide:

- claim text with the confidence label removed, so the judge cannot see it
- a passage from the frozen capture that is relevant to the claim
- a seeded sample, so a capped audit is reproducible without taking the first rows
- a report-clustered Wilson lower bound, so the floor is a confidence bound
  rather than the smallest point rate

``extract_labeled_claims`` stays in document order. Label honesty needs that
order because it rewrites every labeled claim. Calibration sampling is a
separate step.
"""

from __future__ import annotations

import math
import random
import re
from statistics import NormalDist
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

BOUND_METHOD = "report_clustered_wilson_lower"
BOUND_CONFIDENCE = 0.95
DEFAULT_CALIBRATION_SAMPLE_SEED = 0
PASSAGE_MAX_CHARS = 4000

# Same confidence-label token as ``label_calibration._LABEL_RE``.
_LABEL_RE = re.compile(
    r"\((Confirmed|Reported|Estimated|Hypothesis)\b[^)]*\)",
)
_TOKEN_RE = re.compile(r"[a-z0-9$%]+")
_MIN_TOKEN_CHARS = 4
_STOPWORDS = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "were",
        "been",
        "their",
        "there",
        "which",
        "about",
        "would",
        "could",
        "should",
        "after",
        "before",
        "under",
        "where",
        "while",
    }
)

_T = TypeVar("_T")


def claim_text_for_judge(sentence: str) -> str:
    """Return claim text with confidence labels removed.

    The label is the thing under test. Leaving ``(Confirmed)`` in the judge
    prompt tells the model the verdict the report already asserted.
    """
    text = _LABEL_RE.sub(" ", sentence)
    return re.sub(r"\s+", " ", text).strip()


def parse_judge_verdict(raw: str) -> str:
    """Parse a judge answer as ``yes``, ``no``, ``abstain``, or ``unparseable``.

    An opening yes/no/abstain wins. Otherwise the last of those words wins.
    Unparseable text stays unparseable so a later step can record it. It is
    not support, and it is not an explicit abstention.
    """
    text = re.sub(r"<think>.*?</think>", " ", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    opening = re.match(r"""^["'`*\s]*(yes|no|abstain)\b""", text, flags=re.IGNORECASE)
    if opening:
        return opening.group(1).lower()
    matches = re.findall(r"\b(yes|no|abstain)\b", text, flags=re.IGNORECASE)
    if not matches:
        return "unparseable"
    return matches[-1].lower()


def relevant_passage(
    claim_text: str, source_text: str, *, max_chars: int = PASSAGE_MAX_CHARS
) -> str:
    """Return the source window that shares the most claim tokens.

    Short captures are returned whole. A long capture contributes the
    paragraph, or paragraph slice, with the strongest token overlap. Ties
    keep the earlier window. With no overlap, the start of the capture is
    used so the judge still sees source text.
    """
    source = source_text.strip()
    if len(source) <= max_chars:
        return source
    tokens = _claim_tokens(claim_text)
    windows = _passage_windows(source, max_chars)
    if not tokens or not windows:
        return source[:max_chars]
    best = source[:max_chars]
    best_score = -1
    for window in windows:
        haystack = window.lower()
        score = sum(1 for token in tokens if token in haystack)
        if score > best_score:
            best = window
            best_score = score
    if best_score <= 0:
        return source[:max_chars]
    return best[:max_chars]


def sample_labeled_claims(
    claims: Sequence[_T],
    *,
    max_per_label: int | None,
    seed: int = DEFAULT_CALIBRATION_SAMPLE_SEED,
) -> list[_T]:
    """Draw a seeded per-label sample and keep the selected claims in document order.

    ``max_per_label=None`` returns every claim. The draw is independent for
    each call with the same seed: the seed is not a running stream across reports.
    """
    if max_per_label is None:
        return list(claims)
    if max_per_label < 0:
        raise ValueError("max_per_label must be zero or positive")
    groups: dict[str, list[_T]] = {}
    order: list[str] = []
    for claim in claims:
        label = str(getattr(claim, "label", ""))
        if label not in groups:
            order.append(label)
            groups[label] = []
        groups[label].append(claim)
    rng = random.Random(seed)
    selected: set[int] = set()
    for label in order:
        group = groups[label]
        chosen = group if len(group) <= max_per_label else rng.sample(group, max_per_label)
        selected.update(id(item) for item in chosen)
    return [claim for claim in claims if id(claim) in selected]


def load_captured_sources(path: Path) -> dict[str, str]:
    """Load the frozen URL capture written as ``scraped_content.txt``."""
    from primr.core.local_stage_eval import parse_scraped_content_file

    return parse_scraped_content_file(path)


def lookup_captured_source(url: str, captures: Mapping[str, str]) -> str | None:
    """Return only the capture recorded for this exact URL.

    A present key with empty text is a capture, not a miss. The caller must
    not live-fetch that URL. Path/query case and trailing slashes can identify
    different resources. The capture mapping carries no redirect or canonical
    alias evidence, so spelling similarity must never bind frozen evidence.
    """
    return captures.get(url)


def wilson_lower_bound(
    successes: float,
    trials: float,
    *,
    confidence: float = BOUND_CONFIDENCE,
) -> float:
    """Lower end of the Wilson score interval for a binomial proportion."""
    if trials <= 0:
        raise ValueError("Wilson bound requires a positive trial count")
    if successes < 0 or successes > trials:
        raise ValueError("Wilson successes must lie between 0 and the trial count")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    n = float(trials)
    proportion = float(successes) / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (proportion + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt(proportion * (1.0 - proportion) / n + z2 / (4.0 * n * n)) / denom
    return max(0.0, center - margin)


def report_clustered_wilson_lower(
    reports: Sequence[tuple[int, int]],
    *,
    confidence: float = BOUND_CONFIDENCE,
) -> float | None:
    """Wilson lower bound with a cluster design effect across reports.

    Each pair is ``(traceable, decidable)`` for one report. Reports are the
    clusters. The design effect is the ratio of the cluster-robust variance
    of the pooled proportion to the binomial variance. When that variance is
    zero, including a perfect sample, the effect is 1 and the bound is the
    ordinary Wilson lower bound on the pooled counts. That stays below 1 for
    any finite sample.
    """
    pairs = [(int(traceable), int(decidable)) for traceable, decidable in reports if decidable > 0]
    if not pairs:
        return None
    for traceable, decidable in pairs:
        if traceable < 0 or traceable > decidable:
            raise ValueError("traceable count must lie between 0 and decidable count")
    successes = sum(traceable for traceable, _decidable in pairs)
    trials = sum(decidable for _traceable, decidable in pairs)
    if len(pairs) == 1:
        return wilson_lower_bound(successes, trials, confidence=confidence)
    proportion = successes / trials
    residual_sum = sum((traceable - proportion * decidable) ** 2 for traceable, decidable in pairs)
    clusters = len(pairs)
    variance = (clusters / (clusters - 1)) * residual_sum / (trials**2)
    binomial = proportion * (1.0 - proportion) / trials
    if variance <= 0 or binomial <= 0:
        design_effect = 1.0
    else:
        design_effect = max(1.0, variance / binomial)
    effective_trials = trials / design_effect
    effective_successes = proportion * effective_trials
    return wilson_lower_bound(effective_successes, effective_trials, confidence=confidence)


def _claim_tokens(claim_text: str) -> tuple[str, ...]:
    tokens = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer(claim_text.lower()):
        token = match.group(0)
        if len(token) < _MIN_TOKEN_CHARS or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tuple(tokens)


def _passage_windows(source: str, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]
    windows: list[str] = []
    step = max(1, max_chars // 2)
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            windows.append(paragraph)
            continue
        start = 0
        while start < len(paragraph):
            windows.append(paragraph[start : start + max_chars])
            if start + max_chars >= len(paragraph):
                break
            start += step
    return windows
