"""Evaluation profile registration without runtime or runner dependencies."""

from __future__ import annotations

from math import isfinite

from primr.config.eval_profile_types import EvalProfileSlot
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)

_PROFILE_REGISTRY: dict[str, EvalProfileSlot] = {}


def register_eval_profile(slot: EvalProfileSlot, *, replace: bool = False) -> None:
    """Register a new eval profile slot.

    Args:
        slot: The slot to register.
        replace: If True, replace an existing entry with the same name. If
            False (default), raise ValueError on collision so the caller is
            forced to think about whether the redefinition was intentional.

    Raises:
        ValueError: If a slot with this name is already registered and
            replace=False.
    """
    if not slot.name:
        raise ValueError("EvalProfileSlot.name must be non-empty")
    if slot.estimated_cost_usd is not None and (
        not isfinite(slot.estimated_cost_usd) or slot.estimated_cost_usd < 0
    ):
        raise ValueError("EvalProfileSlot.estimated_cost_usd must be finite and non-negative")
    if not replace and slot.name in _PROFILE_REGISTRY:
        existing = _PROFILE_REGISTRY[slot.name]
        raise ValueError(
            f"Profile slot {slot.name!r} is already registered "
            f"(existing: {existing.description or 'no description'}). "
            f"Pass replace=True to override."
        )
    _PROFILE_REGISTRY[slot.name] = slot


def unregister_eval_profile(name: str) -> bool:
    """Remove a profile slot. Built-in slots cannot be removed.

    Returns:
        True if the slot was removed, False if it didn't exist.

    Raises:
        ValueError: If the named slot is a built-in (full / lite / fast).
    """
    slot = _PROFILE_REGISTRY.get(name)
    if slot is None:
        return False
    if slot.is_builtin:
        raise ValueError(
            f"Cannot unregister built-in profile slot {name!r}. "
            f"Built-in slots are required for back-compat with existing eval flows."
        )
    del _PROFILE_REGISTRY[name]
    return True


def get_eval_profile(name: str) -> EvalProfileSlot | None:
    """Look up a registered profile slot by name. Returns None if not found."""
    return _PROFILE_REGISTRY.get(name)


def list_eval_profile_names() -> tuple[str, ...]:
    """Return all registered profile slot names in registration order."""
    return tuple(_PROFILE_REGISTRY.keys())


def list_eval_profiles() -> tuple[EvalProfileSlot, ...]:
    """Return all registered profile slots in registration order."""
    return tuple(_PROFILE_REGISTRY.values())


def _register_builtin_profiles() -> None:
    """Register the three legacy profile slots. Called at module init."""
    for name, description in (
        ("full", "Default Grok 4.7 hybrid pipeline (reasoning + writing + strategy)"),
        ("lite", "Premium pipeline with Pro instead of Deep Research for strategy"),
        ("fast", "Grok 4.7 low-effort + 4.20-non-reasoning bulk writing"),
    ):
        register_eval_profile(
            EvalProfileSlot(
                name=name,
                recipe=None,  # legacy slots use mode flags, not per-role recipe
                estimated_cost_usd=None,  # falls back to mode-based cost estimator
                description=description,
                is_builtin=True,
            )
        )


_register_builtin_profiles()


def _register_candidate_profiles() -> None:
    """Load the declarative catalog without importing the evaluation runner."""
    try:
        from primr.config.eval_profiles import EVAL_MATRIX_SLOTS
    except ImportError as exc:
        logger.warning(
            "Could not load candidate eval profiles: %s; built-ins remain available", exc
        )
        return
    for slot in EVAL_MATRIX_SLOTS:
        register_eval_profile(slot, replace=True)


_register_candidate_profiles()
