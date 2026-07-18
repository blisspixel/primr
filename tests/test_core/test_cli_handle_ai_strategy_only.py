"""Unit tests for _handle_ai_strategy_only in primr.core.cli."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from primr.core.cli import CLIConfig, Command, _handle_ai_strategy_only


def _config(**overrides):
    defaults = {"command": Command.AI_STRATEGY_ONLY}
    defaults.update(overrides)
    return CLIConfig(**defaults)


@pytest.fixture
def report_under_output(tmp_path, monkeypatch):
    """Create a fake report file under a tmp OUTPUT_DIR so containment passes."""
    output_dir = tmp_path / "output"
    working_dir = tmp_path / "working"
    output_dir.mkdir()
    working_dir.mkdir()
    monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr("primr.config.config.WORKING_DIR", str(working_dir))

    report = output_dir / "Acme_Strategic_Overview_01-15-2026.md"
    report.write_text("# Strategic Overview\n\nbody", encoding="utf-8")
    return report


class TestEarlyValidation:
    def test_missing_path_returns_1(self):
        assert _handle_ai_strategy_only(_config(ai_strategy_only_path=None)) == 1

    def test_nonexistent_file_returns_1(self, tmp_path):
        bogus = tmp_path / "missing.md"
        assert _handle_ai_strategy_only(_config(ai_strategy_only_path=str(bogus))) == 1

    def test_file_outside_allowed_roots_returns_1(self, tmp_path, monkeypatch):
        # Put report in a location that's NOT under OUTPUT_DIR or WORKING_DIR
        other = tmp_path / "elsewhere"
        other.mkdir()
        bogus_report = other / "leaked.md"
        bogus_report.write_text("body", encoding="utf-8")
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr("primr.config.config.WORKING_DIR", str(tmp_path / "working"))
        assert _handle_ai_strategy_only(_config(ai_strategy_only_path=str(bogus_report))) == 1

    def test_output_destination_does_not_authorize_report_input(self, tmp_path, monkeypatch):
        other = tmp_path / "elsewhere"
        other.mkdir()
        report = other / "report.md"
        report.write_text("body", encoding="utf-8")
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path / "output"))
        monkeypatch.setattr("primr.config.config.WORKING_DIR", str(tmp_path / "working"))
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        result = _handle_ai_strategy_only(
            _config(ai_strategy_only_path=str(report), output_dir=str(other))
        )

        assert result == 1
        gen_mock.assert_not_called()

    def test_resolution_failure_is_fail_closed(self, report_under_output, monkeypatch):
        real_resolve = Path.resolve

        def fail_report_resolution(path, *args, **kwargs):
            if path == report_under_output:
                raise OSError("resolution unavailable")
            return real_resolve(path, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", fail_report_resolution)
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        assert (
            _handle_ai_strategy_only(_config(ai_strategy_only_path=str(report_under_output))) == 1
        )
        gen_mock.assert_not_called()

    def test_directory_is_rejected(self, tmp_path, monkeypatch):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (tmp_path / "working").mkdir()
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(output_dir))
        monkeypatch.setattr("primr.config.config.WORKING_DIR", str(tmp_path / "working"))
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        assert _handle_ai_strategy_only(_config(ai_strategy_only_path=str(output_dir))) == 1
        gen_mock.assert_not_called()

    def test_symlink_report_is_rejected(self, tmp_path, monkeypatch):
        output_dir = tmp_path / "output"
        working_dir = tmp_path / "working"
        outside = tmp_path / "outside.md"
        output_dir.mkdir()
        working_dir.mkdir()
        outside.write_text("outside", encoding="utf-8")
        link = output_dir / "linked.md"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symbolic links are unavailable on this filesystem")
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(output_dir))
        monkeypatch.setattr("primr.config.config.WORKING_DIR", str(working_dir))
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        assert _handle_ai_strategy_only(_config(ai_strategy_only_path=str(link))) == 1
        gen_mock.assert_not_called()

    def test_hard_link_report_is_rejected(self, tmp_path, monkeypatch):
        output_dir = tmp_path / "output"
        working_dir = tmp_path / "working"
        outside = tmp_path / "outside.md"
        output_dir.mkdir()
        working_dir.mkdir()
        outside.write_text("outside", encoding="utf-8")
        linked = output_dir / "linked.md"
        try:
            os.link(outside, linked)
        except OSError:
            pytest.skip("Hard links are unavailable on this filesystem")
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(output_dir))
        monkeypatch.setattr("primr.config.config.WORKING_DIR", str(working_dir))
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        assert _handle_ai_strategy_only(_config(ai_strategy_only_path=str(linked))) == 1
        gen_mock.assert_not_called()


class TestCompanyNameDerivation:
    def test_invalid_company_name_returns_1(self, report_under_output, monkeypatch):
        from primr.utils.validators import InputValidationError

        def reject(_name):
            raise InputValidationError(field="company_name", reason="too long")

        monkeypatch.setattr("primr.utils.validators.validate_company_name", reject)
        result = _handle_ai_strategy_only(_config(ai_strategy_only_path=str(report_under_output)))
        assert result == 1

    def test_uses_explicit_company_name(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                company_name="ExplicitCo",
                strategy_type="customer_experience",
            )
        )
        assert result == 0
        gen_mock.assert_called_once()
        kwargs = gen_mock.call_args.kwargs
        assert kwargs["company_name"] == "ExplicitCo"

    def test_extracts_company_from_filename(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        # company_name not set; should derive "Acme" from filename
        _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="ai",
                platforms=("azure",),
            )
        )
        kwargs = gen_mock.call_args.kwargs
        assert kwargs["company_name"] == "Acme"


class TestStrategyGeneration:
    def test_dry_run_never_generates(self, report_under_output, monkeypatch, capsys):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                dry_run_requested=True,
                platforms=("azure", "aws"),
            )
        )

        assert result == 0
        assert "Estimated cost" in capsys.readouterr().out
        gen_mock.assert_not_called()

    def test_budget_refusal_never_generates(self, report_under_output, monkeypatch):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                platforms=("azure",),
                budget_usd=0.01,
            )
        )

        assert result == 1
        gen_mock.assert_not_called()

    def test_busy_company_workspace_never_generates(self, report_under_output, monkeypatch, capsys):
        from primr.config.config import WORKING_DIR
        from primr.core.workspace import (
            acquire_company_run_lease_for_target,
            release_resume_lease,
        )

        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        company_root = acquire_company_run_lease_for_target(
            "Acme",
            None,
            base_dir=WORKING_DIR,
        )
        try:
            result = _handle_ai_strategy_only(
                _config(ai_strategy_only_path=str(report_under_output))
            )
        finally:
            release_resume_lease(company_root)

        assert result == 1
        assert "Another active run" in capsys.readouterr().out
        gen_mock.assert_not_called()

    @pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_budget_never_generates(self, report_under_output, monkeypatch, budget):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                platforms=("azure",),
                budget_usd=budget,
            )
        )

        assert result == 1
        gen_mock.assert_not_called()

    def test_declined_confirmation_never_generates(self, report_under_output, monkeypatch):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        monkeypatch.setattr("builtins.input", lambda _prompt: "n")

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                skip_confirm=False,
            )
        )

        assert result == 0
        gen_mock.assert_not_called()

    def test_forced_refresh_is_in_estimate(self, report_under_output, monkeypatch, capsys):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                dry_run_requested=True,
                refresh_vendor_research=True,
                platforms=("azure", "agnostic"),
            )
        )

        assert result == 0
        output = capsys.readouterr().out
        assert "Deep Research tasks: 3" in output
        assert "Vendor refresh tasks: 1" in output
        gen_mock.assert_not_called()

    def test_generates_for_each_vendor_in_ai_strategy(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="ai",
                platforms=("aws", "azure", "gcp"),
            )
        )
        # Called once per vendor.
        assert gen_mock.call_count == 3

    def test_generation_uses_private_stable_snapshot(self, report_under_output, monkeypatch):
        captured: dict[str, object] = {}

        def generate(**kwargs):
            snapshot = Path(kwargs["company_research_path"])
            captured["path"] = snapshot
            captured["content"] = snapshot.read_text(encoding="utf-8")
            return "/output/strategy.docx"

        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section",
            generate,
        )

        result = _handle_ai_strategy_only(_config(ai_strategy_only_path=str(report_under_output)))

        snapshot = captured["path"]
        assert result == 0
        assert isinstance(snapshot, Path)
        assert snapshot != report_under_output
        assert captured["content"] == report_under_output.read_text(encoding="utf-8")
        assert not snapshot.exists()

    def test_replacement_during_approval_never_generates(self, report_under_output, monkeypatch):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)

        def replace_then_approve(_prompt):
            report_under_output.unlink()
            report_under_output.write_text("replacement", encoding="utf-8")
            return "y"

        monkeypatch.setattr("builtins.input", replace_then_approve)

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                skip_confirm=False,
            )
        )

        assert result == 1
        gen_mock.assert_not_called()

    def test_same_identity_content_swap_during_approval_never_generates(
        self,
        report_under_output,
        monkeypatch,
    ):
        gen_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        original = report_under_output.read_bytes()
        original_stat = report_under_output.stat()

        def overwrite_then_approve(_prompt):
            with report_under_output.open("r+b") as report:
                report.write(b"X" * len(original))
                report.flush()
                os.fsync(report.fileno())
            os.utime(
                report_under_output,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            return "y"

        monkeypatch.setattr("builtins.input", overwrite_then_approve)

        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                skip_confirm=False,
            )
        )

        assert report_under_output.stat().st_ino == original_stat.st_ino
        assert report_under_output.stat().st_size == len(original)
        assert report_under_output.stat().st_mtime_ns == original_stat.st_mtime_ns
        assert result == 1
        gen_mock.assert_not_called()

    def test_non_ai_strategy_runs_once(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="customer_experience",
                platforms=("aws", "azure"),  # ignored for non-ai strategies
            )
        )
        assert gen_mock.call_count == 1
        # vendor is "agnostic" for non-ai
        assert gen_mock.call_args.kwargs["platform"] == "agnostic"

    def test_all_failures_return_1(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value=None)
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="customer_experience",
            )
        )
        assert result == 1

    def test_opens_last_result_when_requested(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        open_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent._generate_strategy_section", gen_mock)
        monkeypatch.setattr("primr.core.cli.open_file", open_mock)
        _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="customer_experience",
                open_after=True,
            )
        )
        open_mock.assert_called_once_with("/output/strategy.docx")


def test_parse_standalone_dry_run_keeps_governed_handler():
    from primr.core.cli import parse_args

    config = parse_args(["--ai-strategy-only", "output/report.md", "--dry-run"])

    assert config.command == Command.AI_STRATEGY_ONLY
    assert config.dry_run_requested is True
    assert config.skip_confirm is False
