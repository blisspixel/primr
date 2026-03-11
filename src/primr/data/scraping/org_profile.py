"""Organization-type inference for org-aware scraping behavior."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


ORGANIZATION_TYPES = {
    "commercial",
    "government",
    "nonprofit",
    "education",
    "healthcare",
    "unknown",
}


@dataclass(frozen=True)
class OrganizationProfile:
    """Lightweight classification result used to tune scraping behavior."""

    organization_type: str
    confidence: float
    signals: tuple[str, ...]


_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "government": (".gov", ".mil"),
    "education": (".edu",),
    "nonprofit": (".org",),
}

_TEXT_HINTS: dict[str, tuple[str, ...]] = {
    "government": (
        "department of ",
        "state of ",
        "county",
        "city of ",
        "office of ",
        "public safety",
        "public records",
        "agency",
        "commission",
        "administration",
        "secretary",
        "governor",
        "budget",
        "statute",
        "rule",
    ),
    "education": (
        "university",
        "college",
        "school of ",
        "campus",
        "faculty",
        "student",
        "research institute",
    ),
    "nonprofit": (
        "foundation",
        "nonprofit",
        "not-for-profit",
        "charity",
        "association",
        "society",
        "membership",
        "donate",
    ),
    "healthcare": (
        "hospital",
        "health system",
        "medical center",
        "clinic",
        "patient",
        "care team",
        "physician",
        "healthcare",
    ),
    "commercial": (
        "customers",
        "pricing",
        "solutions",
        "products",
        "platform",
        "case study",
        "book a demo",
        "request a demo",
    ),
}


def classify_organization_type(
    website: str,
    homepage_text: str | None = None,
    company_name: str | None = None,
) -> OrganizationProfile:
    """Infer the site/org type from domain and homepage/company text."""

    parsed = urlparse(website)
    netloc = parsed.netloc.lower()
    text = " ".join(part for part in (company_name or "", homepage_text or "") if part).lower()

    scores = {org_type: 0.0 for org_type in ORGANIZATION_TYPES}
    signals: list[str] = []

    for org_type, suffixes in _DOMAIN_HINTS.items():
        if any(netloc.endswith(suffix) for suffix in suffixes):
            scores[org_type] += 3.0
            signals.append(f"domain:{org_type}")

    for org_type, keywords in _TEXT_HINTS.items():
        matches = [keyword for keyword in keywords if keyword in text]
        if matches:
            scores[org_type] += min(3.0, 0.8 * len(matches))
            signals.extend(f"text:{keyword}" for keyword in matches[:4])

    if "myflorida.com" in netloc and ("department" in text or "state of florida" in text):
        scores["government"] += 2.5
        signals.append("domain:myflorida-government")

    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return OrganizationProfile("unknown", 0.0, ())

    sorted_scores = sorted(scores.values(), reverse=True)
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    confidence = min(0.99, 0.5 + max(0.0, best_score - runner_up) / 6.0)
    return OrganizationProfile(best_type, confidence, tuple(signals[:6]))


def get_focus_areas_for_org_type(organization_type: str) -> tuple[str, ...]:
    """Return page themes worth prioritizing for the given organization type."""

    focus_map: dict[str, tuple[str, ...]] = {
        "commercial": (
            "products and services",
            "customers and industries served",
            "leadership and company background",
            "pricing, business model, or investor information",
            "case studies, partnerships, and announcements",
        ),
        "government": (
            "mission, mandate, and statutory responsibilities",
            "leadership, divisions, facilities, or programs",
            "budgets, annual reports, audits, or public records",
            "press releases, initiatives, and operational updates",
            "procurement, vendors, or technology modernization signals",
        ),
        "nonprofit": (
            "mission and programs",
            "leadership and governance",
            "impact reports, annual reports, or financial disclosures",
            "partners, chapters, or member services",
            "advocacy priorities and recent announcements",
        ),
        "education": (
            "academic programs and research areas",
            "leadership, departments, and institutional structure",
            "student population, campus footprint, or funding signals",
            "news, grants, and strategic initiatives",
            "technology, partnerships, and public reports",
        ),
        "healthcare": (
            "clinical services and care delivery model",
            "leadership, locations, and specialties",
            "quality, patient experience, and operating footprint",
            "news, partnerships, and technology initiatives",
            "community programs and public filings or reports",
        ),
        "unknown": (
            "mission and overview",
            "leadership and org structure",
            "services, programs, or offerings",
            "news and public updates",
            "reports or evidence of operations",
        ),
    }
    return focus_map.get(organization_type, focus_map["unknown"])
