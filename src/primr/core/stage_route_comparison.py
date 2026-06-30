from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StageRouteComparisonRow:
    stage_id: str
    backend_id: str
    backend_kind: str
    billing_mode: str
    inference_profile: str
    attempts: int
    selected_attempts: int
    fallback_attempts: int
    failed_attempts: int
    actual_input_tokens: int
    actual_output_tokens: int
    actual_cached_input_tokens: int
    actual_cost_usd: float
    avg_duration_seconds: float | None
    failure_classes: dict[str, int] = field(default_factory=dict)


def find_run_state_files(root: Path) -> list[Path]:
    """Return run-state files under a working/output root in deterministic order."""

    if root.is_file() and root.name == "_run_state.json":
        return [root]
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("_run_state.json") if path.is_file())


def load_stage_route_records(paths: list[Path]) -> list[dict[str, Any]]:
    """Load body-free stage route records from run-state files."""

    records: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        routes = payload.get("stage_routes", [])
        if not isinstance(routes, list):
            continue
        for route in routes:
            if isinstance(route, dict):
                records.append(route)
    return records


def compare_stage_routes(
    records: list[dict[str, Any]],
    *,
    stage_id: str | None = None,
) -> list[StageRouteComparisonRow]:
    """Aggregate route records by stage, backend, billing mode, and profile."""

    buckets: dict[tuple[str, str, str, str, str], _Accumulator] = {}
    for record in records:
        record_stage = _text(record.get("stage_id"))
        if not record_stage or (stage_id is not None and record_stage != stage_id):
            continue
        key = (
            record_stage,
            _text(record.get("backend_id")) or "unknown",
            _text(record.get("backend_kind")) or "unknown",
            _text(record.get("billing_mode")) or "unknown",
            _text(record.get("inference_profile")) or "unknown",
        )
        bucket = buckets.setdefault(key, _Accumulator())
        bucket.add(record)

    rows: list[StageRouteComparisonRow] = []
    for key, bucket in buckets.items():
        rows.append(bucket.to_row(*key))
    return sorted(
        rows,
        key=lambda row: (
            row.stage_id,
            row.backend_id,
            row.inference_profile,
            row.billing_mode,
        ),
    )


def write_stage_route_comparison_json(
    path: Path,
    *,
    rows: list[StageRouteComparisonRow],
    stage_id: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "stage_id": stage_id,
        "groups": len(rows),
        "rows": [asdict(row) for row in rows],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_stage_route_comparison_markdown(
    path: Path,
    *,
    rows: list[StageRouteComparisonRow],
    title: str = "Stage Route Comparison",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        "| Stage | Backend | Profile | Attempts | Selected | Fallback | Failed | Input Tokens | Cached Input | Output Tokens | Cost | Avg Seconds |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        avg_duration = (
            f"{row.avg_duration_seconds:.3f}" if row.avg_duration_seconds is not None else ""
        )
        lines.append(
            f"| {row.stage_id} | {row.backend_id} | {row.inference_profile} | "
            f"{row.attempts} | {row.selected_attempts} | {row.fallback_attempts} | "
            f"{row.failed_attempts} | {row.actual_input_tokens} | "
            f"{row.actual_cached_input_tokens} | {row.actual_output_tokens} | "
            f"{row.actual_cost_usd:.8f} | {avg_duration} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass
class _Accumulator:
    attempts: int = 0
    selected_attempts: int = 0
    fallback_attempts: int = 0
    failed_attempts: int = 0
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    actual_cached_input_tokens: int = 0
    actual_cost_usd: float = 0.0
    duration_seconds_total: float = 0.0
    duration_count: int = 0
    failure_classes: dict[str, int] = field(default_factory=dict)

    def add(self, record: dict[str, Any]) -> None:
        self.attempts += 1
        outcome = _text(record.get("outcome"))
        if outcome == "selected":
            self.selected_attempts += 1
        elif outcome == "fallback":
            self.fallback_attempts += 1

        failure_class = _text(record.get("failure_class"))
        if failure_class:
            self.failed_attempts += 1
            self.failure_classes[failure_class] = self.failure_classes.get(failure_class, 0) + 1

        self.actual_input_tokens += _int(record.get("actual_input_tokens"))
        self.actual_output_tokens += _int(record.get("actual_output_tokens"))
        self.actual_cached_input_tokens += _int(record.get("actual_cached_input_tokens"))
        self.actual_cost_usd += _float(record.get("actual_cost_usd"))

        duration = _float_or_none(record.get("duration_seconds"))
        if duration is not None:
            self.duration_seconds_total += duration
            self.duration_count += 1

    def to_row(
        self,
        stage_id: str,
        backend_id: str,
        backend_kind: str,
        billing_mode: str,
        inference_profile: str,
    ) -> StageRouteComparisonRow:
        avg_duration = (
            round(self.duration_seconds_total / self.duration_count, 3)
            if self.duration_count
            else None
        )
        return StageRouteComparisonRow(
            stage_id=stage_id,
            backend_id=backend_id,
            backend_kind=backend_kind,
            billing_mode=billing_mode,
            inference_profile=inference_profile,
            attempts=self.attempts,
            selected_attempts=self.selected_attempts,
            fallback_attempts=self.fallback_attempts,
            failed_attempts=self.failed_attempts,
            actual_input_tokens=self.actual_input_tokens,
            actual_output_tokens=self.actual_output_tokens,
            actual_cached_input_tokens=self.actual_cached_input_tokens,
            actual_cost_usd=round(self.actual_cost_usd, 8),
            avg_duration_seconds=avg_duration,
            failure_classes=dict(sorted(self.failure_classes.items())),
        )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return max(0.0, float(value))


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return max(0.0, float(value))
