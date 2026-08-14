from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from primr.ai.providers.base import QuotaExhaustedError
from primr.ai.providers.registry import build_provider, list_known_providers
from primr.ai.providers.xai import BrowseSummary, XAIProvider


def _response(status: int = 200, json_data=None, text: str = ""):
    response = MagicMock()
    response.status_code = status
    response.text = text
    if json_data is None:
        response.json.side_effect = ValueError("no json")
    else:
        response.json.return_value = json_data
    return response


def test_browse_summary_public_dict_excludes_usage_fields() -> None:
    summary = BrowseSummary(
        text="body",
        citations=("https://a.example",),
        source_url="https://example.com",
        tool_calls=1,
        input_tokens=10,
        output_tokens=3,
        cached_input_tokens=4,
    )

    assert summary.to_public_dict() == {
        "text": "body",
        "citations": ["https://a.example"],
        "source_url": "https://example.com",
        "tool_calls": 1,
    }


def test_xai_browse_skips_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    assert (
        XAIProvider().browse_and_summarize(
            "https://example.com",
            model="grok-4.3",
        )
        is None
    )


def test_registry_builds_xai_provider() -> None:
    xai_entry = next(entry for entry in list_known_providers() if entry.name == "xai")

    assert isinstance(build_provider(xai_entry), XAIProvider)


def test_xai_browse_posts_to_responses_api_and_records_usage(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
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
        "usage": {
            "input_tokens": 7,
            "output_tokens": 4,
            "input_tokens_details": {"cached_tokens": 2},
            "cost_in_usd_ticks": 25_000_000,
        },
    }
    captured = {}

    def fake_post(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _response(json_data=data)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = XAIProvider()

    result = provider.browse_and_summarize(
        "https://example.com",
        context="extra",
        model="grok-4.3",
        max_tokens=123,
        timeout=5.0,
    )

    assert result == BrowseSummary(
        text="Summary body.",
        citations=("https://a.example", "https://b.example"),
        source_url="https://example.com",
        tool_calls=1,
        input_tokens=7,
        output_tokens=4,
        cached_input_tokens=2,
        actual_cost_usd=0.0025,
    )
    assert captured["args"] == ("https://api.x.ai/v1/responses",)
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer fake"
    assert captured["kwargs"]["json"]["model"] == "grok-4.3"
    assert captured["kwargs"]["json"]["max_output_tokens"] == 123
    assert captured["kwargs"]["json"]["store"] is False
    assert "Additional context: extra" in captured["kwargs"]["json"]["input"]
    assert captured["kwargs"]["timeout"] == 5.0
    assert provider.get_usage() == {
        "input_tokens": 7,
        "output_tokens": 4,
        "cached_input_tokens": 2,
    }


def test_xai_chat_uses_responses_api_without_storage_and_tracks_exact_cost() -> None:
    provider = XAIProvider()
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(
        output_text="analysis",
        usage=SimpleNamespace(
            input_tokens=200,
            output_tokens=50,
            input_tokens_details=SimpleNamespace(cached_tokens=125),
            cost_in_usd_ticks=75_000_000,
        ),
    )
    provider._client = client

    result = provider.chat(
        [{"role": "user", "content": "Research this company"}],
        model="grok-4.6",
        max_tokens=800,
        reasoning_effort="xhigh",
        prompt_cache_key="run-123",
    )

    assert result.text == "analysis"
    assert result.input_tokens == 200
    assert result.output_tokens == 50
    assert result.cached_input_tokens == 125
    assert result.actual_cost_usd == 0.0075
    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == "grok-4.6"
    assert kwargs["input"] == [{"role": "user", "content": "Research this company"}]
    assert kwargs["max_output_tokens"] == 800
    assert kwargs["store"] is False
    assert kwargs["reasoning"] == {"effort": "xhigh"}
    assert kwargs["extra_body"] == {"prompt_cache_key": "run-123"}
    client.chat.completions.create.assert_not_called()


def test_xai_browse_returns_none_for_transport_failures(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    monkeypatch.setattr("primr.ai.providers.xai.time.sleep", lambda _delay: None)

    def fail(*_args, **_kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "post", fail)

    assert (
        XAIProvider().browse_and_summarize(
            "https://example.com",
            model="grok-4.3",
        )
        is None
    )


def test_xai_browse_returns_none_for_bad_responses(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    monkeypatch.setattr("primr.ai.providers.xai.time.sleep", lambda _delay: None)
    provider = XAIProvider()

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: _response(status=500))
    assert provider.browse_and_summarize("https://example.com", model="grok-4.3") is None

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: _response(json_data=None))
    assert provider.browse_and_summarize("https://example.com", model="grok-4.3") is None

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: _response(
            json_data={
                "output": [{"type": "message", "content": [{"type": "text", "text": "   "}]}]
            }
        ),
    )
    assert provider.browse_and_summarize("https://example.com", model="grok-4.3") is None


def test_xai_browse_retries_429_with_retry_after(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    first = _response(status=429)
    first.headers = {"Retry-After": "3"}
    responses = iter(
        [
            first,
            _response(
                json_data={
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "Summary body."}],
                        }
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                }
            ),
        ]
    )
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: next(responses))
    slept: list[float] = []
    monkeypatch.setattr("primr.ai.providers.xai.time.sleep", slept.append)

    result = XAIProvider().browse_and_summarize(
        "https://example.com",
        model="grok-4.3",
        retries=1,
    )

    assert result is not None
    assert result.text == "Summary body."
    assert slept == [3.0]


def test_xai_browse_retries_network_error(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    calls = 0

    def post(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection failed")
        return _response(
            json_data={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Recovered."}],
                    }
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr("primr.ai.providers.xai.time.sleep", lambda _delay: None)

    result = XAIProvider().browse_and_summarize(
        "https://example.com",
        model="grok-4.3",
        retries=1,
    )

    assert result is not None
    assert result.text == "Recovered."
    assert calls == 2


def test_xai_browse_billing_exhaustion_is_non_retryable(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    response = _response(status=402, text="insufficient credits")
    response.headers = {}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(httpx, "post", post)

    with pytest.raises(QuotaExhaustedError, match="credits exhausted"):
        XAIProvider().browse_and_summarize(
            "https://example.com",
            model="grok-4.3",
            retries=2,
        )

    assert post.call_count == 1


def test_xai_browse_preserves_usage_for_incomplete_empty_response(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: _response(
            json_data={
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [{"type": "web_search_call"}],
                "usage": {
                    "input_tokens": 9,
                    "output_tokens": 1,
                    "cost_in_usd_ticks": 20_000_000,
                },
            }
        ),
    )
    provider = XAIProvider()

    result = provider.browse_and_summarize(
        "https://example.com",
        model="grok-4.3",
    )

    assert result is not None
    assert result.text == ""
    assert result.response_status == "incomplete"
    assert result.incomplete_reason == "max_output_tokens"
    assert result.actual_cost_usd == pytest.approx(0.002)
    assert provider.get_usage()["input_tokens"] == 9


def test_xai_browse_logs_redacted_url_without_provider_body(monkeypatch, caplog) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    caplog.set_level(logging.WARNING, logger="primr.ai.providers.xai")
    url = "https://user:pass@example.com/private/path?token=secret#frag"

    monkeypatch.setattr(
        httpx,
        "post",
        lambda *_args, **_kwargs: _response(
            status=500,
            text="provider body with secret details",
        ),
    )

    assert XAIProvider().browse_and_summarize(url, model="grok-4.3") is None

    messages = "\n".join(caplog.messages)
    assert "https://example.com" in messages
    assert "/private/path" not in messages
    assert "token=secret" not in messages
    assert "user:pass" not in messages
    assert "provider body" not in messages


def test_xai_browse_success_log_uses_low_detail_url(monkeypatch, caplog) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")
    caplog.set_level(logging.INFO, logger="primr.ai.providers.xai")
    data = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Summary body."}],
            }
        ],
    }
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: _response(json_data=data))

    result = XAIProvider().browse_and_summarize(
        "https://example.com/customer/research?account=secret",
        model="grok-4.3",
    )

    assert result is not None
    messages = "\n".join(caplog.messages)
    assert "https://example.com" in messages
    assert "/customer/research" not in messages
    assert "account=secret" not in messages
