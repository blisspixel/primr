"""Run-state JSON I/O helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.

These helpers manage the per-run `_run_state.json` file that the pipeline
uses to persist phase progress, append timeline events, and record
resilience signals (model health / recovery events / background aborts).

All helpers are crash-tolerant: corrupt or missing files return an empty
state rather than raising, and `_save_run_state` retries an atomic
replace (via `primr.utils.atomic_io.atomic_replace`) before falling back
to a direct overwrite so Windows file-lock contention does not abort a
long-running pipeline.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Any

from primr.utils.atomic_io import atomic_replace
from primr.utils.logging_config import get_logger

logger = get_logger(__name__)

_RUN_STATE_LOCKS: dict[str, Any] = {}
_RUN_STATE_LOCKS_GUARD = threading.Lock()


def _run_state_lock(folder_path: str) -> Any:
    key = os.path.normcase(os.path.abspath(folder_path))
    with _RUN_STATE_LOCKS_GUARD:
        return _RUN_STATE_LOCKS.setdefault(key, threading.RLock())


def _run_state_file(folder_path: str) -> str:
    """Return path to the per-run state file."""
    return os.path.join(folder_path, "_run_state.json")


def _load_run_state(folder_path: str) -> dict[str, Any]:
    """Load run state JSON if present, else return empty dict."""
    path = _run_state_file(folder_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as e:
        logger.warning("Run state file corrupted (%s), starting with empty state: %s", path, e)
        return {}
    except Exception as e:
        logger.warning("Failed to load run state from %s, starting with empty state: %s", path, e)
        return {}


def _save_run_state(folder_path: str, state: dict[str, Any]) -> None:
    """Persist run state JSON without aborting the run on transient Windows locks."""
    with _run_state_lock(folder_path):
        path = _run_state_file(folder_path)
        os.makedirs(folder_path, exist_ok=True)
        payload = json.dumps(state, indent=2)
        fd, tmp = tempfile.mkstemp(
            dir=folder_path,
            prefix="._run_state.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                atomic_replace(tmp, path)
                return
            except PermissionError as exc:
                logger.warning(
                    "Atomic run state save failed for %s; falling back to direct overwrite: %s",
                    path,
                    exc,
                )

            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
        finally:
            with suppress(OSError):
                os.remove(tmp)


def _mutate_run_state(
    folder_path: str,
    mutation: Callable[[dict[str, Any]], object],
) -> None:
    """Apply one serialized read-modify-write transaction to run state."""
    with _run_state_lock(folder_path):
        state = _load_run_state(folder_path)
        mutation(state)
        state["updated_at"] = datetime.now().isoformat()
        _save_run_state(folder_path, state)


def _update_run_state(folder_path: str, **updates: Any) -> None:
    """Merge updates into run state file and refresh timestamp."""
    _mutate_run_state(folder_path, lambda state: state.update(updates))


def _append_run_event(
    folder_path: str, phase: str, status: str, message: str, **extra: Any
) -> None:
    """Append a timeline event into run state."""
    event: dict[str, Any] = {
        "ts": datetime.now().isoformat(),
        "phase": phase,
        "status": status,
        "message": message,
    }
    if extra:
        event["extra"] = extra

    def append_event(state: dict[str, Any]) -> None:
        events = state.get("events", [])
        if not isinstance(events, list):
            events = []
        events.append(event)
        state["events"] = events[-200:]

    _mutate_run_state(folder_path, append_event)


def _ensure_resilience_keys(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure resilience arrays exist in run state (backwards compatible)."""
    for key in ("model_health", "recovery_events", "background_aborts"):
        if key not in state or not isinstance(state[key], list):
            state[key] = state.get(key, []) if isinstance(state.get(key), list) else []
    return state


def _append_model_health_event(folder_path: str, event_dict: dict[str, Any]) -> None:
    """Append a ModelHealthEvent dict to the ``model_health`` array."""
    _append_resilience_event(folder_path, "model_health", event_dict)


def _append_recovery_event(folder_path: str, event_dict: dict[str, Any]) -> None:
    """Append a recovery event dict to the ``recovery_events`` array."""
    _append_resilience_event(folder_path, "recovery_events", event_dict)


def _append_background_abort(folder_path: str, event_dict: dict[str, Any]) -> None:
    """Append a background abort dict to the ``background_aborts`` array."""
    _append_resilience_event(folder_path, "background_aborts", event_dict)


def _append_resilience_event(folder_path: str, key: str, event_dict: dict[str, Any]) -> None:
    def append_event(state: dict[str, Any]) -> None:
        _ensure_resilience_keys(state)
        state[key].append(event_dict)
        state[key] = state[key][-200:]

    _mutate_run_state(folder_path, append_event)


def _init_run_state_with_resilience(folder_path: str, base_state: dict[str, Any]) -> None:
    """Initialize run state with resilience keys included."""
    with _run_state_lock(folder_path):
        _ensure_resilience_keys(base_state)
        _save_run_state(folder_path, base_state)
