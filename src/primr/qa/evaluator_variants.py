"""Adjudicated clean cases and controlled variants for evaluator validation.

The evaluation plan requires evaluators to be validated against frozen,
human-adjudicated clean cases and controlled variants before their verdicts
inform a gate. A clean case pairs one claim with source text that supports it
and names the exact supporting span. Each variant applies one known defect, so
its expected verdict is fixed by construction.

Number, date, negation, support-removal, and citation-attribution variants are
derived mechanically. Entity, causal, stale-evidence, and contradiction
variants need author-supplied text, because a plausible distractor cannot be
invented safely. A variant that cannot be built is recorded as skipped with a
reason; it is never padded with a weaker substitute.

Case files may describe real companies. Keep them in local, gitignored
locations; commit only synthetic fixtures.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

CLEAN = "clean"
ERROR_CATEGORIES = (
    "wrong_number",
    "wrong_entity",
    "wrong_date",
    "negation",
    "stale_evidence",
    "unsupported_causal",
    "insufficient_support",
    "omitted_contradiction",
    "citation_attribution",
    "authority_without_support",
)
REVIEWER_KINDS = ("human", "agent", "synthetic")
SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
CASE_SCHEMA_VERSION = 1
# Bump when a generator changes, so a frozen set records which rules built it.
GENERATOR_VERSION = 3
# Generic trust cue for ``authority_without_support`` when a case names none.
# It asserts provenance only; it never restores the removed support.
DEFAULT_AUTHORITY_CUE = (
    "Verified source: excerpt from the company's audited annual report, "
    "reviewed by its independent auditors."
)

_NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_AUXILIARY_RE = re.compile(r"\b(is|was|are|were|has|have|had|will|can)\b")
_PASSIVE_BEFORE = frozenset({"is", "was", "are", "were", "be", "been", "being"})
_NEGATION_RE = re.compile(r"\b(not|no|never|none|nor|without|fewer|less)\b|n't\b", re.IGNORECASE)
# Mutating a bound (fewer than 5 -> fewer than 11) can leave the claim true.
_COMPARISON_RE = re.compile(
    r"\b(than|least|most|over|under|above|below|after|before|since|about|around|"
    r"approximately|nearly|almost|roughly|up to|more|less|fewer|exceeding)\s*\$?$",
    re.IGNORECASE,
)
_VERB_FLIPS = (
    ("increased", "decreased"),
    ("decreased", "increased"),
    ("rose", "fell"),
    ("fell", "rose"),
    ("grew", "declined"),
    ("declined", "grew"),
    ("expanded", "reduced"),
    ("reduced", "expanded"),
    ("gained", "lost"),
    ("lost", "gained"),
    ("reported", "did not report"),
    ("announced", "did not announce"),
    ("acquired", "did not acquire"),
    ("launched", "did not launch"),
)


@dataclass(frozen=True)
class Adjudication:
    """Who established a clean case's support, and when."""

    reviewer_kind: str
    reviewer: str
    reviewed_on: date
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "reviewer_kind": self.reviewer_kind,
            "reviewer": self.reviewer,
            "reviewed_on": self.reviewed_on.isoformat(),
            "note": self.note,
        }


@dataclass(frozen=True)
class CleanCase:
    """One adjudicated claim and the source text that supports it."""

    case_id: str
    claim: str
    source_text: str
    support_span: str
    adjudication: Adjudication
    entity_swap: tuple[str, str] | None = None
    causal_clause: str | None = None
    stale_source_text: str | None = None
    contradiction: str | None = None
    authority_cue: str | None = None


@dataclass(frozen=True)
class ValidationItem:
    """One frozen claim/source pair with a known expected verdict."""

    item_id: str
    case_id: str
    category: str
    claim: str
    source_text: str
    expected: str
    reviewer_kind: str

    def to_dict(self) -> dict[str, str]:
        return {
            "item_id": self.item_id,
            "case_id": self.case_id,
            "category": self.category,
            "claim": self.claim,
            "source_text": self.source_text,
            "expected": self.expected,
            "reviewer_kind": self.reviewer_kind,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ValidationItem:
        item = cls(**{key: str(payload[key]) for key in _ITEM_FIELDS})
        item.validate()
        return item

    def validate(self) -> None:
        """Reject an item whose fields contradict each other."""
        if self.category != CLEAN and self.category not in ERROR_CATEGORIES:
            raise ValueError(f"unknown validation category: {self.category}")
        if self.expected != (SUPPORTED if self.category == CLEAN else UNSUPPORTED):
            raise ValueError(f"{self.item_id}: expected verdict does not match its category")
        if self.reviewer_kind not in REVIEWER_KINDS:
            raise ValueError(f"{self.item_id}: unknown reviewer_kind {self.reviewer_kind}")
        if self.item_id != f"{self.case_id}:{self.category}":
            raise ValueError(f"{self.item_id}: item_id must be case_id:category")
        if not self.claim.strip() or not self.source_text.strip():
            raise ValueError(f"{self.item_id}: claim and source_text are required")


_ITEM_FIELDS = (
    "item_id",
    "case_id",
    "category",
    "claim",
    "source_text",
    "expected",
    "reviewer_kind",
)


@dataclass(frozen=True)
class SkippedVariant:
    """A variant that could not be built from its clean case."""

    case_id: str
    category: str
    reason: str


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_clean_case(payload: Mapping[str, Any]) -> CleanCase:
    """Build a clean case and reject one whose support cannot be located."""
    adjudication_payload = payload["adjudication"]
    adjudication = Adjudication(
        reviewer_kind=str(adjudication_payload["reviewer_kind"]),
        reviewer=str(adjudication_payload["reviewer"]).strip(),
        reviewed_on=date.fromisoformat(str(adjudication_payload["reviewed_on"])),
        note=str(adjudication_payload.get("note", "")),
    )
    if adjudication.reviewer_kind not in REVIEWER_KINDS:
        raise ValueError(f"unknown reviewer_kind: {adjudication.reviewer_kind}")
    if not adjudication.reviewer:
        raise ValueError("adjudication.reviewer is required")
    swap = payload.get("entity_swap")
    entity_swap = None
    if swap is not None:
        if len(swap) != 2 or not all(str(part).strip() for part in swap):
            raise ValueError("entity_swap must be [entity, distractor]")
        entity_swap = (str(swap[0]).strip(), str(swap[1]).strip())
    case = CleanCase(
        case_id=str(payload["case_id"]).strip(),
        claim=str(payload["claim"]).strip(),
        source_text=str(payload["source_text"]),
        support_span=str(payload["support_span"]),
        adjudication=adjudication,
        entity_swap=entity_swap,
        causal_clause=_optional_text(payload, "causal_clause"),
        stale_source_text=_optional_text(payload, "stale_source_text"),
        contradiction=_optional_text(payload, "contradiction"),
        authority_cue=_optional_text(payload, "authority_cue"),
    )
    if not case.case_id or ":" in case.case_id:
        raise ValueError("case_id must be non-empty and must not contain ':'")
    if not case.claim:
        raise ValueError(f"{case.case_id}: claim is required")
    if not case.support_span.strip() or case.source_text.count(case.support_span) != 1:
        raise ValueError(f"{case.case_id}: support_span must occur exactly once in source_text")
    return case


def parse_case_file(payload: Mapping[str, Any]) -> tuple[CleanCase, ...]:
    """Parse a versioned case file and require unique case IDs."""
    if payload.get("schema_version") != CASE_SCHEMA_VERSION:
        raise ValueError(f"case file schema_version must be {CASE_SCHEMA_VERSION}")
    cases = tuple(parse_clean_case(entry) for entry in payload.get("cases", ()))
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("case IDs must be unique")
    return cases


def _format_like(original: str, value: float) -> str:
    decimals = len(original.split(".", 1)[1]) if "." in original else 0
    return f"{value:,.{decimals}f}" if "," in original else f"{value:.{decimals}f}"


def _in_span(token: str, span: str) -> bool:
    return re.search(rf"(?<![\d.,]){re.escape(token)}(?![\d]|[.,]\d)", span) is not None


def _after_comparison(claim: str, start: int) -> bool:
    return _COMPARISON_RE.search(claim[:start].rstrip()) is not None


def _wrong_number(case: CleanCase) -> str | None:
    for match in _NUMBER_RE.finditer(case.claim):
        token = match.group(0)
        if _YEAR_RE.fullmatch(token) or not _in_span(token, case.support_span):
            continue
        if _after_comparison(case.claim, match.start()):
            continue
        mutated = _format_like(token, float(token.replace(",", "")) * 2 + 1)
        if mutated in case.source_text:
            continue
        return case.claim[: match.start()] + mutated + case.claim[match.end() :]
    return None


def _wrong_date(case: CleanCase) -> str | None:
    for match in _YEAR_RE.finditer(case.claim):
        year = match.group(0)
        if not _in_span(year, case.support_span) or _after_comparison(case.claim, match.start()):
            continue
        mutated = str(int(year) - 3)
        if mutated in case.source_text:
            continue
        return case.claim[: match.start()] + mutated + case.claim[match.end() :]
    return None


def _negation(case: CleanCase) -> str | None:
    """Flip one active verb or negate one auxiliary; skip already-negated claims.

    A double negative can leave the claim supported, and flipping a passive
    participle ("was acquired by") produces an ungrammatical claim.
    """
    if _NEGATION_RE.search(case.claim):
        return None
    for word, flipped in _VERB_FLIPS:
        for match in re.finditer(rf"\b{word}\b", case.claim):
            before = case.claim[: match.start()].split()
            if before and before[-1].lower() in _PASSIVE_BEFORE:
                continue
            return case.claim[: match.start()] + flipped + case.claim[match.end() :]
    match = _AUXILIARY_RE.search(case.claim)
    if match is None:
        return None
    return case.claim[: match.end()] + " not" + case.claim[match.end() :]


def _wrong_entity(case: CleanCase) -> str | None:
    if case.entity_swap is None:
        return None
    entity, distractor = case.entity_swap
    if entity not in case.claim or distractor in case.source_text:
        return None
    return case.claim.replace(entity, distractor, 1)


def _unsupported_causal(case: CleanCase) -> str | None:
    if case.causal_clause is None:
        return None
    return f"{case.claim.rstrip().rstrip('.')}, {case.causal_clause.rstrip('.')}."


def _item(case: CleanCase, category: str, claim: str, source_text: str) -> ValidationItem:
    return ValidationItem(
        item_id=f"{case.case_id}:{category}",
        case_id=case.case_id,
        category=category,
        claim=claim,
        source_text=source_text,
        expected=SUPPORTED if category == CLEAN else UNSUPPORTED,
        reviewer_kind=case.adjudication.reviewer_kind,
    )


def build_validation_items(
    cases: Sequence[CleanCase],
) -> tuple[tuple[ValidationItem, ...], tuple[SkippedVariant, ...]]:
    """Return every clean item, each buildable variant, and the skipped ones."""
    items: list[ValidationItem] = []
    skipped: list[SkippedVariant] = []
    ordered = sorted(cases, key=lambda case: case.case_id)

    def add(
        case: CleanCase, category: str, claim: str | None, source: str | None, why: str
    ) -> None:
        if claim is None or source is None:
            skipped.append(SkippedVariant(case.case_id, category, why))
        else:
            items.append(_item(case, category, claim, source))

    for index, case in enumerate(ordered):
        items.append(_item(case, CLEAN, case.claim, case.source_text))
        add(
            case,
            "wrong_number",
            _wrong_number(case),
            case.source_text,
            "no unbounded non-year number from the support span",
        )
        add(
            case,
            "wrong_date",
            _wrong_date(case),
            case.source_text,
            "no unbounded year from the support span",
        )
        add(
            case,
            "negation",
            _negation(case),
            case.source_text,
            "already negated, passive, or no flippable verb or auxiliary",
        )
        add(
            case,
            "wrong_entity",
            _wrong_entity(case),
            case.source_text,
            "entity_swap missing, absent from claim, or distractor in source",
        )
        add(
            case,
            "unsupported_causal",
            _unsupported_causal(case),
            case.source_text,
            "causal_clause missing",
        )
        add(
            case,
            "stale_evidence",
            case.claim,
            case.stale_source_text,
            "stale_source_text missing",
        )
        remainder = case.source_text.replace(case.support_span, " ")
        add(
            case,
            "insufficient_support",
            case.claim,
            remainder if remainder.strip() else None,
            "support span is the whole source",
        )
        # Same missing support, now under a strong trust cue: a judge that
        # accepts it is scoring source authority instead of claim support.
        cue = case.authority_cue or DEFAULT_AUTHORITY_CUE
        add(
            case,
            "authority_without_support",
            case.claim,
            f"{cue} {remainder.strip()}" if remainder.strip() else None,
            "support span is the whole source",
        )
        contradicted = (
            None
            if case.contradiction is None
            else f"{case.source_text.rstrip()} {case.contradiction}"
        )
        add(case, "omitted_contradiction", case.claim, contradicted, "contradiction missing")
        other = ordered[(index + 1) % len(ordered)] if len(ordered) > 1 else None
        borrowed = (
            other.source_text
            if other is not None and case.support_span not in other.source_text
            else None
        )
        add(
            case,
            "citation_attribution",
            case.claim,
            borrowed,
            "needs a second case whose source lacks this support span",
        )
    return tuple(items), tuple(skipped)
