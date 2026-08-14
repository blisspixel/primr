"""Shared human-facing CLI labels (single source of truth).

Keep estimate chrome, launch messaging, dry-run headers, and run summaries
aligned with ``config.models`` / ``docs/design/grok-default-routing.md``:
hybrid and fast stay on Grok 4.3; ``--grok-tier max`` is Grok 4.5.
"""

from __future__ import annotations

import os

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


def resolved_full_mode_label(grok_tier: str) -> str:
    """Return the full-mode label for the currently configured provider route."""
    if os.environ.get("XAI_API_KEY"):
        return full_mode_label(grok_tier, has_xai=True)
    if os.environ.get("GEMINI_API_KEY"):
        return "full (Gemini routed)"
    if os.environ.get("OPENAI_API_KEY"):
        return "full (OpenAI estimate only; execution needs XAI or Gemini)"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "full (Anthropic estimate only; execution needs XAI or Gemini)"
    return f"full ({grok_tier_label(grok_tier)}; provider keys required)"
