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
    write_calibration_pack_manifest,
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
        assert payload["validation_rubric"]["source_reviews"] == 2
        assert payload["claims"][0]["evidence_reviews"][0]["supported"] is True

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

    def test_judge_failure_records_report_error_not_crash(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")

        def fail(*args):
            raise RuntimeError("judge unavailable")

        (outcome,) = run_calibration([path], fetch_fn=lambda u: "text", judge_fn=fail)
        assert outcome.error == "calibration_failed: judge unavailable"
        assert outcome.sidecar_path is None
        assert not sidecar_path_for(path).exists()


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


class TestPackManifest:
    def test_dry_run_manifest_freezes_selected_reports(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        outcomes = run_calibration([path], dry_run=True)
        manifest_path = tmp_path / "calibration-pack.json"

        payload = write_calibration_pack_manifest(
            manifest_path,
            [path],
            outcomes,
            max_per_label=10,
        )

        persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert persisted == payload
        assert payload["manifest_format"] == "primr.calibration_pack.v1"
        assert payload["totals"]["reports"] == 1
        assert payload["totals"]["estimated_judge_calls"] == 2
        assert payload["totals"]["sidecars_present"] == 0
        assert payload["reports"][0]["report_file"] == path.name
        assert payload["reports"][0]["sidecar_exists"] is False

    def test_manifest_includes_existing_sidecar_summary(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        outcomes = run_calibration(
            [path],
            fetch_fn=lambda u: "source text",
            judge_fn=lambda c, t: True,
        )
        manifest_path = tmp_path / "calibration-pack.json"

        payload = write_calibration_pack_manifest(
            manifest_path,
            [path],
            outcomes,
            max_per_label=10,
        )

        report_entry = payload["reports"][0]
        assert payload["totals"]["sidecars_present"] == 1
        assert payload["existing_sidecar_per_label"]["Confirmed"]["traceable"] == 1
        assert report_entry["sidecar_exists"] is True
        assert report_entry["sidecar"]["judge"] == {"kind": "cloud", "model": "fast-tier"}
        assert report_entry["sidecar"]["per_label"]["Confirmed"]["traceable"] == 1

    def test_manifest_can_record_compare_judge_plan(self, tmp_path):
        from primr.qa.calibration_runner import JudgeSelection

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        outcomes = run_calibration([path], dry_run=True)
        manifest_path = tmp_path / "calibration-pack.json"

        payload = write_calibration_pack_manifest(
            manifest_path,
            [path],
            outcomes,
            max_per_label=10,
            judge_metadata={
                "kind": "compare",
                "cloud": {"kind": "cloud", "model": "fast-tier"},
                "local": JudgeSelection(kind="local", model="qwen2.5:14b").to_metadata(),
            },
        )

        assert payload["judge"]["kind"] == "compare"
        assert payload["judge"]["local"] == {"kind": "local", "model": "qwen2.5:14b"}

    def test_manifest_includes_selection_representation(self, tmp_path):
        from primr.qa.calibration_selection import CalibrationPackSelection

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        outcomes = run_calibration([path], dry_run=True)
        manifest_path = tmp_path / "calibration-pack.json"
        selection = CalibrationPackSelection(
            source_path=tmp_path / "selection.json",
            report_paths=(path,),
            required_tags=("clean", "blocked_origin"),
            tags_by_report={str(path.resolve(strict=False)): ("clean",)},
        )

        payload = write_calibration_pack_manifest(
            manifest_path,
            [path],
            outcomes,
            max_per_label=10,
            selection=selection,
        )

        assert payload["representation"]["required_tags"] == ["clean", "blocked_origin"]
        assert payload["representation"]["present_tags"] == ["clean"]
        assert payload["representation"]["missing_tags"] == ["blocked_origin"]
        assert payload["reports"][0]["coverage_tags"] == ["clean"]


class TestJudgeSelection:
    def test_cloud_mode_uses_harness_default(self):
        from primr.qa.calibration_runner import resolve_judge

        selection = resolve_judge("cloud")
        assert selection.kind == "cloud"
        assert selection.judge_fn is None  # harness default judge

    def test_local_mode_errors_when_no_server(self):
        from primr.qa.calibration_runner import resolve_judge

        with pytest.raises(RuntimeError, match="--judge auto"):
            resolve_judge("local", list_models_fn=lambda base: [])

    def test_auto_falls_back_to_cloud_silently(self):
        from primr.qa.calibration_runner import resolve_judge

        selection = resolve_judge("auto", list_models_fn=lambda base: [])
        assert selection.kind == "cloud"

    def test_auto_prefers_local_when_available(self):
        from primr.qa.calibration_runner import resolve_judge

        selection = resolve_judge(
            "auto",
            list_models_fn=lambda base: ["qwen2.5:14b"],
            make_local_judge_fn=lambda model, **kw: lambda c, t: True,
        )
        assert selection.kind == "local"
        assert selection.model == "qwen2.5:14b"
        assert selection.judge_fn("claim", "source") is True

    def test_pinned_model_overrides_auto_pick(self):
        from primr.qa.calibration_runner import resolve_judge

        selection = resolve_judge(
            "local",
            model="my-custom:13b",
            list_models_fn=lambda base: ["qwen2.5:14b", "my-custom:13b"],
            make_local_judge_fn=lambda model, **kw: lambda c, t: True,
        )
        assert selection.model == "my-custom:13b"

    def test_unknown_mode_raises(self):
        from primr.qa.calibration_runner import resolve_judge

        with pytest.raises(ValueError, match="judge mode"):
            resolve_judge("hybrid")


class TestLocalJudge:
    def test_local_judge_parses_completion(self):
        from types import SimpleNamespace

        from primr.qa.calibration_runner import make_local_judge

        judge = make_local_judge("m:7b", complete_fn=lambda *a, **k: SimpleNamespace(text="yes"))
        assert judge("claim", "source") is True

    def test_local_judge_strips_think_blocks(self):
        from types import SimpleNamespace

        from primr.qa.calibration_runner import make_local_judge

        judge = make_local_judge(
            "r1:32b",
            complete_fn=lambda *a, **k: SimpleNamespace(
                text="<think>the claim says X, source says X</think>\nyes"
            ),
        )
        assert judge("claim", "source") is True

    def test_local_failure_falls_back_and_counts(self):
        from primr.qa.calibration_runner import make_local_judge

        def explode(*a, **k):
            raise ConnectionError("server went away")

        counter = [0]
        judge = make_local_judge(
            "m:7b",
            complete_fn=explode,
            on_fallback=lambda c, t: True,
            fallback_counter=counter,
        )
        assert judge("claim", "source") is True  # fallback verdict, not False
        assert counter == [1]

    def test_local_failure_without_explicit_fallback_raises(self):
        from primr.qa.calibration_runner import make_local_judge

        def explode(*a, **k):
            raise ConnectionError("server went away")

        judge = make_local_judge("m:7b", complete_fn=explode)
        with pytest.raises(RuntimeError, match="cloud fallback is disabled"):
            judge("claim", "source")


class TestJudgeProvenance:
    def test_sidecar_records_judge_metadata(self, tmp_path):
        from primr.qa.calibration_runner import JudgeSelection

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        selection = JudgeSelection(kind="local", model="qwen2.5:14b", judge_fn=lambda c, t: True)
        run_calibration([path], fetch_fn=lambda u: "text", judge_selection=selection)
        payload = json.loads(sidecar_path_for(path).read_text(encoding="utf-8"))
        assert payload["judge"] == {"kind": "local", "model": "qwen2.5:14b"}

    def test_default_judge_metadata_is_cloud(self, tmp_path):
        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        run_calibration([path], fetch_fn=lambda u: "text", judge_fn=lambda c, t: True)
        payload = json.loads(sidecar_path_for(path).read_text(encoding="utf-8"))
        assert payload["judge"] == {"kind": "cloud", "model": "fast-tier"}


class TestJudgeComparison:
    def test_agreement_counts_decidable_claims_only(self, tmp_path):
        from primr.qa.calibration_runner import JudgeSelection, compare_judges

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        # Cloud says yes to everything; local says no to everything.
        local = JudgeSelection(kind="local", model="m:7b", judge_fn=lambda c, t: False)
        outcomes, agreement = compare_judges(
            [path],
            local_selection=local,
            fetch_fn=lambda u: "text",
            cloud_judge_fn=lambda c, t: True,
        )
        # Two judgeable claims (Confirmed + Reported); both decided by both judges.
        assert agreement.compared == 2
        assert agreement.agreed == 0
        assert agreement.agreement == 0.0
        # Sidecars come from the cloud pass.
        payload = json.loads(sidecar_path_for(path).read_text(encoding="utf-8"))
        assert payload["judge"]["kind"] == "cloud"
        assert payload["per_label"]["Confirmed"]["traceable"] == 1
        assert payload["judge_agreement"] == {
            "scope": "report",
            "local_model": "m:7b",
            "compared": 2,
            "agreed": 0,
            "agreement": 0.0,
        }

    def test_full_agreement(self, tmp_path):
        from primr.qa.calibration_runner import JudgeSelection, compare_judges

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        local = JudgeSelection(kind="local", model="m:7b", judge_fn=lambda c, t: True)
        _, agreement = compare_judges(
            [path],
            local_selection=local,
            fetch_fn=lambda u: "text",
            cloud_judge_fn=lambda c, t: True,
        )
        assert agreement.agreement == 1.0

    def test_cloud_judge_billed_once_per_pair(self, tmp_path):
        from primr.qa.calibration_runner import JudgeSelection, compare_judges

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        cloud_calls = []

        def counting_cloud(claim, text):
            cloud_calls.append(claim)
            return True

        local = JudgeSelection(kind="local", model="m:7b", judge_fn=lambda c, t: True)
        compare_judges(
            [path],
            local_selection=local,
            fetch_fn=lambda u: "text",
            cloud_judge_fn=counting_cloud,
        )
        # Two judgeable claims -> exactly two unique (claim, source) pairs,
        # despite the sidecar pass AND the comparison pass both consulting it.
        assert len(cloud_calls) == 2

    def test_unfetchable_claims_not_compared(self, tmp_path):
        from primr.qa.calibration_runner import JudgeSelection, compare_judges

        path = _write_report(tmp_path, "Acme_Strategic_Overview_01-01-2026.md")
        local = JudgeSelection(kind="local", model="m:7b", judge_fn=lambda c, t: True)
        _, agreement = compare_judges(
            [path],
            local_selection=local,
            fetch_fn=lambda u: "",  # nothing fetchable -> nothing decidable
            cloud_judge_fn=lambda c, t: True,
        )
        assert agreement.compared == 0
        assert agreement.agreement is None
        payload = json.loads(sidecar_path_for(path).read_text(encoding="utf-8"))
        assert payload["judge_agreement"]["compared"] == 0
        assert payload["judge_agreement"]["agreement"] is None


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
        assert config.calibrate_judge == "cloud"  # cloud is the default judge
        assert config.calibrate_judge_compare is False

    def test_judge_flags(self):
        from primr.core.cli import parse_args

        config = parse_args(
            ["calibrate", "Acme", "--judge", "auto", "--judge-model", "qwen2.5:14b"]
        )
        assert config.calibrate_judge == "auto"
        assert config.calibrate_judge_model == "qwen2.5:14b"

    def test_judge_compare_flag(self):
        from primr.core.cli import parse_args

        config = parse_args(["calibrate", "Acme", "--judge-compare"])
        assert config.calibrate_judge_compare is True

    def test_pack_manifest_flag(self):
        from primr.core.cli import parse_args

        config = parse_args(["calibrate", "Acme", "--pack-manifest", "pack.json"])
        assert config.calibrate_pack_manifest == "pack.json"

    def test_pack_selection_flag(self):
        from primr.core.cli import parse_args

        config = parse_args(["calibrate", "--pack-selection", "selection.json"])
        assert config.calibrate_pack_selection == "selection.json"

    def test_baseline_flags(self):
        from primr.core.cli import parse_args

        config = parse_args(
            [
                "calibrate",
                "--baseline-from",
                "pack.json",
                "--baseline-out",
                "baseline.json",
                "--baseline-md",
                "baseline.md",
                "--baseline-min-reports",
                "7",
            ]
        )
        assert config.calibrate_baseline_from == "pack.json"
        assert config.calibrate_baseline_out == "baseline.json"
        assert config.calibrate_baseline_md == "baseline.md"
        assert config.calibrate_baseline_min_reports == 7

    def test_invalid_judge_choice_rejected(self):
        from primr.core.cli import parse_args

        with pytest.raises(SystemExit):
            parse_args(["calibrate", "Acme", "--judge", "hybrid"])

    def test_handler_errors_when_nothing_resolves(self, tmp_path, monkeypatch):
        from primr.core.cli import CLIConfig, Command, _handle_calibrate

        monkeypatch.chdir(tmp_path)  # empty cwd: no output/ directory
        config = CLIConfig(command=Command.CALIBRATE, calibrate_target="NoSuchCo")
        assert _handle_calibrate(config) == 1

    def test_handler_errors_when_selection_conflicts_with_target(self, tmp_path, monkeypatch):
        from primr.core.cli import CLIConfig, Command, _handle_calibrate

        monkeypatch.chdir(tmp_path)
        config = CLIConfig(
            command=Command.CALIBRATE,
            calibrate_target="Acme",
            calibrate_pack_selection="selection.json",
        )
        assert _handle_calibrate(config) == 1
