"""Gemini orphaned-resource cleanup helpers.

Extracted from `primr.ai.deep_research` for isolated unit testing.

These helpers detect Primr-owned Gemini resources (caches and file
search stores) by display-name prefix, compute their approximate age,
and walk the API to delete only those that are both owned by us AND
older than the configured staleness window.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from primr.ai.genai_factory import default_genai_http_options

logger = logging.getLogger(__name__)


_PRIMR_RESOURCE_PREFIX = "primr-"
# Don't touch stores younger than this — they may belong to a concurrent
# Primr run on the same API key. Configurable via env for operators who
# want a tighter or looser window.
_DEFAULT_STALE_AGE_SECONDS = 3600.0


def _create_genai_client(api_key: str) -> Any:
    """Construct the cleanup client without importing a high-level consumer."""
    from google import genai

    return genai.Client(api_key=api_key, http_options=default_genai_http_options())


def _is_primr_owned(resource: Any) -> bool:
    """True if a Gemini cache/store carries the Primr display-name prefix.

    Any unprefixed resource is treated as foreign and must not be deleted.
    """
    display_name = getattr(resource, "display_name", None) or ""
    return isinstance(display_name, str) and display_name.startswith(_PRIMR_RESOURCE_PREFIX)


def _resource_age_seconds(resource: Any) -> float | None:
    """Approximate age in seconds for a Gemini resource, or None if unknown.

    Falls back to the timestamp embedded in the Primr display_name
    (``primr-...{int(time.time())}``) when the SDK doesn't expose a
    create_time we can parse.
    """
    from datetime import datetime, timezone

    create_time = getattr(resource, "create_time", None)
    if create_time is not None:
        try:
            if hasattr(create_time, "timestamp"):
                return max(0.0, datetime.now(timezone.utc).timestamp() - create_time.timestamp())
            if isinstance(create_time, str):
                parsed = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
                return max(0.0, datetime.now(timezone.utc).timestamp() - parsed.timestamp())
        except Exception:
            pass

    display_name = getattr(resource, "display_name", None) or ""
    if isinstance(display_name, str):
        match = re.search(r"_(\d{9,11})(?:\D|$)", display_name)
        if match:
            try:
                return max(0.0, time.time() - float(match.group(1)))
            except ValueError:
                pass
    return None


def cleanup_orphaned_resources(
    api_key: str | None = None,
    stale_age_seconds: float | None = None,
) -> dict[str, int]:
    """Clean up orphaned Gemini resources that Primr created and abandoned.

    Two safety gates protect resources we did not create or that may still
    be in use:

    1. **Ownership**: only resources whose ``display_name`` starts with the
       Primr prefix (``primr-``) are eligible.
    2. **Staleness**: only resources older than ``stale_age_seconds``
       (default ~1h, configurable via ``PRIMR_CLEANUP_STALE_AGE_SECONDS``)
       are eligible.

    Returns:
        Dict with counts: ``{"caches_deleted": N, "stores_deleted": N}``.
    """
    from primr.config.settings import get_settings

    settings = get_settings()
    key = api_key or settings.api.gemini_key
    client = _create_genai_client(key)

    if stale_age_seconds is None:
        try:
            stale_age_seconds = float(
                os.environ.get("PRIMR_CLEANUP_STALE_AGE_SECONDS", _DEFAULT_STALE_AGE_SECONDS)
            )
        except ValueError:
            stale_age_seconds = _DEFAULT_STALE_AGE_SECONDS

    result = {"caches_deleted": 0, "stores_deleted": 0}

    try:
        caches = list(client.caches.list())
        for cache in caches:
            if not _is_primr_owned(cache):
                logger.debug("Skipping non-Primr cache: %s", getattr(cache, "name", "?"))
                continue
            age = _resource_age_seconds(cache)
            if age is not None and age < stale_age_seconds:
                logger.debug(
                    "Skipping Primr cache younger than %.0fs: %s (age=%.0fs)",
                    stale_age_seconds,
                    cache.name,
                    age,
                )
                continue
            try:
                client.caches.delete(name=cache.name)
                result["caches_deleted"] += 1
                logger.info("Deleted orphaned Primr cache: %s", cache.name)
            except Exception as e:
                logger.warning("Could not delete cache %s: %s", cache.name, e)
    except Exception as e:
        logger.warning("Could not list caches: %s", e)

    try:
        stores = list(client.file_search_stores.list())
        for store in stores:
            store_name = store.name
            if not _is_primr_owned(store):
                logger.debug("Skipping non-Primr store: %s", store_name)
                continue
            age = _resource_age_seconds(store)
            if age is not None and age < stale_age_seconds:
                logger.debug(
                    "Skipping Primr store younger than %.0fs: %s (age=%.0fs)",
                    stale_age_seconds,
                    store_name,
                    age,
                )
                continue
            try:
                docs = list(client.file_search_stores.documents.list(parent=store_name))
                for doc in docs:
                    try:
                        client.file_search_stores.documents.delete(
                            name=doc.name, config={"force": True}
                        )
                    except TypeError:
                        client.file_search_stores.documents.delete(name=doc.name)
                    except Exception as e:
                        logger.warning("Could not delete doc %s: %s", doc.name, e)
            except Exception as e:
                logger.warning("Could not list docs in %s: %s", store_name, e)

            try:
                client.file_search_stores.delete(name=store_name)
                result["stores_deleted"] += 1
                logger.info("Deleted orphaned Primr store: %s", store_name)
            except Exception as e:
                logger.warning("Could not delete store %s: %s", store_name, e)
    except Exception as e:
        logger.warning("Could not list file search stores: %s", e)

    total = result["caches_deleted"] + result["stores_deleted"]
    if total > 0:
        logger.warning(
            f"Cleaned up {total} orphaned resource(s): "
            f"{result['caches_deleted']} cache(s), {result['stores_deleted']} store(s)"
        )

    return result
