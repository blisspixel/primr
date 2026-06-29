from __future__ import annotations

from unittest.mock import MagicMock

import httpx

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
        "usage": {"input_tokens": 7, "output_tokens": 4, "cached_tokens": 2},
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
    )
    assert captured["args"] == ("https://api.x.ai/v1/responses",)
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer fake"
    assert captured["kwargs"]["json"]["model"] == "grok-4.3"
    assert captured["kwargs"]["json"]["max_output_tokens"] == 123
    assert "Additional context: extra" in captured["kwargs"]["json"]["input"]
    assert captured["kwargs"]["timeout"] == 5.0
    assert provider.get_usage() == {
        "input_tokens": 7,
        "output_tokens": 4,
        "cached_input_tokens": 2,
    }


def test_xai_browse_returns_none_for_transport_failures(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "fake")

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
