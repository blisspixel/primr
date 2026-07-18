"""
Coverage-focused tests for primr.core.deep_research_runner internals.

Targets the output-conversion helper, result processing, research
execution wrapper, AI-strategy delegation, and the success path of
perform_deep_research (all I/O mocked).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.core.deep_research_runner import (
    DeepResearchConfig,
    DeepResearchMode,
    _convert_deep_research_to_docx,
    _process_results,
    perform_deep_research,
)

# ---------------------------------------------------------------------------
# _convert_deep_research_to_docx
# ---------------------------------------------------------------------------


def test_convert_to_docx_success(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.deep_research_runner.OUTPUT_DIR", str(tmp_path))
    with patch("primr.output.markdown_converter.markdown_to_docx") as mock_docx:
        out = _convert_deep_research_to_docx("# Report body", "Acme", "https://a.com")
    assert out is not None
    assert out.endswith(".docx")
    assert mock_docx.called
    assert list(tmp_path.glob("*.md"))
    assert list(tmp_path.glob("*.txt"))


def test_convert_to_docx_normalizes_saved_markdown_punctuation(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.deep_research_runner.OUTPUT_DIR", str(tmp_path))
    with patch("primr.output.markdown_converter.markdown_to_docx"):
        out = _convert_deep_research_to_docx(
            "## Executive Summary\n\nThe company\u2014a leader\u2013is expanding.",
            "Acme",
            "https://a.com",
        )
    assert out is not None
    md_files = list(tmp_path.glob("*.md"))
    assert md_files
    markdown = md_files[0].read_text(encoding="utf-8")
    assert "\u2014" not in markdown
    assert "\u2013" not in markdown
    assert "The company, a leader, is expanding." in markdown


def test_convert_to_docx_no_website(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.deep_research_runner.OUTPUT_DIR", str(tmp_path))
    with patch("primr.output.markdown_converter.markdown_to_docx"):
        out = _convert_deep_research_to_docx("# Body", "Acme", None)
    assert out is not None


def test_convert_to_docx_uses_portable_artifact_name(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.deep_research_runner.OUTPUT_DIR", str(tmp_path))
    with patch("primr.output.markdown_converter.markdown_to_docx"):
        out = _convert_deep_research_to_docx("# Body", "Acme, Inc.", None)

    assert out is not None
    assert "Acme, Inc_Strategic_Overview" in out
    assert "Acme, Inc._Strategic_Overview" not in out


def test_convert_to_docx_permission_retry(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.deep_research_runner.OUTPUT_DIR", str(tmp_path))
    calls = {"n": 0}

    def side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("locked")
        return None

    with patch(
        "primr.output.markdown_converter.markdown_to_docx",
        side_effect=side_effect,
    ):
        out = _convert_deep_research_to_docx("# Body", "Acme", "https://a.com")
    assert calls["n"] == 2
    assert out is not None


def test_convert_to_docx_generic_error_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.deep_research_runner.OUTPUT_DIR", str(tmp_path))
    # Make the markdown write fail to hit the outer except clause.
    with patch(
        "primr.core.deep_research_runner.Path.write_text",
        side_effect=RuntimeError("disk full"),
    ):
        out = _convert_deep_research_to_docx("# Body", "Acme", "https://a.com")
    assert out is None


# ---------------------------------------------------------------------------
# _process_results
# ---------------------------------------------------------------------------


def test_process_results_writes_outputs(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme", website="https://a.com", mode=DeepResearchMode.DEEP_RESEARCH
    )
    research_result = MagicMock()
    research_result.section_results = {"intro": "Intro text"}
    research_result.raw_content = "# Raw markdown"

    with (
        patch(
            "primr.core.deep_research_runner.create_working_folder",
            return_value=str(tmp_path),
        ),
        patch("primr.core.deep_research_runner.save_section_output") as mock_save,
        patch(
            "primr.core.deep_research_runner._convert_deep_research_to_docx",
            return_value=str(tmp_path / "out.docx"),
        ),
    ):
        outputs = _process_results(config, research_result)

    assert mock_save.called
    assert outputs["raw_md_path"].endswith("deep_research_output.md")
    assert outputs["docx_path"].endswith("out.docx")


def test_process_results_no_raw_content(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme", website=None, mode=DeepResearchMode.DEEP_RESEARCH
    )
    research_result = MagicMock()
    research_result.section_results = {}
    research_result.raw_content = ""

    with (
        patch(
            "primr.core.deep_research_runner.create_working_folder",
            return_value=str(tmp_path),
        ),
        patch("primr.core.deep_research_runner.save_section_output"),
    ):
        outputs = _process_results(config, research_result)

    assert "raw_md_path" not in outputs
    assert "docx_path" not in outputs


def test_process_results_acknowledges_only_canonical_outputs(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme", website=None, mode=DeepResearchMode.DEEP_RESEARCH
    )
    research_result = MagicMock(
        section_results={},
        raw_content="# Report",
        pending_interaction_id="interaction-123",
    )

    def convert(_content, _company, _website, written_paths):
        paths = [tmp_path / "report.md", tmp_path / "report.txt", tmp_path / "report.docx"]
        for path in paths:
            path.write_text("content", encoding="utf-8")
        written_paths.extend(paths)
        return str(paths[-1])

    with (
        patch("primr.core.deep_research_runner.create_working_folder", return_value=str(tmp_path)),
        patch("primr.core.deep_research_runner.save_section_output"),
        patch(
            "primr.core.deep_research_runner._convert_deep_research_to_docx", side_effect=convert
        ),
        patch(
            "primr.ai.job_persistence.acknowledge_pending_job_after_outputs",
            return_value=True,
        ) as acknowledge_mock,
    ):
        _process_results(config, research_result)

    paths = [tmp_path / "report.md", tmp_path / "report.txt", tmp_path / "report.docx"]
    acknowledge_mock.assert_called_once_with("interaction-123", paths)


def test_process_results_retains_job_when_conversion_fails(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme", website=None, mode=DeepResearchMode.DEEP_RESEARCH
    )
    research_result = MagicMock(
        section_results={},
        raw_content="# Report",
        pending_interaction_id="interaction-123",
    )
    with (
        patch("primr.core.deep_research_runner.create_working_folder", return_value=str(tmp_path)),
        patch("primr.core.deep_research_runner.save_section_output"),
        patch("primr.core.deep_research_runner._convert_deep_research_to_docx", return_value=None),
        patch("primr.ai.job_persistence.acknowledge_pending_job_after_outputs") as acknowledge_mock,
    ):
        outputs = _process_results(config, research_result)

    assert outputs["docx_path"] is None
    acknowledge_mock.assert_not_called()


# ---------------------------------------------------------------------------
# _execute_research
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_research_success():
    from primr.core import deep_research_runner as mod

    config = DeepResearchConfig(
        company_name="Acme", website="https://a.com", mode=DeepResearchMode.DEEP_RESEARCH
    )

    research_obj = MagicMock()
    research_obj.success = True
    research_obj.section_results = {"a": "b"}

    orchestrator = MagicMock()
    orchestrator.research = AsyncMock(return_value=research_obj)

    fake_mod = MagicMock()
    fake_mod.get_orchestrator.return_value = orchestrator

    class _RM:
        DEEP_RESEARCH = "dr"
        COMPLETE = "c"
        HYBRID = "h"

    fake_mod.ResearchMode = _RM

    with patch.dict("sys.modules", {"primr.core.research_orchestrator": fake_mod}):
        result = await mod._execute_research(config)
    assert result is research_obj


@pytest.mark.asyncio
async def test_execute_research_failure_returns_none():
    from primr.core import deep_research_runner as mod

    config = DeepResearchConfig(company_name="Acme", website=None, mode=DeepResearchMode.COMPLETE)

    research_obj = MagicMock()
    research_obj.success = False
    research_obj.error = "nope"

    orchestrator = MagicMock()
    orchestrator.research = AsyncMock(return_value=research_obj)

    fake_mod = MagicMock()
    fake_mod.get_orchestrator.return_value = orchestrator

    class _RM:
        DEEP_RESEARCH = "dr"
        COMPLETE = "c"
        HYBRID = "h"

    fake_mod.ResearchMode = _RM

    with patch.dict("sys.modules", {"primr.core.research_orchestrator": fake_mod}):
        result = await mod._execute_research(config)
    assert result is None


@pytest.mark.asyncio
async def test_execute_research_exception_returns_none():
    from primr.core import deep_research_runner as mod

    config = DeepResearchConfig(company_name="Acme", website=None, mode=DeepResearchMode.HYBRID)

    orchestrator = MagicMock()
    orchestrator.research = AsyncMock(side_effect=RuntimeError("boom"))

    fake_mod = MagicMock()
    fake_mod.get_orchestrator.return_value = orchestrator

    class _RM:
        DEEP_RESEARCH = "dr"
        COMPLETE = "c"
        HYBRID = "h"

    fake_mod.ResearchMode = _RM

    with patch.dict("sys.modules", {"primr.core.research_orchestrator": fake_mod}):
        result = await mod._execute_research(config)
    assert result is None


# ---------------------------------------------------------------------------
# _generate_ai_strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_ai_strategy_success():
    from primr.core import deep_research_runner as mod

    config = DeepResearchConfig(
        company_name="Acme",
        website=None,
        mode=DeepResearchMode.DEEP_RESEARCH,
        platform="azure",
        context_files=("/context/operator-notes.md", "/context/recon.txt"),
    )

    strategy_result = MagicMock()
    strategy_result.success = True
    strategy_result.docx_path = "/out/strategy.docx"

    with patch(
        "primr.core.ai_strategy.generate_ai_strategy",
        new=AsyncMock(return_value=strategy_result),
    ) as generate:
        out = await mod._generate_ai_strategy(config, "/research.md")
    assert out == "/out/strategy.docx"
    assert generate.await_args.kwargs["company_research_path"] == "/research.md"
    assert generate.await_args.kwargs["additional_context_paths"] == config.context_files


@pytest.mark.asyncio
async def test_generate_ai_strategy_failure_returns_none():
    from primr.core import deep_research_runner as mod

    config = DeepResearchConfig(
        company_name="Acme", website=None, mode=DeepResearchMode.DEEP_RESEARCH
    )

    strategy_result = MagicMock()
    strategy_result.success = False

    with patch(
        "primr.core.ai_strategy.generate_ai_strategy",
        new=AsyncMock(return_value=strategy_result),
    ):
        out = await mod._generate_ai_strategy(config, None)
    assert out is None


# ---------------------------------------------------------------------------
# perform_deep_research success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perform_deep_research_success(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme", website="https://a.com", mode=DeepResearchMode.DEEP_RESEARCH
    )

    preflight = MagicMock()
    preflight.is_valid = True

    research_obj = MagicMock()
    research_obj.raw_content = "# Raw"
    research_obj.section_results = {"a": "b"}
    research_obj.citations = ["c1"]

    with (
        patch("primr.core.deep_research_runner.WORKING_DIR", str(tmp_path / "working")),
        patch("primr.core.deep_research_runner.validate_preflight", return_value=preflight),
        patch(
            "primr.core.deep_research_runner._execute_research",
            new=AsyncMock(return_value=research_obj),
        ),
        patch(
            "primr.core.deep_research_runner._process_results",
            return_value={
                "raw_md_path": str(tmp_path / "r.md"),
                "docx_path": str(tmp_path / "r.docx"),
            },
        ),
    ):
        result = await perform_deep_research(config)

    assert result.success is True
    assert result.section_count == 1
    assert result.citation_count == 1


@pytest.mark.asyncio
async def test_perform_deep_research_execution_failure(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme", website=None, mode=DeepResearchMode.DEEP_RESEARCH
    )

    preflight = MagicMock()
    preflight.is_valid = True

    with (
        patch("primr.core.deep_research_runner.WORKING_DIR", str(tmp_path / "working")),
        patch("primr.core.deep_research_runner.validate_preflight", return_value=preflight),
        patch(
            "primr.core.deep_research_runner._execute_research",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await perform_deep_research(config)

    assert result.success is False
    assert "execution failed" in result.error.lower()


@pytest.mark.asyncio
async def test_perform_deep_research_with_ai_strategy(tmp_path):
    config = DeepResearchConfig(
        company_name="Acme",
        website=None,
        mode=DeepResearchMode.DEEP_RESEARCH,
        ai_strategy=True,
        platform="azure",
    )

    preflight = MagicMock()
    preflight.is_valid = True

    research_obj = MagicMock()
    research_obj.raw_content = "# Raw"
    research_obj.section_results = {}
    research_obj.citations = []

    with (
        patch("primr.core.deep_research_runner.WORKING_DIR", str(tmp_path / "working")),
        patch("primr.core.deep_research_runner.validate_preflight", return_value=preflight),
        patch(
            "primr.core.deep_research_runner._execute_research",
            new=AsyncMock(return_value=research_obj),
        ),
        patch(
            "primr.core.deep_research_runner._process_results",
            return_value={"docx_path": str(tmp_path / "r.docx"), "raw_md_path": None},
        ),
        patch(
            "primr.core.deep_research_runner._generate_ai_strategy",
            new=AsyncMock(return_value="/out/strategy.docx"),
        ) as mock_strategy,
    ):
        result = await perform_deep_research(config)

    assert mock_strategy.called
    assert result.ai_strategy_path == "/out/strategy.docx"
