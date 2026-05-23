"""
Coverage-focused tests for primr.core.ai_strategy internal functions.

Targets the lower-coverage internals not covered by test_ai_strategy.py:
_process_citations, _save_strategy_outputs, _gather_context,
_execute_strategy_research, _poll_for_completion, and the
generate_ai_strategy success path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.core.ai_strategy import (
    Platform,
    _process_citations,
    _save_strategy_outputs,
    generate_ai_strategy,
)

# ---------------------------------------------------------------------------
# Platform extras (aliases / display)
# ---------------------------------------------------------------------------


def test_platform_aliases():
    assert Platform.from_string("microsoft") == Platform.AZURE
    assert Platform.from_string("amazon") == Platform.AWS
    assert Platform.from_string("google") == Platform.GCP
    assert Platform.from_string("nvidia") == Platform.PRIVATE


def test_platform_private_display():
    assert Platform.PRIVATE.display_name == "Private Cloud / NVIDIA"


# ---------------------------------------------------------------------------
# _process_citations
# ---------------------------------------------------------------------------


def test_process_citations_converts_inline_refs():
    import primr.ai.deep_research as dr_mod

    content = "Claim one [cite: 1, 2] and claim two [cite: 3]."
    with patch.object(dr_mod, "resolve_citation_urls_sync", side_effect=lambda c: c):
        out = _process_citations(content)
    assert "[1] [2]" in out
    assert "[3]" in out
    assert "[cite:" not in out


def test_process_citations_rewrites_sources_section():
    import primr.ai.deep_research as dr_mod

    content = (
        "Body text [cite: 1].\n\n"
        "**Sources:**\n"
        "1. [vertexaisearch redirect](https://vertexaisearch.example/redir)\n"
        "2. [Real Title](https://realsite.com/page)\n"
    )

    def fake_resolve(citations):
        # Simulate resolution leaving URLs intact
        return citations

    with patch.object(dr_mod, "resolve_citation_urls_sync", side_effect=fake_resolve):
        out = _process_citations(content)
    assert "**Sources:**" in out
    # vertexaisearch title should be replaced with domain
    assert "vertexaisearch.example" in out
    assert "Real Title" in out


def test_process_citations_no_sources_section():
    import primr.ai.deep_research as dr_mod

    content = "Plain text with no sources [cite: 1]."
    with patch.object(dr_mod, "resolve_citation_urls_sync", side_effect=lambda c: c):
        out = _process_citations(content)
    assert "[1]" in out


# ---------------------------------------------------------------------------
# _save_strategy_outputs
# ---------------------------------------------------------------------------


def test_save_strategy_outputs_success(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))
    with (
        patch(
            "primr.core.ai_strategy._process_citations",
            side_effect=lambda c: c,
        ),
        patch("primr.output.markdown_converter.markdown_to_docx") as mock_docx,
    ):
        outputs = _save_strategy_outputs("# Strategy body", "Acme", Platform.AZURE)

    assert outputs["md"] is not None
    assert outputs["txt"] is not None
    assert outputs["docx"] is not None
    assert mock_docx.called
    assert list(tmp_path.glob("*.md"))
    assert list(tmp_path.glob("*.txt"))


def test_save_strategy_outputs_agnostic_no_vendor_tag(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))
    with (
        patch("primr.core.ai_strategy._process_citations", side_effect=lambda c: c),
        patch("primr.output.markdown_converter.markdown_to_docx"),
    ):
        outputs = _save_strategy_outputs("# Body", "Acme", Platform.AGNOSTIC)
    md_name = Path(outputs["md"]).name
    assert "_AGNOSTIC_" not in md_name


def test_save_strategy_outputs_docx_permission_retry(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))
    calls = {"n": 0}

    def docx_side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("locked")
        return None

    with (
        patch("primr.core.ai_strategy._process_citations", side_effect=lambda c: c),
        patch(
            "primr.output.markdown_converter.markdown_to_docx",
            side_effect=docx_side_effect,
        ),
    ):
        outputs = _save_strategy_outputs("# Body", "Acme", Platform.AWS)
    assert calls["n"] == 2
    assert outputs["docx"] is not None


# ---------------------------------------------------------------------------
# generate_ai_strategy success path (full orchestration mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_ai_strategy_success(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))

    with (
        patch("primr.core.ai_strategy._validate_preflight", return_value=[]),
        patch(
            "primr.core.ai_strategy._gather_context",
            new=AsyncMock(return_value=([], ["/v/azure.txt"])),
        ),
        patch(
            "primr.core.ai_strategy.build_ai_strategy_prompt",
            return_value="PROMPT",
        ),
        patch(
            "primr.core.ai_strategy._execute_strategy_research",
            new=AsyncMock(return_value="# Strategy content"),
        ),
        patch(
            "primr.core.ai_strategy._save_strategy_outputs",
            return_value={
                "docx": str(tmp_path / "s.docx"),
                "md": str(tmp_path / "s.md"),
                "txt": str(tmp_path / "s.txt"),
            },
        ),
    ):
        result = await generate_ai_strategy(company_name="Acme", platform="azure")

    assert result.success is True
    assert result.content == "# Strategy content"
    assert result.vendor_research_paths == ["/v/azure.txt"]


@pytest.mark.asyncio
async def test_generate_ai_strategy_research_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("primr.core.ai_strategy.OUTPUT_DIR", str(tmp_path))
    with (
        patch("primr.core.ai_strategy._validate_preflight", return_value=[]),
        patch(
            "primr.core.ai_strategy._gather_context",
            new=AsyncMock(return_value=([], [])),
        ),
        patch("primr.core.ai_strategy.build_ai_strategy_prompt", return_value="P"),
        patch(
            "primr.core.ai_strategy._execute_strategy_research",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await generate_ai_strategy(company_name="Acme", platform="aws")
    assert result.success is False
    assert "research failed" in result.error.lower()


@pytest.mark.asyncio
async def test_generate_ai_strategy_preflight_fail():
    with patch(
        "primr.core.ai_strategy._validate_preflight",
        return_value=["GEMINI_API_KEY not configured"],
    ):
        result = await generate_ai_strategy(company_name="Acme", platform="azure")
    assert result.success is False
    assert "GEMINI_API_KEY" in result.error


# ---------------------------------------------------------------------------
# _execute_strategy_research
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_strategy_research_completed():
    from primr.core import ai_strategy as mod

    class _Status:
        COMPLETED = "completed"

    fake_result = MagicMock()
    fake_result.status = _Status.COMPLETED
    fake_result.content = "RESULT"

    client = MagicMock()
    client.research = AsyncMock(return_value=fake_result)

    fake_dr = MagicMock()
    fake_dr.get_deep_research_client.return_value = client
    fake_dr.ResearchStatus = _Status

    with patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}):
        out = await mod._execute_strategy_research(
            prompt="P", context_files=[], timeout=10
        )
    assert out == "RESULT"


@pytest.mark.asyncio
async def test_execute_strategy_research_exception_returns_none():
    from primr.core import ai_strategy as mod

    class _Status:
        COMPLETED = "completed"

    client = MagicMock()
    client.research = AsyncMock(side_effect=RuntimeError("boom"))

    fake_dr = MagicMock()
    fake_dr.get_deep_research_client.return_value = client
    fake_dr.ResearchStatus = _Status

    with patch.dict("sys.modules", {"primr.ai.deep_research": fake_dr}):
        out = await mod._execute_strategy_research(
            prompt="P", context_files=["/x.txt"], timeout=10
        )
    assert out is None


# ---------------------------------------------------------------------------
# _gather_context (no yaml context files -> vendor research path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gather_context_with_company_research(tmp_path):
    from primr.core.ai_strategy import AIStrategyConfig, _gather_context

    research = tmp_path / "research.md"
    research.write_text("body", encoding="utf-8")

    registry = MagicMock()
    registry.get_context_files.return_value = []

    fake_registry_mod = MagicMock()
    fake_registry_mod.get_registry.return_value = registry

    config = AIStrategyConfig(
        company_name="Acme",
        platform=Platform.AGNOSTIC,
        company_research_path=str(research),
    )

    with patch.dict("sys.modules", {"primr.prompts.registry": fake_registry_mod}):
        context_files, vendor_paths = await _gather_context(config)

    assert str(research) in context_files


@pytest.mark.asyncio
async def test_gather_context_uses_yaml_files(tmp_path):
    from primr.core.ai_strategy import AIStrategyConfig, _gather_context

    yaml_file = tmp_path / "vendor.txt"
    yaml_file.write_text("vendor", encoding="utf-8")

    registry = MagicMock()
    registry.get_context_files.return_value = [yaml_file]

    fake_registry_mod = MagicMock()
    fake_registry_mod.get_registry.return_value = registry

    config = AIStrategyConfig(company_name="Acme", platform=Platform.AZURE)

    with patch.dict("sys.modules", {"primr.prompts.registry": fake_registry_mod}):
        context_files, vendor_paths = await _gather_context(config)

    assert str(yaml_file) in context_files
    assert str(yaml_file) in vendor_paths
