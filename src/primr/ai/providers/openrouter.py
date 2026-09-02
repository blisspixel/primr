"""OpenRouter gateway provider with estimate-bound request controls."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from primr.ai.providers.base import ChatResponse, CredentialCheck, ProviderUnavailableError
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider
from primr.config.models import PrimrModels

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_BILLING_URL = "https://openrouter.ai/settings/credits"
OPENROUTER_APP_HEADERS = {
    "HTTP-Referer": "https://github.com/blisspixel/primr",
    "X-OpenRouter-Title": "Primr",
}
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def openrouter_routing_enabled() -> bool:
    """Return whether paid OpenRouter routing was explicitly enabled."""

    return os.getenv("PRIMR_OPENROUTER_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def openrouter_routing_ready() -> bool:
    """Require a configured key and the separate paid-routing opt-in."""

    return bool(os.getenv("OPENROUTER_API_KEY")) and openrouter_routing_enabled()


def openrouter_zdr_enabled() -> bool:
    """Default OpenRouter calls to zero-data-retention endpoints."""

    return os.getenv("PRIMR_OPENROUTER_ZDR", "1").strip().lower() not in _FALSE_VALUES


def _provider_policy(model: str) -> dict[str, Any]:
    """Build privacy and price limits from the exact registered model row."""

    config = PrimrModels.get_model_config(model)
    if config is None or config.provider != "openrouter":
        raise ValueError(f"OpenRouter model {model!r} is not registered with explicit pricing")
    input_rate, output_rate, _cached_rate = config.standard_rates()
    policy: dict[str, Any] = {
        "allow_fallbacks": True,
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {
            "prompt": input_rate,
            "completion": output_rate,
        },
    }
    if openrouter_zdr_enabled():
        policy["zdr"] = True
    return policy


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenAI-compatible OpenRouter transport with hard policy controls."""

    def __init__(self) -> None:
        super().__init__(
            name="openrouter",
            base_url=OPENROUTER_BASE_URL,
            api_key_env="OPENROUTER_API_KEY",
            billing_help_url=OPENROUTER_BILLING_URL,
            default_headers=OPENROUTER_APP_HEADERS,
        )

    def validate_credentials(self) -> CredentialCheck:
        """Authenticate through ``GET /key`` without making a model call."""

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return CredentialCheck(
                provider=self.name, ok=False, detail="OPENROUTER_API_KEY not set"
            )
        start = time.monotonic()
        try:
            with httpx.Client(follow_redirects=False, timeout=15.0) as client:
                response = client.get(
                    f"{OPENROUTER_BASE_URL}/key",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            return CredentialCheck(
                provider=self.name,
                ok=True,
                detail="authenticated; key endpoint reachable",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return CredentialCheck(
                provider=self.name,
                ok=False,
                detail=f"{type(exc).__name__}: {str(exc)[:120]}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 16_000,
        retries: int = 4,
        **provider_kwargs: Any,
    ) -> ChatResponse:
        """Call OpenRouter with a registered-price ceiling and private routing."""

        if not openrouter_routing_enabled():
            raise ProviderUnavailableError(
                "OpenRouter paid routing is disabled. Set PRIMR_OPENROUTER_ENABLED=1 "
                "only after reviewing the exact Primr dry-run estimate."
            )
        config = PrimrModels.get_model_config(model)
        if config is None or config.provider != "openrouter":
            raise ValueError(f"OpenRouter model {model!r} is not registered with explicit pricing")
        raw_extra_body = provider_kwargs.pop("extra_body", None)
        extra_body = dict(raw_extra_body) if isinstance(raw_extra_body, dict) else {}
        # The caller may add unrelated OpenRouter fields, but cannot weaken the
        # price or privacy policy owned by this provider.
        extra_body["provider"] = _provider_policy(model)
        return super().chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=min(max_tokens, config.max_output_tokens),
            retries=retries,
            extra_body=extra_body,
            **provider_kwargs,
        )
