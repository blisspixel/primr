"""Governed standalone strategy recovery for the CLI."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from contextlib import redirect_stdout
from math import isfinite
from pathlib import Path
from typing import Protocol

from primr.core.strategy_estimate import (
    AI_STRATEGY_IDS,
    StandaloneStrategyEstimate,
    estimate_standalone_strategy,
)
from primr.core.strategy_outcome import strategy_target
from primr.core.trusted_report import (
    ReportSnapshotError as _ReportSnapshotError,
)
from primr.core.trusted_report import (
    TrustedReport as _TrustedReport,
)
from primr.core.trusted_report import stable_report_snapshot, validate_trusted_report
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.run_budget import (
    clear_run_budget,
    get_run_budget,
    observed_session_spend,
    set_run_budget,
    skip_stage_if_over_budget,
)
from primr.utils.terminal import can_prompt_for_input

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
    def deep_research_strategy(self) -> bool:
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
    except (FileNotFoundError, _ReportSnapshotError):
        return None
    except Exception as exc:
        logger.warning("Standalone report validation failed closed: %s", type(exc).__name__)
    return None


def _company_name(
    config: _StrategyConfig,
    report_path: Path,
) -> str | None:
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
    except InputValidationError:
        return None


def _estimate_payload(
    config: _StrategyConfig,
    estimate: StandaloneStrategyEstimate,
) -> dict[str, object]:
    payload = estimate.as_dict()
    if config.budget_usd is not None:
        payload["budget_usd"] = config.budget_usd if isfinite(config.budget_usd) else None
        payload["within_budget"] = (
            isfinite(config.budget_usd)
            and config.budget_usd > 0
            and estimate.estimated_cost_usd <= config.budget_usd
        )
    return payload


def _emit_estimate(config: _StrategyConfig, estimate: StandaloneStrategyEstimate) -> None:
    payload = _estimate_payload(config, estimate)
    if config.json_output:
        from primr.core.cli_command_output import emit_json

        payload["dry_run"] = True
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


def _report_error(
    config: _StrategyConfig,
    estimate: StandaloneStrategyEstimate | None,
    *,
    error_type: str,
    message: str,
    hints: tuple[str, ...] = (),
) -> int:
    if config.json_output:
        from primr.core.cli_command_output import emit_json

        payload: dict[str, object] = {
            "schema_version": "primr.strategy-command.v1",
            "operation": "standalone_strategy_generation",
            "status": "not_started",
            "error": True,
            "error_type": error_type,
            "message": message,
        }
        if estimate is not None:
            payload["estimate"] = _estimate_payload(config, estimate)
        if hints:
            payload["hints"] = list(hints)
        emit_json(payload)
        return 1

    console.error(message)
    for hint in hints:
        console.info(hint)
    return 1


def _strategy_display_name(strategy_type: str) -> str:
    names = {
        "ai": "AI Strategy",
        "ai_strategy": "AI Strategy",
        "customer_experience": "Customer Experience Strategy",
        "modern_security_compliance": "Security & Compliance Strategy",
        "data_fabric_strategy": "Data Fabric Strategy",
    }
    return names.get(strategy_type, strategy_type.replace("_", " ").title())


def _generate_one_target(
    generate_strategy: Callable[..., str | None],
    *,
    json_output: bool,
    arguments: dict[str, object],
) -> str | None:
    """Call one strategy target while preserving the one-object JSON contract."""

    if not json_output:
        return generate_strategy(**arguments)
    with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink):
        return generate_strategy(**arguments)


def _generate_strategy_targets(
    config: _StrategyConfig,
    *,
    snapshot_path: Path,
    company_name: str,
    platforms: tuple[str, ...],
    runtime_strategy_type: str,
    display_name: str,
    generate_strategy: Callable[..., str | None],
    lite_strategy: bool,
    estimated_cost_per_target: float = 0.0,
) -> tuple[list[dict[str, str]], list[str]]:
    artifacts: list[dict[str, str]] = []
    failed_targets: list[str] = []
    diagnostics_dir = Path(config.output_dir) / "_diagnostics" if config.output_dir else None
    spent = 0.0
    for platform in platforms:
        target = strategy_target(runtime_strategy_type, platform)
        if skip_stage_if_over_budget(spent, f"{display_name} ({target})"):
            failed_targets.append(target)
            continue
        arguments: dict[str, object] = {
            "strategy_name": runtime_strategy_type,
            "company_name": company_name,
            "platform": platform,
            "company_research_path": str(snapshot_path),
            "force_refresh_vendor": config.refresh_vendor_research,
            "discovery_notes_content": None,
            "lite_strategy": lite_strategy,
            "output_dir": config.output_dir,
            "diagnostics_dir": diagnostics_dir,
            "write_txt": config.output_dir is None,
        }
        try:
            result = _generate_one_target(
                generate_strategy,
                json_output=config.json_output,
                arguments=arguments,
            )
        except Exception as exc:
            logger.error(
                "Standalone strategy target failed: target=%s failure_type=%s",
                target,
                type(exc).__name__,
            )
            result = None
        if result:
            path = str(result)
            artifacts.append({"target": target, "platform": platform, "path": path})
            if not config.json_output:
                label = f" ({platform.upper()})" if len(platforms) > 1 else ""
                console.blank()
                console.success_box(f"{display_name}{label} generated", path)
        else:
            failed_targets.append(target)
            if not config.json_output:
                console.error(f"{display_name} target {target} failed")
        spent += max(0.0, estimated_cost_per_target)
        if get_run_budget() is not None:
            try:
                spent = max(spent, observed_session_spend())
            except Exception:
                logger.debug(
                    "Could not fold session LLM spend into strategy budget",
                    exc_info=True,
                )
    return artifacts, failed_targets


def _emit_strategy_result(
    config: _StrategyConfig,
    estimate: StandaloneStrategyEstimate,
    *,
    expected_targets: tuple[str, ...],
    artifacts: list[dict[str, str]],
    failed_targets: list[str],
) -> None:
    from primr.core.cli_command_output import emit_json

    status = "completed" if not failed_targets else "partial" if artifacts else "failed"
    emit_json(
        {
            "schema_version": "primr.strategy-result.v1",
            "operation": "standalone_strategy_generation",
            "status": status,
            "error": bool(failed_targets),
            "estimate": _estimate_payload(config, estimate),
            "strategy_type": estimate.strategy_type,
            "expected_targets": list(expected_targets),
            "artifacts": artifacts,
            "failed_targets": failed_targets,
        }
    )


def handle_ai_strategy_only(
    config: _StrategyConfig,
    *,
    open_result: Callable[[str], None],
    generate_strategy: Callable[..., str | None],
) -> int:
    """Generate a strategy from one validated report after cost governance."""
    if not config.ai_strategy_only_path:
        return _report_error(
            config,
            None,
            error_type="missing_report",
            message="Report path is required for --ai-strategy-only.",
            hints=(
                'Usage: primr --ai-strategy-only "output/report.md" '
                "--strategy-type customer_experience",
            ),
        )

    report_path = _resolve_trusted_report(config.ai_strategy_only_path)
    if report_path is None:
        return _report_error(
            config,
            None,
            error_type="invalid_report",
            message="The report path could not be validated. Strategy generation was not started.",
        )

    company_name = _company_name(config, report_path.path)
    if company_name is None:
        return _report_error(
            config,
            None,
            error_type="invalid_company",
            message="The company name could not be validated. Strategy generation was not started.",
        )

    strategy_type = config.strategy_type
    platforms = config.cloud_vendors if strategy_type in AI_STRATEGY_IDS else ("agnostic",)
    # The AI strategy ideation defaults to the ~$1 lite (Pro model) engine; the
    # thorough Deep Research engine is opt-in via --deep-research. Explicit --lite
    # stays honored. (Non-AI strategy types ignore lite_strategy downstream.)
    effective_lite = config.lite_strategy or not config.deep_research_strategy
    try:
        estimate = estimate_standalone_strategy(
            strategy_type,
            platforms=platforms,
            lite_strategy=effective_lite,
            refresh_vendor_research=config.refresh_vendor_research,
        )
    except ValueError as exc:
        return _report_error(
            config,
            None,
            error_type="unsupported_strategy",
            message=str(exc),
        )

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

    if not config.skip_confirm and (config.json_output or not can_prompt_for_input()):
        return _report_error(
            config,
            estimate,
            error_type="approval_required",
            message="Execution requires explicit approval. Re-run with --skip-confirm.",
            hints=("Use --dry-run --json to inspect the estimate without execution.",),
        )

    if not config.json_output:
        _emit_estimate(config, estimate)
    if not config.skip_confirm:
        try:
            response = input("Proceed with standalone strategy generation? [y/N] ").strip().lower()
        except (EOFError, OSError, ValueError):
            return _report_error(
                config,
                estimate,
                error_type="approval_required",
                message="Execution requires explicit approval. Re-run with --skip-confirm.",
                hints=("Use --dry-run to inspect the estimate without execution.",),
            )
        except KeyboardInterrupt:
            console.info("Cancelled. No model calls were started.")
            return 0
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

    display_name = _strategy_display_name(strategy_type)
    if not config.json_output:
        console.banner(f"{display_name} Generation")
        console.info(f"Company: {company_name}")
        console.info(f"Context: {report_path.path.name}")
        if strategy_type in AI_STRATEGY_IDS:
            console.info(f"Platforms: {', '.join(platform.upper() for platform in platforms)}")
        console.blank()

    runtime_strategy_type = "ai" if strategy_type == "ai_strategy" else strategy_type
    expected_targets = tuple(strategy_target(runtime_strategy_type, p) for p in platforms)
    from primr.config.config import WORKING_DIR
    from primr.core.workspace import (
        ActiveRunLeaseError,
        ResumeLeaseError,
        company_run_lease_for_target,
    )

    per_target = estimate.estimated_cost_usd / max(estimate.strategy_calls, 1)
    budget_active = False
    try:
        if config.budget_usd is not None:
            set_run_budget(config.budget_usd)
            budget_active = True
        with (
            company_run_lease_for_target(
                company_name,
                None,
                base_dir=WORKING_DIR,
            ) as company_root,
            stable_report_snapshot(report_path, company_root) as snapshot_path,
        ):
            artifacts, failed_targets = _generate_strategy_targets(
                config,
                snapshot_path=snapshot_path,
                company_name=company_name,
                platforms=platforms,
                runtime_strategy_type=runtime_strategy_type,
                display_name=display_name,
                generate_strategy=generate_strategy,
                lite_strategy=effective_lite,
                estimated_cost_per_target=per_target,
            )
    except ActiveRunLeaseError:
        return _report_error(
            config,
            estimate,
            error_type="active_run",
            message=(
                "Another active run is publishing artifacts for this company. "
                "Wait for it to finish, then retry."
            ),
        )
    except ResumeLeaseError:
        return _report_error(
            config,
            estimate,
            error_type="workspace_claim_failed",
            message=(
                "Could not safely claim this company workspace. "
                "Inspect its ownership record before retrying."
            ),
        )
    except _ReportSnapshotError:
        return _report_error(
            config,
            estimate,
            error_type="report_changed",
            message="The report changed after validation. Strategy generation was not started.",
        )
    except Exception as exc:
        logger.error("Standalone strategy execution failed: %s", type(exc).__name__)
        return _report_error(
            config,
            estimate,
            error_type="execution_failed",
            message="Strategy generation failed before a complete result could be reported.",
        )
    finally:
        if budget_active:
            clear_run_budget()

    if config.json_output:
        _emit_strategy_result(
            config,
            estimate,
            expected_targets=expected_targets,
            artifacts=artifacts,
            failed_targets=failed_targets,
        )
    elif failed_targets:
        console.error(
            f"{display_name} generation completed only "
            f"{len(artifacts)} of {len(expected_targets)} requested target(s)"
        )
    if config.open_after and artifacts and not config.json_output:
        open_result(artifacts[-1]["path"])
    return 1 if failed_targets else 0


__all__ = ["handle_ai_strategy_only"]
