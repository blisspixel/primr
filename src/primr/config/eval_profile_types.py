"""Immutable role recipes and evaluation profile contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileRecipe:
    """Per-role model assignments for an eval profile slot.

    Each role corresponds to a primr pipeline stage class:
      - reasoning: gap analysis, workbook, cross-validation, strategy
      - writing: bulk section writing, polish
      - utility: scrape summaries, link selection, QA
      - premium_research: Deep Research Agent (premium mode only)

    Roles can be None when the slot inherits the default for that role from
    pick_model_for_role. Unknown roles are accepted but have no effect today;
    they reserve namespace for future pipeline stages.
    """

    reasoning: str | None = None
    writing: str | None = None
    utility: str | None = None
    premium_research: str | None = None
    extra: dict[str, str] | None = None  # forward-compat for new role names

    def role_assignments(self) -> dict[str, str]:
        """Return the populated role → model_id mapping (None entries dropped)."""
        out: dict[str, str] = {}
        if self.reasoning:
            out["reasoning"] = self.reasoning
        if self.writing:
            out["writing"] = self.writing
        if self.utility:
            out["utility"] = self.utility
        if self.premium_research:
            out["premium_research"] = self.premium_research
        if self.extra:
            for k, v in self.extra.items():
                if v:
                    out[k] = v
        return out


@dataclass(frozen=True)
class EvalProfileSlot:
    """One cell in the eval matrix.

    Attributes:
        name: Slot identifier used as the directory name under eval_root and
            in scorecards. Must be filesystem-safe.
        recipe: Optional per-role model assignments. None for legacy profiles
            ("full", "lite", "fast") whose recipe is implicit in primr's mode
            flags rather than a per-role override.
        estimated_cost_usd: Optional fixed-cost override. When None, the
            estimator falls back to the legacy mode-based estimator
            (used by built-in full/lite/fast slots).
        description: Human-readable summary of the recipe (e.g.,
            "Grok 4.3 reasoning + Gemini 3.1 Flash-Lite writing").
        is_builtin: True for the three legacy slots; protects them from
            accidental unregister at module-init.
    """

    name: str
    recipe: ProfileRecipe | None = None
    estimated_cost_usd: float | None = None
    description: str = ""
    is_builtin: bool = False
