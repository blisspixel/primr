"""
Tests for resource handlers.

Task 7: Resource handlers
"""

import json
import tempfile
from pathlib import Path
from urllib.parse import quote

import pytest
from mcp.types import ListResourcesRequest, ReadResourceRequest, ReadResourceRequestParams

from primr.mcp_server.security import PathValidator
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage
from primr.qa.calibration_baseline import build_calibration_baseline


class TestResourceListing:
    """Tests for resource listing."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_list_resources(self, server):
        """All resources are listed."""
        handler = server.server.request_handlers[ListResourcesRequest]
        result = await handler(ListResourcesRequest(method="resources/list"))

        resources = result.root.resources
        uris = [str(r.uri) for r in resources]

        assert "primr://research/status" in uris
        assert "primr://research/next-actions" in uris
        assert "primr://agent/governance" in uris
        assert "primr://research/modes" in uris
        assert "primr://output/latest" in uris
        assert "primr://output/artifacts" in uris
        assert "primr://calibration/baseline/inspection?path={baseline_path}" in uris
        assert "primr://config" in uris


class TestResearchStatusResource:
    """Tests for primr://research/status resource."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_status_idle_when_no_job(self, server):
        """Status is idle when no job exists."""
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert data["status"] == "idle"
        assert data["job_id"] is None

    @pytest.mark.asyncio
    async def test_status_in_progress_with_job(self, server):
        """Status is in_progress when job is active."""
        # Create a job
        job = server.job_store.create("Acme Corp", "full")

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert data["status"] == "in_progress"
        assert data["job_id"] == job.job_id
        assert data["company_name"] == "Acme Corp"
        assert data["current_stage"] == "accepted"

    @pytest.mark.asyncio
    async def test_status_completed_with_terminal_job(self, server):
        """Status shows completed job details."""
        # Create and complete a job
        job = server.job_store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        job.output_paths = ["output/report.md"]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert data["status"] == "completed"
        assert data["completion_time"] is not None
        assert data["output_paths"] == ["output/report.md"]

    @pytest.mark.asyncio
    async def test_status_failed_with_error(self, server):
        """Status shows error details for failed job."""
        # Create and fail a job
        job = server.job_store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.FAILED)
        job.error_type = "test_error"
        job.error_message = "Test error message"
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/status"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert data["status"] == "failed"
        assert data["error_type"] == "test_error"
        assert data["error_message"] == "Test error message"


class TestResearchModesResource:
    """Tests for primr://research/modes resource."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_research_modes_returns_default_mode(self, server):
        """Research modes resource includes the default mode."""
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/modes"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert data["default_mode"] == "full"
        assert data["search_defaults"]["provider"] == "duckduckgo"
        assert any(mode["id"] == "premium" for mode in data["modes"])


class TestResearchNextActionsResource:
    """Tests for primr://research/next-actions resource."""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_next_actions_idle(self, server):
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/next-actions"),
            )
        )
        data = json.loads(result.root.contents[0].text)
        assert data["recommended_action"] == "start_new_research"

    @pytest.mark.asyncio
    async def test_next_actions_completed(self, server):
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = ["output/report.md"]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://research/next-actions"),
            )
        )
        data = json.loads(result.root.contents[0].text)
        assert data["recommended_action"] == "review_output"
        assert "output_paths" in data


class TestAgentGovernanceResource:
    """Tests for primr://agent/governance resource."""

    @pytest.fixture
    def server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_agent_governance_describes_cap_argument(self, server):
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://agent/governance"),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["research_flow"]["cap_argument"] == "max_estimated_cost_usd"
        assert data["strategy_flow"]["cap_argument"] == "max_estimated_cost_usd"
        assert "35-45 minutes" in data["research_flow"]["expected_runtime"]
        assert data["research_flow"]["wait_tool"] == "wait_for_status_change"


class TestCalibrationBaselineInspectionResource:
    """Tests for primr://calibration/baseline/inspection."""

    @pytest.fixture
    def server(self, tmp_path):
        server = create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))
        server.path_validator = PathValidator(allowed_roots=[str(tmp_path)])
        return server

    @pytest.mark.asyncio
    async def test_reads_baseline_inspection_from_allowed_path(self, server, tmp_path):
        baseline = build_calibration_baseline(
            {
                "manifest_format": "primr.calibration_pack.v1",
                "totals": {"reports": 1, "sidecars_present": 0, "failures": 0},
                "reports": [
                    {
                        "report_path": "output/Acme_Strategic_Overview.md",
                        "report_file": "Acme_Strategic_Overview.md",
                        "sidecar_exists": False,
                        "claims_sampled": 2,
                        "judgeable_claims": 2,
                    }
                ],
            },
            minimum_reports=1,
        )
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        uri = (
            "primr://calibration/baseline/inspection?path="
            f"{quote(baseline_path.as_posix(), safe='')}"
        )

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri=uri),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["inspection_format"] == "primr.calibration_readiness_inspection.v1"
        assert data["counts"]["missing_sidecars"] == 1
        assert data["blockers"]["missing_sidecars"][0]["report_file"] == (
            "Acme_Strategic_Overview.md"
        )

    @pytest.mark.asyncio
    async def test_rejects_path_outside_allowed_roots(self, server):
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri="primr://calibration/baseline/inspection?path=../secret.json"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "invalid_path"
        assert data["error_type"] == "path_traversal_blocked"

    @pytest.mark.asyncio
    async def test_requires_path_query(self, server):
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://calibration/baseline/inspection"),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "missing_path"


class TestConfigResource:
    """Tests for primr://config resource."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_config_returns_modes(self, server):
        """Config includes available modes."""
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://config"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert "scrape" in data["available_modes"]
        assert "deep" in data["available_modes"]
        assert "full" in data["available_modes"]

    @pytest.mark.asyncio
    async def test_config_returns_strategies(self, server):
        """Config includes available strategies."""
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://config"),
            )
        )

        content = result.root.contents[0]
        data = json.loads(content.text)

        assert "ai_strategy" in data["available_strategies"]
        assert "customer_experience" in data["available_strategies"]

    @pytest.mark.asyncio
    async def test_config_no_sensitive_data(self, server):
        """Config does not include sensitive data."""
        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="primr://config"),
            )
        )

        content = result.root.contents[0]
        text = content.text.lower()

        # Should not contain API key patterns
        assert "sk-" not in text
        assert "akia" not in text
        assert "-----begin" not in text
        assert "api_key" not in text
        assert "secret" not in text


class TestUnknownResource:
    """Tests for unknown resource handling."""

    @pytest.fixture
    def server(self):
        """Create a server with temp journal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = str(Path(tmpdir) / "test_journal.json")
            yield create_mcp_server(journal_path=journal_path)

    @pytest.mark.asyncio
    async def test_unknown_resource_raises(self, server):
        """Unknown resource raises ValueError."""
        handler = server.server.request_handlers[ReadResourceRequest]

        with pytest.raises(ValueError, match="Unknown resource"):
            await handler(
                ReadResourceRequest(
                    method="resources/read",
                    params=ReadResourceRequestParams(uri="primr://unknown"),
                )
            )
