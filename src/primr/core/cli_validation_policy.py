"""CLI validation policy helpers."""

from __future__ import annotations

from typing import Any

UTILITY_COMMAND_VALUES = frozenset(
    {
        "init",
        "doctor",
        "list-recent",
        "clean-temp",
        "check-jobs",
        "clear-jobs",
        "list-strategies",
        "show-usage",
        "enrich",
        "eval",
        "improve",
    }
)


def should_include_api_keys(config: Any) -> bool:
    """Return whether top-level config validation should require provider keys."""
    command_value = _command_value(getattr(config, "command", ""))
    include_api_keys = command_value not in UTILITY_COMMAND_VALUES
    if _is_local_calibration_artifact_command(config, command_value=command_value):
        include_api_keys = False
    if command_value == "eval" and getattr(config, "eval_run_missing", False):
        include_api_keys = True
    return include_api_keys


def _is_local_calibration_artifact_command(config: Any, *, command_value: str) -> bool:
    return command_value == "calibrate" and any(
        (
            getattr(config, "calibrate_inspect_baseline_decision", None),
            getattr(config, "calibrate_baseline_decision_from", None),
            getattr(config, "calibrate_baseline_decision_out", None),
            getattr(config, "calibrate_baseline_decision", None),
            getattr(config, "calibrate_baseline_decision_reviewer", None),
            getattr(config, "calibrate_baseline_decision_rationale", None),
            getattr(config, "calibrate_baseline_decision_notes", ()),
        )
    )


def _command_value(command: Any) -> str:
    return str(getattr(command, "value", command))
