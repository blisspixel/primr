"""Tests for primr.utils.timeutils (deprecation-free UTC helpers)."""

from __future__ import annotations

import warnings
from datetime import datetime, timezone

from primr.utils.timeutils import utcnow, utcnow_naive


class TestUtcnow:
    def test_is_timezone_aware_utc(self):
        now = utcnow()
        assert now.tzinfo is not None
        assert now.utcoffset() == timezone.utc.utcoffset(None)

    def test_returns_datetime(self):
        assert isinstance(utcnow(), datetime)


class TestUtcnowNaive:
    def test_is_naive(self):
        # Behaviour-identical to the old datetime.utcnow(): no tzinfo.
        assert utcnow_naive().tzinfo is None

    def test_isoformat_has_no_offset(self):
        # The whole point: offset-free ISO strings so lexical SQL comparison and
        # fromisoformat round-trips keep working against already-stored rows.
        assert "+00:00" not in utcnow_naive().isoformat()

    def test_matches_legacy_utcnow_shape(self):
        # Same naive-UTC wall clock the deprecated datetime.utcnow() produced
        # (within a generous tolerance — both read the system clock).
        legacy_equivalent = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = abs((utcnow_naive() - legacy_equivalent).total_seconds())
        assert delta < 5


def test_helpers_do_not_emit_deprecation_warning():
    # Guard the reason this module exists: no datetime.utcnow() underneath.
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        utcnow()
        utcnow_naive()
