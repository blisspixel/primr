"""Generic collectors for provider and local-service availability.

Collectors translate user-owned runtime configuration into
``ProviderQuotaSnapshot`` rows. They deliberately avoid billable model calls,
account-specific assumptions, and raw credential exposure. Live quota APIs can
feed the same snapshot shape later when providers expose official zero-token
status surfaces.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime

from primr.ai.local_inference import (
    PROBE_TIMEOUT_SECONDS,
    list_local_models,
    pick_local_judge_model,
)
from primr.ai.openai_compatible_client import normalize_openai_base_url
from primr.ai.provider_availability import ProviderQuotaSnapshot, QuotaWindow
from primr.ai.providers.registry import ProviderEntry, list_known_providers

DEFAULT_LOCAL_OPENAI_BASE_URL = "http://localhost:11434/v1"
LOCAL_OPENAI_COMPATIBLE_PROVIDER = "local_openai_compatible"
LOCAL_OPENAI_COMPATIBLE_DISPLAY_NAME = "Local OpenAI-compatible"

LocalModelLister = Callable[[str | None], Sequence[str]]


def _env_value(name: str, env: Mapping[str, str] | None) -> str | None:
    value = (env.get(name) if env is not None else os.getenv(name)) or ""
    value = value.strip()
    return value or None


def _display_name(entry: ProviderEntry) -> str:
    return entry.description.split("(", 1)[0].strip() or entry.name


def _configured_credential_source(
    entry: ProviderEntry, env: Mapping[str, str] | None
) -> str | None:
    if _env_value(entry.api_key_env, env):
        return "env"
    if entry.api_key_default is not None:
        return "provider_default"
    return None


def _local_base_url(base_url: str | None, env: Mapping[str, str] | None) -> str | None:
    if base_url is not None:
        return normalize_openai_base_url(base_url)
    if env is None:
        return None
    return normalize_openai_base_url(
        env.get("LOCAL_LLM_BASE_URL") or env.get("OLLAMA_BASE_URL") or DEFAULT_LOCAL_OPENAI_BASE_URL
    )


def _local_endpoint_source(base_url: str | None, env: Mapping[str, str] | None) -> str:
    if base_url is not None:
        return "argument"
    if _env_value("LOCAL_LLM_BASE_URL", env):
        return "LOCAL_LLM_BASE_URL"
    if _env_value("OLLAMA_BASE_URL", env):
        return "OLLAMA_BASE_URL"
    return "default_localhost"


def collect_env_provider_availability(
    entry: ProviderEntry,
    *,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> ProviderQuotaSnapshot:
    """Collect non-secret provider configuration status from environment.

    This is intentionally not a quota probe. It answers only whether primr has
    a user-provided credential or provider default available for a known
    provider. Future collectors can merge official quota/status windows onto
    the same snapshot without changing routing consumers.
    """

    credential_source = _configured_credential_source(entry, env)
    configured = credential_source is not None
    return ProviderQuotaSnapshot(
        provider=entry.name,
        display_name=_display_name(entry),
        ok=configured,
        error=None if configured else "missing_api_key",
        as_of=now or datetime.now(UTC),
        metadata={
            "api_key_env": entry.api_key_env,
            "configured": configured,
            "credential_source": credential_source,
            "quota_source": "not_collected",
            "roles": tuple(entry.roles),
        },
    )


def collect_local_openai_compatible_availability(
    *,
    provider: str = LOCAL_OPENAI_COMPATIBLE_PROVIDER,
    display_name: str = LOCAL_OPENAI_COMPATIBLE_DISPLAY_NAME,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
    list_models_fn: LocalModelLister | None = None,
    now: datetime | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    use_cache: bool = True,
) -> ProviderQuotaSnapshot:
    """Collect local OpenAI-compatible service availability.

    The snapshot records whether a reachable endpoint has at least one
    chat-capable model. It does not persist raw endpoint URLs, API keys, or the
    user's installed model names.
    """

    resolved_base_url = _local_base_url(base_url, env)

    def default_lister(url: str | None) -> Sequence[str]:
        return list_local_models(url, timeout=timeout, use_cache=use_cache)

    lister = list_models_fn or default_lister
    metadata = {
        "chat_model_available": False,
        "configured": True,
        "endpoint_source": _local_endpoint_source(base_url, env),
        "model_count": 0,
        "quota_source": "local_probe",
        "roles": ("utility",),
        "zero_incremental_api_cost": True,
    }

    try:
        models = [str(model) for model in lister(resolved_base_url) if str(model).strip()]
    except Exception:
        return ProviderQuotaSnapshot(
            provider=provider,
            display_name=display_name,
            ok=False,
            error="local_openai_compatible_probe_failed",
            as_of=now or datetime.now(UTC),
            metadata=metadata,
        )

    selected = pick_local_judge_model(models)
    metadata["chat_model_available"] = selected is not None
    metadata["model_count"] = len(models)

    if selected is None:
        return ProviderQuotaSnapshot(
            provider=provider,
            display_name=display_name,
            ok=False,
            error="local_openai_compatible_unavailable",
            as_of=now or datetime.now(UTC),
            metadata=metadata,
        )

    return ProviderQuotaSnapshot(
        provider=provider,
        windows=(QuotaWindow("local_service", used_percent=0.0),),
        display_name=display_name,
        ok=True,
        as_of=now or datetime.now(UTC),
        metadata=metadata,
    )


def collect_provider_availability_snapshots(
    *,
    entries: Iterable[ProviderEntry] | None = None,
    env: Mapping[str, str] | None = None,
    include_local: bool = True,
    local_list_models_fn: LocalModelLister | None = None,
    now: datetime | None = None,
) -> tuple[ProviderQuotaSnapshot, ...]:
    """Collect generic availability snapshots for known providers.

    Cloud entries are configuration-only until official quota/status collectors
    are wired. Local availability uses the generic OpenAI-compatible probe so
    users can bring Ollama, LM Studio, llama.cpp server, vLLM, LocalAI, or any
    compatible endpoint without primr knowing about their machine.
    """

    snapshots: list[ProviderQuotaSnapshot] = []
    for entry in entries or list_known_providers():
        if entry.name == "ollama":
            continue
        snapshots.append(collect_env_provider_availability(entry, env=env, now=now))
    if include_local:
        snapshots.append(
            collect_local_openai_compatible_availability(
                env=env,
                list_models_fn=local_list_models_fn,
                now=now,
            )
        )
    return tuple(snapshots)
