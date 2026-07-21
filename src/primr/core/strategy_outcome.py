"""Truthful outcome accounting for explicitly requested strategy artifacts."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path


def strategy_target(strategy_name: str, platform: str = "agnostic") -> str:
    """Return the stable operator-facing identifier for one strategy artifact."""

    name = strategy_name.strip().lower()
    if name == "ai":
        return f"ai:{platform.strip().lower()}"
    return name


def expected_strategy_targets(strategies: list[str], platforms: tuple[str, ...]) -> tuple[str, ...]:
    """Expand strategy names into the exact artifact targets a run requested."""

    targets: list[str] = []
    for strategy_name in strategies:
        vendors = platforms if strategy_name == "ai" else ("agnostic",)
        targets.extend(strategy_target(strategy_name, vendor) for vendor in vendors)
    return tuple(dict.fromkeys(targets))


@dataclass(frozen=True)
class StrategyOutcome:
    """Immutable strategy fulfillment summary persisted with a research run."""

    status: str
    expected_targets: tuple[str, ...]
    completed_targets: tuple[str, ...]
    failed_targets: tuple[str, ...]
    skipped_targets: tuple[str, ...]

    @property
    def requires_nonzero_exit(self) -> bool:
        """Return whether an explicit strategy request was not fully fulfilled."""

        return self.status in {"partial", "failed"}

    def as_run_state(self) -> dict[str, object]:
        """Return the stable run-state and JSON fields for this summary."""

        return {
            "strategy_status": self.status,
            "strategy_expected_targets": list(self.expected_targets),
            "strategy_completed_targets": list(self.completed_targets),
            "strategy_failed_targets": list(self.failed_targets),
            "strategy_skipped_targets": list(self.skipped_targets),
        }


class StrategyOutcomeTracker:
    """Thread-safe maker-side tracker that fails closed on unrecorded targets."""

    def __init__(self, expected_targets: tuple[str, ...]) -> None:
        self._expected = tuple(dict.fromkeys(expected_targets))
        self._completed: set[str] = set()
        self._failed: set[str] = set()
        self._skipped: set[str] = set()
        self._lock = threading.Lock()

    def mark_completed(self, target: str) -> None:
        with self._lock:
            self._completed.add(target)
            self._failed.discard(target)
            self._skipped.discard(target)

    def mark_failed(self, target: str) -> None:
        with self._lock:
            if target not in self._completed:
                self._failed.add(target)
                self._skipped.discard(target)

    def mark_skipped(self, target: str) -> None:
        with self._lock:
            if target not in self._completed and target not in self._failed:
                self._skipped.add(target)

    def mark_remaining_skipped(self) -> None:
        with self._lock:
            resolved = self._completed | self._failed | self._skipped
            self._skipped.update(target for target in self._expected if target not in resolved)

    def snapshot(self) -> StrategyOutcome:
        with self._lock:
            completed = tuple(target for target in self._expected if target in self._completed)
            skipped = tuple(target for target in self._expected if target in self._skipped)
            unresolved = {
                target
                for target in self._expected
                if target not in self._completed
                and target not in self._failed
                and target not in self._skipped
            }
            failed_set = self._failed | unresolved
            failed = tuple(target for target in self._expected if target in failed_set)

        if not self._expected:
            status = "not_requested"
        elif len(completed) == len(self._expected):
            status = "completed"
        elif completed:
            status = "partial"
        else:
            status = "failed"
        return StrategyOutcome(
            status=status,
            expected_targets=self._expected,
            completed_targets=completed,
            failed_targets=failed,
            skipped_targets=skipped,
        )


class StrategyTaskTracker:
    """Count provider submissions for one run without process-global deltas."""

    def __init__(self) -> None:
        self._started_count = 0
        self._lock = threading.Lock()

    def observe(self, event: str) -> None:
        if event != "started":
            return
        with self._lock:
            self._started_count += 1

    @property
    def started_count(self) -> int:
        with self._lock:
            return self._started_count


def persist_strategy_outcome(folder_path: str, outcome: StrategyOutcome) -> None:
    """Persist a strategy summary without changing the base report lifecycle."""

    from primr.core.run_state_io import _update_run_state

    _update_run_state(folder_path, **outcome.as_run_state())


def load_strategy_outcome(folder_path: str | None) -> StrategyOutcome | None:
    """Load a persisted strategy summary from one exact run folder."""

    if not folder_path:
        return None
    try:
        payload = json.loads((Path(folder_path) / "_run_state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return strategy_outcome_from_state(payload)


def strategy_outcome_from_state(payload: object) -> StrategyOutcome | None:
    """Parse one canonical strategy outcome without repairing malformed state."""

    if not isinstance(payload, dict):
        return None
    status = payload.get("strategy_status")
    if status not in {"not_requested", "completed", "partial", "failed"}:
        return None

    def targets(key: str) -> tuple[str, ...] | None:
        values = payload.get(key)
        if not isinstance(values, list):
            return None
        result: list[str] = []
        for value in values:
            if not isinstance(value, str):
                return None
            result.append(value)
        return tuple(result)

    expected = targets("strategy_expected_targets")
    completed = targets("strategy_completed_targets")
    failed = targets("strategy_failed_targets")
    skipped = targets("strategy_skipped_targets")
    if expected is None or completed is None or failed is None or skipped is None:
        return None

    outcome = StrategyOutcome(
        status=status,
        expected_targets=expected,
        completed_targets=completed,
        failed_targets=failed,
        skipped_targets=skipped,
    )
    return outcome if _valid_strategy_outcome(outcome) else None


def _valid_strategy_outcome(outcome: StrategyOutcome) -> bool:
    expected = set(outcome.expected_targets)
    completed = set(outcome.completed_targets)
    failed = set(outcome.failed_targets)
    skipped = set(outcome.skipped_targets)
    groups = (completed, failed, skipped)
    values = (
        outcome.expected_targets,
        outcome.completed_targets,
        outcome.failed_targets,
        outcome.skipped_targets,
    )
    if any(len(value) != len(set(value)) for value in values):
        return False
    if any(group - expected for group in groups):
        return False
    if completed & failed or completed & skipped or failed & skipped:
        return False
    if completed | failed | skipped != expected:
        return False
    if outcome.status == "not_requested":
        return not expected
    if outcome.status == "completed":
        return bool(expected) and completed == expected
    if outcome.status == "partial":
        return bool(completed) and completed != expected
    return bool(expected) and not completed
