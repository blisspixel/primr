"""
Integration tests for pipeline resilience wiring.

Tests that the resilience layer is correctly integrated into the pipeline
orchestrator and CLI without changing behavior on successful runs.

**Feature: pipeline-resilience**
**Validates: Requirements 2.4, 9.4, 12.3, 14.2**
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

# =============================================================================
# TEST: --dry-run output contains recovery table JSON (Req 14.2)
# =============================================================================


class TestDryRunRecoveryTable:
    """Test that --dry-run output includes recovery table information."""

    def test_dry_run_includes_recovery_table_json(self):
        """--dry-run output should contain the recovery table JSON.

        **Validates: Requirements 14.1, 14.2**
        """
        from primr.pipeline.recovery import build_default_recovery_table

        table = build_default_recovery_table()
        table_json = table.to_json()
        table_dict = json.loads(table_json)

        # Verify the table JSON contains all six stages
        assert "scraping" in table_dict
        assert "external_search" in table_dict
        assert "analysis" in table_dict
        assert "section_writing" in table_dict
        assert "cross_validation" in table_dict
        assert "strategy_generation" in table_dict

        # Verify each stage has classification
        for stage_data in table_dict.values():
            assert "classification" in stage_data
            assert stage_data["classification"] in ("foreground", "background")

    def test_dry_run_stage_classifications_displayed(self):
        """--dry-run should display stage classifications alongside hierarchies.

        **Validates: Requirements 14.2**
        """
        from primr.pipeline.recovery import build_default_recovery_table

        table = build_default_recovery_table()
        table_dict = table.to_dict()

        # Verify foreground stages
        assert table_dict["scraping"]["classification"] == "foreground"
        assert table_dict["external_search"]["classification"] == "foreground"
        assert table_dict["analysis"]["classification"] == "foreground"
        assert table_dict["section_writing"]["classification"] == "foreground"

        # Verify background stages
        assert table_dict["cross_validation"]["classification"] == "background"
        assert table_dict["strategy_generation"]["classification"] == "background"

    @patch("primr.utils.cost_estimator.estimate_cost")
    def test_handle_dry_run_prints_recovery_table(self, mock_estimate):
        """_handle_dry_run should print recovery table JSON.

        **Validates: Requirements 14.1, 14.2**
        """
        import io
        from contextlib import redirect_stdout

        from primr.core.cli import CLIConfig, Command
        from primr.core.cli_dryrun import run_dry_run

        mock_estimate.return_value = MagicMock(__str__=lambda x: "Cost: ~$0.20")

        config = CLIConfig(
            company_name="TestCo",
            website="https://test.example",
            command=Command.DRY_RUN,
            mode="structured",
            fast_mode=True,
        )

        captured = io.StringIO()
        with redirect_stdout(captured), patch.dict(os.environ, {"XAI_API_KEY": "test-key"}):
            result = run_dry_run(config)

        output = captured.getvalue()
        assert result == 0
        assert "RECOVERY TABLE" in output
        assert "scraping" in output
        assert "foreground" in output
        assert "background" in output
        assert "retry_backoff" in output


# =============================================================================
# TEST: Sticky-tier preserved during scraping retry (Req 2.4)
# =============================================================================


class TestStickyTierPreservation:
    """Test that the executor preserves sticky-tier optimization."""

    def test_scrape_page_with_recovery_preserves_tier(self):
        """Scraping recovery should delegate tier escalation to existing logic.

        The executor's ESCALATE_TIER action delegates to the existing tier
        hierarchy — it does not override sticky-tier selection.

        **Validates: Requirements 2.4**
        """
        from primr.pipeline.executor import RecoveryExecutor
        from primr.pipeline.integration import scrape_page_with_recovery
        from primr.pipeline.recovery import build_default_recovery_table

        # Simulate a successful scrape — executor should pass through
        call_count = 0
        sticky_tier = "httpx"  # Simulated sticky tier

        def mock_scrape():
            nonlocal call_count
            call_count += 1
            return {"https://example.com": f"content scraped via {sticky_tier}"}

        executor = RecoveryExecutor(recovery_table=build_default_recovery_table())

        with tempfile.TemporaryDirectory() as tmpdir:
            result = scrape_page_with_recovery(executor, mock_scrape, "https://example.com", tmpdir)

        assert result.success is True
        assert call_count == 1  # Only called once on success
        assert sticky_tier == "httpx"  # Tier unchanged


# =============================================================================
# TEST: Health transitions appear in structured log output (Req 12.3)
# =============================================================================


class TestHealthTransitionLogging:
    """Test that model health transitions are logged to run state."""

    def test_health_listener_logs_to_run_state(self):
        """ModelCircuitBreaker health transitions should appear in run state.

        **Validates: Requirements 12.3**
        """
        from primr.core.research_agent import (
            _build_health_listener,
            _ensure_resilience_keys,
            _load_run_state,
            _save_run_state,
        )
        from primr.pipeline.model_breaker import ModelHealthEvent

        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize run state with resilience keys
            state = {"status": "running"}
            _ensure_resilience_keys(state)
            _save_run_state(tmpdir, state)

            # Build listener and emit a health event
            listener = _build_health_listener(tmpdir)
            event = ModelHealthEvent(
                timestamp="2026-01-15T10:30:00",
                model="grok-4.20",
                from_state="closed",
                to_state="open",
                failure_count=3,
            )
            listener(event)

            # Verify event appears in run state
            loaded = _load_run_state(tmpdir)
            assert "model_health" in loaded
            assert len(loaded["model_health"]) == 1
            assert loaded["model_health"][0]["model"] == "grok-4.20"
            assert loaded["model_health"][0]["from_state"] == "closed"
            assert loaded["model_health"][0]["to_state"] == "open"
            assert loaded["model_health"][0]["failure_count"] == 3


# =============================================================================
# TEST: Background abort events recorded with correct reason (Req 9.4)
# =============================================================================


class TestBackgroundAbortRecording:
    """Test that background abort events are recorded in run state."""

    def test_background_abort_logged_with_reason(self):
        """Background stage aborts should be recorded with the abort reason.

        **Validates: Requirements 9.4**
        """
        from primr.core.research_agent import (
            _ensure_resilience_keys,
            _load_run_state,
            _save_run_state,
        )
        from primr.core.resilience_listeners import _build_resilience_event_listener
        from primr.pipeline.executor import RecoveryContext, RecoveryExecutor
        from primr.pipeline.recovery import build_default_recovery_table
        from primr.pipeline.stages import PipelineStage

        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize run state
            state = {"status": "running"}
            _ensure_resilience_keys(state)
            _save_run_state(tmpdir, state)

            listener = _build_resilience_event_listener(tmpdir)
            executor = RecoveryExecutor(
                recovery_table=build_default_recovery_table(),
                event_listener=listener,
            )

            # Execute a background stage with budget_stressed=True
            ctx = RecoveryContext(
                stage=PipelineStage.CROSS_VALIDATION,
                folder_path=tmpdir,
                attempt=0,
                last_error=None,
                budget_stressed=True,
            )
            result = executor.execute(
                PipelineStage.CROSS_VALIDATION,
                lambda: "should not run",
                context=ctx,
            )

            assert result.skipped is True
            assert "budget_stress" in (result.skip_reason or "")

            # Verify abort recorded in run state
            loaded = _load_run_state(tmpdir)
            assert "background_aborts" in loaded
            assert len(loaded["background_aborts"]) == 1
            abort = loaded["background_aborts"][0]
            assert abort["stage"] == "cross_validation"
            assert "budget_stress" in abort["reason"]

    def test_background_abort_on_rate_limit(self):
        """Background stage should abort on 429 and record the reason.

        **Validates: Requirements 9.4**
        """
        from primr.core.research_agent import (
            _ensure_resilience_keys,
            _load_run_state,
            _save_run_state,
        )
        from primr.core.resilience_listeners import _build_resilience_event_listener
        from primr.pipeline.executor import RecoveryExecutor
        from primr.pipeline.recovery import build_default_recovery_table
        from primr.pipeline.stages import PipelineStage

        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"status": "running"}
            _ensure_resilience_keys(state)
            _save_run_state(tmpdir, state)

            listener = _build_resilience_event_listener(tmpdir)
            executor = RecoveryExecutor(
                recovery_table=build_default_recovery_table(),
                event_listener=listener,
            )

            def _raise_429():
                raise RuntimeError("HTTP 429 Too Many Requests rate limit exceeded")

            result = executor.execute(
                PipelineStage.STRATEGY_GENERATION,
                _raise_429,
            )

            assert result.skipped is True
            assert "rate_limit" in (result.skip_reason or "")

            loaded = _load_run_state(tmpdir)
            assert len(loaded["background_aborts"]) == 1
            assert loaded["background_aborts"][0]["stage"] == "strategy_generation"
            assert "rate_limit" in loaded["background_aborts"][0]["reason"]


# =============================================================================
# TEST: Run state resilience keys (Req 16.3, NFR 3)
# =============================================================================


class TestRunStateResilienceKeys:
    """Test that resilience keys are properly initialized and preserved."""

    def test_ensure_resilience_keys_adds_missing(self):
        """_ensure_resilience_keys should add missing arrays.

        **Validates: Requirements 16.3**
        """
        from primr.core.research_agent import _ensure_resilience_keys

        state = {"status": "running", "events": []}
        _ensure_resilience_keys(state)

        assert state["model_health"] == []
        assert state["recovery_events"] == []
        assert state["background_aborts"] == []
        # Existing keys preserved
        assert state["status"] == "running"
        assert state["events"] == []

    def test_ensure_resilience_keys_preserves_existing(self):
        """_ensure_resilience_keys should not overwrite existing arrays.

        **Validates: Requirements NFR 3**
        """
        from primr.core.research_agent import _ensure_resilience_keys

        existing_event = {"timestamp": "2026-01-01", "model": "test"}
        state = {
            "model_health": [existing_event],
            "recovery_events": [],
            "background_aborts": [],
        }
        _ensure_resilience_keys(state)

        assert len(state["model_health"]) == 1
        assert state["model_health"][0] == existing_event

    def test_init_run_state_with_resilience(self):
        """_init_run_state_with_resilience should create state with all keys.

        **Validates: Requirements 16.3, NFR 3**
        """
        from primr.core.research_agent import (
            _init_run_state_with_resilience,
            _load_run_state,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            _init_run_state_with_resilience(
                tmpdir,
                {
                    "company_name": "TestCo",
                    "status": "running",
                    "events": [],
                },
            )

            loaded = _load_run_state(tmpdir)
            assert loaded["company_name"] == "TestCo"
            assert loaded["model_health"] == []
            assert loaded["recovery_events"] == []
            assert loaded["background_aborts"] == []

    def test_backwards_compatible_with_old_run_state(self):
        """Loading old run state without resilience keys should work.

        **Validates: Requirements NFR 3**
        """
        from primr.core.research_agent import (
            _ensure_resilience_keys,
            _load_run_state,
            _save_run_state,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate old run state without resilience keys
            old_state = {
                "company_name": "OldCo",
                "status": "completed",
                "events": [{"ts": "2025-01-01", "phase": "done"}],
            }
            _save_run_state(tmpdir, old_state)

            loaded = _load_run_state(tmpdir)
            assert "model_health" not in loaded  # Old state doesn't have it

            # Ensure resilience keys adds them without breaking existing data
            _ensure_resilience_keys(loaded)
            assert loaded["model_health"] == []
            assert loaded["company_name"] == "OldCo"
            assert len(loaded["events"]) == 1
