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

Expensive (~3 LLM calls per case, times N cases per skill), so it is OFF by
default and gated behind ``SkillPackConfig.with_evals`` / ``--with-evals``.
Best-effort: any failure on a skill is logged and skipped, never fatal.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from primr.skill_pack.prompts_loader import extract_json, load_skill_pack_prompt
from primr.skill_pack.schema import BundledFile, Skill, SkillPack

logger = logging.getLogger(__name__)

DEFAULT_EVAL_CASES = 3
_MAX_OUTPUT_TOKENS = 1_500


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


def generate_skill_evals(
    skill: Skill,
    company_context: str,
    *,
    n_cases: int = DEFAULT_EVAL_CASES,
    reasoning_session: Any | None = None,
) -> list[SkillEvalCase]:
    """Generate behavioral eval cases (task + assertions) for one skill."""
    prompt = load_skill_pack_prompt("gen_skill_evals")
    body_indented = "\n".join("    " + ln for ln in skill.body.splitlines())
    user_msg = prompt.render(
        skill_name=skill.name,
        skill_description=skill.description,
        skill_body_indented=body_indented,
        company_context=company_context,
        n_cases=n_cases,
    )
    raw = _llm(prompt.system_prompt, user_msg, reasoning_session)
    parsed = extract_json(raw)
    cases: list[SkillEvalCase] = []
    for entry in parsed.get("evals") or []:
        if not isinstance(entry, dict):
            continue
        task = str(entry.get("prompt") or "").strip()
        assertions = [str(a).strip() for a in (entry.get("assertions") or []) if str(a).strip()]
        if task and assertions:
            cases.append(
                SkillEvalCase(
                    prompt=task,
                    expected_output=str(entry.get("expected_output") or "").strip(),
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
    return _llm(system, task, reasoning_session, temperature=0.2, max_tokens=_MAX_OUTPUT_TOKENS)


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
    user_msg = prompt.render(task=task, output=output, assertions_block=assertions_block)
    raw = _llm(prompt.system_prompt, user_msg, reasoning_session, temperature=0.0)
    try:
        parsed = extract_json(raw)
    except ValueError:
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
    bench = SkillBenchmark(skill_name=skill.name)
    cases = generate_skill_evals(
        skill, company_context, n_cases=n_cases, reasoning_session=reasoning_session
    )
    bench.cases = cases
    for case in cases:
        with_out = _run_task(case.prompt, skill.body, reasoning_session=reasoning_session)
        base_out = _run_task(case.prompt, None, reasoning_session=reasoning_session)
        with_passed = grade_output(
            case.prompt, with_out, case.assertions, reasoning_session=reasoning_session
        )
        base_passed = grade_output(
            case.prompt, base_out, case.assertions, reasoning_session=reasoning_session
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
                    "assertions": c.assertions,
                }
                for i, c in enumerate(cases)
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def _attach_evals_file(skill: Skill, cases: list[SkillEvalCase]) -> None:
    """Attach evals/evals.json to the skill as a bundled file (replacing any
    prior one) so the packager ships it alongside SKILL.md."""
    if not cases:
        return
    skill.bundled_files = [bf for bf in skill.bundled_files if bf.relpath != "evals/evals.json"]
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
            try:
                bench = benchmark_skill(
                    skill,
                    company_context,
                    n_cases=n_cases,
                    reasoning_session=reasoning_session,
                )
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
]
