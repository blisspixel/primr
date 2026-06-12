"""Confidence-label calibration: measure whether labels are *true*, not just present.

The Confirmed/Reported/Estimated/Hypothesis regime is primr's core epistemic
apparatus, and until now nothing measured whether a label is correctly
assigned — the QA score counts occurrences (and says so honestly). This
module converts the labels from style guide to measured quantity:

- ``extract_labeled_claims`` deterministically samples labeled claims from a
  report, resolving each claim's ``[cite: N]`` references against the
  Sources appendix.
- ``calibrate_claims`` checks traceability per label class: a ``(Confirmed)``
  or ``(Reported)`` claim must be supported by the *fetched text* of a cited
  source (judged by an injectable judge — LLM in production, deterministic in
  tests). ``(Estimated)`` / ``(Hypothesis)`` are exempt from traceability by
  design — they assert inference, not sourced fact.
- ``CalibrationReport`` carries per-label precision for the eval scorecard;
  once a baseline exists, "Confirmed-claim traceability >= X%" becomes a
  HARD eval gate (see docs/design/1x-completion.md, workstream 1).

All effects (source fetching, support judging) are injectable seams; the
module itself performs no network or LLM calls unless the default seams are
used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.utils.logging_config import get_logger

logger = get_logger("qa.label_calibration")

# Canonical label vocabulary (parenthesized, optional explanatory suffix
# inside the parens — e.g. "(Estimated — triangulated from filings)").
_LABEL_RE = re.compile(
    r"\((Confirmed|Reported|Estimated|Hypothesis)\b[^)]*\)",
)
_CITE_RE = re.compile(r"\[cite:\s*(\d+(?:\s*,\s*\d+)*)\]")
_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
# Sources appendix entry formats: "[cite: 1] https://..." (the current
# artifact contract), "1. https://...", or "[1] https://...".
_SOURCE_ENTRY_RE = re.compile(
    r"^\s*(?:\[cite:\s*(\d+)\]|\[(\d+)\]|(\d+)\.)\s+(https?://\S+)", re.MULTILINE
)

# A label alone on its line — the current writer renders block-scoped labels
# this way: [claim paragraphs] [What to validate: ...] [(Reported)].
_STANDALONE_LABEL_RE = re.compile(
    r"^\s*\((Confirmed|Reported|Estimated|Hypothesis)\b[^)]*\)\s*$",
)
# The discovery-question line inside a labeled block — a question to ask, not
# a claim, so it is excluded from the claim text the judge sees.
_VALIDATE_LINE_RE = re.compile(r"^\s*\**\s*what to validate:", re.IGNORECASE)

# Labels whose claims must trace to a cited source.
TRACEABLE_LABELS = frozenset({"Confirmed", "Reported"})
# Labels that assert inference, exempt from traceability by design.
INFERENCE_LABELS = frozenset({"Estimated", "Hypothesis"})

DEFAULT_MAX_PER_LABEL = 10
# Bounds for the block a standalone label annotates: enough to carry the
# claim's substance, small enough to keep the judge prompt focused.
_BLOCK_MAX_PARAGRAPHS = 3
_BLOCK_MAX_CHARS = 1500


@dataclass(frozen=True)
class LabeledClaim:
    """One labeled claim sampled from a report."""

    label: str  # Confirmed | Reported | Estimated | Hypothesis
    sentence: str  # the line carrying the label
    section: str
    cite_numbers: tuple[int, ...]
    source_urls: tuple[str, ...]  # cite numbers resolved against the appendix


@dataclass(frozen=True)
class ClaimCalibration:
    """Calibration verdict for one claim."""

    claim: LabeledClaim
    # traceable      — a cited source's fetched text supports the claim
    # untraceable    — cited sources fetched but none support the claim
    # no_source      — a traceable-class label with no resolvable citation
    # unfetchable    — citations exist but no source content could be fetched
    # exempt         — inference-class label, traceability not required
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.claim.label,
            "section": self.claim.section,
            "sentence": self.claim.sentence[:300],
            "cite_numbers": list(self.claim.cite_numbers),
            "source_urls": list(self.claim.source_urls),
            "verdict": self.verdict,
        }


@dataclass
class CalibrationReport:
    """Per-label calibration aggregate for the eval scorecard."""

    results: list[ClaimCalibration] = field(default_factory=list)

    def _of(self, label: str) -> list[ClaimCalibration]:
        return [r for r in self.results if r.claim.label == label]

    def precision(self, label: str) -> float | None:
        """Traceability precision for a label: traceable / decidable.

        ``unfetchable`` claims are excluded (the harness couldn't decide);
        ``no_source`` counts AGAINST precision — a (Confirmed) claim with no
        citation is mislabeled by definition. Returns None when no claim of
        the label was decidable.
        """
        decidable = [
            r for r in self._of(label) if r.verdict in ("traceable", "untraceable", "no_source")
        ]
        if not decidable:
            return None
        traceable = sum(1 for r in decidable if r.verdict == "traceable")
        return traceable / len(decidable)

    def to_dict(self) -> dict[str, Any]:
        labels = sorted({r.claim.label for r in self.results})
        per_label = {}
        for label in labels:
            of_label = self._of(label)
            precision = self.precision(label)
            per_label[label] = {
                "sampled": len(of_label),
                "traceable": sum(1 for r in of_label if r.verdict == "traceable"),
                "untraceable": sum(1 for r in of_label if r.verdict == "untraceable"),
                "no_source": sum(1 for r in of_label if r.verdict == "no_source"),
                "unfetchable": sum(1 for r in of_label if r.verdict == "unfetchable"),
                "exempt": sum(1 for r in of_label if r.verdict == "exempt"),
                "precision": round(precision, 3) if precision is not None else None,
            }
        return {
            "per_label": per_label,
            "claims": [r.to_dict() for r in self.results],
        }


def parse_sources_appendix(report_content: str) -> dict[int, str]:
    """Map citation numbers to URLs from the Sources/References appendix."""
    appendix_match = re.search(
        r"^##\s+(?:Sources|References|Citations)\s*$", report_content, re.MULTILINE
    )
    haystack = report_content[appendix_match.end() :] if appendix_match else report_content
    mapping: dict[int, str] = {}
    for m in _SOURCE_ENTRY_RE.finditer(haystack):
        number = int(m.group(1) or m.group(2) or m.group(3))
        if number not in mapping:
            mapping[number] = m.group(4).rstrip(".,;")
    return mapping


def _claim_block_above(lines: list[str], label_index: int) -> str:
    """Collect the prose block a standalone label annotates.

    Walks upward from the label line, gathering blank-line-separated
    paragraphs in document order until a heading, another standalone label,
    or the block bounds. ``What to validate:`` paragraphs are discovery
    questions, not claims, and are excluded.
    """
    paragraphs: list[str] = []
    current: list[str] = []

    def _flush() -> None:
        if not current:
            return
        paragraph = " ".join(reversed(current))
        current.clear()
        if not _VALIDATE_LINE_RE.match(paragraph):
            paragraphs.append(paragraph)

    i = label_index - 1
    while i >= 0:
        stripped = lines[i].strip()
        if not stripped:
            _flush()
            if (
                len(paragraphs) >= _BLOCK_MAX_PARAGRAPHS
                or sum(len(p) for p in paragraphs) >= _BLOCK_MAX_CHARS
            ):
                break
            i -= 1
            continue
        if stripped.startswith("#") or _STANDALONE_LABEL_RE.match(stripped):
            break
        current.append(stripped)
        i -= 1
    _flush()

    paragraphs.reverse()  # back to document order
    return "\n".join(paragraphs)


def extract_labeled_claims(
    report_content: str,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
) -> list[LabeledClaim]:
    """Deterministically sample labeled claims from a report.

    Two claim shapes are recognized, matching the artifact contract:

    - **Inline**: the label sits on the claim's own line; citations are the
      ``[cite: N]`` markers on that line.
    - **Standalone**: the label is alone on its line, trailing the block it
      scopes ([paragraphs] [What to validate: ...] [label]); the claim is
      the block's prose (validate-questions excluded) and citations are
      collected from the whole block.

    Citations resolve against the Sources appendix. Sampling keeps document
    order, capped per label so calibration cost stays bounded.
    """
    sources = parse_sources_appendix(report_content)

    # Section boundaries for attribution
    section_spans: list[tuple[int, str]] = [
        (m.start(), m.group(1).strip()) for m in _SECTION_RE.finditer(report_content)
    ]

    def _section_at(pos: int) -> str:
        current = ""
        for start, title in section_spans:
            if start <= pos:
                current = title
            else:
                break
        return current

    line_matches = list(re.finditer(r"^(.*)$", report_content, re.MULTILINE))
    lines = [m.group(1) for m in line_matches]

    claims: list[LabeledClaim] = []
    per_label_counts: dict[str, int] = {}

    for index, line in enumerate(lines):
        label_match = _LABEL_RE.search(line)
        if not label_match:
            continue
        label = label_match.group(1)
        if per_label_counts.get(label, 0) >= max_per_label:
            continue
        section = _section_at(line_matches[index].start())
        if section.lower() in ("sources", "references", "citations"):
            continue

        if _STANDALONE_LABEL_RE.match(line):
            claim_text = _claim_block_above(lines, index)
            if not claim_text:
                continue  # bare label with no associable prose
        else:
            claim_text = line.strip()

        cite_numbers: list[int] = []
        for cite_match in _CITE_RE.finditer(claim_text):
            cite_numbers.extend(int(n.strip()) for n in cite_match.group(1).split(","))
        urls = tuple(sources[n] for n in cite_numbers if n in sources)

        claims.append(
            LabeledClaim(
                label=label,
                sentence=claim_text,
                section=section,
                cite_numbers=tuple(cite_numbers),
                source_urls=urls,
            )
        )
        per_label_counts[label] = per_label_counts.get(label, 0) + 1

    return claims


def _default_fetch(url: str) -> str:
    """Fetch a source page's readable text (SSRF-guarded, zero token cost)."""
    from primr.data.fallback_sources import _http_get
    from primr.data.scraping.content import extract_main_content

    try:
        status, body, _final = _http_get(url, timeout=12.0)
        if status and 200 <= status < 300 and body:
            return extract_main_content(body) or ""
    except Exception as e:
        logger.debug("Calibration fetch failed for %s: %s", url, e)
    return ""


def _default_judge(claim_sentence: str, source_text: str) -> bool:
    """LLM judge: does the source text substantively support the claim?"""
    from primr.ai.llm import llm

    prompt = (
        "You are auditing a research report's citation. Does the SOURCE TEXT "
        "substantively support the CLAIM? Supporting means the source contains "
        "the claim's substance (figures, named facts, events) — topical "
        "relatedness is not support.\n\n"
        f"CLAIM:\n{claim_sentence[:600]}\n\n"
        f"SOURCE TEXT:\n{source_text[:4000]}\n\n"
        'Answer with exactly one word: "yes" or "no".'
    )
    try:
        response = llm(prompt, model_type="fast", temperature=0.0)
        return str(response).strip().lower().startswith("y")
    except Exception as e:
        logger.warning("Calibration judge failed: %s", e)
        return False


def calibrate_claims(
    claims: list[LabeledClaim],
    *,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
    max_sources_per_claim: int = 2,
) -> CalibrationReport:
    """Run the traceability audit over sampled claims.

    Traceable-class labels (Confirmed/Reported) are judged against the
    fetched text of their cited sources; inference-class labels are exempt.
    Fetches are deduped across claims.
    """
    fetch = fetch_fn or _default_fetch
    judge = judge_fn or _default_judge

    fetched: dict[str, str] = {}

    def _get_source_text(url: str) -> str:
        if url not in fetched:
            fetched[url] = fetch(url)
        return fetched[url]

    results: list[ClaimCalibration] = []
    for claim in claims:
        if claim.label in INFERENCE_LABELS:
            results.append(ClaimCalibration(claim=claim, verdict="exempt"))
            continue

        if not claim.source_urls:
            results.append(ClaimCalibration(claim=claim, verdict="no_source"))
            continue

        texts = [
            text
            for url in claim.source_urls[:max_sources_per_claim]
            if (text := _get_source_text(url))
        ]
        if not texts:
            results.append(ClaimCalibration(claim=claim, verdict="unfetchable"))
            continue

        supported = any(judge(claim.sentence, text) for text in texts)
        results.append(
            ClaimCalibration(
                claim=claim,
                verdict="traceable" if supported else "untraceable",
            )
        )

    return CalibrationReport(results=results)


def calibrate_report_file(
    report_path: str,
    *,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
) -> CalibrationReport:
    """Convenience entry: extract + calibrate a report file on disk."""
    from pathlib import Path

    content = Path(report_path).read_text(encoding="utf-8")
    claims = extract_labeled_claims(content, max_per_label=max_per_label)
    return calibrate_claims(claims, fetch_fn=fetch_fn, judge_fn=judge_fn)
