"""Coverage tests for primr.ai.providers.openai_compatible.

Targets the error-classification helpers, retry-after extraction, backoff math,
the openai-vs-other max_tokens branch, cached-token extraction (xAI + OpenAI
shapes), retry-after-driven sleep, and the no-usage path. SDK calls mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primr.ai.providers.base import ProviderUnavailableError, QuotaExhaustedError
from primr.ai.providers.openai_compatible import (
    OpenAICompatibleProvider,
    _compute_backoff_delay,
    _extract_retry_after_seconds,
    _is_retryable_error,
)


def _make(name="testprov", **kw):
    return OpenAICompatibleProvider(
        name=name,
        base_url="https://example.test/v1",
        api_key_env="TEST_OAI_KEY",
        api_key_default="key",
        **kw,
    )


def _resp(text="hi", prompt=10, completion=5, cached=0, openai_shape=False):
    if openai_shape:
        usage = SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        )
    else:
        usage = SimpleNamespace(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
        )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Classifier helpers
# ---------------------------------------------------------------------------


def test_is_retryable_markers():
    assert _is_retryable_error(Exception("503 service unavailable")) is True
    assert _is_retryable_error(Exception("connection refused")) is True


def test_is_retryable_false_for_billing(monkeypatch):
    monkeypatch.setattr(
        "primr.ai.providers.openai_compatible._is_billing_exhausted",
        lambda e: True,
    )
    assert _is_retryable_error(Exception("429")) is False


def test_extract_retry_after_header():
    err = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "8"}))
    assert _extract_retry_after_seconds(err) == 8.0


def test_extract_retry_after_message():
    assert _extract_retry_after_seconds(Exception("retry after 15")) == 15.0


def test_extract_retry_after_none():
    assert _extract_retry_after_seconds(Exception("no info")) is None


def test_compute_backoff_bounds():
    d = _compute_backoff_delay(0)
    assert 5.0 <= d <= 6.0


# ---------------------------------------------------------------------------
# Lazy init
# ---------------------------------------------------------------------------


def test_get_client_missing_key_raises(monkeypatch):
    # The key-check branch is only reachable once `import openai` succeeds, so
    # this assertion only applies when the optional 'openai' package is present
    # (it is not installed in CI's default extras).
    pytest.importorskip("openai")
    monkeypatch.delenv("ABSENT_OAI_KEY", raising=False)
    p = OpenAICompatibleProvider(name="x", base_url="u", api_key_env="ABSENT_OAI_KEY")
    with pytest.raises(ProviderUnavailableError, match="not set"):
        p._get_client()


def test_get_client_missing_openai_package_raises(monkeypatch):
    """The ImportError branch fires when 'openai' is not installed. Simulated by
    blocking the import so this covers the branch regardless of the environment."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("simulated: openai not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    p = OpenAICompatibleProvider(name="x", base_url="u", api_key_env="ANY_KEY")
    with pytest.raises(ProviderUnavailableError, match="openai"):
        p._get_client()


# ---------------------------------------------------------------------------
# max_tokens param branch
# ---------------------------------------------------------------------------


def test_openai_uses_max_completion_tokens():
    p = _make(name="openai")
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp()
    p._client = fake
    p.chat([{"role": "user", "content": "x"}], model="gpt-5", max_tokens=1234)
    kwargs = fake.chat.completions.create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == 1234
    assert "max_tokens" not in kwargs


def test_non_openai_uses_max_tokens():
    p = _make(name="xai")
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp()
    p._client = fake
    p.chat([{"role": "user", "content": "x"}], model="grok-4.3", max_tokens=999)
    kwargs = fake.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 999


# ---------------------------------------------------------------------------
# cached-token extraction
# ---------------------------------------------------------------------------


def test_cached_tokens_xai_shape():
    p = _make(name="xai")
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(cached=4)
    p._client = fake
    p.chat([{"role": "user", "content": "x"}], model="grok-4.3")
    assert p.get_usage()["cached_input_tokens"] == 4


def test_cached_tokens_openai_shape():
    p = _make(name="openai")
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(cached=6, openai_shape=True)
    p._client = fake
    p.chat([{"role": "user", "content": "x"}], model="gpt-5")
    assert p.get_usage()["cached_input_tokens"] == 6


def test_no_usage_records_nothing():
    p = _make(name="xai")
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
        usage=None,
    )
    p._client = fake
    result = p.chat([{"role": "user", "content": "x"}], model="grok-4.3")
    assert result.text == "hi"
    assert p.get_usage()["input_tokens"] == 0


def test_none_message_content_returns_empty_string():
    p = _make(name="xai")
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
        usage=None,
    )
    p._client = fake
    result = p.chat([{"role": "user", "content": "x"}], model="grok-4.3")
    assert result.text == ""


# ---------------------------------------------------------------------------
# retry-after driven sleep
# ---------------------------------------------------------------------------


def test_retry_after_header_drives_sleep():
    p = _make(name="xai")
    fake = MagicMock()

    err = RuntimeError("429 rate limit")
    err.response = SimpleNamespace(headers={"retry-after": "3"})
    fake.chat.completions.create.side_effect = [err, _resp(text="ok")]
    p._client = fake

    slept = []
    with patch(
        "primr.ai.providers.openai_compatible.time.sleep",
        lambda d: slept.append(d),
    ):
        result = p.chat([{"role": "user", "content": "x"}], model="grok-4.3", retries=2)
    assert result.text == "ok"
    assert slept == [3.0]


# ---------------------------------------------------------------------------
# billing exhausted with help link
# ---------------------------------------------------------------------------


def test_billing_exhausted_includes_help_link():
    p = _make(name="xai", billing_help_url="https://console.x.ai/")
    fake = MagicMock()
    fake.chat.completions.create.side_effect = RuntimeError("402 credits")
    p._client = fake
    with (
        patch(
            "primr.ai.providers.openai_compatible._is_billing_exhausted",
            return_value=True,
        ),
        pytest.raises(QuotaExhaustedError, match=r"console\.x\.ai"),
    ):
        p.chat([{"role": "user", "content": "x"}], model="grok-4.3", retries=2)


def test_billing_exhausted_no_help_link():
    p = _make(name="xai")
    fake = MagicMock()
    fake.chat.completions.create.side_effect = RuntimeError("402 credits")
    p._client = fake
    with (
        patch(
            "primr.ai.providers.openai_compatible._is_billing_exhausted",
            return_value=True,
        ),
        pytest.raises(QuotaExhaustedError, match="credits exhausted"),
    ):
        p.chat([{"role": "user", "content": "x"}], model="grok-4.3", retries=2)
