"""Additional coverage for primr.core.research_orchestrator.

Focuses on real behavior the existing suite skips: the async ``research``
dispatch and its success/failure metrics paths, each ``_run_*`` engine method
(deep research, structured, complete, hybrid, deep-research-with-context),
the temp-file helpers, and the ``_summarize_context`` helper.

All LLM / subagent / scrape boundaries are mocked — no network or real APIs.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from primr.core.research_orchestrator import (
    OrchestratorResult,
    ResearchConfig,
    ResearchMode,
    ResearchOrchestrator,
    _cleanup_file_with_retry,
    temp_context_file,
)
from primr.utils.errors import ResearchError

MODULE = "primr.core.research_orchestrator"


# ---------------------------------------------------------------------------
# temp file helpers
# ---------------------------------------------------------------------------


class TestCleanupFileWithRetry:
    def test_removes_existing_file(self, tmp_path):
        f = tmp_path / "scratch.txt"
        f.write_text("data", encoding="utf-8")
        assert _cleanup_file_with_retry(str(f)) is True
        assert not f.exists()

    def test_missing_file_is_considered_clean(self, tmp_path):
        missing = tmp_path / "nope.txt"
        assert _cleanup_file_with_retry(str(missing)) is True

    def test_retries_then_gives_up_and_warns(self, tmp_path):
        f = tmp_path / "locked.txt"
        f.write_text("x", encoding="utf-8")

        # os.path.exists -> True so it attempts remove; os.remove always raises.
        with (
            patch(f"{MODULE}.os.path.exists", return_value=True),
            patch(f"{MODULE}.os.remove", side_effect=OSError("locked")),
            patch("time.sleep") as mock_sleep,
        ):
            result = _cleanup_file_with_retry(str(f), max_retries=3, delay=0.01)

        assert result is False
        # Slept between the first two failed attempts (not after the last).
        assert mock_sleep.call_count == 2

    def test_succeeds_on_second_attempt(self, tmp_path):
        f = tmp_path / "retry.txt"

        with (
            patch(f"{MODULE}.os.path.exists", return_value=True),
            patch(f"{MODULE}.os.remove", side_effect=[OSError("busy"), None]),
            patch("time.sleep"),
        ):
            result = _cleanup_file_with_retry(str(f), max_retries=3, delay=0.01)

        assert result is True


class TestTempContextFile:
    def test_writes_content_and_cleans_up(self):
        captured = {}
        with temp_context_file("Acme Corp", "hello world") as path:
            captured["path"] = path
            assert os.path.exists(path)
            assert path.endswith(".txt")
            assert "Acme_Corp_step1_" in os.path.basename(path)
            with open(path, encoding="utf-8") as fh:
                assert fh.read() == "hello world"
        # Cleanup happened on exit.
        assert not os.path.exists(captured["path"])

    def test_sanitizes_company_name_with_slash(self):
        with temp_context_file("Acme/Co Ltd", "x") as path:
            name = os.path.basename(path)
            assert "/" not in name
            assert "Acme_Co_Ltd_step1_" in name


# ---------------------------------------------------------------------------
# _summarize_context (pure helper)
# ---------------------------------------------------------------------------


class TestSummarizeContext:
    def test_empty_returns_placeholder(self):
        orch = ResearchOrchestrator()
        assert orch._summarize_context({}) == "No initial context available."

    def test_only_priority_sections_included(self):
        orch = ResearchOrchestrator()
        sections = {
            "company_overview": "We make widgets.",
            "non_priority": "ignored content",
        }
        summary = orch._summarize_context(sections)
        assert "Company Overview" in summary
        assert "We make widgets." in summary
        assert "ignored content" not in summary

    def test_long_sections_truncated(self):
        orch = ResearchOrchestrator()
        long_text = "z" * 600
        summary = orch._summarize_context({"company_overview": long_text})
        assert "..." in summary
        assert "z" * 600 not in summary

    def test_no_priority_sections_returns_limited(self):
        orch = ResearchOrchestrator()
        summary = orch._summarize_context({"random": "stuff"})
        assert summary == "Limited context available."


# ---------------------------------------------------------------------------
# research() dispatch + metrics
# ---------------------------------------------------------------------------


def _ok_result(mode: ResearchMode) -> OrchestratorResult:
    return OrchestratorResult(
        company_name="Acme Corp",
        website="https://acme.example",
        mode=mode,
        section_results={"company_overview": "x"},
        citations=["c1"],
        success=True,
    )


class TestResearchDispatch:
    @pytest.mark.asyncio
    async def test_structured_mode_dispatch_sets_duration_and_metrics(self):
        orch = ResearchOrchestrator()

        async def fake_structured(name, site, cfg, prog):
            return _ok_result(ResearchMode.STRUCTURED)

        with (
            patch.object(orch, "_run_structured_research", side_effect=fake_structured),
            patch.object(orch, "_emit_research_metrics") as mock_metrics,
        ):
            result = await orch.research(
                "Acme Corp", "https://acme.example", mode=ResearchMode.STRUCTURED
            )

        assert result.success is True
        assert result.duration_seconds >= 0
        mock_metrics.assert_called_once()
        kwargs = mock_metrics.call_args.kwargs
        assert kwargs["success"] is True
        assert kwargs["mode"] == "structured"
        assert kwargs["section_count"] == 1
        assert kwargs["citation_count"] == 1

    @pytest.mark.asyncio
    async def test_deep_research_mode_dispatch(self):
        orch = ResearchOrchestrator()

        async def fake_dr(name, site, cfg, prog, ctx):
            return _ok_result(ResearchMode.DEEP_RESEARCH)

        with (
            patch.object(orch, "_run_deep_research_with_context", side_effect=fake_dr),
            patch.object(orch, "_emit_research_metrics"),
        ):
            result = await orch.research("Acme Corp", mode=ResearchMode.DEEP_RESEARCH)

        assert result.mode == ResearchMode.DEEP_RESEARCH
        assert result.success is True

    @pytest.mark.asyncio
    async def test_complete_mode_dispatch(self):
        orch = ResearchOrchestrator()

        async def fake_complete(name, site, cfg, prog, ctx):
            return _ok_result(ResearchMode.COMPLETE)

        with (
            patch.object(orch, "_run_complete_research", side_effect=fake_complete),
            patch.object(orch, "_emit_research_metrics"),
        ):
            result = await orch.research("Acme Corp", mode=ResearchMode.COMPLETE)

        assert result.mode == ResearchMode.COMPLETE

    @pytest.mark.asyncio
    async def test_hybrid_mode_dispatch(self):
        orch = ResearchOrchestrator()

        async def fake_hybrid(name, site, cfg, prog):
            return _ok_result(ResearchMode.HYBRID)

        with (
            patch.object(orch, "_run_hybrid_research", side_effect=fake_hybrid),
            patch.object(orch, "_emit_research_metrics"),
        ):
            result = await orch.research("Acme Corp", mode=ResearchMode.HYBRID)

        assert result.mode == ResearchMode.HYBRID

    @pytest.mark.asyncio
    async def test_exception_path_returns_failed_result_and_emits_failure_metrics(self):
        orch = ResearchOrchestrator()

        async def boom(name, site, cfg, prog):
            raise ValueError("kaboom")

        with (
            patch.object(orch, "_run_structured_research", side_effect=boom),
            patch.object(orch, "_emit_research_metrics") as mock_metrics,
        ):
            result = await orch.research(
                "Acme Corp", "https://acme.example", mode=ResearchMode.STRUCTURED
            )

        assert result.success is False
        assert result.error == "kaboom"
        assert result.section_results == {}
        kwargs = mock_metrics.call_args.kwargs
        assert kwargs["success"] is False
        assert kwargs["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_uses_provided_config_over_constructed_one(self):
        orch = ResearchOrchestrator()
        seen = {}

        async def capture(name, site, cfg, prog):
            seen["cfg"] = cfg
            return _ok_result(ResearchMode.STRUCTURED)

        cfg = ResearchConfig(mode=ResearchMode.STRUCTURED, timeout=42)
        with (
            patch.object(orch, "_run_structured_research", side_effect=capture),
            patch.object(orch, "_emit_research_metrics"),
        ):
            await orch.research("Acme Corp", config=cfg, mode=ResearchMode.STRUCTURED)

        assert seen["cfg"] is cfg
        assert seen["cfg"].timeout == 42


# ---------------------------------------------------------------------------
# _emit_research_metrics
# ---------------------------------------------------------------------------


class TestEmitResearchMetrics:
    def test_builds_metrics_object_with_metadata(self):
        orch = ResearchOrchestrator()
        with patch(f"{MODULE}.emit_metrics") as mock_emit:
            orch._emit_research_metrics(
                operation="research",
                company_name="Acme Corp",
                mode="structured",
                duration=12.5,
                success=True,
                section_count=3,
                citation_count=7,
            )
        metric = mock_emit.call_args.args[0]
        assert metric.operation == "research"
        assert metric.duration_seconds == 12.5
        assert metric.success is True
        assert metric.metadata["company"] == "Acme Corp"
        assert metric.metadata["sections"] == 3
        assert metric.metadata["citations"] == 7


# ---------------------------------------------------------------------------
# _run_structured_research
# ---------------------------------------------------------------------------


class TestRunStructuredResearch:
    @pytest.mark.asyncio
    async def test_success_maps_sections(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig()

        with patch(
            "primr.core.research_agent.run_research",
            return_value={"company_overview": "data"},
        ) as mock_run:
            result = await orch._run_structured_research(
                "Acme Corp", "https://acme.example", cfg, None
            )

        assert result.success is True
        assert result.section_results == {"company_overview": "data"}
        # website passed through, fail_on_low_scrape forwarded from config
        _, kwargs = mock_run.call_args
        assert kwargs["fail_on_low_scrape"] is True

    @pytest.mark.asyncio
    async def test_empty_result_marks_failure(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig()

        with patch("primr.core.research_agent.run_research", return_value={}):
            result = await orch._run_structured_research("Acme Corp", None, cfg, None)

        assert result.success is False
        assert result.section_results == {}

    @pytest.mark.asyncio
    async def test_none_website_becomes_empty_string(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig()

        with patch(
            "primr.core.research_agent.run_research",
            return_value={"x": "y"},
        ) as mock_run:
            await orch._run_structured_research("Acme Corp", None, cfg, None)

        # second positional arg is the website
        assert mock_run.call_args.args[1] == ""


# ---------------------------------------------------------------------------
# _run_deep_research
# ---------------------------------------------------------------------------


class TestRunDeepResearch:
    @pytest.mark.asyncio
    async def test_success_normalizes_result(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)

        dr_result = Mock()
        dr_result.success = True
        dr_result.content = "## Company Overview\n\nWidgets."
        dr_result.citations = ["http://src"]
        dr_result.search_queries_count = 5

        mock_client = MagicMock()

        async def fake_research(**kwargs):
            return dr_result

        mock_client.research = fake_research

        progress_msgs: list[str] = []
        with patch.object(ResearchOrchestrator, "deep_research_client", new=mock_client):
            result = await orch._run_deep_research(
                "Acme Corp", "https://acme.example", cfg, progress_msgs.append
            )

        assert result.success is True
        assert result.search_queries_count == 5
        assert "company_overview" in result.section_results

    @pytest.mark.asyncio
    async def test_failure_raises_research_error(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)

        dr_result = Mock()
        dr_result.success = False
        dr_result.error = "quota exhausted"

        mock_client = MagicMock()

        async def fake_research(**kwargs):
            return dr_result

        mock_client.research = fake_research

        with (
            patch.object(ResearchOrchestrator, "deep_research_client", new=mock_client),
            pytest.raises(ResearchError, match="quota exhausted"),
        ):
            await orch._run_deep_research("Acme Corp", None, cfg, None)

    @pytest.mark.asyncio
    async def test_progress_callback_invoked(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)

        dr_result = Mock()
        dr_result.success = True
        dr_result.content = "plain"
        dr_result.citations = []
        dr_result.search_queries_count = 0

        captured = {}

        async def fake_research(**kwargs):
            # Exercise the inner progress_callback wrapper.
            cb = kwargs["on_progress"]
            prog = Mock()
            prog.message = "thinking"
            prog.thought = None
            cb(prog)
            captured["priority"] = kwargs["priority_urls"]
            return dr_result

        mock_client = MagicMock()
        mock_client.research = fake_research

        msgs: list[str] = []
        with patch.object(ResearchOrchestrator, "deep_research_client", new=mock_client):
            await orch._run_deep_research("Acme Corp", "https://acme.example", cfg, msgs.append)

        assert "thinking" in msgs
        assert captured["priority"] == ["https://acme.example"]


# ---------------------------------------------------------------------------
# _run_deep_research_with_context (Accordion method)
# ---------------------------------------------------------------------------


class TestRunDeepResearchWithContext:
    @pytest.mark.asyncio
    async def test_success_formats_report(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)

        deep_result = Mock()
        deep_result.success = True
        deep_result.content = "raw report"
        deep_result.api_calls = 2
        deep_result.sections_written = 8
        deep_result.search_queries_count = 11

        mock_orch = MagicMock()

        async def gen(**kwargs):
            assert kwargs["stage1_context"] is None
            return deep_result

        mock_orch.generate_comprehensive_report = gen

        formatted = Mock()
        formatted.markdown = "# Report"
        formatted.word_count = 1000
        formatted.citations = ["c"]

        with (
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = formatted
            result = await orch._run_deep_research_with_context(
                "Acme Corp", "https://acme.example", cfg, None, None
            )

        assert result.success is True
        assert result.section_results["strategic_overview"] == "# Report"
        assert result.sections_written == 8
        assert result.search_queries_count == 11
        assert result.citations == ["c"]

    @pytest.mark.asyncio
    async def test_failure_returns_failed_result(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)

        deep_result = Mock()
        deep_result.success = False
        deep_result.error = "boom"

        mock_orch = MagicMock()

        async def gen(**kwargs):
            return deep_result

        mock_orch.generate_comprehensive_report = gen

        with patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_orch):
            result = await orch._run_deep_research_with_context("Acme Corp", None, cfg, None, None)

        assert result.success is False
        assert result.error == "boom"
        assert result.section_results == {}


# ---------------------------------------------------------------------------
# _run_hybrid_research
# ---------------------------------------------------------------------------


class TestRunHybridResearch:
    @pytest.mark.asyncio
    async def test_merges_and_overrides_website_sections(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.HYBRID)

        deep = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.DEEP_RESEARCH,
            section_results={
                "industry_insights": "deep industry",
                "detailed_products_services": "deep products",
            },
            success=True,
        )
        structured = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.STRUCTURED,
            section_results={"detailed_products_services": "scraped products"},
            success=True,
        )

        async def fake_deep(*a):
            return deep

        async def fake_struct(*a):
            return structured

        with (
            patch.object(orch, "_run_deep_research", side_effect=fake_deep),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
        ):
            result = await orch._run_hybrid_research("Acme Corp", "https://acme.example", cfg, None)

        assert result.success is True
        # deep-only section preserved
        assert result.section_results["industry_insights"] == "deep industry"
        # website-specific section overridden by structured
        assert result.section_results["detailed_products_services"] == "scraped products"

    @pytest.mark.asyncio
    async def test_handles_exceptions_from_parallel_tasks(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.HYBRID)

        async def fake_deep(*a):
            raise RuntimeError("deep failed")

        async def fake_struct(*a):
            raise RuntimeError("struct failed")

        with (
            patch.object(orch, "_run_deep_research", side_effect=fake_deep),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
        ):
            result = await orch._run_hybrid_research("Acme Corp", None, cfg, None)

        # Both failed -> empty sections -> success False
        assert result.section_results == {}
        assert result.success is False


# ---------------------------------------------------------------------------
# _run_complete_research
# ---------------------------------------------------------------------------


def _make_console_patch():
    """Patch the console import used inside _run_complete_research."""
    return patch("primr.utils.console.console", new=MagicMock())


class TestRunCompleteResearch:
    @pytest.mark.asyncio
    async def test_happy_path_combines_sections(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.COMPLETE)

        structured = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.STRUCTURED,
            section_results={"company_overview": "scraped overview"},
            success=True,
        )

        async def fake_struct(*a):
            return structured

        deep_result = Mock()
        deep_result.success = True
        deep_result.content = "raw"
        deep_result.api_calls = 1
        deep_result.citations = ["c1"]
        deep_result.search_queries_count = 9

        mock_dr_orch = MagicMock()

        async def gen(**kwargs):
            assert kwargs["stage1_context"] is not None
            return deep_result

        mock_dr_orch.generate_comprehensive_report = gen

        formatted = Mock()
        formatted.markdown = "# Deep Report"
        formatted.table_of_contents = "TOC"
        formatted.word_count = 5000
        formatted.chapters = ["c1", "c2"]

        with (
            _make_console_patch(),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_dr_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = formatted
            result = await orch._run_complete_research(
                "Acme Corp", "https://acme.example", cfg, None, None
            )

        assert result.success is True
        assert result.section_results["strategic_overview"] == "# Deep Report"
        assert result.section_results["table_of_contents"] == "TOC"
        # structured section merged in for backward compat
        assert result.section_results["company_overview"] == "scraped overview"
        assert result.search_queries_count == 9

    @pytest.mark.asyncio
    async def test_aborts_when_structured_fails_and_strict(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.COMPLETE, fail_on_low_scrape=True)

        structured = OrchestratorResult(
            company_name="Acme Corp",
            website=None,
            mode=ResearchMode.STRUCTURED,
            section_results={},
            success=False,
        )

        async def fake_struct(*a):
            return structured

        with (
            _make_console_patch(),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator") as mock_get,
        ):
            result = await orch._run_complete_research("Acme Corp", None, cfg, None, None)

        assert result.success is False
        assert result.error == "Data collection failed scrape validation"
        # Should never reach deep research stage.
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_when_structured_fails_but_not_strict(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.COMPLETE, fail_on_low_scrape=False)

        structured = OrchestratorResult(
            company_name="Acme Corp",
            website=None,
            mode=ResearchMode.STRUCTURED,
            section_results={},
            success=False,
        )

        async def fake_struct(*a):
            return structured

        deep_result = Mock()
        deep_result.success = True
        deep_result.content = "raw"
        deep_result.api_calls = 1
        deep_result.citations = []
        deep_result.search_queries_count = 0

        mock_dr_orch = MagicMock()

        async def gen(**kwargs):
            # No stage1 context because structured failed.
            assert kwargs["stage1_context"] is None
            return deep_result

        mock_dr_orch.generate_comprehensive_report = gen

        formatted = Mock()
        formatted.markdown = "# Report"
        formatted.table_of_contents = "TOC"
        formatted.word_count = 100
        formatted.chapters = ["c"]

        with (
            _make_console_patch(),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_dr_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = formatted
            result = await orch._run_complete_research("Acme Corp", None, cfg, None, None)

        assert result.success is True
        assert result.section_results["strategic_overview"] == "# Report"

    @pytest.mark.asyncio
    async def test_deep_research_failure_returns_partial_with_quota_tip(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.COMPLETE)

        structured = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.STRUCTURED,
            section_results={"company_overview": "scraped"},
            success=True,
        )

        async def fake_struct(*a):
            return structured

        deep_result = Mock()
        deep_result.success = False
        deep_result.error = "429 quota exceeded"

        mock_dr_orch = MagicMock()

        async def gen(**kwargs):
            return deep_result

        mock_dr_orch.generate_comprehensive_report = gen

        console_mock = MagicMock()
        with (
            patch("primr.utils.console.console", new=console_mock),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_dr_orch),
        ):
            result = await orch._run_complete_research(
                "Acme Corp", "https://acme.example", cfg, None, None
            )

        assert result.success is False
        assert result.error == "429 quota exceeded"
        # Partial structured results preserved.
        assert result.section_results == {"company_overview": "scraped"}
        # Quota tip surfaced.
        assert console_mock.warn.called

    @pytest.mark.asyncio
    async def test_exception_during_deep_phase_preserves_partial(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.COMPLETE)

        structured = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.STRUCTURED,
            section_results={"company_overview": "scraped"},
            success=True,
        )

        async def fake_struct(*a):
            return structured

        mock_dr_orch = MagicMock()

        async def gen(**kwargs):
            raise RuntimeError("unexpected explosion")

        mock_dr_orch.generate_comprehensive_report = gen

        with (
            _make_console_patch(),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_dr_orch),
        ):
            result = await orch._run_complete_research(
                "Acme Corp", "https://acme.example", cfg, None, None
            )

        assert result.success is False
        assert result.error == "unexpected explosion"
        # Partial structured results preserved from the except branch.
        assert result.section_results == {"company_overview": "scraped"}


class TestSupplementalContext:
    """ResearchConfig.supplemental_context (fenced hiring signals from the
    premium/deep paths) must reach the Deep Research stage-1 context."""

    @staticmethod
    def _deep_result():
        deep_result = Mock()
        deep_result.success = True
        deep_result.content = "raw"
        deep_result.api_calls = 1
        deep_result.sections_written = 3
        deep_result.search_queries_count = 4
        deep_result.citations = []
        return deep_result

    @staticmethod
    def _formatted():
        formatted = Mock()
        formatted.markdown = "# Report"
        formatted.table_of_contents = "TOC"
        formatted.word_count = 100
        formatted.chapters = ["c"]
        formatted.citations = []
        return formatted

    @pytest.mark.asyncio
    async def test_deep_research_mode_passes_supplemental_as_stage1(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(
            mode=ResearchMode.DEEP_RESEARCH, supplemental_context="FENCED HIRING BLOCK"
        )
        captured: dict = {}

        mock_orch = MagicMock()

        async def gen(**kwargs):
            captured.update(kwargs)
            return self._deep_result()

        mock_orch.generate_comprehensive_report = gen

        with (
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = self._formatted()
            await orch._run_deep_research_with_context("Acme Corp", None, cfg, None, None)

        assert captured["stage1_context"] == "FENCED HIRING BLOCK"

    @pytest.mark.asyncio
    async def test_complete_mode_appends_supplemental_to_stage1(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.COMPLETE, supplemental_context="FENCED HIRING BLOCK")
        structured = OrchestratorResult(
            company_name="Acme Corp",
            website="https://acme.example",
            mode=ResearchMode.STRUCTURED,
            section_results={"company_overview": "scraped overview"},
            success=True,
        )

        async def fake_struct(*a):
            return structured

        captured: dict = {}
        mock_dr_orch = MagicMock()

        async def gen(**kwargs):
            captured.update(kwargs)
            return self._deep_result()

        mock_dr_orch.generate_comprehensive_report = gen

        with (
            _make_console_patch(),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_dr_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = self._formatted()
            await orch._run_complete_research("Acme Corp", "https://acme.example", cfg, None, None)

        stage1 = captured["stage1_context"]
        assert stage1 is not None
        assert stage1.endswith("FENCED HIRING BLOCK")
        # The structured phase's content precedes the supplemental block.
        assert "scraped overview" in stage1

    @pytest.mark.asyncio
    async def test_complete_mode_supplemental_survives_structured_failure(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(
            mode=ResearchMode.COMPLETE,
            fail_on_low_scrape=False,
            supplemental_context="FENCED HIRING BLOCK",
        )
        structured = OrchestratorResult(
            company_name="Acme Corp",
            website=None,
            mode=ResearchMode.STRUCTURED,
            section_results={},
            success=False,
        )

        async def fake_struct(*a):
            return structured

        captured: dict = {}
        mock_dr_orch = MagicMock()

        async def gen(**kwargs):
            captured.update(kwargs)
            return self._deep_result()

        mock_dr_orch.generate_comprehensive_report = gen

        with (
            _make_console_patch(),
            patch.object(orch, "_run_structured_research", side_effect=fake_struct),
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_dr_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = self._formatted()
            await orch._run_complete_research("Acme Corp", None, cfg, None, None)

        assert captured["stage1_context"] == "FENCED HIRING BLOCK"

    @pytest.mark.asyncio
    async def test_no_supplemental_keeps_deep_research_stage1_none(self):
        orch = ResearchOrchestrator()
        cfg = ResearchConfig(mode=ResearchMode.DEEP_RESEARCH)
        captured: dict = {}

        mock_orch = MagicMock()

        async def gen(**kwargs):
            captured.update(kwargs)
            return self._deep_result()

        mock_orch.generate_comprehensive_report = gen

        with (
            patch(f"{MODULE}.get_deep_research_orchestrator", return_value=mock_orch),
            patch(f"{MODULE}.ReportFormatter") as MockFmt,
        ):
            MockFmt.return_value.format_report.return_value = self._formatted()
            await orch._run_deep_research_with_context("Acme Corp", None, cfg, None, None)

        assert captured["stage1_context"] is None
