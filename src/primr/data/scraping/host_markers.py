"""Durable positive markers learned from confirmed first-party pages."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

from primr.data.scraping.models import PageAccessAssessment, PageAccessState
from primr.utils.user_cache import get_user_data_subdir

logger = logging.getLogger(__name__)

STATE_FILE: Path | None = None
STATE_FILENAME = "host_positive_markers.json"
MAX_HOSTS = 500
MAX_MARKERS_PER_HOST = 8
MIN_MARKER_LEN = 4
MAX_MARKER_LEN = 48

_GENERIC_MARKERS = {
    "about",
    "address",
    "annual report",
    "announcement",
    "blog",
    "board",
    "category",
    "climate",
    "collection",
    "company",
    "contact",
    "customer service",
    "earnings",
    "email",
    "esg",
    "executive",
    "faq",
    "featured",
    "founded",
    "help",
    "heritage",
    "history",
    "hours",
    "impact",
    "investor",
    "leadership",
    "location",
    "management",
    "media",
    "news",
    "our story",
    "overview",
    "phone",
    "press release",
    "products",
    "responsibility",
    "sec filings",
    "shareholder",
    "shop",
    "since",
    "support",
    "sustainability",
    "team",
    "who we are",
}
_SECRET_HINT_RE = re.compile(r"(api[_ -]?key|authorization|bearer|password|secret|token)", re.I)
_LONG_RANDOM_RE = re.compile(r"^(?=.*[a-z])(?=.*\d)[a-z0-9_-]{20,}$", re.I)
_MARKER_CHARS_RE = re.compile(r"[^a-z0-9 .&_-]+")
_lock = threading.Lock()
_cache: dict[str, dict[str, object]] | None = None


def _state_file() -> Path:
    return STATE_FILE or get_user_data_subdir("scraping") / STATE_FILENAME


def _normalize_host(host_or_url: str) -> str:
    text = (host_or_url or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = parsed.hostname or text.split("/", 1)[0].split(":", 1)[0]
    return host.strip(".").removeprefix("www.")


def _normalize_marker(marker: str) -> str | None:
    text = " ".join(_MARKER_CHARS_RE.sub(" ", marker.lower()).split()).strip(" .&_-")
    if not (MIN_MARKER_LEN <= len(text) <= MAX_MARKER_LEN):
        return None
    if text in _GENERIC_MARKERS or _SECRET_HINT_RE.search(text) or _LONG_RANDOM_RE.match(text):
        return None
    return text


def _updated_at(entry: dict[str, object]) -> float:
    value = entry.get("updated_at", 0.0)
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _load_state() -> dict[str, dict[str, object]]:
    path = _state_file()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("host marker state unreadable (%s); resetting", e)
        return {}
    hosts = raw.get("hosts") if isinstance(raw, dict) else None
    if not isinstance(hosts, dict):
        return {}
    state: dict[str, dict[str, object]] = {}
    for host, entry in hosts.items():
        if not isinstance(host, str) or not isinstance(entry, dict):
            continue
        markers = [_normalize_marker(str(m)) for m in entry.get("markers", [])]
        markers = [m for m in markers if m]
        if markers:
            state[_normalize_host(host)] = {
                "markers": markers[:MAX_MARKERS_PER_HOST],
                "updated_at": _updated_at(entry),
            }
    return state


def _save_state(state: dict[str, dict[str, object]]) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(
        sorted(
            state.items(),
            key=lambda item: _updated_at(item[1]),
            reverse=True,
        )[:MAX_HOSTS]
    )
    payload = {"version": 1, "hosts": ordered}
    try:
        tmp = path.with_suffix(f"{path.suffix}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        logger.debug("failed to write host marker state: %s", e)


def _get_cache() -> dict[str, dict[str, object]]:
    global _cache
    if _cache is None:
        _cache = _load_state()
    return _cache


def get_positive_markers(host_or_url: str) -> list[str]:
    """Return learned positive markers for ``host_or_url`` in stable order."""
    host = _normalize_host(host_or_url)
    if not host:
        return []
    with _lock:
        entry = _get_cache().get(host)
        markers = entry.get("markers", []) if entry else []
    return list(markers) if isinstance(markers, list) else []


def record_positive_markers(host_or_url: str, markers: Iterable[str]) -> list[str]:
    """Persist validated host markers and return the current bounded marker set."""
    host = _normalize_host(host_or_url)
    normalized = [_normalize_marker(str(marker)) for marker in markers]
    candidates = [marker for marker in normalized if marker]
    if not host or not candidates:
        return get_positive_markers(host)
    with _lock:
        cache = _get_cache()
        entry = cache.get(host)
        existing_raw = entry.get("markers", []) if entry else []
        existing = list(existing_raw) if isinstance(existing_raw, list) else []
        combined = list(dict.fromkeys([*existing, *candidates]))[:MAX_MARKERS_PER_HOST]
        cache[host] = {"markers": combined, "updated_at": time.time()}
        _save_state(cache)
    return combined


def learn_positive_markers(
    host_or_url: str,
    assessment: PageAccessAssessment,
    expected_markers: Iterable[str],
) -> list[str]:
    """Learn only explicit expected markers observed on confirmed real pages."""
    if assessment.state != PageAccessState.SUCCESS or assessment.matched_challenge_markers:
        return get_positive_markers(host_or_url)
    matched = {
        normalized
        for marker in assessment.matched_expected_markers
        if (normalized := _normalize_marker(marker))
    }
    expected = [_normalize_marker(str(marker)) for marker in expected_markers]
    return record_positive_markers(
        host_or_url, (marker for marker in expected if marker in matched)
    )


def reset_all_for_testing() -> None:
    """Clear host-marker state in memory and on disk."""
    global _cache
    with _lock:
        _cache = {}
        path = _state_file()
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
