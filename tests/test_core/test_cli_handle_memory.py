"""Unit tests for _handle_memory in primr.core.cli.

Mocks ResearchMemory to exercise the list-companies and per-company
display branches plus error handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.cli import CLIConfig, Command, _handle_memory


def _config(**overrides):
    defaults = {"command": Command.MEMORY}
    defaults.update(overrides)
    return CLIConfig(**defaults)


class TestInitFailure:
    def test_returns_1_when_memory_init_fails(self, monkeypatch):
        monkeypatch.setattr(
            "primr.agentic.memory.ResearchMemory",
            MagicMock(side_effect=RuntimeError("init failed")),
        )
        assert _handle_memory(_config()) == 1


class TestMemoryList:
    def test_returns_0_with_empty_memory(self, monkeypatch):
        mem = MagicMock()
        mem.list_companies.return_value = []
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock(return_value=mem))
        assert _handle_memory(_config(memory_list=True)) == 0

    def test_lists_known_companies(self, monkeypatch):
        mem = MagicMock()
        mem.list_companies.return_value = ["Acme", "OtherCo"]
        mem.get_hypotheses.return_value = []
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock(return_value=mem))
        assert _handle_memory(_config(memory_list=True)) == 0
        mem.list_companies.assert_called_once()


class TestPerCompanyMemory:
    def test_no_company_specified_returns_1(self, monkeypatch):
        mem = MagicMock()
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock(return_value=mem))
        # company_name is "memory" (the positional placeholder) -> rejected
        config = _config(company_name="memory")
        assert _handle_memory(config) == 1

    def test_uses_memory_company_when_set(self, monkeypatch):
        mem = MagicMock()
        mem.get_hypotheses.return_value = []
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock(return_value=mem))
        config = _config(memory_company="Acme Corp")
        assert _handle_memory(config) == 0
        mem.get_hypotheses.assert_called_once_with("Acme Corp")

    def test_uses_website_positional_as_company(self, monkeypatch):
        # When the positional company_name is "memory", the website arg holds the company name.
        mem = MagicMock()
        mem.get_hypotheses.return_value = []
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock(return_value=mem))
        config = _config(company_name="memory", website="Acme Corp")
        assert _handle_memory(config) == 0
        mem.get_hypotheses.assert_called_once_with("Acme Corp")

    def test_displays_grouped_hypotheses(self, monkeypatch):
        # Build hypotheses with different confidence levels
        h_validated = MagicMock()
        h_validated.confidence.value = "validated"
        h_validated.statement = "Acme uses X"
        h_validated.evidence = "From press release"
        h_validated.topic = "tech-stack"

        h_low = MagicMock()
        h_low.confidence.value = "low"
        h_low.statement = "Maybe Acme does Y"
        h_low.evidence = None
        h_low.topic = None

        mem = MagicMock()
        mem.get_hypotheses.return_value = [h_validated, h_low]
        monkeypatch.setattr("primr.agentic.memory.ResearchMemory", MagicMock(return_value=mem))
        config = _config(memory_company="Acme")
        assert _handle_memory(config) == 0
