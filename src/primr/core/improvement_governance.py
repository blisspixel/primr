"""Cost governance for model-backed report improvement commands.

The two public commands governed here have bounded execution shapes:

* ``improve --improve-agentic`` can review once, make one format-correction
  request, and polish once.
* ``refine`` can regenerate at most three sections in each of three
  iterations and can run one bounded acceptance audit per iteration.

Quotes use conservative token ceilings for those shapes. Runtime reservations
are taken before each model-backed stage so ``--budget`` remains a real cap
rather than presentation-only metadata. Deterministic ``improve`` never enters
this model gate.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol

from primr.core.cli_command_output import emit_json, suppress_json_command_stdout
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)

_REFINE_MAX_ITERATIONS = 3
_REFINE_MAX_SECTIONS_PER_ITERATION = 3
_REFINE_MAX_REGENERATIONS = _REFINE_MAX_ITERATIONS * _REFINE_MAX_SECTIONS_PER_ITERATION
_ACCEPTANCE_MAX_CLAIMS_PER_LABEL = 10
_ACCEPTANCE_TRACEABLE_LABELS = 2
_ACCEPTANCE_MAX_SOURCES_PER_CLAIM = 2
_ACCEPTANCE_SNAPSHOTS_PER_ITERATION = 2
_ACCEPTANCE_JUDGES_PER_ITERATION = (
    _ACCEPTANCE_MAX_CLAIMS_PER_LABEL
    * _ACCEPTANCE_TRACEABLE_LABELS
    * _ACCEPTANCE_MAX_SOURCES_PER_CLAIM
    * _ACCEPTANCE_SNAPSHOTS_PER_ITERATION
)


class _ImprovementConfig(Protocol):
    @property
    def improve_path(self) -> str | None: ...

    @property
    def improve_in_place(self) -> bool: ...

    @property
    def improve_agentic(self) -> bool: ...

    @property
    def refine_company(self) -> str | None: ...

    @property
    def refine_target_grade(self) -> float: ...

    @property
    def dry_run_requested(self) -> bool: ...

    @property
    def json_output(self) -> bool: ...

    @property
    def skip_confirm(self) -> bool: ...

    @property
    def budget_usd(self) -> float | None: ...


class _RefineResult(Protocol):
    initial_grade: float
    final_grade: float
    iterations: int
    sections_regenerated: list[str]
    stop_reason: str
    output_path: str | None


@dataclass(frozen=True)
class ImprovementStageEstimate:
    """One reservable stage in a bounded improvement command."""

    name: str
    max_invocations: int
    model_tasks_per_invocation: int
    cost_per_invocation_usd: float

    @property
    def max_model_tasks(self) -> int:
        return self.max_invocations * self.model_tasks_per_invocation

    @property
    def estimated_cost_usd(self) -> float:
        return self.max_invocations * self.cost_per_invocation_usd

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "max_invocations": self.max_invocations,
            "max_model_tasks": self.max_model_tasks,
            "cost_per_invocation_usd": self.cost_per_invocation_usd,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


@dataclass(frozen=True)
class ImprovementEstimate:
    """Conservative quote for one exact improve or refine command."""

    operation: str
    stages: tuple[ImprovementStageEstimate, ...]
    model_names: tuple[str, ...]
    estimated_time_range: str
    cost_basis: str

    @property
    def max_model_tasks(self) -> int:
        return sum(stage.max_model_tasks for stage in self.stages)

    @property
    def estimated_cost_usd(self) -> float:
        return round(sum(stage.estimated_cost_usd for stage in self.stages), 6)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "primr.improvement-estimate.v1",
            "operation": self.operation,
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_time_range": self.estimated_time_range,
            "max_model_tasks": self.max_model_tasks,
            "model_names": list(self.model_names),
            "stages": [stage.as_dict() for stage in self.stages],
            "cost_basis": self.cost_basis,
        }


class ImprovementBudgetError(RuntimeError):
    """Raised before a stage whose reservation would exceed the approved cap."""


def _round_up_usd(value: float) -> float:
    """Round up to a micro-dollar so the quote never understates its inputs."""
    return math.ceil(max(0.0, value) * 1_000_000) / 1_000_000


def _model_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    *,
    role: str,
) -> float:
    from primr.config.models import PrimrModels
    from primr.pipeline.model_breaker import ANALYSIS_FALLBACK_CHAIN, UTILITY_FALLBACK_CHAIN

    chain = ANALYSIS_FALLBACK_CHAIN if role == "reasoning" else UTILITY_FALLBACK_CHAIN
    candidates = tuple(dict.fromkeys((model_name, *chain.models)))
    costs = [
        PrimrModels.calculate_cost_conservative(candidate, input_tokens, output_tokens)
        for candidate in candidates
        if PrimrModels.get_model_config(candidate) is not None
    ]
    if not costs:
        raise ValueError(f"No pricing is registered for improvement model {model_name}")
    return _round_up_usd(max(costs))


def _routed_models() -> tuple[str, str, str]:
    from primr.ai.routing import Role, pick_model_for_legacy_type, pick_model_for_role

    return (
        pick_model_for_role(Role.REASONING),
        pick_model_for_role(Role.WRITING),
        pick_model_for_legacy_type("fast"),
    )


def estimate_agentic_improve(content: str, *, is_strategy: bool) -> ImprovementEstimate:
    """Price the maximum model task shape for ``improve --improve-agentic``."""
    reasoning_model, writing_model, _judge_model = _routed_models()
    bounded_review_chars = min(len(content), 120_000)
    review_output = 4_000 if is_strategy else 5_000
    review_cost = _model_cost(
        reasoning_model,
        bounded_review_chars + 4_000,
        review_output,
        role="reasoning",
    )
    retry_cost = 0.0
    review_tasks = 1
    if not is_strategy:
        retry_cost = _model_cost(reasoning_model, 4_000, 3_000, role="reasoning")
        review_tasks = 2

    polish_output = 32_000 if is_strategy else 10_000
    polish_cost = _model_cost(
        writing_model,
        len(content) + 6_000,
        polish_output,
        role="writing",
    )
    stages = (
        ImprovementStageEstimate(
            name="review",
            max_invocations=1,
            model_tasks_per_invocation=review_tasks,
            cost_per_invocation_usd=_round_up_usd(review_cost + retry_cost),
        ),
        ImprovementStageEstimate(
            name="polish",
            max_invocations=1,
            model_tasks_per_invocation=1,
            cost_per_invocation_usd=polish_cost,
        ),
    )
    return ImprovementEstimate(
        operation="agentic_improve",
        stages=stages,
        model_names=tuple(dict.fromkeys((reasoning_model, writing_model))),
        estimated_time_range="2-10 min",
        cost_basis=(
            "Maximum command shape: one review, one report-only format correction, "
            "and one polish. Input is priced from the selected file, review input is "
            "capped exactly as execution caps it, output uses each task's token ceiling, "
            "and pricing uses the highest published tier across the selected model's "
            "role fallback chain. Actual work may stop after review when no issues are "
            "found."
        ),
    )


def estimate_refine(content: str) -> ImprovementEstimate:
    """Price the bounded three-iteration ``refine`` loop."""
    _reasoning_model, writing_model, judge_model = _routed_models()
    # One rewrite can include a report section, 20k workbook characters,
    # 48k gathered evidence characters, and the source inventory. Counting one
    # token per character is deliberately conservative for the authorization cap.
    regeneration_input_tokens = len(content) * 2 + 72_000
    regeneration_cost = _model_cost(
        writing_model,
        regeneration_input_tokens,
        5_000,
        role="writing",
    )
    judge_cost = _model_cost(judge_model, 5_200, 64, role="writing")
    acceptance_cost = _round_up_usd(judge_cost * _ACCEPTANCE_JUDGES_PER_ITERATION)
    stages = (
        ImprovementStageEstimate(
            name="regenerate",
            max_invocations=_REFINE_MAX_REGENERATIONS,
            model_tasks_per_invocation=1,
            cost_per_invocation_usd=regeneration_cost,
        ),
        ImprovementStageEstimate(
            name="acceptance",
            max_invocations=_REFINE_MAX_ITERATIONS,
            model_tasks_per_invocation=_ACCEPTANCE_JUDGES_PER_ITERATION,
            cost_per_invocation_usd=acceptance_cost,
        ),
    )
    return ImprovementEstimate(
        operation="refine",
        stages=stages,
        model_names=tuple(dict.fromkeys((writing_model, judge_model))),
        estimated_time_range="10-90 min",
        cost_basis=(
            "Maximum command shape: three iterations, three regenerated sections per "
            "iteration, and one before/after acceptance audit per iteration. Each audit "
            "samples at most ten Confirmed and ten Reported claims, with two sources per "
            "claim. Inputs use one token per character and pricing uses the highest "
            "published tier across each selected model's role fallback chain. The loop "
            "normally stops earlier."
        ),
    )


def deterministic_improve_estimate() -> ImprovementEstimate:
    """Return the zero-model-call preview for ordinary deterministic improve."""
    return ImprovementEstimate(
        operation="deterministic_improve",
        stages=(),
        model_names=(),
        estimated_time_range="under 1 min",
        cost_basis="Deterministic local cleanup only. No model calls are permitted.",
    )


class ImprovementBudgetGate:
    """Reserve quoted stage costs against the active process run budget."""

    def __init__(self, estimate: ImprovementEstimate, cap_usd: float) -> None:
        self.estimate = estimate
        self.cap_usd = cap_usd
        self.spent_usd = 0.0
        self._counts: dict[str, int] = {}
        self._stages = {stage.name: stage for stage in estimate.stages}

    def before_model_stage(self, stage_name: str) -> None:
        """Reserve one bounded stage before it can start provider work."""
        stage = self._stages.get(stage_name)
        if stage is None:
            raise ImprovementBudgetError(f"Unquoted model stage: {stage_name}")
        count = self._counts.get(stage_name, 0)
        if count >= stage.max_invocations:
            raise ImprovementBudgetError(
                f"Model stage {stage_name} exceeded its quoted invocation count"
            )
        next_spend = self.spent_usd + stage.cost_per_invocation_usd
        if next_spend > self.cap_usd + 0.0000005:
            raise ImprovementBudgetError(
                f"Approved cap ${self.cap_usd:.6f} cannot cover {stage_name}; "
                f"${self.spent_usd:.6f} reserved"
            )
        self._counts[stage_name] = count + 1
        self.spent_usd = next_spend
        from primr.utils.run_budget import get_run_budget

        active = get_run_budget()
        if active is not None:
            active.sync_spend(self.spent_usd)


@contextmanager
def _active_improvement_budget(
    estimate: ImprovementEstimate,
    budget_usd: float | None,
):
    """Activate the canonical process budget and always clear it after execution."""
    from primr.utils.run_budget import clear_run_budget, set_run_budget

    cap = budget_usd if budget_usd is not None else estimate.estimated_cost_usd
    gate = ImprovementBudgetGate(estimate, cap)
    if cap > 0:
        set_run_budget(cap)
    try:
        yield gate
    finally:
        clear_run_budget()


def _estimate_payload(
    estimate: ImprovementEstimate,
    budget_usd: float | None,
) -> dict[str, object]:
    payload = estimate.as_dict()
    if budget_usd is not None:
        payload["budget_usd"] = budget_usd if isfinite(budget_usd) else None
        payload["within_budget"] = (
            isfinite(budget_usd) and budget_usd > 0 and estimate.estimated_cost_usd <= budget_usd
        )
    return payload


def _format_cost(cost: float) -> str:
    return f"${cost:.4f}" if 0 < cost < 0.01 else f"${cost:.2f}"


def _emit_estimate(
    config: _ImprovementConfig,
    estimate: ImprovementEstimate,
) -> None:
    payload = _estimate_payload(estimate, config.budget_usd)
    if config.json_output:
        payload["dry_run"] = True
        emit_json(payload)
        return
    console.header("Improvement Estimate")
    console.info(f"Operation: {estimate.operation.replace('_', ' ')}")
    console.info(f"Model tasks: up to {estimate.max_model_tasks}")
    console.info(f"Estimated cost: ~{_format_cost(estimate.estimated_cost_usd)}")
    console.info(f"Estimated time: {estimate.estimated_time_range}")
    if config.budget_usd is not None:
        state = "within" if payload["within_budget"] else "exceeds"
        console.info(f"Budget: estimate {state} ${config.budget_usd:.2f}")


def _report_error(
    config: _ImprovementConfig,
    estimate: ImprovementEstimate | None,
    *,
    error_type: str,
    message: str,
    hints: tuple[str, ...] = (),
) -> int:
    if config.json_output:
        payload: dict[str, object] = {
            "schema_version": "primr.improvement-command.v1",
            "operation": estimate.operation if estimate else "improvement",
            "status": "not_started",
            "error": True,
            "error_type": error_type,
            "message": message,
        }
        if estimate is not None:
            payload["estimate"] = _estimate_payload(estimate, config.budget_usd)
        if hints:
            payload["hints"] = list(hints)
        emit_json(payload)
        return 1
    console.error(message)
    for hint in hints:
        console.info(hint)
    return 1


def _validate_budget(
    config: _ImprovementConfig,
    estimate: ImprovementEstimate,
) -> int | None:
    if config.budget_usd is None:
        return None
    if not isfinite(config.budget_usd) or config.budget_usd <= 0:
        return _report_error(
            config,
            estimate,
            error_type="invalid_budget",
            message=f"--budget must be a finite positive number, got {config.budget_usd}",
        )
    if estimate.estimated_cost_usd > config.budget_usd:
        return _report_error(
            config,
            estimate,
            error_type="budget_exceeded",
            message=(
                f"Estimated cost ${estimate.estimated_cost_usd:.6f} exceeds "
                f"--budget ${config.budget_usd:.2f}. Not starting."
            ),
        )
    return None


def _approve(config: _ImprovementConfig, estimate: ImprovementEstimate) -> tuple[bool, str]:
    if config.json_output and not config.skip_confirm:
        return False, "approval_required"
    if not config.json_output:
        _emit_estimate(config, estimate)
    if config.skip_confirm:
        return True, "--skip-confirm"
    try:
        response = input("Proceed with model-backed improvement? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.info("Cancelled. No model calls were started.")
        return False, "cancelled"
    if response not in {"y", "yes"}:
        console.info("Cancelled. No model calls were started.")
        return False, "cancelled"
    return True, "interactive"


def _load_improve_input(config: _ImprovementConfig) -> tuple[Path, str] | int:
    if not config.improve_path:
        return _report_error(
            config,
            None,
            error_type="missing_path",
            message="Path is required for improve.",
            hints=('Usage: primr improve "path/to/output.md" [--in-place]',),
        )
    path = Path(config.improve_path)
    if not path.exists() or not path.is_file():
        return _report_error(
            config,
            None,
            error_type="file_not_found",
            message=f"Improve failed: file not found: {config.improve_path}",
        )
    if path.suffix.lower() not in {".md", ".txt"}:
        return _report_error(
            config,
            None,
            error_type="unsupported_file_type",
            message="Improve supports .md or .txt files.",
        )
    try:
        return path, path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return _report_error(
            config,
            None,
            error_type="file_read_failed",
            message="Improve could not read the input file.",
        )


def handle_improve(
    config: _ImprovementConfig,
    *,
    improve_output_file: Callable[..., str | None],
) -> int:
    """Run deterministic or model-backed improve with the appropriate policy."""
    if not config.improve_agentic:
        estimate = deterministic_improve_estimate()
        if not config.improve_path:
            return _report_error(
                config,
                estimate,
                error_type="missing_path",
                message="Path is required for improve.",
            )
        if config.dry_run_requested:
            loaded = _load_improve_input(config)
            if isinstance(loaded, int):
                return loaded
            _emit_estimate(config, estimate)
            return 0
        with suppress_json_command_stdout(config.json_output):
            result_path = improve_output_file(
                config.improve_path, in_place=config.improve_in_place, use_agentic=False
            )
        if not result_path:
            return _report_error(
                config,
                estimate,
                error_type="execution_failed",
                message="Deterministic improve did not produce an artifact.",
            )
        if config.json_output:
            emit_json(
                {
                    "schema_version": "primr.improvement-result.v1",
                    "operation": estimate.operation,
                    "status": "completed",
                    "error": False,
                    "estimate": _estimate_payload(estimate, config.budget_usd),
                    "artifact": result_path,
                }
            )
        else:
            action = "Updated" if config.improve_in_place else "Improved"
            console.success_box(f"{action} output", result_path)
        return 0

    loaded = _load_improve_input(config)
    if isinstance(loaded, int):
        return loaded
    path, content = loaded
    is_strategy = "# AI Strategy:" in content or "_AI_Strategy_" in path.name
    estimate = estimate_agentic_improve(content, is_strategy=is_strategy)
    budget_error = _validate_budget(config, estimate)
    if budget_error is not None:
        return budget_error
    if config.dry_run_requested:
        _emit_estimate(config, estimate)
        return 0
    approved, approval_source = _approve(config, estimate)
    if not approved:
        if approval_source == "approval_required":
            return _report_error(
                config,
                estimate,
                error_type="approval_required",
                message="Execution requires explicit approval. Re-run with --skip-confirm.",
                hints=("Use --dry-run --json to inspect the estimate first.",),
            )
        return 0

    logger.info(
        "Agentic improve approved: max_tasks=%d estimated_cost_usd=%.6f approval=%s",
        estimate.max_model_tasks,
        estimate.estimated_cost_usd,
        approval_source,
    )
    try:
        with (
            _active_improvement_budget(estimate, config.budget_usd) as gate,
            suppress_json_command_stdout(config.json_output),
        ):
            result_path = improve_output_file(
                str(path),
                in_place=config.improve_in_place,
                use_agentic=True,
                before_model_stage=gate.before_model_stage,
            )
    except ImprovementBudgetError as exc:
        return _report_error(
            config,
            estimate,
            error_type="budget_exceeded",
            message=f"Model-backed improve stopped before exceeding its cap: {exc}",
        )
    if not result_path:
        return _report_error(
            config,
            estimate,
            error_type="execution_failed",
            message="Model-backed improve did not produce an artifact.",
        )
    if config.json_output:
        emit_json(
            {
                "schema_version": "primr.improvement-result.v1",
                "operation": estimate.operation,
                "status": "completed",
                "error": False,
                "estimate": _estimate_payload(estimate, config.budget_usd),
                "approval_source": approval_source,
                "artifact": result_path,
            }
        )
    else:
        action = "Updated" if config.improve_in_place else "Improved"
        console.success_box(f"{action} output", result_path)
    return 0


def handle_refine(
    config: _ImprovementConfig,
    *,
    find_inputs: Callable[[str], tuple[str | None, str | None, str, str | None]],
    refine_report: Callable[..., _RefineResult],
    output_dir: str,
) -> int:
    """Run the bounded QA refinement loop after estimate and approval."""
    company = config.refine_company
    if not company:
        return _report_error(
            config,
            None,
            error_type="missing_company",
            message="Company name is required for refine.",
            hints=('Usage: primr refine "Company Name" [--target-grade 90]',),
        )
    report_path, website, workbook, working_folder = find_inputs(company)
    if not report_path:
        return _report_error(
            config,
            None,
            error_type="report_not_found",
            message=f"No markdown Strategic Overview found for '{company}' in {output_dir}",
        )
    try:
        content = Path(report_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return _report_error(
            config,
            None,
            error_type="file_read_failed",
            message="Refine could not read the selected report.",
        )

    estimate = estimate_refine(content)
    budget_error = _validate_budget(config, estimate)
    if budget_error is not None:
        return budget_error
    if config.dry_run_requested:
        _emit_estimate(config, estimate)
        return 0
    approved, approval_source = _approve(config, estimate)
    if not approved:
        if approval_source == "approval_required":
            return _report_error(
                config,
                estimate,
                error_type="approval_required",
                message="Execution requires explicit approval. Re-run with --skip-confirm.",
                hints=("Use --dry-run --json to inspect the estimate first.",),
            )
        return 0

    logger.info(
        "Refine approved: company=%s max_tasks=%d estimated_cost_usd=%.6f approval=%s",
        company,
        estimate.max_model_tasks,
        estimate.estimated_cost_usd,
        approval_source,
    )
    if not config.json_output:
        console.banner("QA Refine")
        console.info(f"Report: {report_path}")
        if working_folder:
            console.info(f"Run context: {working_folder}")
        console.info(f"Target grade: {config.refine_target_grade:.0f}")

    try:
        with (
            _active_improvement_budget(estimate, config.budget_usd) as gate,
            suppress_json_command_stdout(config.json_output),
        ):
            result = refine_report(
                company,
                report_path,
                website=website,
                working_folder=working_folder,
                analysis_workbook=workbook,
                target_grade=config.refine_target_grade,
                in_place=config.improve_in_place,
                before_model_stage=gate.before_model_stage,
            )
    except ImprovementBudgetError as exc:
        return _report_error(
            config,
            estimate,
            error_type="budget_exceeded",
            message=f"Refine stopped before exceeding its cap: {exc}",
        )

    if config.json_output:
        emit_json(
            {
                "schema_version": "primr.improvement-result.v1",
                "operation": estimate.operation,
                "status": "completed",
                "error": False,
                "estimate": _estimate_payload(estimate, config.budget_usd),
                "approval_source": approval_source,
                "company": company,
                "initial_grade": result.initial_grade,
                "final_grade": result.final_grade,
                "iterations": result.iterations,
                "sections_regenerated": list(result.sections_regenerated),
                "stop_reason": result.stop_reason,
                "artifact": result.output_path,
            }
        )
        return 0

    console.info(
        f"Grade: {result.initial_grade:.0f} -> {result.final_grade:.0f} "
        f"({result.iterations} iteration(s), "
        f"{len(result.sections_regenerated)} section(s) regenerated)"
    )
    console.info(f"Stop reason: {result.stop_reason.replace('_', ' ')}")
    if result.output_path:
        console.success_box("Refined output", result.output_path)
    else:
        console.ok("No sections needed regeneration; report left unchanged")
    return 0


__all__ = [
    "ImprovementBudgetError",
    "ImprovementBudgetGate",
    "ImprovementEstimate",
    "ImprovementStageEstimate",
    "deterministic_improve_estimate",
    "estimate_agentic_improve",
    "estimate_refine",
    "handle_improve",
    "handle_refine",
]
