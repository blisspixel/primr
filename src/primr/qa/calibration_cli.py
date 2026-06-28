"""CLI adapter for calibration commands."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from primr.qa.calibration_baseline import (
    default_baseline_json_path,
    write_calibration_baseline,
)
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
from primr.qa.calibration_selection import CalibrationPackSelection, load_calibration_pack_selection


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

    @property
    def calibrate_pack_selection(self) -> str | None: ...

    @property
    def calibrate_baseline_from(self) -> str | None: ...

    @property
    def calibrate_baseline_out(self) -> str | None: ...

    @property
    def calibrate_baseline_md(self) -> str | None: ...

    @property
    def calibrate_baseline_min_reports(self) -> int: ...


class ConsoleSink(Protocol):
    def banner(self, title: str) -> None: ...

    def error(self, message: str) -> None: ...

    def info(self, message: str) -> None: ...

    def ok(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...


def handle_calibrate(config: CalibrateConfig, console: ConsoleSink) -> int:
    """Handle the label-calibration audit command."""
    if config.calibrate_baseline_min_reports < 1:
        console.error("--baseline-min-reports must be at least 1")
        return 1
    if config.calibrate_baseline_from:
        return _handle_baseline_from_manifest(config, console)
    if (
        config.calibrate_baseline_out or config.calibrate_baseline_md
    ) and not config.calibrate_pack_manifest:
        console.error("--baseline-out and --baseline-md require --baseline-from or --pack-manifest")
        return 1

    try:
        selection = _load_selection_if_requested(config)
        reports = (
            list(selection.report_paths)
            if selection is not None
            else resolve_reports(config.calibrate_target, recent=config.calibrate_recent)
        )
    except (FileNotFoundError, ValueError) as exc:
        console.error(str(exc))
        console.info('Usage: primr calibrate "Company Name" [--dry-run] [--max-per-label 10]')
        console.info("   or: primr calibrate path/to/report.md")
        console.info("   or: primr calibrate --calibrate-recent 10")
        console.info("   or: primr calibrate --pack-selection path/to/selection.json")
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
                selection=selection,
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
        _write_pack_manifest_if_requested(
            config,
            reports,
            outcomes,
            console,
            selection=selection,
            judge_selection=judge_selection,
        )
        return 0

    _write_pack_manifest_if_requested(
        config,
        reports,
        outcomes,
        console,
        selection=selection,
        judge_selection=judge_selection,
        judge_agreement=agreement,
        judge_metadata=judge_metadata,
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


def _load_selection_if_requested(config: CalibrateConfig) -> CalibrationPackSelection | None:
    if not config.calibrate_pack_selection:
        return None
    if config.calibrate_target or config.calibrate_recent is not None:
        raise ValueError("--pack-selection cannot be combined with a target or --calibrate-recent")
    return load_calibration_pack_selection(Path(config.calibrate_pack_selection))


def _write_pack_manifest_if_requested(
    config: CalibrateConfig,
    reports: list[Path],
    outcomes: list[ReportCalibrationOutcome],
    console: ConsoleSink,
    selection: CalibrationPackSelection | None = None,
    judge_selection: JudgeSelection | None = None,
    judge_agreement: JudgeAgreement | None = None,
    judge_metadata: dict[str, object] | None = None,
) -> None:
    if not config.calibrate_pack_manifest:
        return
    manifest_path = Path(config.calibrate_pack_manifest)
    write_calibration_pack_manifest(
        manifest_path,
        reports,
        outcomes,
        max_per_label=config.calibrate_max_per_label,
        judge_selection=judge_selection,
        judge_agreement=judge_agreement,
        judge_metadata=judge_metadata,
        selection=selection,
    )
    console.ok(f"Calibration pack manifest written: {config.calibrate_pack_manifest}")
    _write_baseline_from_manifest_if_requested(config, manifest_path, console)


def _handle_baseline_from_manifest(config: CalibrateConfig, console: ConsoleSink) -> int:
    manifest_path = Path(config.calibrate_baseline_from or "")
    try:
        _write_baseline_from_manifest(config, manifest_path, console, force=True)
    except (OSError, ValueError) as exc:
        console.error(str(exc))
        return 1
    return 0


def _write_baseline_from_manifest_if_requested(
    config: CalibrateConfig,
    manifest_path: Path,
    console: ConsoleSink,
) -> None:
    if not (config.calibrate_baseline_out or config.calibrate_baseline_md):
        return
    _write_baseline_from_manifest(config, manifest_path, console, force=False)


def _write_baseline_from_manifest(
    config: CalibrateConfig,
    manifest_path: Path,
    console: ConsoleSink,
    *,
    force: bool,
) -> None:
    output_path = (
        Path(config.calibrate_baseline_out)
        if config.calibrate_baseline_out
        else default_baseline_json_path(manifest_path)
    )
    markdown_path = Path(config.calibrate_baseline_md) if config.calibrate_baseline_md else None
    baseline = write_calibration_baseline(
        output_path,
        manifest_path,
        markdown_path=markdown_path,
        minimum_reports=config.calibrate_baseline_min_reports,
    )
    if baseline["ready"]:
        console.ok(f"Calibration baseline ready: {output_path}")
    elif force:
        console.warn(f"Calibration baseline not ready ({baseline['status']}): {output_path}")
    else:
        console.warn(
            f"Calibration baseline written but not ready ({baseline['status']}): {output_path}"
        )
    if markdown_path is not None:
        console.ok(f"Calibration baseline summary written: {markdown_path}")


def _judge_compare_metadata(local_selection: JudgeSelection) -> dict[str, object]:
    return {
        "kind": "compare",
        "cloud": {"kind": "cloud", "model": "fast-tier"},
        "local": local_selection.to_metadata(),
    }
