"""Tests for the no-model-call execution policy."""

from __future__ import annotations

import pytest

from primr.utils.model_policy import (
    ModelCallsDisabledError,
    disable_model_calls,
    model_calls_disabled,
    require_model_calls_allowed,
    submit_with_model_policy,
)


def test_context_manager_disables_and_restores_model_calls() -> None:
    assert model_calls_disabled() is False

    with disable_model_calls():
        assert model_calls_disabled() is True
        with pytest.raises(ModelCallsDisabledError, match="generation is disabled"):
            require_model_calls_allowed("generation")

    assert model_calls_disabled() is False


def test_context_policy_can_be_propagated_to_worker_threads() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with disable_model_calls(), ThreadPoolExecutor(max_workers=1) as pool:
        assert submit_with_model_policy(pool, model_calls_disabled).result() is True


def test_context_policy_does_not_block_unrelated_worker() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with disable_model_calls(), ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(model_calls_disabled).result() is False


def test_overlapping_contexts_remain_isolated() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool, disable_model_calls():
        first = submit_with_model_policy(pool, model_calls_disabled)
        with disable_model_calls():
            second = submit_with_model_policy(pool, model_calls_disabled)
        assert first.result() is True
        assert second.result() is True


def test_environment_can_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIMR_DISABLE_MODEL_CALLS", "YES")
    assert model_calls_disabled() is True


def test_nested_context_restores_outer_policy() -> None:
    with disable_model_calls():
        with disable_model_calls():
            assert model_calls_disabled() is True
        assert model_calls_disabled() is True


def test_public_llm_seams_fail_before_provider_egress() -> None:
    from primr.ai.grok_client import ContinuousReasoningSession, grok_browse_and_summarize, grok_llm
    from primr.ai.llm import llm

    with disable_model_calls():
        with pytest.raises(ModelCallsDisabledError):
            llm("do not send")
        with pytest.raises(ModelCallsDisabledError):
            grok_llm("do not send")
        with pytest.raises(ModelCallsDisabledError):
            grok_browse_and_summarize("https://example.com")
        with pytest.raises(ModelCallsDisabledError):
            ContinuousReasoningSession().send("do not send")
