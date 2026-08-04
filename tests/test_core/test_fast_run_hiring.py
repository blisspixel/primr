"""Tests for the extracted hiring-signals stage (roadmap #23, Batch C)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.provider_availability import LocalCapacityBusyError
from primr.core.fast_run_hiring import collect_fenced_hiring_block, collect_hiring_block


def _signals(
    *,
    empty: bool = False,
    source: str = "greenhouse",
    postings_found: int = 12,
    postings_selected: int = 8,
    postings_extracted: int = 8,
) -> MagicMock:
    sig = MagicMock()
    sig.is_empty.return_value = empty
    sig.source = source
    sig.postings_found = postings_found
    sig.postings_selected = postings_selected
    sig.postings_extracted = postings_extracted
    sig.company_slug = "acmeco"
    sig.tech_stack = ["python", "snowflake"]
    sig.strategic_initiatives = ["expansion"]
    return sig


@pytest.fixture
def seams(monkeypatch, tmp_path):
    captured: dict = {}
    gather = MagicMock(return_value=_signals())
    monkeypatch.setattr("primr.data.hiring_signals.gather_hiring_signals", gather)
    monkeypatch.setattr("primr.data.hiring_signals.render_for_prompt", lambda s: "rendered signals")

    def fake_update(folder_path, **updates):
        # Real run-state merges; capture the full merged view across stage calls.
        captured.setdefault("run_state", {}).update(updates)

    monkeypatch.setattr("primr.core.fast_run_hiring._update_run_state", fake_update)
    captured["gather"] = gather
    captured["tmp"] = tmp_path
    return captured


def _call(seams, **overrides):
    defaults = {
        "company_label": "AcmeCo",
        "website": "https://acme.example",
        "scraped_data": {"https://acme.example": "content"},
        "folder_path": str(seams["tmp"]),
    }
    defaults.update(overrides)
    return collect_hiring_block(**defaults)


class TestSignalsFound:
    def test_block_rendered_with_header(self, seams):
        block = _call(seams)
        assert block.startswith("=== HIRING SIGNALS ===\n")
        assert "rendered signals" in block

    def test_run_state_records_full_metrics(self, seams):
        _call(seams)
        state = seams["run_state"]["hiring_signals"]
        assert state["source"] == "greenhouse"
        assert state["postings_found"] == 12
        assert state["postings_extracted"] == 8
        assert state["company_slug"] == "acmeco"

    def test_corpus_threaded_to_gather(self, seams):
        _call(seams, scraped_data={"u": "page text"})
        kwargs = seams["gather"].call_args.kwargs
        assert kwargs["corpus"] == {"u": "page text"}
        assert kwargs["working_folder"] == str(seams["tmp"])


class TestNoSignals:
    def test_empty_signals_yield_empty_block(self, seams):
        seams["gather"].return_value = _signals(empty=True)
        assert _call(seams) == ""

    def test_empty_signals_still_record_run_state(self, seams):
        seams["gather"].return_value = _signals(empty=True, postings_found=0)
        _call(seams)
        state = seams["run_state"]["hiring_signals"]
        assert state["postings_extracted"] == 0
        assert state["postings_found"] == 0


class TestStageFailurePolicy:
    def test_gather_exception_degrades_to_empty_block(self, seams):
        seams["gather"].side_effect = RuntimeError("ATS fan-out exploded")
        assert _call(seams) == ""
        state = seams["run_state"]["hiring_signals"]
        assert state["source"] == "skipped"
        assert state["postings_found"] == 0

    def test_fast_wrapper_propagates_local_capacity_busy_without_logging_raw_error(
        self, seams, monkeypatch
    ):
        busy_error = LocalCapacityBusyError(reason="local_capacity_timeout_busy")
        busy_error.__cause__ = RuntimeError("private endpoint detail")
        seams["gather"].side_effect = busy_error
        logger = MagicMock()
        monkeypatch.setattr("primr.core.fast_run_hiring.logger", logger)

        with pytest.raises(LocalCapacityBusyError) as caught:
            _call(seams)

        assert caught.value is busy_error
        logger.warning.assert_not_called()


class TestFencedVariantForDeepResearch:
    """The Deep Research paths consume the stage via collect_fenced_hiring_block:
    the block carries scraped posting titles, and stage-1 context is otherwise
    trusted LLM output, so it crosses that boundary only as fenced data."""

    def test_non_empty_block_is_fenced(self, seams):
        block = collect_fenced_hiring_block(
            company_label="AcmeCo",
            website="https://acme.example",
            scraped_data={},
            folder_path=str(seams["tmp"]),
        )
        assert "UNTRUSTED_HIRING_SIGNALS_BEGIN" in block
        assert "rendered signals" in block

    def test_no_signals_returns_empty_unfenced(self, seams):
        seams["gather"].return_value = None
        block = collect_fenced_hiring_block(
            company_label="AcmeCo",
            website="https://acme.example",
            scraped_data={},
            folder_path=str(seams["tmp"]),
        )
        assert block == ""

    def test_deep_wrapper_propagates_local_capacity_busy_without_logging_raw_error(
        self, seams, monkeypatch
    ):
        busy_error = LocalCapacityBusyError(reason="local_capacity_timeout_busy")
        busy_error.__cause__ = RuntimeError("private endpoint detail")
        seams["gather"].side_effect = busy_error
        logger = MagicMock()
        monkeypatch.setattr("primr.core.fast_run_hiring.logger", logger)

        with pytest.raises(LocalCapacityBusyError) as caught:
            collect_fenced_hiring_block(
                company_label="AcmeCo",
                website="https://acme.example",
                scraped_data={},
                folder_path=str(seams["tmp"]),
            )

        assert caught.value is busy_error
        logger.warning.assert_not_called()
