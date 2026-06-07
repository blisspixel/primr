"""Unit tests for Tier-2 trigger evaluation + description optimization.

LLM calls are mocked at the grok_llm seam so these run offline. The mock
dispatches on which prompt is being rendered (gen / score / optimize).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from primr.skill_pack.schema import Skill
from primr.skill_pack.trigger_eval import (
    TriggerEval,
    _split_train_test,
    optimize_skill_description,
    score_description,
)

_BODY = (
    "## What This Skill Does\n\n" + ("Does a thing. " * 30) + "\n\n## Workflow\n\n"
    "1. Step one.\n2. Step two.\n\n## Output Format\n\nA table."
)


def _skill(description: str) -> Skill:
    return Skill(
        name="conducting-sam-assessments",
        display_name="Conducting SAM assessments",
        description=description,
        body=_BODY,
    )


def _evals() -> list[TriggerEval]:
    return [
        TriggerEval("run a SAM assessment", True),
        TriggerEval("analyze our licensing", True),
        TriggerEval("find cost savings", True),
        TriggerEval("reset my password", False),
        TriggerEval("write a marketing email", False),
        TriggerEval("deploy a kubernetes cluster", False),
    ]


def test_split_train_test_is_stratified_and_deterministic():
    evals = _evals()
    train, test = _split_train_test(evals)
    # Both splits carry positives and negatives; deterministic across calls.
    assert any(e.should_trigger for e in test)
    assert any(not e.should_trigger for e in test)
    assert train
    assert test
    train2, test2 = _split_train_test(evals)
    assert [e.query for e in train] == [e.query for e in train2]
    assert [e.query for e in test] == [e.query for e in test2]


def test_split_collapse_yields_empty_test():
    """When a class has only one eval, the per-bucket split leaves no training
    rows; the guard rebuilds train from test, which legitimately empties test.
    optimize_skill_description keys off this to skip an un-validatable swap, so
    the collapse must be observable as an empty test split."""
    evals = [TriggerEval("only positive", True), TriggerEval("only negative", False)]
    train, test = _split_train_test(evals)
    assert train  # guard kept training data
    assert test == []  # no held-out set -> optimizer must not swap on this


def test_score_description_computes_accuracy():
    evals = _evals()
    # Perfect oracle: trigger exactly on the should_trigger queries.
    labels = [e.should_trigger for e in evals]

    def _mock(prompt: str, **_kwargs: Any) -> str:
        return json.dumps({"triggers": labels})

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        score = score_description("conducting-sam-assessments", "desc", evals)
    assert score.total == 6
    assert score.accuracy == 1.0
    assert score.missed == []
    assert score.wrongly_grabbed == []


def test_score_description_handles_length_mismatch_gracefully():
    def _mock(prompt: str, **_kwargs: Any) -> str:
        return json.dumps({"triggers": [True]})  # wrong length

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        score = score_description("x", "desc", _evals())
    assert score.total == 0  # treated as no-signal


_EVALS_PAYLOAD = {
    "should_trigger": ["run a SAM assessment", "analyze licensing", "find savings"],
    "should_not_trigger": ["reset password", "write marketing email", "deploy k8s"],
}
_GOOD_DESC_MARKER = "Use when the user asks to"


def _score_block_triggers(prompt: str, *, accurate: bool) -> str:
    """Build a score_triggers response from the numbered queries in the
    prompt. When accurate, trigger only on the SAM-related queries; when
    not, trigger on nothing (a too-narrow description)."""
    triggers: list[bool] = []
    for ln in prompt.splitlines():
        s = ln.strip()
        if s[:3].split(".")[0].isdigit() and "." in s:
            query = s.split(".", 1)[1].lower()
            is_sam = any(k in query for k in ("sam", "licensing", "savings"))
            triggers.append(is_sam if accurate else False)
    return json.dumps({"triggers": triggers})


def test_optimize_skill_description_improves_below_threshold():
    """A poor baseline gets a rewritten description that scores better and is
    applied to the skill."""
    skill = _skill("Does SAM stuff.")

    def _mock(prompt: str, **_kwargs: Any) -> str:
        if "Produce exactly" in prompt:
            return json.dumps(_EVALS_PAYLOAD)
        if "Rewrite the description" in prompt:
            return json.dumps(
                {
                    "description": (
                        "Conducts SAM assessments. Use when the user asks to run a "
                        "SAM assessment, analyze licensing, or find savings."
                    )
                }
            )
        # score_triggers: accurate only when scoring the improved description.
        return _score_block_triggers(prompt, accurate=_GOOD_DESC_MARKER in prompt)

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        result = optimize_skill_description(skill, "Test Co context", threshold=0.8)

    assert result.optimized is True
    assert result.final_accuracy > result.baseline_accuracy
    assert _GOOD_DESC_MARKER in skill.description


def test_optimize_skips_single_class_eval_set():
    """Regression: an all-positive (single-class) eval set scores degenerately,
    so optimization must be skipped rather than pushed toward an over-broad
    description with no false-positive penalty."""
    skill = _skill("Does SAM stuff.")

    def _mock(prompt: str, **_kwargs: Any) -> str:
        if "Produce exactly" in prompt:
            # Only should_trigger queries, no should_not_trigger.
            return json.dumps(
                {
                    "should_trigger": ["a query", "b query", "c query", "d query"],
                    "should_not_trigger": [],
                }
            )
        raise AssertionError("must not score/optimize a single-class eval set")

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        result = optimize_skill_description(skill, "Test Co context", threshold=0.8)
    assert result.optimized is False


def test_optimize_skill_description_noop_when_already_good():
    skill = _skill(
        "Conducts SAM assessments. Use when the user asks to run a SAM "
        "assessment, analyze licensing, or find savings."
    )
    original = skill.description

    def _mock(prompt: str, **_kwargs: Any) -> str:
        if "Produce exactly" in prompt:
            return json.dumps(_EVALS_PAYLOAD)
        if "Rewrite the description" in prompt:
            raise AssertionError("should not optimize an already-good description")
        return _score_block_triggers(prompt, accurate=True)

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        result = optimize_skill_description(skill, "Test Co context", threshold=0.8)

    assert result.optimized is False
    assert skill.description == original
