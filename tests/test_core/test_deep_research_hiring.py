"""Wiring tests: hiring signals ride into the Deep Research paths (roadmap #3).

``perform_deep_research`` gathers the fenced hiring block before the
orchestrator call and threads it through ``ResearchConfig.supplemental_context``;
strategy-only runs skip the gather entirely.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def deep_seams(monkeypatch, tmp_path):
    from primr.core import research_agent as ra

    captured: dict = {}
    hiring = MagicMock(return_value="<<<UNTRUSTED_HIRING_SIGNALS_BEGIN#x>>> block")
    monkeypatch.setattr(ra, "collect_fenced_hiring_block", hiring)

    class FakeOrchestrator:
        async def research(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop-after-capture")

    monkeypatch.setattr(ra, "get_orchestrator", lambda: FakeOrchestrator())
    monkeypatch.setattr(
        "primr.ai.deep_research.cleanup_orphaned_resources",
        lambda: {"caches_deleted": 0, "stores_deleted": 0},
    )
    fake_settings = SimpleNamespace(api=SimpleNamespace(gemini_key="fake-key-for-preflight"))
    monkeypatch.setattr("primr.config.settings.get_settings", lambda: fake_settings)

    return {"captured": captured, "hiring": hiring, "tmp": tmp_path, "ra": ra}


class TestPremiumHiringWiring:
    def test_fenced_hiring_block_reaches_research_config(self, deep_seams):
        result = deep_seams["ra"].perform_deep_research(
            "Acme Corp",
            "https://acme.example",
            "complete",
            time.time(),
            folder_path=str(deep_seams["tmp"]),
        )

        assert result is None  # the sentinel stopped the run after capture
        deep_seams["hiring"].assert_called_once()
        config = deep_seams["captured"]["config"]
        assert config.supplemental_context == "<<<UNTRUSTED_HIRING_SIGNALS_BEGIN#x>>> block"

    def test_empty_hiring_block_threads_none(self, deep_seams):
        deep_seams["hiring"].return_value = ""
        deep_seams["ra"].perform_deep_research(
            "Acme Corp",
            "https://acme.example",
            "deep-research",
            time.time(),
            folder_path=str(deep_seams["tmp"]),
        )
        assert deep_seams["captured"]["config"].supplemental_context is None

    def test_strategy_only_skips_hiring_gather(self, deep_seams):
        deep_seams["ra"].perform_deep_research(
            "Acme Corp",
            "https://acme.example",
            "complete",
            time.time(),
            strategy_only=True,
            folder_path=str(deep_seams["tmp"]),
        )
        deep_seams["hiring"].assert_not_called()

    def test_hybrid_mode_skips_hiring_gather(self, deep_seams):
        """The legacy parallel hybrid path never consumes stage-1 context;
        gathering would spend the stage and drop the block."""
        deep_seams["ra"].perform_deep_research(
            "Acme Corp",
            "https://acme.example",
            "hybrid",
            time.time(),
            folder_path=str(deep_seams["tmp"]),
        )
        deep_seams["hiring"].assert_not_called()
