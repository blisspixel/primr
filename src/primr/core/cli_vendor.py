"""Cost-governed direct vendor-research cache generation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from primr.config.models import DEEP_RESEARCH_COST
from primr.core.cli_contract import CLIConfig
from primr.utils.console import get_console
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class VendorResearchEstimate:
    """Planning estimate for an exact direct cache-generation fan-out."""

    vendors: tuple[str, ...]
    task_count: int
    estimated_cost_usd: float
    estimated_time_min_minutes: int
    estimated_time_max_minutes: int

    @property
    def estimated_time_range(self) -> str:
        return f"{self.estimated_time_min_minutes}-{self.estimated_time_max_minutes} min"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "primr.vendor-research-estimate.v1",
            "operation": "vendor_research_generation",
            "vendors": list(self.vendors),
            "deep_research_tasks": self.task_count,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_time_minutes": self.estimated_time_max_minutes,
            "estimated_time_range": self.estimated_time_range,
            "cost_basis": (
                "Conservative planning estimate using the configured flat cost "
                "for each sequential Deep Research task; actual provider usage varies."
            ),
        }


def estimate_vendor_research(vendors: tuple[str, ...]) -> VendorResearchEstimate:
    """Return the deterministic aggregate estimate for selected vendors."""

    task_count = len(vendors)
    return VendorResearchEstimate(
        vendors=vendors,
        task_count=task_count,
        estimated_cost_usd=round(task_count * DEEP_RESEARCH_COST.standard_task_cost, 6),
        estimated_time_min_minutes=task_count * 5,
        estimated_time_max_minutes=task_count * 10,
    )


def _selected_vendors(value: str | None) -> tuple[str, ...]:
    if value == "all":
        return ("azure", "aws", "gcp", "private", "agnostic")
    return (value,) if value else ()


def _estimate_payload(
    estimate: VendorResearchEstimate,
    *,
    budget_usd: float | None,
) -> dict[str, object]:
    payload = estimate.as_dict()
    if budget_usd is not None:
        payload["budget_usd"] = budget_usd if isfinite(budget_usd) else None
        payload["within_budget"] = (
            isfinite(budget_usd) and budget_usd > 0 and estimate.estimated_cost_usd <= budget_usd
        )
    return payload


def _emit_estimate(config: CLIConfig, estimate: VendorResearchEstimate) -> None:
    payload = _estimate_payload(estimate, budget_usd=config.budget_usd)
    if config.json_output:
        from primr.core.cli_command_output import emit_json

        payload["dry_run"] = True
        emit_json(payload)
        return

    get_console().header("Vendor Research Estimate")
    get_console().info(f"Vendors: {', '.join(estimate.vendors)}")
    get_console().info(f"Deep Research tasks: {estimate.task_count}")
    get_console().info(f"Estimated cost: ~${estimate.estimated_cost_usd:.2f}")
    get_console().info(f"Estimated time: {estimate.estimated_time_range}")
    if config.budget_usd is not None:
        state = "within" if payload["within_budget"] else "exceeds"
        get_console().info(f"Budget: estimate {state} ${config.budget_usd:.2f}")


def _report_error(
    config: CLIConfig,
    estimate: VendorResearchEstimate | None,
    *,
    error_type: str,
    message: str,
    hints: tuple[str, ...] = (),
) -> int:
    if config.json_output:
        from primr.core.cli_command_output import emit_json

        payload: dict[str, object] = {
            "schema_version": "primr.vendor-research-command.v1",
            "operation": "vendor_research_generation",
            "status": "not_started",
            "error": True,
            "error_type": error_type,
            "message": message,
        }
        if estimate is not None:
            payload["estimate"] = _estimate_payload(
                estimate,
                budget_usd=config.budget_usd,
            )
        if hints:
            payload["hints"] = list(hints)
        emit_json(payload)
        return 1

    get_console().error(message)
    for hint in hints:
        get_console().info(hint)
    return 1


def run_generate_vendor(config: CLIConfig) -> int:
    """Generate vendor research only after estimate, budget, and approval gates."""

    vendors = _selected_vendors(config.generate_vendor)
    if not vendors:
        return _report_error(
            config,
            None,
            error_type="missing_vendor",
            message="A vendor is required for direct vendor research generation.",
        )
    estimate = estimate_vendor_research(vendors)

    if config.budget_usd is not None and (
        not isfinite(config.budget_usd) or config.budget_usd <= 0
    ):
        return _report_error(
            config,
            estimate,
            error_type="invalid_budget",
            message=f"--budget must be a finite positive number, got {config.budget_usd}",
        )
    if config.dry_run_requested:
        _emit_estimate(config, estimate)
        return 0
    if config.budget_usd is not None and estimate.estimated_cost_usd > config.budget_usd:
        return _report_error(
            config,
            estimate,
            error_type="budget_exceeded",
            message=(
                f"Estimated cost ${estimate.estimated_cost_usd:.2f} exceeds "
                f"--budget ${config.budget_usd:.2f}. Not starting."
            ),
        )

    from primr.core.vendor_research import _validate_vendor_research_preflight

    preflight_errors = tuple(
        dict.fromkeys(
            error for vendor in vendors for error in _validate_vendor_research_preflight(vendor)
        )
    )
    if preflight_errors:
        return _report_error(
            config,
            estimate,
            error_type="preflight_failed",
            message="Vendor research preflight failed. No provider tasks were started.",
            hints=preflight_errors,
        )
    if config.json_output and not config.skip_confirm:
        return _report_error(
            config,
            estimate,
            error_type="approval_required",
            message="Execution requires explicit approval. Re-run with --skip-confirm.",
            hints=("Use --dry-run --json to inspect the estimate without execution.",),
        )

    if not config.json_output:
        _emit_estimate(config, estimate)
    approval_source = "--skip-confirm"
    if not config.skip_confirm:
        from primr.core.cli_init import _prompt_yes_no

        approved = _prompt_yes_no(
            f"Start {estimate.task_count} Deep Research task(s) for "
            f"~${estimate.estimated_cost_usd:.2f}?",
            default=False,
        )
        if not approved:
            get_console().info("Cancelled. No provider tasks were started.")
            return 0
        approval_source = "interactive"

    logger.info(
        "Vendor research approved: tasks=%d estimated_cost_usd=%.6f approval=%s",
        estimate.task_count,
        estimate.estimated_cost_usd,
        approval_source,
    )
    from primr.core.vendor_research import generate_vendor_research_sync

    if not config.json_output:
        get_console().banner("Vendor AI Research Generation")
    artifacts: list[dict[str, str]] = []
    failed_vendors: list[str] = []
    for vendor in vendors:
        if not config.json_output:
            get_console().step(f"Generating {vendor.upper()} research")
        try:
            result = generate_vendor_research_sync(
                vendor,
                emit_console=not config.json_output,
            )
        except Exception as exc:
            logger.error("Vendor research command failed (%s)", type(exc).__name__)
            result = None
        if result:
            path = str(result)
            artifacts.append({"vendor": vendor, "path": path})
            if not config.json_output:
                get_console().ok(f"Saved: {path}")
        else:
            failed_vendors.append(vendor)
            if not config.json_output:
                get_console().error(f"Failed to generate {vendor} research")

    if config.json_output:
        from primr.core.cli_command_output import emit_json

        status = "completed" if not failed_vendors else "partial" if artifacts else "failed"
        emit_json(
            {
                "schema_version": "primr.vendor-research-result.v1",
                "operation": "vendor_research_generation",
                "status": status,
                "error": bool(failed_vendors),
                "estimate": _estimate_payload(estimate, budget_usd=config.budget_usd),
                "artifacts": artifacts,
                "failed_vendors": failed_vendors,
            }
        )
    return 1 if failed_vendors else 0
