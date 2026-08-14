"""Unit tests for shared Grok tier / mode labels."""

from __future__ import annotations

from primr.core.cli_labels import (
    GROK_TIER_LABELS,
    full_mode_label,
    grok_tier_label,
    resolved_full_mode_label,
)


def test_tier_labels_match_routing_decision():
    """Hybrid stays on 4.3; max is 4.5 (see docs/design/grok-default-routing.md)."""
    assert GROK_TIER_LABELS["fast"] == "Grok 4.3 (low-effort)"
    assert GROK_TIER_LABELS["hybrid"] == "Grok 4.3 hybrid"
    assert GROK_TIER_LABELS["max"] == "Grok 4.5 max"
    assert "4.1" not in grok_tier_label("fast")
    assert "4.3 max" not in grok_tier_label("max")
    assert "4.5" in grok_tier_label("max")


def test_full_mode_label_with_xai():
    assert full_mode_label("hybrid", has_xai=True) == "full (Grok 4.3 hybrid)"
    assert full_mode_label("max", has_xai=True) == "full (Grok 4.5 max)"


def test_resolved_full_mode_label_matches_configured_provider(monkeypatch):
    for name in ("XAI_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    assert resolved_full_mode_label("hybrid") == ("full (Grok 4.3 hybrid; provider keys required)")
    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    assert resolved_full_mode_label("hybrid") == "full (Gemini routed)"
    monkeypatch.setenv("XAI_API_KEY", "configured")
    assert resolved_full_mode_label("hybrid") == "full (Grok 4.3 hybrid)"
