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
    LocalCapacityProbe,
    local_capacity_probe_from_exception,
    pick_local_judge_model,
    probe_local_capacity,
)
from primr.ai.openai_compatible_client import normalize_openai_base_url
from primr.ai.provider_availability import (
    AvailabilityState,
    ProviderQuotaSnapshot,
    QuotaWindow,
)
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
    retry_attempt: int = 0,
) -> ProviderQuotaSnapshot:
    """Collect local OpenAI-compatible service availability.

    The snapshot records whether a reachable endpoint has at least one
    chat-capable model. It does not persist raw endpoint URLs, API keys, or the
    user's installed model names.
    """

    resolved_base_url = _local_base_url(base_url, env)

    metadata = {
        "capacity_reason": "local_probe_unavailable",
        "capacity_state": AvailabilityState.UNAVAILABLE.value,
        "chat_model_available": False,
        "configured": True,
        "endpoint_source": _local_endpoint_source(base_url, env),
        "model_count": 0,
        "quota_source": "local_probe",
        "roles": ("utility",),
        "retryable": False,
        "zero_incremental_api_cost": True,
    }

    if list_models_fn is None:
        probe = probe_local_capacity(
            resolved_base_url,
            timeout=timeout,
            use_cache=use_cache,
            attempt=retry_attempt,
            now=now,
        )
    else:
        try:
            listed_models = tuple(
                str(model) for model in list_models_fn(resolved_base_url) if str(model).strip()
            )
            probe = LocalCapacityProbe(
                state=(
                    AvailabilityState.AVAILABLE if listed_models else AvailabilityState.UNAVAILABLE
                ),
                models=listed_models,
                reason=("local_models_available" if listed_models else "local_models_not_found"),
            )
        except Exception as error:
            probe = local_capacity_probe_from_exception(
                error,
                attempt=retry_attempt,
                now=now,
            )

    metadata["capacity_reason"] = probe.reason
    metadata["capacity_state"] = probe.state.value
    metadata["model_count"] = len(probe.models)
    metadata["retryable"] = probe.state is AvailabilityState.BUSY
    if probe.status_code is not None:
        metadata["status_code"] = probe.status_code

    if probe.state is AvailabilityState.BUSY:
        return ProviderQuotaSnapshot(
            provider=provider,
            display_name=display_name,
            ok=False,
            error="local_openai_compatible_busy",
            as_of=now or datetime.now(UTC),
            state=AvailabilityState.BUSY,
            retry_after_seconds=probe.retry_after_seconds,
            metadata=metadata,
        )

    if probe.state is AvailabilityState.UNAVAILABLE:
        return ProviderQuotaSnapshot(
            provider=provider,
            display_name=display_name,
            ok=False,
            error=(
                "local_openai_compatible_unavailable"
                if probe.reason == "local_models_not_found"
                else "local_openai_compatible_probe_failed"
            ),
            as_of=now or datetime.now(UTC),
            state=AvailabilityState.UNAVAILABLE,
            metadata=metadata,
        )

    selected = pick_local_judge_model(list(probe.models))
    metadata["chat_model_available"] = selected is not None

    if selected is None:
        metadata["capacity_reason"] = "local_chat_model_not_found"
        metadata["capacity_state"] = AvailabilityState.UNAVAILABLE.value
        return ProviderQuotaSnapshot(
            provider=provider,
            display_name=display_name,
            ok=False,
            error="local_openai_compatible_unavailable",
            as_of=now or datetime.now(UTC),
            state=AvailabilityState.UNAVAILABLE,
            metadata=metadata,
        )

    return ProviderQuotaSnapshot(
        provider=provider,
        windows=(QuotaWindow("local_service", used_percent=0.0),),
        display_name=display_name,
        ok=True,
        as_of=now or datetime.now(UTC),
        state=AvailabilityState.AVAILABLE,
        metadata=metadata,
    )


def collect_provider_availability_snapshots(
    *,
    entries: Iterable[ProviderEntry] | None = None,
    env: Mapping[str, str] | None = None,
    include_local: bool = True,
    local_list_models_fn: LocalModelLister | None = None,
    local_retry_attempt: int = 0,
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
                retry_attempt=local_retry_attempt,
                now=now,
            )
        )
    return tuple(snapshots)
