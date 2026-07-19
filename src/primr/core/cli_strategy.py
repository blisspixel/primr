"""Governed standalone strategy recovery for the CLI."""

from __future__ import annotations

import re
from collections.abc import Callable
from math import isfinite
from pathlib import Path
from typing import Protocol

from primr.core.strategy_estimate import (
    AI_STRATEGY_IDS,
    StandaloneStrategyEstimate,
    estimate_standalone_strategy,
)
from primr.core.trusted_report import (
    ReportSnapshotError as _ReportSnapshotError,
)
from primr.core.trusted_report import (
    TrustedReport as _TrustedReport,
)
from primr.core.trusted_report import stable_report_snapshot, validate_trusted_report
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


class _StrategyConfig(Protocol):
    @property
    def ai_strategy_only_path(self) -> str | None:
        raise NotImplementedError

    @property
    def company_name(self) -> str | None:
        raise NotImplementedError

    @property
    def strategy_type(self) -> str:
        raise NotImplementedError

    @property
    def refresh_vendor_research(self) -> bool:
        raise NotImplementedError

    @property
    def lite_strategy(self) -> bool:
        raise NotImplementedError

    @property
    def budget_usd(self) -> float | None:
        raise NotImplementedError

    @property
    def dry_run_requested(self) -> bool:
        raise NotImplementedError

    @property
    def json_output(self) -> bool:
        raise NotImplementedError

    @property
    def skip_confirm(self) -> bool:
        raise NotImplementedError

    @property
    def output_dir(self) -> str | None:
        raise NotImplementedError

    @property
    def open_after(self) -> bool:
        raise NotImplementedError

    @property
    def cloud_vendors(self) -> tuple[str, ...]:
        raise NotImplementedError


def _resolve_trusted_report(report_path: str) -> _TrustedReport | None:
    """Resolve a regular report beneath a fixed trusted root, or fail closed."""
    try:
        from primr.config.config import OUTPUT_DIR, WORKING_DIR

        return validate_trusted_report(
            report_path,
            allowed_roots=(OUTPUT_DIR, WORKING_DIR),
        )
    except FileNotFoundError:
        console.error(f"Report file not found: {report_path}")
    except _ReportSnapshotError as exc:
        console.error(str(exc))
    except Exception as exc:
        logger.warning("Standalone report validation failed closed: %s", type(exc).__name__)
        console.error("Could not validate the report path. Strategy generation was not started.")
    return None


def _company_name(config: _StrategyConfig, report_path: Path) -> str | None:
    company_name = config.company_name
    if not company_name:
        match = re.match(
            r"^(.+?)_(?:Strategic_Overview|AI_Strategy|Customer_Experience|Security|Data_Fabric)",
            report_path.stem,
        )
        company_name = (
            match.group(1).replace("_", " ") if match else report_path.stem.replace("_", " ")
        )

    from primr.utils.validators import InputValidationError, validate_company_name

    try:
        return validate_company_name(company_name)
    except InputValidationError as exc:
        console.error(f"Invalid company name: {exc.reason}")
        return None


def _emit_estimate(config: _StrategyConfig, estimate: StandaloneStrategyEstimate) -> None:
    payload = estimate.as_dict()
    if config.budget_usd is not None:
        payload["budget_usd"] = config.budget_usd
        payload["within_budget"] = (
            config.budget_usd > 0 and estimate.estimated_cost_usd <= config.budget_usd
        )
    if config.json_output:
        from primr.core.cli_output import emit_json

        emit_json(payload)
        return

    console.header("Standalone Strategy Estimate")
    console.info(f"Strategy: {estimate.strategy_type}")
    console.info(f"Platforms: {', '.join(estimate.platforms)}")
    console.info(f"Model calls: {estimate.strategy_calls}")
    console.info(f"Deep Research tasks: {estimate.deep_research_tasks}")
    if estimate.vendor_refresh_tasks:
        console.info(f"Vendor refresh tasks: {estimate.vendor_refresh_tasks}")
    console.info(f"Estimated cost: ~${estimate.estimated_cost_usd:.2f}")
    console.info(f"Estimated time: {estimate.estimated_time_range}")
    if config.budget_usd is not None:
        state = "within" if payload["within_budget"] else "exceeds"
        console.info(f"Budget: estimate {state} ${config.budget_usd:.2f}")


def handle_ai_strategy_only(
    config: _StrategyConfig,
    *,
    open_result: Callable[[str], None],
    generate_strategy: Callable[..., str | None],
) -> int:
    """Generate a strategy from one validated report after cost governance."""
    if not config.ai_strategy_only_path:
        console.error("Report path is required for --ai-strategy-only")
        console.info(
            'Usage: primr --ai-strategy-only "output/report.md" --strategy-type customer_experience'
        )
        return 1

    report_path = _resolve_trusted_report(config.ai_strategy_only_path)
    if report_path is None:
        return 1

    company_name = _company_name(config, report_path.path)
    if company_name is None:
        return 1

    strategy_type = config.strategy_type
    platforms = config.cloud_vendors if strategy_type in AI_STRATEGY_IDS else ("agnostic",)
    from primr.core.vendor_research import vendor_auto_refresh_enabled

    refresh_enabled = config.refresh_vendor_research or vendor_auto_refresh_enabled()
    try:
        estimate = estimate_standalone_strategy(
            strategy_type,
            platforms=platforms,
            lite_strategy=config.lite_strategy,
            refresh_vendor_research=refresh_enabled,
        )
    except ValueError as exc:
        console.error(str(exc))
        return 1

    if config.budget_usd is not None and (
        not isfinite(config.budget_usd) or config.budget_usd <= 0
    ):
        console.error(f"--budget must be a finite positive number, got {config.budget_usd}")
        return 1

    if config.dry_run_requested:
        _emit_estimate(config, estimate)
        return 0

    if config.budget_usd is not None:
        if estimate.estimated_cost_usd > config.budget_usd:
            console.error(
                f"Estimated cost ${estimate.estimated_cost_usd:.2f} exceeds "
                f"--budget ${config.budget_usd:.2f}. Not starting."
            )
            return 1

    _emit_estimate(config, estimate)
    if not config.skip_confirm:
        response = input("Proceed with standalone strategy generation? [y/N] ").strip().lower()
        if response not in {"y", "yes"}:
            console.info("Cancelled. No model calls were started.")
            return 0
        approval_source = "interactive"
    else:
        approval_source = "--skip-confirm"

    logger.info(
        "Standalone strategy approved: type=%s calls=%d estimated_cost_usd=%.6f approval=%s",
        estimate.strategy_type,
        estimate.strategy_calls,
        estimate.estimated_cost_usd,
        approval_source,
    )

    names = {
        "ai": "AI Strategy",
        "ai_strategy": "AI Strategy",
        "customer_experience": "Customer Experience Strategy",
        "modern_security_compliance": "Security & Compliance Strategy",
        "data_fabric_strategy": "Data Fabric Strategy",
    }
    display_name = names.get(strategy_type, strategy_type)
    console.banner(f"{display_name} Generation")
    console.info(f"Company: {company_name}")
    console.info(f"Context: {report_path.path.name}")
    if strategy_type in AI_STRATEGY_IDS:
        console.info(f"Platforms: {', '.join(platform.upper() for platform in platforms)}")
    console.blank()

    result_paths: list[str] = []
    diagnostics_dir = Path(config.output_dir) / "_diagnostics" if config.output_dir else None
    runtime_strategy_type = "ai" if strategy_type == "ai_strategy" else strategy_type
    from primr.config.config import WORKING_DIR
    from primr.core.workspace import (
        ActiveRunLeaseError,
        ResumeLeaseError,
        company_run_lease_for_target,
    )

    try:
        with (
            company_run_lease_for_target(
                company_name,
                None,
                base_dir=WORKING_DIR,
            ) as company_root,
            stable_report_snapshot(report_path, company_root) as snapshot_path,
        ):
            for platform in platforms:
                result = generate_strategy(
                    strategy_name=runtime_strategy_type,
                    company_name=company_name,
                    platform=platform,
                    company_research_path=str(snapshot_path),
                    force_refresh_vendor=config.refresh_vendor_research,
                    discovery_notes_content=None,
                    lite_strategy=config.lite_strategy,
                    output_dir=config.output_dir,
                    diagnostics_dir=diagnostics_dir,
                    write_txt=config.output_dir is None,
                )
                if result:
                    label = f" ({platform.upper()})" if len(platforms) > 1 else ""
                    console.blank()
                    console.success_box(f"{display_name}{label} generated", result)
                    result_paths.append(result)
    except ActiveRunLeaseError:
        console.error(
            "Another active run is publishing artifacts for this company. "
            "Wait for it to finish, then retry."
        )
        return 1
    except ResumeLeaseError:
        console.error(
            "Could not safely claim this company workspace. "
            "Inspect its ownership record before retrying."
        )
        return 1
    except _ReportSnapshotError:
        console.error("The report changed after validation. Strategy generation was not started.")
        return 1

    if not result_paths:
        console.error(f"{display_name} generation failed")
        return 1
    if config.open_after:
        open_result(result_paths[-1])
    return 0


__all__ = ["handle_ai_strategy_only"]
