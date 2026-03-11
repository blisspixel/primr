from types import SimpleNamespace

import pytest

from primr.ai import grok_client


class _Retryable503Error(Exception):
    def __init__(
        self, message: str = "503 Service temporarily unavailable", retry_after: str | None = None
    ):
        super().__init__(message)
        headers = {"retry-after": retry_after} if retry_after is not None else {}
        self.response = SimpleNamespace(headers=headers)


class _FakeCompletions:
    def __init__(self, sequence):
        self._sequence = list(sequence)

    def create(self, **kwargs):
        item = self._sequence.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeClient:
    def __init__(self, sequence):
        self.chat = SimpleNamespace(completions=_FakeCompletions(sequence))


class _FakeResponse:
    def __init__(self, text: str):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=text))]
        self.usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)


def test_retryable_classifier_includes_503():
    assert grok_client._is_retryable_grok_error(_Retryable503Error()) is True


def test_retryable_classifier_excludes_auth_errors():
    assert grok_client._is_retryable_grok_error(Exception("401 unauthorized")) is False


def test_extract_retry_after_seconds_from_headers():
    err = _Retryable503Error(retry_after="17")
    assert grok_client._extract_retry_after_seconds(err) == 17.0


def test_grok_llm_retries_on_503_then_succeeds(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient(
        [
            _Retryable503Error(),
            _FakeResponse("ok"),
        ]
    )

    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)
    monkeypatch.setattr(grok_client.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grok_client, "_compute_backoff_delay", lambda *_args, **_kwargs: 0.0)

    out = grok_client.grok_llm("hello", retries=1)

    assert out == "ok"
    usage = grok_client.get_grok_session_usage()
    assert usage["input_tokens"] == 11
    assert usage["output_tokens"] == 7


def test_grok_llm_exhausts_retryable_errors(monkeypatch):
    grok_client.reset_grok_session()
    client = _FakeClient(
        [
            _Retryable503Error(),
            _Retryable503Error(),
        ]
    )

    monkeypatch.setattr(grok_client, "_get_grok_client", lambda: client)
    monkeypatch.setattr(grok_client.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(grok_client, "_compute_backoff_delay", lambda *_args, **_kwargs: 0.0)

    with pytest.raises(RuntimeError, match="after 2 attempts"):
        grok_client.grok_llm("hello", retries=1)
