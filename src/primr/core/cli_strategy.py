"""Governed standalone strategy recovery for the CLI."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol

from primr.core.strategy_estimate import (
    AI_STRATEGY_IDS,
    StandaloneStrategyEstimate,
    estimate_standalone_strategy,
)
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)


class _StrategyConfig(Protocol):
    @property
    def ai_strategy_only_path(self) -> str | None: ...

    @property
    def company_name(self) -> str | None: ...

    @property
    def strategy_type(self) -> str: ...

    @property
    def refresh_vendor_research(self) -> bool: ...

    @property
    def lite_strategy(self) -> bool: ...

    @property
    def budget_usd(self) -> float | None: ...

    @property
    def dry_run_requested(self) -> bool: ...

    @property
    def json_output(self) -> bool: ...

    @property
    def skip_confirm(self) -> bool: ...

    @property
    def output_dir(self) -> str | None: ...

    @property
    def open_after(self) -> bool: ...

    @property
    def cloud_vendors(self) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class _TrustedReport:
    path: Path
    device: int
    inode: int
    size: int
    modified_ns: int
    content_sha256: str


class _ReportSnapshotError(RuntimeError):
    """Raised when a validated report cannot be pinned safely."""


def _report_identity(report_stat: os.stat_result) -> tuple[int, int, int, int]:
    """Return the metadata identity checked around every content read."""
    return (
        report_stat.st_dev,
        report_stat.st_ino,
        report_stat.st_size,
        report_stat.st_mtime_ns,
    )


def _validated_report_digest(path: Path, expected_stat: os.stat_result) -> str:
    """Hash one stable regular-file identity without following symbolic links."""
    source_fd = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(path, flags)
        with os.fdopen(source_fd, "rb") as source:
            source_fd = -1
            opened_stat = os.fstat(source.fileno())
            current_path_stat = path.lstat()
            if (
                not stat.S_ISREG(opened_stat.st_mode)
                or stat.S_ISLNK(current_path_stat.st_mode)
                or opened_stat.st_nlink > 1
                or _report_identity(opened_stat) != _report_identity(expected_stat)
                or (current_path_stat.st_dev, current_path_stat.st_ino)
                != (opened_stat.st_dev, opened_stat.st_ino)
            ):
                raise _ReportSnapshotError("Report file changed during validation")
            digest = hashlib.file_digest(source, "sha256").hexdigest()
            final_source_stat = os.fstat(source.fileno())

        final_path_stat = path.lstat()
        if (
            _report_identity(final_source_stat) != _report_identity(expected_stat)
            or stat.S_ISLNK(final_path_stat.st_mode)
            or (final_path_stat.st_dev, final_path_stat.st_ino)
            != (expected_stat.st_dev, expected_stat.st_ino)
        ):
            raise _ReportSnapshotError("Report file changed during validation")
        return digest
    finally:
        if source_fd >= 0:
            os.close(source_fd)


def _contains_symlink(path: Path) -> bool:
    """Return whether the supplied path or any existing parent is a symlink."""
    current = path.absolute()
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def _resolve_trusted_report(report_path: str) -> _TrustedReport | None:
    """Resolve a regular report beneath a fixed trusted root, or fail closed."""
    try:
        from primr.config.config import OUTPUT_DIR, WORKING_DIR

        supplied = Path(report_path).expanduser()
        if _contains_symlink(supplied):
            console.error("Report path cannot contain symbolic links")
            return None

        resolved = supplied.resolve(strict=True)
        roots = (Path(OUTPUT_DIR).resolve(), Path(WORKING_DIR).resolve())
        if not any(resolved.is_relative_to(root) for root in roots):
            console.error("Report file is outside the fixed output/ and working/ roots")
            return None
        if not resolved.is_file():
            console.error(f"Report path is not a regular file: {report_path}")
            return None
        report_stat = resolved.stat()
        if report_stat.st_nlink > 1:
            console.error("Report file cannot be a hard link")
            return None
        content_sha256 = _validated_report_digest(resolved, report_stat)
        return _TrustedReport(
            path=resolved,
            device=report_stat.st_dev,
            inode=report_stat.st_ino,
            size=report_stat.st_size,
            modified_ns=report_stat.st_mtime_ns,
            content_sha256=content_sha256,
        )
    except FileNotFoundError:
        console.error(f"Report file not found: {report_path}")
    except Exception as exc:
        logger.warning("Standalone report validation failed closed: %s", type(exc).__name__)
        console.error("Could not validate the report path. Strategy generation was not started.")
    return None


def _snapshot_trusted_report(report: _TrustedReport, destination_dir: Path) -> Path:
    """Copy the validated file identity into a private, stable context file."""
    snapshot_path: Path | None = None
    source_fd = -1
    try:
        if _contains_symlink(report.path):
            raise _ReportSnapshotError("Report path changed after validation")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(report.path, flags)
        opened_stat = os.fstat(source_fd)
        opened_identity = _report_identity(opened_stat)
        expected_identity = (
            report.device,
            report.inode,
            report.size,
            report.modified_ns,
        )
        current_path_stat = report.path.lstat()
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or stat.S_ISLNK(current_path_stat.st_mode)
            or opened_stat.st_nlink > 1
            or opened_identity != expected_identity
            or (current_path_stat.st_dev, current_path_stat.st_ino)
            != (opened_stat.st_dev, opened_stat.st_ino)
        ):
            raise _ReportSnapshotError("Report file changed after validation")

        destination_dir.mkdir(parents=True, exist_ok=True)
        snapshot_fd, snapshot_name = tempfile.mkstemp(
            prefix=".primr-strategy-context-",
            suffix=report.path.suffix,
            dir=destination_dir,
        )
        snapshot_path = Path(snapshot_name)
        snapshot_digest = hashlib.sha256()
        with os.fdopen(snapshot_fd, "wb") as target, os.fdopen(source_fd, "rb") as source:
            source_fd = -1
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
                snapshot_digest.update(chunk)
            target.flush()
            os.fsync(target.fileno())
            final_source_stat = os.fstat(source.fileno())

        final_path_stat = report.path.lstat()
        if (
            (final_source_stat.st_size, final_source_stat.st_mtime_ns)
            != (report.size, report.modified_ns)
            or stat.S_ISLNK(final_path_stat.st_mode)
            or (final_path_stat.st_dev, final_path_stat.st_ino) != (report.device, report.inode)
            or snapshot_digest.hexdigest() != report.content_sha256
        ):
            raise _ReportSnapshotError("Report file changed while it was copied")
        return snapshot_path
    except (OSError, _ReportSnapshotError) as exc:
        if snapshot_path is not None:
            try:
                snapshot_path.unlink()
            except OSError:
                logger.warning("Could not remove rejected standalone strategy snapshot")
        if isinstance(exc, _ReportSnapshotError):
            raise
        raise _ReportSnapshotError("Could not create a stable report snapshot") from exc
    finally:
        if source_fd >= 0:
            os.close(source_fd)


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
        with company_run_lease_for_target(
            company_name,
            None,
            base_dir=WORKING_DIR,
        ) as company_root:
            snapshot_path = _snapshot_trusted_report(report_path, company_root)
            try:
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
            finally:
                try:
                    snapshot_path.unlink()
                except OSError:
                    logger.warning("Could not remove standalone strategy context snapshot")
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
