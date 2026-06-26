"""User-facing budget enforcement descriptions.

The runtime ``RunBudget`` primitive can be activated for any research run, but
only fast-mode full-report stages currently consult it before optional spend.
Keep that distinction in one pure helper so CLI, MCP, and docs tests do not
drift into overpromising.
"""

from __future__ import annotations

from dataclasses import dataclass

_FAST_CHECKPOINTED_MODES = frozenset({"complete", "structured", "hybrid", "full"})
_FAST_CHECKPOINTED_STAGES = (
    "research deepening",
    "cross-validation enrichment",
    "contradiction resolution",
    "strategy generation",
)


@dataclass(frozen=True)
class BudgetEnforcement:
    """How a selected execution profile treats a user-approved budget ceiling."""

    preflight: str
    runtime_checkpoints: bool
    runtime: str
    checkpointed_stages: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe payload for agent surfaces."""
        return {
            "preflight": self.preflight,
            "runtime_checkpoints": self.runtime_checkpoints,
            "runtime": self.runtime,
            "checkpointed_stages": list(self.checkpointed_stages),
        }


def describe_budget_enforcement(
    *, mode: str, fast_mode: bool, premium_mode: bool
) -> BudgetEnforcement:
    """Describe budget behavior for the resolved execution profile."""
    preflight = "refuses to start when the estimated cost exceeds the ceiling"
    if fast_mode and not premium_mode and mode in _FAST_CHECKPOINTED_MODES:
        return BudgetEnforcement(
            preflight=preflight,
            runtime_checkpoints=True,
            runtime=(
                "runtime checkpoints are active for optional fast-mode spend; "
                "core workbook and section-writing calls are not skipped after they start"
            ),
            checkpointed_stages=_FAST_CHECKPOINTED_STAGES,
        )

    return BudgetEnforcement(
        preflight=preflight,
        runtime_checkpoints=False,
        runtime=(
            "estimate-gated only for this mode; mid-run optional-stage budget "
            "checkpoints are not wired for this execution path yet"
        ),
    )
