"""Coverage tests for primr.ai.research_executor.

Exercises _execute_chapter_internal across its success / failed / timeout /
quota-retry / non-quota-error branches, plus _start_research tool wiring and
the content/citation extraction helpers. All genai calls are mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.report_architect import ChapterPlan
from primr.ai.research_executor import ResearchNodeExecutor


@pytest.fixture
def executor():
    with patch("primr.ai.research_executor.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "test-key"
        return ResearchNodeExecutor(file_search_store="store-1", max_concurrent=2)


@pytest.fixture
def chapter():
    return ChapterPlan(1, "Market Position", "Analyze the market.")


# ---------------------------------------------------------------------------
# _start_research tool wiring
# ---------------------------------------------------------------------------


def test_start_research_includes_file_search_tool(executor):
    executor._client = MagicMock()
    executor._client.interactions.create.return_value = SimpleNamespace(id="x")
    executor._start_research("prompt")
    kwargs = executor._client.interactions.create.call_args.kwargs
    assert kwargs["agent"] == executor.AGENT_ID
    assert kwargs["background"] is True
    assert kwargs["store"] is True
    assert kwargs["tools"][0]["type"] == "file_search"
    assert kwargs["tools"][0]["file_search_store_names"] == ["store-1"]


def test_start_research_no_tools_without_store():
    with patch("primr.ai.research_executor.get_settings") as mock_settings:
        mock_settings.return_value.api.gemini_key = "test-key"
        ex = ResearchNodeExecutor(max_concurrent=1)
    ex._client = MagicMock()
    ex._client.interactions.create.return_value = SimpleNamespace(id="y")
    ex._start_research("prompt")
    kwargs = ex._client.interactions.create.call_args.kwargs
    assert "tools" not in kwargs


# ---------------------------------------------------------------------------
# _extract_content / _extract_citations
# ---------------------------------------------------------------------------


def test_extract_content_joins_outputs(executor):
    interaction = SimpleNamespace(
        outputs=[
            SimpleNamespace(text="first"),
            SimpleNamespace(text=None),
            SimpleNamespace(text="second"),
        ]
    )
    assert executor._extract_content(interaction) == "first\n\nsecond"


def test_extract_content_empty_when_no_outputs(executor):
    assert executor._extract_content(SimpleNamespace(outputs=[])) == ""
    assert executor._extract_content(SimpleNamespace()) == ""


def test_extract_citations_from_sources_section(executor):
    content = (
        "Body text.\n\n**Sources:**\n"
        "1. [Acme Report](https://acme.example/r)\n"
        "2. [News](https://news.example/x)\n"
    )
    interaction = SimpleNamespace(outputs=[SimpleNamespace(text=content)])
    citations = executor._extract_citations(interaction)
    assert len(citations) == 2
    assert citations[0]["title"] == "Acme Report"
    assert citations[0]["url"] == "https://acme.example/r"


def test_extract_citations_inline_fallback(executor):
    content = "Claim [cite: 1, 2] and another [cite: 3]."
    interaction = SimpleNamespace(outputs=[SimpleNamespace(text=content)])
    citations = executor._extract_citations(interaction)
    nums = sorted(c["number"] for c in citations)
    assert nums == ["1", "2", "3"]
    assert all(c["url"] == "" for c in citations)


def test_extract_citations_empty_content(executor):
    interaction = SimpleNamespace(outputs=[])
    assert executor._extract_citations(interaction) == []


# ---------------------------------------------------------------------------
# _execute_chapter_internal — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_chapter_success(executor, chapter):
    started = SimpleNamespace(id="int-1")
    completed = SimpleNamespace(
        status="completed",
        outputs=[SimpleNamespace(text="A great chapter with words.")],
    )
    executor._start_research = MagicMock(return_value=started)
    executor._get_interaction = MagicMock(return_value=completed)

    progress = []
    result = await executor._execute_chapter_internal(chapter, "Acme", on_progress=progress.append)
    assert result.success is True
    assert result.content == "A great chapter with words."
    assert result.interaction_id == "int-1"
    assert any("Completed" in m for m in progress)


@pytest.mark.asyncio
async def test_execute_chapter_failed_status(executor, chapter):
    executor._start_research = MagicMock(return_value=SimpleNamespace(id="int-2"))
    executor._get_interaction = MagicMock(
        return_value=SimpleNamespace(status="failed", error="model crashed")
    )
    result = await executor._execute_chapter_internal(chapter, "Acme")
    assert result.success is False
    assert result.error == "model crashed"
    assert result.interaction_id == "int-2"


@pytest.mark.asyncio
async def test_execute_chapter_timeout(executor, chapter):
    executor._start_research = MagicMock(return_value=SimpleNamespace(id="int-3"))
    executor._get_interaction = MagicMock(return_value=SimpleNamespace(status="in_progress"))
    # Force the elapsed-time check to exceed the timeout immediately.
    times = iter([0.0] + [executor.CHAPTER_TIMEOUT + 1] * 20)
    with patch("primr.ai.research_executor.time.time", lambda: next(times)):
        result = await executor._execute_chapter_internal(chapter, "Acme")
    assert result.success is False
    assert "Timed out" in result.error


@pytest.mark.asyncio
async def test_execute_chapter_quota_retry_then_success(executor, chapter):
    started = SimpleNamespace(id="int-4")
    completed = SimpleNamespace(
        status="completed", outputs=[SimpleNamespace(text="recovered content")]
    )
    # First attempt raises quota error, second attempt succeeds.
    calls = {"n": 0}

    def _start(prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429 quota exceeded")
        return started

    executor._start_research = _start
    executor._get_interaction = MagicMock(return_value=completed)

    sleeps = []

    async def _fake_sleep(d):
        sleeps.append(d)

    progress = []
    with patch("primr.ai.research_executor.asyncio.sleep", _fake_sleep):
        result = await executor._execute_chapter_internal(
            chapter, "Acme", on_progress=progress.append
        )
    assert result.success is True
    assert calls["n"] == 2
    assert any("Rate limited" in m for m in progress)
    assert sleeps  # at least one backoff sleep occurred


@pytest.mark.asyncio
async def test_execute_chapter_non_quota_error_no_retry(executor, chapter):
    def _start(prompt):
        raise RuntimeError("invalid agent configuration")

    executor._start_research = _start
    result = await executor._execute_chapter_internal(chapter, "Acme")
    assert result.success is False
    assert "invalid agent configuration" in result.error


# ---------------------------------------------------------------------------
# _require_genai_dependency
# ---------------------------------------------------------------------------


def test_require_genai_dependency_no_error():
    import primr.ai.research_executor as re_mod

    # When import error is None, the call is a no-op.
    with patch.object(re_mod, "_GENAI_IMPORT_ERROR", None):
        re_mod._require_genai_dependency()  # should not raise
