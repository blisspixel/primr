"""Shared document framing for strategy review and repair prompts."""

from __future__ import annotations


def strategy_document_context(label: str, platform: str) -> tuple[str, str]:
    """Return the document label and optional AI platform-emphasis instruction."""
    clean_label = label.strip() or "Strategy"
    if clean_label.casefold() != "ai strategy":
        return f"{clean_label} document", ""
    return (
        "business-first AI strategy",
        f"PLATFORM EVALUATION EMPHASIS: {platform.upper()}. "
        "This is not a predetermined vendor answer.",
    )
