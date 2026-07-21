"""Coverage tests for primr.ai.providers.gemini.

Targets availability, lazy client init errors, streaming path, empty-response
RuntimeError, rate-limit retry then success, generic-error retry, exhausted
retries, and usage extraction edge cases. SDK calls are mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.providers import QuotaExhaustedError
from primr.ai.providers.base import ProviderUnavailableError
from primr.ai.providers.gemini import GeminiProvider, _is_rate_limited


def _provider():
    return GeminiProvider()


def _resp(text="reply", in_tok=10, out_tok=5):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(prompt_token_count=in_tok, candidates_token_count=out_tok),
    )


# ---------------------------------------------------------------------------
# Availability + lazy init
# ---------------------------------------------------------------------------


def test_is_available_true_with_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert _provider().is_available() is True


def test_is_available_false_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert _provider().is_available() is False


def test_get_client_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ProviderUnavailableError, match="not set"):
        _provider()._get_client()


def test_get_client_caches(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    p = _provider()
    sentinel = object()
    p._client = sentinel
    assert p._get_client() is sentinel


def test_get_client_import_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    p = _provider()
    with (
        patch("primr.ai.providers.gemini._GENAI_IMPORT_ERROR", ImportError("no genai")),
        pytest.raises(ProviderUnavailableError, match="not available"),
    ):
        p._get_client()


# ---------------------------------------------------------------------------
# chat success / streaming
# ---------------------------------------------------------------------------


def test_chat_no_contents_raises():
    p = _provider()
    p._client = MagicMock()
    with pytest.raises(RuntimeError, match="at least one non-system message"):
        p.chat([{"role": "system", "content": "only system"}], model="gemini-3-flash")


def test_chat_success():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.return_value = _resp()
    p._client = fake
    result = p.chat(
        [{"role": "user", "content": "hi"}],
        model="gemini-3-flash",
        max_tokens=1_234,
    )
    assert result.text == "reply"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    config = fake.models.generate_content.call_args.kwargs["config"]
    assert config.max_output_tokens == 1_234


def test_chat_streaming():
    p = _provider()
    fake = MagicMock()
    chunks = [SimpleNamespace(text="he"), SimpleNamespace(text="llo"), SimpleNamespace(text=None)]
    fake.models.generate_content_stream.return_value = iter(chunks)
    p._client = fake
    result = p.chat([{"role": "user", "content": "hi"}], model="gemini-3-flash", streaming=True)
    assert result.text == "hello"
    # Streaming path has no usage_metadata -> zero tokens
    assert result.input_tokens == 0


def test_chat_empty_response_retries_and_fails():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.return_value = SimpleNamespace(text="", usage_metadata=None)
    p._client = fake
    with (
        patch("primr.ai.providers.gemini.time.sleep"),
        pytest.raises(RuntimeError, match="failed after"),
    ):
        p.chat([{"role": "user", "content": "hi"}], model="gemini-3-flash", retries=1)


# ---------------------------------------------------------------------------
# error handling: quota / rate limit / generic
# ---------------------------------------------------------------------------


def test_chat_daily_quota_raises():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.side_effect = Exception(
        "RESOURCE_EXHAUSTED quota exceeded per_day"
    )
    p._client = fake
    with pytest.raises(QuotaExhaustedError):
        p.chat([{"role": "user", "content": "x"}], model="gemini-3-flash", retries=0)


def test_quota_guidance_is_provider_owned():
    guidance = _provider().quota_guidance()

    assert guidance.headline == "[QUOTA EXHAUSTED] Daily API limit reached."
    assert "Gemini daily API quota exhausted" in guidance.log_message
    assert "https://ai.google.dev" in guidance.options[1]
    assert guidance.error_message == "[ERROR] Daily API quota exhausted. Cannot continue."


def test_chat_rate_limited_retries_then_succeeds():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.side_effect = [
        Exception("429 too many requests"),
        _resp(text="recovered"),
    ]
    p._client = fake
    with patch("primr.ai.providers.gemini.time.sleep"):
        result = p.chat([{"role": "user", "content": "x"}], model="gemini-3-flash", retries=3)
    assert result.text == "recovered"


def test_chat_rate_limited_exhausts_retries():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.side_effect = Exception("429 rate limited")
    p._client = fake
    with (
        patch("primr.ai.providers.gemini.time.sleep"),
        pytest.raises(RuntimeError, match="failed after"),
    ):
        p.chat([{"role": "user", "content": "x"}], model="gemini-3-flash", retries=1)


def test_chat_generic_error_retries_then_succeeds():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.side_effect = [
        Exception("transient blip"),
        _resp(text="ok"),
    ]
    p._client = fake
    with patch("primr.ai.providers.gemini.time.sleep"):
        result = p.chat([{"role": "user", "content": "x"}], model="gemini-3-flash", retries=2)
    assert result.text == "ok"


def test_chat_generic_error_exhausts():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.side_effect = Exception("persistent failure")
    p._client = fake
    with (
        patch("primr.ai.providers.gemini.time.sleep"),
        pytest.raises(RuntimeError, match="failed after"),
    ):
        p.chat([{"role": "user", "content": "x"}], model="gemini-3-flash", retries=1)


# ---------------------------------------------------------------------------
# _extract_usage / classifiers
# ---------------------------------------------------------------------------


def test_extract_usage_none_response():
    assert GeminiProvider._extract_usage(None) == (0, 0, 0)


def test_extract_usage_no_metadata():
    assert GeminiProvider._extract_usage(SimpleNamespace(usage_metadata=None)) == (0, 0, 0)


def test_extract_usage_values():
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(prompt_token_count=7, candidates_token_count=3)
    )
    assert GeminiProvider._extract_usage(resp) == (7, 3, 0)


def test_extract_usage_cached_tokens():
    resp = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=10,
            candidates_token_count=4,
            cached_content_token_count=6,
        )
    )
    assert GeminiProvider._extract_usage(resp) == (10, 4, 6)


def test_rate_limited_false_for_daily():
    assert _is_rate_limited(Exception("resource_exhausted per_day")) is False


# ---------------------------------------------------------------------------
# Grounded web search (search_and_summarize)
# ---------------------------------------------------------------------------


def _grounded_resp(text="brief", queries=("q1",), uris=("https://x",), in_tok=900, out_tok=1800):
    chunks = [SimpleNamespace(web=SimpleNamespace(uri=u)) for u in uris]
    cand = SimpleNamespace(
        grounding_metadata=SimpleNamespace(
            web_search_queries=list(queries), grounding_chunks=chunks
        )
    )
    return SimpleNamespace(
        text=text,
        candidates=[cand],
        usage_metadata=SimpleNamespace(prompt_token_count=in_tok, candidates_token_count=out_tok),
    )


def test_search_and_summarize_returns_grounded_result_with_evidence():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.return_value = _grounded_resp()
    p._client = fake
    result = p.search_and_summarize(
        "latest AWS AI", model="gemini-3.1-pro-preview", max_tokens=8_000
    )
    assert result is not None
    assert result.text == "brief"
    assert result.search_queries == ("q1",)
    assert result.citations == ("https://x",)
    assert result.input_tokens == 900
    assert result.output_tokens == 1800
    # The live google_search grounding tool must be attached.
    config = fake.models.generate_content.call_args.kwargs["config"]
    assert config.tools
    assert config.max_output_tokens == 8_000


def test_search_and_summarize_empty_body_returns_none():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.return_value = _grounded_resp(text="   ")
    p._client = fake
    assert p.search_and_summarize("q", model="gemini-3.1-pro-preview") is None


def test_search_and_summarize_tolerates_missing_grounding_metadata():
    p = _provider()
    fake = MagicMock()
    fake.models.generate_content.return_value = SimpleNamespace(
        text="body",
        candidates=[SimpleNamespace(grounding_metadata=None)],
        usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=2),
    )
    p._client = fake
    result = p.search_and_summarize("q", model="gemini-3.1-pro-preview")
    assert result is not None
    assert result.text == "body"
    assert result.citations == ()
    assert result.search_queries == ()


# ---------------------------------------------------------------------------
# Credential validation (auth-only, free models.list)
# ---------------------------------------------------------------------------


def test_validate_credentials_ok(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    p = _provider()
    fake = MagicMock()
    fake.models.list.return_value = iter([object(), object(), object()])
    p._client = fake
    result = p.validate_credentials()
    assert result.ok is True
    assert result.provider == "gemini"
    assert "3 models" in result.detail
    fake.models.list.assert_called_once()


def test_validate_credentials_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = _provider().validate_credentials()
    assert result.ok is False
    assert "not set" in result.detail


def test_validate_credentials_reports_auth_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    p = _provider()
    fake = MagicMock()
    fake.models.list.side_effect = RuntimeError("invalid api key")
    p._client = fake
    result = p.validate_credentials()
    assert result.ok is False
    assert "RuntimeError" in result.detail
