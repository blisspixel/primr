"""Tests for the bundled role archetypes loader + matcher."""

from __future__ import annotations

import pytest

from primr.skill_pack.archetypes import (
    HIGH_MATCH_THRESHOLD,
    grounding_prompt_fragment,
    load_archetypes,
    match_archetype,
)


def test_archetypes_load_at_least_one():
    archetypes = load_archetypes()
    assert len(archetypes) >= 5, f"Expected >=5 bundled archetypes, got {len(archetypes)}"


def test_archetypes_required_fields():
    archetypes = load_archetypes()
    for slug, archetype in archetypes.items():
        assert archetype.slug == slug
        assert archetype.display_name
        assert archetype.canonical_skills, f"{slug}: no canonical_skills"
        # Every canonical skill name should be kebab-case-ish
        for skill in archetype.canonical_skills:
            assert skill.name == skill.name.lower(), f"{slug}/{skill.name}: not lowercase"


def test_exact_slug_match():
    match = match_archetype("data-engineer")
    assert match.archetype is not None
    assert match.archetype.slug == "data-engineer"
    assert match.confidence == 1.0
    assert match.matched_via == "exact-slug"


def test_hint_takes_priority():
    # An explicit hint should win over name-based heuristics.
    match = match_archetype("Senior Engineer", hints=["ml-engineer"])
    assert match.archetype is not None
    assert match.archetype.slug == "ml-engineer"
    assert match.matched_via == "exact-slug"


def test_alias_match():
    # "sfdc admin" is listed as an alias of salesforce-admin
    match = match_archetype("SFDC Admin")
    assert match.archetype is not None
    assert match.archetype.slug == "salesforce-admin"
    # Alias match is high-confidence
    assert match.confidence >= 0.9


def test_display_name_similarity_match():
    # "Senior Data Engineer" doesn't match a slug exactly but display
    # similarity should pick up data-engineer.
    match = match_archetype("Senior Data Engineer")
    assert match.archetype is not None
    assert match.archetype.slug in {"data-engineer", "ml-engineer"}


@pytest.mark.parametrize(
    "role_name,expected_slug",
    [
        ("Site Reliability Engineer", "sre"),
        ("Cloud Security Engineer", "security-engineer"),
        ("Microsoft 365 Administrator", "m365-admin"),
        ("DevOps Engineer", "devops-engineer"),
        ("Product Manager", "product-manager"),
        ("Customer Success Manager", "customer-success-manager"),
        ("Sales Director", "account-executive"),
        ("Account Executive", "account-executive"),
        ("Marketing Manager", "marketing-manager"),
        ("HR Business Partner", "people-operations-manager"),
        ("Finance Manager", "finance-manager"),
        ("Legal Counsel", "legal-compliance-manager"),
        ("Operations Manager", "operations-manager"),
    ],
)
def test_canonical_titles_match_intended_archetypes(role_name: str, expected_slug: str):
    match = match_archetype(role_name)
    assert match.archetype is not None
    assert match.archetype.slug == expected_slug, (
        f"{role_name!r} matched {match.archetype.slug}, expected {expected_slug}"
    )


def test_unknown_role_returns_none_or_low_confidence():
    match = match_archetype("Senior Ferret Handler")
    # Either no match or a very low-confidence match — both are acceptable.
    if match.archetype is not None:
        assert match.confidence < HIGH_MATCH_THRESHOLD


def test_weak_display_name_similarity_is_not_returned_as_grounding():
    match = match_archetype("Retail Floor Supervisor")
    assert match.archetype is None
    assert match.confidence < HIGH_MATCH_THRESHOLD


def test_grounding_fragment_includes_canonical_skills():
    archetypes = load_archetypes()
    archetype = archetypes["data-engineer"]
    fragment = grounding_prompt_fragment(archetype, max_skills=5)
    assert "Canonical skills" in fragment
    # Should mention at least one of the data-engineer canonical skills
    assert any(skill.name in fragment for skill in archetype.canonical_skills[:5])
    assert "—" not in fragment


def test_grounding_fragment_includes_ai_patterns():
    archetypes = load_archetypes()
    archetype = archetypes["sre"]
    fragment = grounding_prompt_fragment(archetype, max_skills=5)
    if archetype.ai_augmentation_patterns:
        assert "AI augmentation patterns" in fragment
