"""Unit tests for perform_research early branches in primr.core.research_agent.

Full integration is impractical (the function is ~700 lines spanning
fast/deep/structured pipelines). These tests target the easily-testable
early-return paths plus the dispatch to perform_fast_research /
perform_deep_research / perform_scrape_only.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.core.research_agent import perform_research


@pytest.fixture
def isolated_run(tmp_path, monkeypatch):
    """Redirect WORKING_DIR/OUTPUT_DIR/LOGS_DIR to tmp_path."""
    monkeypatch.setattr("primr.core.research_agent.WORKING_DIR", str(tmp_path / "wk"))
    monkeypatch.setattr("primr.core.research_agent.OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr("primr.core.research_agent.LOGS_DIR", str(tmp_path / "logs"))


class TestEarlyReturns:
    def test_returns_none_when_no_company_or_website(self, isolated_run):
        assert perform_research(company_name=None, website=None) is None

    def test_returns_none_when_both_empty_strings(self, isolated_run):
        assert perform_research(company_name="", website="") is None

    def test_missing_discovery_notes_returns_none(self, isolated_run, tmp_path):
        # File that doesn't exist
        result = perform_research(
            company_name="Acme",
            website="https://acme.example",
            skip_recon=True,
            skip_confirm=True,
            discovery_notes_path=str(tmp_path / "missing.md"),
        )
        assert result is None


class TestDispatch:
    def test_dispatches_to_fast_mode_when_fast_flag_set(self, isolated_run, monkeypatch):
        fast_mock = MagicMock(return_value="/path/to/fast_report.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fast_mock)
        # Avoid network calls in recon path
        result = perform_research(
            company_name="Acme",
            website="https://acme.example",
            fast_mode=True,
            mode="complete",
            skip_recon=True,
            skip_confirm=True,
        )
        assert result == "/path/to/fast_report.docx"
        fast_mock.assert_called_once()

    def test_fast_mode_verify_runs_claim_verification(self, isolated_run, monkeypatch):
        fast_mock = MagicMock(return_value="/path/to/fast_report.docx")
        verify_mock = MagicMock()
        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fast_mock)
        monkeypatch.setattr(
            "primr.core.research_agent._run_claim_verification_non_blocking", verify_mock
        )

        result = perform_research(
            company_name="Acme",
            website="https://acme.example",
            fast_mode=True,
            mode="complete",
            skip_recon=True,
            skip_confirm=True,
            verify=True,
        )

        assert result == "/path/to/fast_report.docx"
        verify_mock.assert_called_once_with("Acme", "https://acme.example", result)

    def test_dispatches_to_scrape_only_for_scrape_mode(self, isolated_run, monkeypatch):
        scrape_mock = MagicMock(return_value="/path/scrape_dir")
        monkeypatch.setattr("primr.core.research_agent.perform_scrape_only", scrape_mock)
        result = perform_research(
            company_name="Acme",
            website="https://acme.example",
            mode="scrape-only",
            skip_recon=True,
            skip_confirm=True,
            fast_mode=False,
        )
        assert result == "/path/scrape_dir"

    def test_dispatches_to_deep_research_for_deep_mode(self, isolated_run, monkeypatch):
        deep_mock = MagicMock(return_value="/path/to/deep.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_deep_research", deep_mock)
        # Force fast_mode auto-detect to be off by removing XAI key.
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        result = perform_research(
            company_name="Acme",
            website="https://acme.example",
            mode="deep-research",
            skip_recon=True,
            skip_confirm=True,
            fast_mode=False,
            premium_mode=True,  # blocks fast-mode auto-detect
        )
        assert result == "/path/to/deep.docx"
        deep_mock.assert_called_once()


class TestRunStateInitialization:
    def test_creates_run_state_file_with_company_metadata(
        self, isolated_run, monkeypatch, tmp_path
    ):
        # Mock the dispatch target so we exit before doing anything expensive.
        monkeypatch.setattr(
            "primr.core.research_agent.perform_fast_research",
            MagicMock(return_value="/x.docx"),
        )

        perform_research(
            company_name="Acme",
            website="https://acme.example",
            fast_mode=True,
            mode="complete",
            skip_recon=True,
            skip_confirm=True,
        )

        # A working folder + _run_state.json should exist under WORKING_DIR.
        wk = tmp_path / "wk"
        state_files = list(wk.glob("**/_run_state.json"))
        assert len(state_files) >= 1
        import json

        loaded = json.loads(state_files[0].read_text(encoding="utf-8"))
        assert loaded["company_name"] == "Acme"
        assert loaded["mode"] == "complete"

    def test_premium_mode_disables_fast_auto_detect(self, isolated_run, monkeypatch):
        # Even with XAI key set, premium mode should NOT trigger fast-mode dispatch.
        monkeypatch.setenv("XAI_API_KEY", "x" * 30)
        fast_mock = MagicMock(return_value="/should-not-call.docx")
        deep_mock = MagicMock(return_value="/deep.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fast_mock)
        monkeypatch.setattr("primr.core.research_agent.perform_deep_research", deep_mock)

        result = perform_research(
            company_name="Acme",
            website="https://acme.example",
            mode="complete",
            premium_mode=True,
            skip_recon=True,
            skip_confirm=True,
        )
        assert result == "/deep.docx"
        fast_mock.assert_not_called()
        deep_mock.assert_called_once()


class TestRunFolder:
    def test_returns_none_for_empty_inputs(self, isolated_run):
        # Already tested in TestEarlyReturns — sanity check the public API matches.
        assert perform_research() is None

    def test_uses_explicit_output_dir(self, isolated_run, tmp_path, monkeypatch):
        custom_out = tmp_path / "custom_out"
        fast_mock = MagicMock(return_value="/x.docx")
        monkeypatch.setattr("primr.core.research_agent.perform_fast_research", fast_mock)

        perform_research(
            company_name="Acme",
            website="https://acme.example",
            fast_mode=True,
            mode="complete",
            output_dir=str(custom_out),
            skip_recon=True,
            skip_confirm=True,
        )
        # The custom output dir should have been created and passed to perform_fast_research.
        assert custom_out.exists()
        # The call to perform_fast_research should use the custom dir
        kwargs = fast_mock.call_args.kwargs
        assert str(custom_out) in str(kwargs.get("output_dir", ""))
