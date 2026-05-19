"""Unit tests for the small _handle_* command dispatchers in primr.core.cli.

Most handlers are thin delegators: they map a parsed `CLIConfig` to a
service call and return the exit code. These tests mock the services
and confirm the delegation contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.core.cli import (
    CLIConfig,
    Command,
    _handle_check_jobs,
    _handle_check_quota,
    _handle_clean_temp,
    _handle_clear_jobs,
    _handle_doctor,
    _handle_init,
    _handle_list_recent,
    _handle_resume_latest,
    _handle_show_usage,
)


def _config(**overrides):
    """Build a CLIConfig with sensible defaults for handler tests."""
    defaults = {
        "command": Command.RESEARCH,
    }
    defaults.update(overrides)
    return CLIConfig(**defaults)


class TestHandleInit:
    def test_delegates_to_run_init_flow_with_flags(self, monkeypatch):
        mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._run_init_flow", mock)
        config = _config(
            init_non_interactive=True,
            init_yes=True,
            init_skip_browsers=True,
            init_no_doctor=True,
        )
        assert _handle_init(config) == 0
        mock.assert_called_once_with(
            non_interactive=True,
            assume_yes=True,
            skip_browsers=True,
            run_doctor_after=False,
        )

    def test_init_no_doctor_inverted(self, monkeypatch):
        mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli._run_init_flow", mock)
        config = _config(init_no_doctor=False)
        _handle_init(config)
        kwargs = mock.call_args.kwargs
        assert kwargs["run_doctor_after"] is True


class TestHandleDoctor:
    def test_delegates_with_fix_flag(self, monkeypatch):
        mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.run_doctor", mock)
        config = _config(doctor_fix=True)
        assert _handle_doctor(config) == 0
        mock.assert_called_once_with(fix=True)

    def test_delegates_without_fix(self, monkeypatch):
        mock = MagicMock(return_value=1)
        monkeypatch.setattr("primr.core.cli.run_doctor", mock)
        config = _config(doctor_fix=False)
        assert _handle_doctor(config) == 1
        mock.assert_called_once_with(fix=False)


class TestHandleListRecent:
    def test_calls_list_recent_and_returns_zero(self, monkeypatch):
        mock = MagicMock()
        monkeypatch.setattr("primr.core.cli.list_recent_outputs", mock)
        config = _config()
        assert _handle_list_recent(config) == 0
        mock.assert_called_once()


class TestHandleCleanTemp:
    def test_calls_clean_temp_and_returns_zero(self, monkeypatch):
        mock = MagicMock()
        monkeypatch.setattr("primr.core.cli.clean_temp_files", mock)
        assert _handle_clean_temp(_config()) == 0
        mock.assert_called_once()


class TestHandleCheckQuota:
    def test_calls_check_quota_and_returns_zero(self, monkeypatch):
        mock = MagicMock()
        monkeypatch.setattr("primr.core.cli.check_api_quota", mock)
        assert _handle_check_quota(_config()) == 0
        mock.assert_called_once()


class TestHandleCheckJobs:
    def test_calls_check_pending_and_returns_zero(self, monkeypatch):
        mock = MagicMock()
        monkeypatch.setattr("primr.core.cli.check_pending_jobs", mock)
        assert _handle_check_jobs(_config()) == 0
        mock.assert_called_once()


class TestHandleResumeLatest:
    def test_delegates_to_resume_pending_jobs(self, monkeypatch):
        mock = MagicMock(return_value=0)
        monkeypatch.setattr("primr.core.cli.resume_pending_jobs", mock)
        assert _handle_resume_latest(_config()) == 0
        mock.assert_called_once()

    def test_propagates_nonzero_exit_code(self, monkeypatch):
        mock = MagicMock(return_value=1)
        monkeypatch.setattr("primr.core.cli.resume_pending_jobs", mock)
        assert _handle_resume_latest(_config()) == 1


class TestHandleClearJobs:
    def test_no_pending_jobs_returns_zero(self, monkeypatch):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(dr, "get_pending_jobs", dict)
        # The function uses `from primr.ai.deep_research import get_pending_jobs`
        # which means we need to patch where it's looked up (the import site).
        assert _handle_clear_jobs(_config()) == 0

    def test_writes_empty_dict_when_pending_jobs(self, tmp_path, monkeypatch):
        import primr.ai.deep_research as dr

        monkeypatch.setattr(
            dr, "get_pending_jobs", lambda: {"j1": {"description": "x"}}
        )
        # Redirect LOGS_DIR to tmp_path so the file write lands in our sandbox.
        monkeypatch.setattr("primr.core.cli.LOGS_DIR", str(tmp_path))
        monkeypatch.setattr(
            "primr.config.config.LOGS_DIR", str(tmp_path)
        )
        assert _handle_clear_jobs(_config()) == 0

        import json

        jobs_file = tmp_path / "pending_research_jobs.json"
        assert jobs_file.exists()
        assert json.loads(jobs_file.read_text()) == {}


class TestHandleShowUsage:
    def test_delegates_to_usage_tracker(self, monkeypatch, capsys):
        tracker = MagicMock()
        tracker.display_usage_history.return_value = "USAGE HISTORY"
        with patch(
            "primr.utils.usage_tracker.get_usage_tracker", return_value=tracker
        ):
            assert _handle_show_usage(_config()) == 0
        captured = capsys.readouterr()
        assert "USAGE HISTORY" in captured.out


@pytest.mark.parametrize(
    ("handler", "patch_path"),
    [
        (_handle_list_recent, "primr.core.cli.list_recent_outputs"),
        (_handle_clean_temp, "primr.core.cli.clean_temp_files"),
        (_handle_check_quota, "primr.core.cli.check_api_quota"),
        (_handle_check_jobs, "primr.core.cli.check_pending_jobs"),
    ],
)
def test_simple_handlers_call_their_service(handler, patch_path, monkeypatch):
    """All four utility handlers should call their service exactly once and return 0."""
    mock = MagicMock()
    monkeypatch.setattr(patch_path, mock)
    assert handler(_config()) == 0
    mock.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_qa_recent / _handle_qa / _handle_improve — additional handlers
# ---------------------------------------------------------------------------


class TestHandleQaRecent:
    def test_uses_default_count_when_none(self, monkeypatch):
        from primr.core.cli import _handle_qa_recent

        cmd = MagicMock()
        cmd.show_recent_qa_summary.return_value = 0
        monkeypatch.setattr("primr.qa.command.QACommand", lambda: cmd)
        assert _handle_qa_recent(_config(qa_recent_count=None)) == 0
        cmd.show_recent_qa_summary.assert_called_once_with(5)

    def test_passes_explicit_count(self, monkeypatch):
        from primr.core.cli import _handle_qa_recent

        cmd = MagicMock()
        cmd.show_recent_qa_summary.return_value = 0
        monkeypatch.setattr("primr.qa.command.QACommand", lambda: cmd)
        _handle_qa_recent(_config(qa_recent_count=10))
        cmd.show_recent_qa_summary.assert_called_once_with(10)

    def test_returns_1_on_exception(self, monkeypatch):
        from primr.core.cli import _handle_qa_recent

        def raises(*_a, **_k):
            raise RuntimeError("qa down")

        monkeypatch.setattr("primr.qa.command.QACommand", raises)
        assert _handle_qa_recent(_config(qa_recent_count=5)) == 1


class TestHandleQa:
    def test_returns_1_when_company_missing(self, monkeypatch):
        from primr.core.cli import _handle_qa

        assert _handle_qa(_config(qa_company=None)) == 1

    def test_analyzes_existing_file(self, tmp_path, monkeypatch):
        from primr.core.cli import _handle_qa

        report = tmp_path / "report.docx"
        report.write_text("body", encoding="utf-8")
        cmd = MagicMock()
        cmd.analyze_report_file.return_value = 0
        monkeypatch.setattr("primr.qa.command.QACommand", lambda: cmd)
        result = _handle_qa(_config(qa_company=str(report)))
        assert result == 0
        cmd.analyze_report_file.assert_called_once_with(str(report))

    def test_path_like_missing_file_returns_1(self, tmp_path, monkeypatch):
        from primr.core.cli import _handle_qa

        cmd = MagicMock()
        monkeypatch.setattr("primr.qa.command.QACommand", lambda: cmd)
        result = _handle_qa(_config(qa_company=str(tmp_path / "missing.docx")))
        assert result == 1

    def test_treats_company_name_as_lookup(self, monkeypatch):
        from primr.core.cli import _handle_qa

        cmd = MagicMock()
        cmd.show_detailed_analysis.return_value = 0
        monkeypatch.setattr("primr.qa.command.QACommand", lambda: cmd)
        result = _handle_qa(_config(qa_company="ExampleCo"))
        assert result == 0
        cmd.show_detailed_analysis.assert_called_once_with("ExampleCo")

    def test_exception_returns_1(self, monkeypatch):
        from primr.core.cli import _handle_qa

        def raises():
            raise RuntimeError("qa down")

        monkeypatch.setattr("primr.qa.command.QACommand", raises)
        result = _handle_qa(_config(qa_company="ExampleCo"))
        assert result == 1


class TestHandleImprove:
    def test_returns_1_when_path_missing(self, monkeypatch):
        from primr.core.cli import _handle_improve

        assert _handle_improve(_config(improve_path=None)) == 1

    def test_calls_improve_output_file_with_in_place_flag(self, monkeypatch):
        from primr.core.cli import _handle_improve

        mock_improve = MagicMock(return_value="/path/to/improved.md")
        monkeypatch.setattr(
            "primr.core.research_agent.improve_output_file", mock_improve
        )
        result = _handle_improve(
            _config(improve_path="/in.md", improve_in_place=True, improve_agentic=False)
        )
        assert result == 0
        mock_improve.assert_called_once_with(
            "/in.md", in_place=True, use_agentic=False
        )

    def test_returns_1_when_improve_returns_none(self, monkeypatch):
        from primr.core.cli import _handle_improve

        monkeypatch.setattr(
            "primr.core.research_agent.improve_output_file",
            MagicMock(return_value=None),
        )
        assert _handle_improve(_config(improve_path="/in.md")) == 1
