"""Measure a claim-support evaluator against frozen, known-answer items.

This is the instrument behind the evaluation plan's "Validate the evaluators"
protocol. It never arms a gate. The flow is:

1. Pre-register tolerances and minimum samples, then freeze the clean cases
   and controlled variants (``freeze_validation_set``). The digest binds both
   and the generator version, so a later edit is detected before judging.
   Record the digest outside this system (for example in the pull request or
   decision record) before any judge runs, so a refreeze after seeing results
   is visible.
2. Run each judge blind (claim and source text only) over the frozen items in
   seeded shuffled passes (``run_judge``). Each call carries one item, so
   repeated passes measure run-to-run consistency, not in-context order effects.
3. Score detection recall per error category, false alarms on clean items,
   abstention, judge failures, retrieval failures, and repeat flips with
   Wilson intervals (``score_run``). Measure errors shared across judges and
   pairwise agreement (``shared_errors``).
4. Queue judge disagreements, repeat flips, and seeded samples of unanimous
   approvals and unanimous rejections for source-grounded human review
   (``review_queue``).
5. ``decide`` rebuilds the score and queue from the runs. It reports
   ``meets_preregistered_tolerance`` only when every item is human-adjudicated,
   samples are large enough, a named human reviewed the whole queue, at least
   two judges and two passes ran, and every interval clears its tolerance.
   Otherwise it names each shortfall.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from primr.qa.calibration_measurement import parse_judge_verdict, wilson_lower_bound
from primr.qa.evaluator_variants import (
    CLEAN,
    ERROR_CATEGORIES,
    GENERATOR_VERSION,
    SUPPORTED,
    ValidationItem,
)
from primr.utils.atomic_io import atomic_write_text

FROZEN_SCHEMA_VERSION = 2
JUDGE_FAILURES = ("unparseable", "error")
RETRIEVAL_FAILURE = "retrieval_failure"

JudgeFn = Callable[[str, str], bool | str]


@dataclass(frozen=True)
class Preregistration:
    """Tolerances fixed before any judge sees the items. No defaults on purpose."""

    registered_on: date
    seed: int
    confidence: float
    min_items_per_category: int
    min_clean_items: int
    min_recall_lower_bound: float
    max_false_alarm_upper_bound: float
    max_abstention_rate: float
    max_failure_rate: float
    max_repeat_flip_rate: float
    approval_sample_size: int
    rejection_sample_size: int
    # Categories where abstaining is the correct response, because the source
    # genuinely lacks the information.
    abstain_detects: tuple[str, ...] = ("insufficient_support",)

    def __post_init__(self) -> None:
        if not 0 < self.confidence < 1:
            raise ValueError("confidence must be between 0 and 1")
        for name in (
            "min_recall_lower_bound",
            "max_false_alarm_upper_bound",
            "max_abstention_rate",
            "max_failure_rate",
            "max_repeat_flip_rate",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        samples = (
            self.min_items_per_category,
            self.min_clean_items,
            self.approval_sample_size,
            self.rejection_sample_size,
        )
        if min(samples) < 1:
            raise ValueError("minimum samples must be positive")
        unknown = set(self.abstain_detects) - set(ERROR_CATEGORIES)
        if unknown:
            raise ValueError(f"unknown abstain_detects categories: {sorted(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["registered_on"] = self.registered_on.isoformat()
        payload["abstain_detects"] = list(self.abstain_detects)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Preregistration:
        values = dict(payload)
        values["registered_on"] = date.fromisoformat(str(values["registered_on"]))
        values["abstain_detects"] = tuple(values.get("abstain_detects", ()))
        return cls(**values)


@dataclass(frozen=True)
class FrozenValidationSet:
    """Items plus pre-registration, bound by a content digest."""

    preregistration: Preregistration
    items: tuple[ValidationItem, ...]
    generator_version: int
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FROZEN_SCHEMA_VERSION,
            "generator_version": self.generator_version,
            "digest": self.digest,
            "preregistration": self.preregistration.to_dict(),
            "items": [item.to_dict() for item in self.items],
        }


def _digest(
    preregistration: Preregistration, items: Sequence[ValidationItem], generator_version: int
) -> str:
    canonical = json.dumps(
        {
            "generator_version": generator_version,
            "preregistration": preregistration.to_dict(),
            "items": [item.to_dict() for item in items],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def freeze_validation_set(
    items: Sequence[ValidationItem],
    preregistration: Preregistration,
    *,
    generator_version: int = GENERATOR_VERSION,
) -> FrozenValidationSet:
    """Validate and bind items and tolerances together before judging.

    Duplicate claim/source pairs are rejected because they would inflate the
    sample and narrow every interval without adding evidence.
    """
    ordered = tuple(sorted(items, key=lambda item: item.item_id))
    if not ordered:
        raise ValueError("a validation set needs at least one item")
    for item in ordered:
        item.validate()
    ids = [item.item_id for item in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("validation item IDs must be unique")
    pairs = [(item.claim, item.source_text) for item in ordered]
    if len(pairs) != len(set(pairs)):
        raise ValueError("validation items must not repeat a claim/source pair")
    digest = _digest(preregistration, ordered, generator_version)
    return FrozenValidationSet(preregistration, ordered, generator_version, digest)


def write_frozen_set(frozen: FrozenValidationSet, path: Path) -> None:
    atomic_write_text(path, json.dumps(frozen.to_dict(), indent=2, ensure_ascii=False) + "\n")


def load_frozen_set(path: Path) -> FrozenValidationSet:
    """Load a frozen set and reject any edit made after freezing."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != FROZEN_SCHEMA_VERSION:
        raise ValueError(f"frozen set schema_version must be {FROZEN_SCHEMA_VERSION}")
    preregistration = Preregistration.from_dict(payload["preregistration"])
    items = tuple(ValidationItem.from_dict(entry) for entry in payload["items"])
    frozen = freeze_validation_set(
        items, preregistration, generator_version=int(payload["generator_version"])
    )
    if frozen.digest != payload.get("digest"):
        raise ValueError("frozen validation set changed after freezing")
    return frozen


@dataclass(frozen=True)
class JudgeRun:
    """Verdicts from one judge over every pass of one frozen set."""

    judge_name: str
    frozen_digest: str
    # verdicts[pass_index][item_id] -> yes | no | abstain | unparseable | error | retrieval_failure
    verdicts: tuple[dict[str, str], ...]

    def primary(self) -> dict[str, str]:
        return self.verdicts[0]


def _coerce(raw: bool | str) -> str:
    if raw is True:
        return "yes"
    if raw is False:
        return "no"
    return parse_judge_verdict(str(raw))


def pass_order(frozen: FrozenValidationSet, pass_index: int) -> list[str]:
    """The seeded item order a pass presents to the judge."""
    ids = [item.item_id for item in frozen.items]
    random.Random(f"{frozen.preregistration.seed}:{pass_index}").shuffle(ids)
    return ids


def run_judge(
    frozen: FrozenValidationSet, judge_fn: JudgeFn, *, judge_name: str, passes: int = 2
) -> JudgeRun:
    """Present each item blind in seeded orders and record normalized verdicts.

    The judge receives only claim and source text: no item ID, category,
    expected verdict, or provider identity. An empty source is a retrieval
    failure and is never sent. A raised exception is recorded as ``error``.
    """
    if passes < 1:
        raise ValueError("passes must be positive")
    if not judge_name.strip():
        raise ValueError("judge_name is required")
    by_id = {item.item_id: item for item in frozen.items}
    verdicts: list[dict[str, str]] = []
    for pass_index in range(passes):
        current: dict[str, str] = {}
        for item_id in pass_order(frozen, pass_index):
            item = by_id[item_id]
            if not item.source_text.strip():
                current[item_id] = RETRIEVAL_FAILURE
                continue
            try:
                current[item_id] = _coerce(judge_fn(item.claim, item.source_text))
            except Exception:  # A judge failure is a measured outcome, not a crash.
                current[item_id] = "error"
        verdicts.append(current)
    return JudgeRun(judge_name, frozen.digest, tuple(verdicts))


def is_correct(item: ValidationItem, verdict: str, preregistration: Preregistration) -> bool:
    """A clean item is correct on ``yes``; a variant on ``no`` (or a permitted abstain)."""
    if item.expected == SUPPORTED:
        return verdict == "yes"
    return verdict == "no" or (
        verdict == "abstain" and item.category in preregistration.abstain_detects
    )


def wilson_interval(successes: int, trials: int, confidence: float) -> tuple[float, float]:
    lower = wilson_lower_bound(successes, trials, confidence=confidence)
    upper = 1.0 - wilson_lower_bound(trials - successes, trials, confidence=confidence)
    return lower, upper


@dataclass(frozen=True)
class CategoryScore:
    category: str
    n: int
    correct: int
    abstained: int
    failed: int
    rate: float | None
    interval: tuple[float, float] | None


@dataclass(frozen=True)
class ValidationScore:
    """One judge's measurements. Clean ``rate`` is the acceptance rate."""

    judge_name: str
    categories: dict[str, CategoryScore]
    clean: CategoryScore
    # Clean items answered anything other than yes or abstain.
    false_alarms: int
    false_alarm_interval: tuple[float, float] | None
    # Pooled across categories: the share of "no" answers that hit a variant.
    # It depends on the variant-to-clean mix, so it is reported, not gated.
    flag_precision: float | None
    # Abstentions outside the categories where abstaining is correct.
    abstention_rate: float
    failure_rate: float
    retrieval_failure_rate: float
    repeat_flip_rate: float | None
    repeat_flips: tuple[str, ...]


def _check_run(frozen: FrozenValidationSet, run: JudgeRun) -> None:
    if run.frozen_digest != frozen.digest:
        raise ValueError(f"judge run {run.judge_name} belongs to a different frozen set")


def _category_score(
    category: str,
    items: Sequence[ValidationItem],
    verdicts: Mapping[str, str],
    preregistration: Preregistration,
) -> CategoryScore:
    n = len(items)
    correct = sum(is_correct(item, verdicts[item.item_id], preregistration) for item in items)
    abstained = sum(verdicts[item.item_id] == "abstain" for item in items)
    failed = sum(verdicts[item.item_id] in (*JUDGE_FAILURES, RETRIEVAL_FAILURE) for item in items)
    if not n:
        return CategoryScore(category, 0, 0, abstained, failed, None, None)
    interval = wilson_interval(correct, n, preregistration.confidence)
    return CategoryScore(category, n, correct, abstained, failed, correct / n, interval)


def score_run(frozen: FrozenValidationSet, run: JudgeRun) -> ValidationScore:
    """Score one judge. Missing, failed, or wrong-set verdicts are never correct."""
    _check_run(frozen, run)
    prereg = frozen.preregistration
    verdicts = {item.item_id: run.primary().get(item.item_id, "error") for item in frozen.items}
    grouped: dict[str, list[ValidationItem]] = {}
    for item in frozen.items:
        grouped.setdefault(item.category, []).append(item)
    categories = {
        category: _category_score(category, grouped.get(category, []), verdicts, prereg)
        for category in ERROR_CATEGORIES
    }
    clean_items = grouped.get(CLEAN, [])
    clean = _category_score(CLEAN, clean_items, verdicts, prereg)
    false_alarms = sum(verdicts[item.item_id] not in ("yes", "abstain") for item in clean_items)
    false_alarm_interval = (
        wilson_interval(false_alarms, len(clean_items), prereg.confidence) if clean_items else None
    )
    flagged = sum(verdicts[item.item_id] == "no" for item in frozen.items if item.category != CLEAN)
    clean_no = sum(verdicts[item.item_id] == "no" for item in clean_items)
    flag_precision = flagged / (flagged + clean_no) if flagged + clean_no else None
    total = len(frozen.items)
    unwarranted_abstentions = sum(
        verdicts[item.item_id] == "abstain" and not is_correct(item, "abstain", prereg)
        for item in frozen.items
    )
    failed = sum(verdict in JUDGE_FAILURES for verdict in verdicts.values())
    retrieval = sum(verdict == RETRIEVAL_FAILURE for verdict in verdicts.values())
    flips: tuple[str, ...] = ()
    flip_rate = None
    if len(run.verdicts) > 1:
        flips = tuple(
            item.item_id
            for item in frozen.items
            if len({passed.get(item.item_id, "error") for passed in run.verdicts}) > 1
        )
        flip_rate = len(flips) / total
    return ValidationScore(
        judge_name=run.judge_name,
        categories=categories,
        clean=clean,
        false_alarms=false_alarms,
        false_alarm_interval=false_alarm_interval,
        flag_precision=flag_precision,
        abstention_rate=unwarranted_abstentions / total,
        failure_rate=failed / total,
        retrieval_failure_rate=retrieval / total,
        repeat_flip_rate=flip_rate,
        repeat_flips=flips,
    )


@dataclass(frozen=True)
class SharedErrors:
    """Errors common to every judge. Correlated misses are not independent votes."""

    judges: tuple[str, ...]
    wrong_by_all: tuple[str, ...]
    wrong_by_any: tuple[str, ...]
    # (judge_a, judge_b) -> share of items with identical primary verdicts.
    pairwise_agreement: dict[tuple[str, str], float]


def shared_errors(frozen: FrozenValidationSet, runs: Sequence[JudgeRun]) -> SharedErrors:
    prereg = frozen.preregistration
    wrong_by: dict[str, int] = {}
    for run in runs:
        _check_run(frozen, run)
        primary = run.primary()
        for item in frozen.items:
            if not is_correct(item, primary.get(item.item_id, "error"), prereg):
                wrong_by[item.item_id] = wrong_by.get(item.item_id, 0) + 1
    agreement: dict[tuple[str, str], float] = {}
    for left, right in itertools.combinations(runs, 2):
        same = sum(
            left.primary().get(item.item_id, "error") == right.primary().get(item.item_id, "error")
            for item in frozen.items
        )
        agreement[(left.judge_name, right.judge_name)] = same / len(frozen.items)
    return SharedErrors(
        judges=tuple(run.judge_name for run in runs),
        wrong_by_all=tuple(sorted(i for i, count in wrong_by.items() if count == len(runs))),
        wrong_by_any=tuple(sorted(wrong_by)),
        pairwise_agreement=agreement,
    )


@dataclass(frozen=True)
class ReviewQueue:
    """Items a person must check against the source before any decision.

    Item IDs name the variant category. Present items to reviewers without
    their IDs and expected verdicts when blind review matters.
    """

    disagreements: tuple[str, ...]
    repeat_flips: tuple[str, ...]
    approval_sample: tuple[str, ...]
    rejection_sample: tuple[str, ...]

    def required(self) -> frozenset[str]:
        return frozenset(
            (*self.disagreements, *self.repeat_flips, *self.approval_sample, *self.rejection_sample)
        )


def review_queue(frozen: FrozenValidationSet, runs: Sequence[JudgeRun]) -> ReviewQueue:
    """Disagreements, repeat flips, and seeded samples of unanimous answers.

    Unanimous approvals of variants are where a shared blind spot hides.
    Unanimous rejections are where a mis-built variant (one the source still
    supports) hides behind apparently correct answers. Both are sampled.
    """
    if not runs:
        raise ValueError("review_queue needs at least one judge run")
    for run in runs:
        _check_run(frozen, run)
    prereg = frozen.preregistration
    primaries = [run.primary() for run in runs]
    disagreements: list[str] = []
    approvals: list[str] = []
    rejections: list[str] = []
    flips: set[str] = set()
    for run in runs:
        for item in frozen.items:
            if len({passed.get(item.item_id, "error") for passed in run.verdicts}) > 1:
                flips.add(item.item_id)
    for item in frozen.items:
        answers = {primary.get(item.item_id, "error") for primary in primaries}
        if len(answers) > 1:
            disagreements.append(item.item_id)
        elif answers == {"yes"}:
            approvals.append(item.item_id)
        elif answers == {"no"} and item.category != CLEAN:
            rejections.append(item.item_id)

    def sample(pool: list[str], size: int, label: str) -> tuple[str, ...]:
        rng = random.Random(f"{prereg.seed}:{label}")
        return tuple(sorted(rng.sample(pool, min(size, len(pool)))))

    return ReviewQueue(
        disagreements=tuple(disagreements),
        repeat_flips=tuple(sorted(flips)),
        approval_sample=sample(approvals, prereg.approval_sample_size, "approvals"),
        rejection_sample=sample(rejections, prereg.rejection_sample_size, "rejections"),
    )


@dataclass(frozen=True)
class HumanReview:
    """A person's source-grounded review of the queue for one frozen set.

    The record is self-reported. Keep it with the operator's evidence so the
    named reviewer can be confirmed outside this system.
    """

    frozen_digest: str
    reviewer_kind: str
    reviewer: str
    reviewed_on: date
    reviewed_item_ids: frozenset[str]
    # Items whose expected verdict the reviewer found mis-built.
    disputed_item_ids: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> HumanReview:
        return cls(
            frozen_digest=str(payload["frozen_digest"]),
            reviewer_kind=str(payload["reviewer_kind"]),
            reviewer=str(payload["reviewer"]).strip(),
            reviewed_on=date.fromisoformat(str(payload["reviewed_on"])),
            reviewed_item_ids=frozenset(map(str, payload.get("reviewed_item_ids", ()))),
            disputed_item_ids=frozenset(map(str, payload.get("disputed_item_ids", ()))),
        )


@dataclass(frozen=True)
class ValidationDecision:
    """Outcome for one judge. ``reasons`` names every shortfall found."""

    judge_name: str
    status: str
    reasons: tuple[str, ...]
    score: ValidationScore
    queue: ReviewQueue
    shared: SharedErrors


def _sample_gaps(frozen: FrozenValidationSet) -> list[str]:
    prereg = frozen.preregistration
    gaps: list[str] = []
    unreviewed = sum(item.reviewer_kind != "human" for item in frozen.items)
    if unreviewed:
        gaps.append(f"{unreviewed} items lack human adjudication; freeze a human-only set")
    counts = dict.fromkeys((CLEAN, *ERROR_CATEGORIES), 0)
    for item in frozen.items:
        if item.reviewer_kind == "human":
            counts[item.category] += 1
    if counts[CLEAN] < prereg.min_clean_items:
        gaps.append(f"human clean items: {counts[CLEAN]} < {prereg.min_clean_items}")
    for category in ERROR_CATEGORIES:
        if counts[category] < prereg.min_items_per_category:
            gaps.append(f"{category}: {counts[category]} < {prereg.min_items_per_category} items")
    return gaps


def _review_gaps(
    frozen: FrozenValidationSet, queue: ReviewQueue, review: HumanReview | None
) -> list[str]:
    if review is None:
        return ["no human review recorded"]
    gaps: list[str] = []
    if review.frozen_digest != frozen.digest:
        gaps.append("review belongs to a different frozen set")
    if review.reviewer_kind != "human":
        gaps.append(f"reviewer_kind is {review.reviewer_kind}, not human")
    if not review.reviewer:
        gaps.append("reviewer is not named")
    missing = queue.required() - review.reviewed_item_ids
    if missing:
        gaps.append(f"{len(missing)} queued items not reviewed")
    if review.disputed_item_ids:
        gaps.append(f"{len(review.disputed_item_ids)} items disputed; rebuild and refreeze")
    return gaps


def _tolerance_findings(
    score: ValidationScore, prereg: Preregistration, judges: int
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    unclear: list[str] = []
    for category, result in score.categories.items():
        assert result.rate is not None
        assert result.interval is not None
        if result.rate < prereg.min_recall_lower_bound:
            failures.append(f"{category} recall {result.rate:.3f}")
        elif result.interval[0] < prereg.min_recall_lower_bound:
            unclear.append(f"{category} recall lower bound {result.interval[0]:.3f}")
    assert score.clean.n
    assert score.false_alarm_interval is not None
    false_alarm_rate = score.false_alarms / score.clean.n
    if false_alarm_rate > prereg.max_false_alarm_upper_bound:
        failures.append(f"false alarm rate {false_alarm_rate:.3f}")
    elif score.false_alarm_interval[1] > prereg.max_false_alarm_upper_bound:
        unclear.append(f"false alarm upper bound {score.false_alarm_interval[1]:.3f}")
    for name, value, limit in (
        ("abstention rate", score.abstention_rate, prereg.max_abstention_rate),
        ("judge failure rate", score.failure_rate, prereg.max_failure_rate),
        ("retrieval failure rate", score.retrieval_failure_rate, prereg.max_failure_rate),
    ):
        if value > limit:
            failures.append(f"{name} {value:.3f}")
    if score.repeat_flip_rate is None:
        unclear.append("repeat consistency not measured; run at least two passes")
    elif score.repeat_flip_rate > prereg.max_repeat_flip_rate:
        failures.append(f"repeat flip rate {score.repeat_flip_rate:.3f}")
    if judges < 2:
        unclear.append("one judge: disagreements and shared errors are unmeasured")
    return failures, unclear


def decide(
    frozen: FrozenValidationSet,
    runs: Sequence[JudgeRun],
    judge_name: str,
    review: HumanReview | None,
) -> ValidationDecision:
    """Decide for one judge, rebuilding its score and the queue from every run.

    Statuses, in precedence order: ``insufficient_sample``,
    ``incomplete_review``, ``fails_preregistered_tolerance``, ``inconclusive``,
    and ``meets_preregistered_tolerance``. None of them arms a gate.
    """
    matching = [run for run in runs if run.judge_name == judge_name]
    if len(matching) != 1:
        raise ValueError(f"expected exactly one run named {judge_name}")
    names = [run.judge_name for run in runs]
    if len(names) != len(set(names)):
        raise ValueError("judge run names must be unique")
    score = score_run(frozen, matching[0])
    queue = review_queue(frozen, runs)
    shared = shared_errors(frozen, runs)

    def result(status: str, reasons: Sequence[str]) -> ValidationDecision:
        return ValidationDecision(judge_name, status, tuple(reasons), score, queue, shared)

    sample = _sample_gaps(frozen)
    if sample:
        return result("insufficient_sample", sample)
    review_gaps = _review_gaps(frozen, queue, review)
    if review_gaps:
        return result("incomplete_review", review_gaps)
    failures, unclear = _tolerance_findings(score, frozen.preregistration, len(runs))
    if failures:
        return result("fails_preregistered_tolerance", failures + unclear)
    if unclear:
        return result("inconclusive", unclear)
    return result("meets_preregistered_tolerance", ())
