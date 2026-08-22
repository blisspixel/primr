"""
Additional coverage for the hook governance system.

Covers the decision branches the property tests leave uncovered:
SSRFGuardHook valid/invalid/ImportError paths, QAGateHook scoring (both the
ReportAnalyzer path and the ImportError fallback), MemoryPersistenceHook,
VerificationGateHook, ContentSanitizationHook ImportError fallback, the
modified_args propagation through run_pre_hooks, post-hook WARN logging,
session-start blocking, and run_error_recovery_hooks WARN/BLOCK/empty paths.

All external modules (URLValidator, ReportAnalyzer, ContentSanitizer) are
mocked or driven through real temp files so no network/LLM calls happen.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

from primr.agentic.cost_guard import CostGuardHook
from primr.agentic.hooks import (
    ContentSanitizationHook,
    Hook,
    HookContext,
    HookResponse,
    HookResult,
    HookSystem,
    HookType,
    MemoryPersistenceHook,
    QAGateHook,
    SSRFGuardHook,
    VerificationGateHook,
)
from primr.agentic.models import ConfidenceLevel, Hypothesis

# =============================================================================
# Test helper hooks
# =============================================================================


class _ModifyingHook(Hook):
    """Pre hook that mutates an argument via modified_args."""

    def __init__(self, key: str, value: str, priority: int = 10):
        super().__init__(priority=priority, name=f"Modifier_{key}")
        self._key = key
        self._value = value

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        return HookResponse(
            result=HookResult.ALLOW,
            modified_args={self._key: self._value},
        )


class _WarnPreHook(Hook):
    def __init__(self, priority: int = 20):
        super().__init__(priority=priority, name="WarnPre")

    @property
    def hook_type(self) -> HookType:
        return HookType.PRE_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        return HookResponse(result=HookResult.WARN, message="just warning")


class _WarnPostHook(Hook):
    @property
    def hook_type(self) -> HookType:
        return HookType.POST_TOOL_USE

    async def execute(self, context: HookContext) -> HookResponse:
        return HookResponse(result=HookResult.WARN, message="post warning")


class _BlockSessionHook(Hook):
    @property
    def hook_type(self) -> HookType:
        return HookType.SESSION_START

    async def execute(self, context: HookContext) -> HookResponse:
        return HookResponse(result=HookResult.BLOCK, message="no session")


class _RecoveryHook(Hook):
    def __init__(self, result: HookResult, message: str = "", priority: int = 10):
        super().__init__(priority=priority, name=f"Recovery_{result.value}")
        self._result = result
        self._message = message

    @property
    def hook_type(self) -> HookType:
        return HookType.ERROR_RECOVERY

    async def execute(self, context: HookContext) -> HookResponse:
        return HookResponse(result=self._result, message=self._message)


# =============================================================================
# run_pre_hooks: modified_args propagation + WARN
# =============================================================================


def test_pre_hooks_propagate_modified_args_through_chain():
    hooks = HookSystem()
    hooks.register(_ModifyingHook("content", "clean-1", priority=10))
    hooks.register(_ModifyingHook("extra", "added", priority=20))

    context = HookContext(hook_type=HookType.PRE_TOOL_USE, arguments={"content": "dirty"})
    response = asyncio.run(hooks.run_pre_hooks("stage", context))

    assert response.result == HookResult.ALLOW
    # Merged modified args returned, and the context was updated in place.
    assert response.modified_args == {"content": "clean-1", "extra": "added"}
    assert context.arguments["content"] == "clean-1"
    assert context.arguments["extra"] == "added"


def test_pre_hooks_warn_does_not_block():
    hooks = HookSystem()
    hooks.register(_WarnPreHook())
    response = asyncio.run(hooks.run_pre_hooks("stage"))
    assert response.result == HookResult.ALLOW


def test_post_hooks_warn_path():
    hooks = HookSystem()
    hooks.register(_WarnPostHook())
    # Should run without raising; warn path is exercised.
    asyncio.run(hooks.run_post_hooks("stage", result=None))


# =============================================================================
# Session hooks
# =============================================================================


def test_session_hooks_block():
    hooks = HookSystem()
    hooks.register(_BlockSessionHook())
    response = asyncio.run(hooks.run_session_hooks())
    assert response.result == HookResult.BLOCK
    assert response.message == "no session"


def test_session_hooks_allow_when_empty():
    hooks = HookSystem()
    response = asyncio.run(hooks.run_session_hooks())
    assert response.result == HookResult.ALLOW


# =============================================================================
# run_error_recovery_hooks: BLOCK / WARN-then-default / empty
# =============================================================================


def test_error_recovery_returns_block_immediately():
    hooks = HookSystem()
    hooks.register(_RecoveryHook(HookResult.BLOCK, "abort now", priority=5))
    hooks.register(_RecoveryHook(HookResult.ALLOW, "retry", priority=10))

    response = asyncio.run(hooks.run_error_recovery_hooks("stage", RuntimeError("x")))
    assert response.result == HookResult.BLOCK
    assert response.message == "abort now"


def test_error_recovery_returns_last_warn_when_no_allow_or_block():
    hooks = HookSystem()
    hooks.register(_RecoveryHook(HookResult.WARN, "skip me", priority=10))

    response = asyncio.run(hooks.run_error_recovery_hooks("stage", RuntimeError("x")))
    assert response.result == HookResult.WARN
    assert response.message == "skip me"


def test_error_recovery_default_block_when_no_hooks():
    hooks = HookSystem()
    response = asyncio.run(hooks.run_error_recovery_hooks("stage", RuntimeError("x")))
    assert response.result == HookResult.BLOCK
    assert "No error recovery hook" in (response.message or "")


def test_error_recovery_builds_default_context():
    """When no context is supplied, one is built from the error."""
    hooks = HookSystem()

    captured = {}

    class _CaptureHook(Hook):
        @property
        def hook_type(self) -> HookType:
            return HookType.ERROR_RECOVERY

        async def execute(self, context: HookContext) -> HookResponse:
            captured["error_type"] = context.arguments.get("error_type")
            return HookResponse(result=HookResult.ALLOW)

    hooks.register(_CaptureHook())
    asyncio.run(hooks.run_error_recovery_hooks("stage", ValueError("bad")))
    assert captured["error_type"] == "ValueError"


# =============================================================================
# SSRFGuardHook
# =============================================================================


def test_ssrf_guard_allows_valid_url(monkeypatch):
    monkeypatch.setattr(
        "primr.utils.security.is_safe_url",
        lambda _url: (True, None),
    )
    hook = SSRFGuardHook()
    ctx = HookContext(hook_type=HookType.PRE_TOOL_USE, arguments={"url": "https://acme.example"})
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


def test_ssrf_guard_blocks_invalid_url(monkeypatch):
    monkeypatch.setattr(
        "primr.utils.security.is_safe_url",
        lambda _url: (False, "private IP"),
    )
    hook = SSRFGuardHook()
    ctx = HookContext(
        hook_type=HookType.PRE_TOOL_USE, arguments={"company_url": "http://127.0.0.1"}
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.BLOCK
    assert "private IP" in (response.message or "")


def test_ssrf_guard_blocks_loopback_without_a_second_validator():
    hook = SSRFGuardHook()
    ctx = HookContext(
        hook_type=HookType.PRE_TOOL_USE, arguments={"target_url": "http://127.0.0.1/"}
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.BLOCK


# =============================================================================
# QAGateHook
# =============================================================================


def _make_report(working: Path, content: str) -> Path:
    report = working / "report.md"
    report.write_text(content, encoding="utf-8")
    return report


def test_qa_gate_skips_non_write_stage():
    hook = QAGateHook(min_score=70)
    ctx = HookContext(hook_type=HookType.POST_TOOL_USE, stage_name="scrape")
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


def test_qa_gate_allows_when_no_report_path():
    hook = QAGateHook()
    ctx = HookContext(hook_type=HookType.POST_TOOL_USE, stage_name="write", result=None)
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


def test_qa_gate_warns_when_report_missing():
    hook = QAGateHook()
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        stage_name="write",
        result=SimpleNamespace(report_path="/no/such/report.md"),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.WARN
    assert "not found" in (response.message or "")


def _install_fake_report_analyzer(
    monkeypatch, *, word_count, sections, missing, hyp_ok, cite_ok, truncated
):
    fake_mod = types.ModuleType("primr.qa.report_analyzer")

    class ReportAnalyzer:
        def __init__(self, path):
            self._path = path

        def analyze_content_quality(self):
            return {"word_count": word_count}

        def analyze_structure(self):
            return {"total_sections": sections, "key_sections_missing": missing}

        def analyze_hypothesis_coverage(self):
            return {"meets_threshold": hyp_ok, "total_signals": 1, "threshold": 3}

        def analyze_citation_density(self):
            return {
                "meets_threshold": cite_ok,
                "density_per_1000_words": 1.0,
                "threshold": 5,
            }

        def analyze_section_lengths(self):
            return {
                "truncated_sections": truncated,
                "truncated_count": len(truncated),
            }

    fake_mod.ReportAnalyzer = ReportAnalyzer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "primr.qa.report_analyzer", fake_mod)


def test_qa_gate_high_score_allows(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        report = _make_report(working, "# Report\n" + "word " * 600)
        _install_fake_report_analyzer(
            monkeypatch,
            word_count=600,
            sections=5,
            missing=[],
            hyp_ok=True,
            cite_ok=True,
            truncated=[],
        )
        hook = QAGateHook(min_score=70)
        ctx = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=SimpleNamespace(report_path=str(report)),
        )
        response = asyncio.run(hook.execute(ctx))
        # 50 +15 +10 +10 +5 +5 = 95
        assert hook.last_score == 95
        assert response.result == HookResult.ALLOW
        assert hook.last_feedback == []


def test_qa_gate_low_score_warns_with_feedback(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        report = _make_report(working, "# Report\nshort")
        _install_fake_report_analyzer(
            monkeypatch,
            word_count=100,
            sections=1,
            missing=["Executive Summary"],
            hyp_ok=False,
            cite_ok=False,
            truncated=["Overview", "Risks"],
        )
        hook = QAGateHook(min_score=70)
        ctx = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=SimpleNamespace(report_path=str(report)),
        )
        response = asyncio.run(hook.execute(ctx))
        # 50 base, nothing added, minus 10 truncation penalty = 40
        assert hook.last_score == 40
        assert response.result == HookResult.WARN
        assert any("short" in f for f in hook.last_feedback)
        assert any("truncated" in f for f in hook.last_feedback)


def test_qa_gate_reads_report_path_from_data_attribute(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        report = _make_report(working, "# Report\n" + "word " * 600)
        _install_fake_report_analyzer(
            monkeypatch,
            word_count=600,
            sections=5,
            missing=[],
            hyp_ok=True,
            cite_ok=True,
            truncated=[],
        )
        hook = QAGateHook(min_score=70)
        # result has no report_path, but result.data does.
        result = SimpleNamespace(data=SimpleNamespace(report_path=str(report)))
        ctx = HookContext(hook_type=HookType.POST_TOOL_USE, stage_name="write", result=result)
        response = asyncio.run(hook.execute(ctx))
        assert response.result == HookResult.ALLOW


def test_qa_gate_fallback_without_report_analyzer(monkeypatch):
    """ImportError on ReportAnalyzer -> basic word/section heuristics."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "primr.qa.report_analyzer":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        # >=500 words and >=3 '#' -> 50 + 20 + 15 = 85
        content = "# A\n## B\n### C\n" + "word " * 600
        report = _make_report(working, content)
        hook = QAGateHook(min_score=70)
        ctx = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=SimpleNamespace(report_path=str(report)),
        )
        response = asyncio.run(hook.execute(ctx))
        assert hook.last_score == 85
        assert response.result == HookResult.ALLOW


def test_qa_gate_fallback_low_quality_feedback(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "primr.qa.report_analyzer":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        report = _make_report(working, "short text no headings")
        hook = QAGateHook(min_score=70)
        ctx = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=SimpleNamespace(report_path=str(report)),
        )
        response = asyncio.run(hook.execute(ctx))
        assert hook.last_score == 50
        assert response.result == HookResult.WARN
        assert any("section" in f for f in hook.last_feedback)
        assert any("short" in f for f in hook.last_feedback)


def test_qa_gate_handles_analysis_exception(monkeypatch):
    """An unexpected error during analysis is swallowed -> ALLOW."""
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        report = _make_report(working, "content")

        fake_mod = types.ModuleType("primr.qa.report_analyzer")

        class ReportAnalyzer:
            def __init__(self, path):
                raise RuntimeError("analyzer boom")

        fake_mod.ReportAnalyzer = ReportAnalyzer  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "primr.qa.report_analyzer", fake_mod)

        hook = QAGateHook()
        ctx = HookContext(
            hook_type=HookType.POST_TOOL_USE,
            stage_name="write",
            result=SimpleNamespace(report_path=str(report)),
        )
        response = asyncio.run(hook.execute(ctx))
        assert response.result == HookResult.ALLOW


def test_qa_gate_properties():
    hook = QAGateHook(min_score=80)
    assert hook.min_score == 80
    assert hook.last_score is None
    assert hook.last_feedback == []
    assert hook.hook_type == HookType.POST_TOOL_USE


# =============================================================================
# MemoryPersistenceHook
# =============================================================================


class _FakeMemory:
    def __init__(self, fail: bool = False):
        self.saved = []
        self._fail = fail

    def save_hypotheses(self, company, hypotheses):
        if self._fail:
            raise RuntimeError("disk full")
        self.saved.append((company, list(hypotheses)))


def _hyp():
    return Hypothesis(id="h_1", claim="Uses cloud", confidence=ConfidenceLevel.UNTESTED)


def test_memory_persistence_saves_from_result_hypotheses():
    memory = _FakeMemory()
    hook = MemoryPersistenceHook(memory)  # type: ignore[arg-type]
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        company_name="Acme Corp",
        result=SimpleNamespace(hypotheses=[_hyp()]),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW
    assert memory.saved[0][0] == "Acme Corp"
    assert len(memory.saved[0][1]) == 1


def test_memory_persistence_reads_from_data_and_arguments_company():
    memory = _FakeMemory()
    hook = MemoryPersistenceHook(memory)  # type: ignore[arg-type]
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        arguments={"company": "FromArgs"},
        result=SimpleNamespace(data=SimpleNamespace(hypotheses=[_hyp()])),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW
    assert memory.saved[0][0] == "FromArgs"


def test_memory_persistence_no_hypotheses_does_nothing():
    memory = _FakeMemory()
    hook = MemoryPersistenceHook(memory)  # type: ignore[arg-type]
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        company_name="Acme Corp",
        result=SimpleNamespace(hypotheses=[]),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW
    assert memory.saved == []


def test_memory_persistence_swallows_save_error():
    memory = _FakeMemory(fail=True)
    hook = MemoryPersistenceHook(memory)  # type: ignore[arg-type]
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        company_name="Acme Corp",
        result=SimpleNamespace(hypotheses=[_hyp()]),
    )
    response = asyncio.run(hook.execute(ctx))
    # Error is logged, not raised.
    assert response.result == HookResult.ALLOW


# =============================================================================
# VerificationGateHook
# =============================================================================


def test_verification_gate_skips_non_verify_stage():
    hook = VerificationGateHook()
    ctx = HookContext(hook_type=HookType.POST_TOOL_USE, stage_name="write")
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


def test_verification_gate_allows_when_no_trust_score():
    hook = VerificationGateHook()
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        stage_name="verify",
        result=SimpleNamespace(data=SimpleNamespace()),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


def test_verification_gate_warns_below_threshold():
    hook = VerificationGateHook(min_trust_score=0.5)
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        stage_name="verify",
        result=SimpleNamespace(data=SimpleNamespace(trust_score=0.3)),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.WARN
    assert "30%" in (response.message or "")
    assert hook.last_trust_score == 0.3


def test_verification_gate_allows_above_threshold():
    hook = VerificationGateHook(min_trust_score=0.5)
    assert hook.min_trust_score == 0.5
    assert hook.last_trust_score is None
    ctx = HookContext(
        hook_type=HookType.POST_TOOL_USE,
        stage_name="verify",
        result=SimpleNamespace(data=SimpleNamespace(trust_score=0.9)),
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW
    assert hook.last_trust_score == 0.9


# =============================================================================
# ContentSanitizationHook ImportError fallback + mode property
# =============================================================================


def test_content_sanitization_module_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "primr.utils.content_sanitizer":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    hook = ContentSanitizationHook(mode="strip")
    assert hook.mode == "strip"
    ctx = HookContext(hook_type=HookType.PRE_TOOL_USE, arguments={"content": "some content"})
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.WARN
    assert "not available" in (response.message or "")


def test_content_sanitization_non_string_content_allowed():
    hook = ContentSanitizationHook(mode="strip")
    ctx = HookContext(hook_type=HookType.PRE_TOOL_USE, arguments={"content": 12345})
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


# =============================================================================
# CostGuardHook hook_type / max_cost properties (light)
# =============================================================================


def test_cost_guard_hook_type_and_max_cost():
    hook = CostGuardHook(max_cost_usd=12.5)
    assert hook.hook_type == HookType.PRE_TOOL_USE
    assert hook.max_cost == 12.5


def test_cost_guard_negative_estimate_treated_as_zero():
    hook = CostGuardHook(max_cost_usd=5.0)
    ctx = HookContext(
        hook_type=HookType.PRE_TOOL_USE,
        arguments={"estimated_cost_usd": -100.0},
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.ALLOW


def test_cost_guard_exhausted_budget_blocks_zero_estimate():
    hook = CostGuardHook(max_cost_usd=5.0)
    hook.set_spent(5.0)
    ctx = HookContext(
        hook_type=HookType.PRE_TOOL_USE,
        arguments={"estimated_cost_usd": 0.0},
    )
    response = asyncio.run(hook.execute(ctx))
    assert response.result == HookResult.BLOCK
    assert "Budget exceeded" in (response.message or "")
