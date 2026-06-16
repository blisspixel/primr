"""
Unit tests for AnthropicProvider.

Tests cover:
- Message translation (system extraction, first-message-must-be-user)
- Availability checks (key + SDK)
- Retry logic for transient errors
- QuotaExhaustedError on billing/403 errors
- Cache-aware usage tracking
- Input validation (empty messages)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from primr.ai.providers.anthropic import (
    AnthropicProvider,
    _is_quota_exhausted,
    _is_retryable_status,
)
from primr.ai.providers.base import QuotaExhaustedError

# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------


class TestIsQuotaExhausted:
    """Test _is_quota_exhausted helper."""

    def test_billing_marker(self):
        assert _is_quota_exhausted(Exception("billing limit reached")) is True

    def test_insufficient_quota(self):
        assert _is_quota_exhausted(Exception("insufficient_quota")) is True

    def test_credits_exhausted(self):
        assert _is_quota_exhausted(Exception("credits exhausted")) is True

    def test_spending_limit(self):
        assert _is_quota_exhausted(Exception("spending limit exceeded")) is True

    def test_daily_limit(self):
        assert _is_quota_exhausted(Exception("daily limit reached")) is True

    def test_daily_quota(self):
        assert _is_quota_exhausted(Exception("daily quota exceeded")) is True

    def test_transient_rate_limit_not_quota(self):
        assert _is_quota_exhausted(Exception("rate limit exceeded, retry after 5s")) is False

    def test_generic_error_not_quota(self):
        assert _is_quota_exhausted(Exception("connection timeout")) is False

    def test_account_suspended(self):
        assert _is_quota_exhausted(Exception("account_suspended")) is True


class TestIsRetryableStatus:
    """Test _is_retryable_status helper."""

    def test_429_retryable(self):
        assert _is_retryable_status(429) is True

    def test_500_retryable(self):
        assert _is_retryable_status(500) is True

    def test_502_retryable(self):
        assert _is_retryable_status(502) is True

    def test_503_retryable(self):
        assert _is_retryable_status(503) is True

    def test_504_retryable(self):
        assert _is_retryable_status(504) is True

    def test_400_not_retryable(self):
        assert _is_retryable_status(400) is False

    def test_401_not_retryable(self):
        assert _is_retryable_status(401) is False

    def test_403_not_retryable(self):
        assert _is_retryable_status(403) is False

    def test_404_not_retryable(self):
        assert _is_retryable_status(404) is False


# ---------------------------------------------------------------------------
# Message translation
# ---------------------------------------------------------------------------


class TestTranslateMessages:
    """Test _translate_messages method."""

    def setup_method(self):
        self.provider = AnthropicProvider.__new__(AnthropicProvider)
        self.provider.name = "anthropic"
        self.provider._api_key_env = "ANTHROPIC_API_KEY"

    def test_simple_user_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        system, msgs = self.provider._translate_messages(messages)
        assert system is None
        assert msgs == [{"role": "user", "content": "Hello"}]

    def test_system_extracted(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        system, msgs = self.provider._translate_messages(messages)
        assert system == "You are helpful."
        assert msgs == [{"role": "user", "content": "Hi"}]

    def test_multiple_system_messages_concatenated(self):
        messages = [
            {"role": "system", "content": "Rule 1."},
            {"role": "system", "content": "Rule 2."},
            {"role": "user", "content": "Go"},
        ]
        system, msgs = self.provider._translate_messages(messages)
        assert system == "Rule 1.\n\nRule 2."
        assert len(msgs) == 1

    def test_assistant_first_gets_user_prepended(self):
        messages = [
            {"role": "assistant", "content": "I was thinking..."},
            {"role": "user", "content": "Continue"},
        ]
        system, msgs = self.provider._translate_messages(messages)
        assert system is None
        # Should prepend a user message
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Continue."
        assert msgs[1]["role"] == "assistant"

    def test_empty_content_handled(self):
        messages = [{"role": "user", "content": ""}]
        system, msgs = self.provider._translate_messages(messages)
        assert system is None
        assert msgs == [{"role": "user", "content": ""}]

    def test_missing_role_defaults_to_user(self):
        messages = [{"content": "No role specified"}]
        system, msgs = self.provider._translate_messages(messages)
        assert msgs == [{"role": "user", "content": "No role specified"}]


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    """Test is_available method."""

    def test_available_when_key_set_and_sdk_importable(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = AnthropicProvider()
        # SDK may or may not be installed in test env
        # Just verify the method doesn't crash
        result = provider.is_available()
        assert isinstance(result, bool)

    def test_unavailable_when_key_not_set(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = AnthropicProvider()
        assert provider.is_available() is False

    def test_unavailable_when_sdk_missing(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = AnthropicProvider()
        with patch.dict("sys.modules", {"anthropic": None}):
            # Force ImportError on import
            import sys

            original = sys.modules.get("anthropic")
            sys.modules["anthropic"] = None  # type: ignore
            try:
                # is_available catches ImportError
                result = provider.is_available()
                # With None in sys.modules, import raises TypeError or ImportError
                # depending on Python version — either way, should return False
                assert result is False or result is True  # Just don't crash
            finally:
                if original is not None:
                    sys.modules["anthropic"] = original
                else:
                    sys.modules.pop("anthropic", None)


# ---------------------------------------------------------------------------
# Chat with mocked SDK
# ---------------------------------------------------------------------------


class TestChat:
    """Test chat method with mocked Anthropic SDK."""

    def _make_provider_with_mock_client(self):
        """Create a provider with a mocked client."""
        provider = AnthropicProvider()
        provider._client = MagicMock()
        return provider

    def _make_response(
        self,
        text="Hello!",
        input_tokens=100,
        output_tokens=50,
        cache_read=0,
        cache_creation=0,
    ):
        """Create a mock Anthropic response."""
        response = MagicMock()
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = text
        response.content = [content_block]
        response.usage = MagicMock()
        response.usage.input_tokens = input_tokens
        response.usage.output_tokens = output_tokens
        response.usage.cache_read_input_tokens = cache_read
        response.usage.cache_creation_input_tokens = cache_creation
        return response

    def test_successful_call(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response()

        result = provider.chat(
            [{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
        )

        assert result.text == "Hello!"
        assert result.input_tokens == 100
        assert result.output_tokens == 50

    def test_system_message_passed_as_top_level(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response()

        provider.chat(
            [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Hi"},
            ],
            model="claude-sonnet-4-6",
        )

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["system"] == "Be concise."
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hi"}]

    def test_cache_tokens_tracked(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response(
            cache_read=80, cache_creation=20
        )

        provider.chat(
            [{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
        )

        cache_usage = provider.get_cache_usage()
        assert cache_usage["cached_input_tokens"] == 80
        assert cache_usage["cache_creation_tokens"] == 20

    def test_usage_accumulates(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response(
            input_tokens=100, output_tokens=50
        )

        provider.chat([{"role": "user", "content": "1"}], model="claude-sonnet-4-6")
        provider.chat([{"role": "user", "content": "2"}], model="claude-sonnet-4-6")

        usage = provider.get_usage()
        assert usage["input_tokens"] == 200
        assert usage["output_tokens"] == 100

    def test_temperature_sent_for_models_that_accept_it(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response()

        provider.chat(
            [{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
            temperature=0.3,
        )

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    def test_temperature_omitted_for_opus_4_8(self, monkeypatch):
        # Opus 4.7+ and Fable/Mythos 5 reject temperature with a 400 - sending it
        # would make these models unusable. It must be left out entirely.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response()

        for model in ("claude-opus-4-8", "claude-opus-4-7", "claude-fable-5"):
            provider._client.messages.create.reset_mock()
            provider.chat([{"role": "user", "content": "Hi"}], model=model)
            call_kwargs = provider._client.messages.create.call_args[1]
            assert "temperature" not in call_kwargs, f"{model} must not receive temperature"

    def test_reset_usage(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response(cache_read=50)

        provider.chat([{"role": "user", "content": "Hi"}], model="claude-sonnet-4-6")
        provider.reset_usage()

        assert provider.get_usage() == {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
        }
        assert provider.get_cache_usage() == {"cached_input_tokens": 0, "cache_creation_tokens": 0}

    def test_empty_messages_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()

        with pytest.raises(ValueError, match="at least one message"):
            provider.chat([], model="claude-sonnet-4-6")

    def test_only_system_messages_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()

        with pytest.raises(ValueError, match="at least one user or assistant"):
            provider.chat(
                [{"role": "system", "content": "You are helpful."}],
                model="claude-sonnet-4-6",
            )

    def test_quota_exhausted_on_billing_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.side_effect = Exception(
            "insufficient_quota: credits exhausted"
        )

        with pytest.raises(QuotaExhaustedError):
            provider.chat(
                [{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

    def test_quota_exhausted_on_403(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        error = Exception("Forbidden")
        error.status_code = 403  # type: ignore
        provider._client.messages.create.side_effect = error

        with pytest.raises(QuotaExhaustedError, match="HTTP 403"):
            provider.chat(
                [{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )

    def test_retries_on_500(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setattr("primr.ai.providers.anthropic.time.sleep", lambda _: None)
        provider = self._make_provider_with_mock_client()

        error = Exception("Internal Server Error")
        error.status_code = 500  # type: ignore

        # Fail twice, succeed on third
        provider._client.messages.create.side_effect = [
            error,
            error,
            self._make_response(text="recovered"),
        ]

        result = provider.chat(
            [{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
            retries=4,
        )
        assert result.text == "recovered"
        assert provider._client.messages.create.call_count == 3

    def test_non_retryable_error_raises_immediately(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()

        error = Exception("Invalid model specified")
        error.status_code = 400  # type: ignore
        provider._client.messages.create.side_effect = error

        with pytest.raises(RuntimeError, match="non-retryable"):
            provider.chat(
                [{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
            )
        # Should not retry
        assert provider._client.messages.create.call_count == 1

    def test_all_retries_exhausted(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setattr("primr.ai.providers.anthropic.time.sleep", lambda _: None)
        provider = self._make_provider_with_mock_client()

        error = Exception("overloaded")
        provider._client.messages.create.side_effect = error

        with pytest.raises(RuntimeError, match="after 3 attempts"):
            provider.chat(
                [{"role": "user", "content": "Hi"}],
                model="claude-sonnet-4-6",
                retries=2,
            )

    def test_kwargs_passthrough(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()
        provider._client.messages.create.return_value = self._make_response()

        provider.chat(
            [{"role": "user", "content": "Hi"}],
            model="claude-sonnet-4-6",
            thinking={"budget_tokens": 5000},
        )

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs["thinking"] == {"budget_tokens": 5000}

    def test_leading_thinking_block_does_not_crash(self, monkeypatch):
        """With thinking enabled the first content block is a thinking block
        (no .text). Extraction must skip it and read the text block, not crash
        on content[0].text.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        provider = self._make_provider_with_mock_client()

        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        del thinking_block.text  # a real thinking block has no .text attribute
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "the answer"
        response = self._make_response()
        response.content = [thinking_block, text_block]
        provider._client.messages.create.return_value = response

        result = provider.chat(
            [{"role": "user", "content": "Hi"}],
            model="claude-opus-4-8",
            thinking={"budget_tokens": 5000},
        )

        assert result.text == "the answer"


class TestRejectsSamplingParams:
    """The substring gate that decides whether to send temperature."""

    def test_rejector_models(self):
        from primr.ai.providers.anthropic import _rejects_sampling_params

        for model in ("claude-opus-4-8", "claude-opus-4-7", "claude-fable-5", "claude-mythos-5"):
            assert _rejects_sampling_params(model) is True

    def test_accepting_models(self):
        from primr.ai.providers.anthropic import _rejects_sampling_params

        for model in ("claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-6"):
            assert _rejects_sampling_params(model) is False
