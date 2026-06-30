"""
Coverage tests for resources.py and agentic_resources.py read paths.

Focuses on output/latest, output/artifacts, output/by_job, manifest/latest,
strategies/available, and the agentic roadmap/memory/context resources.
"""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

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

    @pytest.mark.asyncio
    async def test_authenticated_read_scope_omits_latest_report_body(
        self, server, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "output" / "acme"
        out.mkdir(parents=True)
        report = out / "report.md"
        report.write_text("# SECRET latest body", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read"],
            is_authenticated=True,
        )

        data = await _read(server, "primr://output/latest?full_content=true")
        assert "SECRET latest body" not in json.dumps(data)
        assert data["content_preview"] is None
        assert data["content_preview_included"] is False
        assert data["full_content_included"] is False
        assert data["report_read_required"] is True
        assert data["required_scopes"] == ["report"]

    @pytest.mark.asyncio
    async def test_authenticated_report_scope_still_uses_explicit_latest_report_read(
        self, server, monkeypatch, tmp_path
    ):
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "output" / "acme"
        out.mkdir(parents=True)
        report = out / "report.md"
        report.write_text("# SECRET latest body", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )

        data = await _read(server, "primr://output/latest?full_content=true")
        assert "SECRET latest body" not in json.dumps(data)
        assert data["content_preview"] is None
        assert data["content_preview_included"] is False
        assert data["full_content_included"] is False
        assert data["report_read_required"] is True
        assert "required_scopes" not in data


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

    @pytest.mark.asyncio
    async def test_authenticated_read_scope_omits_report_preview(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# SECRET job report", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(server, f"primr://output/by_job/{job.job_id}")
        assert "SECRET job report" not in json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["content_preview"] is None
        assert data["content_preview_included"] is False
        assert data["report_read_required"] is True
        assert data["report_read_uri"] == f"primr://output/report/by_job/{job.job_id}"
        assert data["required_scopes"] == ["report"]

    @pytest.mark.asyncio
    async def test_authenticated_report_scope_still_uses_explicit_by_job_report_read(
        self, server, tmp_path
    ):
        report = tmp_path / "report.md"
        report.write_text("# SECRET job report", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(server, f"primr://output/by_job/{job.job_id}")
        assert "SECRET job report" not in json.dumps(data)
        assert data["job_id"] == job.job_id
        assert data["content_preview"] is None
        assert data["content_preview_included"] is False
        assert data["report_read_required"] is True
        assert data["report_read_uri"] == f"primr://output/report/by_job/{job.job_id}"
        assert "required_scopes" not in data


class TestReportContentByJob:
    @pytest.mark.asyncio
    async def test_report_resource_requires_report_scope(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# SECRET full report", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(server, f"primr://output/report/by_job/{job.job_id}?content_mode=full")
        assert "SECRET full report" not in json.dumps(data)
        assert data["error"] == "insufficient_scope"
        assert data["required_scopes"] == ["report"]
        assert data["content_included"] is False

    @pytest.mark.asyncio
    async def test_report_resource_returns_bounded_preview_with_scope(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# bounded report body", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(
            server,
            f"primr://output/report/by_job/{job.job_id}?content_mode=preview&max_chars=9",
        )
        assert data["content_mode"] == "preview"
        assert data["content_included"] is True
        assert data["full_content_included"] is False
        assert data["artifacts"][0]["content"] == "# bounded"
        assert data["artifacts"][0]["content_truncated"] is True

    @pytest.mark.asyncio
    async def test_report_resource_can_read_all_artifact_types(self, server, tmp_path):
        report = tmp_path / "Acme_Strategic_Overview.md"
        report.write_text("# overview", encoding="utf-8")
        strategy = tmp_path / "Acme_AI_Strategy.md"
        strategy.write_text("# strategy", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report), str(strategy)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(
            server,
            f"primr://output/report/by_job/{job.job_id}?content_mode=full&artifact_type=all",
        )
        assert data["full_content_included"] is True
        assert data["artifact_count"] == 2
        assert {row["type"] for row in data["artifacts"]} == {
            "strategic_overview",
            "ai_strategy",
        }

    @pytest.mark.asyncio
    async def test_report_resource_metadata_mode_excludes_content(self, server, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# metadata report", encoding="utf-8")
        server._auth_context = SimpleNamespace(
            client_id="client-a",
            scopes=["read", "report"],
            is_authenticated=True,
        )
        job = server.job_store.create("Acme Corp", "full", owner_client_id="client-a")
        job.output_paths = [str(report)]
        job.advance_stage(ResearchStage.COMPLETED)
        server.job_store.update(job)

        data = await _read(
            server,
            f"primr://output/report/by_job/{job.job_id}?content_mode=metadata",
        )
        assert data["content_mode"] == "metadata"
        assert data["content_included"] is False
        assert "content" not in data["artifacts"][0]
        assert data["artifacts"][0]["content_hash"].startswith("sha256:")


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
        monkeypatch.setenv("PRIMR_DATA_DIR", str(tmp_path / "data"))
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
