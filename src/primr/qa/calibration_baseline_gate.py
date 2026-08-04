"""Gate recommendation helpers for calibration baseline artifacts."""

from __future__ import annotations

from typing import Any

GATE_ENV_VAR = "PRIMR_EVAL_MIN_CONFIRMED_TRACEABILITY"
GATE_POLICY = (
    "Do not arm automatically; review the representative pack, measured floor, "
    "disagreement cases, and false-positive risk before setting "
    f"{GATE_ENV_VAR}."
)


def baseline_gate_recommendation(
    *,
    ready: bool,
    reports: list[dict[str, Any]],
    traceability: dict[str, Any],
    evidence: dict[str, Any],
    agreement: dict[str, Any],
    representation: dict[str, Any],
) -> dict[str, Any]:
    """Return the report-only gate recommendation for a calibration baseline."""

    rates = [_optional_rate(report.get("confirmed_traceability")) for report in reports]
    measured_rates = [rate for rate in rates if rate is not None]
    report_count = len(rates)
    missing_confirmed = report_count - len(measured_rates)
    aggregate_confirmed = _optional_rate(
        _dict_value(traceability, "Confirmed").get("traceability_rate")
    )
    base = {
        "environment_variable": GATE_ENV_VAR,
        "recommended_threshold": None,
        "measured_floor": None,
        "aggregate_confirmed_traceability": aggregate_confirmed,
        "reports_total": report_count,
        "reports_considered": len(measured_rates),
        "reports_without_decidable_confirmed": missing_confirmed,
        "confirmed_traceability_floor_complete": missing_confirmed == 0,
        "evidence_source_reviews": _safe_int(evidence.get("source_reviews")),
        "judge_agreement_rate": _optional_rate(agreement.get("agreement_rate")),
        "required_tags": _string_list(representation.get("required_tags")),
        "present_tags": _string_list(representation.get("present_tags")),
        "operator_review_required": True,
        "env_assignment": None,
        "gate_policy": GATE_POLICY,
    }
    if not ready:
        return {"status": "not_recommended", "reason": "baseline_not_ready", **base}
    if not measured_rates:
        return {
            "status": "not_recommended",
            "reason": "no_decidable_confirmed_claims",
            **base,
        }
    if missing_confirmed:
        return {
            "status": "not_recommended",
            "reason": "incomplete_confirmed_traceability_floor",
            **base,
            "measured_floor": round(min(measured_rates), 3),
        }

    measured_floor = min(measured_rates)
    if measured_floor <= 0:
        return {
            "status": "not_recommended",
            "reason": "zero_confirmed_traceability_floor",
            **base,
            "measured_floor": round(measured_floor, 3),
        }

    threshold = round(measured_floor, 3)
    return {
        "status": "candidate",
        "reason": "ready_baseline_measured_floor",
        **base,
        "recommended_threshold": threshold,
        "measured_floor": threshold,
        "env_assignment": f"{GATE_ENV_VAR}={threshold:.3f}",
    }


def inspection_gate_recommendation(
    baseline_recommendation: Any,
    *,
    ready: bool,
) -> dict[str, Any]:
    """Return the gate recommendation visible from baseline inspection."""

    if not isinstance(baseline_recommendation, dict):
        return {
            "status": "not_recommended",
            "reason": "missing_gate_recommendation",
            "environment_variable": GATE_ENV_VAR,
            "operator_review_required": True,
            "gate_policy": GATE_POLICY,
        }
    if ready:
        return dict(baseline_recommendation)
    blocked = dict(baseline_recommendation)
    blocked["status"] = "not_recommended"
    blocked["reason"] = "inspection_not_ready"
    blocked["recommended_threshold"] = None
    blocked["env_assignment"] = None
    blocked["operator_review_required"] = True
    return blocked


def gate_with_report_floor_consistency(
    gate_recommendation: dict[str, Any],
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Downgrade stale candidate gates that no longer match report summaries."""
    if gate_recommendation.get("status") != "candidate":
        return gate_recommendation
    floor = _confirmed_floor_summary(reports)
    expected_threshold = floor["measured_floor"]
    if (
        floor["confirmed_traceability_floor_complete"]
        and expected_threshold is not None
        and _optional_rate(gate_recommendation.get("recommended_threshold")) == expected_threshold
        and _optional_rate(gate_recommendation.get("measured_floor")) == expected_threshold
        and _safe_int(gate_recommendation.get("reports_total")) == floor["reports_total"]
        and _safe_int(gate_recommendation.get("reports_considered")) == floor["reports_considered"]
        and _safe_int(gate_recommendation.get("reports_without_decidable_confirmed"))
        == floor["reports_without_decidable_confirmed"]
    ):
        return gate_recommendation

    blocked = dict(gate_recommendation)
    blocked.update(floor)
    blocked["status"] = "not_recommended"
    blocked["reason"] = "stale_gate_recommendation"
    blocked["recommended_threshold"] = None
    blocked["env_assignment"] = None
    return blocked


def render_gate_recommendation_markdown(gate: dict[str, Any]) -> list[str]:
    """Render the compact Markdown section for a gate recommendation."""

    return [
        "## Gate Recommendation",
        "",
        "| Status | Reason | Threshold | Assignment |",
        "|---|---|---:|---|",
        (
            f"| {gate.get('status', 'not_recommended')} | "
            f"{gate.get('reason', '')} | "
            f"{_percent_or_dash(gate.get('recommended_threshold'))} | "
            f"`{gate.get('env_assignment') or ''}` |"
        ),
        "",
        f"Gate policy: {gate.get('gate_policy', '')}",
    ]


def _dict_value(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key, {})
    return value if isinstance(value, dict) else {}


def _confirmed_floor_summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    rates = [_optional_rate(report.get("confirmed_traceability")) for report in reports]
    measured_rates = [rate for rate in rates if rate is not None]
    reports_total = len(rates)
    reports_without_floor = reports_total - len(measured_rates)
    return {
        "reports_total": reports_total,
        "reports_considered": len(measured_rates),
        "reports_without_decidable_confirmed": reports_without_floor,
        "confirmed_traceability_floor_complete": reports_without_floor == 0,
        "measured_floor": round(min(measured_rates), 3) if measured_rates else None,
    }


def has_decidable_confirmed_floor(report: dict[str, Any]) -> bool:
    """True when Confirmed traceability is a decidable rate (not null / missing)."""
    return _optional_rate(report.get("confirmed_traceability")) is not None


def reports_missing_decidable_confirmed_floor(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Body-free report entries that cannot contribute a Confirmed floor."""
    return [report for report in reports if not has_decidable_confirmed_floor(report)]


def _optional_rate(value: Any) -> float | None:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    if rate < 0 or rate > 1:
        return None
    return round(rate, 3)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _percent_or_dash(value: Any) -> str:
    rate = _optional_rate(value)
    return f"{rate:.0%}" if rate is not None else "-"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
