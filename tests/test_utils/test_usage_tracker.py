"""
Tests for the usage tracker module.

Verifies usage tracking and cost calculation.
"""

import tempfile
from pathlib import Path

from primr.utils.usage_tracker import (
    SessionUsage,
    UsageRecord,
    UsageTracker,
    get_usage_tracker,
    reset_usage_tracker,
)


class TestUsageRecord:
    """Tests for UsageRecord dataclass."""

    def test_create_usage_record(self):
        """Create a usage record with calculated costs."""
        record = UsageRecord.create(
            mode="structured",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=50_000,
            search_queries=0,  # Zero queries so search_cost is deterministic
            duration_seconds=600.0,
        )

        assert record.mode == "structured"
        assert record.company == "TestCo"
        assert record.input_tokens == 100_000
        assert record.output_tokens == 50_000

        # Verify cost calculation uses active Pro model pricing (conservative for tiered)
        from primr.config.models import PrimrModels

        active_pro = PrimrModels.get_active_pro_model()
        if active_pro.has_tiered_pricing:
            inp_price = active_pro.cost_per_1m_input_tokens_high
            out_price = active_pro.cost_per_1m_output_tokens_high
        else:
            inp_price = active_pro.cost_per_1m_input_tokens
            out_price = active_pro.cost_per_1m_output_tokens
        expected_input = (100_000 / 1_000_000) * inp_price
        expected_output = (50_000 / 1_000_000) * out_price
        assert abs(record.input_cost - expected_input) < 0.001
        assert abs(record.output_cost - expected_output) < 0.001
        assert abs(record.total_cost - (expected_input + expected_output)) < 0.001

    def test_create_usage_record_with_search(self):
        """Search queries incur cost at $0.035/query."""
        record = UsageRecord.create(
            mode="structured",
            company="TestCo",
            input_tokens=0,
            output_tokens=0,
            search_queries=10,
        )
        # 10 queries * $0.035 = $0.35
        assert abs(record.search_cost - 0.35) < 0.001

    def test_record_has_timestamp(self):
        """Record includes timestamp."""
        record = UsageRecord.create(
            mode="deep-research",
            company="TestCo",
            input_tokens=1000,
            output_tokens=500,
        )

        assert record.timestamp is not None
        assert len(record.timestamp) > 0


class TestSessionUsage:
    """Tests for SessionUsage tracking."""

    def test_empty_session(self):
        """Empty session has zero totals."""
        session = SessionUsage()

        assert len(session.records) == 0
        assert session.total_input_tokens == 0
        assert session.total_output_tokens == 0
        assert session.total_cost == 0.0

    def test_add_record_updates_totals(self):
        """Adding records updates session totals."""
        session = SessionUsage()

        record1 = UsageRecord.create(
            mode="structured",
            company="Co1",
            input_tokens=100_000,
            output_tokens=50_000,
        )
        session.add(record1)

        assert session.total_input_tokens == 100_000
        assert session.total_output_tokens == 50_000
        assert len(session.records) == 1

        record2 = UsageRecord.create(
            mode="structured",
            company="Co2",
            input_tokens=50_000,
            output_tokens=25_000,
        )
        session.add(record2)

        assert session.total_input_tokens == 150_000
        assert session.total_output_tokens == 75_000
        assert len(session.records) == 2


class TestUsageTracker:
    """Tests for UsageTracker class."""

    def test_tracker_initialization(self):
        """Tracker initializes with empty session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            assert len(tracker.session.records) == 0
            assert tracker.get_session_cost() == 0.0

    def test_record_usage(self):
        """Record usage adds to session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            tracker.record_usage(
                mode="structured",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
            )

            assert len(tracker.session.records) == 1
            assert tracker.session.total_input_tokens == 100_000
            assert tracker.get_session_cost() > 0

    def test_save_and_load_history(self):
        """Save and load usage history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"

            # Create tracker and record usage
            tracker1 = UsageTracker(storage_path=storage_path)
            tracker1.record_usage(
                mode="structured",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
            )
            tracker1.save()

            # Create new tracker and verify history loaded
            tracker2 = UsageTracker(storage_path=storage_path)
            assert len(tracker2.history) == 1
            assert tracker2.history[0]["company"] == "TestCo"

    def test_get_session_summary(self):
        """Get session summary string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            tracker.record_usage(
                mode="structured",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
            )

            summary = tracker.get_session_summary()

            assert "100,000" in summary
            assert "50,000" in summary
            assert "$" in summary

    def test_get_average_by_mode(self):
        """Get average usage by mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            # Add multiple records with search queries
            for i in range(3):
                tracker.record_usage(
                    mode="structured",
                    company=f"Co{i}",
                    input_tokens=100_000 + i * 10_000,
                    output_tokens=50_000 + i * 5_000,
                    search_queries=10 + i * 5,  # 10, 15, 20 -> avg 15
                    cached_input_tokens=20_000 + i * 10_000,
                )
            tracker.save()

            # Reload to get history
            tracker2 = UsageTracker(storage_path=storage_path)
            avg = tracker2.get_average_by_mode("structured")

            assert avg is not None
            assert avg["sample_size"] == 3
            assert avg["avg_input_tokens"] > 0
            assert avg["avg_search_queries"] == 15  # (10+15+20)/3
            assert avg["avg_cached_input_tokens"] == 30_000  # (20k+30k+40k)/3

    def test_get_average_no_data(self):
        """Get average returns None when no data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            avg = tracker.get_average_by_mode("structured")
            assert avg is None


class TestSingletonAccess:
    """Tests for singleton pattern."""

    def test_get_usage_tracker_returns_same_instance(self):
        """get_usage_tracker returns same instance."""
        reset_usage_tracker()

        tracker1 = get_usage_tracker()
        tracker2 = get_usage_tracker()

        assert tracker1 is tracker2

        reset_usage_tracker()

    def test_reset_usage_tracker(self):
        """reset_usage_tracker clears instance."""
        tracker1 = get_usage_tracker()
        reset_usage_tracker()
        tracker2 = get_usage_tracker()

        assert tracker1 is not tracker2

        reset_usage_tracker()


class TestPipelineCostPassthrough:
    """Tests for pre-calculated cost passthrough."""

    def test_create_with_pipeline_cost(self):
        """When pipeline_cost is provided, use it instead of recalculating."""
        record = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=50_000,
            pipeline_cost=0.25,
        )
        # Total should be pipeline_cost (no search, no DR)
        assert abs(record.total_cost - 0.25) < 0.001
        assert record.deep_research_cost == 0.0

    def test_create_with_pipeline_cost_and_search(self):
        """pipeline_cost + search cost combined."""
        record = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=50_000,
            search_queries=10,
            pipeline_cost=0.25,
        )
        # $0.25 + 10 * $0.035 = $0.60
        assert abs(record.total_cost - 0.60) < 0.001

    def test_create_with_deep_research_cost(self):
        """deep_research_cost included in total."""
        record = UsageRecord.create(
            mode="complete",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=50_000,
            pipeline_cost=0.50,
            deep_research_cost=2.50,
        )
        # $0.50 + $2.50 = $3.00
        assert abs(record.total_cost - 3.00) < 0.001
        assert abs(record.deep_research_cost - 2.50) < 0.001

    def test_create_with_all_cost_components(self):
        """pipeline_cost + search + DR all combined."""
        record = UsageRecord.create(
            mode="complete",
            company="TestCo",
            input_tokens=200_000,
            output_tokens=100_000,
            search_queries=20,
            pipeline_cost=0.80,
            deep_research_cost=5.00,
        )
        # $0.80 + 20*$0.035 + $5.00 = $6.50
        assert abs(record.total_cost - 6.50) < 0.001

    def test_create_without_pipeline_cost_backward_compat(self):
        """Without pipeline_cost, falls back to token-based pricing."""
        record = UsageRecord.create(
            mode="structured",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=50_000,
        )
        # Should still work and produce a positive cost
        assert record.total_cost > 0
        assert record.input_cost > 0
        assert record.output_cost > 0

    def test_create_with_pipeline_cost_zeroes_input_output_cost(self):
        """When pipeline_cost provided, input_cost and output_cost are 0."""
        record = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=50_000,
            pipeline_cost=0.25,
        )
        assert record.input_cost == 0.0
        assert record.output_cost == 0.0

    def test_deep_research_cost_in_fallback_path(self):
        """DR cost included even when using token-based pricing."""
        record = UsageRecord.create(
            mode="complete",
            company="TestCo",
            input_tokens=0,
            output_tokens=0,
            deep_research_cost=2.50,
        )
        assert abs(record.total_cost - 2.50) < 0.001
        assert abs(record.deep_research_cost - 2.50) < 0.001

    def test_record_usage_with_pipeline_cost(self):
        """record_usage passes pipeline_cost through to session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="fast",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.25,
            )
            assert abs(tracker.get_session_cost() - 0.25) < 0.001

    def test_record_usage_with_deep_research_cost(self):
        """record_usage passes deep_research_cost through."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="complete",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.50,
                deep_research_cost=5.00,
            )
            assert abs(tracker.get_session_cost() - 5.50) < 0.001

    def test_save_and_load_with_deep_research_cost(self):
        """deep_research_cost persists through save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"

            tracker1 = UsageTracker(storage_path=storage_path)
            tracker1.record_usage(
                mode="complete",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.50,
                deep_research_cost=2.50,
            )
            tracker1.save()

            tracker2 = UsageTracker(storage_path=storage_path)
            assert len(tracker2.history) == 1
            assert abs(tracker2.history[0]["deep_research_cost"] - 2.50) < 0.001
            assert abs(tracker2.history[0]["total_cost"] - 3.00) < 0.001


class TestDisplayUsageHistory:
    """Tests for display_usage_history method."""

    def test_display_empty_history(self):
        """Display message when no history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            output = tracker.display_usage_history()

            assert "No usage history" in output

    def test_display_with_history(self):
        """Display formatted history with records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            # Add some records
            tracker.record_usage(
                mode="structured",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                duration_seconds=600.0,
            )
            tracker.record_usage(
                mode="complete",
                company="AnotherCo",
                input_tokens=200_000,
                output_tokens=100_000,
                duration_seconds=1200.0,
            )
            tracker.save()

            # Reload to populate history
            tracker2 = UsageTracker(storage_path=storage_path)
            output = tracker2.display_usage_history()

            assert "USAGE HISTORY SUMMARY" in output
            assert "Total Records: 2" in output
            assert "structured" in output
            assert "complete" in output
            assert "TestCo" in output
            assert "AnotherCo" in output

    def test_display_shows_mode_breakdown(self):
        """Display shows per-mode statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            # Add multiple records for same mode
            for i in range(3):
                tracker.record_usage(
                    mode="structured",
                    company=f"Co{i}",
                    input_tokens=100_000,
                    output_tokens=50_000,
                    duration_seconds=600.0,
                )
            tracker.save()

            tracker2 = UsageTracker(storage_path=storage_path)
            output = tracker2.display_usage_history()

            assert "By Mode" in output  # Header contains "By Mode (actual averages):"
            assert "Runs: 3" in output
            assert "Avg Cost:" in output

    def test_display_shows_dr_cost_breakdown(self):
        """Display shows DR cost breakdown when present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)

            tracker.record_usage(
                mode="complete",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.50,
                deep_research_cost=5.00,
            )
            tracker.save()

            tracker2 = UsageTracker(storage_path=storage_path)
            output = tracker2.display_usage_history()

            assert "DR cost:" in output
            assert "$5.00" in output

    def test_display_shows_observed_modes_including_fast(self):
        """Fast-mode runs appear in the By Mode breakdown (not a fixed mode list)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="fast",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.79,
            )
            tracker.save()

            output = UsageTracker(storage_path=storage_path).display_usage_history()

            assert "fast:" in output
            assert "Total Cost:" in output

    def test_display_shows_per_company_history(self):
        """Per-company section lists companies with run counts and spend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="fast",
                company="AcmeCo",
                input_tokens=1000,
                output_tokens=500,
                pipeline_cost=2.00,
            )
            tracker.record_usage(
                mode="fast",
                company="AcmeCo",
                input_tokens=1000,
                output_tokens=500,
                pipeline_cost=1.00,
            )
            tracker.record_usage(
                mode="fast",
                company="BetaCo",
                input_tokens=1000,
                output_tokens=500,
                pipeline_cost=0.50,
            )
            tracker.save()

            output = UsageTracker(storage_path=storage_path).display_usage_history()

            assert "By Company" in output
            assert "AcmeCo" in output
            assert "2 run(s)" in output
            assert "BetaCo" in output

    def test_display_shows_cache_hit_rate(self):
        """Cache hit rate appears in totals and recent runs when cached tokens exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="fast",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.79,
                cached_input_tokens=40_000,
            )
            tracker.save()

            output = UsageTracker(storage_path=storage_path).display_usage_history()

            assert "Cached Input:   40,000" in output
            assert "(40% cache hit rate)" in output
            assert "40% cached" in output  # recent-runs line

    def test_display_omits_cache_line_when_no_cached_tokens(self):
        """No cache noise for histories that predate cached-token tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="fast",
                company="TestCo",
                input_tokens=1000,
                output_tokens=500,
                pipeline_cost=0.10,
            )
            tracker.save()

            output = UsageTracker(storage_path=storage_path).display_usage_history()

            assert "Cached Input" not in output
            assert "cached" not in output


class TestCachedInputTokens:
    """Cached-token plumbing through UsageRecord and record_usage."""

    def test_record_persists_cached_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            tracker = UsageTracker(storage_path=storage_path)
            tracker.record_usage(
                mode="fast",
                company="TestCo",
                input_tokens=100_000,
                output_tokens=50_000,
                pipeline_cost=0.79,
                cached_input_tokens=35_000,
            )
            tracker.save()

            tracker2 = UsageTracker(storage_path=storage_path)
            assert tracker2.history[0]["cached_input_tokens"] == 35_000

    def test_cache_hit_rate_property(self):
        record = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=100_000,
            output_tokens=0,
            pipeline_cost=0.5,
            cached_input_tokens=25_000,
        )
        assert abs(record.cache_hit_rate - 0.25) < 1e-9

    def test_cache_hit_rate_zero_input_tokens(self):
        record = UsageRecord.create(
            mode="fast", company="TestCo", input_tokens=0, output_tokens=0, pipeline_cost=0.0
        )
        assert record.cache_hit_rate == 0.0

    def test_cached_tokens_clamped_to_input_tokens(self):
        """Defensive clamp: cached can never exceed input (and never negative)."""
        record = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=1_000,
            output_tokens=0,
            pipeline_cost=0.1,
            cached_input_tokens=5_000,
        )
        assert record.cached_input_tokens == 1_000
        assert record.cache_hit_rate == 1.0

        negative = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=1_000,
            output_tokens=0,
            pipeline_cost=0.1,
            cached_input_tokens=-7,
        )
        assert negative.cached_input_tokens == 0

    def test_default_is_zero_for_backward_compat(self):
        record = UsageRecord.create(
            mode="fast",
            company="TestCo",
            input_tokens=1_000,
            output_tokens=500,
            pipeline_cost=0.1,
        )
        assert record.cached_input_tokens == 0

    def test_token_pricing_fallback_uses_cached_input_discount(self, monkeypatch):
        from primr.config.settings import reset_settings

        monkeypatch.setenv("AI_REASONING_MODEL", "gemini-3.5-flash")
        reset_settings()
        try:
            uncached = UsageRecord.create(
                mode="structured",
                company="TestCo",
                input_tokens=200_000,
                output_tokens=10_000,
            )
            cached = UsageRecord.create(
                mode="structured",
                company="TestCo",
                input_tokens=200_000,
                output_tokens=10_000,
                cached_input_tokens=100_000,
            )
        finally:
            monkeypatch.delenv("AI_REASONING_MODEL", raising=False)
            reset_settings()

        assert cached.total_cost < uncached.total_cost
        assert cached.input_cost < uncached.input_cost

    def test_old_history_records_without_cached_field_display_fine(self):
        """Old-schema persisted records (no cached_input_tokens key) don't crash display."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "usage.json"
            old_record = {
                "timestamp": "2026-01-01T00:00:00",
                "mode": "fast",
                "company": "OldCo",
                "input_tokens": 1000,
                "output_tokens": 500,
                "search_queries": 0,
                "duration_seconds": 60.0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "search_cost": 0.0,
                "total_cost": 0.10,
            }
            storage_path.write_text(json.dumps([old_record]), encoding="utf-8")

            output = UsageTracker(storage_path=storage_path).display_usage_history()

            assert "OldCo" in output
            assert "Cached Input" not in output
