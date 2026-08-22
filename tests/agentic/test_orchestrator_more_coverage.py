"""
Additional coverage for ResearchOrchestrator.

Exercises the interactive helpers (_request_user_input, _handle_stage_transition,
_handle_error_recovery), the hook-driven stage execution (BLOCK path, pre/post
hooks), fail_fast vs. continue-on-failure behavior, partial-failure hypothesis
accumulation, the verification stage, memory load/save error handling, and the
unexpected-error -> OrchestratorError catch path.

All subagents are replaced with deterministic fakes (no scraping/LLM/network).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import primr.agentic.orchestrator as orch_mod
from primr.agentic.errors import OrchestratorError
from primr.agentic.hooks import (
    Hook,
    HookContext,
    HookResponse,
    HookResult,
    HookSystem,
    HookType,
)
from primr.agentic.models import ConfidenceLevel, Hypothesis
from primr.agentic.orchestrator import (
    OrchestratorConfig,
    OrchestratorState,
    ResearchOrchestrator,
)
from primr.agentic.subagents import SubagentResult, SubagentStatus

# =============================================================================
# Fake subagents
# =============================================================================


class _Fake:
    name = "Fake"

    def __init__(self, context, *args, **kwargs):
        self._context = context
        self.company_name = context.company_name
        self.company_url = context.company_url
        self.working_dir = context.working_dir


class _FakeScraper(_Fake):
    name = "ScraperSubagent"

    async def execute(self):
        corpus = self.working_dir / "corpus.txt"
        corpus.write_text("Acme builds cloud services.", encoding="utf-8")
        return SubagentResult(
            status=SubagentStatus.COMPLETED,
            data=SimpleNamespace(corpus_path=corpus),
        )


class _FakeAnalyst(_Fake):
    name = "AnalystSubagent"

    async def execute(self):
        insights = self.working_dir / "insights.txt"
        insights.write_text("- Uses cloud", encoding="utf-8")
        hyp = Hypothesis(id="h_1", claim="Uses cloud", confidence=ConfidenceLevel.UNTESTED)
        return SubagentResult(
            status=SubagentStatus.COMPLETED,
            data=SimpleNamespace(insights_path=insights),
            hypotheses=[hyp],
        )


class _FakeWriter(_Fake):
    name = "WriterSubagent"

    async def execute(self):
        report = self.working_dir / "report.md"
        report.write_text("# Report\n\nbody", encoding="utf-8")
        return SubagentResult(
            status=SubagentStatus.COMPLETED,
            data=SimpleNamespace(report_path=report),
        )


class _FakeQA(_Fake):
    name = "QASubagent"

    def __init__(self, context, *args, min_score=70, **kwargs):
        super().__init__(context)
        self.min_score = min_score

    async def execute(self):
        return SubagentResult(status=SubagentStatus.COMPLETED, data=SimpleNamespace(score=90))


class _FakeVerifier(_Fake):
    name = "VerifierSubagent"

    async def execute(self):
        return SubagentResult(
            status=SubagentStatus.COMPLETED,
            data=SimpleNamespace(trust_percentage=88),
        )


@pytest.fixture
def fast_subagents(monkeypatch):
    monkeypatch.setattr(orch_mod, "ScraperSubagent", _FakeScraper)
    monkeypatch.setattr(orch_mod, "AnalystSubagent", _FakeAnalyst)
    monkeypatch.setattr(orch_mod, "WriterSubagent", _FakeWriter)
    monkeypatch.setattr(orch_mod, "QASubagent", _FakeQA)
    monkeypatch.setattr(orch_mod, "VerifierSubagent", _FakeVerifier)


def _config(tmp: str, **kwargs) -> OrchestratorConfig:
    return OrchestratorConfig(output_dir=Path(tmp), **kwargs)


# =============================================================================
# Happy path full pipeline + verification
# =============================================================================


def test_full_pipeline_with_verification(fast_subagents):
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, enable_verification=True))
        result = asyncio.run(orch.research("Acme Corp", "https://acme.example", mode="full"))

        assert result.state == OrchestratorState.COMPLETED
        assert result.report_path is not None
        assert "scrape" in result.stage_results
        assert "analyze" in result.stage_results
        assert "write" in result.stage_results
        assert "qa" in result.stage_results
        assert "verify" in result.stage_results
        assert len(result.hypotheses) == 1


def test_scrape_only_mode(fast_subagents):
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="scrape"))
        assert "scrape" in result.stage_results
        # No writing in scrape mode -> no report.
        assert result.report_path is None


def test_full_mode_empty_scrape_data_is_not_success(monkeypatch, fast_subagents):
    """Empty intermediate data must not report COMPLETED with no report path."""

    class _EmptyScraper(_Fake):
        name = "ScraperSubagent"

        async def execute(self):
            return SubagentResult(status=SubagentStatus.COMPLETED, data=None)

    monkeypatch.setattr(orch_mod, "ScraperSubagent", _EmptyScraper)
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert result.state == OrchestratorState.FAILED
        assert result.is_success is False
        assert result.report_path is None
        assert any("no report" in err.lower() for err in result.errors)


# =============================================================================
# Memory load/save error handling
# =============================================================================


def test_memory_load_failure_is_swallowed(fast_subagents):
    class _BadLoadMemory:
        def get_hypotheses(self, company):
            raise RuntimeError("load failed")

        def save_hypotheses(self, company, hyps):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp), memory=_BadLoadMemory())
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        # Load failure should not abort the run.
        assert result.state == OrchestratorState.COMPLETED


def test_memory_save_failure_is_swallowed(fast_subagents):
    class _BadSaveMemory:
        def get_hypotheses(self, company):
            return []

        def save_hypotheses(self, company, hyps):
            raise RuntimeError("save failed")

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp), memory=_BadSaveMemory())
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert result.state == OrchestratorState.COMPLETED


def test_memory_save_called_with_hypotheses(fast_subagents):
    class _Memory:
        def __init__(self):
            self.saved = None

        def get_hypotheses(self, company):
            return []

        def save_hypotheses(self, company, hyps):
            self.saved = (company, list(hyps))

    with tempfile.TemporaryDirectory() as tmp:
        memory = _Memory()
        orch = ResearchOrchestrator(config=_config(tmp), memory=memory)
        asyncio.run(orch.research("Acme Corp", "https://acme.example", mode="full"))
        assert memory.saved is not None
        assert memory.saved[0] == "Acme Corp"
        assert len(memory.saved[1]) == 1


# =============================================================================
# Failure handling: fail_fast and continue
# =============================================================================


def test_scrape_failure_fail_fast(monkeypatch):
    class _FailingScraper(_Fake):
        name = "ScraperSubagent"

        async def execute(self):
            return SubagentResult(status=SubagentStatus.FAILED, error="scrape boom")

    monkeypatch.setattr(orch_mod, "ScraperSubagent", _FailingScraper)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, fail_fast=True))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert result.state == OrchestratorState.FAILED
        assert any("scrape boom" in e or "Scrape failed" in e for e in result.errors)


def test_analyst_failure_continues_and_accumulates_hypotheses(fast_subagents, monkeypatch):
    class _PartialFailAnalyst(_Fake):
        name = "AnalystSubagent"

        async def execute(self):
            hyp = Hypothesis(id="h_x", claim="partial", confidence=ConfidenceLevel.UNTESTED)
            return SubagentResult(
                status=SubagentStatus.FAILED,
                error="analysis boom",
                hypotheses=[hyp],
            )

    monkeypatch.setattr(orch_mod, "AnalystSubagent", _PartialFailAnalyst)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, fail_fast=False))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        # Continue-on-failure: state is FAILED but hypotheses still accumulate.
        assert result.state == OrchestratorState.FAILED
        assert any("Analysis failed" in e for e in result.errors)
        assert any(h.id == "h_x" for h in result.hypotheses)
        # Writing skipped because analyze had no data.
        assert "write" not in result.stage_results


def test_analyst_failure_fail_fast_raises(fast_subagents, monkeypatch):
    class _FailAnalyst(_Fake):
        name = "AnalystSubagent"

        async def execute(self):
            return SubagentResult(status=SubagentStatus.FAILED, error="analysis boom")

    monkeypatch.setattr(orch_mod, "AnalystSubagent", _FailAnalyst)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, fail_fast=True))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert result.state == OrchestratorState.FAILED
        assert any("analysis boom" in e or "Analysis failed" in e for e in result.errors)


def test_writer_failure_fail_fast(fast_subagents, monkeypatch):
    class _FailingWriter(_Fake):
        name = "WriterSubagent"

        async def execute(self):
            return SubagentResult(status=SubagentStatus.FAILED, error="write boom")

    monkeypatch.setattr(orch_mod, "WriterSubagent", _FailingWriter)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, fail_fast=True))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert result.state == OrchestratorState.FAILED
        assert any("write boom" in e or "Writing failed" in e for e in result.errors)


def test_qa_failure_recorded_not_fatal(fast_subagents, monkeypatch):
    class _FailingQA(_Fake):
        name = "QASubagent"

        def __init__(self, context, *args, min_score=70, **kwargs):
            super().__init__(context)

        async def execute(self):
            return SubagentResult(status=SubagentStatus.FAILED, error="qa boom")

    monkeypatch.setattr(orch_mod, "QASubagent", _FailingQA)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert result.state == OrchestratorState.FAILED
        assert any("QA failed" in e for e in result.errors)
        # Report still produced.
        assert result.report_path is not None


def test_verification_failure_is_non_blocking(fast_subagents, monkeypatch):
    class _FailingVerifier(_Fake):
        name = "VerifierSubagent"

        async def execute(self):
            return SubagentResult(status=SubagentStatus.FAILED, error="verify boom")

    monkeypatch.setattr(orch_mod, "VerifierSubagent", _FailingVerifier)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, enable_verification=True))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        # Verification failure does not flip overall state.
        assert result.state == OrchestratorState.COMPLETED


def test_verification_stage_raises_is_caught(fast_subagents, monkeypatch):
    class _ExplodingVerifier(_Fake):
        name = "VerifierSubagent"

        async def execute(self):
            raise RuntimeError("verifier exploded")

    monkeypatch.setattr(orch_mod, "VerifierSubagent", _ExplodingVerifier)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, enable_verification=True))
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        # Exception in verify stage is swallowed; run completes.
        assert result.state == OrchestratorState.COMPLETED


# =============================================================================
# Unexpected error -> OrchestratorError
# =============================================================================


def test_unexpected_error_raises_orchestrator_error(fast_subagents, monkeypatch):
    class _ExplodingScraper(_Fake):
        name = "ScraperSubagent"

        async def execute(self):
            raise RuntimeError("scraper exploded")

    monkeypatch.setattr(orch_mod, "ScraperSubagent", _ExplodingScraper)

    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp))
        with pytest.raises(OrchestratorError) as exc:
            asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert orch.state == OrchestratorState.FAILED
        assert "scraper exploded" in str(exc.value)


# =============================================================================
# Hook integration in _execute_stage
# =============================================================================


class _BlockScrapeHook(Hook):
    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        if context.stage_name == "scrape":
            return HookResponse(result=HookResult.BLOCK, message="scrape blocked")
        return HookResponse(result=HookResult.ALLOW)


def test_pre_hook_block_produces_failed_stage(fast_subagents):
    with tempfile.TemporaryDirectory() as tmp:
        hooks = HookSystem()
        hooks.register(_BlockScrapeHook())
        orch = ResearchOrchestrator(config=_config(tmp), hook_system=hooks)
        result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))

        scrape_result = result.stage_results["scrape"]
        assert scrape_result.is_failure
        assert "Blocked by hook" in (scrape_result.error or "")


def test_exhausted_run_budget_blocks_later_stages(fast_subagents, monkeypatch):
    from primr.utils.run_budget import clear_run_budget, set_run_budget

    monkeypatch.setattr(
        "primr.utils.run_budget.observed_session_spend",
        lambda: 1.0,
    )
    clear_run_budget()
    try:
        budget = set_run_budget(1.0)
        with tempfile.TemporaryDirectory() as tmp:
            hooks = HookSystem()
            hooks.register(budget.as_hook())
            orch = ResearchOrchestrator(config=_config(tmp), hook_system=hooks)
            result = asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        scrape_result = result.stage_results["scrape"]
        assert scrape_result.is_failure
        assert "Blocked by hook" in (scrape_result.error or "")
    finally:
        clear_run_budget()


def test_post_hooks_run(fast_subagents):
    calls = []

    class _PostHook(Hook):
        @property
        def hook_type(self) -> HookType:
            return HookType.POST_TOOL_USE

        async def execute(self, context: HookContext) -> HookResponse:
            calls.append(context.stage_name)
            return HookResponse(result=HookResult.ALLOW)

    with tempfile.TemporaryDirectory() as tmp:
        hooks = HookSystem()
        hooks.register(_PostHook())
        orch = ResearchOrchestrator(config=_config(tmp), hook_system=hooks)
        asyncio.run(orch.research("Acme", "https://acme.example", mode="full"))
        assert "scrape" in calls
        assert "write" in calls


# =============================================================================
# _request_user_input
# =============================================================================


def test_request_user_input_raises_without_interactive():
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp))
        with pytest.raises(OrchestratorError):
            asyncio.run(orch._request_user_input("prompt?"))


def test_request_user_input_records_decision_with_context():
    with tempfile.TemporaryDirectory() as tmp:
        seen = {}

        async def cb(prompt, options):
            seen["prompt"] = prompt
            return "go"

        orch = ResearchOrchestrator(
            config=_config(tmp, enable_interactive=True, user_input_callback=cb)
        )
        orch._state = OrchestratorState.ANALYZING
        resp = asyncio.run(orch._request_user_input("Continue?", ["go"], context="ctx"))
        assert resp == "go"
        # Context is prepended to the prompt passed to the callback.
        assert seen["prompt"].startswith("ctx")
        assert orch.user_decisions[0]["prompt"] == "Continue?"
        assert orch.user_decisions[0]["stage"] == "analyzing"


# =============================================================================
# _handle_stage_transition
# =============================================================================


def test_stage_transition_no_pause_returns_true():
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp))
        assert asyncio.run(orch._handle_stage_transition("scrape", "analyze")) is True


def test_stage_transition_pause_but_not_interactive_returns_true():
    """pause_between_stages set but interactive disabled -> continue."""
    with tempfile.TemporaryDirectory() as tmp:
        # enable_interactive auto-disables without a callback.
        orch = ResearchOrchestrator(config=_config(tmp, pause_between_stages=True))
        assert orch.is_interactive is False
        assert asyncio.run(orch._handle_stage_transition("scrape", "analyze")) is True


def test_stage_transition_pause_continue():
    with tempfile.TemporaryDirectory() as tmp:

        async def cb(prompt, options):
            return "continue"

        orch = ResearchOrchestrator(
            config=_config(
                tmp,
                enable_interactive=True,
                user_input_callback=cb,
                pause_between_stages=True,
            )
        )
        assert asyncio.run(orch._handle_stage_transition("scrape", "analyze")) is True


def test_stage_transition_pause_abort():
    with tempfile.TemporaryDirectory() as tmp:

        async def cb(prompt, options):
            return "ABORT"

        orch = ResearchOrchestrator(
            config=_config(
                tmp,
                enable_interactive=True,
                user_input_callback=cb,
                pause_between_stages=True,
            )
        )
        assert asyncio.run(orch._handle_stage_transition("scrape", "analyze")) is False


def test_stage_transition_callback_error_defaults_continue():
    with tempfile.TemporaryDirectory() as tmp:

        async def cb(prompt, options):
            raise RuntimeError("input failed")

        orch = ResearchOrchestrator(
            config=_config(
                tmp,
                enable_interactive=True,
                user_input_callback=cb,
                pause_between_stages=True,
            )
        )
        assert asyncio.run(orch._handle_stage_transition("scrape", "analyze")) is True


# =============================================================================
# _handle_error_recovery
# =============================================================================


def _recovery_hook(result: HookResult):
    class _H(Hook):
        @property
        def hook_type(self) -> HookType:
            return HookType.ERROR_RECOVERY

        async def execute(self, context: HookContext) -> HookResponse:
            return HookResponse(result=result, message="r")

    return _H()


def test_error_recovery_hook_allow_maps_to_retry():
    with tempfile.TemporaryDirectory() as tmp:
        hooks = HookSystem()
        hooks.register(_recovery_hook(HookResult.ALLOW))
        orch = ResearchOrchestrator(config=_config(tmp), hook_system=hooks)
        action = asyncio.run(orch._handle_error_recovery("scrape", RuntimeError("x"), 0))
        assert action == "retry"


def test_error_recovery_hook_warn_maps_to_skip():
    with tempfile.TemporaryDirectory() as tmp:
        hooks = HookSystem()
        hooks.register(_recovery_hook(HookResult.WARN))
        orch = ResearchOrchestrator(config=_config(tmp), hook_system=hooks)
        action = asyncio.run(orch._handle_error_recovery("scrape", RuntimeError("x"), 0))
        assert action == "skip"


def test_error_recovery_default_skip_when_not_fail_fast():
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, fail_fast=False))
        action = asyncio.run(orch._handle_error_recovery("scrape", RuntimeError("x"), 0))
        assert action == "skip"


def test_error_recovery_default_abort_when_fail_fast():
    with tempfile.TemporaryDirectory() as tmp:
        orch = ResearchOrchestrator(config=_config(tmp, fail_fast=True))
        action = asyncio.run(orch._handle_error_recovery("scrape", RuntimeError("x"), 0))
        assert action == "abort"


def test_error_recovery_interactive_user_choice():
    with tempfile.TemporaryDirectory() as tmp:

        async def cb(prompt, options):
            return "Retry"

        orch = ResearchOrchestrator(
            config=_config(
                tmp,
                enable_interactive=True,
                user_input_callback=cb,
                pause_on_error=True,
            )
        )
        # Hook BLOCK falls through to user input.
        hooks = HookSystem()
        hooks.register(_recovery_hook(HookResult.BLOCK))
        orch._hooks = hooks
        action = asyncio.run(orch._handle_error_recovery("scrape", RuntimeError("x"), 1))
        assert action == "retry"


def test_error_recovery_interactive_callback_failure_falls_back():
    with tempfile.TemporaryDirectory() as tmp:

        async def cb(prompt, options):
            raise RuntimeError("input failed")

        orch = ResearchOrchestrator(
            config=_config(
                tmp,
                enable_interactive=True,
                user_input_callback=cb,
                pause_on_error=True,
                fail_fast=True,
            )
        )
        action = asyncio.run(orch._handle_error_recovery("scrape", RuntimeError("x"), 1))
        # Callback failed -> default abort (fail_fast).
        assert action == "abort"
