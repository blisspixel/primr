"""
Tests for the provider abstraction (`primr.ai.providers`).

Step 1: standalone unit tests for the new package — no wiring into
existing client code yet. These tests pin the contract that subsequent
steps build on.
"""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.providers import (
    ChatResponse,
    OpenAICompatibleProvider,
    Provider,
    ProviderUnavailableError,
)

# Some tests below patch `openai.OpenAI` directly, which requires the optional
# `openai` package to be importable. Tests that only use the provider's own
# attributes (set ``provider._client`` directly, etc.) work without it.
_HAS_OPENAI = importlib.util.find_spec("openai") is not None
_requires_openai = pytest.mark.skipif(
    not _HAS_OPENAI, reason="openai package not installed (install primr[fast])"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_response(*, text: str, prompt_tokens: int, completion_tokens: int) -> SimpleNamespace:
    """Build the minimal openai SDK response shape the provider relies on."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


def _make_provider(api_key_default: str | None = "test-key") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="testprov",
        base_url="https://example.test/v1",
        api_key_env="TEST_PROVIDER_API_KEY",
        api_key_default=api_key_default,
    )


# ---------------------------------------------------------------------------
# ChatResponse contract
# ---------------------------------------------------------------------------


class TestChatResponse:
    def test_chat_response_is_immutable(self) -> None:
        r = ChatResponse(text="hi", input_tokens=1, output_tokens=2)
        with pytest.raises((AttributeError, TypeError)):
            r.text = "no"  # type: ignore[misc]

    def test_token_counts_default_to_zero(self) -> None:
        r = ChatResponse(text="hi")
        assert r.input_tokens == 0
        assert r.output_tokens == 0


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_available_when_default_key_provided(self) -> None:
        provider = OpenAICompatibleProvider(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key_env="OLLAMA_API_KEY",
            api_key_default="ollama-local",
        )
        assert provider.is_available() is True

    def test_available_when_env_key_set(self) -> None:
        provider = OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="TEST_PROVIDER_KEY_PRESENT",
        )
        with patch.dict("os.environ", {"TEST_PROVIDER_KEY_PRESENT": "abc"}, clear=False):
            assert provider.is_available() is True

    def test_unavailable_when_env_key_missing(self) -> None:
        provider = OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="DEFINITELY_NOT_SET_KEY",
        )
        env = {k: v for k, v in __import__("os").environ.items() if k != "DEFINITELY_NOT_SET_KEY"}
        with patch.dict("os.environ", env, clear=True):
            assert provider.is_available() is False


# ---------------------------------------------------------------------------
# Lazy client init
# ---------------------------------------------------------------------------


@_requires_openai
class TestClientInit:
    def test_lazy_init_constructs_openai_client_with_url_and_key(self) -> None:
        provider = _make_provider()
        http_client = object()
        with (
            patch("openai.DefaultHttpxClient", return_value=http_client) as mock_http_client,
            patch("openai.OpenAI") as mock_openai,
        ):
            provider._get_client()
        mock_http_client.assert_called_once_with(follow_redirects=False)
        mock_openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://example.test/v1",
            max_retries=0,
            http_client=http_client,
        )

    def test_lazy_init_caches_client(self) -> None:
        provider = _make_provider()
        with (
            patch("openai.DefaultHttpxClient", return_value=object()) as mock_http_client,
            patch("openai.OpenAI") as mock_openai,
        ):
            provider._get_client()
            provider._get_client()
        assert mock_openai.call_count == 1
        assert mock_http_client.call_count == 1

    def test_explicit_retry_cap_is_the_http_request_cap(self, monkeypatch) -> None:
        import httpx
        import openai

        from primr.ai.providers import openai_compatible

        request_count = 0

        def respond_unavailable(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                503,
                request=request,
                json={"error": {"message": "service unavailable", "type": "server_error"}},
            )

        with httpx.Client(
            transport=httpx.MockTransport(respond_unavailable),
            follow_redirects=False,
        ) as transport_client:
            monkeypatch.setattr(
                openai,
                "DefaultHttpxClient",
                lambda **_kwargs: transport_client,
            )
            monkeypatch.setattr(openai_compatible.time, "sleep", lambda _seconds: None)
            provider = _make_provider()

            with pytest.raises(RuntimeError, match="after 2 attempts"):
                provider.chat(
                    [{"role": "user", "content": "test"}],
                    model="test-model",
                    retries=1,
                )

            assert request_count == 2

    def test_transport_does_not_follow_redirects_outside_retry_cap(self, monkeypatch) -> None:
        import httpx
        import openai

        request_count = 0

        def redirect_then_fail(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            if request.url.host == "example.test":
                return httpx.Response(
                    307,
                    request=request,
                    headers={"location": "https://redirect.test/v1/chat/completions"},
                )
            return httpx.Response(
                503,
                request=request,
                json={"error": {"message": "service unavailable", "type": "server_error"}},
            )

        with httpx.Client(
            transport=httpx.MockTransport(redirect_then_fail),
            follow_redirects=False,
        ) as transport_client:
            monkeypatch.setattr(
                openai,
                "DefaultHttpxClient",
                lambda **_kwargs: transport_client,
            )
            provider = _make_provider()

            with pytest.raises(RuntimeError):
                provider.chat(
                    [{"role": "user", "content": "test"}],
                    model="test-model",
                    retries=1,
                )

            assert request_count == 1

    def test_missing_key_raises_provider_unavailable(self) -> None:
        provider = OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="ABSENT_KEY_FOR_TESTING",
        )
        env = {k: v for k, v in __import__("os").environ.items() if k != "ABSENT_KEY_FOR_TESTING"}
        with (
            patch.dict("os.environ", env, clear=True),
            patch("openai.OpenAI"),
            pytest.raises(ProviderUnavailableError),
        ):
            provider._get_client()


# ---------------------------------------------------------------------------
# Chat call: success path
# ---------------------------------------------------------------------------


class TestChatSuccess:
    def test_returns_text_and_usage(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _stub_response(
            text="hello world", prompt_tokens=42, completion_tokens=17
        )
        provider._client = fake_client

        result = provider.chat(
            [{"role": "user", "content": "hi"}],
            model="grok-4.3",
        )

        assert isinstance(result, ChatResponse)
        assert result.text == "hello world"
        assert result.input_tokens == 42
        assert result.output_tokens == 17

    def test_records_usage_per_model(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = [
            _stub_response(text="a", prompt_tokens=10, completion_tokens=5),
            _stub_response(text="b", prompt_tokens=20, completion_tokens=8),
        ]
        provider._client = fake_client

        provider.chat([{"role": "user", "content": "x"}], model="grok-4.3")
        provider.chat([{"role": "user", "content": "y"}], model="grok-4.20-non-reasoning")

        usage = provider.get_usage_by_model()
        assert usage["grok-4.3"]["input_tokens"] == 10
        assert usage["grok-4.3"]["output_tokens"] == 5
        assert usage["grok-4.20-non-reasoning"]["input_tokens"] == 20
        assert usage["grok-4.20-non-reasoning"]["output_tokens"] == 8

        total = provider.get_usage()
        assert total["input_tokens"] == 30
        assert total["output_tokens"] == 13

    def test_reset_usage_clears_counters(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _stub_response(
            text="x", prompt_tokens=10, completion_tokens=5
        )
        provider._client = fake_client

        provider.chat([{"role": "user", "content": "x"}], model="grok-4.3")
        provider.reset_usage()

        assert provider.get_usage() == {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
        }
        assert provider.get_usage_by_model() == {}

    def test_passes_supported_sdk_kwargs(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = _stub_response(
            text="ok", prompt_tokens=1, completion_tokens=1
        )
        provider._client = fake_client

        provider.chat(
            [{"role": "user", "content": "x"}],
            model="grok-4.3",
            top_p=0.9,
            seed=42,
            unknown_kwarg="ignored",
        )

        call = fake_client.chat.completions.create.call_args
        assert call.kwargs["top_p"] == 0.9
        assert call.kwargs["seed"] == 42
        assert "unknown_kwarg" not in call.kwargs


# ---------------------------------------------------------------------------
# Chat call: empty response
# ---------------------------------------------------------------------------


class TestEmptyResponse:
    def test_no_choices_raises_after_retries(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = SimpleNamespace(choices=[], usage=None)
        provider._client = fake_client

        with pytest.raises(RuntimeError, match="testprov API call failed"):
            provider.chat(
                [{"role": "user", "content": "x"}],
                model="grok-4.3",
                retries=0,
            )


# ---------------------------------------------------------------------------
# Chat call: billing exhausted aborts immediately
# ---------------------------------------------------------------------------


class TestBillingExhausted:
    def test_billing_error_raises_without_retry(self) -> None:
        provider = OpenAICompatibleProvider(
            name="xai",
            base_url="https://api.x.ai/v1",
            api_key_env="TEST_PROVIDER_API_KEY",
            api_key_default="test-key",
            billing_help_url="https://console.x.ai/",
        )
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("402 credits exhausted")
        provider._client = fake_client

        with (
            patch(
                "primr.ai.providers.openai_compatible._is_billing_exhausted",
                return_value=True,
            ),
            pytest.raises(RuntimeError, match="credits exhausted"),
        ):
            provider.chat(
                [{"role": "user", "content": "x"}],
                model="grok-4.3",
                retries=4,
            )

        # The billing path must abort immediately — exactly one call, no retries.
        assert fake_client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Chat call: retry + non-retryable
# ---------------------------------------------------------------------------


class TestRetryBehaviour:
    def test_retries_on_429_then_succeeds(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = [
            RuntimeError("429 rate limit"),
            _stub_response(text="ok", prompt_tokens=1, completion_tokens=1),
        ]
        provider._client = fake_client

        with patch(
            "primr.ai.providers.openai_compatible._compute_backoff_delay",
            return_value=0.0,
        ):
            result = provider.chat(
                [{"role": "user", "content": "x"}],
                model="grok-4.3",
                retries=3,
            )

        assert result.text == "ok"
        assert fake_client.chat.completions.create.call_count == 2

    def test_non_retryable_error_raises_immediately(self) -> None:
        provider = _make_provider()
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("invalid model id")
        provider._client = fake_client

        with pytest.raises(RuntimeError, match="non-retryable"):
            provider.chat(
                [{"role": "user", "content": "x"}],
                model="grok-4.3",
                retries=3,
            )

        assert fake_client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# Provider ABC contract
# ---------------------------------------------------------------------------


class TestProviderABC:
    def test_provider_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            Provider("anything")  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# GeminiProvider — translation, retries, quota handling
# ---------------------------------------------------------------------------


class TestGeminiProviderMessageSplit:
    def test_separates_system_from_user(self) -> None:
        from primr.ai.providers.gemini import GeminiProvider

        sys_inst, contents = GeminiProvider._split_messages(
            [
                {"role": "system", "content": "you are an analyst"},
                {"role": "user", "content": "draft the workbook"},
            ]
        )
        assert sys_inst == "you are an analyst"
        assert contents == "draft the workbook"

    def test_no_system_returns_none(self) -> None:
        from primr.ai.providers.gemini import GeminiProvider

        sys_inst, contents = GeminiProvider._split_messages([{"role": "user", "content": "hi"}])
        assert sys_inst is None
        assert contents == "hi"

    def test_collapses_multiple_user_messages(self) -> None:
        from primr.ai.providers.gemini import GeminiProvider

        _, contents = GeminiProvider._split_messages(
            [
                {"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
            ]
        )
        assert contents == "first\n\nsecond"


class TestGeminiProviderQuotaClassifier:
    def test_daily_quota_detected(self) -> None:
        from primr.ai.providers.gemini import _is_daily_quota_exhausted

        assert _is_daily_quota_exhausted(
            Exception("RESOURCE_EXHAUSTED quota exceeded per_day limit")
        )
        assert _is_daily_quota_exhausted(Exception("resource_exhausted: per_day cap reached"))

    def test_rate_limit_distinct_from_daily(self) -> None:
        from primr.ai.providers.gemini import (
            _is_daily_quota_exhausted,
            _is_rate_limited,
        )

        rate_err = Exception("429 too many requests")
        assert _is_rate_limited(rate_err)
        assert not _is_daily_quota_exhausted(rate_err)


class TestGeminiProviderChat:
    def test_chat_returns_text_and_usage(self) -> None:
        from primr.ai.providers.gemini import GeminiProvider

        provider = GeminiProvider()
        fake_client = MagicMock()
        fake_response = SimpleNamespace(
            text="reply",
            usage_metadata=SimpleNamespace(prompt_token_count=42, candidates_token_count=17),
        )
        fake_client.models.generate_content.return_value = fake_response
        provider._client = fake_client

        result = provider.chat(
            [{"role": "user", "content": "hi"}],
            model="gemini-3-flash-preview",
        )

        assert result.text == "reply"
        assert result.input_tokens == 42
        assert result.output_tokens == 17
        assert provider.get_usage()["input_tokens"] == 42

    def test_chat_raises_quota_exhausted_on_daily_limit(self) -> None:
        from primr.ai.providers import QuotaExhaustedError
        from primr.ai.providers.gemini import GeminiProvider

        provider = GeminiProvider()
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = Exception(
            "RESOURCE_EXHAUSTED quota exceeded per_day"
        )
        provider._client = fake_client

        with pytest.raises(QuotaExhaustedError):
            provider.chat(
                [{"role": "user", "content": "x"}],
                model="gemini-3-flash-preview",
                retries=0,
            )

    def test_chat_passes_thinking_level_through_kwargs(self) -> None:
        from primr.ai.providers.gemini import GeminiProvider

        provider = GeminiProvider()
        fake_client = MagicMock()
        fake_response = SimpleNamespace(
            text="ok",
            usage_metadata=SimpleNamespace(prompt_token_count=1, candidates_token_count=1),
        )
        fake_client.models.generate_content.return_value = fake_response
        provider._client = fake_client

        provider.chat(
            [{"role": "user", "content": "x"}],
            model="gemini-3-pro-preview",
            thinking_level="low",
        )

        call = fake_client.models.generate_content.call_args
        config = call.kwargs["config"]
        # Gemini SDK normalizes the string into a ThinkingLevel enum, but the
        # value should still round-trip to "low" case-insensitively.
        level_value = str(config.thinking_config.thinking_level).lower()
        assert "low" in level_value
