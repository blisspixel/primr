"""The ``--dry-run`` handler (cost estimate + recovery table preview).

Extracted from ``cli.py`` to keep that file under its size ceiling. With
``--json`` the estimate and readiness decision are emitted as one JSON object
and the human table/recovery preview is skipped.
"""

from __future__ import annotations

import os

from primr.core.cli_contract import CLIConfig
from primr.core.cli_labels import resolved_full_mode_label as _full_mode_label

_NON_EXECUTABLE_FULL_NOTE = (
    "Dollars are the XAI/Gemini full-recipe planning floor, not OpenAI/Anthropic "
    "live rates. Full execution needs XAI_API_KEY, GEMINI_API_KEY, or an explicitly "
    "enabled OpenRouter route."
)

_UNSUPPORTED_DRY_RUN_MESSAGES: dict[str, tuple[str, str]] = {}


def _routed_strategy_label() -> str:
    """Describe the providers selected for reasoning and writing roles."""

    from primr.ai.routing import Role, pick_model_for_role
    from primr.core.cli_labels import model_provider_label

    reasoning = model_provider_label(pick_model_for_role(Role.REASONING))
    writing = model_provider_label(pick_model_for_role(Role.WRITING))
    if reasoning == writing:
        return reasoning
    return f"{reasoning} reasoning + {writing} writing"


def reject_unsupported_dry_run(config: object) -> int | None:
    """Fail closed when a secondary command cannot produce a safe preview."""
    if not getattr(config, "dry_run_requested", False):
        return None
    command = getattr(config, "command", None)
    messages = _UNSUPPORTED_DRY_RUN_MESSAGES.get(getattr(command, "name", ""))
    if messages is None:
        return None
    from primr.utils.console import console

    console.error(messages[0])
    console.info(messages[1])
    return 1


def _is_full_execution_ready(*, mode: str) -> bool:
    """Return whether the selected full recipe has an executable provider."""
    if mode not in ("complete", "structured", "hybrid"):
        return True
    from primr.ai.providers.openrouter import openrouter_routing_ready

    return bool(
        os.environ.get("XAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or openrouter_routing_ready()
    )


def _annotate_non_executable_full_estimate(estimate, *, mode: str) -> None:
    """Disclose when the quote is planning-only and cannot launch."""
    if _is_full_execution_ready(mode=mode):
        return
    if mode not in ("complete", "structured", "hybrid"):
        return
    notes = list(estimate.notes or [])
    if _NON_EXECUTABLE_FULL_NOTE not in notes:
        notes.append(_NON_EXECUTABLE_FULL_NOTE)
        estimate.notes = notes


def run_dry_run(config: CLIConfig) -> int:
    """Show the cost estimate for a run without executing it."""
    from primr.core.cli_command_output import report_command_error
    from primr.core.cli_inference import (
        inference_estimate_metadata,
        validate_inference_options,
    )

    inference_error = validate_inference_options(
        config.inference_profile,
        config.acknowledge_host_agent_may_bill,
    )
    if inference_error:
        return report_command_error(
            json_output=config.json_output,
            operation="research_estimate",
            error_type="invalid_inference_options",
            message=inference_error,
        )

    # Resolve mode: same logic as _handle_research.
    if config.premium_mode and config.fast_mode:
        return report_command_error(
            json_output=config.json_output,
            operation="research_estimate",
            error_type="incompatible_mode_options",
            message="Cannot use both --fast and --premium. Choose one.",
        )

    from primr.core.cli_budget import resolve_runtime_selection

    selection = resolve_runtime_selection(config)
    use_fast_mode = selection.fast_mode
    use_premium_mode = selection.premium_mode

    # Validate compatibility.
    if use_fast_mode and config.mode not in ("complete", "structured", "hybrid"):
        return report_command_error(
            json_output=config.json_output,
            operation="research_estimate",
            error_type="incompatible_mode_options",
            message=f"--fast only works with full mode, not --mode {config.mode}",
            hints=('Usage: primr "Company" https://url --fast [--platform aws azure] --dry-run',),
        )
    if use_premium_mode and config.mode not in ("complete", "structured", "hybrid"):
        return report_command_error(
            json_output=config.json_output,
            operation="research_estimate",
            error_type="incompatible_mode_options",
            message=f"--premium only works with full mode, not --mode {config.mode}",
        )

    if use_premium_mode:
        mode_label = "premium (Gemini + Deep Research)"
    elif config.mode in ("complete", "structured", "hybrid"):
        # Always use the honest full-mode label (covers keyless + estimate-only keys).
        mode_label = _full_mode_label(config.grok_tier)
    else:
        mode_label = config.mode

    from primr.core.cli_budget import (
        budget_validation_error,
        build_run_estimate,
        estimate_fits_budget,
        strategy_runtime_error,
    )

    runtime_error = strategy_runtime_error(config, fast_mode=use_fast_mode)
    if runtime_error:
        return report_command_error(
            json_output=config.json_output,
            operation="research_estimate",
            error_type="unsupported_strategy_runtime",
            message=runtime_error,
        )

    estimate = build_run_estimate(config, fast_mode=use_fast_mode, premium_mode=use_premium_mode)
    _annotate_non_executable_full_estimate(estimate, mode=config.mode)
    provider_ready = _is_full_execution_ready(mode=config.mode)
    budget_error = budget_validation_error(config.budget_usd)
    if budget_error:
        return report_command_error(
            json_output=config.json_output,
            operation="research_estimate",
            error_type="invalid_budget",
            message=budget_error,
        )
    within_budget = estimate_fits_budget(
        estimated_cost_usd=estimate.total_cost,
        budget_usd=config.budget_usd,
    )
    execution_ready = provider_ready and within_budget is not False

    # Machine-readable path: emit the estimate as JSON and stop.
    if getattr(config, "json_output", False):
        from primr.core.cli_output import cost_estimate_json, emit_json

        budget_enforcement = None
        if config.budget_usd is not None:
            from primr.core.budget_policy import describe_budget_enforcement

            budget_enforcement = describe_budget_enforcement(
                mode=config.mode,
                fast_mode=use_fast_mode,
                premium_mode=use_premium_mode,
            ).as_dict()
            budget_enforcement.update(
                {
                    "ceiling_usd": config.budget_usd,
                    "estimated_cost_usd": estimate.total_cost,
                    "within_budget": within_budget,
                }
            )
        payload = cost_estimate_json(
            estimate,
            mode_label=mode_label,
            ai_strategy=config.ai_strategy,
            budget_enforcement=budget_enforcement,
            inference=inference_estimate_metadata(config),
        )
        payload["provider_ready"] = provider_ready
        payload["execution_ready"] = execution_ready
        emit_json(payload)
        return 0

    from primr.utils.console import console

    console.header("Cost estimate", mode_label)
    if config.ai_strategy and not use_fast_mode:
        strategy_label = (
            "AI Strategy (Pro mode)" if config.lite_strategy else "AI Strategy analysis"
        )
        console.muted(f"Includes {strategy_label}")
    elif use_fast_mode and config.ai_strategy:
        console.muted(f"Includes AI Strategy ({_routed_strategy_label()})")
    console.blank()
    # CostEstimate.__str__ is the multi-line planning breakdown operators expect.
    for line in str(estimate).splitlines():
        console.text(line)

    if config.budget_usd is not None:
        from primr.core.budget_policy import describe_budget_enforcement

        budget_policy = describe_budget_enforcement(
            mode=config.mode,
            fast_mode=use_fast_mode,
            premium_mode=use_premium_mode,
        )
        console.blank()
        console.step("Budget policy")
        budget_state = "within ceiling" if within_budget else "exceeds ceiling; launch blocked"
        console.detail("Ceiling", f"${config.budget_usd:.2f}")
        console.detail("Estimate", f"${estimate.total_cost:.2f} ({budget_state})")
        console.detail("Pre-flight", budget_policy.preflight)
        console.detail("Runtime", budget_policy.runtime)
        if budget_policy.checkpointed_stages:
            stages = ", ".join(budget_policy.checkpointed_stages)
            console.detail("Checkpointed stages", stages)

    if not config.skip_recon:
        console.blank()
        console.step("Recon pre-flight")
        console.detail("DNS intelligence", "$0.00  (~2-3 seconds, no API keys)")
    else:
        console.blank()
        console.muted("Recon pre-flight skipped (--skip-recon)")

    # Recovery table is operator internals; keep progressive disclosure quiet.
    from primr.pipeline.recovery import build_default_recovery_table
    from primr.pipeline.stages import STAGE_CLASSIFICATIONS

    recovery_table = build_default_recovery_table()
    stage_count = len(recovery_table.hierarchies)
    if config.verbose:
        console.blank()
        console.step(f"Recovery table ({stage_count} stages)")
        for stage, hierarchy in recovery_table.hierarchies.items():
            classification = STAGE_CLASSIFICATIONS[stage].value
            actions = ", ".join(a.action_type.value for a in hierarchy.actions)
            console.muted(f"  {stage.value} ({classification}): {actions}")
        console.blank()
        console.muted("Recovery table JSON:")
        console.text(recovery_table.to_json())
    else:
        console.blank()
        console.muted(f"Recovery: {stage_count} stages configured (pass --verbose to list actions)")

    console.blank()
    console.step("Next steps")
    if not provider_ready:
        console.muted(
            "  1. Configure XAI_API_KEY or GEMINI_API_KEY, or explicitly enable "
            "an OpenRouter route before launching."
        )
        console.muted(
            "  2. Re-run this dry-run after keys are set to confirm the executable recipe."
        )
        console.muted(
            "  3. Launch: repeat without --dry-run once execution_ready is true "
            "(optional: --budget <usd>)."
        )
    elif within_budget is False:
        console.muted(
            f"  1. Launch is blocked because ${estimate.total_cost:.2f} exceeds "
            f"--budget ${config.budget_usd:.2f}."
        )
        console.muted("  2. Raise the ceiling or choose a cheaper route, then repeat this dry-run.")
        console.muted("  3. Launch only after the estimate is within the approved ceiling.")
    else:
        console.muted("  1. Launch: repeat this command without --dry-run.")
        console.muted("     Optional: add --budget <usd> to enforce a run ceiling.")
        console.muted("  2. Monitor: follow the phase markers in this terminal.")
        console.muted(
            "  3. Recover interrupted cloud work: primr --check-jobs; "
            "when completed, run primr --resume-latest."
        )
        console.muted(
            "  4. Retrieve: use the artifact path printed when the run completes "
            "(or primr --list-recent)."
        )
    console.blank()
    return 0
