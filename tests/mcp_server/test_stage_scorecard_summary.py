"""Tests for the stage eval scorecard MCP summary resource."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from primr.mcp_server.server import create_mcp_server
from primr.mcp_server.stage_scorecard_summary import read_stage_scorecard_summary_resource
from tests.mcp_server.sdk_compat import read_resource_handler


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    return create_mcp_server(journal_path=str(tmp_path / "test_journal.json"))


async def _read_resource(server, uri: str) -> dict:
    result = await read_resource_handler(server, uri)
    return json.loads(result.contents[0].text)


class TestStageScorecardSummaryResource:
    @pytest.mark.asyncio
    async def test_reads_compact_scorecard_without_raw_bodies(self, server, tmp_path):
        scorecard_dir = tmp_path / "output" / "evals" / "eval-2026-02-r1"
        scorecard_dir.mkdir(parents=True)
        scorecard_path = scorecard_dir / "stage_eval_scorecard.json"
        scorecard_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "decision_policy": "candidate_for_human_review_only",
                    "min_quality_score": 85.0,
                    "max_failure_rate": 0.0,
                    "prompt": "SECRET PROMPT",
                    "report_body": "SECRET REPORT BODY",
                    "rows": [
                        {
                            "stage_id": "fast.scrape_summary",
                            "backend_id": "gemini-flash",
                            "inference_profile": "cloud",
                            "attempts": 3,
                            "selected_attempts": 3,
                            "fallback_attempts": 0,
                            "failed_attempts": 0,
                            "failure_rate": 0.0,
                            "actual_cost_usd": 0.0123,
                            "avg_duration_seconds": 1.25,
                            "quality_score": 91.0,
                            "quality_sample_size": 5,
                            "quality_sources": ["SECRET QUALITY SOURCE BODY"],
                            "review_status": "candidate_for_human_review",
                            "blockers": [],
                        },
                        {
                            "stage_id": "fast.scrape_summary",
                            "backend_id": "local-qwen",
                            "inference_profile": "local",
                            "attempts": 2,
                            "selected_attempts": 1,
                            "fallback_attempts": 1,
                            "failed_attempts": 1,
                            "failure_rate": 0.5,
                            "actual_cost_usd": 0.0,
                            "avg_duration_seconds": 3.0,
                            "quality_score": 88.0,
                            "quality_sample_size": 4,
                            "quality_sources": ["SECRET LOCAL SOURCE BODY"],
                            "review_status": "needs_reliability_review",
                            "blockers": ["failure_rate_above_threshold"],
                            "raw_run_state": "SECRET RAW RUN STATE",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        data = await _read_resource(
            server,
            "primr://eval/stage_scorecard/eval-2026-02-r1",
        )

        text = json.dumps(data)
        assert data["schema_version"] == "1.0"
        assert data["eval_id"] == "eval-2026-02-r1"
        assert data["summary_count"] == 1
        assert data["full_content_included"] is False
        assert "SECRET PROMPT" not in text
        assert "SECRET REPORT BODY" not in text
        assert "SECRET QUALITY SOURCE BODY" not in text
        assert "SECRET RAW RUN STATE" not in text

        summary = data["summary"]
        assert summary["artifact_type"] == "stage_eval_scorecard"
        assert summary["parsed"] is True
        assert summary["raw_rows_included"] is False
        assert summary["quality_sources_included"] is False
        assert summary["row_count"] == 2
        assert summary["candidate_count"] == 1
        assert summary["route_totals"] == {
            "attempts": 5,
            "selected_attempts": 4,
            "fallback_attempts": 1,
            "failed_attempts": 1,
            "actual_cost_usd": 0.0123,
        }
        assert summary["quality_score_stats"] == {
            "count": 2,
            "min": 88.0,
            "max": 91.0,
            "average": 89.5,
        }
        assert summary["status_counts"] == [
            {"value": "candidate_for_human_review", "count": 1},
            {"value": "needs_reliability_review", "count": 1},
        ]
        assert summary["blocker_counts"] == [{"value": "failure_rate_above_threshold", "count": 1}]
        rows = summary["rows"]
        assert rows[0]["backend_id"] == "gemini-flash"
        assert "quality_sources" not in rows[0]
        assert "raw_run_state" not in rows[1]

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_scorecard(self, server):
        data = await _read_resource(
            server,
            "primr://eval/stage_scorecard/eval-missing",
        )

        assert data["error"] == "stage_scorecard_not_found"
        assert data["eval_id"] == "eval-missing"
        assert data["summary_count"] == 0

    def test_rejects_path_traversal_eval_id(self, server):
        result = read_stage_scorecard_summary_resource("primr://eval/stage_scorecard/../secret")
        data = json.loads(result[0].content)

        assert data["error"] == "invalid_eval_id"
        assert data["summary_count"] == 0
