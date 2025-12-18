"""
Tests for the usage tracker module.

Verifies usage tracking and cost calculation.
"""

import pytest
import tempfile
import json
from pathlib import Path

from primr.utils.usage_tracker import (
    UsageTracker,
    UsageRecord,
    SessionUsage,
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
            search_queries=10,
            duration_seconds=600.0,
        )
        
        assert record.mode == "structured"
        assert record.company == "TestCo"
        assert record.input_tokens == 100_000
        assert record.output_tokens == 50_000
        
        # Verify cost calculation
        # Input: 100k tokens * $2/1M = $0.20
        # Output: 50k tokens * $12/1M = $0.60
        assert abs(record.input_cost - 0.20) < 0.001
        assert abs(record.output_cost - 0.60) < 0.001
        assert abs(record.total_cost - 0.80) < 0.001

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
            
            # Add multiple records
            for i in range(3):
                tracker.record_usage(
                    mode="structured",
                    company=f"Co{i}",
                    input_tokens=100_000 + i * 10_000,
                    output_tokens=50_000 + i * 5_000,
                )
            tracker.save()
            
            # Reload to get history
            tracker2 = UsageTracker(storage_path=storage_path)
            avg = tracker2.get_average_by_mode("structured")
            
            assert avg is not None
            assert avg["sample_size"] == 3
            assert avg["avg_input_tokens"] > 0

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
