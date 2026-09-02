"""Curated OpenRouter model rows kept outside the central registry ratchet."""

from collections.abc import Callable
from typing import TypeVar

_ModelConfig = TypeVar("_ModelConfig")


def build_openrouter_models(
    model_config_type: Callable[..., _ModelConfig],
) -> tuple[_ModelConfig, _ModelConfig, _ModelConfig]:
    """Build gateway-qualified rows without importing the registry module."""

    return (
        model_config_type(
            name="google/gemini-2.5-flash-lite",
            display_name="OpenRouter: Gemini 2.5 Flash Lite",
            provider="openrouter",
            cost_per_1m_input_tokens=0.10,
            cost_per_1m_output_tokens=0.40,
            max_input_tokens=1_048_576,
            max_output_tokens=65_535,
            supports_thinking=True,
            supports_tools=True,
            supports_multimodal=True,
            cost_per_1m_input_tokens_cached=0.01,
        ),
        model_config_type(
            name="openai/gpt-4.1-mini",
            display_name="OpenRouter: GPT-4.1 Mini",
            provider="openrouter",
            cost_per_1m_input_tokens=0.40,
            cost_per_1m_output_tokens=1.60,
            max_input_tokens=1_047_576,
            max_output_tokens=32_768,
            supports_thinking=False,
            supports_tools=True,
            supports_multimodal=True,
            cost_per_1m_input_tokens_cached=0.10,
        ),
        model_config_type(
            name="deepseek/deepseek-v3.2",
            display_name="OpenRouter: DeepSeek V3.2",
            provider="openrouter",
            cost_per_1m_input_tokens=0.269,
            cost_per_1m_output_tokens=0.40,
            max_input_tokens=163_840,
            max_output_tokens=65_536,
            supports_thinking=True,
            supports_tools=True,
            supports_multimodal=False,
            cost_per_1m_input_tokens_cached=0.1345,
        ),
    )
