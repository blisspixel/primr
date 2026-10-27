"""Tests for comparing registered OpenAI lifecycles with live shutdown dates.

Rows follow the documented ``GET /v1/models`` shape, where ``shutdown_date``
is an optional ``YYYY-MM-DD`` string or null. No test makes a live call.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openai.types import Model

from primr.ai.model_shutdowns import (
    LOOKUP_TIMEOUT_SECONDS,
    RecordedLifecycle,
    ShutdownLookupError,
    check_openai_shutdowns,
    compare_shutdowns,
    fetch_openai_model_rows,
    parse_live_shutdowns,
    registered_openai_lifecycles,
)
from primr.ai.providers.openai_compatible import OpenAICompatibleProvider

TODAY = date(2026, 10, 27)


def _row(model_id: str, shutdown_date: str | None = None, *, include: bool = True) -> Model:
    payload: dict[str, object] = {
        "id": model_id,
        "created": 1_700_000_000,
        "object": "model",
        "owned_by": "system",
    }
    if include:
        payload["shutdown_date"] = shutdown_date
    return Model.model_validate(payload)


class TestParseLiveShutdowns:
    def test_reads_sdk_rows_with_dates_nulls_and_missing_fields(self):
        live = parse_live_shutdowns(
            [
                _row("o4-mini", "2026-10-23"),
                _row("gpt-5.6-terra", None),
                _row("gpt-6-luna", include=False),
            ]
        )
        assert live == {
            "o4-mini": date(2026, 10, 23),
            "gpt-5.6-terra": None,
            "gpt-6-luna": None,
        }

    def test_reads_plain_mappings(self):
        assert parse_live_shutdowns([{"id": "gpt-5.4", "shutdown_date": "2027-04-01"}]) == {
            "gpt-5.4": date(2027, 4, 1)
        }

    def test_unparseable_dates_and_bad_ids_are_ignored(self):
        live = parse_live_shutdowns(
            [
                {"id": "gpt-5.4", "shutdown_date": "next spring"},
                {"id": "", "shutdown_date": "2027-04-01"},
                {"id": 7, "shutdown_date": "2027-04-01"},
                {"shutdown_date": "2027-04-01"},
            ]
        )
        assert live == {"gpt-5.4": None}


class TestCompareShutdowns:
    def test_classifies_every_registry_and_live_combination(self):
        recorded = {
            "o4-mini": RecordedLifecycle(date(2026, 10, 23), "gpt-5.6-terra"),
            "gpt-5.4-nano": RecordedLifecycle(date(2027, 4, 1), "gpt-6-luna"),
            "gpt-5.4": RecordedLifecycle(None),
            "gpt-5.5": RecordedLifecycle(None),
            "gpt-5.6-terra": RecordedLifecycle(None),
            "gpt-5.4-mini": RecordedLifecycle(date(2027, 1, 1)),
            "gpt-6-luna": RecordedLifecycle(None),
            "gpt-4o": RecordedLifecycle(date(2026, 1, 1)),
        }
        live = {
            "o4-mini": date(2026, 10, 23),
            "gpt-5.4-nano": date(2027, 3, 1),
            "gpt-5.4": date(2026, 10, 27),
            "gpt-5.5": date(2027, 6, 1),
            "gpt-5.6-terra": None,
            "gpt-5.4-mini": None,
        }
        report = compare_shutdowns(recorded, live, TODAY)

        assert report.checked == 6
        assert report.unannounced == ("gpt-5.4-mini",)
        assert report.unlisted == ("gpt-6-luna",)
        assert report.unlisted_retired == ("gpt-4o",)
        by_model = {finding.model: finding for finding in report.findings}
        assert set(by_model) == {"gpt-5.4", "gpt-5.4-nano", "gpt-5.5"}
        assert (by_model["gpt-5.4"].status, by_model["gpt-5.4"].past) == ("unrecorded", True)
        assert (by_model["gpt-5.5"].status, by_model["gpt-5.5"].past) == ("unrecorded", False)
        nano = by_model["gpt-5.4-nano"]
        assert (nano.status, nano.past) == ("date_mismatch", False)
        assert nano.recorded_date == date(2027, 4, 1)
        assert nano.replacement_model == "gpt-6-luna"

    def test_shutdown_on_today_is_past(self):
        report = compare_shutdowns({"gpt-5.4": RecordedLifecycle(None)}, {"gpt-5.4": TODAY}, TODAY)
        assert [(f.status, f.past) for f in report.findings] == [("unrecorded", True)]

    def test_shutdown_moved_earlier_into_the_past_is_past(self):
        report = compare_shutdowns(
            {"gpt-5.4-nano": RecordedLifecycle(date(2027, 4, 1))},
            {"gpt-5.4-nano": date(2026, 10, 1)},
            TODAY,
        )
        assert [(f.status, f.past) for f in report.findings] == [("date_mismatch", True)]

    def test_recorded_retirement_on_today_counts_as_retired_when_unlisted(self):
        report = compare_shutdowns({"o4-mini": RecordedLifecycle(TODAY)}, {}, TODAY)
        assert report.unlisted_retired == ("o4-mini",)
        assert report.unlisted == ()

    @given(
        recorded_date=st.one_of(st.none(), st.dates()),
        live_date=st.one_of(st.none(), st.dates()),
        today=st.dates(),
    )
    def test_reports_exactly_when_live_date_is_announced_and_differs(
        self, recorded_date, live_date, today
    ):
        report = compare_shutdowns(
            {"model": RecordedLifecycle(recorded_date)}, {"model": live_date}, today
        )
        assert report.checked == 1
        expected = live_date is not None and live_date != recorded_date
        assert bool(report.findings) is expected
        assert report.unannounced == (
            ("model",) if live_date is None and recorded_date is not None else ()
        )
        if expected:
            (finding,) = report.findings
            assert finding.status == ("unrecorded" if recorded_date is None else "date_mismatch")
            assert finding.past is (live_date <= today)


def test_registry_lifecycles_include_recorded_retirements_and_image_model():
    from primr.config.models import PrimrModels

    recorded = registered_openai_lifecycles()
    assert recorded["o4-mini"] == RecordedLifecycle(date(2026, 10, 23), "gpt-5.6-terra")
    assert PrimrModels.OPENAI_IMAGE_MODEL in recorded


def test_check_reports_unrecorded_shutdown_against_the_live_registry():
    rows = [
        _row("o4-mini", "2026-10-23"),
        _row("gpt-5.6-terra", "2027-01-15"),
    ]
    report = check_openai_shutdowns(today=TODAY, list_rows=lambda: rows)

    assert report.checked == 2
    assert [(f.model, f.status, f.past) for f in report.findings] == [
        ("gpt-5.6-terra", "unrecorded", False)
    ]


class TestFetchOpenaiModelRows:
    def test_guards_the_provider_base_url_then_lists(self):
        provider = MagicMock(spec=OpenAICompatibleProvider)
        provider.base_url = "https://api.openai.com/v1"
        provider.list_models.return_value = [_row("gpt-5.4")]
        with (
            patch("primr.ai.providers.build_provider", return_value=provider),
            patch("primr.utils.url_security.is_safe_url", return_value=(True, None)) as guard,
        ):
            rows = fetch_openai_model_rows()

        guard.assert_called_once_with("https://api.openai.com/v1")
        provider.list_models.assert_called_once_with(timeout=LOOKUP_TIMEOUT_SECONDS)
        assert [row.id for row in rows] == ["gpt-5.4"]

    def test_unsafe_base_url_stops_before_listing(self):
        provider = MagicMock(spec=OpenAICompatibleProvider)
        provider.base_url = "http://169.254.169.254/v1"
        with (
            patch("primr.ai.providers.build_provider", return_value=provider),
            patch(
                "primr.utils.url_security.is_safe_url",
                return_value=(False, "metadata endpoint"),
            ),
            pytest.raises(ShutdownLookupError, match="ssrf_guard_or_dns"),
        ):
            fetch_openai_model_rows()
        provider.list_models.assert_not_called()

    def test_non_openai_provider_shape_is_rejected(self):
        with (
            patch("primr.ai.providers.build_provider", return_value=object()),
            pytest.raises(ShutdownLookupError, match="provider_shape"),
        ):
            fetch_openai_model_rows()
