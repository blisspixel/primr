"""
Coverage tests for resources.py and agentic_resources.py read paths.

Focuses on output/latest, output/artifacts, output/by_job, manifest/latest,
strategies/available, and the agentic roadmap/memory/context resources.
"""

import json
import tempfile
from pathlib import Path

import pytest
from mcp.types import ReadResourceRequest, ReadResourceRequestParams

from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.types import ResearchStage


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tmpdir:
        journal_path = str(Path(tmpdir) / "test_journal.json")
        yield create_mcp_server(journal_path=journal_path)


async def _read(server, uri):
    handler = server.server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=uri),
        )
    )
    return json.loads(result.root.contents[0].text)


class TestLatestOutput:
    @pytest.mark.asyncio
    async def test_no_output_dir(self, server, monkeypatch, tmp_path):
        # cwd with no output/ directory -> "No reports available"
        monkeypatch.chdir(tmp_path)
        data = await _read(server, "primr://output/latest")
        assert data["report_path"] is None
        assert "No reports" in data["message"]

    @pytest.mark.asyncio
    async def test_empty_output_dir(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        data = await _read(server, "primr://output/latest")
        assert data["report_path"] is None

    @pytest.mark.asyncio
    async def test_latest_report_preview(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "output" / "acme"
        out.mkdir(parents=True)
        report = out / "report.md"
        report.write_text("# Hello world", encoding="utf-8")
        data = await _read(server, "primr://output/latest")
        # The resource uses a relative "output" Path, so the returned path is
        # relative to cwd.
        assert data["report_path"].endswith("report.md")
        assert data["content_preview"].startswith("# Hello")
        assert data["report_type"] == "markdown"
        assert "full_content" not in data

    @pytest.mark.asyncio
    async def test_latest_report_full_content(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "output" / "acme"
        out.mkdir(parents=True)
        report = out / "report.md"
        report.write_text("# Full body", encoding="utf-8")
        data = await _read(server, "primr://output/latest?full_content=true")
        assert data["full_content"] == "# Full body"


class TestArtifacts:
    @pytest.mark.asyncio
    async def test_no_job_empty_artifacts(self, server):
        data = await _read(server, "primr://output/artifacts")
        assert data["job_id"] is None
        assert data["artifacts"] == []

    @pytest.mark.asyncio
    async def test_artifacts_from_workspace(self, server, monkeypatch, tmp_path):
        monkeypatch.setattr("primr.config.config.OUTPUT_DIR", str(tmp_path))
        job = server.job_store.create("Acme Corp", "full")
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        workspace = tmp_path / "acme_corp"
        workspace.mkdir(parents=True)
        (workspace / "insights.txt").write_text("insight data", encoding="utf-8")
        (workspace / "report.md").write_text("report data", encoding="utf-8")

        data = await _read(server, "primr://output/artifacts")
        types = {a["artifact_type"] for a in data["artifacts"]}
        assert "insights" in types
        assert "report" in types
        for a in data["artifacts"]:
            assert "content_hash" in a
            assert a["size_bytes"] > 0


class TestOutputByJob:
    @pytest.mark.asyncio
    async def test_job_not_found(self, server):
        data = await _read(server, "primr://output/by_job/does-not-exist")
        assert data["error"] == "job_not_found"

    @pytest.mark.asyncio
    async def test_job_no_output(self, server):
        job = server.job_store.create("Acme Corp", "full")
        data = await _read(server, f"primr://output/by_job/{job.job_id}")
        assert data["error"] == "no_output"

    @pytest.mark.asyncio
    async def test_job_with_report(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# job report", encoding="utf-8")
        job = server.job_store.create("Acme Corp", "full")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(server, f"primr://output/by_job/{job.job_id}")
        assert data["job_id"] == job.job_id
        assert data["report_path"] == str(report)
        assert data["content_preview"].startswith("# job report")
        assert data["report_type"] == "markdown"


class TestManifestLatest:
    @pytest.mark.asyncio
    async def test_no_output_dir(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        data = await _read(server, "primr://output/manifest/latest")
        assert data["error"] == "no_manifest"

    @pytest.mark.asyncio
    async def test_no_manifest_files(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        data = await _read(server, "primr://output/manifest/latest")
        assert data["error"] == "no_manifest"

    @pytest.mark.asyncio
    async def test_reads_manifest(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "output" / "acme"
        out.mkdir(parents=True)
        manifest = out / "run_manifest.json"
        manifest.write_text(
            json.dumps({"job_id": "abc", "schema_version": "1.0"}), encoding="utf-8"
        )
        data = await _read(server, "primr://output/manifest/latest")
        assert data["job_id"] == "abc"


class TestStrategiesAvailable:
    @pytest.mark.asyncio
    async def test_lists_strategies(self, server):
        data = await _read(server, "primr://strategies/available")
        ids = {s["id"] for s in data["strategies"]}
        assert "ai_strategy" in ids
        assert "customer_experience" in ids
        assert "cost_warning" in data


class TestAgenticResources:
    @pytest.mark.asyncio
    async def test_roadmap(self, server):
        # roadmap reads ROADMAP.md from project root; should return valid JSON
        data = await _read(server, "primr://roadmap")
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_memory_for_company(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        data = await _read(server, "primr://memory/AcmeCorp")
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_context_missing_claude_md(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        data = await _read(server, "primr://context")
        assert data["error"] == "context_not_found"

    @pytest.mark.asyncio
    async def test_context_present(self, server, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "# Title\n\n## Quick Start\n\nDo things.\n\n## Other\n\nNEVER do bad things.\n",
            encoding="utf-8",
        )
        data = await _read(server, "primr://context")
        assert data["full_content_available"] is True
        assert "summary" in data
        assert data["summary"]["has_quick_start"] is True
