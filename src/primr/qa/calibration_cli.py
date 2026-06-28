"""CLI adapter for calibration commands."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from primr.qa.calibration_runner import (
    JudgeAgreement,
    JudgeSelection,
    ReportCalibrationOutcome,
    aggregate_per_label,
    aggregate_precision,
    compare_judges,
    estimate_cost_usd,
    resolve_judge,
    resolve_reports,
    run_calibration,
    write_calibration_pack_manifest,
)


class CalibrateConfig(Protocol):
    @property
    def calibrate_target(self) -> str | None: ...

    @property
    def calibrate_recent(self) -> int | None: ...

    @property
    def calibrate_max_per_label(self) -> int: ...

    @property
    def calibrate_dry_run(self) -> bool: ...

    @property
    def calibrate_judge(self) -> str: ...

    @property
    def calibrate_judge_model(self) -> str | None: ...

    @property
    def calibrate_judge_compare(self) -> bool: ...

    @property
    def calibrate_pack_manifest(self) -> str | None: ...


class ConsoleSink(Protocol):
    def banner(self, title: str) -> None: ...

    def error(self, message: str) -> None: ...

    def info(self, message: str) -> None: ...

    def ok(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...


def handle_calibrate(config: CalibrateConfig, console: ConsoleSink) -> int:
    """Handle the label-calibration audit command."""
    try:
        reports = resolve_reports(config.calibrate_target, recent=config.calibrate_recent)
    except FileNotFoundError as exc:
        console.error(str(exc))
        console.info('Usage: primr calibrate "Company Name" [--dry-run] [--max-per-label 10]')
        console.info("   or: primr calibrate path/to/report.md")
        console.info("   or: primr calibrate --calibrate-recent 10")
        return 1

    console.banner("Label Calibration")
    console.info(f"Reports: {len(reports)}")
    agreement = None
    judge_selection = None
    judge_metadata = None

    if config.calibrate_judge_compare:
        try:
            local_selection = resolve_judge("local", model=config.calibrate_judge_model)
        except RuntimeError as exc:
            console.error(str(exc))
            return 1
        console.info(f"Judges: cloud (fast-tier) vs local ({local_selection.model})")
        judge_metadata = _judge_compare_metadata(local_selection)
        if config.calibrate_dry_run:
            outcomes = run_calibration(
                reports, max_per_label=config.calibrate_max_per_label, dry_run=True
            )
            total_calls = sum(outcome.estimated_judge_calls for outcome in outcomes)
            console.info(
                f"Dry run: ~{total_calls} cloud judge calls "
                f"(${estimate_cost_usd(total_calls):.2f}) + ~{total_calls} local judge calls "
                "($0.00)"
            )
            _write_pack_manifest_if_requested(
                config,
                reports,
                outcomes,
                console,
                judge_metadata=judge_metadata,
            )
            return 0
        outcomes, agreement = compare_judges(
            reports,
            local_selection=local_selection,
            max_per_label=config.calibrate_max_per_label,
        )
        if agreement.agreement is None:
            console.warn("No claims were decidable by both judges - agreement not measurable")
        else:
            console.info(
                f"Judge agreement: {agreement.agreement:.0%} "
                f"({agreement.agreed}/{agreement.compared} decidable claims, "
                f"local={agreement.local_model})"
            )
    else:
        try:
            judge_selection = resolve_judge(
                config.calibrate_judge, model=config.calibrate_judge_model
            )
        except (RuntimeError, ValueError) as exc:
            console.error(str(exc))
            return 1
        console.info(f"Judge: {judge_selection.kind} ({judge_selection.model})")
        outcomes = run_calibration(
            reports,
            max_per_label=config.calibrate_max_per_label,
            dry_run=config.calibrate_dry_run,
            judge_selection=judge_selection,
        )
        if judge_selection.cloud_fallbacks:
            console.warn(
                f"Local judge fell back to cloud on {judge_selection.cloud_fallbacks} call(s)"
            )

    failures = [outcome for outcome in outcomes if outcome.error]
    for outcome in failures:
        console.warn(f"{outcome.report_path.name}: {outcome.error}")

    if config.calibrate_dry_run:
        total_calls = sum(outcome.estimated_judge_calls for outcome in outcomes)
        for outcome in outcomes:
            console.info(
                f"  {outcome.report_path.name}: {outcome.claims_sampled} claims, "
                f"{outcome.judgeable_claims} judgeable, "
                f"~{outcome.estimated_judge_calls} judge calls"
            )
        console.info(
            f"Dry run: ~{total_calls} judge calls, estimated ${estimate_cost_usd(total_calls):.2f}"
        )
        _write_pack_manifest_if_requested(config, reports, outcomes, console, judge_selection)
        return 0

    _write_pack_manifest_if_requested(
        config,
        reports,
        outcomes,
        console,
        judge_selection,
        agreement,
        judge_metadata,
    )

    totals = aggregate_per_label(outcomes)
    for label in ("Confirmed", "Reported"):
        stats = totals.get(label)
        if not stats:
            continue
        precision = aggregate_precision(totals, label)
        shown = f"{precision:.0%}" if precision is not None else "n/a (no decidable claims)"
        console.info(
            f"  {label}: traceability {shown} "
            f"(traceable {stats['traceable']}, untraceable {stats['untraceable']}, "
            f"no-source {stats['no_source']}, unfetchable {stats['unfetchable']})"
        )
    sidecars = [outcome for outcome in outcomes if outcome.sidecar_path]
    if sidecars:
        console.ok(f"Calibration sidecars written: {len(sidecars)}")
    return 0 if not failures else 1


def _write_pack_manifest_if_requested(
    config: CalibrateConfig,
    reports: list[Path],
    outcomes: list[ReportCalibrationOutcome],
    console: ConsoleSink,
    judge_selection: JudgeSelection | None = None,
    judge_agreement: JudgeAgreement | None = None,
    judge_metadata: dict[str, object] | None = None,
) -> None:
    if not config.calibrate_pack_manifest:
        return
    write_calibration_pack_manifest(
        Path(config.calibrate_pack_manifest),
        reports,
        outcomes,
        max_per_label=config.calibrate_max_per_label,
        judge_selection=judge_selection,
        judge_agreement=judge_agreement,
        judge_metadata=judge_metadata,
    )
    console.ok(f"Calibration pack manifest written: {config.calibrate_pack_manifest}")


def _judge_compare_metadata(local_selection: JudgeSelection) -> dict[str, object]:
    return {
        "kind": "compare",
        "cloud": {"kind": "cloud", "model": "fast-tier"},
        "local": local_selection.to_metadata(),
    }
