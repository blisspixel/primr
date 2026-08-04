"""Shared human-facing CLI labels (single source of truth).

Keep estimate chrome, launch messaging, dry-run headers, and run summaries
aligned with ``config.models`` / ``docs/design/grok-default-routing.md``:
hybrid and fast stay on Grok 4.3; ``--grok-tier max`` is Grok 4.5.
"""

from __future__ import annotations

# Product tier → short operator label (used inside "full (...)" mode strings).
GROK_TIER_LABELS: dict[str, str] = {
    "fast": "Grok 4.3 (low-effort)",
    "hybrid": "Grok 4.3 hybrid",
    "max": "Grok 4.5 max",
}


def grok_tier_label(grok_tier: str) -> str:
    """Return the display label for a ``--grok-tier`` value."""
    return GROK_TIER_LABELS.get(grok_tier, "Grok")


def full_mode_label(grok_tier: str, *, has_xai: bool = True) -> str:
    """Human label for the default full research path when xAI is present."""
    if has_xai:
        return f"full ({grok_tier_label(grok_tier)})"
    return "full (provider-routed)"
