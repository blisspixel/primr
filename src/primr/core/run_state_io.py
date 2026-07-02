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
import logging
import os
from datetime import datetime
from typing import Any

from primr.utils.atomic_io import atomic_replace

logger = logging.getLogger(__name__)


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
    path = _run_state_file(folder_path)
    tmp = f"{path}.{os.getpid()}.tmp"
    os.makedirs(folder_path, exist_ok=True)
    payload = json.dumps(state, indent=2)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    try:
        atomic_replace(tmp, path)
        return
    except PermissionError as exc:
        logger.warning(
            "Atomic run state save failed for %s; falling back to direct overwrite: %s",
            path,
            exc,
        )

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                logger.debug("Failed to remove stale run-state temp file %s", tmp, exc_info=True)


def _update_run_state(folder_path: str, **updates: Any) -> None:
    """Merge updates into run state file and refresh timestamp."""
    state = _load_run_state(folder_path)
    state.update(updates)
    state["updated_at"] = datetime.now().isoformat()
    _save_run_state(folder_path, state)


def _append_run_event(
    folder_path: str, phase: str, status: str, message: str, **extra: Any
) -> None:
    """Append a timeline event into run state."""
    state = _load_run_state(folder_path)
    events = state.get("events", [])
    if not isinstance(events, list):
        events = []
    event: dict[str, Any] = {
        "ts": datetime.now().isoformat(),
        "phase": phase,
        "status": status,
        "message": message,
    }
    if extra:
        event["extra"] = extra
    events.append(event)
    state["events"] = events[-200:]
    state["updated_at"] = datetime.now().isoformat()
    _save_run_state(folder_path, state)


def _ensure_resilience_keys(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure resilience arrays exist in run state (backwards compatible)."""
    for key in ("model_health", "recovery_events", "background_aborts"):
        if key not in state or not isinstance(state[key], list):
            state[key] = state.get(key, []) if isinstance(state.get(key), list) else []
    return state


def _append_model_health_event(folder_path: str, event_dict: dict[str, Any]) -> None:
    """Append a ModelHealthEvent dict to the ``model_health`` array."""
    state = _load_run_state(folder_path)
    _ensure_resilience_keys(state)
    state["model_health"].append(event_dict)
    state["model_health"] = state["model_health"][-200:]
    state["updated_at"] = datetime.now().isoformat()
    _save_run_state(folder_path, state)


def _append_recovery_event(folder_path: str, event_dict: dict[str, Any]) -> None:
    """Append a recovery event dict to the ``recovery_events`` array."""
    state = _load_run_state(folder_path)
    _ensure_resilience_keys(state)
    state["recovery_events"].append(event_dict)
    state["recovery_events"] = state["recovery_events"][-200:]
    state["updated_at"] = datetime.now().isoformat()
    _save_run_state(folder_path, state)


def _append_background_abort(folder_path: str, event_dict: dict[str, Any]) -> None:
    """Append a background abort dict to the ``background_aborts`` array."""
    state = _load_run_state(folder_path)
    _ensure_resilience_keys(state)
    state["background_aborts"].append(event_dict)
    state["background_aborts"] = state["background_aborts"][-200:]
    state["updated_at"] = datetime.now().isoformat()
    _save_run_state(folder_path, state)


def _init_run_state_with_resilience(folder_path: str, base_state: dict[str, Any]) -> None:
    """Initialize run state with resilience keys included."""
    _ensure_resilience_keys(base_state)
    _save_run_state(folder_path, base_state)
