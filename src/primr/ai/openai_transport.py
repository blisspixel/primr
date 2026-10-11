"""Shared OpenAI SDK transport construction without provider registration.

Local commands import this owner directly so loading a transport does not load
cloud adapters, their SDKs, or the provider registry. Provider-facing imports
retain a compatibility alias at their existing public seam.

Primr owns retries and redirect decisions outside the SDK. Callers explicitly
choose whether their runtime may inherit environment proxy settings; local
metadata and inference paths disable that inheritance.
"""

from __future__ import annotations

from typing import Any


def create_openai_sdk_client(
    openai_module: Any,
    *,
    api_key: str,
    base_url: str,
    default_headers: dict[str, str] | None = None,
    trust_env: bool = True,
    timeout: float | None = None,
) -> Any:
    """Create a transport whose retries and redirects are bounded by Primr."""
    transport_kwargs: dict[str, Any] = {"follow_redirects": False}
    if not trust_env:
        transport_kwargs["trust_env"] = False
    if timeout is not None:
        transport_kwargs["timeout"] = timeout
    http_client = openai_module.DefaultHttpxClient(**transport_kwargs)
    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": base_url,
        "max_retries": 0,
        "http_client": http_client,
    }
    if default_headers:
        client_kwargs["default_headers"] = default_headers
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    return openai_module.OpenAI(**client_kwargs)
