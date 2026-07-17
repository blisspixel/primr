"""Property-based invariants for the skill-pack roster-cap logic.

These complement the example-based tests in ``test_curation.py`` /
``test_planner.py`` by asserting the cap/merge invariants hold for *arbitrary*
rosters (Hypothesis-generated), not just the hand-picked cases. The roster cap
is the boundary where operator intent, observed roles, and inferred roles
compete for a bounded number of slots — exactly the kind of merge logic where an
off-by-one or a priority inversion would silently ship the wrong pack.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from primr.skill_pack.curation import _drop_excess_to_cap
from primr.skill_pack.planner import _merge_and_cap
from primr.skill_pack.schema import Role, RoleEvidence, RoleProvenance

# Trim-priority each provenance maps to in _drop_excess_to_cap (lower = first out).
_TRIM_PRIORITY = {
    RoleProvenance.RESEARCH: 0,
    RoleProvenance.INDUSTRY: 0,
    RoleProvenance.POSTING: 1,
    RoleProvenance.OVERRIDE: 2,
}

# A small archetype pool (plus None) so dedup-by-archetype actually triggers.
_ARCHETYPES = st.one_of(st.none(), st.sampled_from(["alpha", "beta", "gamma"]))
_PROVENANCES = st.sampled_from(list(RoleProvenance))


def _role(name: str, provenance: RoleProvenance, archetype: str | None) -> Role:
    return Role(
        name=name,
        display_name=name.replace("-", " ").title(),
        confidence="Confirmed",
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


# A roster strategy: index-derived names guarantee uniqueness; provenance and
# archetype are drawn so dedup + trim-priority paths are exercised.
_roster_specs = st.lists(st.tuples(_PROVENANCES, _ARCHETYPES), max_size=14)


def _build(specs) -> list[Role]:
    return [_role(f"role-{i}", prov, arch) for i, (prov, arch) in enumerate(specs)]


class TestDropExcessToCap:
    @given(_roster_specs, st.integers(min_value=1, max_value=15))
    def test_partition_and_cap(self, specs, cap):
        roster = _build(specs)
        kept, trimmed = _drop_excess_to_cap(roster, cap)
        # Exact partition of the input (no role lost or duplicated).
        assert len(kept) + len(trimmed) == len(roster)
        assert {r.name for r in kept} | {r.name for r in trimmed} == {r.name for r in roster}
        assert {r.name for r in kept}.isdisjoint({r.name for r in trimmed})
        # Cap is respected exactly.
        assert len(kept) == min(len(roster), cap)

    @given(_roster_specs, st.integers(min_value=1, max_value=15))
    def test_kept_preserves_relative_order(self, specs, cap):
        roster = _build(specs)
        kept, _ = _drop_excess_to_cap(roster, cap)
        kept_names = [r.name for r in kept]
        roster_order = [r.name for r in roster if r.name in set(kept_names)]
        assert kept_names == roster_order

    @given(_roster_specs, st.integers(min_value=1, max_value=15))
    def test_trim_respects_priority(self, specs, cap):
        """Never trim a higher-priority role while keeping a lower-priority one
        (plausible go before observed go before operator overrides)."""
        roster = _build(specs)
        kept, trimmed = _drop_excess_to_cap(roster, cap)
        if kept and trimmed:
            worst_trimmed = max(_TRIM_PRIORITY[r.evidence.provenance] for r in trimmed)
            best_kept = min(_TRIM_PRIORITY[r.evidence.provenance] for r in kept)
            assert worst_trimmed <= best_kept


class TestMergeAndCap:
    @given(_roster_specs, _roster_specs, st.integers(min_value=1, max_value=15))
    def test_cap_and_no_duplicates(self, obs_specs, plaus_specs, cap):
        # Disjoint name spaces for observed vs plausible.
        observed = [_role(f"obs-{i}", p, a) for i, (p, a) in enumerate(obs_specs)]
        plausible = [_role(f"plaus-{i}", p, a) for i, (p, a) in enumerate(plaus_specs)]
        final, gap = _merge_and_cap(observed, plausible, cap)

        # Cap never exceeded.
        assert len(final) <= cap
        # No duplicate names in the final roster.
        names = [r.name for r in final]
        assert len(names) == len(set(names))
        # Archetype dedup applies to PLAUSIBLE roles only: a plausible role is
        # never added if its archetype already appears (observed or earlier
        # plausible). Observed-vs-observed archetype repeats are allowed by
        # design — two distinct real postings both deserve representation.
        observed_archs = {
            r.evidence.archetype
            for r in final
            if r.name.startswith("obs-") and r.evidence.archetype
        }
        plaus_archs = [
            r.evidence.archetype
            for r in final
            if r.name.startswith("plaus-") and r.evidence.archetype
        ]
        assert len(plaus_archs) == len(set(plaus_archs))
        assert set(plaus_archs).isdisjoint(observed_archs)
        # gap holds plausible roles that overflowed AND any observed roles
        # the plausible-reserve bumped out. No name appears in both lists.
        final_names = {r.name for r in final}
        gap_names = {r.name for r in gap}
        assert final_names.isdisjoint(gap_names)
        # Observed roles that land in gap are a contiguous suffix of the
        # observed list: the reserve bumps the LAST observed roles first, so
        # every bumped observed index is >= the count of observed kept in
        # final — the leading-observed-wins guarantee still holds.
        kept_obs = sum(1 for r in final if r.name.startswith("obs-"))
        for r in gap:
            if r.name.startswith("obs-"):
                assert int(r.name.split("-")[1]) >= kept_obs

    @given(_roster_specs, _roster_specs, st.integers(min_value=1, max_value=15))
    def test_observed_take_priority_prefix(self, obs_specs, plaus_specs, cap):
        observed = [_role(f"obs-{i}", p, a) for i, (p, a) in enumerate(obs_specs)]
        plausible = [_role(f"plaus-{i}", p, a) for i, (p, a) in enumerate(plaus_specs)]
        final, _ = _merge_and_cap(observed, plausible, cap)
        # The leading slots of the final roster are exactly observed[:cap],
        # in order — observed always wins.
        n_observed_kept = sum(1 for r in final if r.name.startswith("obs-"))
        assert [r.name for r in final[:n_observed_kept]] == [r.name for r in observed[:cap]][
            :n_observed_kept
        ]
