"""The July 2026 Gemini models are registered as available, not defaulted.

Model-selection policy: register flagship / newer models so they can be
selected explicitly or eval-gated in, but never silently promote one to a
default tier (defaults change only after an eval on output $/1M). These pins
guard both halves of that: the new ids must be resolvable and priced, and they
must NOT be the active FLASH/PRO defaults.
"""

from __future__ import annotations

import pytest

from primr.config.models import PrimrModels

NEW_GEMINI_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]


@pytest.mark.parametrize("model", NEW_GEMINI_MODELS)
def test_new_gemini_model_is_registered_and_priced(model: str) -> None:
    config = PrimrModels.get_model_config(model)
    assert config is not None, f"{model} must be in ALL_MODELS"
    assert config.provider == "google"
    # Prices must be present so the mandatory cost gate cannot KeyError.
    assert config.cost_per_1m_input_tokens > 0
    assert config.cost_per_1m_output_tokens > 0
    # A representative estimate must compute without raising.
    assert PrimrModels.calculate_cost(model, 100_000, 20_000) > 0


@pytest.mark.parametrize("model", NEW_GEMINI_MODELS)
def test_new_gemini_model_is_not_a_default_tier(model: str) -> None:
    # Registered != defaulted. A repoint of FLASH_MODEL / PRO_MODEL is eval-gated.
    assert model != PrimrModels.FLASH_MODEL
    assert model != PrimrModels.PRO_MODEL
