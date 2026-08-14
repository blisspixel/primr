"""Supplemental unit tests for DeepResearchOrchestrator helpers.

These cover the small mockable methods not exercised by the existing
test_deep_research_orchestrator.py: _calculate_backoff_delay,
_get_phase_name, _get_poll_interval, _extract_* delegators,
_load_accordion_prompts (+ default fallback), and
_build_research_dossier_prompt.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from primr.ai.deep_research import DeepResearchOrchestrator, ResearchResult, ResearchStatus


@pytest.fixture
def orchestrator(monkeypatch):
    """A DeepResearchOrchestrator with genai.Client mocked out."""
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    # Reset class-level caches so each test sees fresh load behavior.
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", None)
    monkeypatch.setattr(DeepResearchOrchestrator, "_accordion_prompts_cache", None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


class TestCalculateBackoffDelay:
    def test_attempt_zero_is_base_delay(self, orchestrator):
        delay = orchestrator._calculate_backoff_delay(0)
        assert delay == orchestrator.BASE_RETRY_DELAY

    def test_doubles_per_attempt(self, orchestrator):
        assert orchestrator._calculate_backoff_delay(1) == orchestrator.BASE_RETRY_DELAY * 2
        assert orchestrator._calculate_backoff_delay(2) == orchestrator.BASE_RETRY_DELAY * 4
        assert orchestrator._calculate_backoff_delay(3) == orchestrator.BASE_RETRY_DELAY * 8


class TestPhaseAndPollInterval:
    def test_phase_name_returns_string(self, orchestrator):
        name = orchestrator._get_phase_name(30)
        assert isinstance(name, str)

    def test_poll_interval_5s_early(self, orchestrator):
        assert orchestrator._get_poll_interval(10) == 5.0
        assert orchestrator._get_poll_interval(59) == 5.0

    def test_poll_interval_10s_at_middle(self, orchestrator):
        assert orchestrator._get_poll_interval(120) == 10.0

    def test_poll_interval_20s_after_middle(self, orchestrator):
        assert orchestrator._get_poll_interval(250) == 20.0

    def test_poll_interval_30s_after_long_run(self, orchestrator):
        assert orchestrator._get_poll_interval(400) == 30.0


class TestExtractDelegators:
    def test_extract_content_returns_string(self, orchestrator):
        with patch(
            "primr.ai.deep_research.extract_interaction_content",
            return_value="content body",
        ):
            assert orchestrator._extract_content(MagicMock()) == "content body"

    def test_extract_citations_returns_list(self, orchestrator):
        with patch(
            "primr.ai.deep_research.extract_interaction_citations",
            return_value=[{"url": "https://x"}],
        ):
            assert orchestrator._extract_citations(MagicMock()) == [{"url": "https://x"}]

    def test_extract_search_queries_count_returns_int(self, orchestrator):
        with patch(
            "primr.ai.deep_research.extract_search_queries_count",
            return_value=7,
        ):
            assert orchestrator._extract_search_queries_count(MagicMock()) == 7


class TestLoadAccordionPrompts:
    def test_default_prompts_contain_expected_keys(self):
        defaults = DeepResearchOrchestrator._get_default_accordion_prompts()
        assert "research_dossier_prompt" in defaults
        assert "section_writing_prompt" in defaults
        assert "position_guidance" in defaults

    def test_falls_back_to_defaults_on_load_error(self, monkeypatch):
        monkeypatch.setattr(DeepResearchOrchestrator, "_accordion_prompts_cache", None)
        with patch(
            "primr.prompts.composer.PromptComposer",
            side_effect=RuntimeError("yaml broken"),
        ):
            result = DeepResearchOrchestrator._load_accordion_prompts()
        assert "research_dossier_prompt" in result

    def test_load_caches_result(self, monkeypatch):
        monkeypatch.setattr(DeepResearchOrchestrator, "_accordion_prompts_cache", None)

        composer = MagicMock()
        config = MagicMock()
        config.raw_config = {
            "accordion_method": {
                "research_dossier_prompt": "DOSSIER {company_name}",
                "section_writing_prompt": "SECTION {section_title}",
                "position_guidance": {"opening": "open"},
            }
        }
        composer._load_config.return_value = config
        with patch("primr.prompts.composer.PromptComposer", return_value=composer):
            result = DeepResearchOrchestrator._load_accordion_prompts()
        assert result["research_dossier_prompt"] == "DOSSIER {company_name}"

        # Second call should hit the cache, not the composer.
        with patch("primr.prompts.composer.PromptComposer") as composer_mock:
            DeepResearchOrchestrator._load_accordion_prompts()
            composer_mock.assert_not_called()


class TestBuildResearchDossierPrompt:
    def test_includes_company_name(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Compile dossier for {company_name}{website_context}.",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme Corp", None)
        assert "Acme Corp" in result

    def test_includes_website_when_provided(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Compile dossier for {company_name}{website_context}.",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme", "https://acme.example")
        assert "https://acme.example" in result

    def test_omits_website_when_missing(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Compile dossier for {company_name}{website_context}.",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme", None)
        assert "website" not in result

    def test_uses_default_when_yaml_template_empty(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme", None)
        # Falls back to default which references "Lead Researcher".
        assert "Lead Researcher" in result

    def test_target_pages_reaches_dossier_prompt(self, orchestrator):
        with patch.object(
            DeepResearchOrchestrator,
            "_load_accordion_prompts",
            return_value={
                "research_dossier_prompt": "Build for {target_pages} pages: {company_name}",
                "section_writing_prompt": "",
                "position_guidance": {},
            },
        ):
            result = orchestrator._build_research_dossier_prompt("Acme", None, target_pages=42)

        assert "42 pages" in result


@pytest.mark.asyncio
async def test_comprehensive_report_uploads_files_and_applies_length_target(
    orchestrator, monkeypatch
):
    sections = [
        {
            "id": "one",
            "title": "One",
            "instructions": "Analyze one.",
            "part": 1,
            "position": "opening",
        },
        {
            "id": "two",
            "title": "Two",
            "instructions": "Analyze two.",
            "part": 1,
            "position": "closing",
        },
    ]
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", sections)
    orchestrator._store_manager = MagicMock()
    orchestrator._store_manager.create_store.return_value = "stores/context"
    orchestrator.SECTION_WRITE_DELAY = 0

    dossier = ResearchResult(content="grounded dossier", interaction_id="job-1")
    section = ResearchResult(content=" ".join(["analysis"] * 600))
    orchestrator._execute_with_retry = AsyncMock(return_value=dossier)
    orchestrator._execute_direct_generation = AsyncMock(return_value=section)

    result = await orchestrator.generate_comprehensive_report(
        company_name="Acme",
        stage1_context="website evidence",
        context_files=["brief.pdf", "notes.md"],
        target_pages=2,
    )

    assert result.success is True
    assert result.target_pages == 2
    assert result.target_attained is True
    orchestrator._store_manager.upload_context.assert_called_once()
    assert [call.args for call in orchestrator._store_manager.upload_file.call_args_list] == [
        ("stores/context", "brief.pdf"),
        ("stores/context", "notes.md"),
    ]
    prompts = [
        call.kwargs["prompt"] for call in orchestrator._execute_direct_generation.call_args_list
    ]
    assert all("at least 500 words" in prompt for prompt in prompts)
    orchestrator._store_manager.delete_store.assert_called_once_with("stores/context")


def _accordion_sections(count: int) -> list[dict[str, object]]:
    return [
        {
            "id": f"section_{index}",
            "title": f"Section {index}",
            "instructions": f"Analyze section {index}.",
            "part": 1,
            "position": "middle",
        }
        for index in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_comprehensive_report_adapts_pacing_after_rate_limit(orchestrator, monkeypatch):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(2))
    orchestrator.SECTION_WRITE_DELAY = 10
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(content="grounded dossier", interaction_id="job-1")
    )
    substantive = ResearchResult(content=" ".join(["analysis"] * 300))
    orchestrator._execute_direct_generation = AsyncMock(
        side_effect=[
            ResearchResult(content="", error="429 quota exceeded"),
            substantive,
            substantive,
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr("primr.ai.deep_research.asyncio.sleep", sleep)
    progress: list[str] = []

    result = await orchestrator.generate_comprehensive_report(
        company_name="Acme",
        target_pages=1,
        on_progress=progress.append,
    )

    assert result.success is True
    assert result.sections_written == 2
    assert [call.args[0] for call in sleep.await_args_list] == [30, 23]
    assert "  Rate limited. Delay now 25s" in progress


@pytest.mark.asyncio
async def test_comprehensive_report_stops_after_three_consecutive_section_failures(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(4))
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(content="grounded dossier", interaction_id="job-1")
    )
    orchestrator._execute_direct_generation = AsyncMock(
        return_value=ResearchResult(content="", error="provider unavailable")
    )
    monkeypatch.setattr("primr.ai.deep_research.asyncio.sleep", AsyncMock())
    progress: list[str] = []

    result = await orchestrator.generate_comprehensive_report(
        company_name="Acme",
        target_pages=1,
        on_progress=progress.append,
    )

    assert result.success is False
    assert result.sections_written == 0
    assert orchestrator._execute_direct_generation.await_count == 9
    assert "Stopping: 3 consecutive failures" in progress


@pytest.mark.asyncio
async def test_comprehensive_report_surfaces_usable_result_below_page_target(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(3))
    orchestrator.SECTION_WRITE_DELAY = 0
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(content="grounded dossier", interaction_id="job-1")
    )
    # Each response clears the half-share retry floor, but the assembled report
    # remains far below the advertised 30-page contract.
    orchestrator._execute_direct_generation = AsyncMock(
        return_value=ResearchResult(content=" ".join(["analysis"] * 2_500))
    )

    result = await orchestrator.generate_comprehensive_report(company_name="Acme", target_pages=30)

    assert result.sections_written == 3
    assert result.actual_pages < result.target_pages
    assert result.target_attained is False
    assert result.success is True
    assert result.error is None


@pytest.mark.asyncio
async def test_comprehensive_report_preserves_short_evidence_limited_sections(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(3))
    orchestrator.SECTION_WRITE_DELAY = 0
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(content="grounded dossier", interaction_id="job-1")
    )
    orchestrator._execute_direct_generation = AsyncMock(
        return_value=ResearchResult(content=" ".join(["evidence"] * 100))
    )
    monkeypatch.setattr("primr.ai.deep_research.asyncio.sleep", AsyncMock())

    result = await orchestrator.generate_comprehensive_report(company_name="Acme", target_pages=30)

    assert result.success is True
    assert result.sections_written == 3
    assert result.target_attained is False
    assert "Section 1" in result.content
    assert orchestrator._execute_direct_generation.await_count == 9


@pytest.mark.asyncio
async def test_comprehensive_report_returns_partial_and_cleans_store_on_exception(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(3))
    orchestrator._store_manager = MagicMock()
    orchestrator._store_manager.create_store.return_value = "stores/context"
    orchestrator.SECTION_WRITE_DELAY = 0
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(content="grounded dossier", interaction_id="job-1")
    )
    orchestrator._execute_direct_generation = AsyncMock(
        return_value=ResearchResult(content=" ".join(["analysis"] * 200))
    )
    build_prompt = MagicMock(side_effect=["first prompt", RuntimeError("prompt failure")])
    monkeypatch.setattr(orchestrator, "_build_section_prompt", build_prompt)
    monkeypatch.setattr("primr.ai.deep_research.asyncio.sleep", AsyncMock())

    result = await orchestrator.generate_comprehensive_report(
        company_name="Acme",
        stage1_context="website evidence",
        target_pages=1,
    )

    assert result.success is False
    assert result.sections_written == 1
    assert "Section 1" in result.content
    assert result.error == "prompt failure"
    orchestrator._store_manager.delete_store.assert_called_once_with("stores/context")


@pytest.mark.asyncio
async def test_comprehensive_report_rejects_empty_section_structure(orchestrator, monkeypatch):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", [])
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(content="grounded dossier", interaction_id="job-1")
    )

    result = await orchestrator.generate_comprehensive_report(company_name="Acme", target_pages=1)

    assert result.success is False
    assert result.sections_written == 0
    assert result.error == "Accordion report structure contains no sections"


@pytest.mark.asyncio
async def test_comprehensive_report_preserves_store_while_dossier_job_is_pending(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(2))
    orchestrator._store_manager = MagicMock()
    orchestrator._store_manager.create_store.return_value = "stores/context"
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="",
            interaction_id="interaction-123",
            status=ResearchStatus.IN_PROGRESS,
            error="polling state uncertain",
        )
    )
    orchestrator._execute_direct_generation = AsyncMock()

    result = await orchestrator.generate_comprehensive_report(
        company_name="Acme",
        stage1_context="website evidence",
    )

    assert result.success is False
    assert result.interaction_id == "interaction-123"
    orchestrator._execute_direct_generation.assert_not_awaited()
    orchestrator._store_manager.delete_store.assert_not_called()


@pytest.mark.asyncio
async def test_comprehensive_report_cancellation_after_acceptance_preserves_store(
    orchestrator, monkeypatch
):
    import asyncio

    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(2))
    orchestrator._store_manager = MagicMock()
    orchestrator._store_manager.create_store.return_value = "stores/context"
    cancelled = asyncio.CancelledError()
    cancelled.interaction_id = "interaction-123"  # type: ignore[attr-defined]
    orchestrator._execute_with_retry = AsyncMock(side_effect=cancelled)

    with pytest.raises(asyncio.CancelledError):
        await orchestrator.generate_comprehensive_report(
            company_name="Acme",
            stage1_context="website evidence",
        )

    orchestrator._store_manager.delete_store.assert_not_called()


@pytest.mark.asyncio
async def test_comprehensive_report_preserves_paid_dossier_id_during_stage1_fallback(
    orchestrator, monkeypatch
):
    monkeypatch.setattr(DeepResearchOrchestrator, "_sections_cache", _accordion_sections(1))
    orchestrator.SECTION_WRITE_DELAY = 0
    orchestrator._store_manager = MagicMock()
    orchestrator._store_manager.create_store.return_value = "stores/context"
    orchestrator._execute_with_retry = AsyncMock(
        return_value=ResearchResult(
            content="",
            interaction_id="interaction-paid",
            status=ResearchStatus.FAILED,
            error="provider response incomplete",
        )
    )
    orchestrator._execute_direct_generation = AsyncMock(
        return_value=ResearchResult(content=" ".join(["analysis"] * 500))
    )

    result = await orchestrator.generate_comprehensive_report(
        company_name="Acme",
        stage1_context="trusted stage one evidence",
        target_pages=1,
    )

    assert result.success is True
    assert result.interaction_id == "interaction-paid"
