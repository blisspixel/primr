from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from primr.ai.provider_availability import (
    ProviderQuotaSnapshot,
    QuotaWindow,
    availability_decision,
    binding_window,
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
