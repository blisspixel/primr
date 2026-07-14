"""Admission and approval binding for operator-supplied role plans.

Saved plans cross a trust boundary: callers may hand-edit the JSON and MCP
clients may point at any file admitted by the server's path policy. This module
therefore owns bounded reads, strict structural validation, prompt-size limits,
and the canonical digest shared by estimation and execution.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from primr.skill_pack.config import MAX_ROLES
from primr.skill_pack.curation import apply_curation
from primr.skill_pack.schema import (
    IndustryClassification,
    Role,
    RoleEvidence,
    RolePlan,
    RoleProvenance,
)
from primr.skill_pack.validator import validate_kebab_case

MAX_SAVED_PLAN_BYTES = 1_000_000
MAX_SAVED_PLAN_PROMPT_CHARS = 64_000
MAX_SAVED_PLAN_ROLE_LIST_ITEMS = 100
MAX_SAVED_PLAN_EVIDENCE_ITEMS = 32


class SavedPlanValidationError(RuntimeError):
    """A sanitized validation failure for an operator-supplied role plan."""


def _saved_plan_error(field: str, requirement: str) -> SavedPlanValidationError:
    return SavedPlanValidationError(f"Saved role plan field '{field}' must {requirement}.")


def _saved_plan_text(
    value: object,
    field: str,
    *,
    limit: int,
    default: str = "",
    allow_none: bool = False,
) -> str | None:
    if value is None:
        return None if allow_none else default
    if not isinstance(value, str):
        raise _saved_plan_error(field, "be text")
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise _saved_plan_error(field, f"contain at most {limit} characters")
    return cleaned


def _saved_plan_text_list(
    value: object,
    field: str,
    *,
    item_limit: int,
    max_items: int = MAX_SAVED_PLAN_EVIDENCE_ITEMS,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise _saved_plan_error(field, "be a list")
    if len(value) > max_items:
        raise _saved_plan_error(field, f"contain at most {max_items} entries")
    return [
        str(_saved_plan_text(item, f"{field}[{index}]", limit=item_limit))
        for index, item in enumerate(value)
    ]


def _saved_plan_role_list(data: dict[str, Any], field: str) -> list[object]:
    value = data.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise _saved_plan_error(field, "be a list")
    if len(value) > MAX_SAVED_PLAN_ROLE_LIST_ITEMS:
        raise _saved_plan_error(
            field,
            f"contain at most {MAX_SAVED_PLAN_ROLE_LIST_ITEMS} roles",
        )
    return value


def _role_approval_dict(role: Role) -> dict[str, Any]:
    return {
        "name": role.name,
        "display_name": role.display_name,
        "confidence": role.confidence,
        "summary": role.summary,
        "evidence": {
            "sources": list(role.evidence.sources),
            "dns_signals": list(role.evidence.dns_signals),
            "posting_count": role.evidence.posting_count,
            "archetype": role.evidence.archetype,
            "provenance": role.evidence.provenance.value,
            "citations": list(role.evidence.citations),
        },
    }


def saved_plan_approval_basis(plan: RolePlan) -> tuple[str, int]:
    """Return a stable digest and bounded authoring-text size for one plan."""
    approval_data = {
        "final_roster": [_role_approval_dict(role) for role in plan.final_roster],
        "industry": plan.industry.to_dict(),
    }
    canonical = json.dumps(
        approval_data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    prompt_chars = len(canonical)
    if prompt_chars > MAX_SAVED_PLAN_PROMPT_CHARS:
        raise SavedPlanValidationError(
            "Saved role plan authoring content exceeds the "
            f"{MAX_SAVED_PLAN_PROMPT_CHARS}-character limit."
        )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), prompt_chars


def load_plan(json_path: Path) -> RolePlan:
    """Load and strictly validate a previously persisted role plan."""
    try:
        with json_path.open("rb") as handle:
            raw_bytes = handle.read(MAX_SAVED_PLAN_BYTES + 1)
    except OSError as exc:
        raise RuntimeError(f"Could not read role plan at {json_path}: {exc}") from exc
    if len(raw_bytes) > MAX_SAVED_PLAN_BYTES:
        raise SavedPlanValidationError(
            f"Saved role plan exceeds the {MAX_SAVED_PLAN_BYTES}-byte input limit."
        )
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SavedPlanValidationError("Saved role plan is not valid UTF-8.") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SavedPlanValidationError("Saved role plan is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise SavedPlanValidationError("Saved role plan must be a JSON object.")

    role_lists = {
        field: _saved_plan_role_list(data, field)
        for field in ("observed", "plausible", "gap_flagged", "operator_added", "final_roster")
    }
    if len(role_lists["final_roster"]) > MAX_ROLES:
        raise SavedPlanValidationError(
            f"Saved role plan final_roster may contain at most {MAX_ROLES} roles."
        )

    def _hydrate_role(entry: object, field: str) -> Role:
        if not isinstance(entry, dict):
            raise _saved_plan_error(field, "be an object")
        evidence_raw = entry.get("evidence")
        if evidence_raw is None:
            evidence_raw = {}
        if not isinstance(evidence_raw, dict):
            raise _saved_plan_error(f"{field}.evidence", "be an object")

        provenance_raw = _saved_plan_text(
            evidence_raw.get("provenance"),
            f"{field}.evidence.provenance",
            limit=20,
            default=RoleProvenance.POSTING.value,
        )
        assert provenance_raw is not None
        try:
            provenance = RoleProvenance(provenance_raw.lower())
        except ValueError as exc:
            raise _saved_plan_error(
                f"{field}.evidence.provenance",
                "name a supported provenance",
            ) from exc

        posting_count = evidence_raw.get("posting_count", 0)
        if (
            isinstance(posting_count, bool)
            or not isinstance(posting_count, int)
            or posting_count < 0
            or posting_count > 1_000_000
        ):
            raise _saved_plan_error(
                f"{field}.evidence.posting_count",
                "be an integer from 0 through 1000000",
            )

        name = _saved_plan_text(entry.get("name"), f"{field}.name", limit=80)
        display_name = _saved_plan_text(
            entry.get("display_name"),
            f"{field}.display_name",
            limit=120,
        )
        if not name:
            raise _saved_plan_error(f"{field}.name", "not be empty")
        if not validate_kebab_case(name):
            raise _saved_plan_error(
                f"{field}.name",
                "be a portable kebab-case identifier",
            )
        if not display_name:
            raise _saved_plan_error(f"{field}.display_name", "not be empty")

        return Role(
            name=name,
            display_name=display_name,
            confidence=str(
                _saved_plan_text(
                    entry.get("confidence"),
                    f"{field}.confidence",
                    limit=40,
                    default="Inferred",
                )
            ),
            summary=str(
                _saved_plan_text(
                    entry.get("summary"),
                    f"{field}.summary",
                    limit=2_000,
                )
            ),
            evidence=RoleEvidence(
                sources=_saved_plan_text_list(
                    evidence_raw.get("sources"),
                    f"{field}.evidence.sources",
                    item_limit=1_000,
                ),
                dns_signals=_saved_plan_text_list(
                    evidence_raw.get("dns_signals"),
                    f"{field}.evidence.dns_signals",
                    item_limit=1_000,
                ),
                posting_count=posting_count,
                archetype=_saved_plan_text(
                    evidence_raw.get("archetype"),
                    f"{field}.evidence.archetype",
                    limit=120,
                    allow_none=True,
                ),
                provenance=provenance,
                citations=_saved_plan_text_list(
                    evidence_raw.get("citations"),
                    f"{field}.evidence.citations",
                    item_limit=2_000,
                ),
            ),
        )

    industry_raw = data.get("industry")
    if industry_raw is None:
        industry_raw = {}
    if not isinstance(industry_raw, dict):
        raise _saved_plan_error("industry", "be an object")
    industry = IndustryClassification(
        business_model=str(
            _saved_plan_text(
                industry_raw.get("business_model"),
                "industry.business_model",
                limit=1_000,
                default="Unknown",
            )
        ),
        industry_vertical=str(
            _saved_plan_text(
                industry_raw.get("industry_vertical"),
                "industry.industry_vertical",
                limit=1_000,
                default="Unknown",
            )
        ),
        company_stage=str(
            _saved_plan_text(
                industry_raw.get("company_stage"),
                "industry.company_stage",
                limit=1_000,
                default="Unknown",
            )
        ),
        employee_estimate=str(
            _saved_plan_text(
                industry_raw.get("employee_estimate"),
                "industry.employee_estimate",
                limit=1_000,
                default="Unknown",
            )
        ),
        confidence=str(
            _saved_plan_text(
                industry_raw.get("confidence"),
                "industry.confidence",
                limit=40,
                default="Low",
            )
        ),
        cited_evidence=_saved_plan_text_list(
            industry_raw.get("cited_evidence"),
            "industry.cited_evidence",
            item_limit=2_000,
        ),
        source=str(
            _saved_plan_text(
                industry_raw.get("source"),
                "industry.source",
                limit=80,
                default="loaded",
            )
        ),
    )

    evidence_summary = data.get("evidence_summary")
    if evidence_summary is None:
        evidence_summary = {}
    if not isinstance(evidence_summary, dict):
        raise _saved_plan_error("evidence_summary", "be an object")

    def _hydrate_list(field: str) -> list[Role]:
        return [
            _hydrate_role(entry, f"{field}[{index}]")
            for index, entry in enumerate(role_lists[field])
        ]

    plan = RolePlan(
        observed=_hydrate_list("observed"),
        plausible=_hydrate_list("plausible"),
        gap_flagged=_hydrate_list("gap_flagged"),
        operator_added=_hydrate_list("operator_added"),
        operator_skipped=_saved_plan_text_list(
            data.get("operator_skipped"),
            "operator_skipped",
            item_limit=80,
            max_items=MAX_SAVED_PLAN_ROLE_LIST_ITEMS,
        ),
        final_roster=_hydrate_list("final_roster"),
        industry=industry,
        evidence_summary=dict(evidence_summary),
        plan_md_path=_saved_plan_text(
            data.get("plan_md_path"),
            "plan_md_path",
            limit=4_096,
            allow_none=True,
        ),
        plan_json_path=str(json_path),
    )
    saved_plan_approval_basis(plan)
    return plan


def prepare_saved_plan(
    json_path: Path,
    *,
    roles_add: list[str] | None = None,
    roles_skip: list[str] | None = None,
) -> RolePlan:
    """Load and deterministically curate one saved-plan execution snapshot."""
    plan = load_plan(json_path)
    if roles_add or roles_skip:
        apply_curation(
            plan,
            roles_add=list(roles_add or []),
            roles_skip=list(roles_skip or []),
            cap=MAX_ROLES,
        )
    if not plan.final_roster:
        raise SavedPlanValidationError(
            "Saved role plan has an empty final_roster; there is nothing to author."
        )
    saved_plan_approval_basis(plan)
    return plan


__all__ = [
    "MAX_SAVED_PLAN_BYTES",
    "MAX_SAVED_PLAN_PROMPT_CHARS",
    "SavedPlanValidationError",
    "load_plan",
    "prepare_saved_plan",
    "saved_plan_approval_basis",
]
