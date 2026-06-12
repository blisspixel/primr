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
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.ai.openai_compatible_client import normalize_openai_base_url
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

# Per-process probe cache: (base_url) -> list of installed model names.
_probe_cache: dict[str, list[str]] = {}


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
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    # B310: scheme is allow-listed to http/https immediately above, and the
    # URL is operator configuration (see docstring), not untrusted input.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        return json.loads(response.read().decode("utf-8"))


def list_local_models(
    base_url: str | None = None,
    *,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    fetch_json_fn: Callable[[str, float], dict] | None = None,
    use_cache: bool = True,
) -> list[str]:
    """Model names served by the local OpenAI-compatible endpoint, or [].

    Fails open: any connection error, timeout, or unexpected payload means
    "no local inference" — never an exception to the caller.
    """
    resolved = normalize_openai_base_url(base_url)
    if use_cache and resolved in _probe_cache:
        return list(_probe_cache[resolved])

    fetch = fetch_json_fn or _http_get_json
    try:
        payload = fetch(f"{resolved}/models", timeout)
        models = [
            str(entry["id"])
            for entry in payload.get("data", [])
            if isinstance(entry, dict) and entry.get("id")
        ]
    except Exception as e:
        logger.debug("Local inference probe failed for %s: %s", resolved, e)
        models = []

    if use_cache:
        _probe_cache[resolved] = list(models)
    return models


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
