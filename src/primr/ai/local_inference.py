"""Detection and model selection for local OpenAI-compatible inference.

Primr treats local inference (Ollama, LM Studio, llama.cpp server, vLLM,
LocalAI — anything speaking the OpenAI chat API) as an *optimization the
system discovers*, never a requirement: every probe fails open, absence is
the silent default, and nothing here assumes a particular machine, GPU, or
installed model. The base URL resolves through the same env chain the local
eval judge uses (``LOCAL_LLM_BASE_URL`` > ``OLLAMA_BASE_URL`` > localhost
Ollama default), so remote boxes, WSL, and containers are covered by
configuration, not platform code.

Detection uses the generic ``GET {base}/models`` endpoint (served by Ollama,
LM Studio, vLLM, and llama.cpp alike) rather than any vendor-specific API.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.ai.openai_compatible_client import normalize_openai_base_url
from primr.ai.provider_availability import (
    AvailabilityState,
    LocalCapacityBusyError,
)
from primr.utils.logging_config import get_logger

logger = get_logger("ai.local_inference")

# Probe timeout: a local server answers in milliseconds; anything slower is
# effectively absent. Kept short so the no-local-inference path costs nothing.
PROBE_TIMEOUT_SECONDS = 2.5

# Family preference for picking a judge model from whatever the user has
# installed. Ordered by how reliably the family follows a strict-output
# instruction at small sizes; reasoning-trace families (deepseek-r1) come
# last because their output needs think-block stripping. This is a
# preference, not a requirement — an installed model from no listed family
# still gets picked as the fallback.
_JUDGE_FAMILY_PREFERENCE = (
    "qwen3",
    "qwen2.5",
    "llama3",
    "gemma",
    "mistral",
    "phi",
    "deepseek-r1",
)

# Models that cannot act as a text judge at all.
_NON_CHAT_MARKERS = ("embed", "rerank", "whisper", "clip", "bge-", "nomic-")


@dataclass(frozen=True)
class LocalCapacityProbe:
    """Body-free local endpoint capacity result."""

    state: AvailabilityState
    models: tuple[str, ...] = ()
    reason: str = "local_probe_failed"
    retry_after_seconds: int | None = None
    status_code: int | None = None

    @property
    def available(self) -> bool:
        return self.state is AvailabilityState.AVAILABLE


# Per-process cache for positive probes only. Busy and unavailable results are
# deliberately not cached so a later, separately initiated job can re-check.
_probe_cache: dict[str, LocalCapacityProbe] = {}


def _http_get_json(url: str, timeout: float) -> dict:
    """Minimal JSON GET for operator-configured local endpoints.

    This deliberately does NOT route through the SSRF guard: the guard
    exists to stop *untrusted scraped content* steering requests at
    internal hosts, while this URL comes only from operator configuration
    and points at the operator's own inference server (usually loopback,
    which the guard would reject by design). Scheme is still validated.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme for local inference probe: {parsed.scheme!r}")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "Local inference URL must name one HTTP endpoint without credentials or query"
        )
    headers = {"Accept": "application/json"}
    api_key = os.getenv("LOCAL_LLM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with (
        httpx.Client(trust_env=False, follow_redirects=False, timeout=timeout) as client,
        client.stream("GET", url, headers=headers) as response,
    ):
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > 2_000_000:
                raise ValueError("Local inference metadata exceeds the allowed size")
        try:
            payload = json.loads(content.decode("utf-8"))
        except RecursionError as exc:
            raise ValueError("Local inference metadata exceeds the JSON nesting limit") from exc
        if not isinstance(payload, dict):
            raise ValueError("Local inference metadata must be an object")
        return payload


def local_capacity_probe_from_exception(
    error: Exception,
    *,
    attempt: int = 0,
    now: datetime | None = None,
) -> LocalCapacityProbe:
    """Classify a local endpoint failure without inspecting raw error text."""

    busy_error = LocalCapacityBusyError.from_exception(error, attempt=attempt, now=now)
    if busy_error is not None:
        return LocalCapacityProbe(
            state=AvailabilityState.BUSY,
            reason=busy_error.reason,
            retry_after_seconds=busy_error.retry_after_seconds,
            status_code=busy_error.status_code,
        )
    return LocalCapacityProbe(
        state=AvailabilityState.UNAVAILABLE,
        reason="local_probe_unavailable",
    )


def probe_local_capacity(
    base_url: str | None = None,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    fetch_json_fn: Callable[[str, float], dict] | None = None,
    use_cache: bool = True,
    attempt: int = 0,
    now: datetime | None = None,
) -> LocalCapacityProbe:
    """Probe local model capacity as available, busy, or unavailable.

    This is a point-in-time read. It returns bounded retry guidance but never
    sleeps, polls, launches a background process, or submits another job.
    """

    resolved = normalize_openai_base_url(base_url)
    if use_cache and resolved in _probe_cache:
        return _probe_cache[resolved]

    fetch = fetch_json_fn or _http_get_json
    try:
        payload = fetch(f"{resolved}/models", timeout)
        models = tuple(
            str(entry["id"])
            for entry in payload.get("data", [])
            if isinstance(entry, dict) and entry.get("id")
        )
    except Exception as error:
        probe = local_capacity_probe_from_exception(error, attempt=attempt, now=now)
        logger.debug("Local inference probe returned %s for %s", probe.state.value, resolved)
        return probe

    if not models:
        return LocalCapacityProbe(
            state=AvailabilityState.UNAVAILABLE,
            reason="local_models_not_found",
        )
    probe = LocalCapacityProbe(
        state=AvailabilityState.AVAILABLE,
        models=models,
        reason="local_models_available",
    )
    if use_cache:
        _probe_cache[resolved] = probe
    return probe


def list_local_models(
    base_url: str | None = None,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    fetch_json_fn: Callable[[str, float], dict] | None = None,
    use_cache: bool = True,
) -> list[str]:
    """Model names served by the local OpenAI-compatible endpoint, or [].

    Fails open: any connection error, timeout, or unexpected payload means
    "no local inference", never an exception to the caller.
    """
    probe = probe_local_capacity(
        base_url,
        timeout=timeout,
        fetch_json_fn=fetch_json_fn,
        use_cache=use_cache,
    )
    return list(probe.models)


def clear_probe_cache() -> None:
    """Reset the per-process probe cache (tests, long-lived servers)."""
    _probe_cache.clear()


def is_local_inference_available(base_url: str | None = None) -> bool:
    """True when a local OpenAI-compatible server is reachable with models."""
    return bool(list_local_models(base_url))


def pick_local_judge_model(installed: list[str]) -> str | None:
    """Pick the most judge-suitable model from whatever is installed.

    Preference-ordered by family, falling back to the first chat-capable
    model when no preferred family is installed. Returns None only when
    nothing usable is installed.
    """
    usable = [
        name
        for name in installed
        if not any(marker in name.lower() for marker in _NON_CHAT_MARKERS)
    ]
    if not usable:
        return None
    for family in _JUDGE_FAMILY_PREFERENCE:
        for name in usable:
            if name.lower().startswith(family):
                return name
    return usable[0]


@dataclass(frozen=True)
class LocalDraftRuntime:
    """One installed model at the operator's explicitly configured runtime."""

    base_url: str
    model: str
    quantization: str
    runtime: str
    installed_models: int


def _has_remote_model_metadata(value: object) -> bool:
    pending = [value]
    inspected = 0
    while pending:
        current = pending.pop()
        inspected += 1
        if inspected > 20_000:
            return True  # Overly complex metadata cannot qualify for local-only execution.
        if isinstance(current, dict):
            for key, item in current.items():
                if (
                    key in {"remote_host", "remote_model", "cloud", "is_cloud", "is_remote"}
                    and item
                ):
                    return True
                if key in {"owned_by", "provider"} and item in (
                    "openai",
                    "anthropic",
                    "xai",
                    "openrouter",
                    "ollama-cloud",
                ):
                    return True
                pending.append(item)
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, str) and any(
            marker in current.casefold() for marker in (":cloud", "-cloud", "/cloud")
        ):
            return True
    return False


def resolve_local_draft_runtime(
    model: str | None = None, *, base_url: str | None = None
) -> LocalDraftRuntime:
    """Select live installed capacity, rejecting detectable cloud routing.

    Operator configuration is the trust boundary: arbitrary compatible servers
    cannot prove where inference executes. Inspect Ollama tag metadata when the
    server provides it, including remote aliases, without pulling any model.
    """
    resolved = normalize_openai_base_url(base_url)
    parsed = urllib.parse.urlsplit(resolved)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Configure one HTTP(S) local inference endpoint without URL credentials")
    cloud_hosts = ("ollama.com", "openai.com", "anthropic.com", "x.ai", "openrouter.ai")
    hostname = parsed.hostname.rstrip(".").casefold()
    if any(hostname == host or hostname.endswith(f".{host}") for host in cloud_hosts):
        raise ValueError("Local drafts cannot use a known cloud provider endpoint")

    metadata: dict = {}

    def fetch(url: str, timeout: float) -> dict:
        payload = _http_get_json(url, timeout)
        metadata.update(payload)
        return payload

    probe = probe_local_capacity(resolved, fetch_json_fn=fetch, use_cache=False)
    if probe.state is AvailabilityState.BUSY:
        raise LocalCapacityBusyError(
            reason=probe.reason,
            requested_seconds=probe.retry_after_seconds,
            status_code=probe.status_code,
        )
    if not probe.available:
        raise RuntimeError("Local runtime is unavailable or has no installed chat models")
    entries = metadata.get("data")
    if not isinstance(entries, list) or len(entries) > 1_000:
        raise ValueError("Local model list is malformed or exceeds the allowed size")
    listed = {
        entry["id"]: entry
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and 0 < len(entry["id"]) <= 256
        and not any(ord(char) < 32 for char in entry["id"])
    }
    tags: dict[str, dict] = {}
    runtime = "OpenAI-compatible (operator configured)"
    tags_url = resolved.rsplit("/v", 1)[0] + "/api/tags"
    try:
        payload = _http_get_json(tags_url, PROBE_TIMEOUT_SECONDS)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {404, 405, 501}:
            busy = LocalCapacityBusyError.from_exception(exc)
            if busy is not None:
                raise busy from exc
            raise RuntimeError("Could not inspect local runtime model metadata") from exc
    except httpx.RequestError as exc:
        busy = LocalCapacityBusyError.from_exception(exc)
        if busy is not None:
            raise busy from exc
        raise RuntimeError("Could not reach local runtime model metadata") from exc
    else:
        models = payload.get("models")
        if not isinstance(models, list) or len(models) > 1_000:
            raise ValueError("Runtime model metadata is malformed")
        tags = {
            str(entry.get("name") or entry.get("model")): entry
            for entry in models
            if isinstance(entry, dict)
        }
        if len(tags) != len(models) or any(
            not 0 < len(name) <= 256 or any(ord(char) < 32 for char in name) for name in tags
        ):
            raise ValueError("Runtime model tags contain invalid or repeated identities")
        runtime = "Ollama"
    usable = [
        name
        for name, entry in listed.items()
        if (runtime != "Ollama" or name in tags)
        and not _has_remote_model_metadata(entry)
        and not _has_remote_model_metadata(tags.get(name, {}))
    ]
    selected = model or pick_local_judge_model(usable)
    if not selected or selected not in usable:
        raise ValueError("Requested model is not an installed, locally served chat model")
    if pick_local_judge_model([selected]) is None:
        raise ValueError("Requested model cannot generate a text draft")
    details = tags.get(selected, {}).get("details", {})
    quantization = details.get("quantization_level") if isinstance(details, dict) else None
    return LocalDraftRuntime(
        base_url=resolved,
        model=selected,
        quantization="".join(
            char
            for char in str(quantization or "unknown (runtime did not report it)")[:128]
            if ord(char) >= 32
        ),
        runtime=runtime,
        installed_models=len(usable),
    )
