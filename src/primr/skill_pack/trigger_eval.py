"""Tier 2: per-skill trigger evaluation + description optimization.

The rigorous replacement for the ``DESC-PUSHY`` heuristic. Instead of
counting keywords, this MEASURES how well a skill's description triggers:

  1. Generate should-trigger and should-not-trigger queries for the skill.
  2. Run a discovery simulator (blind to the labels) to see which queries
     the current description would fire on, and score accuracy.
  3. If accuracy is below threshold, propose an improved description and
     re-score. Keep the better description, decided on a held-out TEST
     split so we don't overfit to the queries used for improvement.

All LLM calls route through ``grok_llm`` (or the shared reasoning session).
The whole pass is opt-in (``SkillPackConfig.optimize_triggers``) because it
adds LLM calls per skill.

This mirrors Anthropic's published description-optimization loop, scaled
down to a bounded, single-improvement pass suitable for whole-pack runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import Skill, SkillPack

logger = logging.getLogger(__name__)

DEFAULT_TRIGGER_THRESHOLD = 0.8
DEFAULT_N_EACH = 6
# Fraction of generated evals held out for the keep-or-revert decision.
_TEST_FRACTION = 0.4
_MIN_EVALS_TO_OPTIMIZE = 4


@dataclass
class TriggerEval:
    query: str
    should_trigger: bool


@dataclass
class TriggerScore:
    total: int = 0
    correct: int = 0
    true_pos: int = 0
    false_pos: int = 0
    true_neg: int = 0
    false_neg: int = 0
    missed: list[str] = field(default_factory=list)  # should-trigger that didn't
    wrongly_grabbed: list[str] = field(default_factory=list)  # should-not that did

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class SkillTriggerResult:
    skill_name: str
    baseline_accuracy: float
    final_accuracy: float
    optimized: bool
    n_evals: int


def _llm(
    system_prompt: str,
    user_prompt: str,
    reasoning_session: Any | None,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4_000,
) -> str:
    if reasoning_session is not None and hasattr(reasoning_session, "send"):
        return reasoning_session.send(  # type: ignore[no-any-return]
            f"{system_prompt}\n\n{user_prompt}",
            temperature=temperature,
            max_tokens=max_tokens,
        )
    from primr.ai.grok_client import grok_llm

    return grok_llm(
        user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def generate_trigger_evals(
    skill: Skill,
    company_context: str,
    *,
    n_each: int = DEFAULT_N_EACH,
    reasoning_session: Any | None = None,
) -> list[TriggerEval]:
    """Generate should/should-not-trigger queries for one skill."""
    prompt = load_skill_pack_prompt("gen_trigger_evals")
    user_msg = prompt.render(
        skill_name=skill.name,
        skill_description=skill.description,
        company_context=company_context,
        n_each=n_each,
    )
    raw = _llm(prompt.system_prompt, user_msg, reasoning_session)
    parsed = extract_json(raw)
    evals: list[TriggerEval] = []
    for q in parsed.get("should_trigger") or []:
        text = str(q).strip()
        if text:
            evals.append(TriggerEval(query=text, should_trigger=True))
    for q in parsed.get("should_not_trigger") or []:
        text = str(q).strip()
        if text:
            evals.append(TriggerEval(query=text, should_trigger=False))
    return evals


def score_description(
    skill_name: str,
    description: str,
    evals: list[TriggerEval],
    *,
    reasoning_session: Any | None = None,
) -> TriggerScore:
    """Run the discovery simulator over `evals` for a candidate description."""
    score = TriggerScore()
    if not evals:
        return score

    queries_block = "\n".join(f"{i + 1}. {e.query}" for i, e in enumerate(evals))
    prompt = load_skill_pack_prompt("score_triggers")
    user_msg = prompt.render(
        skill_name=skill_name,
        skill_description=description,
        queries_block=queries_block,
    )
    raw = _llm(prompt.system_prompt, user_msg, reasoning_session, temperature=0.0)
    parsed = extract_json(raw)
    triggers = parsed.get("triggers") or []
    if not isinstance(triggers, list) or len(triggers) != len(evals):
        # Degrade gracefully: a malformed score is treated as "no signal"
        # (accuracy 0 over 0) so the caller keeps the original description.
        logger.warning(
            "score_triggers returned %d verdicts for %d queries (skill %s); skipping",
            len(triggers) if isinstance(triggers, list) else -1,
            len(evals),
            skill_name,
        )
        return TriggerScore()

    for ev, fired_raw in zip(evals, triggers, strict=True):
        fired = bool(fired_raw)
        score.total += 1
        if ev.should_trigger and fired:
            score.true_pos += 1
            score.correct += 1
        elif ev.should_trigger and not fired:
            score.false_neg += 1
            score.missed.append(ev.query)
        elif not ev.should_trigger and fired:
            score.false_pos += 1
            score.wrongly_grabbed.append(ev.query)
        else:
            score.true_neg += 1
            score.correct += 1
    return score


def _propose_improved_description(
    skill: Skill,
    train_score: TriggerScore,
    *,
    reasoning_session: Any | None = None,
) -> str | None:
    """Ask the optimizer for a better description given the wrong answers."""
    missed_block = "\n".join(f"- {q}" for q in train_score.missed) or "(none)"
    wrong_block = "\n".join(f"- {q}" for q in train_score.wrongly_grabbed) or "(none)"
    prompt = load_skill_pack_prompt("optimize_description")
    user_msg = prompt.render(
        skill_name=skill.name,
        skill_description=skill.description,
        missed_block=missed_block,
        wrong_block=wrong_block,
    )
    raw = _llm(prompt.system_prompt, user_msg, reasoning_session)
    try:
        parsed = extract_json(raw)
    except ValueError as exc:
        logger.warning("optimize_description unparseable for %s: %s", skill.name, exc)
        return None
    improved = str(parsed.get("description") or "").strip()
    if not improved or not (1 <= len(improved) <= 1024):
        return None
    return improved


def _split_train_test(evals: list[TriggerEval]) -> tuple[list[TriggerEval], list[TriggerEval]]:
    """Deterministic, label-stratified train/test split (no RNG — RNG is
    unavailable in some run contexts and would hurt reproducibility)."""
    pos = [e for e in evals if e.should_trigger]
    neg = [e for e in evals if not e.should_trigger]
    test: list[TriggerEval] = []
    train: list[TriggerEval] = []
    for bucket in (pos, neg):
        n_test = max(1, round(len(bucket) * _TEST_FRACTION)) if bucket else 0
        test.extend(bucket[:n_test])
        train.extend(bucket[n_test:])
    # Guard: never let train be empty when there is anything to learn from.
    if not train and test:
        train, test = test, []
    return train, test


def optimize_skill_description(
    skill: Skill,
    company_context: str,
    *,
    threshold: float = DEFAULT_TRIGGER_THRESHOLD,
    reasoning_session: Any | None = None,
) -> SkillTriggerResult:
    """Measure and (if below threshold) improve one skill's description.

    Mutates ``skill.description`` in place only when the improved
    description scores strictly better on the held-out TEST split.
    """
    evals = generate_trigger_evals(skill, company_context, reasoning_session=reasoning_session)
    if len(evals) < _MIN_EVALS_TO_OPTIMIZE:
        logger.info("Too few trigger evals for %s (%d); skipping", skill.name, len(evals))
        return SkillTriggerResult(skill.name, 0.0, 0.0, optimized=False, n_evals=len(evals))

    train, test = _split_train_test(evals)
    score_set = test or train
    baseline = score_description(
        skill.name, skill.description, score_set, reasoning_session=reasoning_session
    )

    if baseline.accuracy >= threshold:
        return SkillTriggerResult(
            skill.name, baseline.accuracy, baseline.accuracy, optimized=False, n_evals=len(evals)
        )

    # Improve against the TRAIN failures, judge on the held-out set.
    train_score = score_description(
        skill.name, skill.description, train, reasoning_session=reasoning_session
    )
    improved = _propose_improved_description(
        skill, train_score, reasoning_session=reasoning_session
    )
    if improved is None:
        return SkillTriggerResult(
            skill.name, baseline.accuracy, baseline.accuracy, optimized=False, n_evals=len(evals)
        )

    new_score = score_description(
        skill.name, improved, score_set, reasoning_session=reasoning_session
    )
    if new_score.accuracy > baseline.accuracy:
        skill.description = improved
        logger.info(
            "Optimized trigger description for %s: %.0f%% -> %.0f%%",
            skill.name,
            baseline.accuracy * 100,
            new_score.accuracy * 100,
        )
        return SkillTriggerResult(
            skill.name, baseline.accuracy, new_score.accuracy, optimized=True, n_evals=len(evals)
        )

    return SkillTriggerResult(
        skill.name, baseline.accuracy, baseline.accuracy, optimized=False, n_evals=len(evals)
    )


def optimize_pack_triggers(
    pack: SkillPack,
    company_context: str,
    *,
    threshold: float = DEFAULT_TRIGGER_THRESHOLD,
    reasoning_session: Any | None = None,
) -> list[SkillTriggerResult]:
    """Run trigger optimization across every skill in the pack. Best-effort:
    a failure on one skill is logged and skipped, never fatal."""
    results: list[SkillTriggerResult] = []
    for role in pack.roles:
        for skill in role.skills:
            try:
                results.append(
                    optimize_skill_description(
                        skill,
                        company_context,
                        threshold=threshold,
                        reasoning_session=reasoning_session,
                    )
                )
            except Exception as exc:
                logger.warning("Trigger optimization failed for %s: %s", skill.name, exc)
    optimized = sum(1 for r in results if r.optimized)
    logger.info("Trigger optimization: %d/%d skills improved", optimized, len(results))
    return results


__all__ = [
    "SkillTriggerResult",
    "TriggerEval",
    "TriggerScore",
    "generate_trigger_evals",
    "optimize_pack_triggers",
    "optimize_skill_description",
    "score_description",
]
