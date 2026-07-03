"""Confidence-label calibration: measure whether labels are true, not just present.

The Confirmed/Reported/Estimated/Hypothesis regime is primr's core epistemic
apparatus, and the QA score only counts whether labels appear. This module
turns the labels from style guide into measured evidence:

- ``extract_labeled_claims`` deterministically samples labeled claims from a
  report, resolving each claim's ``[cite: N]`` references against the Sources
  appendix.
- ``calibrate_claims`` preserves the stable traceability verdicts used by
  scorecards, while also allowing richer evidence reviews for each cited source.
  Traceability is the first measurable slice. It is not the full validation
  story.
- ``CalibrationReport`` carries per-label precision plus optional evidence
  dimensions: support, contradiction, source independence, source authority,
  reasoning strength, uncertainty honesty, and business relevance.

All effects (source fetching and judging) are injectable seams. The module
itself performs no network or LLM calls unless the default seams are used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.utils.logging_config import get_logger

logger = get_logger("qa.label_calibration")

_REVIEW_DIMENSIONS = (
    "contradiction",
    "source_independence",
    "source_authority",
    "reasoning_strength",
    "uncertainty_honesty",
    "business_relevance",
)
_REVIEW_ALLOWED_VALUES = {
    "contradiction": frozenset({"none", "partial", "direct", "unknown"}),
    "source_independence": frozenset({"independent", "first_party", "unknown"}),
    "source_authority": frozenset({"high", "medium", "low", "unknown"}),
    "reasoning_strength": frozenset({"strong", "partial", "weak", "unknown"}),
    "uncertainty_honesty": frozenset({"honest", "overstated", "understated", "unknown"}),
    "business_relevance": frozenset({"high", "medium", "low", "unknown"}),
}
# Canonical label vocabulary (parenthesized, optional explanatory suffix
# inside the parens - e.g. "(Estimated - triangulated from filings)").
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

# A label alone on its line - the current writer renders block-scoped labels
# this way: [claim paragraphs] [What to validate: ...] [(Reported)].
_STANDALONE_LABEL_RE = re.compile(
    r"^\s*\((Confirmed|Reported|Estimated|Hypothesis)\b[^)]*\)\s*$",
)
# The discovery-question line inside a labeled block - a question to ask, not
# a claim, so it is excluded from the claim text the judge sees.
_VALIDATE_LINE_RE = re.compile(r"^\s*\**\s*what to validate:", re.IGNORECASE)

# Labels whose claims must trace to a cited source.
TRACEABLE_LABELS = frozenset({"Confirmed", "Reported"})
# Labels that assert inference, exempt from traceability by design.
INFERENCE_LABELS = frozenset({"Estimated", "Hypothesis"})

DEFAULT_MAX_PER_LABEL = 10
_SOURCE_COPY_MIN_CHARS = 40
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
    # Absolute (start, end) offsets of the label token in the report, so a
    # consumer (the label-honesty pass) can rewrite this exact occurrence
    # without re-scanning. (-1, -1) when the claim was built directly.
    label_span: tuple[int, int] = (-1, -1)


@dataclass(frozen=True)
class EvidenceReview:
    """A source-level evidence review for one claim.

    ``supported`` preserves the existing traceability decision. The remaining
    dimensions are report-only calibration signal until a measured baseline is
    strong enough to justify gates.
    """

    supported: bool
    contradiction: str = "unknown"
    source_independence: str = "unknown"
    source_authority: str = "unknown"
    reasoning_strength: str = "unknown"
    uncertainty_honesty: str = "unknown"
    business_relevance: str = "unknown"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "contradiction": self.contradiction,
            "source_independence": self.source_independence,
            "source_authority": self.source_authority,
            "reasoning_strength": self.reasoning_strength,
            "uncertainty_honesty": self.uncertainty_honesty,
            "business_relevance": self.business_relevance,
            "rationale": self.rationale[:500],
        }


@dataclass(frozen=True)
class ClaimCalibration:
    """Calibration verdict for one claim."""

    claim: LabeledClaim
    # traceable      - a cited source's fetched text supports the claim
    # untraceable    - cited sources fetched but none support the claim
    # no_source      - a traceable-class label with no resolvable citation
    # unfetchable    - citations exist but no source content could be fetched
    # exempt         - inference-class label, traceability not required
    # source_copied  - inference-class label appears copied from a cited source
    verdict: str
    evidence_reviews: tuple[EvidenceReview, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "label": self.claim.label,
            "section": self.claim.section,
            "sentence": self.claim.sentence[:300],
            "cite_numbers": list(self.claim.cite_numbers),
            "source_urls": list(self.claim.source_urls),
            "verdict": self.verdict,
        }
        if self.evidence_reviews:
            payload["evidence_reviews"] = [review.to_dict() for review in self.evidence_reviews]
        return payload


@dataclass
class CalibrationReport:
    """Per-label calibration aggregate for the eval scorecard."""

    results: list[ClaimCalibration] = field(default_factory=list)

    def _of(self, label: str) -> list[ClaimCalibration]:
        return [r for r in self.results if r.claim.label == label]

    def precision(self, label: str) -> float | None:
        """Traceability precision for a label: traceable / decidable.

        ``unfetchable`` claims are excluded (the harness couldn't decide);
        ``no_source`` counts AGAINST precision - a (Confirmed) claim with no
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

    def validation_rubric(self) -> dict[str, Any]:
        """Aggregate optional evidence-review dimensions for reporting."""
        reviews = [review for result in self.results for review in result.evidence_reviews]
        rubric: dict[str, Any] = {
            "claims_with_reviews": sum(1 for result in self.results if result.evidence_reviews),
            "source_reviews": len(reviews),
            "support": {
                "supported": sum(1 for review in reviews if review.supported),
                "unsupported": sum(1 for review in reviews if not review.supported),
            },
        }
        for dimension in _REVIEW_DIMENSIONS:
            counts: dict[str, int] = dict.fromkeys(sorted(_REVIEW_ALLOWED_VALUES[dimension]), 0)
            for review in reviews:
                value = getattr(review, dimension)
                counts[value if value in counts else "unknown"] += 1
            rubric[dimension] = counts
        return rubric

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
                "source_copied": sum(1 for r in of_label if r.verdict == "source_copied"),
                "precision": round(precision, 3) if precision is not None else None,
            }
        return {
            "per_label": per_label,
            "validation_rubric": self.validation_rubric(),
            "claims": [r.to_dict() for r in self.results],
        }


def summarize_label_citation_coverage(report_content: str) -> dict[str, int | float]:
    """Deterministic, judge-free label-citation coverage for one report.

    The paid label-honesty / calibration pass judges whether a cited source
    *supports* a claim (faithfulness). This is its cheap always-on
    complement: for the traceable-class labels (``Confirmed``/``Reported``),
    how many claims carry ANY resolvable citation at all - the ``no_source``
    slice, which needs no LLM and no network. A ``(Confirmed)`` claim that
    cites nothing is a structural honesty defect regardless of phrasing, so
    surfacing the ratio on every run gives users a label-honesty signal for
    free when the paid pass is off. Report-only: a signal, never a gate.

    Returns per-label and combined totals plus a ``coverage_rate`` in [0, 1]
    (1.0 when there are no traceable-class claims - nothing to under-cite).
    """
    claims = extract_labeled_claims(report_content, max_per_label=None)
    per_label_total: dict[str, int] = dict.fromkeys(TRACEABLE_LABELS, 0)
    per_label_cited: dict[str, int] = dict.fromkeys(TRACEABLE_LABELS, 0)
    for claim in claims:
        if claim.label not in TRACEABLE_LABELS:
            continue
        per_label_total[claim.label] += 1
        if claim.source_urls:
            per_label_cited[claim.label] += 1

    traceable_total = sum(per_label_total.values())
    traceable_cited = sum(per_label_cited.values())
    coverage_rate = traceable_cited / traceable_total if traceable_total else 1.0

    return {
        "confirmed_total": per_label_total["Confirmed"],
        "confirmed_cited": per_label_cited["Confirmed"],
        "reported_total": per_label_total["Reported"],
        "reported_cited": per_label_cited["Reported"],
        "traceable_total": traceable_total,
        "traceable_cited": traceable_cited,
        "coverage_rate": coverage_rate,
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
    max_per_label: int | None = DEFAULT_MAX_PER_LABEL,
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
    order, capped per label so calibration cost stays bounded. Pass
    ``max_per_label=None`` to extract every labeled claim (the label-honesty
    pass needs complete coverage, since it mutates).
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
        if max_per_label is not None and per_label_counts.get(label, 0) >= max_per_label:
            continue
        line_start = line_matches[index].start()
        section = _section_at(line_start)
        if section.lower() in ("sources", "references", "citations"):
            continue
        label_span = (line_start + label_match.start(), line_start + label_match.end())

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
                label_span=label_span,
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


def build_judge_prompt(claim_sentence: str, source_text: str) -> str:
    """The traceability-judge prompt, shared by the cloud and local judges
    so a verdict never depends on which backend produced it."""
    return (
        "You are auditing a research report's citation. Does the SOURCE TEXT "
        "substantively support the CLAIM? Supporting means the source contains "
        "the claim's substance (figures, named facts, events) - topical "
        "relatedness is not support.\n\n"
        f"CLAIM:\n{claim_sentence[:600]}\n\n"
        f"SOURCE TEXT:\n{source_text[:4000]}\n\n"
        'Answer with exactly one word: "yes" or "no".'
    )


def build_evidence_review_prompt(claim_sentence: str, source_text: str) -> str:
    """Prompt for a richer evidence review over one claim/source pair."""
    schema = {
        "supported": "boolean",
        "contradiction": "none | partial | direct | unknown",
        "source_independence": "independent | first_party | unknown",
        "source_authority": "high | medium | low | unknown",
        "reasoning_strength": "strong | partial | weak | unknown",
        "uncertainty_honesty": "honest | overstated | understated | unknown",
        "business_relevance": "high | medium | low | unknown",
        "rationale": "one concise sentence",
    }
    return (
        "You are auditing a research report's citation for evidence quality. "
        "Evaluate only the SOURCE TEXT against the CLAIM. Do not use outside "
        "knowledge. Topical relatedness is not support. Direct contradiction "
        "means the source says the claim is false or materially different.\n\n"
        f"CLAIM:\n{claim_sentence[:600]}\n\n"
        f"SOURCE TEXT:\n{source_text[:4000]}\n\n"
        "Return JSON only with this schema and allowed values:\n"
        f"{json.dumps(schema, indent=2)}"
    )


def parse_judge_answer(raw: str) -> bool:
    """Parse a yes/no judge answer defensively.

    Local models vary: reasoning families wrap answers in <think> blocks,
    others add punctuation or a trailing explanation. Strategy: strip think
    blocks; if the answer *opens* with yes/no, that is the verdict (the
    model answered directly, anything after is elaboration); otherwise take
    the LAST yes/no token (reasoning-style answers conclude with the
    verdict). Unparseable answers are ``False`` - an undecipherable
    judgment must never count as support.
    """
    text = re.sub(r"<think>.*?</think>", " ", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    opening = re.match(r'^["\'`*\s]*(yes|no)\b', text, flags=re.IGNORECASE)
    if opening:
        return opening.group(1).lower() == "yes"
    matches = re.findall(r"\b(yes|no)\b", text, flags=re.IGNORECASE)
    if not matches:
        return False
    return matches[-1].lower() == "yes"


def _extract_json_object(raw: str) -> str | None:
    text = re.sub(r"<think>.*?</think>", " ", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    return text[start : end + 1]


def _normalize_review_value(dimension: str, value: Any) -> str:
    raw = str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    allowed = _REVIEW_ALLOWED_VALUES[dimension]
    return raw if raw in allowed else "unknown"


def _coerce_supported(value: Any, fallback_text: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "supported", "support", "traceable"}:
        return True
    if text in {"false", "no", "unsupported", "untraceable"}:
        return False
    return parse_judge_answer(fallback_text)


def parse_evidence_review(raw: str) -> EvidenceReview:
    """Parse structured evidence-review output with conservative fallback."""
    json_text = _extract_json_object(raw)
    if json_text is None:
        return EvidenceReview(supported=parse_judge_answer(raw), rationale=str(raw)[:500])

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return EvidenceReview(supported=parse_judge_answer(raw), rationale=str(raw)[:500])

    if not isinstance(parsed, dict):
        return EvidenceReview(supported=parse_judge_answer(raw), rationale=str(raw)[:500])

    supported = _coerce_supported(parsed.get("supported"), raw)
    values = {
        dimension: _normalize_review_value(dimension, parsed.get(dimension))
        for dimension in _REVIEW_DIMENSIONS
    }
    return EvidenceReview(
        supported=supported,
        contradiction=values["contradiction"],
        source_independence=values["source_independence"],
        source_authority=values["source_authority"],
        reasoning_strength=values["reasoning_strength"],
        uncertainty_honesty=values["uncertainty_honesty"],
        business_relevance=values["business_relevance"],
        rationale=str(parsed.get("rationale") or "")[:500],
    )


def _default_judge(claim_sentence: str, source_text: str) -> bool:
    """LLM judge: does the source text substantively support the claim?"""
    from primr.ai.llm import llm

    try:
        response = llm(
            build_judge_prompt(claim_sentence, source_text), model_type="fast", temperature=0.0
        )
        return parse_judge_answer(str(response))
    except Exception as e:
        logger.warning("Calibration judge failed: %s", e)
        return False


def _default_review(claim_sentence: str, source_text: str) -> EvidenceReview:
    """LLM review: evaluate support and evidence dimensions for one source."""
    from primr.ai.llm import llm

    try:
        response = llm(
            build_evidence_review_prompt(claim_sentence, source_text),
            model_type="fast",
            temperature=0.0,
        )
        return parse_evidence_review(str(response))
    except Exception as e:
        logger.warning("Calibration evidence review failed: %s", e)
        return EvidenceReview(supported=False, rationale="judge_error")


def _normalized_copy_text(text: str) -> str:
    text = _LABEL_RE.sub(" ", text)
    text = _CITE_RE.sub(" ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9$%.]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _source_copy_segments(claim_sentence: str) -> tuple[str, ...]:
    cleaned = _LABEL_RE.sub(" ", claim_sentence)
    cleaned = _CITE_RE.sub(" ", cleaned)
    segments = re.split(r"[\n.!?;]+", cleaned)
    normalized = [_normalized_copy_text(segment) for segment in segments]
    return tuple(segment for segment in normalized if len(segment) >= _SOURCE_COPY_MIN_CHARS)


def _is_source_copied(claim_sentence: str, source_text: str) -> bool:
    source = _normalized_copy_text(source_text)
    if len(source) < _SOURCE_COPY_MIN_CHARS:
        return False
    return any(segment in source for segment in _source_copy_segments(claim_sentence))


def calibrate_claims(
    claims: list[LabeledClaim],
    *,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
    review_fn: Callable[[str, str], EvidenceReview] | None = None,
    max_sources_per_claim: int = 2,
) -> CalibrationReport:
    """Run the evidence audit over sampled claims.

    Traceable-class labels (Confirmed/Reported) are judged against the
    fetched text of their cited sources. Inference-class labels
    (Estimated/Hypothesis) are exempt from traceability, but cited inference
    claims are still checked for deterministic source-copy leakage: if the
    claim text appears copied from a cited source, the verdict is
    ``source_copied``. Fetches are deduped across claims.
    """
    fetch = fetch_fn or _default_fetch

    def review(claim_sentence: str, source_text: str) -> EvidenceReview:
        if review_fn is not None:
            return review_fn(claim_sentence, source_text)
        if judge_fn is not None:
            return EvidenceReview(supported=judge_fn(claim_sentence, source_text))
        return _default_review(claim_sentence, source_text)

    fetched: dict[str, str] = {}

    def _get_source_text(url: str) -> str:
        if url not in fetched:
            fetched[url] = fetch(url)
        return fetched[url]

    results: list[ClaimCalibration] = []
    for claim in claims:
        if claim.label in INFERENCE_LABELS:
            texts = [
                text
                for url in claim.source_urls[:max_sources_per_claim]
                if (text := _get_source_text(url))
            ]
            verdict = (
                "source_copied"
                if any(_is_source_copied(claim.sentence, text) for text in texts)
                else "exempt"
            )
            results.append(ClaimCalibration(claim=claim, verdict=verdict))
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

        evidence_reviews = tuple(review(claim.sentence, text) for text in texts)
        supported = any(item.supported for item in evidence_reviews)
        results.append(
            ClaimCalibration(
                claim=claim,
                verdict="traceable" if supported else "untraceable",
                evidence_reviews=evidence_reviews,
            )
        )

    return CalibrationReport(results=results)


def calibrate_report_file(
    report_path: str,
    *,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
    review_fn: Callable[[str, str], EvidenceReview] | None = None,
) -> CalibrationReport:
    """Convenience entry: extract + calibrate a report file on disk."""
    from pathlib import Path

    content = Path(report_path).read_text(encoding="utf-8")
    claims = extract_labeled_claims(content, max_per_label=max_per_label)
    return calibrate_claims(claims, fetch_fn=fetch_fn, judge_fn=judge_fn, review_fn=review_fn)
