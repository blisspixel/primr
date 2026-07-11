from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from primr.ai.provider_availability import (
    MAX_RETRY_AFTER_SECONDS,
    AvailabilityState,
    LocalCapacityBusyError,
    ProviderQuotaSnapshot,
    QuotaWindow,
    availability_decision,
    binding_window,
    bounded_retry_after_seconds,
    provider_headroom,
    provider_with_most_headroom,
)

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def test_binding_window_uses_most_constrained_quota() -> None:
    snapshot = ProviderQuotaSnapshot(
        provider="gemini",
        windows=(
            QuotaWindow("requests_per_day", used_percent=40, resets_at=NOW + timedelta(hours=8)),
            QuotaWindow("tokens_per_minute", used_percent=99, resets_at=NOW + timedelta(minutes=1)),
        ),
    )

    window = binding_window(snapshot, NOW)

    assert window is not None
    assert window.label == "tokens_per_minute"
    assert provider_headroom(snapshot, NOW) == pytest.approx(1.0)


def test_elapsed_reset_window_counts_as_fresh() -> None:
    snapshot = ProviderQuotaSnapshot(
        provider="xai",
        windows=(QuotaWindow("daily", used_percent=100, resets_at=NOW - timedelta(seconds=1)),),
    )

    decision = availability_decision(snapshot, NOW)

    assert decision.available is True
    assert decision.headroom_percent == pytest.approx(100.0)
    assert decision.binding_window_label == "daily"


def test_decision_marks_exhausted_headroom_unavailable() -> None:
    snapshot = ProviderQuotaSnapshot(
        provider="openai",
        windows=(QuotaWindow("monthly", used=994, limit=1000, resets_at=NOW + timedelta(days=3)),),
    )

    decision = availability_decision(snapshot, NOW)

    assert decision.available is True
    assert decision.headroom_percent == pytest.approx(0.6)

    strict_decision = availability_decision(snapshot, NOW, min_headroom_percent=0.7)
    assert strict_decision.available is False


def test_failed_provider_without_windows_does_not_rank() -> None:
    live = ProviderQuotaSnapshot(
        provider="anthropic",
        windows=(QuotaWindow("daily", used_percent=55),),
    )
    failed = ProviderQuotaSnapshot(
        provider="gemini",
        ok=False,
        error="quota endpoint unavailable",
    )

    assert provider_headroom(failed, NOW) is None
    assert provider_with_most_headroom((failed, live), NOW) == live


def test_failed_provider_with_windows_does_not_rank() -> None:
    live = ProviderQuotaSnapshot(
        provider="anthropic",
        windows=(QuotaWindow("daily", used_percent=55),),
    )
    failed_with_cache = ProviderQuotaSnapshot(
        provider="gemini",
        ok=False,
        error="live status unavailable",
        windows=(QuotaWindow("daily", used_percent=1),),
    )

    assert provider_headroom(failed_with_cache, NOW) == pytest.approx(99.0)
    assert availability_decision(failed_with_cache, NOW).available is False
    assert provider_with_most_headroom((failed_with_cache, live), NOW) == live


def test_stale_snapshot_preserves_windows_but_loses_to_fresh_snapshot() -> None:
    stale = ProviderQuotaSnapshot(
        provider="codex",
        windows=(QuotaWindow("weekly", used_percent=5),),
    ).as_stale("live read failed")
    fresh = ProviderQuotaSnapshot(
        provider="ollama",
        windows=(QuotaWindow("runtime", used_percent=90),),
    )

    assert stale.stale is True
    assert stale.error == "live read failed"
    assert provider_headroom(stale, NOW) == pytest.approx(95.0)
    assert provider_with_most_headroom((stale, fresh), NOW) == fresh


def test_window_validation_and_clamping() -> None:
    assert QuotaWindow("daily", used=120, limit=100).percent_used == pytest.approx(100.0)
    assert QuotaWindow("daily", used_percent=150).remaining_percent(NOW) == pytest.approx(0.0)

    with pytest.raises(ValueError, match="used and limit"):
        QuotaWindow("daily", used=10)

    with pytest.raises(ValueError, match="label is required"):
        QuotaWindow(" ")


def test_busy_snapshot_returns_bounded_machine_readable_retry_guidance() -> None:
    snapshot = ProviderQuotaSnapshot(
        provider="local_openai_compatible",
        ok=False,
        error="local_openai_compatible_busy",
        state=AvailabilityState.BUSY,
        retry_after_seconds=1_800,
    )

    decision = availability_decision(snapshot, NOW)

    assert decision.available is False
    assert decision.state is AvailabilityState.BUSY
    assert decision.retry_after_seconds == 1_800
    assert decision.retry_at == NOW + timedelta(minutes=30)


def test_exhausted_window_with_future_reset_is_busy_and_caps_retry() -> None:
    snapshot = ProviderQuotaSnapshot(
        provider="local_openai_compatible",
        windows=(
            QuotaWindow(
                "runtime_capacity",
                used_percent=100,
                resets_at=NOW + timedelta(days=2),
            ),
        ),
    )

    decision = availability_decision(snapshot, NOW)

    assert decision.state is AvailabilityState.BUSY
    assert decision.retry_after_seconds == MAX_RETRY_AFTER_SECONDS
    assert decision.retry_at == NOW + timedelta(seconds=MAX_RETRY_AFTER_SECONDS)


def test_retry_guidance_uses_product_sequence_and_bounded_server_hint() -> None:
    assert bounded_retry_after_seconds(attempt=0) == 1_800
    assert bounded_retry_after_seconds(attempt=1) == 7_200
    assert bounded_retry_after_seconds(attempt=2) == MAX_RETRY_AFTER_SECONDS
    assert bounded_retry_after_seconds(attempt=99) == MAX_RETRY_AFTER_SECONDS
    assert bounded_retry_after_seconds(requested_seconds=5) == 30
    assert bounded_retry_after_seconds(requested_seconds=90_000) == MAX_RETRY_AFTER_SECONDS

    with pytest.raises(ValueError, match="attempt"):
        bounded_retry_after_seconds(attempt=-1)


def test_local_capacity_busy_error_exposes_safe_execution_retry_metadata() -> None:
    error = RuntimeError("raw operator endpoint detail")
    error.response = SimpleNamespace(  # type: ignore[attr-defined]
        status_code=503,
        headers={"retry-after": "120"},
    )

    busy_error = LocalCapacityBusyError.from_exception(error, now=NOW)

    assert busy_error is not None
    assert busy_error.retry_after_seconds == 120
    assert busy_error.retry_at == NOW + timedelta(seconds=120)
    assert busy_error.as_metadata() == {
        "error": "local_capacity_busy",
        "reason": "local_capacity_http_503_busy",
        "retry_after_seconds": 120,
        "retry_at": (NOW + timedelta(seconds=120)).isoformat(),
        "retryable": True,
        "state": "busy",
        "status_code": 503,
    }
    assert "operator endpoint" not in str(busy_error)


def test_local_capacity_busy_error_sanitizes_caller_supplied_reason() -> None:
    busy_error = LocalCapacityBusyError(reason="http://private-host.example/retry")

    assert busy_error.reason == "local_capacity_busy"
    assert busy_error.as_metadata()["reason"] == "local_capacity_busy"
    assert "private-host" not in str(busy_error.as_metadata())
