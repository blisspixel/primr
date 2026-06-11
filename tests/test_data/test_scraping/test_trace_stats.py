"""Tests for scrape-trace analytics (doctor --scraper-stats)."""

import json
from pathlib import Path

from primr.data.scraping.trace_stats import (
    THIN_CONTENT_CHARS,
    aggregate_scraper_stats,
    format_scraper_stats,
    percentile,
)


def _write_trace(
    directory: Path,
    name: str,
    entries: list[dict],
    company: str = "AcmeCo",
) -> Path:
    """Write a minimal schema-1.1 trace file."""
    path = directory / name
    header = {
        "schema_version": "1.1",
        "run_id": "run-1",
        "company": company,
        "started_at": "2026-06-11T00:00:00",
    }
    base_entry = {
        "run_id": "run-1",
        "url": "https://acme.example/page",
        "timestamp": "2026-06-11T00:00:01",
        "tier_attempts": [],
        "success_tier": None,
        "blocked": False,
        "block_type": None,
        "blocked_reason": None,
        "http_status": 200,
        "content_type": "text/html",
        "final_url": None,
        "elapsed_total_ms": 100.0,
        "extracted_text_length": None,
        "validation_result": None,
        "access_assessment": None,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for overrides in entries:
            f.write(json.dumps({**base_entry, **overrides}) + "\n")
    return path


class TestPercentile:
    def test_single_value(self):
        assert percentile([42.0], 95) == 42.0

    def test_p95_nearest_rank(self):
        values = [float(v) for v in range(1, 101)]  # 1..100
        assert percentile(values, 95) == 95.0

    def test_bounds(self):
        assert percentile([1.0, 2.0, 3.0], 0) == 1.0
        assert percentile([1.0, 2.0, 3.0], 100) == 3.0


class TestAggregate:
    def test_no_directory_returns_none(self, tmp_path):
        assert aggregate_scraper_stats(tmp_path / "missing") is None

    def test_empty_directory_returns_none(self, tmp_path):
        assert aggregate_scraper_stats(tmp_path) is None

    def test_per_tier_success_and_latency(self, tmp_path):
        _write_trace(
            tmp_path,
            "run1.jsonl",
            [
                {
                    "tier_attempts": [
                        {"tier": "playwright", "success": True, "elapsed_ms": 400.0},
                    ],
                    "success_tier": "playwright",
                    "extracted_text_length": 5000,
                },
                {
                    "tier_attempts": [
                        {"tier": "playwright", "success": False, "elapsed_ms": 900.0},
                        {"tier": "requests", "success": True, "elapsed_ms": 80.0},
                    ],
                    "success_tier": "requests",
                    "extracted_text_length": 3000,
                },
                {
                    "tier_attempts": [
                        {"tier": "playwright", "success": False, "elapsed_ms": 1000.0},
                    ],
                    "success_tier": None,
                },
            ],
        )

        summary = aggregate_scraper_stats(tmp_path)
        assert summary is not None
        assert summary.runs_analyzed == 1
        assert summary.urls_total == 3
        assert summary.urls_succeeded == 2
        assert summary.overall_success_rate == 2 / 3

        by_tier = {t.tier: t for t in summary.tiers}
        assert by_tier["playwright"].attempts == 3
        assert by_tier["playwright"].successes == 1
        assert by_tier["playwright"].success_rate == 1 / 3
        assert by_tier["requests"].attempts == 1
        assert by_tier["requests"].success_rate == 1.0
        assert by_tier["requests"].p95_latency_ms == 80.0
        # Tiers ordered by attempts descending
        assert summary.tiers[0].tier == "playwright"

    def test_content_quality_signals(self, tmp_path):
        _write_trace(
            tmp_path,
            "run1.jsonl",
            [
                {
                    "success_tier": "playwright",
                    "extracted_text_length": 100,  # thin
                    "validation_result": {"valid": False},
                },
                {
                    "success_tier": "playwright",
                    "extracted_text_length": 4000,
                    "validation_result": {"valid": True},
                },
            ],
        )
        summary = aggregate_scraper_stats(tmp_path)
        assert summary is not None
        assert summary.thin_pages == 1
        assert summary.avg_text_length == 2050
        assert summary.content_valid_rate == 0.5
        assert 100 < THIN_CONTENT_CHARS

    def test_unreadable_file_skipped(self, tmp_path):
        (tmp_path / "garbage.jsonl").write_text("not json at all\n", encoding="utf-8")
        _write_trace(
            tmp_path,
            "good.jsonl",
            [
                {
                    "success_tier": "requests",
                    "tier_attempts": [{"tier": "requests", "success": True}],
                }
            ],
        )
        summary = aggregate_scraper_stats(tmp_path)
        assert summary is not None
        assert summary.runs_analyzed == 1

    def test_max_runs_limits_files(self, tmp_path):
        for i in range(5):
            _write_trace(tmp_path, f"run{i}.jsonl", [{"success_tier": "requests"}])
        summary = aggregate_scraper_stats(tmp_path, max_runs=2)
        assert summary is not None
        assert summary.runs_analyzed == 2
        assert summary.urls_total == 2


class TestFormat:
    def test_format_contains_table_and_quality(self, tmp_path):
        _write_trace(
            tmp_path,
            "run1.jsonl",
            [
                {
                    "tier_attempts": [{"tier": "playwright", "success": True, "elapsed_ms": 400.0}],
                    "success_tier": "playwright",
                    "extracted_text_length": 5000,
                    "validation_result": {"valid": True},
                }
            ],
        )
        summary = aggregate_scraper_stats(tmp_path)
        assert summary is not None
        out = format_scraper_stats(summary)
        assert "playwright" in out
        assert "p95 ms" in out
        assert "Overall page success rate: 100%" in out
        assert "Content quality" in out
        assert "validation pass rate: 100%" in out


class TestCLIWiring:
    def test_parser_maps_scraper_stats_flag(self):
        from primr.core.cli import parse_args

        config = parse_args(["doctor", "--scraper-stats"])
        assert config.doctor_scraper_stats is True

    def test_handle_doctor_routes_to_stats(self, monkeypatch):
        from primr.core import cli_doctor
        from primr.core.cli import CLIConfig, Command, _handle_doctor

        called = {}

        def fake_stats() -> int:
            called["stats"] = True
            return 0

        monkeypatch.setattr(cli_doctor, "run_scraper_stats", fake_stats)
        config = CLIConfig(command=Command.DOCTOR, doctor_scraper_stats=True)
        assert _handle_doctor(config) == 0
        assert called.get("stats") is True
