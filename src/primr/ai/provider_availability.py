"""Pure provider quota and availability helpers.

This module normalizes service-availability signals before they reach the
capability router. It does not call provider APIs, read credentials, or mutate
runtime circuit breakers. Provider collectors should translate their live or
cached quota metadata into these records, then routing can make a deterministic
decision from the normalized shape.
"""

from __future__ import annotations

import socket
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import Enum
from math import ceil, isfinite
from typing import Any

MIN_AVAILABLE_HEADROOM_PERCENT = 0.5
MIN_RETRY_AFTER_SECONDS = 30
DEFAULT_BUSY_RETRY_AFTER_SECONDS = 30 * 60
MAX_RETRY_AFTER_SECONDS = 6 * 60 * 60
BUSY_RETRY_SCHEDULE_SECONDS = (
    DEFAULT_BUSY_RETRY_AFTER_SECONDS,
    2 * 60 * 60,
    MAX_RETRY_AFTER_SECONDS,
)
_LOCAL_BUSY_HTTP_STATUS_CODES = frozenset({429, 503})


class AvailabilityState(str, Enum):
    """Normalized provider or local-capacity state."""

    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


def _validate_finite_number(name: str, value: float | None, *, allow_zero: bool = True) -> None:
    if value is None:
        return
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    if not allow_zero and value <= 0:
        raise ValueError(f"{name} must be positive")


def bounded_retry_after_seconds(
    *,
    attempt: int = 0,
    requested_seconds: float | None = None,
) -> int:
    """Return bounded retry guidance without sleeping or scheduling work.

    A structured server hint wins when present. Without one, retry guidance
    follows the product sequence of 30 minutes, two hours, then six hours. The
    function is intentionally pure so a CLI, MCP host, or scheduler can decide
    whether and when to submit another single Primr job.
    """

    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
        raise ValueError("attempt must be a non-negative integer")
    if (
        requested_seconds is not None
        and not isinstance(requested_seconds, bool)
        and isfinite(requested_seconds)
        and requested_seconds > 0
    ):
        seconds = requested_seconds
    else:
        seconds = BUSY_RETRY_SCHEDULE_SECONDS[min(attempt, len(BUSY_RETRY_SCHEDULE_SECONDS) - 1)]
    return max(MIN_RETRY_AFTER_SECONDS, min(MAX_RETRY_AFTER_SECONDS, ceil(seconds)))


def _capacity_error_status_code(error: Exception) -> int | None:
    for attribute in ("code", "status_code", "status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _capacity_error_retry_after(error: Exception, now: datetime) -> float | None:
    headers = getattr(error, "headers", None)
    if headers is None:
        headers = getattr(getattr(error, "response", None), "headers", None)
    if headers is None or not hasattr(headers, "get"):
        return None
    value = headers.get("Retry-After")
    if value is None:
        value = headers.get("retry-after")
    if value is None:
        return None
    raw = str(value).strip()
    try:
        seconds = float(raw)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        retry_at_utc = _as_utc(retry_at)
        if retry_at_utc is None:  # pragma: no cover
            return None
        seconds = (retry_at_utc - now).total_seconds()
    return seconds if seconds > 0 else None


def _is_capacity_timeout(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    reason = getattr(error, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    return "timeout" in type(error).__name__.lower()


class LocalCapacityBusyError(RuntimeError):
    """Structured terminal result for transient local chat capacity."""

    def __init__(
        self,
        *,
        reason: str,
        attempt: int = 0,
        requested_seconds: float | None = None,
        status_code: int | None = None,
        now: datetime | None = None,
    ) -> None:
        current_time = _as_utc(now) or _utc_now()
        self.state = AvailabilityState.BUSY
        safe_status = (
            status_code
            if isinstance(status_code, int)
            and not isinstance(status_code, bool)
            and 100 <= status_code <= 599
            else None
        )
        expected_http_reason = (
            f"local_capacity_http_{safe_status}_busy" if safe_status is not None else None
        )
        self.reason = (
            reason
            if reason in {"local_capacity_timeout_busy", expected_http_reason}
            else "local_capacity_busy"
        )
        self.retry_after_seconds = bounded_retry_after_seconds(
            attempt=attempt,
            requested_seconds=requested_seconds,
        )
        self.retry_at = current_time + timedelta(seconds=self.retry_after_seconds)
        self.status_code = safe_status
        super().__init__(
            f"Local inference capacity is busy; retry after {self.retry_after_seconds} seconds"
        )

    @classmethod
    def from_exception(
        cls,
        error: Exception,
        *,
        attempt: int = 0,
        now: datetime | None = None,
    ) -> LocalCapacityBusyError | None:
        """Classify structured HTTP and timeout failures without raw text."""

        if isinstance(error, cls):
            return error
        current_time = _as_utc(now) or _utc_now()
        status_code = _capacity_error_status_code(error)
        timed_out = _is_capacity_timeout(error)
        if status_code not in _LOCAL_BUSY_HTTP_STATUS_CODES and not timed_out:
            return None
        reason = (
            f"local_capacity_http_{status_code}_busy"
            if status_code is not None
            else "local_capacity_timeout_busy"
        )
        return cls(
            reason=reason,
            attempt=attempt,
            requested_seconds=_capacity_error_retry_after(error, current_time),
            status_code=status_code,
            now=current_time,
        )

    def as_metadata(self) -> dict[str, Any]:
        """Return body-free retry metadata for logs, manifests, and hosts."""

        metadata: dict[str, Any] = {
            "error": "local_capacity_busy",
            "reason": self.reason,
            "retry_after_seconds": self.retry_after_seconds,
            "retry_at": self.retry_at.isoformat(),
            "retryable": True,
            "state": self.state.value,
        }
        if self.status_code is not None:
            metadata["status_code"] = self.status_code
        return metadata


@dataclass(frozen=True)
class QuotaWindow:
    """One quota bucket exposed by a provider or host-account surface."""

    label: str
    used_percent: float | None = None
    used: float | None = None
    limit: float | None = None
    resets_at: datetime | None = None

    def __post_init__(self) -> None:
        label = self.label.strip()
        if not label:
            raise ValueError("label is required")
        _validate_finite_number("used_percent", self.used_percent)
        _validate_finite_number("used", self.used)
        _validate_finite_number("limit", self.limit, allow_zero=False)
        if (self.used is None) != (self.limit is None):
            raise ValueError("used and limit must be provided together")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "resets_at", _as_utc(self.resets_at))

    @property
    def percent_used(self) -> float | None:
        """Return normalized percent used, clamped to a sane display range."""

        if self.used_percent is not None:
            return _clamp_percent(float(self.used_percent))
        if self.used is None or self.limit is None:
            return None
        return _clamp_percent((float(self.used) / float(self.limit)) * 100.0)

    def remaining_percent(self, now: datetime | None = None) -> float | None:
        """Return remaining quota percent, treating elapsed resets as fresh."""

        reset_at = self.resets_at
        current_time = _as_utc(now) or _utc_now()
        if reset_at is not None and reset_at <= current_time:
            return 100.0
        percent = self.percent_used
        if percent is None:
            return None
        return _clamp_percent(100.0 - percent)

    def is_exhausted(self, now: datetime | None = None) -> bool:
        remaining = self.remaining_percent(now)
        return remaining is not None and remaining <= MIN_AVAILABLE_HEADROOM_PERCENT


@dataclass(frozen=True)
class ProviderQuotaSnapshot:
    """Normalized quota/availability snapshot for one provider account."""

    provider: str
    windows: Iterable[QuotaWindow] = field(default_factory=tuple)
    display_name: str | None = None
    account: str | None = None
    plan: str | None = None
    ok: bool = True
    error: str | None = None
    as_of: datetime = field(default_factory=_utc_now)
    stale: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    state: AvailabilityState | str | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        provider = self.provider.strip()
        if not provider:
            raise ValueError("provider is required")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "windows", tuple(self.windows))
        object.__setattr__(self, "as_of", _as_utc(self.as_of) or _utc_now())
        if self.state is not None:
            object.__setattr__(self, "state", AvailabilityState(self.state))
        if self.retry_after_seconds is not None:
            if isinstance(self.retry_after_seconds, bool) or self.retry_after_seconds <= 0:
                raise ValueError("retry_after_seconds must be positive")
            object.__setattr__(
                self,
                "retry_after_seconds",
                bounded_retry_after_seconds(requested_seconds=self.retry_after_seconds),
            )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def has_windows(self) -> bool:
        return bool(self.windows)

    def as_stale(self, note: str) -> ProviderQuotaSnapshot:
        """Return a stale copy with an explanatory error note."""

        return ProviderQuotaSnapshot(
            provider=self.provider,
            windows=self.windows,
            display_name=self.display_name,
            account=self.account,
            plan=self.plan,
            ok=self.ok,
            error=note,
            as_of=self.as_of,
            stale=True,
            state=self.state,
            retry_after_seconds=self.retry_after_seconds,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class AvailabilityDecision:
    """Deterministic availability decision derived from quota windows."""

    available: bool
    state: AvailabilityState
    headroom_percent: float | None
    binding_window_label: str | None
    resets_at: datetime | None
    stale: bool
    error: str | None = None
    retry_after_seconds: int | None = None
    retry_at: datetime | None = None


def binding_window(
    snapshot: ProviderQuotaSnapshot,
    now: datetime | None = None,
) -> QuotaWindow | None:
    """Return the quota window with the least remaining usable headroom."""

    current_time = _as_utc(now) or _utc_now()
    scored: list[tuple[float, QuotaWindow]] = []
    for window in snapshot.windows:
        remaining = window.remaining_percent(current_time)
        if remaining is not None:
            scored.append((remaining, window))
    if not scored:
        return None
    return min(scored, key=lambda item: item[0])[1]


def provider_headroom(
    snapshot: ProviderQuotaSnapshot,
    now: datetime | None = None,
) -> float | None:
    """Return available headroom percent from the most constrained window."""

    current_time = _as_utc(now) or _utc_now()
    window = binding_window(snapshot, current_time)
    if window is None:
        return None
    return window.remaining_percent(current_time)


def availability_decision(
    snapshot: ProviderQuotaSnapshot,
    now: datetime | None = None,
    *,
    min_headroom_percent: float = MIN_AVAILABLE_HEADROOM_PERCENT,
) -> AvailabilityDecision:
    """Convert a provider snapshot into a routing-friendly availability row."""

    current_time = _as_utc(now) or _utc_now()
    window = binding_window(snapshot, current_time)
    headroom = window.remaining_percent(current_time) if window is not None else None
    quota_available = headroom is None or headroom > min_headroom_percent
    explicit_state = AvailabilityState(snapshot.state) if snapshot.state is not None else None
    available = (
        snapshot.ok
        and quota_available
        and explicit_state not in (AvailabilityState.BUSY, AvailabilityState.UNAVAILABLE)
    )

    quota_busy = (
        explicit_state is None
        and snapshot.ok
        and not quota_available
        and window is not None
        and window.resets_at is not None
        and window.resets_at > current_time
    )
    if available:
        state = AvailabilityState.AVAILABLE
    elif explicit_state is AvailabilityState.BUSY or quota_busy:
        state = AvailabilityState.BUSY
    else:
        state = AvailabilityState.UNAVAILABLE

    retry_after_seconds: int | None = None
    retry_at: datetime | None = None
    if state is AvailabilityState.BUSY:
        requested_seconds: float | None = snapshot.retry_after_seconds
        if requested_seconds is None and window is not None and window.resets_at is not None:
            requested_seconds = (window.resets_at - current_time).total_seconds()
        retry_after_seconds = bounded_retry_after_seconds(requested_seconds=requested_seconds)
        retry_at = current_time + timedelta(seconds=retry_after_seconds)

    return AvailabilityDecision(
        available=available,
        state=state,
        headroom_percent=headroom,
        binding_window_label=window.label if window is not None else None,
        resets_at=window.resets_at if window is not None else None,
        stale=snapshot.stale,
        error=snapshot.error,
        retry_after_seconds=retry_after_seconds,
        retry_at=retry_at,
    )


def provider_with_most_headroom(
    snapshots: Iterable[ProviderQuotaSnapshot],
    now: datetime | None = None,
) -> ProviderQuotaSnapshot | None:
    """Choose the best provider by fresh status first, then quota headroom."""

    current_time = _as_utc(now) or _utc_now()
    candidates: list[tuple[bool, float, str, ProviderQuotaSnapshot]] = []
    for snapshot in snapshots:
        decision = availability_decision(snapshot, current_time)
        headroom = decision.headroom_percent
        if not decision.available:
            continue
        if headroom is None:
            continue
        candidates.append((not snapshot.stale, headroom, snapshot.provider, snapshot))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]
