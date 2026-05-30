"""Industry / business-model classification for the planning step.

Resolution order, cheapest first:

1. ``classify_from_report(report_text)`` — when a primr strategic report
   already exposes industry / business model / stage in recognizable
   fields, use those directly. No LLM call.
2. ``classify_via_llm(...)`` — a single cheap LLM call against recon +
   hiring + research evidence. This is the workhorse.

The output `IndustryClassification` flows into the plausible-roles prompt
so inference can gate which common-org-shape roles (Marketing, Sales,
Customer Success, etc.) are reasonable for this company at this stage.

This module has no LLM imports at module load — the LLM path is imported
lazily inside ``classify_via_llm`` so unit tests can exercise the
report-derived path without provider keys.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

from primr.skill_pack.schema import IndustryClassification

# =============================================================================
# Report-derived classifier
# =============================================================================

_REPORT_INDUSTRY_HINT = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*|[-*]\s*\**)?industry[^:\n]*:\s*\**\s*([^\n*]+)",
    re.IGNORECASE,
)
_REPORT_MODEL_HINT = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*|[-*]\s*\**)?business\s+model[^:\n]*:\s*\**\s*([^\n*]+)",
    re.IGNORECASE,
)
_REPORT_STAGE_HINT = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*|[-*]\s*\**)?(?:company\s+)?stage[^:\n]*:\s*\**\s*([^\n*]+)",
    re.IGNORECASE,
)
_REPORT_EMPLOYEE_HINT = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*|[-*]\s*\**)?(?:employees?|headcount)[^:\n]*:\s*\**\s*([^\n*]+)",
    re.IGNORECASE,
)


def classify_from_report(report_text: str) -> IndustryClassification | None:
    """Pull a classification straight from a primr strategic report when
    one is available. Returns None when the report does not expose the
    fields in a recognizable form — callers fall through to the LLM path.
    """
    if not report_text or len(report_text) < 200:
        return None

    industry_match = _REPORT_INDUSTRY_HINT.search(report_text)
    model_match = _REPORT_MODEL_HINT.search(report_text)
    stage_match = _REPORT_STAGE_HINT.search(report_text)
    employee_match = _REPORT_EMPLOYEE_HINT.search(report_text)

    if not any((industry_match, model_match, stage_match, employee_match)):
        return None

    industry = industry_match.group(1).strip() if industry_match else "Unknown"
    model = model_match.group(1).strip() if model_match else "Unknown"
    stage = stage_match.group(1).strip() if stage_match else "Unknown"
    employees = employee_match.group(1).strip() if employee_match else "Unknown"

    citations: list[str] = []
    for label, match in (
        ("industry", industry_match),
        ("business_model", model_match),
        ("stage", stage_match),
        ("employees", employee_match),
    ):
        if match is not None:
            snippet = match.group(0).strip()
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            citations.append(f"report:{label}: {snippet}")

    # Confidence reflects how many of the four fields the report yielded.
    matched_fields = sum(
        1 for m in (industry_match, model_match, stage_match, employee_match)
        if m is not None
    )
    if matched_fields >= 3:
        confidence = "High"
    elif matched_fields == 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    return IndustryClassification(
        business_model=model,
        industry_vertical=industry,
        company_stage=stage,
        employee_estimate=employees,
        confidence=confidence,
        cited_evidence=citations,
        source="report",
    )


# =============================================================================
# LLM classifier
# =============================================================================


def _strip_json_fence(raw: str) -> str:
    """Return JSON content stripped of any markdown code fence."""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1)
    obj = re.search(r"(\{.*\})", raw, re.DOTALL)
    if obj:
        return obj.group(1)
    return raw.strip()


def classify_via_llm(
    company_name: str,
    recon_text: str,
    hiring_text: str,
    research_text: str = "",
) -> IndustryClassification | None:
    """LLM-driven classification. Returns None on any failure so the
    caller can fall through to whatever default the orchestrator chose.

    Uses a small reasoning-light model — the schema is constrained and the
    decision is shallow. ~$0.005 per call.
    """
    try:
        from primr.ai.grok_client import grok_llm
    except Exception:
        return None

    inputs_present = [
        ("Recon evidence", recon_text.strip()),
        ("Hiring evidence", hiring_text.strip()),
        ("Research evidence", research_text.strip()),
    ]
    blocks = [f"{label}:\n{text[:3000]}" for label, text in inputs_present if text]
    if not blocks:
        return None
    inputs_blob = "\n\n".join(blocks)

    prompt = (
        "Classify the company below into a coarse industry profile. Pick the "
        "single best label for each field; do not hedge or list alternates. "
        "Cite up to 8 verbatim phrases from the inputs that justify the "
        "classification. Return ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "business_model": "B2B SaaS | Services / Reseller | Marketplace | '
        'Hardware / OEM | Regulated Finance | Healthcare | Government / '
        'Public Sector | Education | Media | Other",\n'
        '  "industry_vertical": "<short label, e.g. Cybersecurity, Logistics, '
        'HR Tech, FinTech, Cloud Reseller, Education Tech>",\n'
        '  "company_stage": "Early / Series A-C | Growth / Late-stage | '
        'PE-backed | Public / Mature | Mature / Private | Unknown",\n'
        '  "employee_estimate": "Small (<50) | Early (50-500) | Mid-market '
        '(500-5000) | Enterprise (5000+) | Unknown",\n'
        '  "confidence": "High | Medium | Low",\n'
        '  "cited_evidence": ["<verbatim phrase>", ...]\n'
        "}\n\n"
        f"Company: {company_name}\n\n"
        f"{inputs_blob}\n"
    )
    try:
        raw = grok_llm(
            prompt,
            model="grok-4.20-non-reasoning",
            temperature=0.1,
            max_tokens=1_000,
            retries=1,
        )
    except Exception:
        return None

    try:
        parsed = json.loads(_strip_json_fence(raw))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None

    cited = parsed.get("cited_evidence") or []
    if not isinstance(cited, list):
        cited = []
    return IndustryClassification(
        business_model=str(parsed.get("business_model") or "Unknown").strip() or "Unknown",
        industry_vertical=str(parsed.get("industry_vertical") or "Unknown").strip() or "Unknown",
        company_stage=str(parsed.get("company_stage") or "Unknown").strip() or "Unknown",
        employee_estimate=str(parsed.get("employee_estimate") or "Unknown").strip() or "Unknown",
        confidence=str(parsed.get("confidence") or "Low").strip() or "Low",
        cited_evidence=[str(c).strip() for c in cited if str(c).strip()][:8],
        source="llm",
    )


# =============================================================================
# Orchestrator
# =============================================================================


def classify_industry(
    *,
    company_name: str,
    recon_text: str,
    hiring_text: str,
    research_text: str = "",
    report_text: str = "",
) -> IndustryClassification:
    """Resolve the company's industry classification.

    Order:
      1. Parse structured fields from a primr strategic report when one
         is supplied and exposes them.
      2. Single LLM call against recon + hiring + research evidence.

    The returned object always carries a `source` field so role_plan.md
    can show where the classification came from. When every path fails
    (no inputs available, LLM unreachable, parse error), an Unknown
    placeholder is returned and downstream plausible-roles inference
    narrows itself accordingly.
    """
    if report_text:
        from_report = classify_from_report(report_text)
        if from_report is not None and from_report.confidence in ("High", "Medium"):
            return from_report

    llm = classify_via_llm(company_name, recon_text, hiring_text, research_text)
    if llm is not None:
        return llm

    # Both paths failed (typically: no report, LLM unreachable, or empty
    # evidence). Return an Unknown placeholder so the planner downstream
    # can still proceed with a narrowed inference budget.
    return replace(
        IndustryClassification(),
        source="unavailable",
    )


__all__ = [
    "classify_from_report",
    "classify_industry",
    "classify_via_llm",
]
