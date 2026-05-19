"""Unit tests for the in-place dataclasses in primr.ai.deep_research.

These cover ResearchStatus / ResearchProgress / ThinkingLog /
ResearchResult — small data carriers that were previously untested.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from primr.ai.deep_research import (
    ResearchProgress,
    ResearchResult,
    ResearchStatus,
    ThinkingLog,
)

# ---------------------------------------------------------------------------
# ResearchStatus
# ---------------------------------------------------------------------------


class TestResearchStatus:
    def test_known_members(self):
        assert ResearchStatus.PENDING.value == "pending"
        assert ResearchStatus.IN_PROGRESS.value == "in_progress"
        assert ResearchStatus.COMPLETED.value == "completed"
        assert ResearchStatus.FAILED.value == "failed"

    def test_membership(self):
        # Sanity: the four canonical states are all present.
        assert {m.value for m in ResearchStatus} == {
            "pending",
            "in_progress",
            "completed",
            "failed",
        }


# ---------------------------------------------------------------------------
# ResearchProgress
# ---------------------------------------------------------------------------


class TestResearchProgress:
    def test_minimal_construction(self):
        p = ResearchProgress(status=ResearchStatus.PENDING)
        assert p.status == ResearchStatus.PENDING
        assert p.message == ""
        assert p.thought is None
        assert p.partial_result is None
        assert isinstance(p.timestamp, datetime)

    def test_full_construction(self):
        p = ResearchProgress(
            status=ResearchStatus.IN_PROGRESS,
            message="halfway",
            thought="considering competitors",
            partial_result="draft outline",
        )
        assert p.message == "halfway"
        assert p.thought == "considering competitors"
        assert p.partial_result == "draft outline"


# ---------------------------------------------------------------------------
# ThinkingLog
# ---------------------------------------------------------------------------


class TestThinkingLog:
    def test_minimal_construction(self):
        log = ThinkingLog(interaction_id="iid-1", company_name="Acme")
        assert log.interaction_id == "iid-1"
        assert log.company_name == "Acme"
        assert log.thoughts == []
        assert log.search_queries == []
        assert log.sources_visited == []
        assert log.end_time is None

    def test_add_thought_includes_timestamp_prefix(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        log.add_thought("considering pricing")
        assert len(log.thoughts) == 1
        # Format: [HH:MM:SS] thought
        assert log.thoughts[0].endswith("considering pricing")
        assert log.thoughts[0].startswith("[")
        assert "] " in log.thoughts[0]

    def test_add_search_appends(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        log.add_search("revenue 2024")
        log.add_search("ceo background")
        assert log.search_queries == ["revenue 2024", "ceo background"]

    def test_add_source_deduplicates(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        log.add_source("https://example.com/a")
        log.add_source("https://example.com/a")  # duplicate
        log.add_source("https://example.com/b")
        assert log.sources_visited == ["https://example.com/a", "https://example.com/b"]

    def test_to_markdown_minimal_log(self):
        log = ThinkingLog(interaction_id="iid-123", company_name="Acme Corp")
        md = log.to_markdown()
        assert "# Deep Research Thinking Log" in md
        assert "Acme Corp" in md
        assert "iid-123" in md
        assert "Started:" in md

    def test_to_markdown_with_thoughts_and_searches(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        log.add_thought("first thought")
        log.add_search("query one")
        log.add_search("query two")
        log.add_source("https://example.com/a")
        md = log.to_markdown()
        assert "first thought" in md
        assert "## Search Queries Executed" in md
        assert "1. query one" in md
        assert "2. query two" in md
        assert "## Sources Analyzed" in md
        assert "- https://example.com/a" in md

    def test_to_markdown_skips_empty_sections(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        md = log.to_markdown()
        # When no searches/sources are logged, those headings should NOT appear.
        assert "Search Queries Executed" not in md
        assert "Sources Analyzed" not in md

    def test_to_markdown_includes_duration_when_end_time_set(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        log.end_time = log.start_time + timedelta(seconds=120)
        md = log.to_markdown()
        assert "**Duration:** 120 seconds" in md

    def test_to_markdown_omits_duration_when_end_time_missing(self):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        md = log.to_markdown()
        assert "Duration:" not in md


# ---------------------------------------------------------------------------
# ResearchResult
# ---------------------------------------------------------------------------


class TestResearchResult:
    def test_minimal_construction_defaults(self):
        r = ResearchResult(content="hello")
        assert r.content == "hello"
        assert r.citations == []
        assert r.interaction_id == ""
        assert r.duration_seconds == 0.0
        assert r.status == ResearchStatus.COMPLETED
        assert r.error is None
        assert r.thinking_log is None
        assert r.search_queries_count == 0

    def test_success_true_when_completed_with_content(self):
        r = ResearchResult(content="hello", status=ResearchStatus.COMPLETED)
        assert r.success is True

    def test_success_false_when_failed(self):
        r = ResearchResult(content="hello", status=ResearchStatus.FAILED)
        assert r.success is False

    def test_success_false_when_completed_but_empty(self):
        r = ResearchResult(content="", status=ResearchStatus.COMPLETED)
        assert r.success is False

    @pytest.mark.parametrize(
        "status",
        [ResearchStatus.PENDING, ResearchStatus.IN_PROGRESS, ResearchStatus.FAILED],
    )
    def test_success_false_for_non_completed_statuses(self, status):
        r = ResearchResult(content="hello", status=status)
        assert r.success is False

    def test_save_thinking_log_writes_markdown(self, tmp_path):
        log = ThinkingLog(interaction_id="iid", company_name="Acme")
        log.add_thought("a thought")
        r = ResearchResult(content="x", thinking_log=log)

        out = tmp_path / "log.md"
        r.save_thinking_log(str(out))
        assert out.exists()
        body = out.read_text(encoding="utf-8")
        assert "a thought" in body
        assert "# Deep Research Thinking Log" in body

    def test_save_thinking_log_no_op_when_log_missing(self, tmp_path):
        r = ResearchResult(content="x")  # no thinking_log
        out = tmp_path / "log.md"
        r.save_thinking_log(str(out))
        # File should NOT have been created when there's nothing to write.
        assert not out.exists()

    def test_citations_carried(self):
        r = ResearchResult(
            content="x",
            citations=[
                {"number": "1", "url": "https://example.com/a"},
                {"number": "2", "url": "https://example.com/b"},
            ],
        )
        assert len(r.citations) == 2
        assert r.citations[0]["url"] == "https://example.com/a"
