"""Unit tests for _handle_ai_strategy_only in primr.core.cli."""

from __future__ import annotations

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
        assert (
            _handle_ai_strategy_only(_config(ai_strategy_only_path=str(bogus)))
            == 1
        )

    def test_file_outside_allowed_roots_returns_1(self, tmp_path, monkeypatch):
        # Put report in a location that's NOT under OUTPUT_DIR or WORKING_DIR
        other = tmp_path / "elsewhere"
        other.mkdir()
        bogus_report = other / "leaked.md"
        bogus_report.write_text("body", encoding="utf-8")
        monkeypatch.setattr(
            "primr.config.config.OUTPUT_DIR", str(tmp_path / "output")
        )
        monkeypatch.setattr(
            "primr.config.config.WORKING_DIR", str(tmp_path / "working")
        )
        assert (
            _handle_ai_strategy_only(
                _config(ai_strategy_only_path=str(bogus_report))
            )
            == 1
        )


class TestCompanyNameDerivation:
    def test_invalid_company_name_returns_1(
        self, report_under_output, monkeypatch
    ):
        from primr.utils.validators import InputValidationError

        def reject(_name):
            raise InputValidationError(field="company_name", reason="too long")

        monkeypatch.setattr("primr.utils.validators.validate_company_name", reject)
        result = _handle_ai_strategy_only(
            _config(ai_strategy_only_path=str(report_under_output))
        )
        assert result == 1

    def test_uses_explicit_company_name(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section", gen_mock
        )
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

    def test_extracts_company_from_filename(
        self, report_under_output, monkeypatch
    ):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section", gen_mock
        )
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
    def test_generates_for_each_vendor_in_ai_strategy(
        self, report_under_output, monkeypatch
    ):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section", gen_mock
        )
        _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="ai",
                platforms=("aws", "azure", "gcp"),
            )
        )
        # Called once per vendor.
        assert gen_mock.call_count == 3

    def test_non_ai_strategy_runs_once(self, report_under_output, monkeypatch):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section", gen_mock
        )
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
        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section", gen_mock
        )
        result = _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="customer_experience",
            )
        )
        assert result == 1

    def test_opens_last_result_when_requested(
        self, report_under_output, monkeypatch
    ):
        gen_mock = MagicMock(return_value="/output/strategy.docx")
        open_mock = MagicMock()
        monkeypatch.setattr(
            "primr.core.research_agent._generate_strategy_section", gen_mock
        )
        monkeypatch.setattr("primr.core.cli.open_file", open_mock)
        _handle_ai_strategy_only(
            _config(
                ai_strategy_only_path=str(report_under_output),
                strategy_type="customer_experience",
                open_after=True,
            )
        )
        open_mock.assert_called_once_with("/output/strategy.docx")
