"""The ``--dry-run`` handler (cost estimate + recovery table preview).

Extracted from ``cli.py`` to keep that file under its size ceiling. Behavior is
unchanged from the inline version, plus a ``--json`` branch: with ``--json`` the
estimate is emitted as a single JSON object (estimate-first for agents) and the
human table/recovery preview is skipped.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from primr.utils.console import console

if TYPE_CHECKING:
    from primr.core.cli import CLIConfig


def run_dry_run(config: CLIConfig) -> int:
    """Show the cost estimate for a run without executing it."""
    from primr.utils.cost_estimator import estimate_cost

    # Resolve mode: same logic as _handle_research.
    if config.premium_mode and config.fast_mode:
        console.error("Cannot use both --fast and --premium. Choose one.")
        return 1

    use_fast_mode = config.fast_mode
    use_premium_mode = config.premium_mode

    if (
        not use_fast_mode
        and not use_premium_mode
        and config.mode in ("complete", "structured", "hybrid")
    ):
        if os.environ.get("XAI_API_KEY"):
            use_fast_mode = True

    # Validate compatibility.
    if use_fast_mode and config.mode not in ("complete", "structured", "hybrid"):
        console.error(f"--fast only works with full mode, not --mode {config.mode}")
        console.info('Usage: primr "Company" https://url --fast [--platform aws azure] --dry-run')
        return 1
    if use_premium_mode and config.mode not in ("complete", "structured", "hybrid"):
        console.error(f"--premium only works with full mode, not --mode {config.mode}")
        return 1

    tier_labels = {"fast": "Grok 4.1", "hybrid": "Grok 4.3 hybrid", "max": "Grok 4.3 max"}
    if use_premium_mode:
        mode_label = "premium (Gemini + Deep Research)"
    elif use_fast_mode:
        mode_label = f"standard ({tier_labels.get(config.grok_tier, 'Grok')})"
    else:
        mode_label = config.mode

    estimate = estimate_cost(
        config.mode,
        config.ai_strategy,
        num_vendors=len(config.cloud_vendors),
        lite_strategy=config.lite_strategy,
        fast_mode=use_fast_mode,
        premium_mode=use_premium_mode,
        grok_tier=config.grok_tier,
    )

    # Machine-readable path: emit the estimate as JSON and stop.
    if getattr(config, "json_output", False):
        from primr.core.cli_output import cost_estimate_json, emit_json

        emit_json(
            cost_estimate_json(estimate, mode_label=mode_label, ai_strategy=config.ai_strategy)
        )
        return 0

    print("")
    print("=" * 60)
    print(f"COST ESTIMATE: {mode_label} mode")
    if config.ai_strategy and not use_fast_mode:
        strategy_label = (
            "AI Strategy (Pro mode)" if config.lite_strategy else "AI Strategy analysis"
        )
        print(f"(includes {strategy_label})")
    elif use_fast_mode and config.ai_strategy:
        print("(includes AI Strategy via Grok)")
    print("=" * 60)
    print("")
    print(str(estimate))

    # Recon pre-flight step (DNS intelligence — no API cost)
    if not config.skip_recon:
        print("")
        print("RECON PRE-FLIGHT")
        print("-" * 40)
        print("  DNS intelligence lookup:  $0.00  (~2-3 seconds)")
        print("  (no API keys required)")
    else:
        print("")
        print("RECON PRE-FLIGHT: skipped (--skip-recon)")

    # Recovery table summary (pipeline-resilience feature)
    print("")
    print("RECOVERY TABLE")
    print("-" * 40)
    from primr.pipeline.recovery import build_default_recovery_table
    from primr.pipeline.stages import STAGE_CLASSIFICATIONS

    recovery_table = build_default_recovery_table()
    for stage, hierarchy in recovery_table.hierarchies.items():
        classification = STAGE_CLASSIFICATIONS[stage].value
        actions = ", ".join(a.action_type.value for a in hierarchy.actions)
        print(f"  {stage.value} ({classification}): {actions}")
    print("")
    print("Recovery Table JSON:")
    print(recovery_table.to_json())

    print("")
    print("=" * 60)
    print("")
    print("To run research, remove --dry-run flag")
    return 0
