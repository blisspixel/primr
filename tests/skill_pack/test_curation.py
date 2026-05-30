"""Tests for operator curation: --roles-add, --roles-skip, and how they
compose with --from-plan and --roles-override.

Covers the composition matrix locked in the design discussion:
  - --roles-add alone (plan + append)
  - --roles-skip alone (plan + drop)
  - --roles-add + --roles-skip (curate)
  - --from-plan + --roles-add (augment saved plan)
  - --from-plan + --roles-skip (drop from saved plan)
  - --roles-override + --roles-add/--roles-skip (override wins, curation warned)

Plus edge cases:
  - Cap overflow trims plausible first, then observed, never operator-added
  - Name dedup between added and discovered (existing wins)
  - Archetype dedup between added and discovered
  - Skip removes everything (hard error)
  - Skip mentions a name not in plan (logs warning)
"""

from __future__ import annotations

import pytest

from primr.skill_pack.config import MAX_ROLES, SkillPackConfig
from primr.skill_pack.planner import (
    _drop_excess_to_cap,
    _materialize_added_role,
    _normalize_curation_key,
    apply_curation,
)
from primr.skill_pack.schema import (
    IndustryClassification,
    Role,
    RoleEvidence,
    RolePlan,
    RoleProvenance,
)

# =============================================================================
# Helpers
# =============================================================================


def _role(
    name: str,
    *,
    display: str | None = None,
    provenance: RoleProvenance = RoleProvenance.POSTING,
    archetype: str | None = None,
) -> Role:
    return Role(
        name=name,
        display_name=display or name.replace("-", " ").title(),
        confidence={
            RoleProvenance.POSTING: "Confirmed",
            RoleProvenance.RESEARCH: "Inferred",
            RoleProvenance.INDUSTRY: "Inferred",
            RoleProvenance.OVERRIDE: "Operator",
        }[provenance],
        summary=f"summary for {name}",
        evidence=RoleEvidence(
            sources=[],
            dns_signals=[],
            posting_count=1 if provenance == RoleProvenance.POSTING else 0,
            archetype=archetype,
            provenance=provenance,
            citations=["test"],
        ),
    )


def _plan(observed=None, plausible=None, final=None) -> RolePlan:
    observed = list(observed or [])
    plausible = list(plausible or [])
    final = list(final if final is not None else observed + plausible)
    return RolePlan(
        observed=observed,
        plausible=plausible,
        final_roster=final,
        industry=IndustryClassification(),
        evidence_summary={
            "observed_count": len(observed),
            "plausible_count": len(plausible),
            "final_roster_count": len(final),
            "gap_flagged_count": 0,
        },
    )


# =============================================================================
# Normalization
# =============================================================================


class TestNormalize:
    def test_label_to_slug_form(self):
        assert _normalize_curation_key("Marketing Manager") == "marketing-manager"
        assert _normalize_curation_key("marketing-manager") == "marketing-manager"
        assert _normalize_curation_key("VP of Marketing") == "vp-of-marketing"

    def test_handles_punctuation(self):
        assert _normalize_curation_key("Sr. Cloud Engineer") == "sr-cloud-engineer"


# =============================================================================
# Materialize added role
# =============================================================================


class TestMaterializeAdded:
    def test_provenance_is_override(self):
        role = _materialize_added_role("Account Executive")
        assert role.evidence.provenance == RoleProvenance.OVERRIDE
        assert role.confidence == "Operator"
        assert role.citations_count() if hasattr(role, "citations_count") else True
        assert "operator override" in role.evidence.citations[0].lower()

    def test_archetype_match_runs(self):
        # "Salesforce Administrator" should hit the salesforce-admin archetype.
        role = _materialize_added_role("Salesforce Administrator")
        assert role.evidence.archetype is not None


# =============================================================================
# Cap-aware trim
# =============================================================================


class TestDropExcessToCap:
    def test_under_cap_returns_unchanged(self):
        roster = [_role("a"), _role("b")]
        kept, trimmed = _drop_excess_to_cap(roster, cap=5)
        assert [r.name for r in kept] == ["a", "b"]
        assert trimmed == []

    def test_plausible_trimmed_first(self):
        roster = [
            _role("obs1", provenance=RoleProvenance.POSTING),
            _role("plaus1", provenance=RoleProvenance.RESEARCH),
            _role("over1", provenance=RoleProvenance.OVERRIDE),
            _role("plaus2", provenance=RoleProvenance.INDUSTRY),
        ]
        kept, trimmed = _drop_excess_to_cap(roster, cap=2)
        kept_names = {r.name for r in kept}
        # Override always survives, observed survives over plausible.
        assert "over1" in kept_names
        assert "obs1" in kept_names
        # Both plausible roles got trimmed.
        assert {r.name for r in trimmed} == {"plaus1", "plaus2"}

    def test_observed_trimmed_before_override(self):
        roster = [
            _role("obs1", provenance=RoleProvenance.POSTING),
            _role("obs2", provenance=RoleProvenance.POSTING),
            _role("over1", provenance=RoleProvenance.OVERRIDE),
            _role("over2", provenance=RoleProvenance.OVERRIDE),
        ]
        kept, trimmed = _drop_excess_to_cap(roster, cap=2)
        kept_provs = {r.evidence.provenance for r in kept}
        # Both overrides survive; both observed trimmed.
        assert kept_provs == {RoleProvenance.OVERRIDE}
        assert {r.evidence.provenance for r in trimmed} == {RoleProvenance.POSTING}


# =============================================================================
# apply_curation — the composition matrix
# =============================================================================


class TestApplyCuration:
    def test_add_appends_to_roster(self):
        plan = _plan(observed=[_role("data-engineer")])
        apply_curation(plan, roles_add=["Account Executive"], roles_skip=[], cap=5)
        names = [r.name for r in plan.final_roster]
        assert names == ["data-engineer", "account-executive"]
        assert len(plan.operator_added) == 1
        assert plan.operator_added[0].evidence.provenance == RoleProvenance.OVERRIDE

    def test_skip_removes_by_display_name(self):
        plan = _plan(
            observed=[_role("data-engineer"), _role("marketing-manager")]
        )
        apply_curation(plan, roles_add=[], roles_skip=["Marketing Manager"], cap=5)
        assert [r.name for r in plan.final_roster] == ["data-engineer"]
        assert plan.operator_skipped == ["marketing-manager"]

    def test_skip_removes_by_slug(self):
        plan = _plan(
            observed=[_role("data-engineer"), _role("marketing-manager")]
        )
        apply_curation(plan, roles_add=[], roles_skip=["marketing-manager"], cap=5)
        assert [r.name for r in plan.final_roster] == ["data-engineer"]

    def test_skip_then_add_swap(self):
        plan = _plan(observed=[_role("marketing-manager")])
        apply_curation(
            plan,
            roles_add=["Demand Generation Manager"],
            roles_skip=["Marketing Manager"],
            cap=5,
        )
        names = [r.name for r in plan.final_roster]
        assert "marketing-manager" not in names
        assert "demand-generation-manager" in names

    def test_add_dedupes_by_existing_name(self):
        plan = _plan(observed=[_role("marketing-manager")])
        apply_curation(plan, roles_add=["Marketing Manager"], roles_skip=[], cap=5)
        # Existing wins; no duplicate appended.
        assert [r.name for r in plan.final_roster] == ["marketing-manager"]
        assert plan.operator_added == []

    def test_add_dedupes_by_archetype(self):
        # An existing role with archetype=salesforce-admin blocks an add
        # that resolves to the same archetype.
        plan = _plan(
            observed=[
                _role("crm-admin-acme", archetype="salesforce-admin")
            ]
        )
        # "Salesforce Administrator" resolves to archetype salesforce-admin
        # via the bundled archetype list.
        apply_curation(
            plan, roles_add=["Salesforce Administrator"], roles_skip=[], cap=5
        )
        assert plan.operator_added == []
        assert [r.name for r in plan.final_roster] == ["crm-admin-acme"]

    def test_two_adds_share_archetype_both_kept(self):
        # Regression: archetype dedup must NOT block a second --roles-add
        # entry just because the first one happened to resolve to the
        # same archetype. The operator typed two distinct labels and
        # both belong in the final roster.
        plan = _plan(observed=[_role("data-engineer", archetype="data-engineer")])
        apply_curation(
            plan,
            roles_add=["Account Executive", "Senior Account Executive"],
            roles_skip=[],
            cap=5,
        )
        added_names = [r.name for r in plan.operator_added]
        # Both AE labels survive even though they may share an archetype
        # (e.g., both fall back to salesforce-admin via display-name match).
        assert len(added_names) == 2
        assert "account-executive" in added_names
        assert "senior-account-executive" in added_names

    def test_warning_emitted_when_archetype_dedup_drops_add(self, caplog):
        # Bug 2 regression: archetype-based dedup must surface as a
        # WARNING so the operator sees that their --roles-add entry was
        # not authored. INFO logs are not shown in CLI mode by default.
        import logging

        caplog.set_level(logging.WARNING, logger="primr.skill_pack.planner")
        plan = _plan(
            observed=[_role("crm-admin-acme", archetype="salesforce-admin")]
        )
        apply_curation(
            plan,
            roles_add=["Salesforce Administrator"],
            roles_skip=[],
            cap=5,
        )
        warnings = " ".join(rec.message for rec in caplog.records)
        assert "Salesforce Administrator" in warnings
        assert "salesforce-admin" in warnings.lower()

    def test_cap_pushes_plausible_to_gap(self):
        plan = _plan(
            observed=[_role("obs1", provenance=RoleProvenance.POSTING)],
            plausible=[
                _role("plaus1", provenance=RoleProvenance.RESEARCH),
                _role("plaus2", provenance=RoleProvenance.INDUSTRY),
            ],
        )
        # Adding 2 + roster of 3 = 5; cap = 3 means 2 must be trimmed.
        apply_curation(
            plan,
            roles_add=["Account Executive", "Procurement Manager"],
            roles_skip=[],
            cap=3,
        )
        # The two added survive; the observed survives; the two plausible
        # got trimmed to gap_flagged.
        kept_provs = {r.evidence.provenance for r in plan.final_roster}
        assert RoleProvenance.OVERRIDE in kept_provs
        assert RoleProvenance.POSTING in kept_provs
        gap_provs = {r.evidence.provenance for r in plan.gap_flagged}
        assert RoleProvenance.RESEARCH in gap_provs or RoleProvenance.INDUSTRY in gap_provs

    def test_skip_removes_everything_raises(self):
        plan = _plan(observed=[_role("a"), _role("b")])
        with pytest.raises(RuntimeError, match="empty roster"):
            apply_curation(plan, roles_add=[], roles_skip=["a", "b"], cap=5)

    def test_unmatched_skip_logs_warning(self, caplog):
        import logging
        caplog.set_level(logging.WARNING, logger="primr.skill_pack.planner")
        plan = _plan(observed=[_role("a")])
        apply_curation(
            plan,
            roles_add=[],
            roles_skip=["nonexistent", "also-not-there"],
            cap=5,
        )
        warnings = " ".join(rec.message for rec in caplog.records)
        assert "nonexistent" in warnings or "also-not-there" in warnings


# =============================================================================
# Config-level validation
# =============================================================================


# =============================================================================
# Bug-fix regressions
# =============================================================================


class TestCapClampedToMaxRoles:
    """Bug 1 regression: --from-plan + --roles-add must not exceed MAX_ROLES."""

    def test_overflow_clamps_to_max_roles(self):
        # Build a plan at the MAX_ROLES ceiling, then try to add more.
        plan = _plan(
            observed=[
                _role(f"obs-{i}", provenance=RoleProvenance.POSTING)
                for i in range(MAX_ROLES)
            ]
        )
        # Adding 3 more should not push the roster over MAX_ROLES.
        apply_curation(
            plan,
            roles_add=["Role A", "Role B", "Role C"],
            roles_skip=[],
            cap=MAX_ROLES,  # cap clamped by caller to MAX_ROLES
        )
        assert len(plan.final_roster) == MAX_ROLES
        # Operator-added entries win on trim order, so all 3 adds survive
        # and 3 observed get trimmed instead.
        added_names = {r.name for r in plan.operator_added}
        kept_names = {r.name for r in plan.final_roster}
        assert added_names.issubset(kept_names)


class TestLoadPlanErrorWrap:
    """Bug 5 regression: malformed JSON should raise RuntimeError, not raw
    JSONDecodeError, so the pipeline error path renders cleanly."""

    def test_malformed_json_raises_runtime_error(self, tmp_path):
        from primr.skill_pack.planner import load_plan

        bad = tmp_path / "role_plan.json"
        bad.write_text("{not-json: }", encoding="utf-8")
        with pytest.raises(RuntimeError, match="not valid JSON"):
            load_plan(bad)

    def test_missing_file_raises_runtime_error(self, tmp_path):
        from primr.skill_pack.planner import load_plan

        missing = tmp_path / "does-not-exist.json"
        with pytest.raises(RuntimeError, match="Could not read"):
            load_plan(missing)

    def test_non_object_json_raises_runtime_error(self, tmp_path):
        from primr.skill_pack.planner import load_plan

        list_json = tmp_path / "role_plan.json"
        list_json.write_text("[]", encoding="utf-8")
        with pytest.raises(RuntimeError, match="not a JSON object"):
            load_plan(list_json)


class TestThreeWayClashDetection:
    """Bug 10 regression: config validation must reject any clash across
    the three list-typed flags (override, add, skip)."""

    def test_override_and_add_clash_raises(self):
        config = SkillPackConfig(
            roles_count=5,
            roles_override=["Account Executive"],
            roles_add=["account executive"],
        )
        with pytest.raises(ValueError, match="roles_override and roles_add"):
            config.validate()

    def test_override_and_skip_clash_raises(self):
        config = SkillPackConfig(
            roles_count=5,
            roles_override=["Account Executive"],
            roles_skip=["ACCOUNT EXECUTIVE"],
        )
        with pytest.raises(ValueError, match="roles_override and roles_skip"):
            config.validate()


class TestHalfCuratedStatePreflight:
    """Bug 12 regression: when curation would leave an empty roster the
    plan must NOT be partially mutated. The skip pass needs to be
    preflight-validated before any state change."""

    def test_skip_all_with_no_add_raises_before_mutation(self):
        original_observed = [_role("a"), _role("b")]
        plan = _plan(observed=original_observed)
        original_final = list(plan.final_roster)
        with pytest.raises(RuntimeError, match="would leave an empty roster"):
            apply_curation(plan, roles_add=[], roles_skip=["a", "b"], cap=5)
        # Plan untouched: final_roster, operator_skipped, operator_added
        # all preserved.
        assert plan.final_roster == original_final
        assert plan.operator_skipped == []
        assert plan.operator_added == []


class TestProvenanceFallbackRaises:
    """Bug 14 regression: _provenance_guidance must raise on unknown
    enum values so authoring doesn't silently degrade if RoleProvenance
    is extended without updating the guidance branch chain."""

    def test_unknown_provenance_raises(self):
        from primr.skill_pack.authoring import _provenance_guidance
        from primr.skill_pack.schema import Role, RoleEvidence

        # Forge a Role with an evidence.provenance value that isn't in
        # the enum by setting it to a string sentinel. This simulates the
        # "new enum value added but not handled" scenario.
        role = Role(
            name="x",
            display_name="X",
            confidence="Operator",
            summary="x",
            evidence=RoleEvidence(),
        )
        # Replace the provenance with a stub object the branch chain
        # won't recognize.
        role.evidence.provenance = "synthetic-future-value"  # type: ignore
        with pytest.raises(ValueError, match="Unhandled RoleProvenance"):
            _provenance_guidance(role)


class TestConfigValidation:
    def test_clash_between_add_and_skip_raises(self):
        config = SkillPackConfig(
            roles_count=5,
            roles_add=["Marketing Manager"],
            roles_skip=["marketing manager"],  # different case + space
        )
        with pytest.raises(ValueError, match="cannot appear in both"):
            config.validate()

    def test_add_within_max_roles(self):
        config = SkillPackConfig(
            roles_count=5,
            roles_add=[f"Role {i}" for i in range(MAX_ROLES)],
        )
        config.validate()  # exactly MAX_ROLES is allowed

    def test_add_exceeds_max_roles_raises(self):
        config = SkillPackConfig(
            roles_count=5,
            roles_add=[f"Role {i}" for i in range(MAX_ROLES + 1)],
        )
        with pytest.raises(ValueError, match="roles_add accepts at most"):
            config.validate()

    def test_skip_long_label_raises(self):
        config = SkillPackConfig(roles_count=5, roles_skip=["X" * 100])
        with pytest.raises(ValueError, match="exceeds 80 characters"):
            config.validate()

    def test_add_and_skip_dedupe_within_themselves(self):
        config = SkillPackConfig(
            roles_count=5,
            roles_add=["Account Executive", "ACCOUNT EXECUTIVE"],
            roles_skip=["Foo", "foo "],
        )
        config.validate()
        assert config.roles_add == ["Account Executive"]
        assert config.roles_skip == ["Foo"]
