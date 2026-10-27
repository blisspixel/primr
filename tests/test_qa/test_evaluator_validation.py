"""Evaluator validation: controlled variants, freezing, scoring, and decisions."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from primr.qa.evaluator_validation import (
    FrozenValidationSet,
    HumanReview,
    JudgeRun,
    Preregistration,
    decide,
    freeze_validation_set,
    load_frozen_set,
    pass_order,
    review_queue,
    run_judge,
    score_run,
    shared_errors,
    write_frozen_set,
)
from primr.qa.evaluator_variants import (
    CLEAN,
    ERROR_CATEGORIES,
    ValidationItem,
    build_validation_items,
    parse_case_file,
    parse_clean_case,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "evaluator_validation" / "synthetic_cases.json"


def _prereg(**overrides: object) -> Preregistration:
    values: dict[str, object] = {
        "registered_on": date(2026, 10, 27),
        "seed": 7,
        "confidence": 0.95,
        "min_items_per_category": 1,
        "min_clean_items": 1,
        "min_recall_lower_bound": 0.5,
        "max_false_alarm_upper_bound": 0.5,
        "max_abstention_rate": 0.5,
        "max_failure_rate": 0.05,
        "max_repeat_flip_rate": 0.1,
        "approval_sample_size": 3,
        "rejection_sample_size": 3,
    }
    values.update(overrides)
    return Preregistration(**values)  # type: ignore[arg-type]


def _fixture_items() -> tuple[ValidationItem, ...]:
    cases = parse_case_file(json.loads(FIXTURE.read_text(encoding="utf-8")))
    items, _skipped = build_validation_items(cases)
    return items


def _case_payload(index: int, reviewer_kind: str = "human", **overrides: object) -> dict:
    revenue = 100 + index * 7
    payload: dict = {
        "case_id": f"exampleco-{index:03d}",
        "claim": f"ExampleCo unit {index} reported revenue of ${revenue} million in 2025.",
        "source_text": (
            f"Filing {index}. In 2025 ExampleCo unit {index} reported revenue of "
            f"${revenue} million. Other notes follow."
        ),
        "support_span": f"In 2025 ExampleCo unit {index} reported revenue of ${revenue} million",
        "adjudication": {
            "reviewer_kind": reviewer_kind,
            "reviewer": "Reviewer A",
            "reviewed_on": "2026-10-27",
        },
        "entity_swap": ["ExampleCo", "Acme Corp"],
        "causal_clause": "driven by a price increase",
        "stale_source_text": f"Filing {index}. In 2021 the unit reported revenue of $9 million.",
        "contradiction": f"A later filing restated unit {index} revenue to $1 million.",
    }
    payload.update(overrides)
    return payload


def _built(**overrides: object) -> dict[str, ValidationItem]:
    case = parse_clean_case(_case_payload(1, **overrides))
    items, _skipped = build_validation_items([case])
    return {item.category: item for item in items}


def _large_set(count: int, reviewer_kind: str = "human", **prereg: object) -> FrozenValidationSet:
    cases = [parse_clean_case(_case_payload(i, reviewer_kind)) for i in range(count)]
    items, skipped = build_validation_items(cases)
    assert skipped == ()
    return freeze_validation_set(items, _prereg(**prereg))


def _oracle(frozen: FrozenValidationSet):
    answers = {
        (item.claim, item.source_text): "yes" if item.category == CLEAN else "no"
        for item in frozen.items
    }
    return lambda claim, source_text: answers[(claim, source_text)]


def _full_review(frozen: FrozenValidationSet, runs, kind: str = "human") -> HumanReview:
    return HumanReview(
        frozen_digest=frozen.digest,
        reviewer_kind=kind,
        reviewer="Reviewer A",
        reviewed_on=date(2026, 10, 28),
        reviewed_item_ids=review_queue(frozen, runs).required(),
    )


def _two_judges(frozen: FrozenValidationSet, judge, passes: int = 2) -> list[JudgeRun]:
    return [
        run_judge(frozen, judge, judge_name="judge", passes=passes),
        run_judge(frozen, _oracle(frozen), judge_name="second", passes=passes),
    ]


class TestCases:
    def test_fixture_builds_every_category_for_a_fully_hinted_case(self):
        built = {item.category for item in _fixture_items() if item.case_id == "exampleco-revenue"}
        assert built == {CLEAN, *ERROR_CATEGORIES}

    def test_variants_apply_the_named_defect(self):
        items = {item.item_id: item for item in _fixture_items()}
        assert "$825 million" in items["exampleco-revenue:wrong_number"].claim
        assert "2022" in items["exampleco-revenue:wrong_date"].claim
        assert items["exampleco-revenue:wrong_entity"].claim.startswith("Acme Corp")
        assert items["exampleco-revenue:negation"].claim.startswith("ExampleCo did not report")
        assert items["acme-headcount:negation"].claim.startswith("Acme Corp reduced")
        assert "$412 million" not in items["exampleco-revenue:insufficient_support"].source_text
        assert items["exampleco-revenue:citation_attribution"].source_text.startswith("Workforce")

    def test_missing_hints_are_skipped_with_reasons(self):
        cases = parse_case_file(json.loads(FIXTURE.read_text(encoding="utf-8")))
        _items, skipped = build_validation_items(cases)
        reasons = {s.category: s.reason for s in skipped if s.case_id == "acme-headcount"}
        assert set(reasons) == {
            "wrong_entity",
            "unsupported_causal",
            "stale_evidence",
            "omitted_contradiction",
        }
        assert all(reasons.values())

    def test_single_case_cannot_borrow_a_citation(self):
        _items, skipped = build_validation_items([parse_clean_case(_case_payload(1))])
        assert "citation_attribution" in {s.category for s in skipped}

    def test_negation_skips_already_negated_claims(self):
        claim = "ExampleCo has not disclosed revenue of $107 million in 2025."
        assert "negation" not in _built(claim=claim, source_text=claim, support_span=claim)

    def test_negation_leaves_passive_participles_grammatical(self):
        claim = "ExampleCo was acquired by Acme Corp in 2025."
        built = _built(claim=claim, source_text=claim, support_span=claim, entity_swap=None)
        assert built["negation"].claim == "ExampleCo was not acquired by Acme Corp in 2025."

    def test_bounded_numbers_and_dates_are_not_mutated(self):
        claim = "ExampleCo has fewer than 5 offices opened after 2020."
        built = _built(claim=claim, source_text=claim, support_span=claim)
        assert "wrong_number" not in built
        assert "wrong_date" not in built

    def test_number_must_match_a_whole_token_in_the_span(self):
        source = "ExampleCo opened 15 offices."
        built = _built(claim="ExampleCo opened 5 offices.", source_text=source, support_span=source)
        assert "wrong_number" not in built

    def test_whole_source_support_span_skips_insufficient_support(self):
        text = "ExampleCo reported revenue of $107 million in 2025."
        assert "insufficient_support" not in _built(source_text=text, support_span=text, claim=text)

    @pytest.mark.parametrize(
        ("field", "value"),
        [("support_span", "text that is absent"), ("case_id", "bad:id"), ("claim", " ")],
    )
    def test_invalid_cases_are_rejected(self, field, value):
        with pytest.raises(ValueError):
            parse_clean_case(_case_payload(1, **{field: value}))

    def test_unknown_reviewer_kind_and_duplicate_ids_are_rejected(self):
        adjudication = {"reviewer_kind": "model", "reviewer": "x", "reviewed_on": "2026-10-27"}
        with pytest.raises(ValueError):
            parse_clean_case(_case_payload(1, adjudication=adjudication))
        with pytest.raises(ValueError):
            parse_case_file({"schema_version": 1, "cases": [_case_payload(1), _case_payload(1)]})


class TestFreezing:
    def test_digest_ignores_input_order_and_round_trips(self, tmp_path):
        items = _fixture_items()
        first = freeze_validation_set(items, _prereg())
        assert first.digest == freeze_validation_set(tuple(reversed(items)), _prereg()).digest
        path = tmp_path / "frozen.json"
        write_frozen_set(first, path)
        assert load_frozen_set(path) == first

    @pytest.mark.parametrize("target", ["item", "threshold", "generator"])
    def test_edits_after_freezing_are_detected(self, tmp_path, target):
        path = tmp_path / "frozen.json"
        write_frozen_set(freeze_validation_set(_fixture_items(), _prereg()), path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if target == "item":
            payload["items"][0]["claim"] += " Edited."
        elif target == "threshold":
            payload["preregistration"]["min_recall_lower_bound"] = 0.1
        else:
            payload["generator_version"] -= 1
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="changed after freezing"):
            load_frozen_set(path)

    @pytest.mark.parametrize(
        "item",
        [
            ValidationItem("a:clean", "a", CLEAN, "Claim.", "Source.", "unsupported", "human"),
            ValidationItem("a:negation", "a", "negation", "C.", "S.", "supported", "human"),
            ValidationItem("a:clean", "a", CLEAN, "Claim.", "Source.", "supported", "robot"),
            ValidationItem("b:clean", "a", CLEAN, "Claim.", "Source.", "supported", "human"),
            ValidationItem("a:clean", "a", CLEAN, "Claim.", " ", "supported", "human"),
        ],
    )
    def test_inconsistent_items_are_rejected(self, item):
        with pytest.raises(ValueError):
            freeze_validation_set([item], _prereg())

    def test_duplicate_claim_source_pairs_are_rejected(self):
        first = ValidationItem("a:clean", "a", CLEAN, "Claim.", "Source.", "supported", "human")
        second = replace(first, item_id="b:clean", case_id="b")
        with pytest.raises(ValueError, match="repeat"):
            freeze_validation_set([first, second], _prereg())

    def test_preregistration_rejects_out_of_range_tolerances(self):
        with pytest.raises(ValueError):
            _prereg(min_recall_lower_bound=1.5)
        with pytest.raises(ValueError):
            _prereg(abstain_detects=("not_a_category",))


class TestRunning:
    def test_judge_is_blind_and_passes_use_distinct_seeded_orders(self):
        frozen = freeze_validation_set(_fixture_items(), _prereg())
        seen: list[tuple[str, str]] = []

        def judge(claim: str, source_text: str) -> bool:
            seen.append((claim, source_text))
            return True

        run = run_judge(frozen, judge, judge_name="recording", passes=2)
        assert len(seen) == 2 * len(frozen.items)
        assert pass_order(frozen, 0) != pass_order(frozen, 1)
        assert pass_order(frozen, 0) == pass_order(frozen, 0)
        assert set(run.primary().values()) == {"yes"}

    def test_exceptions_are_recorded_not_raised(self):
        frozen = _large_set(2)

        def judge(claim: str, source_text: str) -> str:
            raise RuntimeError("judge offline")

        run = run_judge(frozen, judge, judge_name="broken", passes=1)
        assert set(run.primary().values()) == {"error"}
        score = score_run(frozen, run)
        assert score.failure_rate == 1.0
        assert score.false_alarms == score.clean.n


class TestScoring:
    def test_oracle_judge_detects_every_variant(self):
        frozen = _large_set(4)
        score = score_run(frozen, run_judge(frozen, _oracle(frozen), judge_name="oracle"))
        assert all(result.rate == 1.0 for result in score.categories.values())
        assert score.false_alarms == 0
        assert score.flag_precision == 1.0
        assert score.repeat_flip_rate == 0.0

    def test_always_yes_judge_misses_everything_without_false_alarms(self):
        frozen = _large_set(4)
        score = score_run(frozen, run_judge(frozen, lambda c, s: True, judge_name="yes"))
        assert all(result.rate == 0.0 for result in score.categories.values())
        assert score.clean.rate == 1.0
        assert score.flag_precision is None

    def test_unparseable_clean_answers_are_false_alarms(self):
        frozen = _large_set(3)
        score = score_run(frozen, run_judge(frozen, lambda c, s: "maybe", judge_name="garbage"))
        assert score.false_alarms == score.clean.n
        assert score.failure_rate == 1.0

    def test_permitted_abstentions_are_not_counted_against_the_judge(self):
        frozen = _large_set(2)
        score = score_run(frozen, run_judge(frozen, lambda c, s: "abstain", judge_name="abstain"))
        assert score.categories["insufficient_support"].rate == 1.0
        assert score.categories["wrong_number"].rate == 0.0
        permitted = score.categories["insufficient_support"].n
        assert score.abstention_rate == pytest.approx(1 - permitted / len(frozen.items))

    def test_run_from_another_set_is_rejected(self):
        run = run_judge(_large_set(3), lambda c, s: True, judge_name="yes", passes=1)
        with pytest.raises(ValueError):
            score_run(_large_set(2), run)

    def test_shared_errors_agreement_and_review_queue(self):
        frozen = _large_set(3)
        always_yes = run_judge(frozen, lambda c, s: True, judge_name="yes", passes=1)
        oracle = run_judge(frozen, _oracle(frozen), judge_name="oracle", passes=1)
        lenient = run_judge(frozen, lambda c, s: True, judge_name="also-yes", passes=1)
        shared = shared_errors(frozen, [always_yes, lenient])
        variants = sorted(i.item_id for i in frozen.items if i.category != CLEAN)
        assert list(shared.wrong_by_all) == variants
        assert shared.pairwise_agreement == {("yes", "also-yes"): 1.0}
        queue = review_queue(frozen, [always_yes, oracle])
        assert sorted(queue.disagreements) == variants
        assert len(queue.approval_sample) == 3
        assert review_queue(frozen, [always_yes, oracle]) == queue
        assert len(review_queue(frozen, [oracle]).rejection_sample) == 3

    def test_repeat_flips_are_measured_and_queued(self):
        frozen = _large_set(2)
        calls = {"n": 0}

        def flaky(claim: str, source_text: str) -> bool:
            calls["n"] += 1
            return calls["n"] <= len(frozen.items)

        run = run_judge(frozen, flaky, judge_name="flaky", passes=2)
        assert score_run(frozen, run).repeat_flip_rate == 1.0
        assert set(review_queue(frozen, [run]).repeat_flips) == {i.item_id for i in frozen.items}


class TestDecision:
    def _decide(self, frozen, judge, review_kind: str | None = "human", passes: int = 2):
        runs = _two_judges(frozen, judge, passes)
        review = _full_review(frozen, runs, review_kind) if review_kind else None
        return decide(frozen, runs, "judge", review)

    def test_small_sample_is_insufficient(self):
        frozen = _large_set(2, min_items_per_category=5, min_clean_items=5)
        assert self._decide(frozen, _oracle(frozen)).status == "insufficient_sample"

    def test_synthetic_adjudication_never_counts_as_human(self):
        frozen = _large_set(4, reviewer_kind="synthetic")
        decision = self._decide(frozen, _oracle(frozen))
        assert decision.status == "insufficient_sample"
        assert any("lack human adjudication" in reason for reason in decision.reasons)

    @pytest.mark.parametrize("review_kind", [None, "agent"])
    def test_missing_or_non_human_review_is_incomplete(self, review_kind):
        frozen = _large_set(4)
        assert self._decide(frozen, _oracle(frozen), review_kind).status == "incomplete_review"

    def test_unnamed_reviewer_and_partial_coverage_are_incomplete(self):
        frozen = _large_set(4)
        runs = _two_judges(frozen, lambda c, s: True)
        review = _full_review(frozen, runs)
        partial = replace(review, reviewed_item_ids=frozenset(sorted(review.reviewed_item_ids)[1:]))
        assert decide(frozen, runs, "judge", partial).status == "incomplete_review"
        unnamed = replace(review, reviewer="")
        assert decide(frozen, runs, "judge", unnamed).status == "incomplete_review"

    def test_disputed_items_block_a_decision(self):
        frozen = _large_set(4)
        runs = _two_judges(frozen, _oracle(frozen))
        review = replace(
            _full_review(frozen, runs), disputed_item_ids=frozenset({"exampleco-000:negation"})
        )
        assert decide(frozen, runs, "judge", review).status == "incomplete_review"

    def test_weak_judge_fails(self):
        frozen = _large_set(4)
        assert self._decide(frozen, lambda c, s: True).status == "fails_preregistered_tolerance"

    def test_perfect_judge_on_small_sample_is_inconclusive(self):
        frozen = _large_set(3, min_recall_lower_bound=0.8)
        decision = self._decide(frozen, _oracle(frozen))
        assert decision.status == "inconclusive"
        assert any("lower bound" in reason for reason in decision.reasons)

    def test_single_pass_or_single_judge_cannot_meet_tolerance(self):
        frozen = _large_set(30, min_recall_lower_bound=0.8, max_false_alarm_upper_bound=0.2)
        assert self._decide(frozen, _oracle(frozen), passes=1).status == "inconclusive"
        alone = [run_judge(frozen, _oracle(frozen), judge_name="judge")]
        decision = decide(frozen, alone, "judge", _full_review(frozen, alone))
        assert decision.status == "inconclusive"
        assert any("one judge" in reason for reason in decision.reasons)

    def test_perfect_judges_on_adequate_reviewed_sample_meet_tolerance(self):
        frozen = _large_set(30, min_recall_lower_bound=0.8, max_false_alarm_upper_bound=0.2)
        decision = self._decide(frozen, _oracle(frozen))
        assert decision.status == "meets_preregistered_tolerance"
        assert decision.reasons == ()

    def test_judge_names_must_identify_one_run(self):
        frozen = _large_set(2)
        runs = [run_judge(frozen, _oracle(frozen), judge_name="judge")] * 2
        with pytest.raises(ValueError):
            decide(frozen, runs, "judge", None)


@settings(max_examples=50, deadline=None)
@given(st.lists(st.sampled_from(["yes", "no", "abstain", "unparseable"]), min_size=30, max_size=30))
def test_scores_stay_bounded_and_never_meet_below_minimum_sample(verdicts):
    frozen = _large_set(3, min_items_per_category=4)
    answers = dict(zip(pass_order(frozen, 0), verdicts, strict=True))
    by_pair = {(i.claim, i.source_text): answers[i.item_id] for i in frozen.items}
    runs = _two_judges(frozen, lambda c, s: by_pair[(c, s)], passes=1)
    score = score_run(frozen, runs[0])
    for result in [*score.categories.values(), score.clean]:
        assert result.rate is not None
        assert result.interval is not None
        assert result.interval[0] <= result.rate <= result.interval[1]
    assert 0 <= score.abstention_rate <= 1
    assert 0 <= score.false_alarms <= score.clean.n
    decision = decide(frozen, runs, "judge", _full_review(frozen, runs))
    assert decision.status == "insufficient_sample"
