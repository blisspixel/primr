"""Tests for skill-pack posting coverage assessment."""

from __future__ import annotations

from primr.skill_pack.posting_coverage import (
    POSTING_COVERAGE_ADEQUATE,
    POSTING_COVERAGE_INCOMPLETE,
    POSTING_COVERAGE_NOT_APPLICABLE,
    assess_posting_coverage,
)
from primr.skill_pack.schema import IndustryClassification, Role, RoleEvidence


def _industry(
    *,
    stage: str = "Enterprise",
    employee_estimate: str = "10,000+",
) -> IndustryClassification:
    return IndustryClassification(
        business_model="Retail",
        industry_vertical="Multi-brand retailer",
        company_stage=stage,
        employee_estimate=employee_estimate,
        confidence="Medium",
    )


def _role(name: str, *, posting_count: int, archetype: str | None = None) -> Role:
    return Role(
        name=name,
        display_name=name.replace("-", " ").title(),
        confidence="Confirmed",
        summary=f"{name} role",
        evidence=RoleEvidence(
            posting_count=posting_count,
            archetype=archetype,
            citations=[f"{name} posting"],
        ),
    )


def test_empty_observed_roles_not_applicable():
    assessment = assess_posting_coverage([], _industry())

    assert assessment.status == POSTING_COVERAGE_NOT_APPLICABLE
    assert not assessment.warns
    assert assessment.total_postings == 0


def test_clustered_frontline_roles_warn_for_enterprise():
    roles = [
        _role("store-associate", posting_count=7),
        _role("retail-shift-lead", posting_count=2),
        _role("warehouse-associate", posting_count=1),
    ]

    assessment = assess_posting_coverage(roles, _industry())

    assert assessment.status == POSTING_COVERAGE_INCOMPLETE
    assert assessment.warns
    assert assessment.dominant_bucket == "frontline-operations"
    assert assessment.dominant_share == 1.0
    assert "--from-jd" in assessment.recommendation
    assert "--roles-add" in assessment.recommendation


def test_clustered_roles_do_not_warn_for_small_company():
    roles = [
        _role("store-associate", posting_count=4),
        _role("retail-shift-lead", posting_count=2),
    ]

    assessment = assess_posting_coverage(
        roles,
        _industry(stage="Seed", employee_estimate="25-50"),
    )

    assert assessment.status == POSTING_COVERAGE_ADEQUATE
    assert not assessment.warns


def test_diverse_enterprise_roles_are_adequate():
    roles = [
        _role("store-associate", posting_count=4),
        _role("account-executive", posting_count=2),
        _role("security-engineer", posting_count=2),
    ]

    assessment = assess_posting_coverage(roles, _industry())

    assert assessment.status == POSTING_COVERAGE_ADEQUATE
    assert not assessment.warns
    assert assessment.bucket_count == 3
