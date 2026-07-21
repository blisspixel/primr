"""Run-local outcome accounting for explicit vendor research refreshes."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VendorRefreshOutcome:
    """Immutable fulfillment summary for one explicit refresh request."""

    status: str
    expected_vendors: tuple[str, ...]
    started_vendors: tuple[str, ...]
    completed_vendors: tuple[str, ...]
    failed_vendors: tuple[str, ...]
    skipped_vendors: tuple[str, ...]

    @property
    def started_count(self) -> int:
        return len(self.started_vendors)

    @property
    def requires_nonzero_exit(self) -> bool:
        return self.status in {"partial", "failed"}

    def as_run_state(self) -> dict[str, object]:
        return {
            "vendor_refresh_status": self.status,
            "vendor_refresh_expected": list(self.expected_vendors),
            "vendor_refresh_started": list(self.started_vendors),
            "vendor_refresh_completed": list(self.completed_vendors),
            "vendor_refresh_failed": list(self.failed_vendors),
            "vendor_refresh_skipped": list(self.skipped_vendors),
        }


class VendorRefreshTracker:
    """Thread-safe local tracker fed by provider submission callbacks."""

    def __init__(self, expected_vendors: tuple[str, ...]) -> None:
        self._expected = tuple(dict.fromkeys(vendor.lower() for vendor in expected_vendors))
        self._started: set[str] = set()
        self._completed: set[str] = set()
        self._failed: set[str] = set()
        self._skipped: set[str] = set()
        self._lock = threading.Lock()

    def observe(self, vendor: str, event: str) -> None:
        normalized = vendor.lower()
        with self._lock:
            if event == "started":
                self._started.add(normalized)
            elif event == "completed":
                self._completed.add(normalized)
                self._failed.discard(normalized)
                self._skipped.discard(normalized)
            elif event == "failed" and normalized not in self._completed:
                self._failed.add(normalized)
                self._skipped.discard(normalized)

    def observer(self, vendor: str) -> Callable[[str], None]:
        """Return the callback accepted by the vendor-research provider seam."""

        return lambda event: self.observe(vendor, event)

    def mark_skipped(self, vendor: str) -> None:
        normalized = vendor.lower()
        with self._lock:
            if normalized not in self._completed and normalized not in self._failed:
                self._skipped.add(normalized)

    def mark_remaining_skipped(self) -> None:
        with self._lock:
            resolved = self._completed | self._failed | self._skipped
            self._skipped.update(v for v in self._expected if v not in resolved)

    def snapshot(self) -> VendorRefreshOutcome:
        with self._lock:
            completed = tuple(v for v in self._expected if v in self._completed)
            started = tuple(v for v in self._expected if v in self._started)
            skipped = tuple(v for v in self._expected if v in self._skipped)
            unresolved = {
                v
                for v in self._expected
                if v not in self._completed and v not in self._failed and v not in self._skipped
            }
            failed_set = self._failed | unresolved
            failed = tuple(v for v in self._expected if v in failed_set)

        if not self._expected:
            status = "not_requested"
        elif len(completed) == len(self._expected):
            status = "completed"
        elif completed:
            status = "partial"
        else:
            status = "failed"
        return VendorRefreshOutcome(
            status,
            self._expected,
            started,
            completed,
            failed,
            skipped,
        )


def persist_vendor_refresh_outcome(folder_path: str, outcome: VendorRefreshOutcome) -> None:
    from primr.core.run_state_io import _update_run_state

    _update_run_state(folder_path, **outcome.as_run_state())


def load_vendor_refresh_outcome(folder_path: str | None) -> VendorRefreshOutcome | None:
    if not folder_path:
        return None
    try:
        payload = json.loads((Path(folder_path) / "_run_state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return vendor_refresh_outcome_from_state(payload)


def vendor_refresh_outcome_from_state(payload: object) -> VendorRefreshOutcome | None:
    """Parse one canonical refresh outcome without repairing malformed state."""

    if not isinstance(payload, dict):
        return None
    status = payload.get("vendor_refresh_status")
    if status not in {"not_requested", "completed", "partial", "failed"}:
        return None

    def vendors(key: str) -> tuple[str, ...] | None:
        values = payload.get(key)
        if not isinstance(values, list):
            return None
        result: list[str] = []
        for value in values:
            if not isinstance(value, str):
                return None
            result.append(value)
        return tuple(result)

    expected = vendors("vendor_refresh_expected")
    started = vendors("vendor_refresh_started")
    completed = vendors("vendor_refresh_completed")
    failed = vendors("vendor_refresh_failed")
    skipped = vendors("vendor_refresh_skipped")
    if (
        expected is None
        or started is None
        or completed is None
        or failed is None
        or skipped is None
    ):
        return None

    outcome = VendorRefreshOutcome(
        status=status,
        expected_vendors=expected,
        started_vendors=started,
        completed_vendors=completed,
        failed_vendors=failed,
        skipped_vendors=skipped,
    )
    return outcome if _valid_vendor_refresh_outcome(outcome) else None


def _valid_vendor_refresh_outcome(outcome: VendorRefreshOutcome) -> bool:
    expected = set(outcome.expected_vendors)
    started = set(outcome.started_vendors)
    completed = set(outcome.completed_vendors)
    failed = set(outcome.failed_vendors)
    skipped = set(outcome.skipped_vendors)
    groups = (completed, failed, skipped)
    values = (
        outcome.expected_vendors,
        outcome.started_vendors,
        outcome.completed_vendors,
        outcome.failed_vendors,
        outcome.skipped_vendors,
    )
    if any(len(value) != len(set(value)) for value in values):
        return False
    if started - expected or any(group - expected for group in groups):
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
