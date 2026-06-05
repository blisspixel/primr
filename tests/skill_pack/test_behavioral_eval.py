"""Unit tests for Tier-4 behavioral evaluation.

LLM calls are mocked at the grok_llm seam. The mock dispatches on which
prompt is rendered (generate cases / run task / grade output).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from primr.skill_pack.behavioral_eval import (
    benchmark_skill,
    generate_skill_evals,
    grade_output,
    run_pack_behavioral_evals,
)
from primr.skill_pack.schema import Role, RoleEvidence, RoleProvenance, Skill, SkillPack

_BODY = (
    "## What This Skill Does\n\nConduct a SAM assessment via the the SAM platform.\n\n"
    "## Workflow\n\n1. Pull usage.\n2. Reconcile in Salesforce.\n\n"
    "## Output Format\n\nA license-utilization table ranked by ROI."
)


def _skill() -> Skill:
    return Skill(
        name="conducting-sam-assessments",
        display_name="Conducting SAM assessments",
        description="Conducts SAM assessments. Use when the user asks to assess licensing.",
        body=_BODY,
    )


def _pack() -> SkillPack:
    role = Role(
        name="software-asset-manager",
        display_name="Software Asset Manager",
        confidence="Inferred",
        summary="Test role.",
        evidence=RoleEvidence(provenance=RoleProvenance.RESEARCH, citations=["x"]),
        skills=[_skill()],
    )
    return SkillPack(
        company_name="Test Co",
        company_url=None,
        generated_at="2026-01-01T00:00:00+00:00",
        roles=[role],
    )


_CASES_PAYLOAD = {
    "evals": [
        {
            "prompt": "Assess the client's M365 licensing for waste.",
            "expected_output": "A ranked table of license waste with the SAM platform as source.",
            "assertions": [
                "names the the SAM platform as the data source",
                "includes a license-utilization table",
                "ranks recommendations by ROI",
            ],
        }
    ]
}


def test_generate_skill_evals_parses_cases():
    def _mock(prompt: str, **_kwargs: Any) -> str:
        return json.dumps(_CASES_PAYLOAD)

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        cases = generate_skill_evals(_skill(), "Test Co context", n_cases=1)
    assert len(cases) == 1
    assert len(cases[0].assertions) == 3


def test_grade_output_counts_passed_assertions():
    def _mock(prompt: str, **_kwargs: Any) -> str:
        return json.dumps({"results": [True, False, True]})

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        passed = grade_output("task", "output", ["a", "b", "c"])
    assert passed == 2


def test_benchmark_skill_with_beats_baseline():
    """With-skill output is graded higher than baseline; delta is positive."""

    def _mock(prompt: str, **kwargs: Any) -> str:
        system = str(kwargs.get("system_prompt", ""))
        if "Produce" in prompt and "eval cases" in prompt:
            return json.dumps(_CASES_PAYLOAD)
        if "ASSERTIONS" in prompt and "OUTPUT TO GRADE" in prompt:
            # Grade by the distinctive OUTPUT text (the assertions block also
            # mentions the the SAM platform, so key on the output marker instead): the
            # baseline output is the "generic answer", which fails everything.
            if "generic answer" in prompt:
                return json.dumps({"results": [False, False, False]})
            return json.dumps({"results": [True, True, True]})
        # A run_task call. The with-skill arm carries the body (which mentions
        # the the SAM platform) in the system prompt; baseline does not.
        if "the SAM platform" in system:
            return "Here is a ranked table sourced from the the SAM platform."
        return "Here is a generic answer."

    skill = _skill()
    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        bench = benchmark_skill(skill, "Test Co context", n_cases=1)

    assert bench.n_cases == 1
    assert bench.n_assertions == 3
    assert bench.with_skill_pass_rate == 1.0
    assert bench.baseline_pass_rate == 0.0
    assert bench.delta > 0


def test_run_pack_behavioral_evals_attaches_evals_json():
    pack = _pack()

    def _mock(prompt: str, **_kwargs: Any) -> str:
        if "Produce" in prompt and "eval cases" in prompt:
            return json.dumps(_CASES_PAYLOAD)
        if "ASSERTIONS" in prompt and "OUTPUT TO GRADE" in prompt:
            return json.dumps({"results": [True, True, True]})
        return "some output"

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        benchmarks = run_pack_behavioral_evals(pack, "Test Co context", n_cases=1)

    assert len(benchmarks) == 1
    # evals/evals.json was attached as a bundled file on the skill.
    bundled = pack.roles[0].skills[0].bundled_files
    eval_files = [b for b in bundled if b.relpath == "evals/evals.json"]
    assert len(eval_files) == 1
    data = json.loads(eval_files[0].content)
    assert data["skill_name"] == "conducting-sam-assessments"
    assert len(data["evals"]) == 1
    assert data["evals"][0]["id"] == 1
