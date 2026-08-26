"""Governed planning and execution for batch research and enrichment."""

from __future__ import annotations

import csv
import glob
import json
import logging
import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from primr.core.cli_batch import _ColumnMap, _csv_safe, _ensure_valid_url, _prepare_batch_df
from primr.utils.console import console
from primr.utils.terminal import prompt_for_approval

if TYPE_CHECKING:
    from primr.utils.cost_estimator import CostEstimate

logger = logging.getLogger(__name__)

_BATCH_SCHEMA_VERSION = "primr.batch-plan.v1"
_ENRICH_SCHEMA_VERSION = "primr.batch-enrich-plan.v1"
_MAX_CONSECUTIVE_FAILURES = 3
_MIN_REPORT_SIZE_KB = 5
_MAX_RUN_STATE_BYTES = 1024 * 1024


def _required_number(values: Mapping[str, object], key: str) -> float:
    """Return one required numeric payload value without permissive coercion."""
    value = values[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")
    return float(value)


@dataclass(frozen=True)
class BatchCompany:
    """One deduplicated, locally parsed spreadsheet row."""

    name: str
    website: str | None
    industry: str
    context: dict[str, str]


@dataclass(frozen=True)
class ExistingBatchReport:
    company: BatchCompany
    path: str
    size_kb: float


@dataclass(frozen=True)
class BatchPlan:
    """Local, zero-egress batch plan."""

    companies: tuple[BatchCompany, ...]
    pending: tuple[BatchCompany, ...]
    missing_websites: tuple[BatchCompany, ...]
    invalid_rows: tuple[str, ...]
    existing: tuple[ExistingBatchReport, ...]


def _nonempty_cell(row: object, column: str | None) -> str:
    if column is None:
        return ""
    value = str(row.get(column, "")).strip()  # type: ignore[attr-defined]
    return "" if value.lower() == "nan" else value


def _extract_companies(
    df: object, col_map: _ColumnMap
) -> tuple[tuple[BatchCompany, ...], tuple[str, ...]]:
    """Normalize, validate, and deduplicate rows without network activity."""
    from primr.utils.validators import InputValidationError, validate_company_name, validate_url

    companies: list[BatchCompany] = []
    invalid_rows: list[str] = []
    seen: set[str] = set()
    for row_number, (_, row) in enumerate(df.iterrows(), start=2):  # type: ignore[attr-defined]
        raw_website = _nonempty_cell(row, col_map.website)
        website = _ensure_valid_url(raw_website)
        if website:
            try:
                website = validate_url(website)
            except InputValidationError as exc:
                invalid_rows.append(f"row {row_number}: invalid website ({exc.reason})")
                continue

        raw_name = (
            "" if col_map.company == col_map.website else _nonempty_cell(row, col_map.company)
        )
        if not raw_name and website:
            raw_name = (urlsplit(website).hostname or "").removeprefix("www.")
        if not raw_name:
            continue
        try:
            company_name = validate_company_name(raw_name)
        except InputValidationError as exc:
            invalid_rows.append(f"row {row_number}: invalid company name ({exc.reason})")
            continue
        normalized_key = company_name.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)

        context = {
            column: value for column in col_map.context if (value := _nonempty_cell(row, column))
        }
        companies.append(
            BatchCompany(
                name=company_name,
                website=website,
                industry=_nonempty_cell(row, col_map.industry),
                context=context,
            )
        )
    return (tuple(companies), tuple(invalid_rows))


def _find_existing_report(
    company: BatchCompany,
    output_root: Path,
    *,
    expected_mode: str,
    expected_strategy_targets: tuple[str, ...],
    expected_refresh_vendors: tuple[str, ...],
) -> ExistingBatchReport | None:
    """Find today's report only when its owning run fulfilled this exact request."""

    today = datetime.now().strftime("%m-%d-%Y")
    candidates = {company.name, company.name.replace(" ", "_").replace("/", "_")}
    matches: list[str] = []
    for name in candidates:
        pattern = str(output_root / f"{glob.escape(name)}*Overview*{today}*")
        matches.extend(glob.glob(pattern))
    if not matches:
        return None
    ordered = sorted(
        dict.fromkeys(matches),
        key=lambda path: ({".docx": 0, ".md": 1, ".txt": 2}.get(Path(path).suffix, 3), path),
    )
    for selected in ordered:
        if not _has_matching_completed_run(
            company,
            selected,
            expected_mode=expected_mode,
            expected_strategy_targets=expected_strategy_targets,
            expected_refresh_vendors=expected_refresh_vendors,
        ):
            continue
        size_kb = os.path.getsize(selected) / 1024 if os.path.exists(selected) else 0.0
        return ExistingBatchReport(company, selected, size_kb)
    return None


def _has_matching_completed_run(
    company: BatchCompany,
    report_path: str,
    *,
    expected_mode: str,
    expected_strategy_targets: tuple[str, ...],
    expected_refresh_vendors: tuple[str, ...],
) -> bool:
    """Verify exact request fulfillment from bounded canonical run state."""

    from primr.config.config import WORKING_DIR
    from primr.core.research_artifact_binding import primary_artifact_matches_state
    from primr.core.strategy_outcome import strategy_outcome_from_state
    from primr.core.vendor_refresh_outcome import vendor_refresh_outcome_from_state
    from primr.core.workspace import derive_working_folder_name

    company_root = Path(WORKING_DIR) / derive_working_folder_name(company.name, company.website)
    if not company_root.is_dir() or company_root.is_symlink():
        return False
    for state_path in company_root.glob("*/_run_state.json"):
        state = _read_bounded_run_state(state_path)
        if state is None:
            continue
        strategy = strategy_outcome_from_state(state)
        refresh = vendor_refresh_outcome_from_state(state)
        recorded_website = str(state.get("website", "")).rstrip("/")
        expected_website = str(company.website or "").rstrip("/")
        if (
            str(state.get("status", "")).lower() != "completed"
            or str(state.get("company_name", "")).casefold() != company.name.casefold()
            or recorded_website != expected_website
            or state.get("mode") != expected_mode
            or strategy is None
            or refresh is None
            or strategy.expected_targets != expected_strategy_targets
            or refresh.expected_vendors != expected_refresh_vendors
            or strategy.requires_nonzero_exit
            or refresh.requires_nonzero_exit
            or not primary_artifact_matches_state(state, report_path)
        ):
            continue
        return True
    return False


def _read_bounded_run_state(path: Path) -> dict[str, object] | None:
    """Read one small, singly linked regular run-state file."""

    from primr.utils.fs_safety import (
        path_contains_link_or_reparse_point,
        path_is_linked_or_nonregular_file,
    )

    if path_contains_link_or_reparse_point(path) or path_is_linked_or_nonregular_file(path):
        return None
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAX_RUN_STATE_BYTES
        ):
            return None
        chunks: list[bytes] = []
        remaining = _MAX_RUN_STATE_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or sum(len(chunk) for chunk in chunks) != after.st_size:
            return None
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return payload if isinstance(payload, dict) else None


def build_batch_plan(
    file_path: str,
    *,
    industry: str | None,
    limit: int | None,
    output_dir: str | Path | None,
    quiet: bool,
    expected_mode: str,
    expected_strategy_targets: tuple[str, ...],
    expected_refresh_vendors: tuple[str, ...],
) -> BatchPlan:
    """Build a deterministic plan from one file snapshot."""
    df, col_map = _prepare_batch_df(
        file_path,
        industry=industry,
        limit=limit,
        quiet=quiet,
    )
    companies, invalid_rows = _extract_companies(df, col_map)
    output_root = Path(output_dir) if output_dir is not None else _default_output_dir()
    pending: list[BatchCompany] = []
    missing: list[BatchCompany] = []
    existing: list[ExistingBatchReport] = []
    for company in companies:
        found = _find_existing_report(
            company,
            output_root,
            expected_mode=expected_mode,
            expected_strategy_targets=expected_strategy_targets,
            expected_refresh_vendors=expected_refresh_vendors,
        )
        if found is not None:
            existing.append(
                ExistingBatchReport(company=company, path=found.path, size_kb=found.size_kb)
            )
        elif not company.website:
            missing.append(company)
        else:
            pending.append(company)
    return BatchPlan(
        companies=companies,
        pending=tuple(pending),
        missing_websites=tuple(missing),
        invalid_rows=invalid_rows,
        existing=tuple(existing),
    )


def _default_output_dir() -> Path:
    from primr.config.config import OUTPUT_DIR

    return Path(OUTPUT_DIR)


def _budget_error(budget_usd: float | None) -> str | None:
    if budget_usd is None:
        return None
    if not isfinite(budget_usd) or budget_usd <= 0:
        return f"--budget must be a finite positive number, got {budget_usd}"
    return None


def _batch_estimate_payload(
    *,
    file_path: str,
    plan: BatchPlan,
    estimate: CostEstimate,
    mode_label: str,
    ai_strategy: bool,
    budget_usd: float | None,
    deprecated_alias: str | None,
) -> dict[str, object]:
    from primr.core.cli_output import cost_estimate_json

    batch_estimate = estimate.total_cost * len(plan.pending)
    per_company_allocation = (
        None if budget_usd is None or not plan.pending else budget_usd / len(plan.pending)
    )
    per_company_within_budget = (
        None if per_company_allocation is None else estimate.total_cost <= per_company_allocation
    )
    return {
        "schema_version": _BATCH_SCHEMA_VERSION,
        "operation": "batch_research",
        "batch_file": str(Path(file_path).resolve()),
        "total_company_count": len(plan.companies),
        "eligible_company_count": len(plan.pending),
        "already_completed_count": len(plan.existing),
        "missing_website_count": len(plan.missing_websites),
        "invalid_row_count": len(plan.invalid_rows),
        "invalid_rows": list(plan.invalid_rows),
        "estimate_basis": (
            "Canonical per-company estimate multiplied by pending companies with supplied "
            "websites; today's existing reports are excluded."
        ),
        "mode_label": mode_label,
        "per_company_estimate": cost_estimate_json(
            estimate,
            mode_label=mode_label,
            ai_strategy=ai_strategy,
        ),
        "website_lookup_estimate": {
            "lookup_count": 0,
            "estimated_cost_usd": 0.0,
            "included": False,
            "reason": "Batch research does not look up websites; run --enrich first.",
        },
        "estimated_batch_cost_usd": round(batch_estimate, 6),
        "budget_usd": budget_usd,
        "budget_scope": "batch",
        "batch_within_budget": (None if budget_usd is None else batch_estimate <= budget_usd),
        "per_company_budget_allocation_usd": (
            None if per_company_allocation is None else round(per_company_allocation, 6)
        ),
        "per_company_within_budget": per_company_within_budget,
        "approval_required": bool(plan.pending),
        "automatic_retries": 0,
        "deprecated_alias": deprecated_alias,
    }


def _emit_json(payload: dict[str, object]) -> None:
    from primr.core.cli_output import emit_json

    emit_json(payload)


def _emit_json_error(operation: str, message: str) -> None:
    _emit_json(
        {
            "schema_version": (
                _ENRICH_SCHEMA_VERSION if operation == "batch_enrich" else _BATCH_SCHEMA_VERSION
            ),
            "operation": operation,
            "error": True,
            "message": message,
        }
    )


def _render_batch_plan(payload: dict[str, object], plan: BatchPlan) -> None:
    console.banner("Batch Research")
    console.info(f"File: {payload['batch_file']}")
    console.info(f"Mode: {payload['mode_label']}")
    console.info(f"Companies parsed: {payload['total_company_count']}")
    console.info(f"Pending research: {payload['eligible_company_count']}")
    if plan.existing:
        console.info(f"Already completed today: {len(plan.existing)}")
    if plan.missing_websites:
        console.warn(f"Missing websites: {len(plan.missing_websites)}")
    if plan.invalid_rows:
        console.error(f"Invalid rows: {len(plan.invalid_rows)}")
        for issue in plan.invalid_rows[:10]:
            console.info(f"  {issue}")
    per_company = payload["per_company_estimate"]
    assert isinstance(per_company, dict)
    console.info(f"Per-company estimate: ~${float(per_company['total_cost']):.2f}")
    console.info(f"Batch estimate: ~${_required_number(payload, 'estimated_batch_cost_usd'):.2f}")
    console.info("Automatic paid retries: disabled")


def _fallback_estimate(
    *,
    mode: str,
    ai_strategy: bool,
    platforms: tuple[str, ...] | None,
    lite_strategy: bool,
    fast_mode: bool,
    premium_mode: bool,
    verify: bool,
    grok_tier: str,
    strategies: list[str] | None,
) -> CostEstimate:
    from primr.utils.cost_display import estimate_cost_with_planning_floor

    return estimate_cost_with_planning_floor(
        mode,
        ai_strategy,
        num_vendors=max(len(platforms or ("agnostic",)), 1),
        lite_strategy=lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=verify,
        grok_tier=grok_tier,
        strategy_types=strategies,
    )


def _batch_execution_blocker(
    plan: BatchPlan,
    *,
    budget_usd: float | None,
    estimate: CostEstimate,
    ai_strategy: bool,
) -> tuple[str, str | None] | None:
    """Return a zero-egress execution blocker and optional recovery hint."""
    if not plan.companies:
        return ("No valid companies were found in the batch file.", None)
    if plan.invalid_rows:
        return ("Fix invalid rows before starting batch research.", None)
    if plan.missing_websites:
        return (
            "Every batch company needs a website before paid research can start.",
            "Run batch enrichment first, then review its output.",
        )
    batch_estimate = estimate.total_cost * len(plan.pending)
    if budget_usd is not None and batch_estimate > budget_usd:
        return (
            f"Batch estimate ${batch_estimate:.2f} exceeds "
            f"--budget ${budget_usd:.2f}. Not starting.",
            None,
        )
    if ai_strategy:
        from primr.core.vendor_research import vendor_auto_refresh_enabled

        if vendor_auto_refresh_enabled():
            return (
                "Batch research cannot run while PRIMR_ALLOW_VENDOR_REFRESH is enabled "
                "because refresh fan-out is not included in the batch quote.",
                "Disable vendor auto-refresh or use governed single-company runs.",
            )
    return None


def _authorize_batch_execution(
    plan: BatchPlan,
    payload: dict[str, object],
    *,
    skip_confirm: bool,
    execution_preflight: Callable[[], tuple[bool, list[str]]] | None,
) -> int | None:
    """Return an exit code when approval or local preflight stops execution."""
    if not skip_confirm:
        decision = prompt_for_approval(
            f"Proceed with {len(plan.pending)} companies for an estimated "
            f"${_required_number(payload, 'estimated_batch_cost_usd'):.2f}? [y/N] "
        )
        if decision == "unavailable":
            console.error("Interactive approval unavailable. Re-run with --skip-confirm.")
            return 1
        if decision == "declined":
            console.info("Cancelled. No research calls were started.")
            return 0
        approval_source = "interactive"
    else:
        approval_source = "--skip-confirm"

    if execution_preflight is not None:
        try:
            preflight_ok, preflight_errors = execution_preflight()
        except Exception:
            logger.exception("Approved batch execution preflight failed")
            console.error("Batch preflight failed unexpectedly. No research calls were started.")
            return 1
        if not preflight_ok:
            for error in preflight_errors:
                console.error(error)
            console.info("Run 'primr doctor' for detailed diagnostics")
            return 1

    logger.info(
        "Batch approved: companies=%d estimated_cost_usd=%.6f approval=%s retries=0",
        len(plan.pending),
        _required_number(payload, "estimated_batch_cost_usd"),
        approval_source,
    )
    return None


def _batch_artifact_status(
    result_path: str,
    working_folder: str | None,
    size_kb: float,
) -> tuple[str, str | None, str | None]:
    """Return truthful batch status, diagnostic text, and run-state path."""

    from primr.core.cli_research_result import assess_research_fulfillment

    assessment = assess_research_fulfillment(result_path, working_folder)
    if assessment.status == "unknown":
        return (
            "partial",
            "outcome state unavailable; inspect logs before retrying",
            assessment.run_state_path,
        )
    if assessment.status != "completed":
        return (
            "partial",
            "requested strategy or vendor refresh work is incomplete",
            assessment.run_state_path,
        )
    if size_kb < _MIN_REPORT_SIZE_KB:
        return "warning", "small report", assessment.run_state_path
    return "ok", None, assessment.run_state_path


def process_batch(
    file_path: str,
    mode: str = "complete",
    citation_style: str = "numbered",
    ai_strategy: bool = True,
    platforms: tuple[str, ...] | None = None,
    industry: str | None = None,
    limit: int | None = None,
    skip_confirm: bool = False,
    *,
    dry_run: bool = False,
    json_output: bool = False,
    per_company_estimate: CostEstimate | None = None,
    mode_label: str | None = None,
    output_dir: str | Path | None = None,
    strategies: list[str] | None = None,
    no_qa: bool = False,
    max_scrape_time: int | None = None,
    lite_strategy: bool = False,
    fast_mode: bool = False,
    premium_mode: bool = False,
    skip_scrape_validation: bool = False,
    verify: bool = False,
    grok_tier: str = "hybrid",
    skip_recon: bool = False,
    continuous_reasoning: bool = True,
    budget_usd: float | None = None,
    execution_preflight: Callable[[], tuple[bool, list[str]]] | None = None,
    deprecated_alias: str | None = None,
    research_runner: Callable[..., str | None] | None = None,
) -> int:
    """Plan once, approve once, then run each company at most once."""
    if json_output and not dry_run:
        _emit_json_error("batch_research", "--json is supported for batch dry-run only")
        return 1
    budget_error = _budget_error(budget_usd)
    if budget_error:
        if json_output:
            _emit_json_error("batch_research", budget_error)
        else:
            console.error(budget_error)
        return 1

    try:
        from primr.core.platform_mapper import DEFAULT_PLATFORM_FALLBACK
        from primr.core.strategy_outcome import expected_strategy_targets as expand_targets

        requested_strategies = list(strategies) if strategies else (["ai"] if ai_strategy else [])
        requested_platforms = platforms or DEFAULT_PLATFORM_FALLBACK
        plan = build_batch_plan(
            file_path,
            industry=industry,
            limit=limit,
            output_dir=output_dir,
            quiet=json_output,
            expected_mode=mode,
            expected_strategy_targets=expand_targets(
                requested_strategies,
                tuple(requested_platforms),
            ),
            expected_refresh_vendors=(),
        )
    except (Exception, SystemExit) as exc:
        message = "Could not read or classify the batch file"
        logger.exception("Batch planning failed")
        if json_output:
            _emit_json_error("batch_research", message)
        else:
            console.error(f"{message}: {type(exc).__name__}")
        return 1

    estimate = per_company_estimate or _fallback_estimate(
        mode=mode,
        ai_strategy=ai_strategy,
        platforms=platforms,
        lite_strategy=lite_strategy,
        fast_mode=fast_mode,
        premium_mode=premium_mode,
        verify=verify,
        grok_tier=grok_tier,
        strategies=strategies,
    )
    resolved_label = mode_label or mode
    payload = _batch_estimate_payload(
        file_path=file_path,
        plan=plan,
        estimate=estimate,
        mode_label=resolved_label,
        ai_strategy=ai_strategy,
        budget_usd=budget_usd,
        deprecated_alias=deprecated_alias,
    )
    if json_output:
        _emit_json(payload)
        return 0
    _render_batch_plan(payload, plan)
    if dry_run:
        return 0
    blocker = _batch_execution_blocker(
        plan,
        budget_usd=budget_usd,
        estimate=estimate,
        ai_strategy=ai_strategy,
    )
    if blocker is not None:
        message, hint = blocker
        console.error(message)
        if hint:
            console.info(hint)
        return 1
    if not plan.pending:
        console.ok("No pending companies. Today's reports already cover this batch.")
        return 0
    authorization_result = _authorize_batch_execution(
        plan,
        payload,
        skip_confirm=skip_confirm,
        execution_preflight=execution_preflight,
    )
    if authorization_result is not None:
        return authorization_result

    if research_runner is None:
        console.error("Batch execution is unavailable because no research runner was supplied.")
        return 1

    from primr.core.workspace import ActiveRunLeaseError, ResumeLeaseError
    from primr.utils.run_budget import clear_run_budget, set_run_budget

    results: list[dict[str, object]] = [
        {
            "company": item.company.name,
            "status": "ok",
            "path": item.path,
            "size_kb": item.size_kb,
            "error": None,
        }
        for item in plan.existing
    ]
    consecutive_failures = 0
    per_company_budget = None if budget_usd is None else budget_usd / len(plan.pending)
    for index, company in enumerate(plan.pending, start=1):
        console.step(f"[{index}/{len(plan.pending)}] Researching {company.name}")
        clear_run_budget()
        try:
            if per_company_budget is not None:
                set_run_budget(per_company_budget)
            run_context: dict[str, str] = {}
            result_path = research_runner(
                company.name,
                company.website,
                mode=mode,
                citation_style=citation_style,
                ai_strategy=ai_strategy,
                platforms=platforms,
                output_dir=str(output_dir) if output_dir is not None else None,
                skip_confirm=True,
                refresh_vendor_research=False,
                strategies=strategies,
                no_qa=no_qa,
                max_scrape_time=max_scrape_time,
                lite_strategy=lite_strategy,
                fast_mode=fast_mode,
                premium_mode=premium_mode,
                skip_scrape_validation=skip_scrape_validation,
                resume_local=False,
                verify=verify,
                grok_tier=grok_tier,
                skip_recon=skip_recon,
                continuous_reasoning=continuous_reasoning,
                run_context=run_context,
            )
            if not result_path:
                raise RuntimeError("research returned no output artifact")
            from primr.core.research_artifact_binding import bind_primary_artifact

            binding_available = bind_primary_artifact(
                run_context.get("working_folder"),
                result_path,
            )
            size_kb = os.path.getsize(result_path) / 1024 if os.path.exists(result_path) else 0.0
            status, error, run_state_path = _batch_artifact_status(
                result_path,
                run_context.get("working_folder"),
                size_kb,
            )
            results.append(
                {
                    "company": company.name,
                    "status": status,
                    "path": result_path,
                    "size_kb": size_kb,
                    "error": error,
                }
            )
            consecutive_failures = 0
            if status == "partial":
                console.warn(
                    "Base report preserved, but requested work is incomplete. "
                    f"Run state: {run_state_path or 'unavailable'}"
                )
            elif not binding_available and Path(result_path).is_file():
                console.warn(
                    "Resume verification could not bind this report to its run state. "
                    "A later batch run will require a fresh estimate."
                )
            elif status == "warning":
                console.warn(f"Report is only {size_kb:.1f}KB and may be incomplete")
            else:
                console.ok(f"Done: {size_kb:.0f}KB")
        except ActiveRunLeaseError:
            results.append(
                {
                    "company": company.name,
                    "status": "failed",
                    "path": None,
                    "size_kb": 0.0,
                    "error": "another active run owns this company workspace",
                }
            )
            consecutive_failures += 1
        except ResumeLeaseError:
            results.append(
                {
                    "company": company.name,
                    "status": "failed",
                    "path": None,
                    "size_kb": 0.0,
                    "error": "company workspace ownership could not be verified",
                }
            )
            consecutive_failures += 1
        except Exception:
            logger.exception("Batch company research failed: %s", company.name)
            results.append(
                {
                    "company": company.name,
                    "status": "failed",
                    "path": None,
                    "size_kb": 0.0,
                    "error": "research failed; inspect logs before rerunning",
                }
            )
            consecutive_failures += 1
        finally:
            clear_run_budget()

        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            console.error(
                "Stopping after three consecutive failures. Re-run the same command after "
                "addressing the logged cause; automatic paid retries are disabled."
            )
            attempted_names = {str(result["company"]) for result in results}
            for remaining in plan.pending[index:]:
                if remaining.name not in attempted_names:
                    results.append(
                        {
                            "company": remaining.name,
                            "status": "not_attempted",
                            "path": None,
                            "size_kb": 0.0,
                            "error": "stopped after consecutive failures",
                        }
                    )
            break

    return _render_batch_summary(results)


def _render_batch_summary(results: list[dict[str, object]]) -> int:
    console.banner("Batch Summary")
    for index, result in enumerate(results, start=1):
        size = _required_number(result, "size_kb")
        size_label = f"{size:.0f}KB" if size else "-"
        console.info(
            f"{index:>3}. {str(result['company'])[:40]:<40} "
            f"{result['status']!s:<13} {size_label:>8}  {result['error'] or ''}"
        )
    failed = sum(result["status"] in {"failed", "not_attempted"} for result in results)
    partial = sum(result["status"] == "partial" for result in results)
    usable = sum(result["status"] in {"ok", "warning"} for result in results)
    if failed or partial:
        console.error(
            f"Batch finished with {usable} complete, {partial} partial, "
            f"and {failed} failed or not attempted."
        )
        console.info("Re-run the same command to resume completed work safely.")
        return 1
    console.success_box(f"All {usable} reports are usable", "Batch complete")
    return 0


def estimate_website_lookup(count: int) -> dict[str, object]:
    """Price the exact bounded utility-model shape used by enrichment."""
    from primr.ai.routing import Role, pick_model_for_role
    from primr.config.models import PrimrModels
    from primr.data.search_utils import (
        WEBSITE_LOOKUP_MAX_INPUT_BYTES,
        WEBSITE_LOOKUP_MAX_OUTPUT_TOKENS,
    )

    model = pick_model_for_role(Role.UTILITY)
    per_lookup = PrimrModels.calculate_cost_conservative(
        model,
        WEBSITE_LOOKUP_MAX_INPUT_BYTES,
        WEBSITE_LOOKUP_MAX_OUTPUT_TOKENS,
    )
    return {
        "lookup_count": count,
        "model_name": model,
        "max_input_tokens_per_lookup": WEBSITE_LOOKUP_MAX_INPUT_BYTES,
        "max_output_tokens_per_lookup": WEBSITE_LOOKUP_MAX_OUTPUT_TOKENS,
        "estimated_cost_per_lookup_usd": round(per_lookup, 6),
        "estimated_cost_usd": round(per_lookup * count, 6),
        "search_provider": "DuckDuckGo",
        "search_cost_usd": 0.0,
    }


def _enrich_output_path(
    file_path: str,
    industry: str | None,
    output_dir: str | Path | None,
) -> Path:
    base = Path(file_path).stem
    suffix = f"_{industry.lower().replace(' ', '_')}" if industry else ""
    destination = Path(output_dir) if output_dir is not None else Path.cwd()
    return destination / f"{base}{suffix}_enriched.csv"


def enrich_batch(
    file_path: str,
    industry: str | None = None,
    limit: int | None = None,
    mode: str = "complete",
    *,
    dry_run: bool = False,
    json_output: bool = False,
    skip_confirm: bool = False,
    budget_usd: float | None = None,
    output_dir: str | Path | None = None,
) -> int:
    """Plan, approve, and execute website enrichment without hidden egress."""
    del mode  # Retained for backward-compatible callers; enrichment is mode-independent.
    if json_output and not dry_run:
        _emit_json_error("batch_enrich", "--json is supported for enrich dry-run only")
        return 1
    budget_error = _budget_error(budget_usd)
    if budget_error:
        if json_output:
            _emit_json_error("batch_enrich", budget_error)
        else:
            console.error(budget_error)
        return 1
    try:
        df, col_map = _prepare_batch_df(
            file_path,
            industry=industry,
            limit=limit,
            quiet=json_output,
        )
        companies, invalid_rows = _extract_companies(df, col_map)
    except (Exception, SystemExit) as exc:
        logger.exception("Batch enrichment planning failed")
        message = "Could not read or classify the enrichment file"
        if json_output:
            _emit_json_error("batch_enrich", message)
        else:
            console.error(f"{message}: {type(exc).__name__}")
        return 1

    missing = tuple(company for company in companies if not company.website)
    lookup_estimate = estimate_website_lookup(len(missing))
    output_path = _enrich_output_path(file_path, industry, output_dir)
    estimated_lookup_cost = _required_number(lookup_estimate, "estimated_cost_usd")
    payload: dict[str, object] = {
        "schema_version": _ENRICH_SCHEMA_VERSION,
        "operation": "batch_enrich",
        "batch_file": str(Path(file_path).resolve()),
        "company_count": len(companies),
        "lookup_count": len(missing),
        "invalid_row_count": len(invalid_rows),
        "invalid_rows": list(invalid_rows),
        "website_lookup_estimate": lookup_estimate,
        "estimated_cost_usd": estimated_lookup_cost,
        "budget_usd": budget_usd,
        "budget_scope": "operation",
        "within_budget": (None if budget_usd is None else estimated_lookup_cost <= budget_usd),
        "approval_required": bool(missing),
        "automatic_retries": 0,
        "provider_failover": False,
        "output_path": str(output_path.resolve()),
    }
    if json_output:
        _emit_json(payload)
        return 0

    console.banner("Batch Enrich")
    console.info(f"File: {payload['batch_file']}")
    console.info(f"Companies: {len(companies)}")
    console.info(f"Websites to look up: {len(missing)}")
    console.info(f"Estimated lookup cost: ~${estimated_lookup_cost:.4f}")
    console.info("Automatic retries: disabled")
    if dry_run:
        return 0
    if invalid_rows:
        console.error("Fix invalid rows before enrichment.")
        return 1
    if budget_usd is not None and estimated_lookup_cost > budget_usd:
        console.error(
            f"Enrichment estimate ${estimated_lookup_cost:.4f} exceeds "
            f"--budget ${budget_usd:.2f}. Not starting."
        )
        return 1
    if missing and not skip_confirm:
        decision = prompt_for_approval(
            f"Proceed with {len(missing)} website lookups for an estimated "
            f"${estimated_lookup_cost:.4f}? [y/N] "
        )
        if decision == "unavailable":
            console.error("Interactive approval unavailable. Re-run with --skip-confirm.")
            return 1
        if decision == "declined":
            console.info("Cancelled. No searches or model calls were started.")
            return 0
    logger.info(
        "Batch enrichment approved: lookups=%d estimated_cost_usd=%.6f "
        "approval=%s retries=0 failover=false",
        len(missing),
        estimated_lookup_cost,
        "--skip-confirm" if skip_confirm else "interactive",
    )

    from primr.data.search_utils import lookup_company_website
    from primr.utils.run_budget import clear_run_budget, set_run_budget

    rows: list[dict[str, str]] = []
    unresolved = 0
    lookup_model = str(lookup_estimate["model_name"])
    clear_run_budget()
    try:
        if budget_usd is not None:
            set_run_budget(budget_usd)
        for index, company in enumerate(companies, start=1):
            website = company.website
            if not website:
                console.info(f"[{index}/{len(companies)}] Looking up {company.name}")
                website = lookup_company_website(
                    company.name,
                    context=company.context,
                    model=lookup_model,
                    retries=0,
                    allow_failover=False,
                )
                if not website:
                    unresolved += 1
            rows.append(
                {
                    "company_name": company.name,
                    "website": website or "",
                    "industry": company.industry,
                }
            )
    finally:
        clear_run_budget()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_rows = [{key: _csv_safe(value) for key, value in row.items()} for row in rows]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["company_name", "website", "industry"],
        )
        writer.writeheader()
        writer.writerows(safe_rows)
    console.ok(f"Saved: {output_path}")
    if unresolved:
        console.warn(f"{unresolved} website(s) remain unresolved; add them before research.")
        return 1
    console.info(f'Next step: primr --batch "{output_path}" --dry-run')
    return 0


__all__ = [
    "BatchCompany",
    "BatchPlan",
    "build_batch_plan",
    "enrich_batch",
    "estimate_website_lookup",
    "process_batch",
]
