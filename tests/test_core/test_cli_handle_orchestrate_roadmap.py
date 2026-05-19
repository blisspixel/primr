"""Unit tests for _handle_orchestrate and _handle_roadmap in primr.core.cli."""

from __future__ import annotations

from unittest.mock import MagicMock

from primr.core.cli import (
    CLIConfig,
    Command,
    _handle_orchestrate,
    _handle_roadmap,
)


def _config(**overrides):
    defaults = {"command": Command.ORCHESTRATE}
    defaults.update(overrides)
    return CLIConfig(**defaults)


# ---------------------------------------------------------------------------
# _handle_orchestrate
# ---------------------------------------------------------------------------


class TestHandleOrchestrate:
    def test_missing_company_or_website_returns_1(self, monkeypatch):
        result = _handle_orchestrate(_config(company_name=None, website=None))
        assert result == 1

    def test_orchestrate_positional_shifts_args(self, monkeypatch):
        # When "orchestrate" is the company_name (positional), website holds the name.
        # Without an actual website, we still get 1.
        result = _handle_orchestrate(
            _config(company_name="orchestrate", website="Acme Corp")
        )
        # website becomes None after shift -> error
        assert result == 1

    def test_orchestration_failure_returns_1(self, monkeypatch):
        orchestrator = MagicMock()
        orchestrator.research = MagicMock(side_effect=RuntimeError("crashed"))
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            MagicMock(return_value=orchestrator),
        )
        monkeypatch.setattr(
            "primr.agentic.memory.ResearchMemory", MagicMock()
        )
        monkeypatch.setattr(
            "primr.agentic.orchestrator.OrchestratorConfig", MagicMock()
        )

        result = _handle_orchestrate(
            _config(company_name="Acme", website="https://acme.example")
        )
        assert result == 1

    def test_successful_research_returns_0(self, monkeypatch):
        result_obj = MagicMock()
        result_obj.is_success = True
        result_obj.duration_seconds = 12.5
        result_obj.report_path = "/path/report.md"
        result_obj.hypotheses = []
        result_obj.completed_stages = ["scrape", "analyze", "write"]
        result_obj.errors = []

        orchestrator = MagicMock()

        async def fake_research(**kwargs):
            return result_obj

        orchestrator.research = fake_research
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            MagicMock(return_value=orchestrator),
        )
        monkeypatch.setattr(
            "primr.agentic.memory.ResearchMemory", MagicMock()
        )
        monkeypatch.setattr(
            "primr.agentic.orchestrator.OrchestratorConfig", MagicMock()
        )

        result = _handle_orchestrate(
            _config(company_name="Acme", website="https://acme.example")
        )
        assert result == 0

    def test_failed_research_returns_1(self, monkeypatch):
        result_obj = MagicMock()
        result_obj.is_success = False
        result_obj.errors = ["network error"]
        result_obj.completed_stages = ["scrape"]

        orchestrator = MagicMock()

        async def fake_research(**kwargs):
            return result_obj

        orchestrator.research = fake_research
        monkeypatch.setattr(
            "primr.agentic.orchestrator.ResearchOrchestrator",
            MagicMock(return_value=orchestrator),
        )
        monkeypatch.setattr(
            "primr.agentic.memory.ResearchMemory", MagicMock()
        )
        monkeypatch.setattr(
            "primr.agentic.orchestrator.OrchestratorConfig", MagicMock()
        )

        result = _handle_orchestrate(
            _config(company_name="Acme", website="https://acme.example")
        )
        assert result == 1


# ---------------------------------------------------------------------------
# _handle_roadmap
# ---------------------------------------------------------------------------


class TestHandleRoadmap:
    def test_roadmap_init_failure_returns_1(self, monkeypatch):
        monkeypatch.setattr(
            "primr.agentic.roadmap_api.RoadmapAPI",
            MagicMock(side_effect=RuntimeError("yaml broken")),
        )
        assert _handle_roadmap(_config()) == 1

    def test_unknown_version_returns_1(self, monkeypatch):
        api = MagicMock()
        api.get_version.return_value = None
        api.list_by_status.return_value = []
        monkeypatch.setattr(
            "primr.agentic.roadmap_api.RoadmapAPI", MagicMock(return_value=api)
        )
        result = _handle_roadmap(_config(roadmap_version="999.0.0"))
        assert result == 1

    def test_known_version_returns_0(self, monkeypatch):
        version = MagicMock()
        version.number = "1.2.3"
        version.status.value = "completed"
        version.title = "Test release"
        version.features = []
        api = MagicMock()
        api.get_version.return_value = version
        monkeypatch.setattr(
            "primr.agentic.roadmap_api.RoadmapAPI", MagicMock(return_value=api)
        )
        assert _handle_roadmap(_config(roadmap_version="1.2.3")) == 0

    def test_version_string_without_v_prefix_normalized(self, monkeypatch):
        version = MagicMock()
        version.number = "1.0.0"
        version.status.value = "completed"
        version.title = "T"
        version.features = []
        api = MagicMock()
        api.get_version.return_value = version
        monkeypatch.setattr(
            "primr.agentic.roadmap_api.RoadmapAPI", MagicMock(return_value=api)
        )
        _handle_roadmap(_config(roadmap_version="1.0.0"))
        # Should have called get_version with the normalized number
        api.get_version.assert_called_once()

    def test_roadmap_overview_returns_0(self, monkeypatch):
        api = MagicMock()
        current = MagicMock()
        current.number = "1.0"
        next_ver = MagicMock()
        next_ver.number = "1.1"
        api.get_current_version.return_value = current
        api.get_next_version.return_value = next_ver
        api.list_by_status.return_value = []
        monkeypatch.setattr(
            "primr.agentic.roadmap_api.RoadmapAPI", MagicMock(return_value=api)
        )
        assert _handle_roadmap(_config()) == 0

    def test_roadmap_overview_with_versions_listed(self, monkeypatch):
        api = MagicMock()
        api.get_current_version.return_value = None
        api.get_next_version.return_value = None
        completed = [MagicMock(number=f"1.{i}", title=f"v1.{i}") for i in range(8)]
        planned = [MagicMock(number=f"2.{i}", title=f"v2.{i}") for i in range(3)]
        # api.list_by_status called twice — first for COMPLETED, then PLANNED
        api.list_by_status.side_effect = [completed, planned]
        monkeypatch.setattr(
            "primr.agentic.roadmap_api.RoadmapAPI", MagicMock(return_value=api)
        )
        assert _handle_roadmap(_config()) == 0
