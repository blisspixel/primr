"""Tests for small helpers in deep_research: ConsultingPromptBuilder checks,
DeepResearchOrchestratorResult.word_count, validate_prerequisites, and
_require_genai_dependency."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from primr.ai.deep_research import (
    ConsultingPromptBuilder,
    DeepResearchOrchestrator,
    DeepResearchOrchestratorResult,
)


class TestConsultingPromptBuilderChecks:
    def test_contains_all_chapters_true(self):
        b = ConsultingPromptBuilder()
        # Build a prompt containing all chapters
        prompt = "\n".join(b.CHAPTERS)
        assert b.contains_all_chapters(prompt) is True

    def test_contains_all_chapters_missing_one(self):
        b = ConsultingPromptBuilder()
        partial = "\n".join(b.CHAPTERS[:-1])
        assert b.contains_all_chapters(partial) is False

    def test_contains_consulting_persona_true(self):
        b = ConsultingPromptBuilder()
        assert b.contains_consulting_persona("You are a Senior Strategy Consultant.") is True

    def test_contains_consulting_persona_false(self):
        b = ConsultingPromptBuilder()
        assert b.contains_consulting_persona("you are a poet") is False


class TestOrchestratorResultWordCount:
    def test_word_count_basic(self):
        r = DeepResearchOrchestratorResult(
            company_name="X",
            content="alpha beta gamma delta",
            citations=[],
            duration_seconds=1.0,
            success=True,
        )
        assert r.word_count == 4

    def test_word_count_empty(self):
        r = DeepResearchOrchestratorResult(
            company_name="X",
            content="",
            citations=[],
            duration_seconds=1.0,
            success=False,
        )
        assert r.word_count == 0

    def test_word_count_whitespace_only(self):
        r = DeepResearchOrchestratorResult(
            company_name="X",
            content="   \n\n   ",
            citations=[],
            duration_seconds=1.0,
            success=True,
        )
        # split() with no args splits on any whitespace; empty after split -> 0
        assert r.word_count == 0


@pytest.fixture
def orchestrator(monkeypatch):
    import primr.ai.deep_research as dr

    mock_genai = MagicMock()
    mock_genai.Client.return_value = MagicMock()
    monkeypatch.setattr(dr, "genai", mock_genai)
    monkeypatch.setattr(dr, "_require_genai_dependency", lambda: None)
    monkeypatch.setattr(dr, "_orchestrator", None)
    monkeypatch.setattr(dr, "_client", None)
    return DeepResearchOrchestrator(api_key="fake-key-1234567890")


class TestValidatePrerequisites:
    @pytest.mark.asyncio
    async def test_wraps_preflight_validator(self, orchestrator, monkeypatch):
        # Mock PreflightValidator to return a known result
        validator = MagicMock()
        result_obj = MagicMock()
        result_obj.success = True
        result_obj.errors = []
        result_obj.warnings = ["w1"]
        result_obj.checks = {"k": "v"}
        result_obj.estimated_duration = 60
        result_obj.estimated_cost = 0.5
        validator.validate = AsyncMock(return_value=result_obj)
        monkeypatch.setattr(
            "primr.ai.preflight.PreflightValidator",
            MagicMock(return_value=validator),
        )
        result = await orchestrator.validate_prerequisites(
            company_name="Acme", website_url="https://acme.example", mode="full"
        )
        assert result["success"] is True
        assert result["warnings"] == ["w1"]
        assert result["details"] == {"k": "v"}
        assert result["estimated_duration"] == 60
        assert result["estimated_cost"] == 0.5

    @pytest.mark.asyncio
    async def test_returns_failure_dict_on_validator_fail(self, orchestrator, monkeypatch):
        validator = MagicMock()
        result_obj = MagicMock()
        result_obj.success = False
        result_obj.errors = ["missing key"]
        result_obj.warnings = []
        result_obj.checks = {}
        result_obj.estimated_duration = 0
        result_obj.estimated_cost = 0.0
        validator.validate = AsyncMock(return_value=result_obj)
        monkeypatch.setattr(
            "primr.ai.preflight.PreflightValidator",
            MagicMock(return_value=validator),
        )
        result = await orchestrator.validate_prerequisites(mode="deep")
        assert result["success"] is False
        assert result["errors"] == ["missing key"]


class TestRequireGenaiDependency:
    def test_noop_when_import_succeeded(self, monkeypatch):
        # Force the import-error variable to None — should be a no-op
        import primr.ai.deep_research as dr

        monkeypatch.setattr(dr, "_GENAI_IMPORT_ERROR", None)
        # Should NOT raise
        dr._require_genai_dependency()

    def test_raises_when_fallback_still_in_use(self, monkeypatch):
        import primr.ai.deep_research as dr
        from primr.utils.errors import AIError

        # Simulate "import failed and the fallback class is still the active Client"
        class FakeFallback:
            pass

        fake_genai = MagicMock()
        fake_genai.Client = FakeFallback
        monkeypatch.setattr(dr, "_GENAI_IMPORT_ERROR", ImportError("no google"))
        monkeypatch.setattr(dr, "_FALLBACK_CLIENT_CLASS", FakeFallback)
        monkeypatch.setattr(dr, "genai", fake_genai)
        with pytest.raises(AIError):
            dr._require_genai_dependency()

    def test_passes_when_genai_client_was_injected(self, monkeypatch):
        import primr.ai.deep_research as dr

        class RealClient:
            pass

        class FakeFallback:
            pass

        fake_genai = MagicMock()
        fake_genai.Client = RealClient  # Patched-in real client
        monkeypatch.setattr(dr, "_GENAI_IMPORT_ERROR", ImportError("no google"))
        monkeypatch.setattr(dr, "_FALLBACK_CLIENT_CLASS", FakeFallback)
        monkeypatch.setattr(dr, "genai", fake_genai)
        # Should NOT raise because Client is no longer the fallback class
        dr._require_genai_dependency()
