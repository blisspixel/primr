"""
Coverage tests for prompts.py.

Exercises list_prompts and get_prompt for all three prompts plus the
unknown-prompt error path, through the registered MCP handlers.
"""

import tempfile
from pathlib import Path

import pytest
from mcp.types import GetPromptRequest, GetPromptRequestParams, ListPromptsRequest

from primr.mcp_server.server import create_mcp_server


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        yield create_mcp_server(journal_path=journal_path)


async def _get_prompt(server, name, arguments=None):
    handler = server.server.request_handlers[GetPromptRequest]
    return await handler(
        GetPromptRequest(
            method="prompts/get",
            params=GetPromptRequestParams(name=name, arguments=arguments or {}),
        )
    )


class TestListPrompts:
    @pytest.mark.asyncio
    async def test_lists_all(self, server):
        handler = server.server.request_handlers[ListPromptsRequest]
        result = await handler(ListPromptsRequest(method="prompts/list"))
        names = [p.name for p in result.root.prompts]
        assert "research_workflow" in names
        assert "strategy_selection" in names
        assert "governed_execution" in names


class TestGetPrompt:
    @pytest.mark.asyncio
    async def test_research_workflow_default(self, server):
        result = await _get_prompt(server, "research_workflow")
        text = result.root.messages[0].content.text
        assert "Company Research Workflow" in text
        assert "the target company" in text
        assert "vendor-neutral AI Strategy by default" in text
        assert 'platform="azure"' not in text
        assert "Estimate Costs (Required)" in text
        assert 'max_estimated_cost_usd=estimate["estimated_cost_usd"]' in text
        assert 'approval_token=estimate["approval_token"]' in text
        assert "34-53 minutes" in text

    @pytest.mark.asyncio
    async def test_research_workflow_with_company(self, server):
        result = await _get_prompt(server, "research_workflow", {"company_name": "Acme Corp"})
        text = result.root.messages[0].content.text
        assert "Acme Corp" in text

    @pytest.mark.asyncio
    async def test_strategy_selection_default(self, server):
        result = await _get_prompt(server, "strategy_selection")
        text = result.root.messages[0].content.text
        assert "Strategy Document Selection Guide" in text
        assert "business-first decisions" in text
        assert "A platform is an evaluation emphasis" in text
        assert "Copilot" not in text
        assert "Bedrock" not in text
        assert "Vertex AI" not in text
        assert "estimate = estimate_strategy(" in text
        assert 'max_estimated_cost_usd=estimate["estimated_cost_usd"]' in text
        assert 'approval_token=estimate["approval_token"]' in text

    @pytest.mark.asyncio
    async def test_strategy_selection_with_context(self, server):
        result = await _get_prompt(server, "strategy_selection", {"context": "B2C retail company"})
        text = result.root.messages[0].content.text
        assert "B2C retail company" in text

    @pytest.mark.asyncio
    async def test_governed_execution(self, server):
        result = await _get_prompt(server, "governed_execution")
        text = result.root.messages[0].content.text
        assert "Governed Execution Contract" in text
        assert "estimate_run" in text
        assert "agnostic AI Strategy by default" in text
        assert "when `platform` is set" not in text
        assert "Authenticated HTTP clients receive metadata" in text
        assert 'destination="client-deliverables"' in text
        assert 'destination="/path/to/output"' not in text
        assert text.count('max_estimated_cost_usd=estimate["estimated_cost_usd"]') == 3
        assert text.count('approval_token=estimate["approval_token"]') == 3

    @pytest.mark.asyncio
    async def test_unknown_prompt_raises(self, server):
        with pytest.raises(ValueError, match="Unknown prompt"):
            await _get_prompt(server, "no_such_prompt")
