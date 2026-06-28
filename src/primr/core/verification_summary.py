"""Display helpers for optional claim verification results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VerificationDisplayStats:
    """Console-ready stats for verification completion and trust summary."""

    phase: list[tuple[str, str]]
    trust_summary: list[tuple[str, str]]


def _count(result: Any, field_name: str) -> int:
    value = getattr(result, field_name, 0)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def build_verification_display_stats(result: Any) -> VerificationDisplayStats:
    """Build compact, auditable display stats from a verification result."""

    total = _count(result, "total_claims")
    verified = _count(result, "verified_count")
    unverified = _count(result, "unverified_count")
    contradicted = _count(result, "contradicted_count")
    trust_percentage = _count(result, "trust_percentage")

    phase = [
        ("Trust", f"{trust_percentage}%"),
        ("Verified", f"{verified}/{total}"),
    ]
    if contradicted:
        phase.append(("Contradicted", str(contradicted)))

    trust_summary = [
        ("Verification Gate", "WARN" if contradicted else "PASS"),
        ("Claim Trust", f"{trust_percentage}%"),
        ("Claims Checked", str(total)),
        ("Verified", f"{verified}/{total}"),
    ]
    if unverified:
        trust_summary.append(("Unverified", str(unverified)))
    if contradicted:
        trust_summary.append(("Contradicted", str(contradicted)))

    return VerificationDisplayStats(phase=phase, trust_summary=trust_summary)
