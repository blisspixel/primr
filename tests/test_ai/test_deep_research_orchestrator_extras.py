"""Additional unit tests for DeepResearchOrchestrator covering _assemble_report
and _execute_followup branches."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from primr.ai.deep_research import DeepResearchOrchestrator, ResearchStatus


@pytest.fixture
def orchestrator(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


# ---------------------------------------------------------------------------
# _assemble_report
# ---------------------------------------------------------------------------


class TestAssembleReport:
    def test_includes_title_and_company_metadata(self, orchestrator):
        sections = [{"title": "Executive Summary", "content": "body"}]
        report = orchestrator._assemble_report(
            company_name="Acme", website_url="https://acme.example", sections=sections
        )
        assert "# Strategic Company Overview: Acme" in report
        assert "**Company Name:** Acme" in report
        assert "**Website:** https://acme.example" in report

    def test_uses_full_legal_name_in_metadata(self, orchestrator):
        sections = [{"title": "S", "content": "x"}]
        report = orchestrator._assemble_report(
            company_name="Acme",
            website_url=None,
            sections=sections,
            full_company_name="Acme Corporation, Inc.",
        )
        # Title uses user name; metadata uses full legal name
        assert "Overview: Acme" in report
        assert "**Company Name:** Acme Corporation, Inc." in report

    def test_includes_industry_when_provided(self, orchestrator):
        sections = [{"title": "S", "content": "x"}]
        report = orchestrator._assemble_report(
            company_name="Acme",
            website_url=None,
            sections=sections,
            industry="Financial Services",
        )
        assert "**Industry:** Financial Services" in report

    def test_omits_industry_when_none(self, orchestrator):
        sections = [{"title": "S", "content": "x"}]
        report = orchestrator._assemble_report(
            company_name="Acme", website_url=None, sections=sections
        )
        assert "**Industry:**" not in report

    def test_omits_website_when_none(self, orchestrator):
        sections = [{"title": "S", "content": "x"}]
        report = orchestrator._assemble_report(
            company_name="Acme", website_url=None, sections=sections
        )
        assert "**Website:**" not in report

    def test_inserts_horizontal_rule_every_5_sections(self, orchestrator):
        sections = [{"title": f"S{i}", "content": f"body {i}"} for i in range(11)]
        report = orchestrator._assemble_report(
            company_name="Acme", website_url=None, sections=sections
        )
        # Should have separators after section 5 and 10
        assert report.count("\n---\n") >= 2

    def test_no_trailing_rule_after_last_section(self, orchestrator):
        sections = [{"title": f"S{i}", "content": f"b{i}"} for i in range(5)]
        report = orchestrator._assemble_report(
            company_name="Acme", website_url=None, sections=sections
        )
        # No rule after the last section
        assert not report.rstrip().endswith("---")


# ---------------------------------------------------------------------------
# _execute_followup
# ---------------------------------------------------------------------------


class TestExecuteFollowup:
    @pytest.mark.asyncio
    async def test_returns_completed_with_content(self, orchestrator):
        interaction = MagicMock()
        interaction.id = "iid-1"
        # outputs is a list of objects with .text attribute
        out = MagicMock()
        out.text = "follow-up body"
        interaction.outputs = [out]

        orchestrator._client.interactions.create.return_value = interaction
        result = await orchestrator._execute_followup(
            "prev-iid-xyz", "prompt body"
        )
        assert result.status == ResearchStatus.COMPLETED
        assert "follow-up body" in result.content

    @pytest.mark.asyncio
    async def test_empty_content_returns_failed(self, orchestrator):
        interaction = MagicMock()
        interaction.id = "iid-1"
        interaction.outputs = []  # no text parts
        orchestrator._client.interactions.create.return_value = interaction
        result = await orchestrator._execute_followup(
            "prev-iid", "prompt"
        )
        assert result.status == ResearchStatus.FAILED
        assert "Empty response" in result.error

    @pytest.mark.asyncio
    async def test_rate_limit_returns_specific_error(self, orchestrator):
        orchestrator._client.interactions.create.side_effect = RuntimeError(
            "429 quota exceeded"
        )
        result = await orchestrator._execute_followup("prev", "prompt")
        assert result.status == ResearchStatus.FAILED
        assert "Rate limited" in result.error

    @pytest.mark.asyncio
    async def test_invalid_interaction_id_returns_specific_error(
        self, orchestrator
    ):
        orchestrator._client.interactions.create.side_effect = RuntimeError(
            "invalid previous_interaction_id provided"
        )
        result = await orchestrator._execute_followup("prev", "prompt")
        assert result.status == ResearchStatus.FAILED
        assert "Interaction ID issue" in result.error

    @pytest.mark.asyncio
    async def test_generic_error_returns_failed(self, orchestrator):
        orchestrator._client.interactions.create.side_effect = RuntimeError(
            "something else"
        )
        result = await orchestrator._execute_followup("prev", "prompt")
        assert result.status == ResearchStatus.FAILED
        assert "something else" in result.error

    @pytest.mark.asyncio
    async def test_increments_api_call_count(self, orchestrator):
        interaction = MagicMock()
        interaction.id = "iid"
        interaction.outputs = []
        orchestrator._client.interactions.create.return_value = interaction
        before = orchestrator._api_call_count
        await orchestrator._execute_followup("prev", "prompt")
        assert orchestrator._api_call_count == before + 1
