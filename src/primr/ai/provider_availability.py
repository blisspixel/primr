"""Pure provider quota and availability helpers.

This module normalizes service-availability signals before they reach the
capability router. It does not call provider APIs, read credentials, or mutate
runtime circuit breakers. Provider collectors should translate their live or
cached quota metadata into these records, then routing can make a deterministic
decision from the normalized shape.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any

MIN_AVAILABLE_HEADROOM_PERCENT = 0.5


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

    def __post_init__(self) -> None:
        provider = self.provider.strip()
        if not provider:
            raise ValueError("provider is required")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "windows", tuple(self.windows))
        object.__setattr__(self, "as_of", _as_utc(self.as_of) or _utc_now())
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
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class AvailabilityDecision:
    """Deterministic availability decision derived from quota windows."""

    available: bool
    headroom_percent: float | None
    binding_window_label: str | None
    resets_at: datetime | None
    stale: bool
    error: str | None = None


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
    available = snapshot.ok and (headroom is None or headroom > min_headroom_percent)
    return AvailabilityDecision(
        available=available,
        headroom_percent=headroom,
        binding_window_label=window.label if window is not None else None,
        resets_at=window.resets_at if window is not None else None,
        stale=snapshot.stale,
        error=snapshot.error,
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
