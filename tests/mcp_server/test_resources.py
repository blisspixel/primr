"""
Tests for resource handlers.

Task 7: Resource handlers
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from mcp.types import ListResourcesRequest, ReadResourceRequest, ReadResourceRequestParams

from primr.mcp_server.security import PathValidator
from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage
from primr.qa.artifact_fingerprints import artifact_fingerprint
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
        assert "primr://output/artifacts/by_job/%7Bjob_id%7D" in uris
        assert "primr://output/qa_summary/by_job/%7Bjob_id%7D" in uris
        assert "primr://output/usage_summary/by_job/%7Bjob_id%7D" in uris
        assert "primr://output/source_summary/by_job/%7Bjob_id%7D" in uris
        assert "primr://output/trace_summary/by_job/%7Bjob_id%7D" in uris
        assert "primr://output/verification_summary/by_job/%7Bjob_id%7D" in uris
        assert "primr://output/calibration_summary/by_job/%7Bjob_id%7D" in uris
        assert "primr://eval/stage_scorecard/%7Beval_id%7D" in uris
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


class TestArtifactMetadataByJobResource:
    """Tests for primr://output/artifacts/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    @pytest.mark.asyncio
    async def test_reads_owned_job_artifact_metadata_without_body(self, server, tmp_path):
        report = tmp_path / "Acme_Strategic_Overview_07-17-2026.md"
        report.write_text("# Secret body that must not be returned", encoding="utf-8")
        missing = tmp_path / "missing.docx"
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report), str(missing)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/artifacts/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.1"
        assert data["job_id"] == job.job_id
        assert data["artifact_count"] == 2
        assert data["full_content_included"] is False
        assert "Secret body" not in text
        first = data["artifacts"][0]
        assert first["artifact_type"] == "report_markdown"
        assert first["artifact_role"] == "primary_report"
        assert first["exists"] is True
        assert first["size_bytes"] == report.stat().st_size
        assert first["content_hash"].startswith("sha256:")
        assert data["artifacts"][1]["exists"] is False

    @pytest.mark.asyncio
    async def test_expands_exact_format_siblings_only(self, server, tmp_path):
        report = tmp_path / "report.v2.md"
        docx = tmp_path / "report.v2.docx"
        unrelated = tmp_path / "unrelated.txt"
        report.write_text("body", encoding="utf-8")
        docx.write_bytes(b"docx")
        unrelated.write_text("other", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/artifacts/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert {row["file_name"] for row in data["artifacts"]} == {
            report.name,
            docx.name,
        }
        assert data["truncated"] is False

    @pytest.mark.asyncio
    async def test_returns_no_artifacts_for_job_without_outputs(self, server):
        job = server.job_store.create("Acme Corp", "full")

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/artifacts/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "no_artifacts"
        assert data["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Private", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/artifacts/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


class TestQASummaryByJobResource:
    """Tests for primr://output/qa_summary/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    @pytest.mark.asyncio
    async def test_reads_owned_job_qa_summary_without_body(self, server, tmp_path):
        qa_summary = tmp_path / "Acme_QA_Report.json"
        qa_summary.write_text(
            json.dumps(
                {
                    "overall_score": 91,
                    "status": "passed",
                    "ready_for_use": True,
                    "issues": [{"description": "Secret issue body"}],
                    "warnings": ["Secret warning body"],
                    "recommendations": ["Secret recommendation body"],
                    "secret_details": "Detailed narrative that must not be returned",
                }
            ),
            encoding="utf-8",
        )
        report = tmp_path / "report.md"
        report.write_text("# Report body", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report), str(qa_summary)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/qa_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.0"
        assert data["job_id"] == job.job_id
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "Detailed narrative" not in text
        assert "Secret issue body" not in text
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "qa_summary"
        assert summary["parsed"] is True
        assert summary["score_fields"] == {"overall_score": 91}
        assert summary["status_fields"] == {
            "ready_for_use": True,
            "status": "passed",
        }
        assert summary["count_fields"] == {
            "issues_count": 1,
            "recommendations_count": 1,
            "warnings_count": 1,
        }

    @pytest.mark.asyncio
    async def test_returns_not_found_when_job_has_no_qa_summary(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/qa_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "qa_summary_not_found"
        assert data["summary_count"] == 0
        assert data["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_malformed_json_returns_metadata_without_body(self, server, tmp_path):
        qa_summary = tmp_path / "Acme_QA_Report.json"
        qa_summary.write_text('{"overall_score": 91, "secret": "not closed"', encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(qa_summary)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/qa_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert "not closed" not in text
        assert data["summaries"][0]["parsed"] is False
        assert data["summaries"][0]["parse_error"] == "invalid_json"
        assert data["summaries"][0]["content_hash"].startswith("sha256:")

    @pytest.mark.asyncio
    async def test_summarizes_current_text_qa_report_without_body(self, server, tmp_path):
        qa_report = tmp_path / "Acme_QA_Report_06-28-2026_10-30-00.txt"
        qa_report.write_text(
            "\n".join(
                [
                    "Quality Assessment Report for Acme",
                    "OVERALL ASSESSMENT",
                    "Ready for Use: Yes",
                    "Confidence Level: High",
                    "Grade: 88/100",
                    "Quality Score: 88/100",
                    "Citation Score: 81/100",
                    "Total Citations: 12",
                    "1. Secret detailed issue body",
                ]
            ),
            encoding="utf-8",
        )
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(qa_report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/qa_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert "Secret detailed issue body" not in text
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "qa_summary"
        assert summary["source_format"] == "text"
        assert summary["score_fields"]["grade"] == 88
        assert summary["score_fields"]["quality_score"] == 88
        assert summary["score_fields"]["citation_score"] == 81
        assert summary["status_fields"] == {
            "confidence_level": "High",
            "ready_for_use": True,
        }
        assert summary["count_fields"] == {"total_citations": 12}

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        qa_summary = tmp_path / "Acme_QA_Report.json"
        qa_summary.write_text('{"overall_score": 91}', encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(qa_summary)]
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/qa_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


class TestUsageSummaryByJobResource:
    """Tests for primr://output/usage_summary/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    @pytest.mark.asyncio
    async def test_reads_owned_job_usage_summary_without_manifest_body(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report body", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        manifest = tmp_path / "run_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "job_id": job.job_id,
                    "company_name": "Acme Corp",
                    "company_url": "https://secret.example",
                    "mode": "full",
                    "estimate": {
                        "cost_usd": 0.76,
                        "time_minutes": 42,
                        "estimated_at": "2026-06-28T19:00:00Z",
                    },
                    "approval": {
                        "token": "secret approval token",
                        "approved_at": "2026-06-28T19:01:00Z",
                        "approved_by": "client-secret",
                        "bound_to_estimate": True,
                    },
                    "budget": {
                        "approved_ceiling_usd": 0.8,
                        "runtime_budget_active": True,
                        "enforcement": {
                            "preflight": "refuses to start when estimate exceeds cap",
                            "runtime_checkpoints": True,
                            "runtime": "required Deep Research task cannot be stopped",
                            "checkpointed_stages": ["optional strategy generation"],
                            "non_interruptible_required_tasks": ["required Deep Research task"],
                        },
                    },
                    "execution": {
                        "started_at": "2026-06-28T19:02:00Z",
                        "completed_at": "2026-06-28T19:44:00Z",
                        "status": "completed",
                        "actual_cost_usd": 0.72,
                        "actual_time_minutes": 42,
                    },
                    "artifacts": [str(report), "secret artifact path"],
                }
            ),
            encoding="utf-8",
        )
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/usage_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.0"
        assert data["job_id"] == job.job_id
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "secret approval token" not in text
        assert "client-secret" not in text
        assert "https://secret.example" not in text
        assert "secret artifact path" not in text
        summary = data["summaries"][0]
        assert summary["artifact_type"] == "run_manifest"
        assert summary["parsed"] is True
        assert summary["mode"] == "full"
        assert summary["estimate"] == {
            "cost_usd": 0.76,
            "estimated_at": "2026-06-28T19:00:00Z",
            "time_minutes": 42,
        }
        assert summary["approval"] == {
            "approved": True,
            "approved_at": "2026-06-28T19:01:00Z",
            "approved_by_present": True,
            "bound_to_estimate": True,
            "token_present": True,
        }
        assert summary["budget"] == {
            "approved_ceiling_usd": 0.8,
            "checkpointed_stages": ["optional strategy generation"],
            "non_interruptible_required_tasks": ["required Deep Research task"],
            "preflight": "refuses to start when estimate exceeds cap",
            "runtime": "required Deep Research task cannot be stopped",
            "runtime_budget_active": True,
            "runtime_checkpoints": True,
        }
        assert summary["execution"] == {
            "actual_cost_usd": 0.72,
            "actual_time_minutes": 42,
            "completed_at": "2026-06-28T19:44:00Z",
            "started_at": "2026-06-28T19:02:00Z",
            "status": "completed",
        }
        assert summary["artifact_count"] == 2

    @pytest.mark.asyncio
    async def test_returns_not_found_when_manifest_missing(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/usage_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "usage_summary_not_found"
        assert data["summary_count"] == 0
        assert data["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_malformed_manifest_returns_metadata_without_body(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report", encoding="utf-8")
        manifest = tmp_path / "run_manifest.json"
        manifest.write_text('{"estimate": {"token": "secret"', encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report), str(manifest)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/usage_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert "secret" not in text
        assert data["summaries"][0]["parsed"] is False
        assert data["summaries"][0]["parse_error"] == "invalid_json"
        assert data["summaries"][0]["content_hash"].startswith("sha256:")

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report", encoding="utf-8")
        manifest = tmp_path / "run_manifest.json"
        manifest.write_text('{"schema_version": "1.0"}', encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/usage_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


class TestSourceSummaryByJobResource:
    """Tests for primr://output/source_summary/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    @pytest.mark.asyncio
    async def test_reads_owned_job_source_summary_without_report_body(self, server, tmp_path):
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text(
            "\n".join(
                [
                    "# Strategic Overview",
                    "Secret body claim uses a source [cite: 1] and another [cite: 2].",
                    "A bracket-style citation also appears [3].",
                    "",
                    "## Sources",
                    "[cite: 1] Acme newsroom - https://www.acme.example/news?q=launch",
                    "[cite: 2] https://investors.acme.example/q4",
                    "[3] SEC filing",
                    "    https://sec.gov/Archives/example",
                    "[cite: 4] https://www.acme.example/news?q=launch",
                    "[cite: 5] not-a-url",
                ]
            ),
            encoding="utf-8",
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/source_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.0"
        assert data["job_id"] == job.job_id
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "Secret body claim" not in text

        summary = data["summaries"][0]
        assert summary["artifact_type"] == "report_markdown"
        assert summary["parsed"] is True
        assert summary["source_section_present"] is True
        assert summary["inline_reference_count"] == 3
        assert summary["referenced_numbers"] == [1, 2, 3]
        assert summary["definition_count"] == 4
        assert summary["valid_source_count"] == 4
        assert summary["invalid_source_count"] == 1
        assert summary["duplicate_url_count"] == 1
        assert summary["missing_definition_numbers"] == []
        assert summary["unused_definition_numbers"] == [4]
        assert summary["domains"] == [
            {"count": 2, "domain": "acme.example"},
            {"count": 1, "domain": "investors.acme.example"},
            {"count": 1, "domain": "sec.gov"},
        ]
        assert summary["sources"][0] == {
            "domain": "acme.example",
            "reference": 1,
            "title": "Acme newsroom",
            "url": "https://www.acme.example/news?q=launch",
        }

    @pytest.mark.asyncio
    async def test_reports_missing_definitions_when_appendix_absent(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("## Body\nClaim [cite: 7] without appendix.", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/source_summary/by_job/{job.job_id}"
                ),
            )
        )

        summary = json.loads(result.root.contents[0].text)["summaries"][0]
        assert summary["source_section_present"] is False
        assert summary["referenced_numbers"] == [7]
        assert summary["definition_count"] == 0
        assert summary["missing_definition_numbers"] == [7]

    @pytest.mark.asyncio
    async def test_returns_not_found_when_no_report_artifact_exists(self, server, tmp_path):
        manifest = tmp_path / "run_manifest.json"
        manifest.write_text('{"schema_version": "1.0"}', encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(manifest)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/source_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "source_summary_not_found"
        assert data["summary_count"] == 0
        assert data["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text(
            "Claim [cite: 1]\n\n## Sources\n[cite: 1] https://a.example",
            encoding="utf-8",
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/source_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


class TestTraceSummaryByJobResource:
    """Tests for primr://output/trace_summary/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    def _write_trace(self, path: Path) -> None:
        header = {
            "schema_version": "1.1",
            "run_id": "trace-run-1",
            "company": "Acme_Corp",
            "started_at": "2026-06-28T21:00:00",
        }
        base_entry = {
            "run_id": "trace-run-1",
            "url": "https://secret.example/page",
            "timestamp": "2026-06-28T21:00:01",
            "tier_attempts": [],
            "success_tier": None,
            "blocked": False,
            "block_type": None,
            "blocked_reason": None,
            "http_status": None,
            "content_type": None,
            "final_url": "https://secret.example/final",
            "elapsed_total_ms": 0.0,
            "extracted_text_length": None,
            "validation_result": None,
            "access_assessment": None,
        }
        entries = [
            {
                **base_entry,
                "tier_attempts": [
                    {"tier": "requests", "success": False, "elapsed_ms": 100.0},
                    {"tier": "playwright", "success": True, "elapsed_ms": 500.0},
                ],
                "success_tier": "playwright",
                "http_status": 200,
                "extracted_text_length": 1200,
                "validation_result": {"valid": True},
            },
            {
                **base_entry,
                "tier_attempts": [
                    {"tier": "requests", "success": False, "elapsed_ms": 250.0},
                ],
                "blocked": True,
                "block_type": "hard_block",
                "http_status": 403,
                "extracted_text_length": 100,
                "validation_result": {"valid": False},
            },
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(row) for row in [header, *entries]) + "\n",
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_reads_owned_job_trace_summary_without_urls_or_raw_entries(
        self, server, tmp_path
    ):
        trace_path = tmp_path / "logs" / "scrape_traces" / "Acme_Corp_20260628.jsonl"
        self._write_trace(trace_path)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(trace_path)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/trace_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.0"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "secret.example" not in text

        summary = data["summaries"][0]
        assert summary["artifact_type"] == "scrape_trace"
        assert summary["parsed"] is True
        assert summary["trace_schema_version"] == "1.1"
        assert summary["raw_entries_included"] is False
        assert summary["urls_included"] is False
        assert summary["entry_count"] == 2
        assert summary["success_count"] == 1
        assert summary["failure_count"] == 1
        assert summary["success_rate"] == 0.5
        assert summary["blocked_count"] == 1
        assert summary["block_type_counts"] == [{"count": 1, "value": "hard_block"}]
        assert summary["http_status_counts"] == [
            {"count": 1, "value": "200"},
            {"count": 1, "value": "403"},
        ]
        assert summary["thin_page_count"] == 0
        assert summary["validated_page_count"] == 2
        assert summary["valid_page_count"] == 1
        assert summary["content_valid_rate"] == 0.5
        by_tier = {tier["tier"]: tier for tier in summary["tier_summaries"]}
        assert by_tier["requests"]["attempts"] == 2
        assert by_tier["requests"]["successes"] == 0
        assert by_tier["playwright"]["success_rate"] == 1.0
        assert by_tier["playwright"]["p95_latency_ms"] == 500.0

    @pytest.mark.asyncio
    async def test_returns_not_found_when_no_trace_artifact_exists(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/trace_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "trace_summary_not_found"
        assert data["summary_count"] == 0

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        trace_path = tmp_path / "logs" / "scrape_traces" / "Acme_Corp_20260628.jsonl"
        self._write_trace(trace_path)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(trace_path)]
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/trace_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


class TestVerificationSummaryByJobResource:
    """Tests for primr://output/verification_summary/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    def _write_verification(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "trust_score": 0.5,
                    "trust_percentage": 50,
                    "verified_count": 1,
                    "unverified_count": 0,
                    "contradicted_count": 1,
                    "total_claims": 2,
                    "duration_seconds": 12.4,
                    "claim_results": [
                        {
                            "claim": "Secret claim text",
                            "status": "verified",
                            "supporting_sources": ["https://secret.example/source"],
                            "evidence_sources": ["https://evidence.example/source"],
                            "search_query": "secret acquisition query",
                            "explanation": "Sensitive explanation",
                            "first_party_downgrade": True,
                        },
                        {
                            "claim": "Another secret claim",
                            "status": "contradicted",
                            "supporting_sources": ["https://secret.example/conflict"],
                            "search_query": "secret contradiction query",
                            "explanation": "Sensitive contradiction",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    @pytest.mark.asyncio
    async def test_reads_owned_job_verification_summary_without_raw_claims(self, server, tmp_path):
        verification = tmp_path / "verification.json"
        self._write_verification(verification)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(verification)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/verification_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.0"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "Secret claim text" not in text
        assert "secret.example" not in text
        assert "secret acquisition query" not in text
        assert "Sensitive explanation" not in text

        summary = data["summaries"][0]
        assert summary["artifact_type"] == "verification_summary"
        assert summary["parsed"] is True
        assert summary["raw_claim_results_included"] is False
        assert summary["source_urls_included"] is False
        assert summary["search_queries_included"] is False
        assert summary["trust_score"] == 0.5
        assert summary["trust_percentage"] == 50
        assert summary["verification_gate"] == "WARN"
        assert summary["total_claims"] == 2
        assert summary["verified_count"] == 1
        assert summary["contradicted_count"] == 1
        assert summary["claim_result_count"] == 2
        assert summary["first_party_downgrade_count"] == 1
        assert summary["source_reference_count"] == 3
        assert summary["claim_status_counts"] == [
            {"count": 1, "value": "contradicted"},
            {"count": 1, "value": "verified"},
        ]

    @pytest.mark.asyncio
    async def test_returns_not_found_when_no_verification_artifact_exists(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/verification_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "verification_summary_not_found"
        assert data["summary_count"] == 0

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        verification = tmp_path / "verification.json"
        self._write_verification(verification)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(verification)]
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/verification_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


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
        assert "34-53 minutes" in data["research_flow"]["expected_runtime"]
        assert data["research_flow"]["wait_tool"] == "wait_for_status_change"
        assert data["research_flow"]["approval_argument"] == "approval_token"
        assert data["skill_pack_flow"]["approval_argument"] == "approval_token"


class TestCalibrationSummaryByJobResource:
    """Tests for primr://output/calibration_summary/by_job/{job_id}."""

    @pytest.fixture
    def server(self, tmp_path):
        return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))

    def _write_calibration_sidecar(self, report_path: Path) -> Path:
        sidecar = report_path.with_name(report_path.name + ".calibration.json")
        sidecar.write_text(
            json.dumps(
                {
                    "report_file": report_path.name,
                    "report_artifact": artifact_fingerprint(report_path),
                    "max_per_label": 10,
                    "judge": {
                        "kind": "local",
                        "model": "qwen2.5:14b",
                        "cloud_fallbacks": 1,
                    },
                    "judge_agreement": {
                        "scope": "report",
                        "local_model": "qwen2.5:14b",
                        "compared": 4,
                        "agreed": 3,
                        "agreement": 0.75,
                        "disagreements": [
                            {
                                "claim_index": 2,
                                "cloud_verdict": "traceable",
                                "local_verdict": "untraceable",
                            }
                        ],
                    },
                    "per_label": {
                        "Confirmed": {
                            "sampled": 3,
                            "traceable": 1,
                            "untraceable": 1,
                            "no_source": 1,
                            "unfetchable": 0,
                            "exempt": 0,
                            "source_copied": 0,
                            "precision": 0.333,
                        },
                        "Hypothesis": {
                            "sampled": 2,
                            "traceable": 0,
                            "untraceable": 0,
                            "no_source": 0,
                            "unfetchable": 0,
                            "exempt": 1,
                            "source_copied": 1,
                            "precision": None,
                        },
                    },
                    "validation_rubric": {
                        "claims_with_reviews": 2,
                        "source_reviews": 3,
                        "support": {"supported": 2, "unsupported": 1},
                        "contradiction": {
                            "direct": 1,
                            "none": 2,
                            "partial": 0,
                            "unknown": 0,
                        },
                        "source_independence": {
                            "independent": 1,
                            "first_party": 2,
                            "unknown": 0,
                        },
                        "source_authority": {
                            "high": 1,
                            "medium": 1,
                            "low": 1,
                            "unknown": 0,
                        },
                        "reasoning_strength": {
                            "strong": 2,
                            "partial": 1,
                            "weak": 0,
                            "unknown": 0,
                        },
                        "uncertainty_honesty": {
                            "honest": 2,
                            "overstated": 1,
                            "understated": 0,
                            "unknown": 0,
                        },
                        "business_relevance": {
                            "high": 2,
                            "medium": 1,
                            "low": 0,
                            "unknown": 0,
                        },
                    },
                    "claims": [
                        {
                            "label": "Confirmed",
                            "section": "Secret Section",
                            "sentence": "Secret calibrated claim text",
                            "source_urls": ["https://secret.example/source"],
                            "verdict": "traceable",
                            "evidence_reviews": [
                                {
                                    "supported": True,
                                    "rationale": "Sensitive evidence rationale",
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return sidecar

    @pytest.mark.asyncio
    async def test_reads_owned_job_calibration_summary_without_raw_claims(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report", encoding="utf-8")
        self._write_calibration_sidecar(report)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-a", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/calibration_summary/by_job/{job.job_id}"
                ),
            )
        )

        text = result.root.contents[0].text
        data = json.loads(text)
        assert data["schema_version"] == "1.0"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "Secret calibrated claim text" not in text
        assert "secret.example" not in text
        assert "Sensitive evidence rationale" not in text

        summary = data["summaries"][0]
        assert summary["artifact_type"] == "calibration_sidecar"
        assert summary["parsed"] is True
        assert summary["report_binding_valid"] is True
        assert summary["raw_claims_included"] is False
        assert summary["claim_text_included"] is False
        assert summary["source_urls_included"] is False
        assert summary["evidence_reviews_included"] is False
        assert summary["rationales_included"] is False
        assert summary["report_file"] == "Acme_Report.md"
        assert summary["judge"] == {
            "kind": "local",
            "model": "qwen2.5:14b",
            "cloud_fallbacks": 1,
        }
        assert summary["judge_agreement"] == {
            "scope": "report",
            "local_model": "qwen2.5:14b",
            "compared": 4,
            "agreed": 3,
            "agreement": 0.75,
        }
        assert summary["claim_result_count"] == 1
        assert summary["claims_sampled"] == 5
        assert summary["decidable_claims"] == 3
        assert summary["traceable_count"] == 1
        assert summary["untraceable_count"] == 1
        assert summary["no_source_count"] == 1
        assert summary["exempt_count"] == 1
        assert summary["source_copied_count"] == 1
        by_label = {item["label"]: item for item in summary["per_label"]}
        assert by_label["Confirmed"]["precision"] == 0.333
        assert by_label["Hypothesis"]["exempt"] == 1
        assert by_label["Hypothesis"]["source_copied"] == 1
        rubric = summary["validation_rubric"]
        assert rubric["claims_with_reviews"] == 2
        assert rubric["source_reviews"] == 3
        assert rubric["support_counts"] == [
            {"count": 2, "value": "supported"},
            {"count": 1, "value": "unsupported"},
        ]

    @pytest.mark.asyncio
    async def test_reads_explicit_calibration_sidecar_artifact(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report", encoding="utf-8")
        sidecar = self._write_calibration_sidecar(report)
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(sidecar)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/calibration_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["summary_count"] == 1
        assert data["summaries"][0]["parsed"] is True

    @pytest.mark.asyncio
    async def test_rejects_sidecar_after_report_bytes_change(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Original report", encoding="utf-8")
        self._write_calibration_sidecar(report)
        report.write_text("# Mutated report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/calibration_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        summary = data["summaries"][0]
        assert summary["parsed"] is False
        assert summary["parse_error"] == "report_artifact_mismatch"
        assert "claims_sampled" not in summary

    @pytest.mark.asyncio
    async def test_rejects_sidecar_when_bound_report_is_missing(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Original report", encoding="utf-8")
        sidecar = self._write_calibration_sidecar(report)
        report.unlink()
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(sidecar)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/calibration_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        summary = data["summaries"][0]
        assert summary["parsed"] is False
        assert summary["parse_error"] == "report_artifact_mismatch"

    @pytest.mark.asyncio
    async def test_returns_not_found_when_no_calibration_sidecar_exists(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        server.job_store.update(job)

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/calibration_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "calibration_summary_not_found"
        assert data["summary_count"] == 0

    @pytest.mark.asyncio
    async def test_rejects_unowned_http_job_like_missing(self, server, tmp_path):
        report = tmp_path / "Acme_Report.md"
        report.write_text("# Report", encoding="utf-8")
        self._write_calibration_sidecar(report)
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        server.job_store.update(job)
        server._auth_context = SimpleNamespace(client_id="client-b", scopes=["read"])

        handler = server.server.request_handlers[ReadResourceRequest]
        result = await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(
                    uri=f"primr://output/calibration_summary/by_job/{job.job_id}"
                ),
            )
        )

        data = json.loads(result.root.contents[0].text)
        assert data["error"] == "job_not_found"
        assert data["job_id"] == job.job_id


class TestCalibrationBaselineInspectionResource:
    """Tests for primr://calibration/baseline/inspection."""

    @pytest.fixture
    def server(self, tmp_path):
        server = create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))
        server.path_validator = PathValidator(allowed_roots=[str(tmp_path)])
        return server

    @staticmethod
    def _agreement_sidecar(*, confirmed_claims: bool = True) -> dict[str, object]:
        confirmed_sampled = 1 if confirmed_claims else 0
        return {
            "judge": {"kind": "cloud", "model": "fast-tier"},
            "per_label": {
                "Confirmed": {
                    "sampled": confirmed_sampled,
                    "traceable": confirmed_sampled,
                    "untraceable": 0,
                    "no_source": 0,
                    "unfetchable": 0,
                    "exempt": 0,
                    "source_copied": 0,
                },
                "Reported": {
                    "sampled": 1,
                    "traceable": 1,
                    "untraceable": 0,
                    "no_source": 0,
                    "unfetchable": 0,
                    "exempt": 0,
                    "source_copied": 0,
                },
            },
            "validation_rubric": {
                "source_reviews": 1,
                "support": {"supported": 1},
                "contradiction": {"none": 1},
                "source_independence": {"independent": 1},
                "source_authority": {"high": 1},
                "reasoning_strength": {"strong": 1},
                "uncertainty_honesty": {"honest": 1},
                "business_relevance": {"high": 1},
            },
            "judge_agreement": {
                "scope": "report",
                "local_model": "qwen2.5:14b",
                "compared": 1,
                "agreed": 1,
                "agreement": 1.0,
            },
        }

    def _partial_confirmed_floor_baseline(self) -> dict[str, object]:
        reports = []
        for index in range(5):
            reports.append(
                {
                    "report_path": f"output/Company{index}_Strategic_Overview.md",
                    "report_file": f"Company{index}_Strategic_Overview.md",
                    "sidecar_exists": True,
                    "sidecar_matches_report": True,
                    "claims_sampled": 2,
                    "judgeable_claims": 2,
                    "coverage_tags": ["clean"] if index % 2 == 0 else ["blocked_origin"],
                    "sidecar": self._agreement_sidecar(confirmed_claims=index != 0),
                }
            )
        return build_calibration_baseline(
            {
                "manifest_format": "primr.calibration_pack.v1",
                "totals": {"reports": 5, "sidecars_present": 5, "failures": 0},
                "representation": {
                    "selection_format": "primr.calibration_pack_selection.v1",
                    "selection_path": ".agent/calibration-selection.json",
                    "required_tags": ["clean", "blocked_origin"],
                    "present_tags": ["clean", "blocked_origin"],
                    "missing_tags": [],
                },
                "reports": reports,
            },
            minimum_reports=5,
        )

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
    async def test_reads_partial_confirmed_floor_inspection_contract(self, server, tmp_path):
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            json.dumps(self._partial_confirmed_floor_baseline()),
            encoding="utf-8",
        )
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
        assert data["ready"] is True
        assert data["gate_recommendation"]["status"] == "not_recommended"
        assert data["gate_recommendation"]["reason"] == ("incomplete_confirmed_traceability_floor")
        assert data["gate_recommendation"]["reports_total"] == 5
        assert data["gate_recommendation"]["reports_considered"] == 4
        assert data["gate_recommendation"]["reports_without_decidable_confirmed"] == 1
        assert data["gate_recommendation"]["confirmed_traceability_floor_complete"] is False
        assert data["gate_recommendation"]["env_assignment"] is None
        review = data["operator_review"]
        assert review["decision_status"] == "report_only_recommended"
        assert review["operator_may_arm_after_review"] is False
        assert any(item["id"] == "report_only_gate_decision" for item in review["items"])
        assert data["next_actions"]["hard_gate_action"] == (
            "keep_gate_unset_until_confirmed_floor_complete"
        )
        assert data["next_actions"]["gate_recommendation_reason"] == (
            "incomplete_confirmed_traceability_floor"
        )
        assert data["next_actions"]["reports_without_decidable_confirmed"] == 1
        assert any(
            item["reason"] == "incomplete_confirmed_traceability_floor"
            for item in data["next_actions"]["items"]
        )
        decision_template = data["operator_decision_template"]
        assert decision_template["recommended_decision"] == "keep_report_only"
        assert decision_template["allowed_decisions"] == ["keep_report_only"]
        assert decision_template["hard_gate_action"] == (
            "keep_gate_unset_until_confirmed_floor_complete"
        )
        assert decision_template["evidence"]["reports_without_decidable_confirmed"] == 1

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
        assert "premium" in data["available_modes"]

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
        assert "skills" in data["available_strategies"]
        assert "Business-first AI portfolio" in data["available_strategies"]["ai_strategy"]

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


@pytest.mark.parametrize(
    "manifest_body",
    ["not json", "[]", '{"job_id":"another-job"}'],
)
def test_adjacent_manifest_requires_correlated_object(tmp_path, manifest_body):
    from primr.mcp_server.artifact_resources import _job_manifest_paths

    report = tmp_path / "report.md"
    report.write_text("body", encoding="utf-8")
    (tmp_path / "run_manifest.json").write_text(manifest_body, encoding="utf-8")
    assert _job_manifest_paths([str(report)], "job-1") == []
