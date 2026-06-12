"""Tests for the offline calibration runner (epistemics measurement, 1.x step 1)."""

import json
import time
from pathlib import Path

import pytest

from primr.qa.calibration_runner import (
    ReportCalibrationOutcome,
    aggregate_per_label,
    aggregate_precision,
    estimate_cost_usd,
    resolve_reports,
    run_calibration,
    sidecar_path_for,
)

REPORT = """## Executive Summary
Revenue reached $50M in 2025. (Confirmed) [cite: 1]
Headcount grew to 500. (Reported) [cite: 2]
Margins are likely compressing. (Estimated)
A confirmed claim with no citation. (Confirmed)

## Sources
[cite: 1] https://news.example.com/revenue
[cite: 2] https://trade.example.org/headcount
"""


def _write_report(directory: Path, name: str, content: str = REPORT, mtime: float | None = None):
    path = directory / name
    path.write_text(content, encoding="utf-8")
    if mtime is not None:
        import os

        os.utime(path, (mtime, mtime))
    return path


class TestResolveReports:
    def test_explicit_file_path(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        assert resolve_reports(str(path)) == [path]

    def test_missing_file_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_reports(str(tmp_path / "ghost.md"))

    def test_company_name_resolves_latest_markdown(self, tmp_path):
        now = time.time()
        _write_report(tmp_path, "AcmeCo_Strategic_Overview_01-01-2026.md", mtime=now - 100)
        newest = _write_report(tmp_path, "AcmeCo_Strategic_Overview_02-01-2026.md", mtime=now)
        assert resolve_reports("AcmeCo", output_dir=tmp_path) == [newest]

    def test_unknown_company_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_reports("NoSuchCo", output_dir=tmp_path)

    def test_recent_takes_latest_per_company(self, tmp_path):
        now = time.time()
        _write_report(tmp_path, "Alpha_Strategic_Overview_01-01-2026.md", mtime=now - 300)
        alpha_new = _write_report(tmp_path, "Alpha_Strategic_Overview_02-01-2026.md", mtime=now)
        beta = _write_report(tmp_path, "Beta_Strategic_Overview_01-15-2026.md", mtime=now - 50)
        resolved = resolve_reports(None, recent=2, output_dir=tmp_path)
        assert set(resolved) == {alpha_new, beta}

    def test_recent_ignores_sidecar_files(self, tmp_path):
        report = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        sidecar_path_for(report).write_text("{}", encoding="utf-8")
        resolved = resolve_reports(None, recent=5, output_dir=tmp_path)
        assert resolved == [report]

    def test_empty_output_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_reports(None, recent=3, output_dir=tmp_path)


class TestDryRun:
    def test_dry_run_makes_no_fetch_or_judge_calls(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")

        def explode(*args):
            raise AssertionError("dry run must not fetch or judge")

        outcomes = run_calibration([path], dry_run=True, fetch_fn=explode, judge_fn=explode)
        assert len(outcomes) == 1
        assert outcomes[0].sidecar_path is None
        assert not sidecar_path_for(path).exists()

    def test_dry_run_counts_judge_calls(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        (outcome,) = run_calibration([path], dry_run=True)
        # Two judgeable claims (Confirmed cite 1, Reported cite 2), one URL each.
        assert outcome.judgeable_claims == 2
        assert outcome.estimated_judge_calls == 2
        assert outcome.claims_sampled == 4

    def test_cost_estimate_scales_with_calls(self):
        assert estimate_cost_usd(0) == 0.0
        assert estimate_cost_usd(100) == pytest.approx(0.05)


class TestLiveRun:
    def test_sidecar_written_with_per_label_counts(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        (outcome,) = run_calibration(
            [path], fetch_fn=lambda u: "source text", judge_fn=lambda c, t: True
        )
        assert outcome.sidecar_path == sidecar_path_for(path)
        payload = json.loads(outcome.sidecar_path.read_text(encoding="utf-8"))
        assert payload["report_file"] == path.name
        assert payload["per_label"]["Confirmed"]["traceable"] == 1
        assert payload["per_label"]["Confirmed"]["no_source"] == 1
        assert payload["per_label"]["Reported"]["traceable"] == 1
        assert payload["per_label"]["Estimated"]["exempt"] == 1

    def test_write_sidecar_false_skips_persistence(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        (outcome,) = run_calibration(
            [path],
            write_sidecar=False,
            fetch_fn=lambda u: "text",
            judge_fn=lambda c, t: True,
        )
        assert outcome.sidecar_path is None
        assert not sidecar_path_for(path).exists()
        assert outcome.per_label["Confirmed"]["traceable"] == 1

    def test_unreadable_report_records_error_not_crash(self, tmp_path):
        good = _write_report(tmp_path, "Good_Strategic_Overview_01-01-2026.md")
        missing = tmp_path / "Gone_Strategic_Overview_01-01-2026.md"
        outcomes = run_calibration(
            [missing, good], fetch_fn=lambda u: "text", judge_fn=lambda c, t: True
        )
        assert outcomes[0].error is not None
        assert outcomes[1].error is None
        assert outcomes[1].sidecar_path is not None


class TestAggregation:
    def _outcome(self, per_label):
        return ReportCalibrationOutcome(
            report_path=Path("r.md"),
            claims_sampled=0,
            judgeable_claims=0,
            estimated_judge_calls=0,
            per_label=per_label,
        )

    def test_aggregates_counts_across_reports(self):
        a = self._outcome({"Confirmed": {"sampled": 2, "traceable": 1, "untraceable": 1}})
        b = self._outcome({"Confirmed": {"sampled": 3, "traceable": 3}})
        totals = aggregate_per_label([a, b])
        assert totals["Confirmed"]["traceable"] == 4
        assert totals["Confirmed"]["untraceable"] == 1
        assert totals["Confirmed"]["sampled"] == 5

    def test_pooled_precision(self):
        a = self._outcome({"Confirmed": {"traceable": 3, "untraceable": 1, "no_source": 1}})
        totals = aggregate_per_label([a])
        assert aggregate_precision(totals, "Confirmed") == pytest.approx(0.6)

    def test_precision_none_without_decidable_claims(self):
        totals = aggregate_per_label([self._outcome({"Confirmed": {"unfetchable": 2}})])
        assert aggregate_precision(totals, "Confirmed") is None
        assert aggregate_precision(totals, "Reported") is None


class TestCLIWiring:
    def test_calibrate_positional_routes(self):
        from primr.core.cli import Command, parse_args

        config = parse_args(["calibrate", "Acme Corp"])
        assert config.command == Command.CALIBRATE
        assert config.calibrate_target == "Acme Corp"
        assert config.calibrate_recent is None
        assert config.calibrate_max_per_label == 10
        assert config.calibrate_dry_run is False

    def test_calibrate_flags(self):
        from primr.core.cli import Command, parse_args

        config = parse_args(
            ["calibrate", "--calibrate-recent", "10", "--max-per-label", "5", "--dry-run"]
        )
        assert config.command == Command.CALIBRATE
        assert config.calibrate_target is None
        assert config.calibrate_recent == 10
        assert config.calibrate_max_per_label == 5
        assert config.calibrate_dry_run is True

    def test_handler_errors_when_nothing_resolves(self, tmp_path, monkeypatch):
        from primr.core.cli import CLIConfig, Command, _handle_calibrate

        monkeypatch.chdir(tmp_path)  # empty cwd: no output/ directory
        config = CLIConfig(command=Command.CALIBRATE, calibrate_target="NoSuchCo")
        assert _handle_calibrate(config) == 1
