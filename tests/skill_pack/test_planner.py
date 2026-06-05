"""Unit tests for the planner: observed/plausible split, merge, cap.

LLM calls are mocked at the grok_llm seam so these run offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from primr.skill_pack.discovery import EmptyHiringEvidenceError
from primr.skill_pack.planner import _merge_and_cap, load_plan, plan_roles
from primr.skill_pack.schema import Role, RoleEvidence, RoleProvenance


def _write_evidence(
    working_dir: Path,
    *,
    recon: str | None = None,
    hiring: str | None = None,
    research: str | None = None,
) -> None:
    working_dir.mkdir(parents=True, exist_ok=True)
    if recon is not None:
        (working_dir / "_recon_context.txt").write_text(recon, encoding="utf-8")
    if hiring is not None:
        hiring_dir = working_dir / "_hiring"
        hiring_dir.mkdir(parents=True, exist_ok=True)
        (hiring_dir / "hiring_signals.md").write_text(hiring, encoding="utf-8")
    if research is not None:
        (working_dir / "insights.txt").write_text(research, encoding="utf-8")


def _make_role(
    name: str, *, archetype: str | None = None, provenance: RoleProvenance = RoleProvenance.POSTING
) -> Role:
    return Role(
        name=name,
        display_name=name.replace("-", " ").title(),
        confidence="Confirmed" if provenance == RoleProvenance.POSTING else "Inferred",
        summary=f"Summary for {name}",
        evidence=RoleEvidence(
            sources=[],
            dns_signals=[],
            posting_count=1 if provenance == RoleProvenance.POSTING else 0,
            archetype=archetype,
            provenance=provenance,
            citations=["test citation"],
        ),
    )


# =============================================================================
# Merge and cap
# =============================================================================


class TestMergeAndCap:
    def test_observed_wins_when_archetypes_collide(self):
        observed = [_make_role("salesforce-admin", archetype="salesforce-admin")]
        plausible = [
            _make_role(
                "sfdc-administrator",
                archetype="salesforce-admin",
                provenance=RoleProvenance.RESEARCH,
            )
        ]
        final, gap = _merge_and_cap(observed, plausible, cap=5)
        assert len(final) == 1
        assert final[0].name == "salesforce-admin"
        assert gap == []  # archetype-collided plausible is dropped silently

    def test_plausible_fills_remaining_slots(self):
        observed = [_make_role("data-engineer", archetype="data-engineer")]
        plausible = [
            _make_role(
                "marketing-manager",
                archetype="marketing-manager",
                provenance=RoleProvenance.INDUSTRY,
            ),
            _make_role(
                "customer-success", archetype="customer-success", provenance=RoleProvenance.RESEARCH
            ),
        ]
        final, gap = _merge_and_cap(observed, plausible, cap=3)
        assert [r.name for r in final] == ["data-engineer", "marketing-manager", "customer-success"]
        assert gap == []

    def test_cap_pushes_overflow_to_gap(self):
        observed = [_make_role(f"obs-{i}", archetype=f"arch-{i}") for i in range(2)]
        plausible = [
            _make_role(f"plaus-{i}", archetype=f"arch-{10 + i}", provenance=RoleProvenance.INDUSTRY)
            for i in range(4)
        ]
        final, gap = _merge_and_cap(observed, plausible, cap=4)
        assert len(final) == 4
        assert len(gap) == 2
        # Observed kept; first 2 plausible joined; last 2 plausible gap-flagged
        assert [r.name for r in final[:2]] == ["obs-0", "obs-1"]
        assert [r.name for r in gap] == ["plaus-2", "plaus-3"]

    def test_observed_beyond_cap_truncates(self):
        observed = [_make_role(f"obs-{i}", archetype=f"arch-{i}") for i in range(5)]
        final, gap = _merge_and_cap(observed, [], cap=3)
        assert len(final) == 3
        # The truncated observed entries are NOT moved to gap (gap is for
        # plausible overflow; trimming observed is a quiet cap behavior).
        # Reserve only fires when eligible plausible roles are waiting.
        assert gap == []

    def test_reserve_guarantees_org_roles_when_postings_all_technical(self):
        # The infra-heavy-reseller case: a company whose postings are ALL one
        # technical function. Without the reserve, 5 observed technical roles
        # would fill cap=5 and every plausible business role would be
        # gap-flagged. The reserve guarantees org-shape roles still land.
        observed = [
            _make_role(f"cloud-engineer-{i}", archetype=f"azure-cloud-engineer-{i}")
            for i in range(5)
        ]
        plausible = [
            _make_role(
                "account-executive",
                archetype="account-executive",
                provenance=RoleProvenance.INDUSTRY,
            ),
            _make_role(
                "marketing-manager",
                archetype="marketing-manager",
                provenance=RoleProvenance.INDUSTRY,
            ),
            _make_role(
                "hr-business-partner",
                archetype="hr-business-partner",
                provenance=RoleProvenance.INDUSTRY,
            ),
        ]
        final, gap = _merge_and_cap(observed, plausible, cap=5)
        assert len(final) == 5
        # At cap=5, reserve = int(5 * 0.4) = 2 → 3 observed kept + 2 plausible.
        kept_plausible = [r for r in final if r.evidence.provenance == RoleProvenance.INDUSTRY]
        kept_observed = [r for r in final if r.evidence.provenance == RoleProvenance.POSTING]
        assert len(kept_observed) == 3
        assert len(kept_plausible) == 2
        # Leading slots are still observed (postings stay primary).
        assert all(r.evidence.provenance == RoleProvenance.POSTING for r in final[:3])
        # The 2 bumped observed roles are surfaced in gap, not silently dropped.
        bumped_observed = [r for r in gap if r.evidence.provenance == RoleProvenance.POSTING]
        assert len(bumped_observed) == 2


# =============================================================================
# plan_roles orchestrator
# =============================================================================


def _mock_llm_planner(prompt: str, **_kwargs: Any) -> str:
    """Return planning-call JSON keyed off prompt content."""
    if "Classify the company below" in prompt:
        return json.dumps(
            {
                "business_model": "B2B SaaS",
                "industry_vertical": "Developer Tools",
                "company_stage": "Growth / Late-stage",
                "employee_estimate": "Mid-market (500-5000)",
                "confidence": "Medium",
                "cited_evidence": ["dbt and Snowflake postings"],
            }
        )

    if "Extract every distinct role" in prompt:
        return json.dumps(
            {
                "signal_strength": "moderate",
                "roles": [
                    {
                        "name": "data-engineer",
                        "display_name": "Data Engineer",
                        "archetype": "data-engineer",
                        "summary": "Builds dbt models.",
                        "posting_citations": ["Data Engineer with dbt"],
                        "posting_count": 2,
                    },
                ],
            }
        )

    if "Identify up to" in prompt and "plausible" in prompt:
        return json.dumps(
            {
                "signal_strength": "moderate",
                "roles": [
                    {
                        "name": "customer-success-manager",
                        "display_name": "Customer Success Manager",
                        "archetype": None,
                        "confidence": "Inferred",
                        "summary": "Drives renewal motion.",
                        "research_citations": ["Mid-market SaaS typically employs CSMs"],
                        "provenance": "industry",
                    },
                    {
                        "name": "marketing-manager",
                        "display_name": "Marketing Manager",
                        "archetype": None,
                        "confidence": "Inferred",
                        "summary": "Owns demand gen.",
                        "research_citations": ["Mid-market SaaS typically employs marketing"],
                        "provenance": "industry",
                    },
                ],
            }
        )

    raise AssertionError(f"Unexpected prompt in planner mock: {prompt[:120]!r}")


class TestPlanRoles:
    def test_observed_plus_plausible_split(self, tmp_path: Path):
        working = tmp_path / "working"
        _write_evidence(
            working,
            recon="Recon: Snowflake account",
            hiring="# Hiring\n- Data Engineer (2 postings)",
            research="Acme is a growing SaaS provider focused on dbt tooling",
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_llm_planner):
            plan = plan_roles(
                company_name="Acme",
                company_url="https://acme.example",
                working_dir=working,
                roles_count=3,
            )
        assert len(plan.observed) == 1
        assert len(plan.plausible) == 2
        assert len(plan.final_roster) == 3
        assert plan.industry.business_model == "B2B SaaS"
        assert plan.plan_md_path is not None
        assert Path(plan.plan_md_path).exists()
        assert plan.plan_json_path is not None
        assert Path(plan.plan_json_path).exists()
        provenances = {r.evidence.provenance for r in plan.final_roster}
        assert RoleProvenance.POSTING in provenances
        assert RoleProvenance.INDUSTRY in provenances

    def test_refuses_when_hiring_and_research_both_empty(self, tmp_path: Path):
        working = tmp_path / "working"
        _write_evidence(working, recon="Recon only — no hiring or research")
        with (
            patch("primr.ai.grok_client.grok_llm", side_effect=_mock_llm_planner),
            pytest.raises(EmptyHiringEvidenceError),
        ):
            plan_roles(
                company_name="Acme",
                company_url="https://acme.example",
                working_dir=working,
                roles_count=3,
            )

    def test_roles_add_bypasses_empty_evidence_error(self, tmp_path: Path):
        """Bug 3 regression: when both posting and research evidence are
        empty, --roles-add (operator-supplied roles) is sufficient
        recovery signal — the EmptyHiringEvidenceError must not fire."""
        working = tmp_path / "working"
        _write_evidence(working, recon="Recon only — no hiring or research")

        def _bypass_mock(prompt: str, **kwargs: Any) -> str:
            # Industry classification still runs; mock it. Observed +
            # plausible calls should be skipped because both evidence
            # streams are empty.
            if "Classify the company below" in prompt:
                return json.dumps(
                    {
                        "business_model": "Unknown",
                        "industry_vertical": "Unknown",
                        "company_stage": "Unknown",
                        "employee_estimate": "Unknown",
                        "confidence": "Low",
                        "cited_evidence": [],
                    }
                )
            return _mock_llm_planner(prompt, **kwargs)

        with patch("primr.ai.grok_client.grok_llm", side_effect=_bypass_mock):
            plan = plan_roles(
                company_name="Acme",
                company_url="https://acme.example",
                working_dir=working,
                roles_count=3,
                roles_add=["Account Executive", "Cloud Migration Consultant"],
            )

        assert len(plan.observed) == 0
        assert len(plan.plausible) == 0
        assert len(plan.operator_added) == 2
        assert len(plan.final_roster) == 2
        assert all(r.evidence.provenance == RoleProvenance.OVERRIDE for r in plan.final_roster)

    def test_allow_recon_only_proceeds(self, tmp_path: Path):
        working = tmp_path / "working"
        _write_evidence(
            working,
            recon="Recon: detected Snowflake account",
            research="Acme is a SaaS company providing dbt tooling.",
        )

        def _no_hiring_mock(prompt: str, **kwargs: Any) -> str:
            if "Extract every distinct role" in prompt:
                # No postings -> empty observed roles.
                return json.dumps({"signal_strength": "sparse", "roles": []})
            return _mock_llm_planner(prompt, **kwargs)

        with patch("primr.ai.grok_client.grok_llm", side_effect=_no_hiring_mock):
            plan = plan_roles(
                company_name="Acme",
                company_url="https://acme.example",
                working_dir=working,
                roles_count=3,
                allow_recon_only=True,
            )
        assert plan.observed == []
        assert len(plan.plausible) >= 1


class TestLoadPlan:
    def test_roundtrip_persist_and_load(self, tmp_path: Path):
        working = tmp_path / "working"
        _write_evidence(
            working,
            recon="Recon: Snowflake",
            hiring="# Hiring\n- Data Engineer",
            research="SaaS company",
        )
        with patch("primr.ai.grok_client.grok_llm", side_effect=_mock_llm_planner):
            plan = plan_roles(
                company_name="Acme",
                company_url="https://acme.example",
                working_dir=working,
                roles_count=3,
            )
        assert plan.plan_json_path is not None
        loaded = load_plan(Path(plan.plan_json_path))
        assert [r.name for r in loaded.final_roster] == [r.name for r in plan.final_roster]
        assert loaded.industry.business_model == plan.industry.business_model
