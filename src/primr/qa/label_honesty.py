"""Label-honesty pass: downgrade confidence labels that don't trace to source.

primr's June-2026 calibration eval measured a systemic grounding gap: across a
sample of briefs, ``(Confirmed)`` labels traced to their cited source only ~8%
of the time and ``(Reported)`` ~0%. The prose reads authoritative, but the
confidence labels overclaim their grounding. This pass closes that gap the
doctrine-clean way (``docs/design/agentic-balance.md``): model *judgment*
decides whether a cited source substantively supports a labeled claim (reusing
the calibration harness's injectable judge), and the downgrade is a *mechanical*
rewrite -- never a regex that judges content.

Only the unambiguous signal triggers a change. A traceable-class label
(``Confirmed``/``Reported``) whose cited sources were fetched and judged NOT to
support the claim (calibration verdict ``untraceable``) is rewritten to
``(Estimated)`` -- the honest label when the source does not substantiate the
claim, presenting it as the analyst's inference. Every other verdict fails
*open* (the label is kept):

- ``no_source`` / ``unfetchable`` are not positive evidence of an overclaim, so
  acting on them would be the over-correction the doctrine warns against;
- ``traceable`` claims are grounded; ``exempt`` (inference) labels are out of
  scope by design.

Downgrading is asymmetrically safe: a false downgrade only makes a true claim
read more humbly, while a missed overclaim is the exact failure this pass
exists to fix -- so the pass moves confidence in one direction only.

The transformation is pure and the judge/fetch effects are injectable, so the
whole pass is free to validate with mocks. It is *measured*, not gated: it never
blocks shipping (a shipping gate is reserved for structure and irreversible
acts), and it is opt-in at the pipeline so the default run stays byte-identical
until eval validates the recipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from primr.qa.label_calibration import (
    _LABEL_RE,
    TRACEABLE_LABELS,
    calibrate_claims,
    extract_labeled_claims,
)
from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from primr.qa.label_calibration import CalibrationReport

logger = get_logger("qa.label_honesty")

# The honest label for a sourced claim its own source does not substantiate:
# the model's inference, not confirmed or third-party-reported fact.
HONEST_DOWNGRADE_LABEL = "Estimated"

# The single calibration verdict that is positive evidence a traceable-class
# label overclaims: sources existed, were fetched, and none supported the claim.
_DOWNGRADE_VERDICTS = frozenset({"untraceable"})

# Audit EVERY labeled claim (no per-label cap). The pass mutates the report, so a
# cap would be actively harmful: it could leave the same ungrounded claim with
# two different labels in one document. Cost is bounded by the report's
# labeled-claim count, and source fetches are deduped by URL in calibrate_claims.
_AUDIT_ALL: int | None = None


@dataclass(frozen=True)
class LabelDowngrade:
    """One planned label rewrite, with its exact location in the report."""

    section: str
    original_label: str
    new_label: str
    span: tuple[int, int]  # absolute (start, end) of the label token
    sentence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "original_label": self.original_label,
            "new_label": self.new_label,
            "sentence": self.sentence[:300],
        }


@dataclass(frozen=True)
class LabelHonestyResult:
    """Outcome of the pass: the (possibly rewritten) report plus an audit."""

    report_content: str
    downgrades: tuple[LabelDowngrade, ...]

    @property
    def changed(self) -> bool:
        return bool(self.downgrades)

    def to_dict(self) -> dict[str, Any]:
        return {
            "downgraded_count": len(self.downgrades),
            "downgrade_target": HONEST_DOWNGRADE_LABEL,
            "downgrades": [d.to_dict() for d in self.downgrades],
        }


def plan_label_downgrades(
    report_content: str, calibration: CalibrationReport
) -> list[LabelDowngrade]:
    """Decide which labels to downgrade from a calibration report.

    A downgrade is planned only for a traceable-class label with verdict
    ``untraceable`` whose recorded span still points at its own label token --
    if the span drifted (e.g. a directly-built claim), the rewrite is refused
    rather than applied blindly.
    """
    downgrades: list[LabelDowngrade] = []
    for result in calibration.results:
        if result.verdict not in _DOWNGRADE_VERDICTS:
            continue
        claim = result.claim
        if claim.label not in TRACEABLE_LABELS:
            continue
        start, end = claim.label_span
        if start < 0 or start >= end or end > len(report_content):
            continue
        token = report_content[start:end]
        match = _LABEL_RE.fullmatch(token)
        if match is None or match.group(1) != claim.label:
            continue  # span no longer identifies this claim's label; refuse
        downgrades.append(
            LabelDowngrade(
                section=claim.section,
                original_label=claim.label,
                new_label=HONEST_DOWNGRADE_LABEL,
                span=(start, end),
                sentence=claim.sentence,
            )
        )
    return downgrades


def apply_label_downgrades(report_content: str, downgrades: list[LabelDowngrade]) -> str:
    """Rewrite the planned label tokens, dropping any explanatory suffix.

    Applied in reverse offset order so earlier spans are not shifted by later
    edits. The whole label token (including any ``-- per the 10-K`` suffix that
    asserted a grounding which did not hold) is replaced by the plain honest
    label.
    """
    new_label = f"({HONEST_DOWNGRADE_LABEL})"
    for downgrade in sorted(downgrades, key=lambda d: d.span[0], reverse=True):
        start, end = downgrade.span
        report_content = report_content[:start] + new_label + report_content[end:]
    return report_content


def apply_label_honesty(
    report_content: str,
    *,
    fetch_fn: Callable[[str], str] | None = None,
    judge_fn: Callable[[str, str], bool] | None = None,
    max_per_label: int | None = _AUDIT_ALL,
) -> LabelHonestyResult:
    """Audit a report's confidence labels and downgrade the ungrounded ones.

    Extracts labeled claims, judges traceable-class labels against their cited
    sources (via the calibration harness's injectable fetch/judge seams), and
    rewrites the labels that do not trace. Audits every labeled claim by default
    so the mutation is internally consistent. Pure given its seams; with the
    defaults it performs SSRF-guarded fetches and cheap judge LLM calls.
    """
    claims = extract_labeled_claims(report_content, max_per_label=max_per_label)
    calibration = calibrate_claims(claims, fetch_fn=fetch_fn, judge_fn=judge_fn)
    downgrades = plan_label_downgrades(report_content, calibration)
    if not downgrades:
        return LabelHonestyResult(report_content=report_content, downgrades=())
    rewritten = apply_label_downgrades(report_content, downgrades)
    logger.info(
        "Label-honesty: downgraded %d ungrounded label(s) to (%s)",
        len(downgrades),
        HONEST_DOWNGRADE_LABEL,
    )
    return LabelHonestyResult(report_content=rewritten, downgrades=tuple(downgrades))
