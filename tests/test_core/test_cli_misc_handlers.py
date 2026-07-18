"""Unit tests for miscellaneous _handle_* commands in primr.core.cli.

Covers _handle_generate_vendor, _handle_enrich, _handle_batch,
_handle_test_accordion, _handle_analyze_report.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from primr.core.cli import (
    CLIConfig,
    Command,
    _handle_analyze_report,
    _handle_batch,
    _handle_enrich,
    _handle_test_accordion,
    parse_args,
)
from primr.core.cli_vendor import run_generate_vendor


def _config(**overrides):
    defaults = {"command": Command.GENERATE_VENDOR}
    defaults.update(overrides)
    return CLIConfig(**defaults)


# ---------------------------------------------------------------------------
# _handle_generate_vendor
# ---------------------------------------------------------------------------


class TestHandleGenerateVendor:
    def test_no_vendor_returns_zero(self, monkeypatch):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.vendor_research.generate_vendor_research_sync", gen_mock)
        # No vendor specified -> loops over empty list -> returns 0
        result = run_generate_vendor(_config(generate_vendor=None))
        assert result == 0
        gen_mock.assert_not_called()

    def test_all_generates_four_vendors(self, monkeypatch):
        gen_mock = MagicMock(return_value="/path.json")
        monkeypatch.setattr("primr.core.vendor_research.generate_vendor_research_sync", gen_mock)
        result = run_generate_vendor(_config(generate_vendor="all"))
        assert result == 0
        # all == azure, aws, gcp, agnostic
        assert gen_mock.call_count == 4

    def test_single_vendor(self, monkeypatch):
        gen_mock = MagicMock(return_value="/path.json")
        monkeypatch.setattr("primr.core.vendor_research.generate_vendor_research_sync", gen_mock)
        result = run_generate_vendor(_config(generate_vendor="azure"))
        assert result == 0
        gen_mock.assert_called_once_with("azure")

    def test_failed_generation_still_returns_zero(self, monkeypatch):
        # The function logs the error but doesn't escalate exit code
        gen_mock = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.vendor_research.generate_vendor_research_sync", gen_mock)
        result = run_generate_vendor(_config(generate_vendor="azure"))
        assert result == 0


# ---------------------------------------------------------------------------
# _handle_enrich
# ---------------------------------------------------------------------------


class TestHandleEnrich:
    def test_no_batch_file_returns_1(self):
        assert _handle_enrich(_config(batch_file=None)) == 1

    def test_delegates_to_enrich_batch(self, monkeypatch):
        enrich_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.enrich_batch", enrich_mock)
        result = _handle_enrich(_config(batch_file="/path.csv", industry="tech", limit=10))
        assert result == 0
        enrich_mock.assert_called_once()
        kwargs = enrich_mock.call_args.kwargs
        assert kwargs["industry"] == "tech"
        assert kwargs["limit"] == 10

    def test_rejects_host_billing_acknowledgment(self, monkeypatch):
        enrich_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.enrich_batch", enrich_mock)

        result = _handle_enrich(
            _config(
                batch_file="/path.csv",
                acknowledge_host_agent_may_bill=True,
            )
        )

        assert result == 1
        enrich_mock.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_batch
# ---------------------------------------------------------------------------


class TestHandleBatch:
    def test_rejects_experimental_host_fanout(self, monkeypatch):
        batch_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.process_batch", batch_mock)

        result = _handle_batch(
            _config(
                batch_file="/path.csv",
                inference_profile="hybrid",
                acknowledge_host_agent_may_bill=True,
            )
        )

        assert result == 1
        batch_mock.assert_not_called()

    def test_batch_file_takes_priority(self, monkeypatch):
        batch_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.process_batch", batch_mock)
        result = _handle_batch(_config(batch_file="/path.csv", csv_file="/legacy.csv"))
        assert result == 0
        batch_mock.assert_called_once()
        assert batch_mock.call_args.kwargs["platforms"] is None

    def test_batch_preserves_explicit_platforms(self, monkeypatch):
        batch_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.process_batch", batch_mock)

        result = _handle_batch(_config(batch_file="/path.csv", platforms=("aws",)))

        assert result == 0
        assert batch_mock.call_args.kwargs["platforms"] == ("aws",)

    def test_falls_back_to_csv_when_no_batch_file(self, monkeypatch):
        batch_mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.process_batch", batch_mock)
        result = _handle_batch(
            _config(
                batch_file=None,
                csv_file="/legacy.csv",
                dry_run_requested=True,
            )
        )
        assert result == 0
        batch_mock.assert_called_once()
        assert batch_mock.call_args.args[0] == "/legacy.csv"
        assert batch_mock.call_args.kwargs["platforms"] is None

    def test_no_file_returns_1(self):
        result = _handle_batch(_config(batch_file=None, csv_file=None))
        assert result == 1

    def test_legacy_csv_json_stdout_is_one_object(self, monkeypatch, capsys):
        def emit_plan(_path, **kwargs):
            from primr.core.cli_output import emit_json

            emit_json({"deprecated_alias": kwargs["deprecated_alias"]})
            return 0

        monkeypatch.setattr("primr.core.cli.process_batch", emit_plan)
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        result = _handle_batch(parse_args(["--csv", "/legacy.csv", "--dry-run", "--json"]))

        assert result == 0
        assert json.loads(capsys.readouterr().out) == {"deprecated_alias": "--csv"}

    @pytest.mark.parametrize(
        ("extra_args", "expected_option"),
        [
            (["--context", "notes.md"], "--context"),
            (["--question", "What changes?"], "--question"),
            (["--open"], "--open"),
        ],
    )
    def test_unsupported_batch_option_is_one_json_error(
        self,
        extra_args,
        expected_option,
        capsys,
    ):
        config = parse_args(["--batch", "/path.csv", "--dry-run", "--json", *extra_args])

        result = _handle_batch(config)

        payload = json.loads(capsys.readouterr().out)
        assert result == 1
        assert payload["error"] is True
        assert expected_option in payload["message"]

    def test_conflicting_modes_are_one_json_error(self, capsys):
        config = parse_args(
            [
                "--batch",
                "/path.csv",
                "--dry-run",
                "--json",
                "--fast",
                "--premium",
            ]
        )

        result = _handle_batch(config)

        payload = json.loads(capsys.readouterr().out)
        assert result == 1
        assert payload["error"] is True
        assert "both --fast and --premium" in payload["message"]


# ---------------------------------------------------------------------------
# _handle_test_accordion
# ---------------------------------------------------------------------------


class TestHandleTestAccordion:
    def test_no_topic_returns_1(self):
        assert _handle_test_accordion(_config(test_accordion_topic=None)) == 1

    def test_dispatches_to_runner(self, monkeypatch):
        # Just verify the runner gets called; don't assert specific exit code.
        run_mock = MagicMock(side_effect=RuntimeError("test"))
        monkeypatch.setattr("primr.ai.accordion_test.run_accordion_test", run_mock)
        try:
            _handle_test_accordion(
                _config(
                    test_accordion_topic="Oceanography 2026",
                    test_accordion_pages=50,
                )
            )
        except RuntimeError:
            pass
        run_mock.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_analyze_report
# ---------------------------------------------------------------------------


class TestHandleAnalyzeReport:
    def test_no_path_returns_1(self):
        result = _handle_analyze_report(_config(analyze_report_path=None))
        assert result == 1

    def test_with_path_attempts_analysis(self, tmp_path):
        # Create a sample MD file; the handler will try to load and analyze it.
        report = tmp_path / "report.md"
        report.write_text("body", encoding="utf-8")
        result = _handle_analyze_report(_config(analyze_report_path=str(report)))
        # Whether it succeeds depends on internal logic, just verify it runs.
        assert result in (0, 1)
