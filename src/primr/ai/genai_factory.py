"""Default HTTP options for google-genai clients: a finite request timeout.

Root cause this exists for: the google-genai SDK ships with NO default HTTP
timeout. A live run hung for 3.5 hours in ``ssl.read`` — the Gemini endpoint
went quiet mid-response during a writing-tier call and the socket blocked
forever, freezing the whole pipeline past the point any retry loop could
help (the call simply never returned). Stack: ``genai._api_client._request``
-> ``httpx`` -> ``ssl.read``, no deadline anywhere.

Every ``genai.Client(...)`` construction in primr passes
``http_options=default_genai_http_options()`` so each HTTP request carries a
finite timeout (default 5 minutes — generous enough for the longest
legitimate ``generate_content`` call, finite enough that the provider retry
loops regain control). Override per machine with
``PRIMR_GEMINI_HTTP_TIMEOUT_MS``.

Design note: call sites keep constructing through their own module's
``genai.Client`` reference (rather than a central factory) so the existing
test seam — patching ``<module>.genai.Client`` — keeps working; this module
only supplies the options object. ``google.genai`` is imported lazily so
importing this module never pulls the SDK at startup.
"""

from __future__ import annotations

import os
from typing import Any

from primr.utils.logging_config import get_logger

logger = get_logger("ai.genai_factory")

# 5 minutes per HTTP request. The SDK value is in milliseconds.
DEFAULT_GENAI_HTTP_TIMEOUT_MS = 300_000


def accepts_sampling_parameters(model: str) -> bool:
    """Whether ``model`` still accepts explicit sampling controls.

    Google removed ``temperature``, ``top_p``, and ``top_k`` beginning with
    Gemini 3.6 Flash and Gemini 3.5 Flash-Lite. Gemini 3.7 and later reject
    them. Older production models retain their existing request shape.
    """
    normalized = model.lower()
    unsupported_prefixes = (
        "gemini-3.5-flash-lite",
        "gemini-3.6-",
        "gemini-3.7-",
    )
    return not normalized.startswith(unsupported_prefixes)


def supported_thinking_levels(model: str) -> tuple[str, ...]:
    """Return the published thinking-level contract for a Gemini model."""
    normalized = model.lower()
    all_levels = ("minimal", "low", "medium", "high")
    if normalized.startswith(
        ("gemini-3.6-", "gemini-3.5-", "gemini-3.1-flash-lite", "gemini-3-flash")
    ):
        return all_levels
    if normalized.startswith("gemini-3-pro"):
        return ("low", "high")
    if normalized.startswith(("gemini-3.7-", "gemini-3.1-pro", "gemini-2.5-")):
        return ("low", "medium", "high")
    return ("low", "high")


def get_genai_http_timeout_ms() -> int:
    """Resolve the genai HTTP timeout (ms), env-overridable, always finite."""
    raw = os.environ.get("PRIMR_GEMINI_HTTP_TIMEOUT_MS", "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
            logger.warning(
                "PRIMR_GEMINI_HTTP_TIMEOUT_MS must be positive, got %r — using default %d",
                raw,
                DEFAULT_GENAI_HTTP_TIMEOUT_MS,
            )
        except ValueError:
            logger.warning(
                "PRIMR_GEMINI_HTTP_TIMEOUT_MS is not an integer: %r — using default %d",
                raw,
                DEFAULT_GENAI_HTTP_TIMEOUT_MS,
            )
    return DEFAULT_GENAI_HTTP_TIMEOUT_MS


def default_genai_http_options() -> Any:
    """HttpOptions with a finite request timeout, for genai.Client(...)."""
    from google.genai import types as genai_types

    return genai_types.HttpOptions(timeout=get_genai_http_timeout_ms())
