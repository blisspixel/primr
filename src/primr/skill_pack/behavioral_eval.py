"""Tier 4: behavioral evaluation — does the skill actually help?

Structural validation proves a skill is well-formed; trigger optimization
proves it fires for the right requests. Neither proves the skill improves
the agent's OUTPUT. This pass measures that directly, the way Anthropic's
skill-creator does:

  1. Generate realistic task cases for the skill, each with objective
     assertions.
  2. Run each task TWICE — once with the SKILL.md body as guidance
     (with-skill) and once without (baseline).
  3. Grade both outputs against the assertions (blind to which arm).
  4. Report with-skill vs baseline pass rates and the delta.

Also emits an ``evals/evals.json`` resource per skill (Anthropic's published
structure) so users can re-grade against their own assertions later.

Expensive (one generation plus four LLM calls per case), so it is OFF by
default and gated behind ``SkillPackConfig.with_evals`` / ``--with-evals``.
Best-effort: any failure on a skill is logged and skipped, never fatal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from primr.skill_pack.config import (
    DEFAULT_EVAL_CASES,
    EVAL_GENERATION_OUTPUT_TOKEN_CAP,
    EVAL_GRADER_OUTPUT_TOKEN_CAP,
    EVAL_MODEL_RETRIES,
    EVAL_TASK_OUTPUT_TOKEN_CAP,
    MAX_EVAL_CASES,
)
from primr.skill_pack.eval_validation import scan_eval_case_fields, scan_eval_json
from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import BundledFile, Skill, SkillPack
from primr.utils.content_sanitizer import fence_untrusted

logger = logging.getLogger(__name__)


@dataclass
class SkillEvalCase:
    prompt: str
    expected_output: str
    assertions: list[str]


@dataclass
class SkillBenchmark:
    skill_name: str
    n_cases: int = 0
    n_assertions: int = 0
    with_skill_passed: int = 0
    baseline_passed: int = 0
    cases: list[SkillEvalCase] = field(default_factory=list)

    @property
    def with_skill_pass_rate(self) -> float:
        return self.with_skill_passed / self.n_assertions if self.n_assertions else 0.0

    @property
    def baseline_pass_rate(self) -> float:
        return self.baseline_passed / self.n_assertions if self.n_assertions else 0.0

    @property
    def delta(self) -> float:
        return self.with_skill_pass_rate - self.baseline_pass_rate


def _llm(
    system_prompt: str,
    user_prompt: str,
    reasoning_session: Any | None,
    *,
    temperature: float = 0.3,
    max_tokens: int = EVAL_GENERATION_OUTPUT_TOKEN_CAP,
    use_history: bool = True,
) -> str:
    if reasoning_session is not None and hasattr(reasoning_session, "send"):
        if use_history:
            return reasoning_session.send(  # type: ignore[no-any-return]
                f"{system_prompt}\n\n{user_prompt}",
                temperature=temperature,
                max_tokens=max_tokens,
                retries=EVAL_MODEL_RETRIES,
            )
        send_stateless = getattr(reasoning_session, "send_stateless", None)
        if not callable(send_stateless):
            raise TypeError("reasoning_session must provide send_stateless for unbiased evals")
        return send_stateless(  # type: ignore[no-any-return]
            user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=EVAL_MODEL_RETRIES,
        )
    from primr.ai.grok_client import grok_llm

    return grok_llm(
        user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=EVAL_MODEL_RETRIES,
    )


def generate_skill_evals(
    skill: Skill,
    company_context: str,
    *,
    n_cases: int = DEFAULT_EVAL_CASES,
    reasoning_session: Any | None = None,
) -> list[SkillEvalCase]:
    """Generate behavioral eval cases (task + assertions) for one skill."""
    if type(n_cases) is not int:
        raise ValueError("n_cases must be an integer")
    requested_cases = min(max(0, n_cases), MAX_EVAL_CASES)
    if requested_cases == 0:
        return []
    prompt = load_skill_pack_prompt("gen_skill_evals")
    body_indented = "\n".join("    " + ln for ln in skill.body.splitlines())
    user_msg = prompt.render(
        skill_name=skill.name,
        skill_description=skill.description,
        skill_body_indented=body_indented,
        company_context=company_context,
        n_cases=requested_cases,
    )
    raw = _llm(prompt.system_prompt, user_msg, reasoning_session)
    parsed = extract_json(raw)
    cases: list[SkillEvalCase] = []
    if not isinstance(parsed, dict):
        return cases
    entries = parsed.get("evals") or []
    if not isinstance(entries, list):
        return cases
    for entry in entries[:requested_cases]:
        if not isinstance(entry, dict):
            continue
        raw_task = entry.get("prompt")
        raw_expected_output = entry.get("expected_output")
        raw_assertions = entry.get("expectations", entry.get("assertions"))
        if not isinstance(raw_task, str) or not isinstance(raw_assertions, list):
            continue
        task = raw_task.strip()
        expected_output = (
            raw_expected_output.strip() if isinstance(raw_expected_output, str) else ""
        )
        assertions = [
            assertion.strip()
            for assertion in raw_assertions
            if isinstance(assertion, str) and assertion.strip()
        ]
        if task and assertions:
            if unsafe := scan_eval_case_fields(task, expected_output, assertions):
                logger.warning("Dropping unsafe generated behavioral eval case: %s", unsafe)
                continue
            cases.append(
                SkillEvalCase(
                    prompt=task,
                    expected_output=expected_output,
                    assertions=assertions,
                )
            )
    return cases


def _run_task(
    task: str,
    skill_body: str | None,
    *,
    reasoning_session: Any | None = None,
) -> str:
    """Run one task. When skill_body is given, it is supplied as guidance
    (the with-skill arm); otherwise the agent answers cold (baseline)."""
    if skill_body:
        system = (
            "You are an expert assistant. Use the following skill guidance to "
            "complete the user's task:\n\n" + skill_body
        )
    else:
        system = "You are an expert assistant. Complete the user's task."
    return _llm(
        system,
        task,
        reasoning_session,
        temperature=0.2,
        max_tokens=EVAL_TASK_OUTPUT_TOKEN_CAP,
        use_history=False,
    )


def grade_output(
    task: str,
    output: str,
    assertions: list[str],
    *,
    reasoning_session: Any | None = None,
) -> int:
    """Return how many assertions the output satisfies."""
    if not assertions:
        return 0
    prompt = load_skill_pack_prompt("grade_skill_output")
    assertions_block = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(assertions))
    user_msg = prompt.render(
        task=fence_untrusted("EVAL_TASK", task),
        output=fence_untrusted("EVAL_OUTPUT", output),
        assertions_block=fence_untrusted("EVAL_EXPECTATIONS", assertions_block),
    )
    raw = _llm(
        prompt.system_prompt,
        user_msg,
        reasoning_session,
        temperature=0.0,
        max_tokens=EVAL_GRADER_OUTPUT_TOKEN_CAP,
        use_history=False,
    )
    try:
        parsed = extract_json(raw)
    except ValueError:
        return 0
    if not isinstance(parsed, dict):
        return 0
    results = parsed.get("results") or []
    if not isinstance(results, list):
        return 0
    if len(results) != len(assertions):
        # Length mismatch corrupts the with/baseline delta asymmetrically.
        # Log and score only the verdicts we got (missing ones count as fail),
        # mirroring trigger_eval's defensive handling.
        logger.warning(
            "grade returned %d verdicts for %d assertions; scoring the overlap only",
            len(results),
            len(assertions),
        )
    return sum(1 for r in results[: len(assertions)] if _is_pass(r))


def _is_pass(verdict: Any) -> bool:
    """Strict truthiness for a grader verdict. A real JSON `true` passes;
    string verdicts like "false"/"no"/"0" must NOT pass (every non-empty
    string is truthy in Python, so a bare bool() would inflate pass counts)."""
    if isinstance(verdict, bool):
        return verdict
    if isinstance(verdict, (int, float)):
        return verdict == 1
    if isinstance(verdict, str):
        return verdict.strip().lower() in {"true", "yes", "pass", "passed", "1"}
    return False


def benchmark_skill(
    skill: Skill,
    company_context: str,
    *,
    n_cases: int = DEFAULT_EVAL_CASES,
    reasoning_session: Any | None = None,
) -> SkillBenchmark:
    """Run the with-skill vs baseline benchmark for one skill."""
    if reasoning_session is not None and (
        not callable(getattr(reasoning_session, "send", None))
        or not callable(getattr(reasoning_session, "send_stateless", None))
    ):
        raise TypeError("reasoning_session must provide send and send_stateless")
    bench = SkillBenchmark(skill_name=skill.name)
    cases = generate_skill_evals(
        skill, company_context, n_cases=n_cases, reasoning_session=reasoning_session
    )
    bench.cases = cases
    for case in cases:
        # Each arm and grader is stateless. Reusing the generation session would
        # contaminate the baseline with skill guidance and prior model output.
        with_out = _run_task(
            case.prompt,
            skill.body,
            reasoning_session=reasoning_session,
        )
        base_out = _run_task(
            case.prompt,
            None,
            reasoning_session=reasoning_session,
        )
        with_passed = grade_output(
            case.prompt,
            with_out,
            case.assertions,
            reasoning_session=reasoning_session,
        )
        base_passed = grade_output(
            case.prompt,
            base_out,
            case.assertions,
            reasoning_session=reasoning_session,
        )
        bench.n_cases += 1
        bench.n_assertions += len(case.assertions)
        bench.with_skill_passed += with_passed
        bench.baseline_passed += base_passed
    return bench


def _evals_json(skill_name: str, cases: list[SkillEvalCase]) -> str:
    """Serialize cases into Anthropic's evals/evals.json structure."""
    return json.dumps(
        {
            "skill_name": skill_name,
            "evals": [
                {
                    "id": i + 1,
                    "prompt": c.prompt,
                    "expected_output": c.expected_output,
                    "expectations": c.assertions,
                }
                for i, c in enumerate(cases)
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def _attach_evals_file(skill: Skill, cases: list[SkillEvalCase]) -> None:
    """Replace the skill's eval resource with the current admitted cases."""
    skill.bundled_files = [bf for bf in skill.bundled_files if bf.relpath != "evals/evals.json"]
    if not cases:
        return
    skill.bundled_files.append(
        BundledFile(relpath="evals/evals.json", content=_evals_json(skill.name, cases))
    )


def run_pack_behavioral_evals(
    pack: SkillPack,
    company_context: str,
    *,
    n_cases: int = DEFAULT_EVAL_CASES,
    reasoning_session: Any | None = None,
) -> list[SkillBenchmark]:
    """Benchmark every skill in the pack and attach evals/evals.json to each.
    Best-effort: a failure on one skill is logged and skipped."""
    benchmarks: list[SkillBenchmark] = []
    for role in pack.roles:
        for skill in role.skills:
            # A requested rerun owns the resource. Remove any prior result
            # before generation so rejected cases and provider failures cannot
            # silently ship stale behavioral evidence.
            _attach_evals_file(skill, [])
            try:
                bench = benchmark_skill(
                    skill,
                    company_context,
                    n_cases=n_cases,
                    reasoning_session=reasoning_session,
                )
                if bench.n_cases == 0:
                    logger.warning(
                        "Behavioral eval skipped %s because no valid cases remained",
                        skill.name,
                    )
                    continue
                _attach_evals_file(skill, bench.cases)
                benchmarks.append(bench)
            except Exception as exc:  # best-effort, never fatal
                logger.warning("Behavioral eval failed for %s: %s", skill.name, exc)
    helped = sum(1 for b in benchmarks if b.delta > 0)
    logger.info(
        "Behavioral eval: %d/%d skills improved output vs baseline", helped, len(benchmarks)
    )
    return benchmarks


__all__ = [
    "DEFAULT_EVAL_CASES",
    "SkillBenchmark",
    "SkillEvalCase",
    "benchmark_skill",
    "generate_skill_evals",
    "grade_output",
    "run_pack_behavioral_evals",
    "scan_eval_case_fields",
    "scan_eval_json",
]
