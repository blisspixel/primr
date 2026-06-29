"""Coverage tests for primr.ai.grok_client.

Focus areas: cross-provider dispatch in grok_llm, billing-exhaustion classifier,
retry-after fallback parsing, backoff math, approx_context_tokens, and the
grok_browse_and_summarize compatibility wrapper.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from primr.ai import grok_client

# ---------------------------------------------------------------------------
# Error classifiers / helpers
# ---------------------------------------------------------------------------


def test_is_billing_exhausted_delegates(monkeypatch):
    monkeypatch.setattr("primr.ai.error_policy.is_billing_exhausted", lambda e: True)
    assert grok_client._is_billing_exhausted(Exception("402")) is True


def test_retryable_returns_false_for_billing(monkeypatch):
    monkeypatch.setattr(grok_client, "_is_billing_exhausted", lambda e: True)
    assert grok_client._is_retryable_grok_error(Exception("429 rate limit")) is False


def test_retryable_markers_match():
    for marker in ("timeout", "connection reset", "502", "service unavailable"):
        assert grok_client._is_retryable_grok_error(Exception(marker)) is True


def test_extract_retry_after_from_message_fragment():
    err = Exception("please retry after 12 seconds")
    assert grok_client._extract_retry_after_seconds(err) == 12.0


def test_extract_retry_after_none_when_absent():
    assert grok_client._extract_retry_after_seconds(Exception("nope")) is None


def test_extract_retry_after_ignores_non_positive_header():
    err = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "0"}))
    # 0 is not > 0 and there's no message fragment -> None
    assert grok_client._extract_retry_after_seconds(err) is None


def test_extract_retry_after_invalid_header_falls_through():
    err = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "abc"}))
    assert grok_client._extract_retry_after_seconds(err) is None


def test_compute_backoff_delay_within_bounds():
    delay = grok_client._compute_backoff_delay(0, base=5.0, cap=90.0)
    assert 5.0 <= delay <= 6.0  # base + up to 20% jitter


def test_compute_backoff_delay_caps():
    delay = grok_client._compute_backoff_delay(20, base=5.0, cap=90.0)
    assert 90.0 <= delay <= 108.0


# ---------------------------------------------------------------------------
# Session usage accessors
# ---------------------------------------------------------------------------


def test_reset_grok_session_clears_counters():
    grok_client._session_input_tokens = 99
    grok_client._session_output_tokens = 88
    grok_client._session_cached_input_tokens = 44
    grok_client._session_tokens_by_model = {"m": {"input_tokens": 1, "output_tokens": 1}}
    grok_client.reset_grok_session()
    assert grok_client.get_grok_session_usage() == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
    }
    assert grok_client.get_grok_session_usage_by_model() == {}


# ---------------------------------------------------------------------------
# Cross-provider dispatch path of grok_llm
# ---------------------------------------------------------------------------


def test_grok_llm_cross_provider_dispatch(monkeypatch):
    grok_client.reset_grok_session()

    # Model config that is NOT xai -> triggers cross-provider branch
    fake_config = SimpleNamespace(provider="gemini")
    monkeypatch.setattr(
        "primr.config.models.PrimrModels.get_model_config",
        lambda model: fake_config,
    )

    cross_provider = MagicMock()
    cross_provider.chat.return_value = SimpleNamespace(
        text="gemini reply", input_tokens=5, output_tokens=3, cached_input_tokens=0
    )
    monkeypatch.setattr("primr.ai.routing.get_provider_for_model", lambda model: cross_provider)

    out = grok_client.grok_llm("hello", model="gemini-3.1-flash-lite", reasoning_effort="low")

    assert out == "gemini reply"
    # reasoning_effort forwarded
    assert cross_provider.chat.call_args.kwargs["reasoning_effort"] == "low"
    usage = grok_client.get_grok_session_usage()
    assert usage["input_tokens"] == 5
    assert usage["output_tokens"] == 3
    by_model = grok_client.get_grok_session_usage_by_model()
    assert by_model["gemini-3.1-flash-lite"]["input_tokens"] == 5


def test_grok_llm_includes_system_prompt(monkeypatch):
    grok_client.reset_grok_session()
    monkeypatch.setattr(
        "primr.config.models.PrimrModels.get_model_config",
        lambda model: SimpleNamespace(provider="xai"),
    )

    captured = {}

    class _Prov:
        _client = None

        def chat(self, messages, **kwargs):
            captured["messages"] = messages
            return SimpleNamespace(
                text="ok", input_tokens=1, output_tokens=1, cached_input_tokens=0
            )

    monkeypatch.setattr(grok_client, "_get_provider", lambda: _Prov())
    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: object())

    out = grok_client.grok_llm("user prompt", system_prompt="be terse")
    assert out == "ok"
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user"]


# ---------------------------------------------------------------------------
# ContinuousReasoningSession.approx_context_tokens
# ---------------------------------------------------------------------------


def test_approx_context_tokens_heuristic():
    session = grok_client.ContinuousReasoningSession(model="grok-4.3")
    session.history.append({"role": "user", "content": "x" * 400})
    # 400 chars / 4 = 100
    assert session.approx_context_tokens == 100


# ---------------------------------------------------------------------------
# grok_browse_and_summarize
# ---------------------------------------------------------------------------


def test_browse_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert grok_client.grok_browse_and_summarize("https://example.com") is None


def _resp(status=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text
    if json_data is None:
        r.json.side_effect = ValueError("no json")
    else:
        r.json.return_value = json_data
    return r


def test_browse_success_parses_text_and_citations(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "fake")
    grok_client.reset_grok_session()

    data = {
        "output": [
            {"type": "web_search_call"},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Summary body.",
                        "annotations": [
                            {"type": "url_citation", "url": "https://a.example"},
                            {"type": "url_citation", "url": "https://a.example"},
                            {"type": "url_citation", "url": "https://b.example"},
                        ],
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 7, "output_tokens": 4},
    }
    import httpx

    import primr.ai.grok_client as gc

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(json_data=data))

    result = gc.grok_browse_and_summarize("https://example.com", context="extra")
    assert result is not None
    assert result["text"] == "Summary body."
    assert result["citations"] == ["https://a.example", "https://b.example"]
    assert result["tool_calls"] == 1
    assert result["source_url"] == "https://example.com"
    # usage tracked
    assert grok_client.get_grok_session_usage()["input_tokens"] == 7


def test_browse_non_200_returns_none(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "fake")
    import httpx

    import primr.ai.grok_client as gc

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(status=500, text="boom"))
    assert gc.grok_browse_and_summarize("https://example.com") is None


def test_browse_non_json_returns_none(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "fake")
    import httpx

    import primr.ai.grok_client as gc

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(json_data=None))
    assert gc.grok_browse_and_summarize("https://example.com") is None


def test_browse_empty_body_returns_none(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "fake")
    import httpx

    import primr.ai.grok_client as gc

    data = {"output": [{"type": "message", "content": [{"type": "text", "text": "   "}]}]}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _resp(json_data=data))
    assert gc.grok_browse_and_summarize("https://example.com") is None


def test_browse_network_error_returns_none(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "fake")
    import httpx

    import primr.ai.grok_client as gc

    def _raise(*a, **k):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "post", _raise)
    assert gc.grok_browse_and_summarize("https://example.com") is None
