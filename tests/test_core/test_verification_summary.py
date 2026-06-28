"""Tests for claim-verification display summaries."""

from __future__ import annotations

from types import SimpleNamespace

from primr.core.verification_summary import build_verification_display_stats


def test_verification_summary_passes_without_contradictions():
    result = SimpleNamespace(
        trust_percentage=80,
        total_claims=5,
        verified_count=4,
        unverified_count=1,
        contradicted_count=0,
    )

    stats = build_verification_display_stats(result)

    assert stats.phase == [("Trust", "80%"), ("Verified", "4/5")]
    assert dict(stats.trust_summary) == {
        "Verification Gate": "PASS",
        "Claim Trust": "80%",
        "Claims Checked": "5",
        "Verified": "4/5",
        "Unverified": "1",
    }


def test_verification_summary_warns_and_surfaces_contradictions():
    result = SimpleNamespace(
        trust_percentage=50,
        total_claims=6,
        verified_count=3,
        unverified_count=1,
        contradicted_count=2,
    )

    stats = build_verification_display_stats(result)

    assert ("Contradicted", "2") in stats.phase
    summary = dict(stats.trust_summary)
    assert summary["Verification Gate"] == "WARN"
    assert summary["Contradicted"] == "2"


def test_verification_summary_coerces_missing_or_bad_counts():
    result = SimpleNamespace(
        trust_percentage="bad",
        total_claims=None,
        verified_count=-1,
        unverified_count="2",
        contradicted_count="3",
    )

    stats = build_verification_display_stats(result)

    assert stats.phase == [("Trust", "0%"), ("Verified", "0/0"), ("Contradicted", "3")]
    assert dict(stats.trust_summary)["Unverified"] == "2"
