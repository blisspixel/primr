"""Shared, dependency-light system health operation."""

from __future__ import annotations

import os
from typing import Any

DIRECT_PROVIDER_KEY_ENV_VARS = (
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def get_doctor_status() -> dict[str, Any]:
    """Return configuration and output-directory health for agent transports."""
    from primr.config.config import OUTPUT_DIR

    warnings: list[str] = []
    api_keys_configured = any(os.environ.get(name) for name in DIRECT_PROVIDER_KEY_ENV_VARS)
    if not api_keys_configured:
        warnings.append(
            "No direct LLM provider key configured "
            "(XAI_API_KEY, GEMINI_API_KEY or GOOGLE_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY)"
        )

    if not os.path.exists(OUTPUT_DIR):
        warnings.append(f"Output directory does not exist: {OUTPUT_DIR}")

    config_valid = True
    try:
        from primr.config.config import validate_config

        result = validate_config()
        config_valid = result.valid
        if not config_valid:
            for error in result.errors:
                warnings.append(f"Config: {error}")
    except Exception as exc:
        config_valid = False
        warnings.append(f"Configuration error: {exc}")

    return {
        "orphaned_stores_count": 0,
        "config_valid": config_valid,
        "api_keys_configured": api_keys_configured,
        "warnings": warnings,
    }


__all__ = ["DIRECT_PROVIDER_KEY_ENV_VARS", "get_doctor_status"]
