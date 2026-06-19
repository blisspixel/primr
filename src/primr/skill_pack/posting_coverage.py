"""Posting-coverage assessment for skill-pack role plans.

This is a visibility signal, not a quality gate. It flags the common
enterprise failure mode where discovered postings are real but represent only
one slice of the organization, such as front-line/store roles on a segmented
career site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from primr.skill_pack.schema import IndustryClassification, Role

POSTING_COVERAGE_ADEQUATE = "adequate"
POSTING_COVERAGE_INCOMPLETE = "posting-incomplete"
POSTING_COVERAGE_NOT_APPLICABLE = "not-applicable"

MIN_POSTINGS_FOR_CLUSTER_WARNING = 3
DOMINANT_BAND_WARNING_SHARE = 0.8

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_NUMBER_RE = re.compile(r"\d[\d,]*")

_ENTERPRISE_STAGE_TERMS = (
    "enterprise",
    "mid-market",
    "midmarket",
    "large",
    "global",
    "public",
    "fortune",
    "mature",
)

_ROLE_BANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "frontline-operations",
        (
            "associate",
            "branch",
            "cashier",
            "call center",
            "customer service",
            "driver",
            "field",
            "frontline",
            "front-line",
            "fulfillment",
            "hourly",
            "retail",
            "shift",
            "store",
            "teller",
            "warehouse",
        ),
    ),
    (
        "technical-engineering",
        (
            "cloud",
            "data",
            "developer",
            "devops",
            "engineer",
            "engineering",
            "infrastructure",
            "machine learning",
            "ml",
            "platform",
            "security",
            "software",
            "sre",
        ),
    ),
    (
        "sales-revenue",
        (
            "account executive",
            "business development",
            "customer success",
            "renewal",
            "sales",
        ),
    ),
)


@dataclass(frozen=True)
class PostingCoverageAssessment:
    """Compact, JSON-friendly summary of observed posting coverage."""

    status: str
    total_postings: int
    bucket_count: int
    dominant_bucket: str | None = None
    dominant_postings: int = 0
    dominant_share: float = 0.0
    reason: str = ""
    recommendation: str = ""

    @property
    def warns(self) -> bool:
        return self.status == POSTING_COVERAGE_INCOMPLETE

    def to_evidence_summary(self) -> dict[str, object]:
        return {
            "posting_coverage_status": self.status,
            "posting_coverage_warns": self.warns,
            "posting_coverage_total_postings": self.total_postings,
            "posting_coverage_bucket_count": self.bucket_count,
            "posting_coverage_dominant_bucket": self.dominant_bucket or "",
            "posting_coverage_dominant_share": round(self.dominant_share, 3),
            "posting_coverage_reason": self.reason,
            "posting_coverage_recommendation": self.recommendation,
        }


def assess_posting_coverage(
    observed_roles: list[Role],
    industry: IndustryClassification,
) -> PostingCoverageAssessment:
    """Return a non-blocking coverage signal for observed posting evidence."""

    if not observed_roles:
        return PostingCoverageAssessment(
            status=POSTING_COVERAGE_NOT_APPLICABLE,
            total_postings=0,
            bucket_count=0,
            reason="No observed roles were extracted from hiring evidence.",
        )

    bucket_counts: dict[str, int] = {}
    for role in observed_roles:
        bucket = _role_bucket(role)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + max(role.evidence.posting_count, 1)

    total_postings = sum(bucket_counts.values())
    dominant_bucket, dominant_postings = max(bucket_counts.items(), key=lambda item: item[1])
    dominant_share = dominant_postings / total_postings if total_postings else 0.0

    if not _looks_enterprise_scale(industry):
        return PostingCoverageAssessment(
            status=POSTING_COVERAGE_ADEQUATE,
            total_postings=total_postings,
            bucket_count=len(bucket_counts),
            dominant_bucket=dominant_bucket,
            dominant_postings=dominant_postings,
            dominant_share=dominant_share,
            reason="Company scale signal does not require enterprise coverage warning.",
        )

    if total_postings < MIN_POSTINGS_FOR_CLUSTER_WARNING:
        return PostingCoverageAssessment(
            status=POSTING_COVERAGE_ADEQUATE,
            total_postings=total_postings,
            bucket_count=len(bucket_counts),
            dominant_bucket=dominant_bucket,
            dominant_postings=dominant_postings,
            dominant_share=dominant_share,
            reason="Too few observed postings to infer a segmented coverage gap.",
        )

    if dominant_share >= DOMINANT_BAND_WARNING_SHARE:
        share_percent = round(dominant_share * 100)
        return PostingCoverageAssessment(
            status=POSTING_COVERAGE_INCOMPLETE,
            total_postings=total_postings,
            bucket_count=len(bucket_counts),
            dominant_bucket=dominant_bucket,
            dominant_postings=dominant_postings,
            dominant_share=dominant_share,
            reason=(
                f"{dominant_postings}/{total_postings} observed postings "
                f"({share_percent}%) cluster in `{dominant_bucket}` for a "
                "mid-market-or-larger organization."
            ),
            recommendation=(
                "Treat observed roles as a partial career-site slice. Add a corporate "
                "JD or role brief with --from-jd, use --roles-add/--roles-override for "
                "known specialized roles, or rerun from a richer report/segmented "
                "career-site evidence set."
            ),
        )

    return PostingCoverageAssessment(
        status=POSTING_COVERAGE_ADEQUATE,
        total_postings=total_postings,
        bucket_count=len(bucket_counts),
        dominant_bucket=dominant_bucket,
        dominant_postings=dominant_postings,
        dominant_share=dominant_share,
        reason="Observed postings span more than one dominant role band.",
    )


def _role_bucket(role: Role) -> str:
    text = " ".join([role.name, role.display_name, role.summary]).lower()
    for band, terms in _ROLE_BANDS:
        if any(term in text for term in terms):
            return band
    if role.evidence.archetype:
        return role.evidence.archetype
    return _normalize_bucket(role.display_name or role.name)


def _normalize_bucket(value: str) -> str:
    return _NON_ALNUM_RE.sub("-", value.lower()).strip("-") or "unknown"


def _looks_enterprise_scale(industry: IndustryClassification) -> bool:
    text = " ".join([industry.company_stage, industry.employee_estimate]).lower()
    if any(term in text for term in _ENTERPRISE_STAGE_TERMS):
        return True
    numbers = [int(match.group(0).replace(",", "")) for match in _NUMBER_RE.finditer(text)]
    return bool(numbers and max(numbers) >= 500)


__all__ = [
    "DOMINANT_BAND_WARNING_SHARE",
    "MIN_POSTINGS_FOR_CLUSTER_WARNING",
    "POSTING_COVERAGE_ADEQUATE",
    "POSTING_COVERAGE_INCOMPLETE",
    "POSTING_COVERAGE_NOT_APPLICABLE",
    "PostingCoverageAssessment",
    "assess_posting_coverage",
]
