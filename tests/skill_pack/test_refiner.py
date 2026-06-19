"""Unit tests for the refinement loop.

LLM calls are mocked at the grok_llm seam so these run offline.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from primr.skill_pack.config import SkillPackConfig
from primr.skill_pack.refiner import _actionable_findings, auto_resolve_overlaps, refine_role
from primr.skill_pack.schema import Role, RoleEvidence, RoleProvenance, Skill, SkillPack

# A body comfortably over the 300-word floor with all required quality markers.
_GOOD_BODY = (
    "## What This Skill Does\n\n"
    + ("Handles a concrete company-specific task using the named stack. " * 24)
    + "\n\n## Workflow\n\n"
    + "Progress:\n"
    + "- [ ] Intake: confirm the source artifact, account context, and decision owner.\n"
    + "- [ ] Evidence: collect the named systems, constraints, and citations.\n"
    + "- [ ] Draft: produce the requested artifact.\n"
    + "- [ ] Validate: check the result against the guardrail.\n\n"
    + "1. First ask for missing customer scope, time window, source artifact, "
    + "and approval owner.\n"
    + "\n".join(f"{i}. Step {i} that names a specific system." for i in range(2, 8))
    + "\n\nScope guardrail: This skill prepares the analysis; it does not approve "
    + "customer-facing commitments or contractual changes.\n"
    + "Human checkpoint: Pause before sending recommendations to a customer, "
    + "changing pricing assumptions, or making compliance claims."
    + "\n\n## Output Format\n\n"
    + "| Field | Value |\n|---|---|\n| Source | named system |\n| Action | ranked next step |\n\n"
    + "Example input: Review the latest account data and produce a savings plan.\n"
    + "Example output: A ranked table of findings, evidence, owner, risk, and next action.\n\n"
    + ("A structured report with a table of results and ranked actions. " * 12)
)

# A body under the 300-word floor (thin stub) but structurally valid.
_THIN_BODY = (
    "## What This Skill Does\n\nDoes a thing for the company.\n\n"
    "## Workflow\n\n1. Do step one.\n2. Do step two.\n\n"
    "## Output Format\n\nA short list."
)


def _skill(name: str, body: str) -> Skill:
    return Skill(
        name=name,
        display_name=name.replace("-", " ").title(),
        description=(
            "Conducts a concrete task. Use when the user asks to perform it, "
            "review it, or report on it."
        ),
        body=body,
    )


def _role(*skills: Skill) -> Role:
    return Role(
        name="software-asset-manager",
        display_name="Software Asset Manager",
        confidence="Inferred",
        summary="Test role.",
        evidence=RoleEvidence(
            sources=[],
            dns_signals=[],
            posting_count=0,
            archetype=None,
            provenance=RoleProvenance.RESEARCH,
            citations=["test"],
        ),
        skills=list(skills),
    )


def test_actionable_findings_includes_too_short_body():
    """A thin body (under the floor) is an actionable finding even with no
    HARD issues."""
    skill = _skill("conducting-sam-assessments", _THIN_BODY)
    actionable = _actionable_findings(skill, "software-asset-manager")
    codes = {f.code for f in actionable}
    assert "BODY-LEN" in codes


def test_actionable_findings_skips_healthy_skill():
    """A well-formed skill over the floor produces no actionable findings."""
    skill = _skill("conducting-sam-assessments", _GOOD_BODY)
    assert _actionable_findings(skill, "software-asset-manager") == []


def test_refine_role_expands_thin_body():
    """refine_role sends a thin-body skill back through the LLM and the
    expanded body clears the actionable finding."""
    role = _role(_skill("conducting-sam-assessments", _THIN_BODY))

    def _mock(prompt: str, **_kwargs: Any) -> str:
        # The refiner asks for a fixed skill; return one with a full body.
        return json.dumps(
            {
                "name": "conducting-sam-assessments",
                "display_name": "Conducting SAM assessments",
                "description": (
                    "Conducts SAM assessments. Use when the user asks to "
                    "perform an assessment, analyze subscriptions, or report "
                    "savings."
                ),
                "body": _GOOD_BODY,
            }
        )

    config = SkillPackConfig(max_refine_iterations=2)
    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        iters = refine_role(role, config, company_context="Test Co context")

    # The skill was refined and now clears the actionable check.
    assert iters.get("conducting-sam-assessments") == 1
    assert _actionable_findings(role.skills[0], "software-asset-manager") == []


def test_refine_role_noop_on_healthy_role():
    """No LLM call when every skill is already clean."""
    role = _role(_skill("conducting-sam-assessments", _GOOD_BODY))
    config = SkillPackConfig(max_refine_iterations=2)
    with patch("primr.ai.grok_client.grok_llm", side_effect=AssertionError("should not call LLM")):
        iters = refine_role(role, config, company_context="Test Co context")
    assert iters == {}


# ---------------------------------------------------------------------------
# Auto-resolve overlaps
# ---------------------------------------------------------------------------


def _pack_with_two_skills() -> SkillPack:
    role = _role(
        _skill("producing-cost-savings-reports", _GOOD_BODY),
        _skill("reporting-managed-services-margins", _GOOD_BODY),
    )
    return SkillPack(
        company_name="Test Co",
        company_url=None,
        generated_at="2026-01-01T00:00:00+00:00",
        roles=[role],
    )


def test_auto_resolve_rescopes_second_skill_and_pops_entry():
    pack = _pack_with_two_skills()
    coherence = {
        "semantic_overlaps": [
            {
                "skill_a": "software-asset-manager/producing-cost-savings-reports",
                "skill_b": "software-asset-manager/reporting-managed-services-margins",
                "overlap_summary": "Both produce margin/savings reports.",
            }
        ]
    }

    narrowed_body = _GOOD_BODY.replace("Handles", "Narrowly handles")

    def _mock(prompt: str, **_kwargs: Any) -> str:
        return json.dumps(
            {
                "name": "reporting-managed-services-margins",
                "display_name": "Reporting managed-services margins",
                "description": (
                    "Reports managed-services contract margins only. Use when the "
                    "user asks to review contract margins, report SLA penalties, or "
                    "reconcile delivery costs."
                ),
                "body": narrowed_body,
            }
        )

    with patch("primr.ai.grok_client.grok_llm", side_effect=_mock):
        resolved = auto_resolve_overlaps(pack, coherence, "Test Co context")

    assert len(resolved) == 1
    # skill_b was re-scoped; skill_a untouched. (_apply_refined strips the body.)
    assert pack.roles[0].skills[1].body == narrowed_body.strip()
    assert pack.roles[0].skills[0].body == _GOOD_BODY
    # The resolved entry was popped so it won't be reported as unresolved.
    assert coherence["semantic_overlaps"] == []


def test_auto_resolve_reverts_when_refinement_breaks_skill():
    """If the re-scope introduces a HARD finding (e.g. drops a required H2
    section), the change is reverted and the entry is NOT popped."""
    pack = _pack_with_two_skills()
    coherence = {
        "semantic_overlaps": [
            {
                "skill_a": "software-asset-manager/producing-cost-savings-reports",
                "skill_b": "software-asset-manager/reporting-managed-services-margins",
                "overlap_summary": "Both produce margin/savings reports.",
            }
        ]
    }

    def _bad_mock(prompt: str, **_kwargs: Any) -> str:
        # Body missing required H2 sections -> HARD BODY-SEC finding.
        return json.dumps(
            {
                "name": "reporting-managed-services-margins",
                "display_name": "Reporting managed-services margins",
                "description": "Reports margins. Use when the user asks to do X, Y, or Z.",
                "body": "Just a paragraph with no required headings at all.",
            }
        )

    with patch("primr.ai.grok_client.grok_llm", side_effect=_bad_mock):
        resolved = auto_resolve_overlaps(pack, coherence, "Test Co context")

    assert resolved == []
    # Original body preserved; entry remains for the report.
    assert pack.roles[0].skills[1].body == _GOOD_BODY
    assert len(coherence["semantic_overlaps"]) == 1
