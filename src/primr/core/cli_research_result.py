"""Research-command completion assessment and structured handoff."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from primr.core.strategy_outcome import StrategyOutcome
from primr.core.vendor_refresh_outcome import VendorRefreshOutcome
from primr.utils.console import console


@dataclass(frozen=True)
class ResearchFulfillmentAssessment:
    """Canonical completion assessment for one research artifact and run state."""

    status: str
    strategy_outcome: StrategyOutcome | None
    vendor_refresh_outcome: VendorRefreshOutcome | None
    state_available: bool
    run_state_path: str | None


def assess_research_fulfillment(
    result_path: str | None,
    working_folder: str | None,
) -> ResearchFulfillmentAssessment:
    """Assess requested work without emitting output or opening the artifact."""

    from primr.core.strategy_outcome import load_strategy_outcome
    from primr.core.vendor_refresh_outcome import load_vendor_refresh_outcome

    strategy_outcome = load_strategy_outcome(working_folder)
    refresh_outcome = load_vendor_refresh_outcome(working_folder)
    state_available = strategy_outcome is not None and refresh_outcome is not None
    incomplete = bool(
        (strategy_outcome and strategy_outcome.requires_nonzero_exit)
        or (refresh_outcome and refresh_outcome.requires_nonzero_exit)
    )
    return ResearchFulfillmentAssessment(
        status=_fulfillment_status(
            result_path,
            state_available=state_available,
            incomplete=incomplete,
        ),
        strategy_outcome=strategy_outcome,
        vendor_refresh_outcome=refresh_outcome,
        state_available=state_available,
        run_state_path=_run_state_path(working_folder),
    )


def finalize_research_command(
    *,
    result_path: str | None,
    run_context: dict[str, str],
    company_name: str,
    website: str,
    mode: str,
    json_output: bool,
    open_after: bool,
    open_result: Callable[[str], None],
) -> int:
    """Return truthful CLI status while preserving a completed base artifact."""

    working_folder = run_context.get("working_folder")
    from primr.core.research_artifact_binding import bind_primary_artifact

    binding_available = bind_primary_artifact(working_folder, result_path)
    assessment = assess_research_fulfillment(result_path, working_folder)
    strategy_outcome = assessment.strategy_outcome
    refresh_outcome = assessment.vendor_refresh_outcome
    state_path = assessment.run_state_path
    state_available = assessment.state_available
    strategy_incomplete = bool(strategy_outcome and strategy_outcome.requires_nonzero_exit)
    refresh_incomplete = bool(refresh_outcome and refresh_outcome.requires_nonzero_exit)
    fulfillment_status = assessment.status

    if strategy_incomplete and not json_output:
        _warn_strategy_outcome(strategy_outcome, result_path, state_path)
    if refresh_incomplete and not json_output:
        _warn_refresh_outcome(refresh_outcome, result_path, state_path)
    if result_path and not state_available and not json_output:
        _warn_unknown_outcome_state(result_path, state_path)
    if (
        result_path
        and working_folder
        and Path(result_path).is_file()
        and not binding_available
        and not json_output
    ):
        console.warn(
            "Resume verification could not bind this report to its run state. "
            "A later batch run will require a fresh estimate."
        )

    if open_after and result_path:
        open_result(result_path)

    if json_output:
        from primr.core.cli_output import emit_json, research_result_json

        emit_json(
            research_result_json(
                result_path,
                company=company_name,
                website=website,
                mode=mode,
                strategy_outcome=strategy_outcome,
                vendor_refresh_outcome=refresh_outcome,
                fulfillment_status=fulfillment_status,
                outcome_state_status="available" if state_available else "unavailable",
                run_state_path=state_path,
            )
        )

    return 0 if fulfillment_status == "completed" else 1


def _run_state_path(working_folder: str | None) -> str | None:
    if not working_folder:
        return None
    return str((Path(working_folder) / "_run_state.json").resolve())


def _fulfillment_status(
    result_path: str | None,
    *,
    state_available: bool,
    incomplete: bool,
) -> str:
    if not result_path or not Path(result_path).is_file():
        return "failed"
    if not state_available:
        return "unknown"
    return "partial" if incomplete else "completed"


def _items(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _warn_strategy_outcome(
    outcome: StrategyOutcome,
    result_path: str | None,
    state_path: str | None,
) -> None:
    console.warn(
        f"Strategy fulfillment {outcome.status.upper()}. "
        f"Completed: {_items(outcome.completed_targets)}. "
        f"Failed: {_items(outcome.failed_targets)}. "
        f"Skipped: {_items(outcome.skipped_targets)}. "
        f"Base report preserved: {result_path}. Run state: {state_path}. "
        "Review a fresh dry-run before retrying only the unresolved targets."
    )


def _warn_refresh_outcome(
    outcome: VendorRefreshOutcome,
    result_path: str | None,
    state_path: str | None,
) -> None:
    console.warn(
        f"Vendor refresh fulfillment {outcome.status.upper()}. "
        f"Completed: {_items(outcome.completed_vendors)}. "
        f"Failed: {_items(outcome.failed_vendors)}. "
        f"Skipped: {_items(outcome.skipped_vendors)}. "
        f"Base report preserved: {result_path}. Run state: {state_path}. "
        "Review a fresh dry-run before retrying only the unresolved vendors."
    )


def _warn_unknown_outcome_state(result_path: str, state_path: str | None) -> None:
    console.warn(
        "Outcome verification is unavailable because the run state is missing or unreadable. "
        f"Base report preserved: {result_path}. Run state: {state_path or 'unavailable'}. "
        "Inspect the run state and logs before assuming requested strategy or refresh work completed."
    )
